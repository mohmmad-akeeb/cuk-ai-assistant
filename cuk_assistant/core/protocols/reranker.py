"""cuk_assistant/core/protocols/reranker.py

Abstract Reranker Protocol for cross-encoder reranking.
Zero external vendor dependencies per GEMINI.md.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from cuk_assistant.schemas.retrieval import ScoredChunk


@runtime_checkable
class RerankerProtocol(Protocol):
    """Abstract contract for cross-encoder reranking (e.g. FlashRank ms-marco-TinyBERT)."""

    def rerank(
        self,
        query: str,
        candidates: list[ScoredChunk],
        top_k: int = 5,
    ) -> list[ScoredChunk]:
        """Rescore candidate chunks and return top_k most relevant items."""
        ...


__all__ = [
    "RerankerProtocol",
]
