# Original User Request

## Approved Task Prompt — 2026-11-16T17:34:52Z

Command an autonomous team of specialized subagents (Swarm Coordinator & Lead Architect, worker-data, worker-ai, worker-serving, worker-eval) to construct the production-ready Central University of Kashmir (CUK) RAG Assistant (`cuk-assistant`) from end to end.

Working directory: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot
Integrity mode: development

## Verification Resources
- Unit and integration test suites in `tests/unit/` and `tests/integration/`.
- Golden benchmark evaluation dataset in `evals/golden_dataset.jsonl`.

## Requirements

### R1. Non-Negotiable Operational Invariants & Constraints
- Protected Paths (Strict Sandbox): Never read, edit, delete, or inspect files under: `data/cache/`, `data/logs/`, `data/raw/pdf/`, `data/processed/`, and any `*.pdf` files. Never expose or rewrite credentials in `.env` (use `.env.example` as a template).
- $0 / Local-First Compute Rule: Local FastEmbed ONNX (`bge-small-en-v1.5`, 384d, CPU), Embedded LanceDB (Arrow + Tantivy FTS BM25 + RRF $k=60$), Local FlashRank ONNX (`ms-marco-TinyBERT-L-2-v2`, CPU, <20ms), Free-tier multi-provider pool (Google Gemini Flash + Groq `qwen/qwen3.8-27b`) with circuit breaker, Deterministic regex domain router (<1ms, $0) + Groq Llama Guard 3.
- Strict Verbatim Grounding: Zero hallucination. Every factual assertion must be programmatically verified against retrieved context chunks before serving.
- Phase-Gated Skill Discipline: Install required skills before each phase (`npx @rmyndharis/antigravity-skills install <skill>`) and delete immediately after phase sign-off (`rm -rf .agent/skills/<skill>`).
- Observability & Attribution Mandate: Every workflow, API call, and retrieval query must log OpenTelemetry spans to Logfire and traces to Langfuse/Langsmith. Profile TTFT and span execution times. Tag degraded or failed steps with the 12 Diagnostic Failure Codes: `GUARDRAIL_BLOCKED`, `PARSING_DEFECT`, `QUESTION_PARSING_FAILED`, `RETRIEVAL_EMPTY`, `RETRIEVAL_RECALL_MISS`, `MISSED_TOP_RANKED`, `CONTEXT_TRUNCATION`, `LLM_EXTRACTION_FAILURE`, `LLM_HALLUCINATION`, `LLM_FORMAT_VIOLATION`, `OUTPUT_SAFETY_VIOLATION`, `CORPUS_MISSING_CONTENT`.

### R2. Swarm Team Roles & File Boundaries
Tasks are assigned strictly according to file boundaries to ensure zero agent drift:
- `coordinator`: Architecture, Integration & Gatekeeper (`GEMINI.md`, `Makefile`, `docs/`, reviews diffs, runs test gates).
- `worker-data`: Ingestion, Layout Chunking & LanceDB (`cuk_assistant/schemas/`, `cuk_assistant/ingestion/`, `cuk_assistant/retrieval/`).
- `worker-ai`: LLM Pool, Safety Rails & Session Memory (`cuk_assistant/llm/`, `cuk_assistant/guardrails/`, `cuk_assistant/agent/`).
- `worker-serving`: Serving Interfaces & Containerization (`cuk_assistant/api/`, `cuk_assistant/ui/`, `Dockerfile`, `docker-compose.yml`).
- `worker-eval`: Observability, Regression & Evals (`cuk_assistant/observability/`, `cuk_assistant/evals/`, `tests/`).

### R3. Ingestion Lakehouse, Two-Tier Reconciliation & Delta Sync (Phase 1)
- Pydantic v2 metadata schemas (`cuk_assistant/schemas/metadata.py`) with polymorphic domains (Syllabus, Admissions, Results, Datesheets, Notifications, General).
- Normalizers (`metadata_normalizer.py`) for circular IDs, dates, and course codes.
- Two-Tier Reconciler (`reconciler.py`) harmonizing web provenance breadcrumbs with internal PDF facts.
- Delta detector (`delta_detector.py`) tracking `ETag`, `Last-Modified`, and SHA-256 hashes.

### R4. Document Parsing, OCR & Layout-Aware Hierarchical Chunking (Phase 2)
- Chunk models (`cuk_assistant/schemas/chunks.py`) with `ChunkRecord` and `ParentChunkContainer`.
- Docling PDF adapter (`docling_adapter.py`) using RapidOCR and TableFormer for table preservation.
- Intrinsic Fact Extractor (`pdf_fact_extractor.py`) parsing notification headers and reference numbers.
- Heading-aware chunker (`hierarchical_chunker.py`) preserving markdown tables and section ASTs.
- Ingestion runner CLI (`cuk-ingest run`) populating `data/processed/chunks.jsonl`.

### R5. Hybrid LanceDB Storage, FastEmbed & FlashRank Reranker (Phase 3)
- FastEmbed ONNX adapter (`fastembed_adapter.py`, `bge-small-en-v1.5`, 384d, CPU).
- LanceDB store (`lancedb_store.py`) with Tantivy FTS BM25 index, RRF ($k=60$) search fusion, and column filter sanitization against `self._table.schema.names`.
- FlashRank adapter (`flashrank_reranker.py`, `ms-marco-TinyBERT-L-2-v2`, <20ms).
- Hybrid Retrieval Coordinator (`coordinator.py`) with automatic scope relaxation (scoped to global) and deterministic regex circular fallback.

