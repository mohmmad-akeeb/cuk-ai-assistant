"""Health and readiness probe endpoints.

Governed by docs/api_contracts.md Section 2.1.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, ConfigDict

from cuk_assistant.api.routes.sessions import get_session_store
from cuk_assistant.core.protocols.session import SessionStoreProtocol

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    """Health status response model."""

    model_config = ConfigDict(extra="ignore")

    status: str
    service: str = "cuk-assistant"
    version: str = "0.1.0"
    timestamp: str
    components: dict[str, Any] | None = None


@router.get(
    "/api/v1/health",
    response_model=HealthResponse,
    summary="Health check probe",
)
@router.get(
    "/health",
    response_model=HealthResponse,
    include_in_schema=False,
)
def get_health(
    response: Response,
    deep: bool = Query(default=False, description="Run deep subsystem dependency probes"),
    store: SessionStoreProtocol = Depends(get_session_store),
) -> HealthResponse:
    """Check ASGI process uptime and optional deep database accessibility."""
    response.headers["Cache-Control"] = "no-cache, no-store"
    now_iso = datetime.now(UTC).isoformat()

    if not deep:
        return HealthResponse(
            status="healthy",
            service="cuk-assistant",
            version="0.1.0",
            timestamp=now_iso,
        )

    components: dict[str, Any] = {}
    is_ready = True

    try:
        if hasattr(store, "_get_connection"):
            conn = store._get_connection()
            t0 = time.perf_counter()
            conn.execute("SELECT 1;").fetchone()
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            components["sqlite_session_db"] = {
                "status": "ready",
                "journal_mode": "wal",
                "latency_ms": latency_ms,
            }
        else:
            components["sqlite_session_db"] = {"status": "ready"}
    except Exception as exc:
        is_ready = False
        components["sqlite_session_db"] = {
            "status": "error",
            "error": str(exc),
        }

    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthResponse(
            status="not_ready",
            service="cuk-assistant",
            version="0.1.0",
            timestamp=now_iso,
            components=components,
        )

    return HealthResponse(
        status="healthy",
        service="cuk-assistant",
        version="0.1.0",
        timestamp=now_iso,
        components=components,
    )


@router.get(
    "/health/ready",
    response_model=HealthResponse,
    summary="Deep readiness probe",
)
def get_readiness(
    response: Response,
    store: SessionStoreProtocol = Depends(get_session_store),
) -> HealthResponse:
    """Explicit deep readiness probe endpoint."""
    return get_health(response=response, deep=True, store=store)
