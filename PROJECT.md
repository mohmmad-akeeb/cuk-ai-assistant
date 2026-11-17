# Project: cuk-rag-chatbot

## Architecture
- Module/package boundaries, data flow, shared interfaces (adhering to GEMINI.md SoC, DI, OCP)

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Ingestion | Collector, Parser, Normalization | M2 | Survey |
| 2 | Retrieval | Vector/BM25 storage, Reranking | M2 | Survey |
| 3 | LLM/Inference | LLM client, pool management | M2 | Survey |
| 4 | Guardrails | Input/Output safety | M2 | Survey |
| 5 | Observability | Logfire integration | M3 | Survey |
| 6 | API | FastAPI routes, middleware | M1 | Survey |
| 7 | Core | Protocols, Factory | M1 | Survey |
| 8 | Evals | Query miner, schemas | M3 | Survey |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Phase 1: Blueprint & Schemas | Architecture, API, Data Schema | none | DONE |
| 2 | Phase 2: Subsystem Deep-Dives | Ingestion, Retrieval, Guardrails, LLM | M1 | DONE |
| 3 | Phase 3: Ops & DevEx | Ops, Observability, Evals, Contributing | M2 | DONE |

## Interface Contracts
### API ↔ Core
- Standardized request/response models, session handling.

### Core ↔ Components (Ingestion, Retrieval, Guardrails, LLM)
- Abstract Protocols defined in `cuk_assistant/core/protocols/`.
