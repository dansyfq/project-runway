import numpy as np
import pytest

from runway.rag import Retriever, format_context, load_chunks, split_sections, window


@pytest.fixture(scope="module")
def retriever():
    return Retriever(load_chunks())


def test_corpus_has_30_plus_official_documents():
    chunks = load_chunks()
    docs = {c.doc for c in chunks}
    assert len(docs) >= 30
    assert all(c.url.startswith("https://") for c in chunks)
    assert all(len(c.text.split()) <= 160 for c in chunks)


def test_split_sections_keeps_headings():
    sections = split_sections("intro\n# A\none\n## B\ntwo")
    assert sections == [("", "intro"), ("A", "one"), ("B", "two")]


def test_window_overlaps():
    parts = window([str(i) for i in range(300)], size=160, overlap=40)
    assert parts[0][-40:] == parts[1][:40]
    assert parts[-1][-1] == "299"


@pytest.mark.parametrize(
    ("query", "expected_doc_prefix"),
    [
        ("How much CPF can I use if the lease does not cover the youngest buyer to age 95?", "cpf-faq-lease"),
        ("What is the loan-to-value limit for an HDB housing loan?", "hdb-"),
        ("How long is the HFE letter valid?", "hdb-hfe"),
        ("Proximity Housing Grant living within 4km of parents", "hdb-proximity"),
        ("Can I pay cash over valuation with CPF?", "cpf-guide-buying-financing"),
        ("buyer's stamp duty rates", "iras-"),
    ],
)
def test_keyword_retrieval_finds_expected_source(retriever, query, expected_doc_prefix):
    docs = [c.doc for c in retriever.search(query, k=5)]
    assert any(d.startswith(expected_doc_prefix) for d in docs), docs


def test_hybrid_mode_uses_embedder():
    calls = []

    def fake_embed(texts):
        calls.append(len(texts))
        return np.ones((len(texts), 4)) + np.arange(len(texts))[:, None] * np.array([1, 0, 0, 0])

    chunks = load_chunks()[:20]
    r = Retriever(chunks, embed=fake_embed)
    assert r.mode.startswith("hybrid")
    assert len(r.search("lease", k=3)) == 3
    assert calls[0] == 20 and calls[-1] == 1


def test_format_context_numbers_passages(retriever):
    text = format_context(retriever.search("Valuation Limit", k=2))
    assert text.startswith("[1] ")
    assert "\n\n[2] " in text


def test_search_falls_back_to_keywords_when_query_embedding_fails():
    """Embeddings built at start-up, then the API times out: answer from BM25, don't crash the ask."""
    chunks = load_chunks()
    calls = []

    def embed(texts):
        calls.append(len(texts))
        if len(calls) > 1:
            raise TimeoutError("upstream timed out")
        return np.ones((len(texts), 4), dtype=np.float32)

    index = Retriever(chunks, embed=embed)
    assert [c.id for c in index.search("Valuation Limit", k=3)] == [c.id for c in Retriever(chunks).search("Valuation Limit", k=3)]
