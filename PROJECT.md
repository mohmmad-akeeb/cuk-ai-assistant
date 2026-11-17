# Project: CUK RAG Assistant (`cuk-assistant`)

## Architecture
- **Ingestion & Lakehouse**: Dual-tier document metadata reconciliation (Web Tier 1 + PDF Tier 2 intrinsic facts), SHA-256 delta detection, Docling layout extraction with PyMuPDF fallback, heading-aware hierarchical chunker (`ChunkRecord`, `ParentChunkContainer`).
- **Hybrid Storage & Retrieval**: FastEmbed ONNX (`bge-small-en-v1.5`, 384d, CPU), Embedded LanceDB with Tantivy BM25 FTS index, Reciprocal Rank Fusion ($k=60$), FlashRank cross-encoder reranker (`ms-marco-TinyBERT-L-2-v2`, <20ms), and deterministic circular regex fallback.
- **LLM Pool & Guardrails**: Gemini Flash and Groq provider pool with 3-state circuit breaker failover, <1ms regex local domain classifier, Groq Llama Guard 3 input safety, PII regex output scrubber, and verbatim citation grounding verifier.
- **Multi-Turn Memory & Serving**: SQLite WAL Session Store (4-turn sliding window + summary + IP rate limiting), Faceted Slot-Filler, Adaptive Router, FastAPI REST/SSE streaming API, Chainlit interactive UI with quick-reply chips and citation cards, and interactive CLI.
- **Observability & Attribution**: Logfire 22-step atomic span latency profiling, 12 Diagnostic Failure Codes taxonomy, Langfuse and Arize Phoenix sinks, Golden evaluation harness (`cuk-eval`, 55 golden queries), and container deployment.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | UniversalDocMetadata & Polymorphic Schemas | Pydantic v2 metadata models for Syllabus, Admissions, Results, Datesheets, Notifications, General | M1 | Survey / R3 |
| 2 | Circular ID & Date Normalization | Heuristic regex normalizer standardizing circular IDs and ISO-8601 dates | M1 | Survey / R3 |
| 3 | Two-Tier Metadata Reconciliation | Harmonizes web provenance breadcrumbs with internal PDF facts | M1 | Survey / R3 |
| 4 | Delta Sync & Tombstoning | Tracks ETag, Last-Modified, SHA-256 hashes to skip unchanged docs and tombstone deleted docs | M1 | Survey / R3 |
| 5 | ChunkRecord & ParentChunkContainer | Heading-aware chunk data models with parent pointers | M2 | Survey / R4 |
| 6 | Docling & PyMuPDF PDF Parsing | Layout-aware table and section extraction with OCR and offline fallback | M2 | Survey / R4 |
| 7 | Intrinsic Fact Extractor | Extracts official circular IDs, issue dates, signatories from PDF text headers | M2 | Survey / R4 |
| 8 | Hierarchical Chunker | AST section chunking preserving Markdown tables and parent context | M2 | Survey / R4 |
| 9 | Ingestion CLI Runner | Batch ingestion runner (`cuk-ingest run`) populating chunk records | M2 | Survey / R4 |
| 10 | FastEmbed ONNX Adapter | Local CPU embeddings using `BAAI/bge-small-en-v1.5` (384d) | M3 | Survey / R5 |
| 11 | LanceDB Store & Tantivy BM25 | Arrow-backed vector store with Tantivy FTS BM25 index and column sanitization | M3 | Survey / R5 |
| 12 | Reciprocal Rank Fusion (RRF) | Fuses top-30 vector and top-30 BM25 results with $k=60$ | M3 | Survey / R5 |
| 13 | FlashRank Cross-Encoder | Local ONNX reranker (`ms-marco-TinyBERT-L-2-v2`, <20ms) | M3 | Survey / R5 |
| 14 | Hybrid Retrieval Coordinator | Automatic scope relaxation and deterministic regex circular fallback | M3 | Survey / R5 |
| 15 | Gemini Flash & Groq LLM Adapters | Free-tier LLM clients enforcing typed `AnswerWithCitations` schema | M4 | Survey / R6 |
| 16 | LLMProviderPool & Circuit Breaker | 3-state circuit breaker (`CLOSED`, `OPEN`, `HALF_OPEN`) with failover on 429/503 | M4 | Survey / R6 |
| 17 | Local Domain Classifier | Deterministic regex/keyword classifier (<1ms, $0) deflecting out-of-domain queries | M4 | Survey / R6 |
| 18 | Input & Output Safety Rails | Groq Llama Guard 3 input rail and regex PII scrubber (phone numbers, IDs) | M4 | Survey / R6 |
| 19 | Verbatim Citation Verifier | Programmatic verification ensuring quoted facts match retrieved chunks | M4 | Survey / R6 |
| 20 | SQLite WAL Session Store | Concurrency-safe multi-turn session store with 4-turn window, rolling summary, rate limit | M5 | Survey / R7 |
| 21 | Faceted Slot-Filler & Adaptive Router | Disambiguates queries missing `[program, batch_year, semester]`, routes greetings | M5 | Survey / R7 |
| 22 | Dependency Injection Factory & Orchestrator | Central `create_rag_orchestrator` DI factory and end-to-end `RAGOrchestrator` | M5 | Survey / R7 |
| 23 | FastAPI REST & SSE Streaming Server | Endpoints for `/chat/stream`, `/chat/feedback`, `/menu/starter`, `/sessions` | M5 | Survey / R7 |
| 24 | Interactive Terminal CLI | Rich console interactive chat CLI (`scripts/interactive_chat.py`) | M5 | Survey / R7 |
| 25 | Chainlit Web UI & Test Suite | Web UI with streaming, chips, citation cards, and unit tests (`test_chainlit_ui.py`) | M5 | Survey / R7 |
| 26 | Observability & 12 Failure Attribution Codes | Logfire 22-step profiling, Langfuse, Phoenix sinks, 12 diagnostic failure codes | M6 | Survey / R8 |
| 27 | Query Mining CLI & Starter Menu | Mining CLI populating `configs/menu_hierarchy.json` | M6 | Survey / R8 |
| 28 | Golden Evaluation CLI & Regression Suite | Benchmark runner (`cuk-eval run`) and automated regression test (`test_golden_regression.py`)| M6 | Survey / R8 |
| 29 | Containerization (Dockerfile & Compose) | Multi-stage CPU `Dockerfile` and `docker-compose.yml` (FastAPI 8000, Chainlit 8001) | M6 | Survey / R8 |
| 30 | Production Makefile Targets & Status Update | `make chat`, `make ui`, `make eval`, `make ingest`, and `docs/project_status.md` at 100% | M6 | Survey / R8 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Ingestion Lakehouse & Metadata Reconciliation | Schemas, normalizers, reconciler, delta detector | none | DONE |
| M2 | Document Parsing & Hierarchical Chunking | Docling/PyMuPDF parser, fact extractor, hierarchical chunker, runner | M1 | DONE |
| M3 | Hybrid LanceDB Storage & Reranker | FastEmbed ONNX, LanceDB Tantivy FTS, RRF $k=60$, FlashRank, coordinator | M2 | DONE |
| M4 | LLM Pool, Guardrails & Citation Verifier | Gemini/Groq pool, circuit breaker, input/output guards, citation verifier | M3 | DONE |
| M5 | Serving Interfaces, Chainlit UI & Tests | Session store, router, orchestrator, FastAPI SSE, Chainlit UI, `test_chainlit_ui.py` | M4 | DONE |
| M6 | Observability, Evals, Containerization & Sign-Off | Regression suite, menu hierarchy, Dockerfile, docker-compose, Makefile, docs | M5 | DONE |

