"""The neural vector store: every passage embedded with bge-small (fastembed, ONNX on the CPU) in a FAISS index.

runway.rag.Retriever ranks passages with it (mode "vector", and inside "hybrid"). Cosine similarity: the vectors are
normalised and the index is an inner-product one (IndexFlatIP), searched exhaustively (349 passages need no more).

The index is kept on disk: data/index/ holds the one built for the committed documents (`python -m runway.vector`
rebuilds it), so a fresh start only loads the model and embeds each question. When the documents differ (an upload,
or a document edited without rebuilding the index), passages already embedded are reused by a hash of their text and
only the new ones are embedded; the result goes to data/runtime/index/, which is gitignored like the uploads, so a
redeploy's `git pull` never clashes with it. A disk that can't be written only costs the next start that work again.

Never in the way: without fastembed or faiss, while the model downloads (about 65 MB from Hugging Face, once per
machine) or if anything here fails, the Retriever keeps searching with its TF-IDF vectors. VECTOR_BACKEND = "tfidf"
(Streamlit secret or environment variable) turns this off and saves the model's memory.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path

import numpy as np

from runway.config import get_setting

ROOT = Path(__file__).resolve().parent.parent
INDEX_DIR = ROOT / "data" / "index"
MODEL = "BAAI/bge-small-en-v1.5"  # 384 numbers per passage; English; 33M parameters (quantised ONNX)
# bge's instruction for a short question searching longer passages. eval/questions.json: right document first 18 of 19
# with it, 17 without; same in the hybrid.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
# A passage less similar than this is not a match. Eval questions' best passage: 0.63 to 0.95; "zzzz qqqq": 0.47.
MIN_SIMILARITY = 0.55
BATCH = 1  # passages are all about 160 words: bigger batches were slower here and used more memory (256: 2.7 GB)
WAIT_SECONDS = 15  # how long a new Retriever waits for the store before it starts with TF-IDF vectors
RETRY_SECONDS = 600  # after a failed model load (no network, Hugging Face down), try again this much later


def backend() -> str:
    """"faiss" (default) or "tfidf"."""
    return "tfidf" if str(get_setting("VECTOR_BACKEND", "faiss") or "").strip().lower() == "tfidf" else "faiss"


def passage_text(chunk) -> str:
    return f"{chunk.title}\n{chunk.heading}\n{chunk.text}"


def chunk_key(chunk, model: str) -> str:
    """Names one passage's vector: the same text under the same model is never embedded twice."""
    return hashlib.sha256(f"{model}\n{passage_text(chunk)}".encode()).hexdigest()[:20]


def fingerprint(keys: list[str]) -> str:
    return hashlib.sha256("\n".join(keys).encode()).hexdigest()


class Embedder:
    """bge-small through fastembed. Loading it may download the model, so it is made once per process (embedder())."""

    def __init__(self, model: str = MODEL):
        import faiss  # noqa: F401  (imported first: without FAISS there is no point downloading the model)
        from fastembed import TextEmbedding

        self.name = model
        self._model = TextEmbedding(model)
        self.dim = self.query("dimension check").shape[1]

    def passages(self, texts: list[str]) -> np.ndarray:
        return _unit(np.array(list(self._model.embed(texts, batch_size=BATCH)), dtype=np.float32))

    def query(self, text: str) -> np.ndarray:
        return _unit(np.array(list(self._model.query_embed(QUERY_PREFIX + text)), dtype=np.float32))


def _unit(m: np.ndarray) -> np.ndarray:
    m = np.ascontiguousarray(m, dtype=np.float32).reshape(len(m), -1)
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    return m / np.where(norms == 0, 1, norms)


_loaded: Embedder | None = None
_failed_at = 0.0
_load_lock = threading.Lock()


def embedder() -> Embedder | None:
    """The process's one embedding model, loaded on first use (Retrievers are rebuilt after every upload; the model is
    not). None when it can't be loaded; that is said once in the log and tried again RETRY_SECONDS later."""
    global _loaded, _failed_at
    with _load_lock:  # two sessions starting at once load it once
        if _loaded is None and time.time() - _failed_at > RETRY_SECONDS:
            started = time.time()
            try:
                _loaded = Embedder()
                print(f"[runway] vector search: {MODEL} loaded in {time.time() - started:.1f} s", flush=True)
            except Exception as exc:  # no package, no network, a broken download: TF-IDF vectors instead
                _failed_at = time.time()
                print(f"[runway] vector search falls back to TF-IDF: {type(exc).__name__}: {exc}"[:300], flush=True)
        return _loaded


