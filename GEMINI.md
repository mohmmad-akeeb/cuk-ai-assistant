# Antigravity Agent Project Rules: CUK RAG Assistant

These rules govern all AI coding sessions on this repository. They are always active and must be strictly followed.

---

## 1. Protected Paths & Security (Non-Negotiable)

Never read, list, search, open, edit, copy, or summarize contents from:
- **Caches & Temporary Dirs**: `.cache/`, `**/__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `node_modules/`
- **Data & Raw PDFs**: `data/cache`, `data/logs/`, `data/raw/pdf/`, `data/processed/`, and any `*.pdf` files
- **Credentials & Secrets**: `.env`, `.env.*` (except `.env.example`), `secrets/`, `private/`, `*.pem`, `*.key`, `id_rsa*`

*Invariant*: Terminal commands (`cat`, `head`, `grep`, `find`, `strings`, `python`) must never be used to bypass these restrictions. If a task requires touching external networks, ask for explicit approval first.

---

## 2. Core Architectural Invariants

Every file and feature added to `cuk_assistant` must strictly adhere to:
1. **Separation of Concerns (SoC)**:
   - `schemas/`: Pure Pydantic data models with zero external database/vendor dependencies.
   - `core/protocols/`: Abstract Python `Protocol` interfaces only (type signatures, no implementations).
   - `ingestion/`: Layout extraction, OCR, and chunking only. Never calls vector databases or LLMs.
   - `retrieval/`: Vector/BM25 storage and reranking only. Never formulates conversational responses.
   - `guardrails/`: Input/output safety and citation verification only.
   - `llm/`: Inference, structured schema enforcement, and provider load-balancing only.
   - `pipeline/`: Workflow orchestration via injected protocols. Never instantiates concrete classes directly.
2. **Dependency Injection (DI)**:
   - Components must receive their dependencies via constructors as abstract `Protocol` types.
   - Never instantiate concrete adapters (e.g. `LanceDBStore()`, `GeminiClient()`) inside pipeline or business logic. All instances are assembled in `core/factory.py`.
3. **Open/Closed Principle (OCP)**:
   - New vector databases, parsers, or LLM providers must be added as isolated adapter classes decorated with their registry (e.g. `@register_vector_store("qdrant")`).
   - Adding a new adapter must require **zero modifications** to existing pipeline code.

---

## 3. Ground Truth & Specifications First

1. **Adhere to Specifications**: Implementations must conform strictly to `docs/requirements.md` and approved architectural documents.
2. **Never Assume or Guess APIs**: Verify library signatures using Python stdlib or `tokenade skeleton` before writing code.
3. **Structured Outputs & Grounding**: LLMs must generate typed Pydantic models (`AnswerWithCitations`). Every factual assertion must be programmatically verified against retrieved context chunks before being served.

---

## 4. Observability & Failure Attribution

1. **Logfire Integration**: Every workflow, API endpoint, and async task must emit structured OpenTelemetry spans via Logfire.
2. **Mandatory Failure Tagging**: When a step fails, degrades, or returns an empty result, tag the span with the precise diagnostic code:
   - `GUARDRAIL_BLOCKED`
   - `PARSING_DEFECT`
   - `QUESTION_PARSING_FAILED`
   - `RETRIEVAL_EMPTY`
   - `RETRIEVAL_RECALL_MISS`
   - `MISSED_TOP_RANKED`
   - `CONTEXT_TRUNCATION`
   - `LLM_EXTRACTION_FAILURE`
   - `LLM_HALLUCINATION`
   - `LLM_FORMAT_VIOLATION`
   - `OUTPUT_SAFETY_VIOLATION`
   - `CORPUS_MISSING_CONTENT`

---

## 5. Token Optimization & Development Workflow

1. **Lean Code Exploration**:
   - Do not read entire files into context when checking interfaces. Use:
     `tokenade skeleton <file...>` (for class/function signatures)
     `tokenade query <symbol>` (to locate symbols)
   - Scope all searches (`rg` or `git ls-files`) to relevant folders (`src/`, `cuk_assistant/`, `tests/`).
2. **Keep Output Terse**:
   - Answer directly without conversational preamble or recap.
   - Write the least code that completely works.
3. **Verification Before Completion**:
   - Run `ruff check <modified_files>` and relevant `pytest` suites before declaring any task complete.

---

## 6. Dynamic Skill Lifecycle & Working Discipline

1. **Phase-Gated Skill Management**:
   - Actively manage skills in `.agent/skills/` using `@rmyndharis/antigravity-skills`.
   - Before starting any phase or task, proactively suggest which specialized skills to install (`npx @rmyndharis/antigravity-skills install ...`) and immediately clean up/remove obsolete skills (`rm -rf .agent/skills/<name>`) to minimize token consumption and prevent context bloat.
2. **Ground-Truth First & Zero Premature Coding**:
   - Strictly follow the established specifications: `docs/requirements.md`, `docs/architecture.md`, `docs/database_schema.md`, and `docs/api_contracts.md`.
   - Never guess or write ungrounded code without explicit alignment on schemas and contracts.
3. **Rigorous Architectural Discipline**:
   - Enforce Separation of Concerns (SoC), Dependency Injection (DI) via `Protocol` types, and Open/Closed Principle (OCP) across all files.

