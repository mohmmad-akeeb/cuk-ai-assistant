"""cuk_assistant/schemas/retrieval.py

Retrieval value objects, candidate scoring models, and ScoredChunk definitions.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from cuk_assistant.schemas.chunks import ChunkRecord


class ScoredChunk(BaseModel):
    """Candidate chunk scored by dense, sparse, or cross-encoder models."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk: ChunkRecord | dict[str, Any] = Field(
        ..., description="Underlying chunk record or payload dict"
    )
    score: float = Field(..., description="Final combined or reranked relevance score")
    dense_score: float = Field(default=0.0, description="Normalized dense cosine score")
    lexical_score: float = Field(default=0.0, description="BM25 Tantivy lexical score")
    rrf_rank: int | None = Field(default=None, description="Pre-reranking rank")
    scope_relaxed: bool = Field(
        default=False, description="Flag indicating scope filter was relaxed to global search"
    )
    regex_fallback: bool = Field(
        default=False,
        description="Flag indicating chunk was retrieved via deterministic regex fallback",
    )

    @property
    def chunk_id(self) -> str:
        """Convenience property for retrieving chunk_id."""
        if isinstance(self.chunk, dict):
            return str(self.chunk.get("chunk_id", ""))
        return str(getattr(self.chunk, "chunk_id", ""))

    @property
    def text_content(self) -> str:
        """Convenience property for retrieving text_content."""
        if isinstance(self.chunk, dict):
            return str(self.chunk.get("text_content", ""))
        return str(getattr(self.chunk, "text_content", ""))

    @property
    def metadata(self) -> dict[str, Any]:
        """Convenience property for accessing chunk metadata dictionary."""
        if isinstance(self.chunk, dict):
            return self.chunk.get("metadata", {})
        return getattr(self.chunk, "metadata", {})


__all__ = [
    "ScoredChunk",
]