# ---------- the index on disk ----------

def runtime_dir() -> Path:
    """Beside the uploaded documents (data/runtime/), so the index rebuilt for them goes wherever they go."""
    from runway import content

    return content.RUNTIME_CORPUS.parent / "index"


def read_store(folder: Path):
    """(meta, FAISS index) saved in folder, or None if missing or not whole (the two files are checked together)."""
    import faiss

    try:
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8"))
        data = (folder / "faiss.index").read_bytes()
        if meta.get("index_sha256") != hashlib.sha256(data).hexdigest():  # half of a write that is still going on
            return None
        index = faiss.deserialize_index(np.frombuffer(data, dtype=np.uint8))
        if index.ntotal != len(meta["chunks"]):
            return None
        return meta, index
    except Exception:  # missing, unreadable or from another FAISS version: build again
        return None


def write_store(folder: Path, model: str, keys: list[str], index) -> bool:
    """Save atomically: each file is written beside its final name and renamed into place, so a reader never sees a
    half-written file and two processes saving at once each leave a whole, identical copy."""
    import faiss

    data = faiss.serialize_index(index).tobytes()
    meta = {"model": model, "dim": index.d, "count": index.ntotal, "fingerprint": fingerprint(keys),
            "index_sha256": hashlib.sha256(data).hexdigest(), "chunks": keys}
    try:
        folder.mkdir(parents=True, exist_ok=True)
        for name, body in (("faiss.index", data), ("meta.json", (json.dumps(meta, indent=0) + "\n").encode())):
            tmp = folder / f".{name}.{os.getpid()}.{threading.get_ident()}.tmp"
            tmp.write_bytes(body)
            os.replace(tmp, folder / name)
        return True
    except OSError as exc:  # a read-only disk: the index still works from memory
        print(f"[runway] couldn't save the vector index to {folder}: {type(exc).__name__}: {exc}", flush=True)
        return False


class FaissStore:
    """The passages' vectors in a FAISS index: loaded from disk if it matches these passages, else (re)built."""

    def __init__(self, chunks: list, emb, folders: list[Path] | None = None, save_to: Path | None = None):
        import faiss

        self.embedder = emb
        self.keys = [chunk_key(c, emb.name) for c in chunks]
        self.embedded = 0  # passages embedded here rather than loaded
        folders = [runtime_dir(), INDEX_DIR] if folders is None else folders
        stores = [s for s in map(read_store, folders) if s and s[0].get("model") == emb.name and s[1].d == emb.dim]
        exact = next((index for meta, index in stores if meta.get("fingerprint") == fingerprint(self.keys)), None)
        if exact is not None:
            self.index = exact
            return
        known: dict[str, np.ndarray] = {}
        for meta, index in reversed(stores):  # the first folder's copy wins
            known.update(zip(meta["chunks"], index.reconstruct_n(0, index.ntotal)))
        missing = [i for i, key in enumerate(self.keys) if key not in known]
        if missing:
            started = time.time()
            known.update(zip((self.keys[i] for i in missing), emb.passages([passage_text(chunks[i]) for i in missing])))
            self.embedded = len(missing)
            print(f"[runway] vector search: embedded {len(missing)} passages in {time.time() - started:.1f} s",
                  flush=True)
        self.index = faiss.IndexFlatIP(emb.dim)
        if self.keys:
            self.index.add(np.vstack([known[k] for k in self.keys]).astype(np.float32))
        write_store(save_to or runtime_dir(), emb.name, self.keys, self.index)

    def search(self, query: str, n: int) -> list[int]:
        """Passage numbers, most similar first, at least MIN_SIMILARITY."""
        if not self.index.ntotal:
            return []
        sims, ids = self.index.search(self.embedder.query(query), min(n, self.index.ntotal))
        return [int(i) for s, i in zip(sims[0], ids[0]) if i >= 0 and s >= MIN_SIMILARITY]


def main() -> None:
    """Rebuild data/index/ for the committed documents (commit it with them, so the app starts without embedding)."""
    from runway.rag import CORPUS_DIR, load_chunks

    emb = embedder()
    if emb is None:
        raise SystemExit("the embedding model could not be loaded")
    store = FaissStore(load_chunks(CORPUS_DIR), emb, folders=[INDEX_DIR], save_to=INDEX_DIR)
    size = sum(p.stat().st_size for p in INDEX_DIR.iterdir())
    print(f"{INDEX_DIR}: {store.index.ntotal} passages, {store.embedded} embedded now, {size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
