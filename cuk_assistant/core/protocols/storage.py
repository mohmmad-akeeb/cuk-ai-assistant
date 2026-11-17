"""cuk_assistant/core/protocols/storage.py

Abstract Storage & Retrieval Protocols for vector/lexical search and query embeddings.
Zero external vendor dependencies per GEMINI.md.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from cuk_assistant.schemas.retrieval import ScoredChunk


@runtime_checkable
class EmbeddingModelProtocol(Protocol):
    """Abstract contract for dense vector embeddings (e.g. FastEmbed BGE-small-en-v1.5)."""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Compute dense vectors for document chunks."""
        ...

    def embed_query(self, query: str) -> list[float]:
        """Compute dense vector for an incoming user query."""
        ...

    @property
    def dimension(self) -> int:
        """Vector dimensionality (e.g. 384 for bge-small-en-v1.5)."""
        ...


@runtime_checkable
class VectorStoreProtocol(Protocol):
    """Abstract contract for embedded hybrid storage (e.g. LanceDB + Tantivy BM25)."""

    def add_chunks(self, chunks: list[Any], embeddings: list[list[float]]) -> None:
        """Batch upsert chunks and dense vectors into storage."""
        ...

    def hybrid_search(
        self,
        query_text: str,
        query_vector: list[float],
        top_k: int = 30,
        where_filter: str | None = None,
    ) -> list[ScoredChunk]:
        """Execute fused dense cosine and sparse BM25 search via Reciprocal Rank Fusion."""
        ...

    def get_parent_chunk(self, parent_chunk_id: str) -> Any | None:
        """Retrieve full parent container section for O(1) context expansion."""
        ...

    def deterministic_regex_search(self, pattern: str) -> list[Any]:
        """Full-corpus deterministic regex scan used on retrieval misses."""
        ...

    def delete_document(self, doc_id: str) -> None:
        """Remove all chunks associated with a specific doc_id during delta sync."""
        ...


__all__ = [
    "EmbeddingModelProtocol",
    "VectorStoreProtocol",
]
