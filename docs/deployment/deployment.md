# Deployment

> **Docker multi-stage build, model pre-warming, and caching strategy.**
>
> Related: [Architecture](../architecture.md)

---

## 1. Purpose

The system runs as two Docker services: FastAPI (port 8000) and Chainlit UI (port 8001). A multi-stage Dockerfile builds dependencies and pre-warms ONNX models in the builder stage, then copies them to a minimal runtime image.

---

## 2. Deployment Topology

```mermaid
flowchart TB
    subgraph DOCKER["docker-compose.yml"]
        subgraph API["Service: api"]
            API_CMD["uvicorn cuk_assistant.api.main:app<br/>--host 0.0.0.0 --port 8000"]
            API_HEALTH["Healthcheck: GET /health<br/>30s interval, 5s timeout"]
        end

        subgraph UI["Service: ui"]
            UI_CMD["chainlit run cuk_assistant/ui/app.py<br/>--host 0.0.0.0 --port 8001"]
            UI_HEALTH["Healthcheck: GET /<br/>20s interval, 5s timeout"]
            UI_DEP["depends_on: api (healthy)"]
        end

        subgraph VOL["Volume: cuk_data"]
            LAN["data/lancedb/<br/>chunks.lance + parent_sections.lance"]
            SQL["data/sessions.db"]
        end
    end

    EXT["External services"]
    GEMINI["Google Gemini API"]
    GROQ["Groq API"]
    LF["Logfire / Langfuse<br/>(optional)"]

    API_CMD --> API_HEALTH
    UI_CMD --> UI_HEALTH
    UI_DEP --> API_HEALTH

    API -.->|"shared volume"| LAN
    UI -.->|"shared volume"| LAN
    API -.->|"SQLite"| SQL

    API -->|"primary LLM"| GEMINI
    API -->|"failover LLM"| GROQ
    UI -->|"LLM calls"| GEMINI
    API -.->|"telemetry"| LF

    style API fill:#1a2a3a,color:#fff
    style UI fill:#3a2a1a,color:#fff
    style VOL fill:#1a3a1a,color:#fff
    style EXT fill:#3a1a2a,color:#fff
```

---

## 3. Docker Multi-Stage Build

```mermaid
flowchart TB
    subgraph BUILDER["Stage 1: Builder (python:3.12-slim-bookworm)"]
        B_DEPS["Install build-essential, curl, ca-certificates"]
        B_UV["Install uv binary"]
        B_COPY["COPY pyproject.toml uv.lock README.md"]
        B_SYNC["uv sync --frozen --no-dev<br/>(install production deps)"]
        B_WARM["Pre-warm ONNX models:<br/>• FastEmbed BGE-small-en-v1.5<br/>• FlashRank ms-marco-TinyBERT<br/>→ /opt/model_cache/"]
        B_SRC["COPY cuk_assistant configs scripts<br/>uv sync --frozen --no-dev<br/>(install project package)"]
    end

    subgraph RUNTIME["Stage 2: Runtime (python:3.12-slim-bookworm)"]
        R_DEPS["Install curl, ca-certificates<br/>(for healthcheck only)"]
        R_USER["Create unprivileged user<br/>appuser:appgroup (UID:GID 10001)"]
        R_VENV["COPY .venv from builder<br/>(chown appuser)"]
        R_CACHE["COPY /opt/model_cache from builder<br/>(chown appuser)"]
        R_SRC["COPY app source + configs + scripts<br/>(chown appuser)"]
        R_VOL["mkdir /app/data/lancedb<br/>/app/data/logs /app/data/processed<br/>/app/.files /app/.chainlit"]
        R_SWITCH["USER appuser<br/>(never run as root)"]
        R_PORTS["EXPOSE 8000 8001"]
        R_HEALTH["HEALTHCHECK<br/>GET /health || exit 1"]
        R_CMD["CMD uvicorn cuk_assistant.api.main:app<br/>--host 0.0.0.0 --port 8000"]
    end

    B_DEPS --> B_UV --> B_COPY --> B_SYNC --> B_WARM --> B_SRC
    R_DEPS --> R_USER --> R_VENV --> R_CACHE --> R_SRC --> R_VOL --> R_SWITCH --> R_PORTS --> R_HEALTH --> R_CMD

    B_VENV_OUT[".venv/"] -.->|"COPY --from=builder"| R_VENV
    B_CACHE_OUT["/opt/model_cache/"] -.->|"COPY --from=builder"| R_CACHE

    style BUILDER fill:#1a3a1a,color:#fff
    style RUNTIME fill:#1a2a3a,color:#fff
    style B_WARM fill:#3a2a1a,color:#fff
```

### Model pre-warming

The builder stage downloads and caches ONNX models so the runtime image starts without cold-start latency:

```dockerfile
ENV FASTEMBED_CACHE_PATH=/opt/model_cache/fastembed
ENV FLASHRANK_CACHE_PATH=/opt/model_cache/flashrank

RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/opt/model_cache/fastembed')"
RUN python -c "from flashrank import Ranker; Ranker(model_name='ms-marco-TinyBERT-L-2-v2', cache_dir='/opt/model_cache/flashrank')"
```

---

## 4. Caching Layers

