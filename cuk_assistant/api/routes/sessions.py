"""Session management endpoints.

Governed by docs/api_contracts.md Section 2.6 and FR-7.1.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from cuk_assistant.agent.session_store import SQLiteSessionStore
from cuk_assistant.core.protocols.session import SessionStoreProtocol

router = APIRouter(prefix="/api/v1/sessions", tags=["Sessions"])


class SessionMessageResponse(BaseModel):
    """Dialogue turn message payload."""

    model_config = ConfigDict(extra="ignore")

    message_id: str
    role: str
    content: str
    tokens: int = 0
    quoted_citations: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str | datetime


class SessionHistoryResponse(BaseModel):
    """Complete session conversation history payload."""

    model_config = ConfigDict(extra="ignore")

    session_id: str
    created_at: str | datetime
    last_active_at: str | datetime
    summary: str = ""
    messages: list[SessionMessageResponse]


_global_session_store: SessionStoreProtocol | None = None


def get_session_store() -> SessionStoreProtocol:
    """Dependency provider for conversation session store."""
    global _global_session_store
    if _global_session_store is None:
        _global_session_store = SQLiteSessionStore("data/sessions.db")
    return _global_session_store


def _get_session_meta(store: SessionStoreProtocol, session_id: str) -> dict[str, Any] | None:
    """Check existence of session and extract metadata."""
    if hasattr(store, "_get_connection"):
        conn = store._get_connection()
        cur = conn.execute(
            "SELECT session_id, created_at, last_active_at, summary FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        row = cur.fetchone()
        if row is not None:
            return {
                "session_id": str(row["session_id"]),
                "created_at": str(row["created_at"]),
                "last_active_at": str(row["last_active_at"]),
                "summary": str(row["summary"] or ""),
            }
        return None

    # Fallback for custom/mock implementations
    history = store.get_session_history(session_id)
    if history:
        return {
            "session_id": session_id,
            "created_at": history[0].created_at.isoformat(),
            "last_active_at": history[-1].created_at.isoformat(),
            "summary": store.get_latest_summary(session_id) or "",
        }
    return None


@router.get(
    "/{session_id}",
    response_model=SessionHistoryResponse,
    summary="Retrieve session history",
)
def get_session(
    session_id: str,
    store: SessionStoreProtocol = Depends(get_session_store),
) -> SessionHistoryResponse:
    """Fetch complete chronological dialogue history for a session."""
    meta = _get_session_meta(store, session_id)
    if meta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "SESSION_NOT_FOUND",
                "message": f"Session '{session_id}' not found.",
                "trace_id": uuid.uuid4().hex,
                "details": {"session_id": session_id},
            },
        )

    messages = store.get_session_history(session_id)
    formatted_messages = [
        SessionMessageResponse(
            message_id=m.message_id,
            role=m.role,
            content=m.content,
            tokens=m.tokens,
            quoted_citations=m.quoted_citations,
            created_at=m.created_at,
        )
        for m in messages
    ]

    return SessionHistoryResponse(
        session_id=meta["session_id"],
        created_at=meta["created_at"],
        last_active_at=meta["last_active_at"],
        summary=meta["summary"],
        messages=formatted_messages,
    )


@router.delete(
    "/{session_id}",
    summary="Delete session history",
)
def delete_session(
    session_id: str,
    store: SessionStoreProtocol = Depends(get_session_store),
) -> dict[str, str]:
    """Purge session and cascade delete all associated messages."""
    deleted = store.delete_session(session_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error_code": "SESSION_NOT_FOUND",
                "message": f"Session '{session_id}' not found.",
                "trace_id": uuid.uuid4().hex,
                "details": {"session_id": session_id},
            },
        )

    return {"status": "deleted", "session_id": session_id}
