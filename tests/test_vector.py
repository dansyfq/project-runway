"""The FAISS vector store (runway/vector.py), its place in the hybrid search, and the LangChain layer (runway/chain.py).

Most tests use a small stand-in embedder, so they need no model download and no network. The ones marked `model` use
the real bge-small model and are skipped when it can't be loaded."""

import base64
import hashlib
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

import runway.content as content
import runway.store as store
from runway import llm as llm_mod
from runway import vector
from runway.chain import RunwayRetriever, retrieve, to_anthropic, to_chunk, to_document
from runway.llm import ANSWER_SYSTEM, EXPLAIN_SYSTEM, LLM, SEARCH_SYSTEM, SUMMARY_SYSTEM, language_rule
from runway.rag import CORPUS_DIR, Chunk, Retriever, format_context, fuse, load_chunks


class FakeEmbedder:
    """Hashed bag of words: texts that share words are similar. Counts what it embeds."""

    name = "fake-bag-of-words"
    dim = 1024

    def __init__(self):
        self.embedded = 0

    def _vec(self, text):
        v = np.zeros(self.dim, dtype=np.float32)
        for w in text.lower().split():
            v[int(hashlib.md5(w.strip("?.,").encode()).hexdigest(), 16) % self.dim] += 1
        return v

    def passages(self, texts):
        self.embedded += len(texts)
        return vector._unit(np.array([self._vec(t) for t in texts]))

    def query(self, text):
        return vector._unit(np.array([self._vec(text)]))


def chunk(i, text, doc="doc"):
    return Chunk(i, doc, f"Title {doc}", "HDB", f"https://www.hdb.gov.sg/{doc}", "2026-10-16", "", text)


CHUNKS = [chunk(0, "valuation limit for cpf usage", "valuation"),
          chunk(1, "option fee deposit paid to seller", "option"),
          chunk(2, "stamp duty rates for buyers", "duty")]


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    """Committed and runtime index folders in a temp folder; similarity floor off for the bag-of-words stand-in."""
    monkeypatch.setattr(vector, "INDEX_DIR", tmp_path / "index")
    monkeypatch.setattr(vector, "runtime_dir", lambda: tmp_path / "runtime" / "index")
    monkeypatch.setattr(vector, "MIN_SIMILARITY", 0.0)
    return tmp_path


# ---------- the store on disk ----------

def test_store_is_built_saved_then_loaded_without_embedding(dirs):
    emb = FakeEmbedder()
    first = vector.FaissStore(CHUNKS, emb)
    assert first.embedded == 3 and first.index.ntotal == 3
    assert (dirs / "runtime" / "index" / "faiss.index").exists()
    meta, index = vector.read_store(dirs / "runtime" / "index")
    assert meta["model"] == emb.name and meta["count"] == 3 and meta["fingerprint"] == vector.fingerprint(first.keys)
    again = vector.FaissStore(CHUNKS, emb)
    assert again.embedded == 0 and emb.embedded == 3  # loaded from disk
    assert again.search("cpf valuation limit", 3)[0] == 0


def test_changed_passages_reuse_the_rest_and_rewrite_the_index(dirs):
    emb = FakeEmbedder()
    vector.FaissStore(CHUNKS, emb)
    changed = [*CHUNKS[:2], chunk(2, "additional buyer's stamp duty", "duty")]
    store_ = vector.FaissStore(changed, emb)
    assert store_.embedded == 1  # only the changed passage
    meta, _ = vector.read_store(dirs / "runtime" / "index")
    assert meta["fingerprint"] == vector.fingerprint(store_.keys)
    assert vector.FaissStore(changed, emb).embedded == 0


def test_committed_index_is_used_and_never_rewritten(dirs):
    emb = FakeEmbedder()
    vector.FaissStore(CHUNKS, emb, folders=[], save_to=dirs / "index")  # as `python -m runway.vector` does
    committed = (dirs / "index" / "faiss.index").read_bytes()
    assert vector.FaissStore(CHUNKS, emb).embedded == 0
    upload = [*CHUNKS, chunk(3, "lease buyback scheme", "upload")]
    assert vector.FaissStore(upload, emb).embedded == 1  # the upload; the rest come from the committed index
    assert (dirs / "index" / "faiss.index").read_bytes() == committed  # a redeploy's git pull can't clash
    assert vector.read_store(dirs / "runtime" / "index")[0]["count"] == 4


