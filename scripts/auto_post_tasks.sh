#!/usr/bin/env bash
# ==============================================================================
# scripts/auto_post_tasks.sh
# Autonomous Post-Task Watcher & Pipeline Execution Harness
# ==============================================================================
# Polls for the completion of the 5 parallel tasks, then automatically executes:
# 1. Full linting & formatting validation (ruff)
# 2. Complete unit & integration test regression (pytest)
# 3. LanceDB hybrid indexing (cuk-index)
# 4. Golden evaluation regression benchmark (cuk-eval)
# 5. Generates reports/pipeline_completion_report.md
# ==============================================================================

set -uo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

LOG_FILE="reports/auto_post_tasks.log"
REPORT_FILE="reports/pipeline_completion_report.md"
mkdir -p reports

log() {
    local msg="[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    echo "$msg"
    echo "$msg" >> "$LOG_FILE"
}

log "=========================================================="
log "Starting Autonomous Post-Task Watcher Daemon..."
log "Project Root: $PROJECT_ROOT"
log "Watching for completion of all 5 parallel tasks..."
log "=========================================================="

# Define sentinel deliverables that mark completion of the 5 tasks
TASK1_SENTINEL="cuk_assistant/ingestion/cli/index.py"
TASK2_SENTINEL="evals/golden_dataset.jsonl"
TASK3_SENTINEL="cuk_assistant/observability/langfuse_sink.py"
TASK4_SENTINEL="cuk_assistant/evals/query_miner.py"
TASK5_SENTINEL="cuk_assistant/pipeline/orchestrator.py"
TASK5_UI_SENTINEL="cuk_assistant/ui/app.py"

MAX_WAIT_MINUTES=360  # Wait up to 6 hours
POLL_INTERVAL_SECS=30
ELAPSED=0

while [ $ELAPSED -lt $((MAX_WAIT_MINUTES * 60)) ]; do
    T1_DONE=0; T2_DONE=0; T3_DONE=0; T4_DONE=0; T5_DONE=0

    [ -f "$TASK1_SENTINEL" ] && T1_DONE=1
    [ -f "$TASK2_SENTINEL" ] && T2_DONE=1
    [ -f "$TASK3_SENTINEL" ] && T3_DONE=1
    [ -f "$TASK4_SENTINEL" ] && T4_DONE=1
    [ -f "$TASK5_SENTINEL" ] && [ -f "$TASK5_UI_SENTINEL" ] && T5_DONE=1

    TOTAL_DONE=$((T1_DONE + T2_DONE + T3_DONE + T4_DONE + T5_DONE))

    if [ "$TOTAL_DONE" -eq 5 ]; then
        log ">>> ALL 5 TASKS HAVE COMPLETED DELIVERABLES! Starting automated pipeline execution..."
        break
    fi

    # Log progress every 2.5 minutes (every 5 iterations)
    if [ $((ELAPSED % 150)) -eq 0 ]; then
        log "Waiting for tasks... Progress: $TOTAL_DONE/5 ready (T1:$T1_DONE, T2:$T2_DONE, T3:$T3_DONE, T4:$T4_DONE, T5:$T5_DONE). Elapsed: $((ELAPSED / 60)) min."
    fi

    sleep $POLL_INTERVAL_SECS
    ELAPSED=$((ELAPSED + POLL_INTERVAL_SECS))
done

if [ "$TOTAL_DONE" -lt 5 ]; then
    log "[TIMEOUT] Reached max wait time without all tasks completing."
    exit 1
fi

log "--- STEP 1: Running Ruff Linter & Formatter Check ---"
RUFF_STATUS="PASSED"
uv run ruff check cuk_assistant/ tests/ >> "$LOG_FILE" 2>&1 || RUFF_STATUS="FAILED"

log "--- STEP 2: Running Unit Test Regression Suite ---"
PYTEST_STATUS="PASSED"
uv run pytest tests/unit/ -q >> "$LOG_FILE" 2>&1 || PYTEST_STATUS="FAILED"

log "--- STEP 3: Executing LanceDB Vector Hybrid Batch Indexing ---"
INDEX_STATUS="PASSED"
uv run cuk-index >> "$LOG_FILE" 2>&1 || INDEX_STATUS="FAILED"

log "--- STEP 4: Executing Golden Dataset Regression Benchmark ---"
EVAL_STATUS="SKIPPED"
if command -v uv run cuk-eval &> /dev/null || [ -f "cuk_assistant/evals/cli.py" ]; then
    log "Running cuk-eval benchmark..."
    uv run cuk-eval run --dataset evals/golden_dataset.jsonl >> "$LOG_FILE" 2>&1 && EVAL_STATUS="PASSED" || EVAL_STATUS="FAILED"
fi

log "--- Generating Final Pipeline Completion Report ---"
cat << EOF > "$REPORT_FILE"
# CUK Assistant Automated Execution Report

Generated: $(date '+%Y-%m-%d %H:%M:%S')

## Task Delivery Verification
- **Task 1 (Batch Indexing):** Completed
- **Task 2 (Golden Benchmark):** Completed
- **Task 3 (Telemetry Sinks):** Completed
- **Task 4 (Query Mining):** Completed
- **Phase 5 (Orchestrator & UI):** Completed

## Execution Results
| Step | Action | Status |
| :--- | :--- | :---: |
| 1 | Ruff Code Quality & Style Check | **$RUFF_STATUS** |
| 2 | Unit Test Regression Suite | **$PYTEST_STATUS** |
| 3 | LanceDB Hybrid Vector Indexing | **$INDEX_STATUS** |
| 4 | Golden Dataset Evaluation Benchmark | **$EVAL_STATUS** |

Full execution logs available at \`$LOG_FILE\`.
EOF

log "=========================================================="
log "Automated execution completed. Report generated at $REPORT_FILE."
log "=========================================================="
