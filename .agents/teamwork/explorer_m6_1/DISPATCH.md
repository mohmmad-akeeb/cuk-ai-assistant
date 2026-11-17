## 2026-11-16T18:58:04Z
You are explorer_m6_1.
Working directory: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot
State folder: /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m6_1/

MANDATORY: Read /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/ORIGINAL_REQUEST.md before starting work.
Also read:
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/PROJECT.md
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/evals/golden_dataset.jsonl (check lines/size without loading massive chunks, or use tokenade)
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/cuk_assistant/evals/
- /home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/tests/integration/

Task:
Investigate and design specifications for Milestone M6 Evaluation & Regression Suite:
1. `tests/integration/test_golden_regression.py`:
   - Inspect existing `cuk_assistant/evals/benchmark.py` / `evaluator.py` / runner.
   - Formulate test asserting Hit Rate@5 >= 0.50 and MRR >= 0.40 on `evals/golden_dataset.jsonl` using the evaluation harness.
   - Ensure the test integrates with `pytest` and runs efficiently.
2. Query mining and menu hierarchy:
   - Check how `cuk-eval mine-queries` works and how to produce `configs/menu_hierarchy.json`.
3. Schema consolidation:
   - Check `cuk_assistant/schemas/chat.py` requirements per `PROJECT.md:55` and design pure Pydantic models / re-exports.
4. Write your comprehensive analysis and implementation blueprint in `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m6_1/handoff.md`.
5. Send a message to parent with your findings.
DO NOT implement code — you are a read-only explorer.
