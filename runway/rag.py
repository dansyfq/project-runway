"""Retrieval over the fixed library of official CPF, HDB and MND documents.

Hybrid search: BM25 keyword scores always; OpenAI embeddings when an API key is
configured. The two rankings are merged with reciprocal rank fusion, so exact
terms ("Valuation Limit", "HFE") and paraphrases ("my partner is younger") both
find the right passage.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

CORPUS_DIR = Path(__file__).resolve().parent.parent / "data" / "corpus"
CHUNK_WORDS = 160
OVERLAP_WORDS = 40
RRF_K = 60

Embedder = Callable[[list[str]], np.ndarray]


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


def load_chunks(corpus_dir: Path = CORPUS_DIR) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(corpus_dir.glob("*.md")):
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


def expand_query(query: str) -> str:
    extra = [SYNONYMS[w] for w in tokenize(query) if w in SYNONYMS]
    return " ".join([query, *extra])


class Retriever:
    def __init__(self, chunks: list[Chunk], embed: Embedder | None = None):
        self.chunks = chunks
        self.embed = embed
        self.embed_error: str | None = None
        self.bm25 = BM25Okapi([tokenize(f"{c.title} {c.heading} {c.text}") for c in chunks])
        self.vectors = None
        if embed is not None:
            vecs = embed([f"{c.title}. {c.heading}. {c.text}" for c in chunks])
            self.vectors = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)

    @property
    def mode(self) -> str:
        return "hybrid (BM25 + embeddings)" if self.vectors is not None else "keyword (BM25)"

    def search(self, query: str, k: int = 5) -> list[Chunk]:
        rankings = [np.argsort(-self.bm25.get_scores(tokenize(expand_query(query))))]
        if self.vectors is not None:
            q = self.embed([query])[0]
            q = q / np.linalg.norm(q)
            rankings.append(np.argsort(-(self.vectors @ q)))
        fused: dict[int, float] = {}
        for ranking in rankings:
            for rank, idx in enumerate(ranking[:50]):
                fused[int(idx)] = fused.get(int(idx), 0.0) + 1.0 / (RRF_K + rank + 1)
        best = sorted(fused, key=fused.get, reverse=True)
        return [self.chunks[i] for i in best[:k]]


def format_context(chunks: list[Chunk]) -> str:
    """Numbered passages for the prompt; the model cites them as [1], [2], ..."""
    return "\n\n".join(
        f"[{i}] {c.title} ({c.publisher})" + (f" - {c.heading}" if c.heading else "") + f"\n{c.text}"
        for i, c in enumerate(chunks, start=1)
    )