```mermaid
flowchart TB
    subgraph L1["Layer 1: HTTP Response Cache (in-memory)"]
        HTTP["core/http_cache.py<br/>LRU + disk cache<br/>Used by crawler to avoid<br/>duplicate HTTP requests"]
    end

    subgraph L2["Layer 2: ONNX Model Cache (disk, pre-warmed)"]
        FE["FastEmbed<br/>/opt/model_cache/fastembed/<br/>BAAI/bge-small-en-v1.5 (ONNX)"]
        FR["FlashRank<br/>/opt/model_cache/flashrank/<br/>ms-marco-TinyBERT-L-2-v2 (ONNX)"]
    end

    subgraph L3["Layer 3: LanceDB Vector Store (disk)"]
        LAN["data/lancedb/chunks.lance<br/>Arrow columnar: vectors + text<br/>+ metadata_json + Tantivy FTS"]
        PAR["data/lancedb/parent_sections.lance<br/>Parent chunk context expansion"]
    end

    subgraph L4["Layer 4: SQLite Session Store (disk, WAL)"]
        SES["data/sessions.db<br/>Conversation history<br/>Rolling summaries<br/>Feedback records"]
    end

    subgraph SHARED["Shared volume (cuk_data)"]
        DATA["/app/data/"]
    end

    HTTP --> L1
    FE --> L2
    FR --> L2
    LAN --> L3
    PAR --> L3
    SES --> L4
    LAN --> DATA
    SES --> DATA

    style L1 fill:#3a1a2a,color:#fff
    style L2 fill:#2a2a3a,color:#fff
    style L3 fill:#1a3a1a,color:#fff
    style L4 fill:#3a2a1a,color:#fff
    style SHARED fill:#2a2a1a,color:#fff
```

| Layer | Type | Location | Lifetime | Invalidated by |
|-------|------|----------|----------|---------------|
| HTTP cache | In-memory LRU + disk | Process memory + `.cache/` | Process lifetime | TTL expiry |
| Model cache | Disk (ONNX) | `/opt/model_cache/` | Until image rebuild | Docker rebuild |
| LanceDB | Disk (Arrow) | `data/lancedb/` | Until re-indexing | `cuk-index` command |
| SQLite | Disk (WAL) | `data/sessions.db` | Manual deletion | Session delete API |

---

## 5. Environment Variables

| Variable | Default | Required | Purpose |
|----------|---------|----------|---------|
| `GEMINI_API_KEY` | — | Yes (for LLM) | Google Gemini API key |
| `GROQ_API_KEY` | — | Yes (for failover) | Groq API key |
| `GEMINI_MODEL` | `gemini-flash-latest` | No | Gemini model name |
| `GROQ_MODEL` | `qwen/qwen3.8-27b` | No | Groq model name |
| `LANCEDB_DIR` | `data/lancedb` | No | Vector store path |
| `SQLITE_DB_PATH` | `data/sessions.db` | No | Session DB path |
| `FASTEMBED_CACHE_PATH` | — | No | Embedding model cache |
| `FLASHRANK_CACHE_PATH` | — | No | Reranker model cache |
| `LOGFIRE_TOKEN` | — | No | Logfire telemetry |
| `LANGFUSE_PUBLIC_KEY` | — | No | Langfuse telemetry |
| `LANGFUSE_SECRET_KEY` | — | No | Langfuse telemetry |
| `PHOENIX_COLLECTOR_ENDPOINT` | — | No | Phoenix telemetry |
| `BASE_URL` | `https://www.cukashmir.ac.in` | No | Crawler target URL |
| `CONTACT_EMAIL` | — | No | Rate limit contact |
| `CHAINLIT_PORT` | `8001` | No | Chainlit port |
| `CHAINLIT_HOST` | `0.0.0.0` | No | Chainlit bind address |

---

## 6. Docker Compose Commands

```bash
# Build images
make docker-build    # docker compose build

# Start stack (API:8000 + UI:8001)
make docker-up       # docker compose up -d

# View logs
make docker-logs    # docker compose logs -f

# Stop stack
make docker-down    # docker compose down
```

---

## 7. Local Development

```bash
# Install dependencies
make install         # uv sync

# Ingest documents (offline)
make ingest          # cuk-ingest + cuk-index

# Run API server
make run-api         # uvicorn on :8000

# Run UI server
make ui              # chainlit on :8001

# Run tests
make test-unit       # pytest tests/unit/
make test            # pytest tests/unit/ + tests/integration/

# Lint and format
make lint            # ruff check + format check
make fmt             # ruff format
```

---

## 8. Security

| Measure | Implementation |
|---------|---------------|
| Non-root user | Runtime runs as `appuser` (UID 10001) |
| Minimal image | `python:3.12-slim-bookworm` — no dev tools in runtime |
| Secrets in env | API keys via environment variables, not baked into image |
| `.dockerignore` | Excludes `.env`, `.git`, tests, data, caches |
| Rate limiting | 20 req/hr per IP (sliding window) |
| CORS | Configurable origins (currently `*` — tighten for production) |

---

## 9. Key Files

| File | Responsibility |
|------|---------------|
| `Dockerfile` | Multi-stage build (builder + runtime) |
| `docker-compose.yml` | Dual-service compose (API + UI) |
| `.dockerignore` | Excludes secrets, caches, tests from image |
| `Makefile` | All development and deployment commands |
| `.env.example` | Template for environment variables |
