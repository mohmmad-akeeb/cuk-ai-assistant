# CUK RAG Assistant

A retrieval-augmented generation chatbot for the **Central University of Kashmir (CUK)**. It scrapes the university website, ingests academic documents into a hybrid vector store, and answers student queries with citation-grounded responses.

## What it does

Students ask questions like *"What is the syllabus of DBMS for B.Tech CSE Semester 4?"* The assistant:

1. Classifies the query as an academic intent (syllabus, result, datesheet, admission)
2. Asks follow-up chips if mandatory fields are missing (batch year, semester, course)
3. Retrieves relevant chunks from LanceDB using hybrid vector + BM25 search
4. Reranks with a cross-encoder for precision
5. Generates an answer with Google Gemini (falls back to Groq)
6. Verifies every cited snippet exists verbatim in retrieved documents
7. Streams the response with side-panel citation cards

## Tech stack

| Component | Technology |
|-----------|-----------|
| API | FastAPI (REST + SSE streaming) |
| UI | Chainlit |
| Vector store | LanceDB (hybrid dense + sparse) |
| Full-text search | Tantivy (BM25) |
| Embeddings | FastEmbed — BGE-small-en-v1.5 (384-dim) |
| Reranker | FlashRank — ms-marco-TinyBERT |
| LLM | Google Gemini (primary), Groq (fallback) |
| Session store | SQLite (WAL mode) |
| Observability | Logfire / Langfuse / Phoenix |
| Containerization | Docker + docker-compose |

## Quickstart

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- `.env` file with API keys (see `.env.example`)

### Install

```bash
uv sync
cp .env.example .env  # then fill in GEMINI_API_KEY and GROQ_API_KEY
```

### Ingest documents (offline, run once)

```bash
make ingest    # runs: cuk-crawl → cuk-parse → cuk-ingest → cuk-index
```

This scrapes the CUK website, parses PDFs/HTML, chunks them, embeds, and indexes into LanceDB. See the [ingestion overview](docs/ingestion/overview.md) for details.

### Run the chatbot

```bash
make ui         # Chainlit web UI on http://localhost:8001
make run-api    # FastAPI server on http://localhost:8000
```

### Docker

```bash
make docker-up    # starts API:8000 + UI:8001
make docker-down
```

### Tests

```bash
make test-unit    # unit tests only
make test         # unit + integration
```

## Architecture

The system has three subsystems:

```
A. Ingestion (offline)    →  crawl → parse → normalize → chunk → embed → index
B. Request pipeline (runtime)  →  guardrails → route → retrieve → rerank → LLM → citations
C. Infrastructure         →  DI factory, config, session, telemetry, API, UI
```

All components are wired through dependency injection in `core/factory.py`. New adapters (vector stores, LLM providers, parsers) are added via the registry decorator pattern — zero changes to pipeline code needed.

```
cuk_assistant/
├── core/           # protocols, factory, registry, config
├── ingestion/      # crawl, parse, normalize, chunk, embed, index
├── pipeline/       # orchestrator (the request flow hub)
├── agent/          # router, slot filler, session store
├── guardrails/     # input guard, output guard, citation verifier
├── retrieval/      # LanceDB store, hybrid coordinator, FlashRank reranker
├── llm/            # Gemini client, Groq client, circuit-breaker pool
├── api/            # FastAPI REST + SSE endpoints
├── ui/             # Chainlit web app
├── schemas/        # Pydantic data models
├── observability/  # telemetry sinks, failure attribution
└── evals/          # golden dataset evaluation harness
```

## Documentation

Full documentation lives in [`docs/`](docs/). Start with:

- [**Architecture**](docs/architecture.md) — system design, module map, deployment, caching
- [**Documentation Index**](docs/INDEX.md) — table of contents for all docs

## Configuration

Environment variables are defined in `.env` (see `.env.example`). Key ones:

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY` | Primary LLM provider |
| `GROQ_API_KEY` | Fallback LLM provider |
| `LANCEDB_DIR` | Vector store path (default: `data/lancedb`) |
| `SQLITE_DB_PATH` | Session store path (default: `data/sessions.db`) |

See the [architecture doc](docs/architecture.md#6-deployment-topology) for the full list.

## License

See project repository for license details.
