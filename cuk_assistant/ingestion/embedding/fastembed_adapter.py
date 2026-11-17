"""cuk_assistant/ingestion/embedding/fastembed_adapter.py

Local Dense Embedding Adapter using FastEmbed with BAAI/bge-small-en-v1.5.
Provides local CPU ONNX inference with sub-10ms latency and zero API cost.
Conforms to EmbeddingModelProtocol and OCP component registration.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from fastembed import TextEmbedding

from cuk_assistant.core.protocols.storage import EmbeddingModelProtocol
from cuk_assistant.core.registry import register_embedding_model

logger = logging.getLogger(__name__)

DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_DIMENSION = 384


@register_embedding_model("fastembed")
class FastEmbedAdapter(EmbeddingModelProtocol):
    """Local ONNX CPU embedding adapter backed by FastEmbed."""

    def __init__(
        self,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        dimension: int = DEFAULT_DIMENSION,
        threads: int | None = None,
        cache_dir: str | None = None,
        **kwargs: Any,
    ) -> None:
        self._model_name = model_name
        self._dimension = dimension
        self._threads = threads
        self._cache_dir = cache_dir

        logger.info(
            "Initializing FastEmbedAdapter model=%s dimension=%d threads=%s",
            self._model_name,
            self._dimension,
            self._threads,
        )
        self._model = TextEmbedding(
            model_name=self._model_name,
            cache_dir=self._cache_dir,
            threads=self._threads,
            **kwargs,
        )

    @property
    def dimension(self) -> int:
        """Vector dimensionality (e.g. 384 for bge-small-en-v1.5)."""
        return self._dimension

    def embed_documents(self, texts: list[str], batch_size: int = 64) -> list[list[float]]:
        """Compute dense vectors for document chunks with batching and thread pooling.

        Args:
            texts: List of document strings to embed.
            batch_size: Number of texts per forward pass.

        Returns:
            List of float vector embeddings.
        """
        if not texts:
            return []

        embeddings: list[list[float]] = []
        total_texts = len(texts)

        logger.debug("Embedding %d document chunks in batches of %d", total_texts, batch_size)

        for i in range(0, total_texts, batch_size):
            batch = texts[i : i + batch_size]
            generator: Iterable[Any] = self._model.embed(
                batch,
                batch_size=len(batch),
                parallel=self._threads,
            )
            for vec in generator:
                embeddings.append(vec.tolist())

        return embeddings

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Compute dense vectors for document chunks. Conforms to EmbeddingModelProtocol."""
        return self.embed_documents(texts)

    def embed_query(self, query: str) -> list[float]:
        """Compute dense vector for an incoming user query.

        Args:
            query: User search query string.

        Returns:
            Single 384-dimensional float vector.
        """
        if not query or not query.strip():
            return [0.0] * self._dimension

        try:
            generator = self._model.query_embed(query)
            vec = next(iter(generator))
            return vec.tolist()
        except Exception:
            # Fallback to general embedding if query_embed is unsupported
            generator = self._model.embed([query])
            vec = next(iter(generator))
            return vec.tolist()


__all__ = [
    "DEFAULT_DIMENSION",
    "DEFAULT_EMBEDDING_MODEL",
    "FastEmbedAdapter",
]
