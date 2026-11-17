"""cuk_assistant/core/registry.py

Component registries adhering to the Open/Closed Principle (OCP).
Zero vendor dependencies per GEMINI.md.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from cuk_assistant.core.protocols.reranker import RerankerProtocol
    from cuk_assistant.core.protocols.storage import (
        EmbeddingModelProtocol,
        VectorStoreProtocol,
    )
    from cuk_assistant.core.protocols.telemetry import TelemetrySinkProtocol

T = TypeVar("T")

_VECTOR_STORES: dict[str, type[VectorStoreProtocol]] = {}
_EMBEDDING_MODELS: dict[str, type[EmbeddingModelProtocol]] = {}
_RERANKERS: dict[str, type[RerankerProtocol]] = {}
_TELEMETRY_SINKS: dict[str, type[TelemetrySinkProtocol]] = {}


def register_vector_store(name: str) -> Callable[[type[T]], type[T]]:
    """Decorator to register a VectorStoreProtocol implementation."""

    def decorator(cls: type[T]) -> type[T]:
        _VECTOR_STORES[name.lower()] = cls  # type: ignore[assignment]
        return cls

    return decorator


def get_vector_store_cls(name: str) -> type[VectorStoreProtocol]:
    """Retrieve a registered vector store adapter class."""
    name_clean = name.lower()
    if name_clean not in _VECTOR_STORES:
        raise KeyError(
            f"Vector store '{name}' is not registered. Available: {list(_VECTOR_STORES.keys())}"
        )
    return _VECTOR_STORES[name_clean]


def register_embedding_model(name: str) -> Callable[[type[T]], type[T]]:
    """Decorator to register an EmbeddingModelProtocol implementation."""

    def decorator(cls: type[T]) -> type[T]:
        _EMBEDDING_MODELS[name.lower()] = cls  # type: ignore[assignment]
        return cls

    return decorator


def get_embedding_model_cls(name: str) -> type[EmbeddingModelProtocol]:
    """Retrieve a registered embedding model adapter class."""
    name_clean = name.lower()
    if name_clean not in _EMBEDDING_MODELS:
        raise KeyError(
            f"Embedding model '{name}' is not registered. Available: {list(_EMBEDDING_MODELS.keys())}"
        )
    return _EMBEDDING_MODELS[name_clean]


def register_reranker(name: str) -> Callable[[type[T]], type[T]]:
    """Decorator to register a RerankerProtocol implementation."""

    def decorator(cls: type[T]) -> type[T]:
        _RERANKERS[name.lower()] = cls  # type: ignore[assignment]
        return cls

    return decorator


def get_reranker_cls(name: str) -> type[RerankerProtocol]:
    """Retrieve a registered reranker adapter class."""
    name_clean = name.lower()
    if name_clean not in _RERANKERS:
        raise KeyError(f"Reranker '{name}' is not registered. Available: {list(_RERANKERS.keys())}")
    return _RERANKERS[name_clean]


def register_telemetry_sink(name: str) -> Callable[[type[T]], type[T]]:
    """Decorator to register a TelemetrySinkProtocol implementation."""

    def decorator(cls: type[T]) -> type[T]:
        _TELEMETRY_SINKS[name.lower()] = cls  # type: ignore[assignment]
        return cls

    return decorator


def get_telemetry_sink_cls(name: str) -> type[TelemetrySinkProtocol]:
    """Retrieve a registered telemetry sink adapter class."""
    name_clean = name.lower()
    if name_clean not in _TELEMETRY_SINKS:
        raise KeyError(
            f"Telemetry sink '{name}' is not registered. Available: {list(_TELEMETRY_SINKS.keys())}"
        )
    return _TELEMETRY_SINKS[name_clean]


def list_registered_components() -> dict[str, list[str]]:
    """Return a mapping of registered component names."""
    return {
        "vector_stores": list(_VECTOR_STORES.keys()),
        "embedding_models": list(_EMBEDDING_MODELS.keys()),
        "rerankers": list(_RERANKERS.keys()),
        "telemetry_sinks": list(_TELEMETRY_SINKS.keys()),
    }


__all__ = [
    "get_embedding_model_cls",
    "get_reranker_cls",
    "get_telemetry_sink_cls",
    "get_vector_store_cls",
    "list_registered_components",
    "register_embedding_model",
    "register_reranker",
    "register_telemetry_sink",
    "register_vector_store",
]
