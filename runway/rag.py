"""Retrieval over the fixed library of official CPF, HDB and MND documents.

Hybrid search: keyword search (BM25) with a few everyday synonyms, so exact terms ("Valuation Limit", "HFE") and
common paraphrases ("deposit") find the right passage, merged with a vector store (cosine similarity) by
weighted reciprocal rank fusion. The vector store is FAISS over bge-small embeddings (runway/vector.py), with TF-IDF
vectors (VectorIndex below) as the fallback while it loads or if it can't. A question in another language is put into
English first (runway.llm.LLM.search_query). runway/chain.py puts this search behind LangChain's retriever interface.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

CORPUS_DIR = Path(__file__).resolve().parent.parent / "data" / "corpus"
CHUNK_WORDS = 160
OVERLAP_WORDS = 40



@dataclass(frozen=True)
class Chunk:
    id: int
    doc: str  # file slug
    title: str
    publisher: str
    url: str
    retrieved: str
    heading: str
    text: str


def parse_doc(path: Path) -> tuple[dict, str]:
    raw = path.read_text(encoding="utf-8")
    _, header, body = raw.split("---\n", 2)
    meta = dict(line.split(": ", 1) for line in header.strip().splitlines())
    return meta, body.strip()


def split_sections(body: str) -> list[tuple[str, str]]:
    """Split on markdown headings, keeping the heading as context for each section."""
    sections, heading, buf = [], "", []
    for line in body.splitlines():
        if line.startswith("#"):
            if buf:
                sections.append((heading, "\n".join(buf).strip()))
            heading, buf = line.lstrip("# ").strip(), []
        else:
            buf.append(line)
    if buf:
        sections.append((heading, "\n".join(buf).strip()))
    return [(h, t) for h, t in sections if t]


def window(words: list[str], size: int = CHUNK_WORDS, overlap: int = OVERLAP_WORDS) -> list[list[str]]:
    if len(words) <= size:
        return [words]
    step = size - overlap
    return [words[i : i + size] for i in range(0, len(words) - overlap, step)]


def load_chunks(corpus_dir: Path | None = None) -> list[Chunk]:
    """The committed documents plus any a reviewer uploaded since the last start (runway.content)."""
    from runway.content import corpus_files

    paths = corpus_files().values() if corpus_dir is None else sorted(corpus_dir.glob("*.md"))
    chunks: list[Chunk] = []
    for path in paths:
        meta, body = parse_doc(path)
        for heading, text in split_sections(body):
            for words in window(text.split()):
                chunks.append(
                    Chunk(
                        id=len(chunks),
                        doc=path.stem,
                        title=meta["title"],
                        publisher=meta["publisher"],
                        url=meta["url"],
                        retrieved=meta["retrieved"],
                        heading=heading,
                        text=" ".join(words),
                    )
                )
    return chunks


# Everyday words buyers use -> the terms the official documents use (keyword search only).
SYNONYMS = {
    "partner": "spouse co-owner buyer",
    "wife": "spouse co-owner buyer",
    "husband": "spouse co-owner buyer",
    "younger": "youngest age",
    "older": "age",
    "cut": "pro-rated reduced",
    "reduced": "pro-rated",
    "short": "remaining lease",
    "loan": "housing loan",
    "deposit": "option fee",
}


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


# Word pairs that mean more together than apart: "how long" alone is about a letter or a lease; with "loan", its term.
PAIRS = {("long", "loan"): "repayment period"}


def expand_query(query: str) -> str:
    words = tokenize(query)
    extra = [SYNONYMS[w] for w in words if w in SYNONYMS]
    extra += [v for pair, v in PAIRS.items() if set(pair) <= set(words)]
    return " ".join([query, *extra])


RRF_K = 60  # reciprocal rank fusion constant; 60 is the value from the original paper
POOL = 20  # how deep each ranking is read before the two are merged
# Function words carry no meaning in a term vector: without them "How long can my loan be?" matched
# "How long is an HFE letter valid?" on "how long" instead of HDB's loan page.
STOPWORDS = set(
    "a an the is are was were be been being am i me my we our you your he she it its they them their this that these "
    "those of to in on at by for with from as or and but if so than then there here what which who whom whose when "
    "where why how can could do does did will would shall should may might must have has had not no yes any all some "
    "more most much many very just also into about up out over".split()
)


class VectorIndex:
    """A small vector store: every passage is a TF-IDF vector (L2-normalised) and a query is matched by cosine similarity.

    The fallback for runway.vector.FaissStore (neural embeddings): used while that loads, if it can't, or with
    VECTOR_BACKEND = "tfidf".
    """

    def __init__(self, texts: list[str]):
        docs = [self.words(t) for t in texts]
        df: dict[str, int] = {}
        for words in docs:
            for w in set(words):
                df[w] = df.get(w, 0) + 1
        self.vocab = {w: i for i, w in enumerate(sorted(df))}
        n = len(docs)
        self.idf = np.array([np.log((1 + n) / (1 + df[w])) + 1 for w in self.vocab], dtype=np.float32)
        self.matrix = np.vstack([self.embed(words) for words in docs]) if docs else np.zeros((0, len(self.vocab)), np.float32)

    def embed(self, words: list[str]) -> np.ndarray:
        vec = np.zeros(len(self.vocab), dtype=np.float32)
        for w in words:
            if w in self.vocab:
                vec[self.vocab[w]] += 1
        vec = (1 + np.log(np.maximum(vec, 1))) * (vec > 0) * self.idf  # sublinear term frequency x idf
        norm = float(np.linalg.norm(vec))
        return vec / norm if norm else vec

    @staticmethod
    def words(text: str) -> list[str]:
        return [w for w in tokenize(text) if w not in STOPWORDS]

    def scores(self, query: str) -> np.ndarray:
        return self.matrix @ self.embed(self.words(query))


# eval/questions.json (python eval/run_eval.py): with TF-IDF vectors, at 0.3 hybrid matches BM25 at top 1 (15/19) and
# beats it at top 3 (19 vs 18); at 1.0 top 1 fell to 13. With FAISS (bge-small), 0.3 gives 17/19 first (0.5: 17,
# 1.0: 15). Re-run the eval after changing it.
VECTOR_WEIGHT = 0.3


def fuse(rankings: list[list[int]], weights: list[float] | None = None, k: int = RRF_K) -> list[int]:
    """Weighted reciprocal rank fusion: a passage ranked high by both lists comes first."""
    total: dict[int, float] = {}
    for ranking, weight in zip(rankings, weights or [1.0] * len(rankings)):
        for rank, idx in enumerate(ranking):
            total[idx] = total.get(idx, 0.0) + weight / (k + rank + 1)
    return sorted(total, key=lambda i: (-total[i], i))


class Retriever:
    mode = "hybrid (BM25 keywords + TF-IDF vector store)"  # this instance's mode changes once FAISS is ready
    FAISS_MODE = "hybrid (BM25 keywords + FAISS vector store, bge-small embeddings)"

    def __init__(self, chunks: list[Chunk], embedder=None):
        """embedder: None for the process's bge-small model (unless VECTOR_BACKEND is "tfidf"), False for TF-IDF
        vectors only, or any object like runway.vector.Embedder."""
        self.chunks = chunks
        texts = [f"{c.title} {c.heading} {c.text}" for c in chunks]
        self.bm25 = BM25Okapi([tokenize(t) for t in texts])
        self.vectors = VectorIndex(texts)
        self.dense = None  # runway.vector.FaissStore once loaded
        self.dense_ready = threading.Event()
        from runway import vector

        if embedder is False or (embedder is None and vector.backend() == "tfidf"):
            self.dense_ready.set()
            return
        # In a thread, so a slow model download or a big re-embed can't hold up the app: TF-IDF until it is done.
        threading.Thread(target=self._load_dense, args=(embedder,), daemon=True).start()
        self.dense_ready.wait(vector.WAIT_SECONDS)

    def _load_dense(self, embedder) -> None:
        from runway import vector

        try:
            emb = embedder if embedder is not None else vector.embedder()
            if emb is not None:
                self.dense = vector.FaissStore(self.chunks, emb)
                self.mode = self.FAISS_MODE
        except Exception as exc:
            print(f"[runway] vector search falls back to TF-IDF: {type(exc).__name__}: {exc}"[:300], flush=True)
        finally:
            self.dense_ready.set()

    def vector_ranking(self, query: str) -> list[int]:
        dense = self.dense
        if dense is not None:
            try:
                return dense.search(query, POOL)  # the question as asked: the embedding model knows synonyms
            except Exception as exc:  # this question only
                print(f"[runway] vector search failed, using TF-IDF: {type(exc).__name__}: {exc}"[:300], flush=True)
        vector = self.vectors.scores(expand_query(query))
        return [int(i) for i in np.argsort(-vector)[:POOL] if vector[i] > 0]

    def as_langchain(self, k: int = 5, mode: str = "hybrid"):
        """This search as a LangChain retriever (runway.chain.RunwayRetriever), returning Documents."""
        from runway.chain import RunwayRetriever

        return RunwayRetriever(index=self, k=k, mode=mode)

    def rankings(self, query: str) -> tuple[list[int], list[int]]:
        """(BM25 order, vector order) of passage numbers for one query, best first. A passage that scores 0 is not a match."""
        keyword = self.bm25.get_scores(tokenize(expand_query(query)))
        return [int(i) for i in np.argsort(-keyword)[:POOL] if keyword[i] > 0], self.vector_ranking(query)

    def search(self, query: str, k: int = 5, mode: str = "hybrid") -> list[Chunk]:
        keyword, vector = self.rankings(query)
        if mode == "keyword":
            order = keyword
        elif mode == "vector":
            order = vector
        elif mode == "hybrid":
            order = fuse([keyword, vector], [1.0, VECTOR_WEIGHT])
        else:
            raise ValueError(f"unknown search mode: {mode}")
        return [self.chunks[i] for i in order[:k]]


def format_context(chunks: list[Chunk]) -> str:
    """Numbered passages for the prompt; the model cites them as [1], [2], ..."""
    return "\n\n".join(
        f"[{i}] {c.title} ({c.publisher}" + (f", retrieved {c.retrieved}" if c.retrieved else "") + ")"
        + (f" - {c.heading}" if c.heading else "") + f"\n{c.text}"
        for i, c in enumerate(chunks, start=1)
    )
