"""cuk_assistant/retrieval/flashrank_reranker.py

Local Cross-Encoder Reranker using FlashRank with ms-marco-TinyBERT-L-2-v2.
Provides local CPU ONNX cross-encoder reranking with sub-20ms latency.
Conforms to RerankerProtocol and OCP component registration.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from flashrank import Ranker, RerankRequest

from cuk_assistant.core.protocols.reranker import RerankerProtocol
from cuk_assistant.core.registry import register_reranker
from cuk_assistant.schemas.retrieval import ScoredChunk

logger = logging.getLogger(__name__)

DEFAULT_RERANKER_MODEL = "ms-marco-TinyBERT-L-2-v2"
DEFAULT_OPT_CACHE = Path("/opt/model_cache/flashrank")
DEFAULT_CACHE_DIR = "/tmp"


@register_reranker("flashrank")
class FlashRankReranker(RerankerProtocol):
    """Local CPU ONNX cross-encoder reranker backed by FlashRank."""

    def __init__(
        self,
        model_name: str = DEFAULT_RERANKER_MODEL,
        cache_dir: str | None = None,
        **kwargs: Any,
    ) -> None:
        resolved_cache = cache_dir or kwargs.pop("cache_dir", None)
        if not resolved_cache:
            resolved_cache = os.environ.get("FLASHRANK_CACHE_PATH") or os.environ.get(
                "FLASHRANK_CACHE_DIR"
            )
        if not resolved_cache and DEFAULT_OPT_CACHE.is_dir():
            resolved_cache = str(DEFAULT_OPT_CACHE)
        if not resolved_cache:
            resolved_cache = DEFAULT_CACHE_DIR

        self._model_name = model_name
        self._cache_dir = str(resolved_cache)

        logger.info(
            "Initializing FlashRankReranker model=%s cache_dir=%s",
            self._model_name,
            self._cache_dir,
        )
        init_kwargs: dict[str, Any] = dict(kwargs)
        init_kwargs["cache_dir"] = self._cache_dir

        self._ranker = Ranker(
            model_name=self._model_name,
            **init_kwargs,
        )

    def rerank(
        self,
        query: str,
        candidates: list[ScoredChunk],
        top_k: int = 5,
    ) -> list[ScoredChunk]:
        """Rescore candidate chunks and return top_k most relevant items.

        Args:
            query: User search query string.
            candidates: Initial retrieved candidate chunks (from hybrid search).
            top_k: Number of highest-ranked chunks to return.

        Returns:
            List of ScoredChunk instances sorted by cross-encoder score descending.
        """
        if not candidates or top_k <= 0:
            return []

        if not query or not query.strip():
            # If no query text to compare against, preserve original candidate order
            return sorted(candidates, key=lambda c: c.score, reverse=True)[:top_k]

        # Prepare passages for FlashRank with integer indices
        passages: list[dict[str, Any]] = []
        for idx, cand in enumerate(candidates):
            text = cand.text_content or ""
            passages.append({"id": idx, "text": text})

        rerank_request = RerankRequest(query=query, passages=passages)
        ranked_passages = self._ranker.rerank(rerank_request)

        # Map back results to ScoredChunk instances with updated cross-encoder score
        reranked_candidates: list[ScoredChunk] = []
        for item in ranked_passages:
            idx = int(item["id"])
            score = float(item["score"])
            original_chunk = candidates[idx]
            updated_chunk = original_chunk.model_copy(update={"score": score})
            reranked_candidates.append(updated_chunk)

        # Sort descending by score just in case and slice top_k
        reranked_candidates.sort(key=lambda c: c.score, reverse=True)
        return reranked_candidates[:top_k]


__all__ = [
    "DEFAULT_RERANKER_MODEL",
    "FlashRankReranker",
]
