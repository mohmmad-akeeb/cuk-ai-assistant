# FastAPI REST + SSE

> **The REST and Server-Sent Events API surface.** FastAPI serves health probes, starter menu, session history, and streaming chat.
>
> Related: [UI Interaction](./ui.md) · [Pipeline Overview](../pipeline/overview.md)

---

## 1. Purpose

The FastAPI server (`api/main.py`) exposes REST endpoints for programmatic access and SSE streaming for real-time chat. It sits in front of the `RAGOrchestrator` — it contains no business logic, only transport and error handling.

---

## 2. Application Architecture

```mermaid
flowchart TB
    subgraph APP["api/main.py — create_app()"]
        CORS["CORSMiddleware<br/>allow_origins=*"]
        RATE["RateLimiterMiddleware<br/>20 req/hr per IP (sliding window)"]

        subgraph HANDLERS["Global exception handlers"]
            HTTP["StarletteHTTPException → ApiErrorEnvelope<br/>400/401/403/404/429/503"]
            VAL["RequestValidationError → ApiErrorEnvelope<br/>VALIDATION_ERROR (422)"]
            UNHANDLED["Exception → ApiErrorEnvelope<br/>INTERNAL_ERROR (500)"]
        end

        subgraph ROUTES["Route groups"]
            HEALTH["health.router<br/>/health, /api/v1/health"]
            MENU["menu.router<br/>/api/v1/menu/starter"]
            SESSIONS["sessions.router<br/>/api/v1/sessions/{id}"]
            CHAT["chat.router<br/>/api/v1/chat, /api/v1/chat/stream,<br/>/api/v1/chat/feedback"]
        end
    end

    REQUEST["Incoming HTTP request"]
    RESPONSE["JSON / SSE response"]
    ORCHESTRATOR["RAGOrchestrator<br/>(via Depends)"]
    SESSION_STORE["SQLiteSessionStore<br/>(via Depends)"]

    REQUEST --> CORS --> RATE --> ROUTES
    ROUTES --> ORCHESTRATOR
    ROUTES --> SESSION_STORE
    ROUTES --> RESPONSE
    HANDLERS -.->|"on error"| RESPONSE

    style APP fill:#1a2a3a,color:#fff
    style ROUTES fill:#1a3a1a,color:#fff
    style HANDLERS fill:#3a1a1a,color:#fff
```

---

## 3. Request Flow

```mermaid
flowchart TD
    REQ["HTTP Request"]
    CORS["CORS middleware<br/>Allow all origins"]
    RATE["Rate limiter<br/>20 req/hr per IP"]
    ROUTE{"Route matching"}
    DEP["Dependency injection<br/>get_orchestrator()<br/>get_session_store()<br/>get_router()"]
    BIZ["Business logic<br/>(orchestrator.stream_turn or handle_turn)"]
    RESP["Response"]
    ERR["ApiErrorEnvelope<br/>error_code, message,<br/>trace_id, details"]
    RATE_EXCEEDED["429 RATE_LIMITED"]

    REQ --> CORS --> RATE
    RATE -->|"Under limit"| ROUTE
    RATE -->|"Over limit"| RATE_EXCEEDED
    ROUTE --> DEP --> BIZ
    BIZ -->|"Success"| RESP
    BIZ -->|"Exception"| ERR

    style RATE_EXCEEDED fill:#3a1a1a,color:#fff
    style ERR fill:#3a2a1a,color:#fff
    style RESP fill:#1a3a1a,color:#fff
```

---

## 4. Endpoints

### Health

```mermaid
flowchart LR
    GET_HEALTH["GET /health<br/>GET /api/v1/health<br/>Shallow probe"]
    GET_READY["GET /health/ready<br/>Deep probe (DB check)"]
    HEALTH_RES["HealthResponse<br/>status, service, version,<br/>timestamp, components"]

    GET_HEALTH --> HEALTH_RES
    GET_READY --> HEALTH_RES

    style GET_HEALTH fill:#1a3a1a,color:#fff
    style GET_READY fill:#1a3a2a,color:#fff
```

| Method | Path | Response | Notes |
|--------|------|----------|-------|
| GET | `/health` | `HealthResponse` | Shallow probe, no DB check. `Cache-Control: no-store` |
| GET | `/api/v1/health` | `HealthResponse` | Same as `/health` (OpenAPI documented) |
| GET | `/health/ready` | `HealthResponse` | Deep probe: executes `SELECT 1` on SQLite, reports latency. Returns 503 if DB unavailable. |

### Menu

| Method | Path | Response | Notes |
|--------|------|----------|-------|
| GET | `/api/v1/menu/starter` | `StarterMenuResponse` | Returns 5 categories of guided starter prompts. 1-hour public cache. Loads from `configs/menu_hierarchy.json` if available, otherwise uses built-in defaults. |

### Sessions

| Method | Path | Response | Notes |
|--------|------|----------|-------|
| GET | `/api/v1/sessions/{session_id}` | `SessionHistoryResponse` | Full chronological message history + rolling summary. 404 if not found. |
| DELETE | `/api/v1/sessions/{session_id}` | `{status: "deleted"}` | Cascade deletes session + messages + summaries. 404 if not found. |

### Chat

