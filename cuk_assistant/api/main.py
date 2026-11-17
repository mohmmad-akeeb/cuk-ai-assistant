"""FastAPI REST & Server-Sent Events (SSE) Application Entrypoint.

Governed by docs/api_contracts.md, docs/requirements.md FR-7.2, FR-7.3, and GEMINI.md.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from cuk_assistant.api import ApiErrorEnvelope
from cuk_assistant.api.middleware.rate_limiter import RateLimiterMiddleware
from cuk_assistant.api.routes import chat, health, menu, sessions

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Application factory for CUK RAG Assistant API."""
    app = FastAPI(
        title="CUK RAG Assistant API",
        description="Official REST & Server-Sent Events API for Central University of Kashmir AI Assistant.",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # 1. CORS Configuration for Web and Mobile Clients
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2. Sliding-Window IP Rate Limiter (20 req/hour for guest)
    app.add_middleware(RateLimiterMiddleware, max_requests=20, window_seconds=3600)

    # 3. Global Exception Handlers conforming to ApiErrorEnvelope
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        trace_id = uuid.uuid4().hex
        if isinstance(exc.detail, dict) and "error_code" in exc.detail:
            envelope = ApiErrorEnvelope(
                error_code=exc.detail["error_code"],
                message=exc.detail.get("message", "An HTTP error occurred."),
                trace_id=exc.detail.get("trace_id") or trace_id,
                details=exc.detail.get("details", {}),
            )
        else:
            code_mapping = {
                400: "BAD_REQUEST",
                401: "UNAUTHORIZED",
                403: "FORBIDDEN",
                404: "NOT_FOUND",
                429: "RATE_LIMIT_EXCEEDED",
                503: "SERVICE_UNAVAILABLE",
            }
            error_code = code_mapping.get(exc.status_code, f"HTTP_{exc.status_code}")
            envelope = ApiErrorEnvelope(
                error_code=error_code,
                message=str(exc.detail),
                trace_id=trace_id,
                details={},
            )

        headers: dict[str, str] = {}
        if getattr(exc, "headers", None):
            headers.update(exc.headers)  # type: ignore[arg-type]
        headers["X-Trace-ID"] = envelope.trace_id

        return JSONResponse(
            status_code=exc.status_code,
            content=envelope.model_dump(),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        trace_id = uuid.uuid4().hex
        clean_errors: list[dict[str, Any]] = []
        for err in exc.errors():
            clean_errors.append(
                {
                    "loc": [str(loc_item) for loc_item in err.get("loc", [])],
                    "msg": err.get("msg", ""),
                    "type": err.get("type", ""),
                }
            )

        envelope = ApiErrorEnvelope(
            error_code="VALIDATION_ERROR",
            message="Request payload failed schema validation constraints.",
            trace_id=trace_id,
            details={"errors": clean_errors},
        )
        return JSONResponse(
            status_code=422,
            content=envelope.model_dump(),
            headers={"X-Trace-ID": trace_id},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        trace_id = uuid.uuid4().hex
        logger.exception("Unhandled server defect on %s: %s", request.url.path, exc)
        envelope = ApiErrorEnvelope(
            error_code="INTERNAL_ERROR",
            message="An unexpected server defect occurred.",
            trace_id=trace_id,
            details={"error_type": exc.__class__.__name__},
        )
        return JSONResponse(
            status_code=500,
            content=envelope.model_dump(),
            headers={"X-Trace-ID": trace_id},
        )

    # 4. Register Subsystem Route Handlers
    app.include_router(health.router)
    app.include_router(menu.router)
    app.include_router(sessions.router)
    app.include_router(chat.router)

    return app


app = create_app()
