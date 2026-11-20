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
        ("How long can my loan be?", "hdb-housing-loan-from-hdb"),  # one of the Ask page's own suggestions
        ("Proximity Housing Grant living within 4km of parents", "hdb-proximity"),
        ("Can I pay cash over valuation with CPF?", "cpf-guide-buying-financing"),
        ("buyer's stamp duty rates", "iras-"),
    ],
)
def test_keyword_retrieval_finds_expected_source(retriever, query, expected_doc_prefix):
    docs = [c.doc for c in retriever.search(query, k=5)]
    assert any(d.startswith(expected_doc_prefix) for d in docs), docs


def test_format_context_numbers_passages(retriever):
    text = format_context(retriever.search("Valuation Limit", k=2))
    assert text.startswith("[1] ")
    assert "\n\n[2] " in text


def test_vector_index_ranks_by_cosine_similarity():
    from runway.rag import VectorIndex

    idx = VectorIndex(["valuation limit for cpf", "option fee deposit", "stamp duty rates"])
    scores = idx.scores("what is the valuation limit")
    assert int(np.argmax(scores)) == 0
    assert np.allclose(np.linalg.norm(idx.matrix, axis=1), 1.0, atol=1e-5)  # unit vectors: the dot product is the cosine
    assert idx.scores("zzz unknown words").max() == 0  # no shared words, no match


def test_fuse_puts_passages_both_lists_agree_on_first():
    from runway.rag import fuse

    assert fuse([[1, 2, 3], [3, 1, 4]])[0] == 1  # 1st and 2nd beats 3rd and 1st
    assert fuse([[1, 2], [2, 1]], [1.0, 0.5]) == [1, 2]  # the keyword list counts more
    assert set(fuse([[5], [6]])) == {5, 6}


def test_hybrid_search_modes(retriever):
    q = "Proximity Housing Grant living within 4km of parents"
    for mode in ("keyword", "vector", "hybrid"):
        top = retriever.search(q, k=5, mode=mode)
        assert 0 < len(top) <= 5 and top[0].doc.startswith("hdb-proximity"), (mode, [c.doc for c in top])
    assert retriever.search("zzzz qqqq", k=5) == []  # nothing matches: no made-up sources
    assert "vector" in Retriever.mode


def test_hybrid_is_at_least_as_good_as_keywords_on_the_eval_questions(retriever):
    import json
    from pathlib import Path

    cases = [c for c in json.loads((Path(__file__).parent.parent / "eval" / "questions.json").read_text())
             if c["type"] == "retrieval"]

    def hits(mode, k):
        return sum(any(x.doc in c["expect_docs"] for x in retriever.search(c["question"], k=k, mode=mode)) for c in cases)

    for k in (1, 3, 5):
        assert hits("hybrid", k) >= hits("keyword", k), k


def test_search_mode_is_never_silently_swapped(retriever):
    q = "zzzz valuation"  # some words match, so each mode returns its own list
    assert [c.id for c in retriever.search(q, mode="keyword")] == retriever.rankings(q)[0][:5]
    assert [c.id for c in retriever.search(q, mode="vector")] == retriever.rankings(q)[1][:5]
    with pytest.raises(ValueError):
        retriever.search(q, mode="semantic")