def test_a_half_written_or_stale_index_is_rebuilt(dirs):
    emb = FakeEmbedder()
    vector.FaissStore(CHUNKS, emb)
    path = dirs / "runtime" / "index" / "faiss.index"
    path.write_bytes(path.read_bytes()[:-10])  # meta.json no longer matches the index file
    assert vector.read_store(path.parent) is None
    assert vector.FaissStore(CHUNKS, emb).embedded == 3
    (path.parent / "meta.json").write_text("not json")
    assert vector.FaissStore(CHUNKS, emb).embedded == 3


def test_a_read_only_disk_still_searches(dirs):
    (dirs / "runtime").write_text("a file where the folder should be")  # mkdir fails like on a read-only disk
    s = vector.FaissStore(CHUNKS, FakeEmbedder())
    assert s.search("option fee", 1) == [1]


def test_two_sessions_building_at_once_leave_a_whole_index(dirs):
    errors = []

    def build():
        try:
            vector.FaissStore(CHUNKS, FakeEmbedder())
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=build) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert vector.read_store(dirs / "runtime" / "index")[1].ntotal == 3
    assert not list((dirs / "runtime" / "index").glob(".*.tmp"))


def test_committed_index_matches_the_model_and_is_small():
    meta, index = vector.read_store(vector.INDEX_DIR)
    assert meta["model"] == vector.MODEL and index.d == 384 and index.ntotal == meta["count"] == len(meta["chunks"])
    assert sum(p.stat().st_size for p in vector.INDEX_DIR.iterdir()) < 1_000_000
    keys = [vector.chunk_key(c, vector.MODEL) for c in load_chunks(CORPUS_DIR)]
    assert len(set(keys) & set(meta["chunks"])) >= 0.9 * len(keys), "run python -m runway.vector and commit data/index"


# ---------- hybrid search ----------

def test_rrf_fusion_order_with_the_vector_weight():
    # 1: 1/61 = .0164; 2: 1/62 + .3/62 = .0210; 3: 1/63 + .3/61 = .0208
    assert fuse([[1, 2, 3], [3, 2]], [1.0, 0.3]) == [2, 3, 1]
    assert fuse([[1, 2, 3], [3, 2]], [1.0, 1.0]) == [3, 2, 1]


def test_retriever_uses_faiss_for_vectors_and_in_the_hybrid(dirs):
    r = Retriever(CHUNKS, embedder=FakeEmbedder())
    assert r.dense is not None and r.mode == Retriever.FAISS_MODE and "vector" in r.mode
    assert r.rankings("cpf valuation limit")[1][0] == 0
    assert [c.doc for c in r.search("seller option fee", k=1, mode="vector")] == ["option"]
    assert r.search("seller option fee", k=1)[0].doc == "option"


class Broken(FakeEmbedder):
    def passages(self, texts):
        raise RuntimeError("embedding failed")


def test_failed_embedding_falls_back_to_tfidf(dirs, capsys):
    r = Retriever(CHUNKS, embedder=Broken())
    assert r.dense is None and "TF-IDF" in r.mode
    assert r.search("stamp duty rates", k=1)[0].doc == "duty"
    assert capsys.readouterr().out.count("falls back to TF-IDF") == 1


def test_a_failing_question_embedding_uses_tfidf_for_that_question(dirs):
    r = Retriever(CHUNKS, embedder=FakeEmbedder())
    r.dense.embedder.query = lambda text: (_ for _ in ()).throw(RuntimeError("onnx error"))
    assert r.search("stamp duty rates", k=1, mode="vector")[0].doc == "duty"


