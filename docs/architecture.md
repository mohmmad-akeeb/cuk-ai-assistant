# System Architecture: CUK RAG Assistant

## Overview
The CUK RAG Assistant is a modular Retrieval-Augmented Generation (RAG) system built with strict Separation of Concerns (SoC) and Dependency Injection (DI) to ensure maintainability, scalability, and compliance with Open/Closed Principle (OCP).

## Architectural Invariants
1.  **Separation of Concerns (SoC)**:
    -   `schemas/`: Pure Pydantic data models.
    -   `core/protocols/`: Abstract interface definitions.
    -   `ingestion/`: Layout extraction, OCR, chunking (no DB/LLM calls).
    -   `retrieval/`: Vector/BM25 storage and reranking (no conversational logic).
    -   `guardrails/`: Safety and citation verification.
    -   `llm/`: Inference and structured schema enforcement.
    -   `pipeline/`: Orchestration via injected protocols.
2.  **Dependency Injection (DI)**: Components receive dependencies via constructors as abstract `Protocol` types.
3.  **Open/Closed Principle (OCP)**: New adapters (e.g., vector stores, LLM providers) are registered via registry decorators (`@register_vector_store`, etc.) and require zero modifications to pipeline code.

## Component Layers

### 1. API Layer (`cuk_assistant/api`)
Handles HTTP requests, middleware, and request/response orchestration.

### 2. Guardrails Layer (`cuk_assistant/guardrails`)
Ensures safety of input queries and factual accuracy/citation verification of generated outputs.

### 3. Pipeline Layer (`cuk_assistant/pipeline`)
Orchestrates the RAG flow by utilizing injected protocols (e.g., `RetrievalProtocol`, `LLMClientProtocol`, `TelemetrySinkProtocol`).

### 4. Ingestion Layer (`cuk_assistant/ingestion`)
Robust, scalable ingestion pipeline for processing documents into indexed chunks.

### 5. Retrieval Layer (`cuk_assistant/retrieval`)
Handles vector storage, hybrid search (BM25 + Vector), and reranking.

### 6. LLM Layer (`cuk_assistant/llm`)
Structured interaction with LLM providers with enforced Pydantic schemas for structured outputs (`AnswerWithCitations`).

### 7. Observability (`cuk_assistant/observability`)
Structured OpenTelemetry spans via Logfire, with mandatory failure tagging (e.g., `GUARDRAIL_BLOCKED`, `RETRIEVAL_EMPTY`).
