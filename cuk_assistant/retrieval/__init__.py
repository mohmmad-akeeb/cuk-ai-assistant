"""cuk_assistant/retrieval package.

Exports the hybrid retrieval coordinator, LanceDB storage adapter, and FlashRank reranker.
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cuk_assistant.retrieval.coordinator import (
        HybridRetrievalCoordinator,
        extract_circular_reference,
        format_where_filter,
    )
    from cuk_assistant.retrieval.flashrank_reranker import FlashRankReranker
    from cuk_assistant.retrieval.lancedb_store import LanceDBStore

__all__ = [
    "FlashRankReranker",
    "HybridRetrievalCoordinator",
    "LanceDBStore",
    "extract_circular_reference",
    "format_where_filter",
]


def __getattr__(name: str) -> Any:
    if name in ("HybridRetrievalCoordinator", "extract_circular_reference", "format_where_filter"):
        from cuk_assistant.retrieval.coordinator import (
            HybridRetrievalCoordinator,
            extract_circular_reference,
            format_where_filter,
        )

        mapping = {
            "HybridRetrievalCoordinator": HybridRetrievalCoordinator,
            "extract_circular_reference": extract_circular_reference,
            "format_where_filter": format_where_filter,
        }
        return mapping[name]
    if name == "LanceDBStore":
        from cuk_assistant.retrieval.lancedb_store import LanceDBStore

        return LanceDBStore
    if name == "FlashRankReranker":
        from cuk_assistant.retrieval.flashrank_reranker import FlashRankReranker

        return FlashRankReranker
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
