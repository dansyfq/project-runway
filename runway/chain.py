"""The RAG pipeline on LangChain's core interfaces (langchain-core only).

- Retrieval: RunwayRetriever is a LangChain BaseRetriever over runway.rag.Retriever (keyword, vector or hybrid search),
  returning Documents whose metadata name the source (doc, title, publisher, url). The Ask page retrieves through it.
- Prompts: runway.llm builds every prompt (answer, why, summary, translation) with ChatPromptTemplate; to_anthropic
  turns the formatted messages into the Anthropic Messages API's system text and turns.

The model call itself stays on the Anthropic SDK (runway.llm.LLM._create): it needs beta parameters (server-side
fallbacks, output effort) and the calculator-tool loop, which LangChain's chat model wrapper would not pass through.
"""

from __future__ import annotations

from typing import Any

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.prompt_values import PromptValue
from langchain_core.retrievers import BaseRetriever

from runway.rag import Chunk


def to_document(chunk: Chunk) -> Document:
    return Document(page_content=chunk.text, metadata={
        "id": chunk.id, "doc": chunk.doc, "title": chunk.title, "publisher": chunk.publisher, "url": chunk.url,
        "retrieved": chunk.retrieved, "heading": chunk.heading})


def to_chunk(doc: Document) -> Chunk:
    m = doc.metadata
    return Chunk(id=m["id"], doc=m["doc"], title=m["title"], publisher=m["publisher"], url=m["url"],
                 retrieved=m["retrieved"], heading=m["heading"], text=doc.page_content)


class RunwayRetriever(BaseRetriever):
    """Runway's search as a LangChain retriever. invoke(query) gives the top k Documents; k and mode can also be
    passed per call: invoke(query, k=3, mode="vector")."""

    index: Any  # runway.rag.Retriever
    k: int = 5
    mode: str = "hybrid"  # "keyword", "vector" or "hybrid"

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun,
                                k: int | None = None, mode: str | None = None) -> list[Document]:
        return [to_document(c) for c in self.index.search(query, k=k or self.k, mode=mode or self.mode)]


def retrieve(index, query: str, k: int = 5) -> list[Chunk]:
    """The passages for one question, through the LangChain retriever (so LangChain callbacks and tracing see it)."""
    return [to_chunk(d) for d in RunwayRetriever(index=index, k=k).invoke(query)]


def literal(text: str) -> str:
    """Fixed prompt text inside a template: braces are not template variables."""
    return text.replace("{", "{{").replace("}", "}}")


ROLES = {"human": "user", "ai": "assistant"}


def to_anthropic(prompt: PromptValue) -> tuple[str, list[dict]]:
    """A formatted ChatPromptTemplate as the Messages API wants it: (system text, [{"role", "content"}, ...])."""
    system, turns = [], []
    for m in prompt.to_messages():
        if m.type == "system":
            system.append(m.content)
        elif m.type in ROLES:
            turns.append({"role": ROLES[m.type], "content": m.content})
        else:
            raise ValueError(f"unexpected message type in a prompt: {m.type}")
    return "\n\n".join(system), turns
