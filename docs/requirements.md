# Requirements Specification: CUK RAG Assistant

## 1. Introduction
The CUK RAG Assistant is a modular, scalable Retrieval-Augmented Generation system designed for robustness, maintainability, and strict adherence to architectural invariants as defined in the [System Architecture](architecture.md).

## 2. Functional Requirements
The system must support the following core capabilities:
- **Modular Ingestion Pipeline**: Scalable document collection, parsing, and normalization, decoupled from storage and LLM services ([Ingestion Layer](ingestion_pipeline/parsers.md)).
- **Hybrid Retrieval**: Effective vector and BM25 search capabilities combined with reranking mechanisms ([Retrieval Strategy](retrieval_strategy.md)).
- **LLM-Driven Inference**: Structured interaction with LLM providers with enforced Pydantic schema validation ([LLM Documentation](llm/llm_layer.md) - *need to check if this exists*).
- **Safety & Guardrails**: Input/output safety and citation verification for factual grounding ([Guardrails](guardrails.md)).
- **Observability**: Comprehensive logging and tracing using OpenTelemetry via Logfire ([Observability](ops/observability.md)).
- **API Interfaces**: Robust HTTP endpoints for user interaction ([API Contracts](api_contracts.md)).

## 3. Architectural Requirements (Non-Negotiable)
As per the [Architecture Documentation](architecture.md), all components MUST adhere to:
- **Separation of Concerns (SoC)**: Strict isolation of layers (`schemas/`, `core/`, `ingestion/`, etc.).
- **Dependency Injection (DI)**: Components MUST NOT instantiate concrete implementations; they must receive abstract `Protocol` types via constructors.
- **Open/Closed Principle (OCP)**: New adapters (vector stores, LLM providers) must be added via registry mechanisms without modifying the `pipeline/` code.
- **Failure Observability**: All failures must be tagged with mandatory diagnostic codes (e.g., `RETRIEVAL_EMPTY`, `LLM_HALLUCINATION`) as defined in [Observability](ops/observability.md).

## 4. Data & Schema Requirements
- All data models must be pure Pydantic models with no external dependencies ([Data Schema](data_schema.md)).

---
*See [System Architecture](architecture.md) for detailed design principles.*