| Method | Path | Response | Notes |
|--------|------|----------|-------|
| POST | `/api/v1/chat` | `ChatResponse` | Synchronous turn via `handle_turn()`. For programmatic evaluation. |
| POST | `/api/v1/chat/stream` | `text/event-stream` (SSE) | Streaming turn via `stream_turn()`. Real-time tokens, slot prompts, citation cards. |
| POST | `/api/v1/chat/feedback` | `{status: "success"}` | Records thumbs up/down feedback to telemetry sink. |

---

## 5. SSE Streaming Protocol

The `/api/v1/chat/stream` endpoint returns Server-Sent Events:

```mermaid
flowchart LR
    REQ["POST /api/v1/chat/stream<br/>Body: ChatRequest<br/>{query, session_id, slots}"]
    SSE["StreamingResponse<br/>media_type='text/event-stream'<br/>Cache-Control: no-cache<br/>Connection: keep-alive"]
    GEN["sse_generator()<br/>async for event in orchestrator.stream_turn()<br/>yield f'data: {json(event)}\\n\\n'"]

    EVENTS["SSE events:<br/>data: {type: 'token', token: 'The ', text: 'The '}<br/>data: {type: 'slot_prompt', target_slot: 'batch_year', ...}<br/>data: {type: 'citation_card', doc_id: '...', ...}<br/>data: {type: 'done', citations: [...], trace_id: '...', ...}"]

    ERROR["data: {type: 'error', error_code: 'INTERNAL_STREAM_ERROR', message: '...', trace_id: '...'}"]

    REQ --> SSE --> GEN
    GEN --> EVENTS
    GEN -.->|"on exception"| ERROR

    style SSE fill:#1a2a3a,color:#fff
    style EVENTS fill:#1a3a1a,color:#fff
    style ERROR fill:#3a1a1a,color:#fff
```

### SSE event format

Each event is a JSON object prefixed with `data: `:

```
data: {"type": "token", "token": "The ", "text": "The "}

data: {"type": "token", "token": "syllabus ", "text": "syllabus "}

data: {"type": "citation_card", "citation_id": "cite_1", "doc_id": "...", "title": "B.Tech CSE Syllabus", "source_url": "...", "page_number": 5, "quoted_snippet": "..."}

data: {"type": "done", "citations": [...], "trace_id": "abc123", "session_id": "sess_xyz"}
```

---

## 6. Rate Limiting

```mermaid
flowchart TD
    REQ["Incoming request"]
    IP["_extract_client_ip()<br/>X-Forwarded-For or socket IP"]
    KEY["Key: hash(client_ip)"]
    CHECK["Sliding window check<br/>20 requests per 3600 seconds"]
    RESULT{"Under limit?"}
    PASS["Proceed to route"]
    BLOCK["429 RATE_LIMITED<br/>ApiErrorEnvelope"]

    REQ --> IP --> KEY --> CHECK --> RESULT
    RESULT -->|"Yes"| PASS
    RESULT -->|"No"| BLOCK

    style BLOCK fill:#3a1a1a,color:#fff
    style PASS fill:#1a3a1a,color:#fff
```

The `RateLimiterMiddleware` uses a sliding window of 20 requests per hour per client IP. The IP is extracted from `X-Forwarded-For` header (for reverse proxies) or the socket address.

---

## 7. Error Envelope

All errors conform to `ApiErrorEnvelope`:

```json
{
  "error_code": "RATE_LIMITED",
  "message": "Rate limit exceeded. Maximum 20 requests per hour.",
  "trace_id": "abc123def456",
  "details": {
    "retry_after_seconds": 3600,
    "limit": 20,
    "window_seconds": 3600
  }
}
```

| HTTP Status | `error_code` | When |
|------------|-------------|------|
| 400 | `BAD_REQUEST` | Malformed request |
| 404 | `NOT_FOUND` | Session not found / empty query |
| 422 | `VALIDATION_ERROR` | Pydantic validation failed |
| 429 | `RATE_LIMITED` | Rate limit exceeded |
| 500 | `INTERNAL_ERROR` | Unhandled exception |
| 503 | `SERVICE_UNAVAILABLE` | Health check deep probe failure |

---

## 8. Dependency Injection in API Routes

Each route uses FastAPI's `Depends()` to get its dependencies. They use lazy singleton pattern:

```python
_global_orchestrator: RAGOrchestrator | None = None

def get_orchestrator() -> RAGOrchestrator:
    global _global_orchestrator
    if _global_orchestrator is None:
        _global_orchestrator = create_rag_orchestrator()
    return _global_orchestrator
```

| Dependency | Provider | Singleton |
|-----------|---------|-----------|
| Orchestrator | `get_orchestrator()` | Yes (module-level) |
| Session store | `get_session_store()` | Yes (module-level) |
| Router | `get_router()` | Yes (module-level) |
| Telemetry sink | `get_telemetry_sink()` | Yes (module-level, InMemory default) |

---

## 9. Key Files

| File | Responsibility |
|------|---------------|
| `api/main.py` | `create_app()` — FastAPI application factory |
| `api/middleware/rate_limiter.py` | `RateLimiterMiddleware` — sliding window IP limiter |
| `api/routes/health.py` | Health and readiness probes |
| `api/routes/menu.py` | Starter menu endpoint |
| `api/routes/sessions.py` | Session history and delete endpoints |
| `api/routes/chat.py` | Chat (sync + SSE) and feedback endpoints |
| `schemas/chat.py` | `ChatRequest`, `ChatResponse`, `FeedbackRequest` |
