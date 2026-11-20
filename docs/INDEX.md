# Documentation Index

> Complete table of contents for the CUK RAG Assistant documentation. Start with [Architecture](./architecture.md) for the system overview.

---

## System-Level

| Document | Description | Flow charts |
|----------|-------------|-------------|
| [README.md](../README.md) | Project overview, tech stack, quickstart commands | — |
| [architecture.md](./architecture.md) | System design, module map, deployment topology, caching strategy, design principles | System overview, module map, DI wiring, data flow, deployment topology, caching layers, entry points |

## Ingestion Pipeline (Offline)

| Document | Description | Flow charts |
|----------|-------------|-------------|
| [ingestion/overview.md](./ingestion/overview.md) | End-to-end 5-stage ingestion pipeline: crawl → parse → normalize → chunk → embed + index | Pipeline stages, data formats, module structure, re-ingestion |
| [ingestion/crawl.md](./ingestion/crawl.md) | Crawler internals: Angular SPA route discovery, API content fetch, PDF downloads | 4-phase crawl flow, node discovery seeds, content fetch dispatch, PDF dedup |
| [ingestion/parse-normalize.md](./ingestion/parse-normalize.md) | Parsing + TwoTierReconciler + PII scrubbing + delta detection | Parse pipeline, HTML/API/PSD paths, PII redaction, delta state machine, metadata reconciliation |
| [ingestion/chunk-index.md](./ingestion/chunk-index.md) | Hierarchical chunking, FastEmbed embeddings, LanceDB indexing | Chunking pipeline, block detection, text splitting, parent-child linking, LanceDB schema |

## Request Pipeline (Runtime)

| Document | Description | Flow charts |
|----------|-------------|-------------|
| [pipeline/overview.md](./pipeline/overview.md) | The 9-step RAGOrchestrator lifecycle from message to response | 9-step lifecycle, routing destinations, short-circuit points, event types |
| [pipeline/guardrails.md](./pipeline/guardrails.md) | Input domain classification, safety rails, PII scrubbing, citation verification | Input guard flow, output guard flow, PII scrubbing steps, citation verification |
| [pipeline/routing-slots.md](./pipeline/routing-slots.md) | AdaptiveRouter intent detection + FacetedSlotFiller chip generation | Routing decision tree, intent detection, slot extraction, slot filling flow, chip generation, metadata filter, **known issues** |
| [pipeline/retrieval-rerank.md](./pipeline/retrieval-rerank.md) | Hybrid vector + BM25 search, RRF fusion, FlashRank reranking, regex fallback | Retrieval lifecycle, hybrid search, where filter sanitization, regex fallback, parent expansion |
| [pipeline/llm-failover.md](./pipeline/llm-failover.md) | Gemini primary + Groq fallback with per-provider circuit breakers | Circuit breaker state machine, failover flow, error hierarchy |
| [pipeline/session.md](./pipeline/session.md) | SQLite WAL session store, rolling context window, summary management | Database schema ERD, session lifecycle, context window, thread-local connections |

## Infrastructure

| Document | Description | Flow charts |
|----------|-------------|-------------|
| [core/di-factory.md](./core/di-factory.md) | Dependency injection factory, registry pattern, 7 protocol interfaces | Factory wiring diagram, registry pattern, telemetry auto-selection, protocol reference |
| [core/schemas.md](./core/schemas.md) | Pydantic v2 data models: metadata, chunks, chat, LLM, retrieval | Schema inheritance tree, chunk schemas, request/response schemas |
| [api-ui/api.md](./api-ui/api.md) | FastAPI REST + SSE endpoints, rate limiting, error envelopes | Application architecture, request flow, endpoints, SSE protocol, rate limiting |
| [api-ui/ui.md](./api-ui/ui.md) | Chainlit UI: chat lifecycle, slot chips, citation cards, feedback | Interaction flow, event handling, slot-filling chip flow, citation rendering |
| [observability/telemetry.md](./observability/telemetry.md) | Telemetry sinks, 12-diagnostic failure codes, feedback recording | Telemetry architecture, 12-code matrix, span recording, InMemory sink |
| [deployment/deployment.md](./deployment/deployment.md) | Docker multi-stage build, model pre-warming, caching layers, env vars | Deployment topology, multi-stage build, caching layers, security |
| [evals/evaluation.md](./evals/evaluation.md) | Golden dataset regression benchmarks, menu hierarchy mining | Evaluation flow, metrics, test case schema, menu mining |

---

## Document Statistics

| Category | Documents | Flow charts |
|----------|-----------|-------------|
| System-level | 2 | 7 |
| Ingestion pipeline | 4 | 8 |
| Request pipeline | 6 | 11 |
| Infrastructure | 7 | 8 |
| **Total** | **19** | **34** |

---

## Reading Order

**New to the system?**

1. [README.md](../README.md) — high-level overview
2. [architecture.md](./architecture.md) — system design and module map
3. [ingestion/overview.md](./ingestion/overview.md) — how data gets in
4. [pipeline/overview.md](./pipeline/overview.md) — how queries get answered
5. [core/di-factory.md](./core/di-factory.md) — how components are wired

**Debugging the slot-filling flow?**

1. [pipeline/routing-slots.md](./pipeline/routing-slots.md) — §9 Known Issues
2. [api-ui/ui.md](./api-ui/ui.md) — §4 Slot-Filling Chip Flow
3. [ingestion/chunk-index.md](./ingestion/chunk-index.md) — §6 LanceDB Schema (metadata_json issue)

**Deploying?**

1. [deployment/deployment.md](./deployment/deployment.md)
2. [architecture.md](./architecture.md) — §6 Deployment Topology, §7 Caching Strategy
