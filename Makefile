.PHONY: install crawl crawl-force nodes nodes-force save-pdfs ingest chat ui run-api eval test test-v test-unit test-network lint fmt fmt-check docker-build docker-up docker-down docker-logs help

# ── Setup ─────────────────────────────────────────────────────────────────────
install:
	uv sync

# ── Ingestion Lakehouse & Vector Indexing ──────────────────────────────────────
crawl:
	uv run cuk-crawl crawl

crawl-force:
	uv run cuk-crawl crawl --force

nodes:
	uv run cuk-crawl build-nodes

nodes-force:
	uv run cuk-crawl build-nodes --force

save-pdfs:
	uv run cuk-crawl save-pdfs

ingest:
	@echo "==> Running document chunking and hierarchical ingestion..."
	uv run cuk-ingest
	@echo "==> Indexing chunks into hybrid LanceDB store (FastEmbed + Tantivy BM25)..."
	uv run cuk-index

# ── Serving Interfaces ────────────────────────────────────────────────────────
chat:
	@echo "==> Launching CUK Assistant interactive terminal CLI..."
	uv run python scripts/interactive_chat.py

ui:
	@echo "==> Launching Chainlit Web UI on port 8001..."
	uv run chainlit run cuk_assistant/ui/app.py -w --port 8001

run-api:
	@echo "==> Launching FastAPI REST & SSE server on port 8000..."
	uv run uvicorn cuk_assistant.api.main:app --host 0.0.0.0 --port 8000 --reload

# ── Regression Benchmarks & Quality Evaluation ─────────────────────────────────
eval:
	@echo "==> Running Golden Regression Benchmark Evaluation Harness..."
	uv run cuk-eval run --top-k 5

# ── Tests ─────────────────────────────────────────────────────────────────────
test:
	@echo "==> Running full unit and integration test suite..."
	uv run pytest tests/unit/ tests/integration/ -q

test-v:
	uv run pytest tests/ -v

test-unit:
	uv run pytest tests/unit/ -v

test-network:
	PYTEST_RUN_NETWORK=1 uv run pytest tests/ -v

# ── Code Quality ──────────────────────────────────────────────────────────────
lint:
	@echo "==> Checking code quality with ruff..."
	uv run ruff check cuk_assistant/ scripts/ tests/
	uv run ruff format --check cuk_assistant/ scripts/ tests/

fmt:
	@echo "==> Formatting codebase with ruff..."
	uv run ruff format cuk_assistant/ scripts/ tests/

fmt-check:
	uv run ruff format --check cuk_assistant/ scripts/ tests/

# ── Containerization (Docker Compose) ─────────────────────────────────────────
docker-build:
	@echo "==> Building production multi-stage CPU Docker image..."
	docker compose build

docker-up:
	@echo "==> Starting CUK Assistant stack (FastAPI: 8000, Chainlit: 8001)..."
	docker compose up -d

docker-down:
	@echo "==> Stopping CUK Assistant container stack..."
	docker compose down

docker-logs:
	docker compose logs -f

# ── Help ──────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "Central University of Kashmir (CUK) RAG Assistant — Makefile Targets"
	@echo "===================================================================="
	@echo "  make install       Install all project dependencies with uv"
	@echo "  make ingest        Run hierarchical chunking and LanceDB hybrid indexing"
	@echo "  make chat          Launch interactive terminal CLI assistant"
	@echo "  make ui            Launch Chainlit Web UI on http://localhost:8001"
	@echo "  make run-api       Launch FastAPI backend on http://localhost:8000"
	@echo "  make eval          Execute golden QA regression benchmark evaluation"
	@echo "  make test          Run all unit and integration test suites"
	@echo "  make test-unit     Run unit test suite"
	@echo "  make test-network  Run network-enabled test suite"
	@echo "  make lint          Verify code standards and format compliance"
	@echo "  make fmt           Format code with ruff"
	@echo "  make fmt-check     Check code formatting with ruff"
	@echo "  make docker-build  Build multi-stage Docker images"
	@echo "  make docker-up     Start docker compose stack in background"
	@echo "  make docker-down   Stop docker compose stack"
	@echo "  make docker-logs   Stream container runtime logs"
	@echo ""
