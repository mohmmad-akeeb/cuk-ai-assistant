# Task Assignment: Test & Eval Explorer (Survey)

## Mission
Survey the existing test suites, benchmark evaluation datasets, and verification tooling across all 6 phases.

## Working Directory
/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot

## State Directory
/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_survey_3/

## Mandatory Reading
Read `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md` before starting work.

## Scope of Investigation
- Check existing unit tests under `tests/unit/`.
- Check existing integration tests under `tests/integration/`.
- Check evaluation datasets under `evals/` (e.g., `evals/golden_dataset.jsonl`).
- Check test configurations (`pytest.ini` / `pyproject.toml`).
- Assess current test coverage and mapping against the phase verification gates:
  * Phase 1 Gate: tests/unit/test_schemas_metadata.py, test_metadata_normalizer.py, test_reconciliation.py, test_delta_detector.py
  * Phase 2 Gate: tests/unit/test_protocols_chunk.py, test_docling_adapter.py, test_pdf_fact_extractor.py, test_hierarchical_chunker.py, test_ingestion_runner.py
  * Phase 3 Gate: tests/unit/test_fastembed_adapter.py, test_lancedb_store.py, test_flashrank_reranker.py, test_retrieval_coordinator.py
  * Phase 4 Gate: tests/unit/test_llm_clients.py, test_llm_pool.py, test_input_guard.py, test_output_guard.py, test_citation_verifier.py
  * Phase 5 Gate: tests/unit/test_session_store.py, test_router.py, test_factory_and_orchestrator.py, test_api_endpoints.py, test_chainlit_ui.py
  * Phase 6 / Comprehensive Gate: tests/unit/ and tests/integration/ (including test_golden_regression.py)
- Note which test files already exist and their contents/expectations, and which test files are missing.

## Strict Sandbox Rule
NEVER read, edit, delete, or inspect files under:
`data/cache/`, `data/logs/`, `data/raw/pdf/`, `data/processed/`, and any `*.pdf` files.
Never expose secrets or `.env`.

## Deliverable
Write your detailed report to `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_survey_3/handoff.md` and send a completion message with summary.


## 2026-11-16T17:38:16Z
[Message] timestamp=2026-11-16T17:38:16Z sender=30963065-bb08-41aa-acec-725022359cce priority=MESSAGE_PRIORITY_HIGH content=You are assigned to survey the test suites, verification gates, and evaluation datasets for cuk-rag-chatbot.
Read your assignment at `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_survey_3/DISPATCH.md`.
Read `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md` before starting work.
Working directory: `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot`.
State directory: `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_survey_3/`.
Strict sandbox: NEVER inspect, read, edit, or delete files under `data/cache/`, `data/logs/`, `data/raw/pdf/`, `data/processed/`, or any `*.pdf` files.
Write your findings to `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_survey_3/handoff.md` and message the orchestrator when done.