def test_model_that_cannot_load_is_reported_once_and_not_retried_at_once(monkeypatch, capsys):
    attempts = []

    def no_model():
        attempts.append(1)
        raise ImportError("No module named 'fastembed'")

    monkeypatch.setattr(vector, "Embedder", no_model)
    monkeypatch.setattr(vector, "_loaded", None)
    monkeypatch.setattr(vector, "_failed_at", 0.0)
    assert vector.embedder() is None and vector.embedder() is None
    assert len(attempts) == 1 and capsys.readouterr().out.count("falls back to TF-IDF") == 1
    r = Retriever(CHUNKS)
    assert r.dense is None and r.search("stamp duty", k=1)[0].doc == "duty"


def test_tfidf_backend_setting_never_loads_the_model(monkeypatch):
    monkeypatch.setattr(vector, "backend", lambda: "tfidf")
    monkeypatch.setattr(vector, "embedder", lambda: pytest.fail("model loaded"))
    r = Retriever(CHUNKS)
    assert r.dense is None and "TF-IDF" in r.mode and r.search("stamp duty", k=1)[0].doc == "duty"
    assert Retriever(CHUNKS, embedder=False).dense is None


class Slow(FakeEmbedder):
    def passages(self, texts):
        time.sleep(0.3)
        return super().passages(texts)


def test_a_slow_build_never_holds_up_the_app(dirs, monkeypatch):
    monkeypatch.setattr(vector, "WAIT_SECONDS", 0)
    r = Retriever(CHUNKS, embedder=Slow())
    assert r.dense is None and r.search("stamp duty", k=1)[0].doc == "duty"  # TF-IDF meanwhile
    assert r.dense_ready.wait(5) and r.mode == Retriever.FAISS_MODE


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(content, "RUNTIME_CORPUS", tmp_path / "corpus")
    monkeypatch.setattr(content, "RUNTIME_CONTENT", tmp_path / "content.json")
    monkeypatch.setattr(content, "get_setting", lambda name, default=None: default)
    monkeypatch.setattr(store, "db_enabled", lambda: False)
    monkeypatch.setattr(store, "r2_enabled", lambda: False)
    content.restore.cache_clear()
    rule = "Each flat may have one canine of an approved breed, licensed by the Animal and Veterinary Service. "
    pets = "# Pets in HDB flats\n\n" + rule * 3
    r = content.add_doc({"name": "pets.md", "data": base64.b64encode(pets.encode()).decode(), "title": "Pets",
                         "publisher": "HDB", "url": "https://www.hdb.gov.sg/pets"})
    assert r["ok"]
    return tmp_path


def test_an_upload_is_found_by_vectors(uploads, dirs):
    r = Retriever(load_chunks(), embedder=FakeEmbedder())
    assert r.dense is not None
    assert r.search("canine of an approved breed", k=1, mode="vector")[0].doc == "pets"
    assert r.search("canine of an approved breed", k=1, mode="keyword")[0].doc == "pets"


def model():
    emb = vector.embedder()
    if emb is None:
        pytest.skip("the embedding model can't be loaded here")
    return emb


def test_model_upload_embeds_only_the_new_passages(uploads, monkeypatch):
    emb = model()
    monkeypatch.setattr(vector, "runtime_dir", lambda: uploads / "index")
    r = Retriever(load_chunks(), embedder=emb)
    assert r.dense.embedded == len([c for c in r.chunks if c.doc == "pets"])  # the rest come from data/index
    assert r.search("Can I keep a dog in my flat?", k=1, mode="vector")[0].doc == "pets"  # "dog" is not in it
    assert (uploads / "index" / "faiss.index").exists()


def test_model_vectors_are_normalised_and_unrelated_text_is_no_match():
    emb = model()
    q = emb.query("What is the Valuation Limit?")
    assert q.shape == (1, 384) and abs(float(np.linalg.norm(q)) - 1) < 1e-4
    r = Retriever(load_chunks(CORPUS_DIR), embedder=emb)
    assert r.dense.embedded == 0  # the committed index matches the committed documents
    assert r.rankings("zzzz qqqq")[1] == []


# ---------- LangChain ----------

