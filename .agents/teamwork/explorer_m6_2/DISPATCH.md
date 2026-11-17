## 2026-11-16T18:58:04Z
Task:
Investigate and design specifications for Milestone M6 Containerization & Makefile targets:
1. Multi-stage CPU `Dockerfile`:
   - Python 3.12, ONNX runtime, FastEmbed model cache (`BAAI/bge-small-en-v1.5`), `uv`.
   - Security best practices (non-root user, lean layers, `.dockerignore`).
2. `docker-compose.yml`:
   - Service 1: FastAPI (`cuk_assistant.api.main:app`) on port 8000.
   - Service 2: Chainlit Web UI (`cuk_assistant/ui/app.py`) on port 8001.
   - Shared volumes for `data/lancedb/` and `data/sessions.db`.
   - Health checks and environment variable mappings.
3. `Makefile`:
   - Targets: `make ingest`, `make chat`, `make ui`, `make eval`, `make test`, `make lint`.
4. Write your comprehensive blueprint in `/home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/.agents/teamwork/explorer_m6_2/handoff.md`.
5. Send a message to parent with your findings.
DO NOT implement code — you are a read-only explorer.
