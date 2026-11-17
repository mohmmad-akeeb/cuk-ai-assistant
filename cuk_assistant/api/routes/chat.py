"""Chat and feedback endpoints (REST and Server-Sent Events).

Governed by docs/api_contracts.md Section 2.2, 2.3, 2.4, FR-7.2, FR-7.3, FR-7.4, and Task 5.4.
Wired directly to the end-to-end RAGOrchestrator.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from cuk_assistant.agent.router import (
    AdaptiveRouter,
)
from cuk_assistant.api.routes.sessions import get_session_store
from cuk_assistant.core.protocols.session import SessionStoreProtocol
from cuk_assistant.core.protocols.telemetry import TelemetrySinkProtocol
from cuk_assistant.observability.in_memory_sink import InMemoryTelemetrySink
from cuk_assistant.pipeline.orchestrator import RAGOrchestrator
from cuk_assistant.schemas.chat import ChatRequest, ChatResponse, FeedbackRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chat", tags=["Chat"])

_global_telemetry_sink: TelemetrySinkProtocol | None = None
_global_router: AdaptiveRouter | None = None
_global_orchestrator: RAGOrchestrator | None = None


def get_telemetry_sink() -> TelemetrySinkProtocol:
    """Dependency provider for telemetry/observability sink."""
    global _global_telemetry_sink
    if _global_telemetry_sink is None:
        _global_telemetry_sink = InMemoryTelemetrySink()
    return _global_telemetry_sink


def get_router() -> AdaptiveRouter:
    """Dependency provider for Adaptive Query Router."""
    global _global_router
    if _global_router is None:
        _global_router = AdaptiveRouter()
    return _global_router


def get_orchestrator() -> RAGOrchestrator:
    """Dependency provider for end-to-end RAGOrchestrator."""
    global _global_orchestrator
    if _global_orchestrator is None:
        from cuk_assistant.core.factory import create_rag_orchestrator

        _global_orchestrator = create_rag_orchestrator()
    return _global_orchestrator


@router.post(
    "/feedback",
    summary="Record user satisfaction feedback",
)
def record_feedback(
    payload: FeedbackRequest,
    sink: TelemetrySinkProtocol = Depends(get_telemetry_sink),
) -> dict[str, str]:
    """Capture thumbs up/down user reaction mapped to trace ID."""
    sink.record_feedback(
        trace_id=payload.trace_id,
        score=payload.score,
        feedback_category=payload.feedback_category,
        comment=payload.comment,
    )
    return {
        "status": "success",
        "recorded_at": datetime.now(UTC).isoformat(),
    }


def _extract_client_ip(request: Request) -> str:
    """Extract client IP from headers or socket address."""
    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    if request.client and request.client.host:
        return str(request.client.host)
    return "127.0.0.1"


@router.post(
    "/stream",
    summary="Streaming conversational chat turn via Server-Sent Events",
)
async def chat_stream(
    request: Request,
    body: ChatRequest,
    orchestrator: RAGOrchestrator = Depends(get_orchestrator),
    store: SessionStoreProtocol = Depends(get_session_store),
    router_engine: AdaptiveRouter = Depends(get_router),
) -> StreamingResponse:
    """Stream token chunks, slot clarification chips, and verified citations."""
    query_text = (body.query or body.message or "").strip()
    if not query_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "EMPTY_QUERY",
                "message": "Query message cannot be empty.",
                "trace_id": uuid.uuid4().hex,
                "details": {},
            },
        )

    session_id = body.session_id or f"sess_{uuid.uuid4().hex}"
    trace_id = uuid.uuid4().hex
    client_ip = _extract_client_ip(request)

    async def sse_generator() -> AsyncGenerator[str, None]:
        try:
            async for event in orchestrator.stream_turn(
                query=query_text,
                session_id=session_id,
                slots=body.slots,
                user_context=body.user_context,
                client_ip=client_ip,
                session_store=store,
                router=router_engine,
                trace_id=trace_id,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as exc:
            logger.exception("SSE stream processing encountered error: %s", exc)
            err_envelope = {
                "type": "error",
                "error_code": "INTERNAL_STREAM_ERROR",
                "message": str(exc),
                "trace_id": trace_id,
            }
            yield f"data: {json.dumps(err_envelope)}\n\n"

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "",
    response_model=ChatResponse,
    summary="Synchronous conversational chat turn",
)
async def chat_sync(
    request: Request,
    body: ChatRequest,
    orchestrator: RAGOrchestrator = Depends(get_orchestrator),
    store: SessionStoreProtocol = Depends(get_session_store),
    router_engine: AdaptiveRouter = Depends(get_router),
) -> ChatResponse:
    """Synchronous chat endpoint for programmatic evaluations and tests."""
    query_text = (body.query or body.message or "").strip()
    if not query_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error_code": "EMPTY_QUERY",
                "message": "Query message cannot be empty.",
                "trace_id": uuid.uuid4().hex,
                "details": {},
            },
        )

    session_id = body.session_id or f"sess_{uuid.uuid4().hex}"
    trace_id = uuid.uuid4().hex
    client_ip = _extract_client_ip(request)

    turn_res = await orchestrator.handle_turn(
        query=query_text,
        session_id=session_id,
        slots=body.slots,
        user_context=body.user_context,
        client_ip=client_ip,
        session_store=store,
        router=router_engine,
        trace_id=trace_id,
    )

    return ChatResponse(
        message_id=turn_res.message_id,
        session_id=turn_res.session_id,
        role=turn_res.role,
        content=turn_res.content,
        quick_replies=turn_res.quick_replies,
        citations=turn_res.citations,
        metadata={"trace_id": trace_id, **(turn_res.metadata or {})},
    )


__all__ = [
    "ChatRequest",
    "ChatResponse",
    "FeedbackRequest",
    "router",
]