## Code Layout
- `cuk_assistant/schemas/`: Pure Pydantic v2 data models (`metadata.py`, `chunks.py`, `chat.py`).
- `cuk_assistant/core/protocols/`: Abstract Python `Protocol` interfaces only.
- `cuk_assistant/core/factory.py`: Dependency injection assembly and registry lookup.
- `cuk_assistant/ingestion/`: Layout extraction, normalization, chunking, and CLI runners.
- `cuk_assistant/retrieval/`: FastEmbed, LanceDB storage, FlashRank reranking, and retrieval coordinator.
- `cuk_assistant/llm/`: Gemini/Groq REST clients, circuit breaker pool.
- `cuk_assistant/guardrails/`: Input domain/safety guards, PII scrubber, verbatim citation verifier.
- `cuk_assistant/agent/`: SQLite session store, faceted slot-filler, adaptive router.
- `cuk_assistant/pipeline/`: `RAGOrchestrator` coordinating lifecycle and SSE streaming.
- `cuk_assistant/api/`: FastAPI REST and SSE endpoints, rate limiter middleware.
- `cuk_assistant/ui/`: Chainlit web application (`app.py`).
- `cuk_assistant/observability/`: Diagnostic attribution, Logfire, Langfuse, and Phoenix sinks.
- `cuk_assistant/evals/`: Golden benchmark evaluation harness, query miner, and CLI.
- `scripts/`: Interactive chat CLI (`interactive_chat.py`), ingestion runner (`run_ingest.py`).
- `configs/`: Menu hierarchy (`menu_hierarchy.json`), ingestion filters, sources.
- `tests/unit/`: Unit tests per module.
- `tests/integration/`: Integration tests (`test_live_hybrid_search.py`, `test_golden_regression.py`).
- `evals/`: Golden dataset (`golden_dataset.jsonl`).

## Interface Contracts
### API ↔ Client
- `POST /api/v1/chat/stream`: Accepts `ChatRequest(query, session_id, slots)`, yields SSE events (`text`, `token`, `slot_prompt`, `citations`, `done`, `error`).
- `POST /api/v1/chat/feedback`: Accepts `FeedbackRequest(session_id, trace_id, score: int, comment: Optional[str])`.
- `GET /api/v1/menu/starter`: Returns `StarterMenuResponse` with dynamic category chips.
- `GET /health` & `/health/ready`: System and index readiness checks.

### Pipeline ↔ Serving
- `RAGOrchestratorProtocol`: `stream_query(query: str, session_id: str, client_ip: str) -> AsyncIterator[ServerSentEvent]`
- `RAGOrchestrator.handle_turn(...) -> TurnResult`