def test_langchain_retriever_returns_documents_with_source_metadata(dirs):
    r = Retriever(CHUNKS, embedder=FakeEmbedder())
    lc = r.as_langchain(k=2)
    assert isinstance(lc, BaseRetriever)
    docs = lc.invoke("seller option fee")
    assert all(isinstance(d, Document) for d in docs) and len(docs) == 2
    assert docs[0].metadata == {"id": 1, "doc": "option", "title": "Title option", "publisher": "HDB",
                                "url": "https://www.hdb.gov.sg/option", "retrieved": "2026-10-16", "heading": ""}
    assert [to_chunk(d) for d in docs] == r.search("seller option fee", k=2)
    keyword = lc.invoke("stamp duty", k=1, mode="keyword")
    assert [to_chunk(d) for d in keyword] == r.search("stamp duty", k=1, mode="keyword")
    assert to_chunk(to_document(CHUNKS[2])) == CHUNKS[2]


def test_retrieve_goes_through_langchain_callbacks():
    from langchain_core.callbacks import BaseCallbackHandler

    seen = []

    class Spy(BaseCallbackHandler):
        def on_retriever_end(self, documents, **kwargs):
            seen.append(len(documents))

    index = SimpleNamespace(search=lambda q, k, mode: CHUNKS[:k])
    assert retrieve(index, "anything", k=2) == CHUNKS[:2]
    RunwayRetriever(index=index, k=1).invoke("anything", config={"callbacks": [Spy()]})
    assert seen == [1]


def capturing_llm():
    sent = []
    bot = LLM.__new__(LLM)
    bot.chat_model = "test"

    def create(**kw):
        sent.append(kw)
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text="Ok [1].")])

    bot._client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    return bot, sent


def test_prompt_templates_give_the_same_requests_as_before(monkeypatch):
    """The ChatPromptTemplates reproduce the hand-built prompts exactly (system text, turns, beta parameters)."""
    monkeypatch.setattr(llm_mod, "_calls", __import__("collections").deque())
    bot, sent = capturing_llm()
    history = [{"role": "user", "content": "What is {the} HFE?"}, {"role": "assistant", "content": "A letter [1]."}]
    bot.answer("And the loan?", CHUNKS, history=history, situation="Youngest buyer age: 30", lang="zh")
    question = "And the loan?\n\n(My situation, computed by Runway: Youngest buyer age: 30)"
    assert sent[-1]["system"] == ANSWER_SYSTEM + language_rule("zh")
    assert sent[-1]["messages"] == [*history, {"role": "user", "content":
                                               f"PASSAGES:\n{format_context(CHUNKS)}\n\nQUESTION: {question}"}]
    assert sent[-1]["fallbacks"] == "default" and sent[-1]["output_config"] == {"effort": "low"} and sent[-1]["tools"]

    facts = {"Remaining lease (years)": "58", "CPF usable (% of Valuation Limit)": "80.9"}
    bot.explain(facts, CHUNKS)
    facts_text = "- Remaining lease (years): 58\n- CPF usable (% of Valuation Limit): 80.9"
    assert sent[-1]["system"] == EXPLAIN_SYSTEM
    expected = f"FACTS:\n{facts_text}\n\nRULE PASSAGES:\n{format_context(CHUNKS)}"
    assert sent[-1]["messages"] == [{"role": "user", "content": expected}]

    bot.summarise(history)
    assert sent[-1]["system"] == SUMMARY_SYSTEM
    assert sent[-1]["messages"] == [{"role": "user", "content": "USER: What is {the} HFE?\nASSISTANT: A letter [1]."}]

    bot.search_query("公积金能用多少")
    assert sent[-1]["system"] == SEARCH_SYSTEM
    assert sent[-1]["messages"] == [{"role": "user", "content": "公积金能用多少"}]


def test_to_anthropic_maps_roles():
    from langchain_core.prompts import ChatPromptTemplate

    value = ChatPromptTemplate.from_messages([("system", "S"), ("ai", "A"), ("human", "{q}")]).invoke({"q": "{x}"})
    assert to_anthropic(value) == ("S", [{"role": "assistant", "content": "A"}, {"role": "user", "content": "{x}"}])
