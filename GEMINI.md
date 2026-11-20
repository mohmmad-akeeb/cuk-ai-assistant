# CUK RAG Assistant — Project Rules

These rules govern all AI coding sessions on this repository. They are always active and must be strictly followed.

---

## 1. Protected Paths & Security (Non-Negotiable)

Never read, list, search, open, edit, copy, or summarize contents from:
- **Caches & Temporary Dirs**: `.cache/`, `**/__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `node_modules/`
- **Data & Raw PDFs**: `data/cache`, `data/logs/`, `data/raw/pdf/`, `data/processed/`, and any `*.pdf` files
- **Credentials & Secrets**: `.env`, `.env.*` (except `.env.example`), `secrets/`, `private/`, `.logfire/`, `*.pem`, `*.key`, `id_rsa*`

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
   - `agent/`: Intent routing, slot filling, and session memory only. Never performs retrieval or LLM generation directly.
   - `api/`: FastAPI REST/SSE transport layer only. Delegates to the orchestrator; contains no business logic.
   - `ui/`: Chainlit web presentation layer only. Consumes the orchestrator streaming protocol; contains no business logic.
   - `observability/`: Telemetry sinks and failure attribution. Read-only diagnostics; never mutates pipeline behavior.
2. **Dependency Injection (DI)**:
   - Components must receive their dependencies via constructors as abstract `Protocol` types.
   - Never instantiate concrete adapters (e.g. `LanceDBStore()`, `GeminiClient()`) inside pipeline or business logic. All instances are assembled in `core/factory.py`.
3. **Open/Closed Principle (OCP)**:
   - New vector databases, parsers, or LLM providers must be added as isolated adapter classes decorated with their registry (e.g. `@register_vector_store("qdrant")`).
   - Adding a new adapter must require **zero modifications** to existing pipeline code.

---

## 3. Ground Truth & Specifications First

1. **Adhere to Specifications**: Implementations must conform strictly to `docs/requirements.md` and approved architectural documents.
2. **Never Assume or Guess APIs**: Verify library signatures using Python stdlib (`inspect`, `typing.get_type_hints`) before writing code. The `tokenade` CLI (`tokenade skeleton`, `tokenade query`) is a convenience when available, not a requirement.
3. **Structured Outputs & Grounding**: LLMs must generate typed Pydantic models (`AnswerWithCitations`). Every factual assertion must be programmatically verified against retrieved context chunks before being served.

---

## 4. Observability & Failure Attribution

1. **Logfire Integration**: Emit structured OpenTelemetry spans via Logfire where it is available. Guard the import (`try: import logfire`) so the pipeline degrades gracefully without it; telemetry must never become a hard dependency that breaks request handling.
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
   - Do not read entire files into context when checking interfaces. Prefer Python stdlib (`inspect`, `typing`) for signatures; `tokenade skeleton <file...>` / `tokenade query <symbol>` are optional conveniences.
   - Scope all searches (`rg` or `git ls-files`) to relevant folders (`cuk_assistant/`, `tests/`).
2. **Keep Output Terse**:
   - Answer directly without conversational preamble or recap.
   - Write the least code that completely works.
3. **Verification Before Completion**:
   - Run `ruff check <modified_files>` and relevant `pytest` suites before declaring any task complete.

---

## 6. Skill Management (Optional)

Skills live in `.agent/skills/` and may help with specialized tasks. Treat the following as a recommendation, not a hard rule:

- Review installed skills before starting a phase; keep only those relevant to the current task to avoid context bloat.
- The `@rmyndharis/antigravity-skills` CLI (`npx @rmyndharis/antigravity-skills install ...`) is a convenience for installing/removing skills when available — it is not required, and skill management can be done manually.
- Remove obsolete skills with care; confirm before deleting directories.

Architectural discipline (SoC, DI, OCP) and ground-truth adherence are covered in §2 and §3 above and are not repeated here.
