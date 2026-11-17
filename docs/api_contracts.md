# API Contracts

## Overview
The CUK RAG Assistant API is built with FastAPI. It enforces strict schemas for requests and responses.

## Endpoints

### 1. Chat
`POST /chat`
- **Request**: `{ query: str, session_id: str, history: list[dict] }`
- **Response**: `{ answer: str, citations: list[str], trace_id: str }`

### 2. Health
`GET /health`
- **Response**: `{ status: "ok" }`

### 3. Menu
`GET /menu`
- **Response**: `{ items: list[dict] }`

### 4. Sessions
`GET /sessions/{session_id}`
- **Response**: `{ session_data: dict }`


## Error Handling
All endpoints return structured error responses with failure diagnostic codes for observability.

---

## Related Documentation
- [System Requirements](requirements.md)
- [System Architecture](architecture.md)
