"""Session store protocol and data models for multi-turn conversation memory."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class MessageRecord(BaseModel):
    """Dialogue message record stored in SQLite."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    message_id: str
    session_id: str
    role: str  # "user" | "assistant" | "system"
    content: str
    tokens: int = 0
    quoted_citations: list[dict[str, Any]] = Field(default_factory=list)
    diagnostic_code: str | None = None
    latency_ms: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SessionRecord(BaseModel):
    """Session record tracking user profile, timestamps, and conversation state."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    session_id: str
    user_type: str = "guest"
    auth_subject: str | None = None
    ip_hash: str
    user_agent: str | None = None
    summary: str = ""
    status: str = "active"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_active_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class SessionStoreProtocol(Protocol):
    """Abstract contract for relational conversation memory in SQLite (WAL mode)."""

    def get_or_create_session(
        self,
        session_id: str,
        ip_hash: str,
        user_type: str = "guest",
        user_agent: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SessionRecord:
        """Fetch existing session or initialize a new record."""
        ...

    def append_message(self, message: MessageRecord) -> None:
        """Persist a user or assistant dialogue turn to SQLite."""
        ...

    def get_context_window(
        self,
        session_id: str,
        window_turns: int = 4,
    ) -> tuple[str, list[MessageRecord]]:
        """Fetch rolling summary and recent messages (last 2*N turns) in chronological order."""
        ...

    def update_session_summary(self, session_id: str, summary: str) -> None:
        """Update rolling summary of older conversation turns."""
        ...

    def get_session_history(self, session_id: str) -> list[MessageRecord]:
        """Fetch all historical messages for a session in chronological order."""
        ...

    def delete_session(self, session_id: str) -> bool:
        """Purge session messages and summaries on client reset."""
        ...

    def get_recent_turns(
        self,
        session_id: str,
        limit_turns: int = 4,
    ) -> list[MessageRecord]:
        """Fetch the last N turns (2*N user/assistant messages) for prompt context."""
        ...

    def get_latest_summary(self, session_id: str) -> str | None:
        """Retrieve the rolling 2-sentence summary for turns preceding the window."""
        ...

    def save_summary(
        self,
        session_id: str,
        start_message_id: str,
        end_message_id: str,
        turns_covered: int,
        summary_text: str,
    ) -> None:
        """Persist compressed conversation history summary."""
        ...
