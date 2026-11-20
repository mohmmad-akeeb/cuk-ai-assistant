"""cuk_assistant/core/factory.py

Component factory for Dependency Injection (DI).
Assembles storage, embedding, reranker, coordinator, LLM pool, guardrails,
session store, router, and end-to-end RAG orchestrator adapters.
Business logic and endpoints receive abstract protocols assembled here.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cuk_assistant.agent.router import AdaptiveRouter
from cuk_assistant.agent.session_store import SQLiteSessionStore
from cuk_assistant.agent.slot_filler import FacetedSlotFiller
from cuk_assistant.core.protocols.llm import LLMClientProtocol
from cuk_assistant.core.protocols.reranker import RerankerProtocol
from cuk_assistant.core.protocols.session import SessionStoreProtocol
from cuk_assistant.core.protocols.storage import (
    EmbeddingModelProtocol,
    VectorStoreProtocol,
)
from cuk_assistant.core.protocols.telemetry import TelemetrySinkProtocol
from cuk_assistant.core.registry import (
    get_embedding_model_cls,
    get_reranker_cls,
    get_telemetry_sink_cls,
    get_vector_store_cls,
)
from cuk_assistant.guardrails.subsystems import (
    InputGuard,
    OutputGuard,
    VerbatimCitationVerifier,
)
from cuk_assistant.llm import GeminiClient, GroqClient, LLMProviderPool
from cuk_assistant.pipeline.orchestrator import RAGOrchestrator
from cuk_assistant.retrieval.subsystems.coordinator import HybridRetrievalCoordinator

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Storage, Embedding & Reranker Factories
# ---------------------------------------------------------------------------


def create_embedding_model(
    name: str = "fastembed",
    **kwargs: Any,
) -> EmbeddingModelProtocol:
    """Instantiate a registered embedding model adapter."""
    # Ensure modules are imported to trigger registry decorators
    import cuk_assistant.ingestion.embedding.fastembed_adapter  # noqa: F401

    cls = get_embedding_model_cls(name)
    logger.info("Factory instantiating embedding model '%s' (%s)", name, cls.__name__)
    return cls(**kwargs)  # type: ignore[return-value]


def create_vector_store(
    name: str = "lancedb",
    **kwargs: Any,
) -> VectorStoreProtocol:
    """Instantiate a registered vector store adapter."""
    import cuk_assistant.retrieval.subsystems.lancedb_store  # noqa: F401

    cls = get_vector_store_cls(name)
    init_kwargs = dict(kwargs)
    if "db_path" not in init_kwargs or init_kwargs["db_path"] is None:
        env_lancedb_dir = os.environ.get("LANCEDB_DIR")
        if env_lancedb_dir:
            init_kwargs["db_path"] = env_lancedb_dir

    logger.info("Factory instantiating vector store '%s' (%s)", name, cls.__name__)
    return cls(**init_kwargs)  # type: ignore[return-value]


def create_reranker(
    name: str = "flashrank",
    **kwargs: Any,
) -> RerankerProtocol:
    """Instantiate a registered reranker adapter."""
    import cuk_assistant.retrieval.subsystems.flashrank_reranker  # noqa: F401

    cls = get_reranker_cls(name)
    init_kwargs = dict(kwargs)
    if "cache_dir" not in init_kwargs or init_kwargs["cache_dir"] is None:
        env_cache_path = os.environ.get("FLASHRANK_CACHE_PATH") or os.environ.get(
            "FLASHRANK_CACHE_DIR"
        )
        if env_cache_path:
            init_kwargs["cache_dir"] = env_cache_path
        elif Path("/opt/model_cache/flashrank").is_dir():
            init_kwargs["cache_dir"] = "/opt/model_cache/flashrank"

    logger.info("Factory instantiating reranker '%s' (%s)", name, cls.__name__)
    return cls(**init_kwargs)  # type: ignore[return-value]


def create_retrieval_coordinator(
    vector_store: VectorStoreProtocol | None = None,
    embedding_model: EmbeddingModelProtocol | None = None,
    reranker: RerankerProtocol | None = None,
    relevance_threshold: float = 0.35,
    telemetry_sink: TelemetrySinkProtocol | None = None,
    **kwargs: Any,
) -> HybridRetrievalCoordinator:
    """Assemble and return a fully wired HybridRetrievalCoordinator."""
    if vector_store is None:
        vector_store = create_vector_store(**kwargs.get("vector_store_kwargs", {}))
    if embedding_model is None:
        embedding_model = create_embedding_model(**kwargs.get("embedding_kwargs", {}))
    if reranker is None:
        reranker = create_reranker(**kwargs.get("reranker_kwargs", {}))

    return HybridRetrievalCoordinator(
        vector_store=vector_store,
        embedding_model=embedding_model,
        reranker=reranker,
        relevance_threshold=relevance_threshold,
        telemetry_sink=telemetry_sink,
    )


# ---------------------------------------------------------------------------
# LLM Provider Pool Factory
# ---------------------------------------------------------------------------


def create_llm_pool(
    gemini_api_key: str | None = None,
    groq_api_key: str | None = None,
    cooloff_seconds: float = 60.0,
    failure_threshold: int = 1,
    **kwargs: Any,
) -> LLMClientProtocol:
    """Assemble LLM provider pool: Gemini Flash primary with Groq failover."""
    env_vals: dict[str, Any] = {}
    try:
        from dotenv import dotenv_values

        env_vals = dotenv_values(".env")
    except Exception:
        pass

    gemini_key = (
        gemini_api_key
        or os.environ.get("GEMINI_API_KEY")
        or str(env_vals.get("GEMINI_API_KEY", ""))
    )
    groq_key = (
        groq_api_key or os.environ.get("GROQ_API_KEY") or str(env_vals.get("GROQ_API_KEY", ""))
    )

    gemini_model = (
        kwargs.get("gemini_model")
        or os.environ.get("GEMINI_MODEL")
        or str(env_vals.get("GEMINI_MODEL", ""))
        or "gemini-flash-latest"
    )
    groq_model = (
        kwargs.get("groq_model")
        or os.environ.get("GROQ_MODEL")
        or str(env_vals.get("GROQ_MODEL", ""))
        or "qwen/qwen3.8-27b"
    )
    if "llama" in groq_model.lower():
        groq_model = "qwen/qwen3.8-27b"

    gemini_client = GeminiClient(
        api_key=gemini_key, model=gemini_model, **kwargs.get("gemini_kwargs", {})
    )
    groq_client = GroqClient(api_key=groq_key, model=groq_model, **kwargs.get("groq_kwargs", {}))

    logger.info(
        "Factory assembling LLMProviderPool with Gemini (%s) and Groq (%s) fallback",
        gemini_model,
        groq_model,
    )
    return LLMProviderPool(
        providers=[gemini_client, groq_client],
        cooloff_seconds=cooloff_seconds,
        failure_threshold=failure_threshold,
    )


# ---------------------------------------------------------------------------
# Guardrails & Verification Factories
# ---------------------------------------------------------------------------


def create_input_guard(**kwargs: Any) -> InputGuard:
    """Instantiate multi-layer input guardrail."""
    return InputGuard(**kwargs)


def create_output_guard(**kwargs: Any) -> OutputGuard:
    """Instantiate output safety and PII scrubbing rail."""
    return OutputGuard(**kwargs)


def create_citation_verifier(**kwargs: Any) -> VerbatimCitationVerifier:
    """Instantiate deterministic verbatim citation verifier."""
    return VerbatimCitationVerifier(**kwargs)


# ---------------------------------------------------------------------------
# Session Memory Store Factory
# ---------------------------------------------------------------------------


def create_session_store(
    db_path: Path | str | None = None,
    timeout_seconds: float = 5.0,
    **kwargs: Any,
) -> SessionStoreProtocol:
    """Instantiate high-concurrency SQLite session store in WAL mode."""
    if db_path is None:
        db_path = os.environ.get("SQLITE_DB_PATH") or "data/sessions.db"

    logger.info("Factory instantiating SQLiteSessionStore at '%s'", db_path)
    return SQLiteSessionStore(db_path=db_path, timeout_seconds=timeout_seconds, **kwargs)


# ---------------------------------------------------------------------------
# Router & Orchestrator Factories
# ---------------------------------------------------------------------------


def create_router(
    slot_filler: FacetedSlotFiller | None = None,
    input_guard: InputGuard | None = None,
    **kwargs: Any,
) -> AdaptiveRouter:
    """Instantiate Adaptive Query Router."""
    slot_filler = slot_filler or FacetedSlotFiller()
    return AdaptiveRouter(slot_filler=slot_filler, input_guard=input_guard, **kwargs)


def create_telemetry_sink(
    sink_type: str = "auto",
    **kwargs: Any,
) -> TelemetrySinkProtocol:
    """Instantiate telemetry sink adapter.

    If sink_type is 'auto':
      1. Checks for LANGFUSE_SECRET_KEY / LANGFUSE_PUBLIC_KEY -> LangfuseTelemetrySink
      2. Checks for PHOENIX_COLLECTOR_ENDPOINT -> PhoenixTelemetrySink
      3. Defaults to InMemoryTelemetrySink.
    Explicit types: 'langfuse', 'phoenix', 'in_memory' / 'memory'.
    """
    import cuk_assistant.observability.in_memory_sink  # noqa: F401
    import cuk_assistant.observability.langfuse_sink  # noqa: F401
    import cuk_assistant.observability.phoenix_sink  # noqa: F401

    st = (sink_type or "auto").lower()

    if st == "auto":
        # Check Langfuse credentials
        if (
            kwargs.get("public_key")
            or kwargs.get("secret_key")
            or (os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"))
        ):
            st = "langfuse"
        elif kwargs.get("endpoint") or os.environ.get("PHOENIX_COLLECTOR_ENDPOINT"):
            st = "phoenix"
        else:
            st = "in_memory"

    cls = get_telemetry_sink_cls(st)
    logger.info("Factory instantiating telemetry sink '%s' (%s)", st, cls.__name__)
    return cls(**kwargs)


def create_rag_orchestrator(
    retrieval_coordinator: HybridRetrievalCoordinator | None = None,
    llm_client: LLMClientProtocol | None = None,
    input_guard: InputGuard | None = None,
    output_guard: OutputGuard | None = None,
    citation_verifier: VerbatimCitationVerifier | None = None,
    session_store: SessionStoreProtocol | None = None,
    router: AdaptiveRouter | None = None,
    telemetry_sink: TelemetrySinkProtocol | None = None,
    system_persona: str | None = None,
    **kwargs: Any,
) -> RAGOrchestrator:
    """Assemble the complete end-to-end RAG orchestrator dependency graph."""
    if telemetry_sink is None:
        telemetry_sink = create_telemetry_sink(**kwargs.get("telemetry_kwargs", {}))

    if retrieval_coordinator is None:
        retrieval_coordinator = create_retrieval_coordinator(
            telemetry_sink=telemetry_sink,
            **kwargs.get("retrieval_kwargs", {}),
        )

    if llm_client is None:
        llm_client = create_llm_pool(**kwargs.get("llm_kwargs", {}))

    if input_guard is None:
        input_guard = create_input_guard(**kwargs.get("input_guard_kwargs", {}))

    if output_guard is None:
        output_guard = create_output_guard(**kwargs.get("output_guard_kwargs", {}))

    if citation_verifier is None:
        citation_verifier = create_citation_verifier(**kwargs.get("verifier_kwargs", {}))

    if session_store is None:
        session_store = create_session_store(**kwargs.get("session_store_kwargs", {}))

    if router is None:
        router = create_router(input_guard=input_guard, **kwargs.get("router_kwargs", {}))

    logger.info("Factory assembling full RAGOrchestrator dependency graph")
    return RAGOrchestrator(
        retrieval_coordinator=retrieval_coordinator,
        llm_client=llm_client,
        input_guard=input_guard,
        output_guard=output_guard,
        citation_verifier=citation_verifier,
        session_store=session_store,
        router=router,
        telemetry_sink=telemetry_sink,
        system_persona=system_persona,
    )


__all__ = [
    "create_citation_verifier",
    "create_embedding_model",
    "create_input_guard",
    "create_llm_pool",
    "create_output_guard",
    "create_rag_orchestrator",
    "create_reranker",
    "create_retrieval_coordinator",
    "create_router",
    "create_session_store",
    "create_telemetry_sink",
    "create_vector_store",
]
