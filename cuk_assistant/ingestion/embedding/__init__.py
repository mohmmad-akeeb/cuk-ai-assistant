"""cuk_assistant/ingestion/embedding/__init__.py

Embedding models and local ONNX adapters.
"""

from cuk_assistant.ingestion.embedding.fastembed_adapter import (
    DEFAULT_DIMENSION,
    DEFAULT_EMBEDDING_MODEL,
    FastEmbedAdapter,
)

__all__ = [
    "DEFAULT_DIMENSION",
    "DEFAULT_EMBEDDING_MODEL",
    "FastEmbedAdapter",
]