### R6. Free-Tier LLM Pool, Multi-Layer Guardrails & Citation Verifier (Phase 4)
- Gemini Flash and Groq (`qwen/qwen3.8-27b`) adapters enforcing typed Pydantic `AnswerWithCitations` JSON schema.
- `LLMProviderPool` (`pool.py`) with circuit breaker (`CLOSED`, `OPEN`, `HALF_OPEN`) and automatic failover on 429/503.
- Local Domain Classifier (<1ms regex whitelist for academic cohorts, syllabus terms, course acronyms, and slot inputs) + Groq Llama Guard 3 input safety rail (`input_guard.py`).
- Output safety rail (`output_guard.py`) with regex PII scrubbing (phone numbers, national IDs).
- Verbatim Citation Verifier (`citation_verifier.py`) validating that all quoted facts match retrieved chunks.

### R7. Multi-Turn Memory, Pipeline Assembly & Serving Interfaces (Phase 5)
- SQLite WAL Session Store (`session_store.py`) with 4-turn verbatim window and rolling summary.
- Faceted Slot-Filling & Adaptive Router (`slot_filler.py`, `router.py`) disambiguating queries missing `[program, batch_year, semester]`.
- Dependency injection factory (`core/factory.py`) and end-to-end `RAGOrchestrator` (`pipeline/orchestrator.py`).
- FastAPI REST & SSE streaming server (`api/routes/chat.py`, rate limiter middleware).
- Chainlit Web UI (`ui/app.py`) with real-time streaming, quick-reply chips, and citation cards.
- Interactive terminal CLI (`scripts/interactive_chat.py`) supporting multi-turn slot answers.
- UI unit test suite in `tests/unit/test_chainlit_ui.py`.

### R8. Observability, Evals, Containerization & Final Sign-Off (Phase 6)
- Logfire, Langfuse, and Arize Phoenix sinks (`observability/langfuse_sink.py`, `phoenix_sink.py`, `failure_attribution.py`).
- Query Mining CLI (`cuk-eval mine-queries`) updating `configs/menu_hierarchy.json`.
- Golden Evaluation CLI (`cuk-eval run`) and automated regression test suite (`tests/integration/test_golden_regression.py`).
- Production deployment files:
  - Multi-stage CPU `Dockerfile` (Python 3.12, ONNX runtime, FastEmbed model cache, `uv`).
  - `docker-compose.yml` (FastAPI on port 8000, Chainlit UI on port 8001, volumes for `data/lancedb/` and `data/sessions.db`).
- Makefile targets: `make ingest`, `make chat`, `make ui`, `make eval`, `make test`, `make lint`.
- Update `docs/project_status.md` to 100% completion across all milestones.

## Acceptance Criteria

### Verification Gates by Phase
- [ ] Phase 1 Gate: `uv run pytest tests/unit/test_schemas_metadata.py tests/unit/test_metadata_normalizer.py tests/unit/test_reconciliation.py tests/unit/test_delta_detector.py -q` passes with 0 errors.
- [ ] Phase 2 Gate: `uv run pytest tests/unit/test_protocols_chunk.py tests/unit/test_docling_adapter.py tests/unit/test_pdf_fact_extractor.py tests/unit/test_hierarchical_chunker.py tests/unit/test_ingestion_runner.py -q` passes with 0 errors.
- [ ] Phase 3 Gate: `uv run pytest tests/unit/test_fastembed_adapter.py tests/unit/test_lancedb_store.py tests/unit/test_flashrank_reranker.py tests/unit/test_retrieval_coordinator.py -q` passes with 0 errors.
- [ ] Phase 4 Gate: `uv run pytest tests/unit/test_llm_clients.py tests/unit/test_llm_pool.py tests/unit/test_input_guard.py tests/unit/test_output_guard.py tests/unit/test_citation_verifier.py -q` passes with 0 errors.
- [ ] Phase 5 Gate: `uv run pytest tests/unit/test_session_store.py tests/unit/test_router.py tests/unit/test_factory_and_orchestrator.py tests/unit/test_api_endpoints.py tests/unit/test_chainlit_ui.py -q` passes with 0 errors.
- [ ] Phase 6 / Comprehensive Gate: `uv run pytest tests/unit/ -q` and `uv run pytest tests/integration/ -q` pass with 0 errors.
- [ ] Code Quality: `uv run ruff check cuk_assistant/ scripts/ tests/` passes with 0 lint errors or warnings.

### Quality and Evaluation Benchmarks
- [ ] Golden dataset regression test (`tests/integration/test_golden_regression.py` / `uv run cuk-eval run`) asserts Hit Rate@5 >= 0.50 and MRR >= 0.40 on `evals/golden_dataset.jsonl`.
- [ ] Verbatim Grounding: Every factual assertion is programmatically verified against retrieved context chunks before serving.

### Operational Deliverables
- [ ] CLI runs interactively: `uv run python scripts/interactive_chat.py`.
- [ ] FastAPI backend starts and serves endpoints: `uv run uvicorn cuk_assistant.api.main:app --port 8000`.
- [ ] Chainlit Web UI launches with streaming and citation cards: `uv run chainlit run cuk_assistant/ui/app.py -w --port 8001`.
- [ ] Docker stack builds and boots cleanly: `docker compose up --build -d`.
- [ ] Telemetry and attribution: OpenTelemetry spans (Logfire) and traces (Langfuse) emit with execution profiling and the 12 mandatory failure attribution tags.


## Follow-up — 2026-11-16T19:45:27Z

The machine was rebooted following an unexpected laptop shutdown. All subagents have been stopped due to the restart. Please resume and restart the teamwork swarm orchestration from where you left off (Phase 6 / Milestone 6 Iteration 2: worker_m6_it2_1 tasks, gate verification, and final sign-off).
