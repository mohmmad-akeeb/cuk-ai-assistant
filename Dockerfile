# ==============================================================================
# Stage 1: Builder (Dependency compilation & Model pre-warming)
# ==============================================================================
FROM python:3.12-slim-bookworm AS builder

# Prevent interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Astral uv binary directly from official image
COPY --from=ghcr.io/astral-sh/uv:0.5.26 /uv /uvx /bin/

# Copy dependency manifests first for layer caching
COPY pyproject.toml uv.lock README.md ./

# Create virtualenv and install production dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Pre-warm FastEmbed ONNX model (BAAI/bge-small-en-v1.5) and FlashRank reranker
ENV FASTEMBED_CACHE_PATH=/opt/model_cache/fastembed \
    FLASHRANK_CACHE_PATH=/opt/model_cache/flashrank
RUN mkdir -p /opt/model_cache/fastembed /opt/model_cache/flashrank && \
    /app/.venv/bin/python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', cache_dir='/opt/model_cache/fastembed')" && \
    /app/.venv/bin/python -c "from flashrank import Ranker; Ranker(model_name='ms-marco-TinyBERT-L-2-v2', cache_dir='/opt/model_cache/flashrank')"

# Copy source code and build project package
COPY cuk_assistant ./cuk_assistant
COPY configs ./configs
COPY scripts ./scripts

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ==============================================================================
# Stage 2: Runtime (Minimal unprivileged production environment)
# ==============================================================================
FROM python:3.12-slim-bookworm AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PATH="/app/.venv/bin:$PATH" \
    FASTEMBED_CACHE_PATH=/opt/model_cache/fastembed \
    FLASHRANK_CACHE_PATH=/opt/model_cache/flashrank \
    LANCEDB_DIR=/app/data/lancedb \
    SQLITE_DB_PATH=/app/data/sessions.db \
    CHAINLIT_PORT=8001 \
    CHAINLIT_HOST=0.0.0.0

# Install runtime utilities (curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Security: Create dedicated unprivileged user and group
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/bash -m appuser

WORKDIR /app

# Copy virtualenv and cached models from builder stage
COPY --from=builder --chown=appuser:appgroup /app/.venv /app/.venv
COPY --from=builder --chown=appuser:appgroup /opt/model_cache /opt/model_cache

# Copy application source code and configurations
COPY --chown=appuser:appgroup cuk_assistant ./cuk_assistant
COPY --chown=appuser:appgroup configs ./configs
COPY --chown=appuser:appgroup scripts ./scripts
COPY --chown=appuser:appgroup chainlit.md ./chainlit.md
COPY --chown=appuser:appgroup pyproject.toml ./pyproject.toml

# Prepare writable volume mount points with correct non-root permissions
RUN mkdir -p /app/data/lancedb /app/data/logs /app/data/processed /app/.files /app/.chainlit && \
    chown -R appuser:appgroup /app/data /app/.files /app/.chainlit /opt/model_cache

# Switch to unprivileged user
USER appuser

# Expose ports: 8000 (FastAPI), 8001 (Chainlit Web UI)
EXPOSE 8000 8001

# Default healthcheck targeting FastAPI
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default container entrypoint (FastAPI server)
CMD ["uvicorn", "cuk_assistant.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
