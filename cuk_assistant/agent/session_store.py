"""SQLite WAL multi-turn session store and context memory engine."""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

from cuk_assistant.core.protocols.session import (
    MessageRecord,
    SessionRecord,
    SessionStoreProtocol,
)

_SCHEMA_DDL = """
-- Core sessions table
CREATE TABLE IF NOT EXISTS sessions (
    session_id          TEXT PRIMARY KEY,
    user_type           TEXT NOT NULL DEFAULT 'guest'
                        CHECK (user_type IN ('guest', 'student', 'faculty', 'staff')),
    auth_subject        TEXT,
    ip_hash             TEXT NOT NULL,
    user_agent          TEXT,
    status              TEXT NOT NULL DEFAULT 'active',
    summary             TEXT NOT NULL DEFAULT '',
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_active_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata            TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_last_active
    ON sessions(last_active_at DESC);

CREATE INDEX IF NOT EXISTS idx_sessions_ip_hash
    ON sessions(ip_hash, created_at DESC);

-- Messages table
CREATE TABLE IF NOT EXISTS messages (
    message_id          TEXT PRIMARY KEY,
    session_id          TEXT NOT NULL,
    role                TEXT NOT NULL
                        CHECK (role IN ('user', 'assistant', 'system')),
    content             TEXT NOT NULL,
    tokens              INTEGER NOT NULL DEFAULT 0,
    quoted_citations    TEXT,
    diagnostic_code     TEXT,
    latency_ms          INTEGER,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_session_time
    ON messages(session_id, created_at ASC);

-- Sliding-window rolling session summaries table
CREATE TABLE IF NOT EXISTS session_summaries (
    summary_id          TEXT PRIMARY KEY,
    session_id          TEXT NOT NULL,
    start_message_id    TEXT NOT NULL,
    end_message_id      TEXT NOT NULL,
    turns_covered       INTEGER NOT NULL,
    summary_text        TEXT NOT NULL,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE,
    FOREIGN KEY (start_message_id) REFERENCES messages(message_id) ON DELETE CASCADE,
    FOREIGN KEY (end_message_id) REFERENCES messages(message_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_summaries_session_recent
    ON session_summaries(session_id, created_at DESC);
"""


def _parse_datetime(val: Any) -> datetime:
    """Parse datetime from SQLite column or return current UTC datetime."""
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=UTC)
        return val
    if isinstance(val, str):
        cleaned = val.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(cleaned)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        except ValueError:
            pass
    return datetime.now(UTC)


class SQLiteSessionStore(SessionStoreProtocol):
    """High-concurrency SQLite session store operating in WAL mode."""

    def __init__(
        self,
        db_path: Path | str | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        """Initialize session store with WAL mode pragmas and DDL schema."""
        if db_path is None:
            db_path = os.environ.get("SQLITE_DB_PATH") or "data/sessions.db"
        self._timeout_seconds = timeout_seconds
        self._local = threading.local()
        self._lock = threading.Lock()
        self._connections: list[sqlite3.Connection] = []

        if str(db_path) == ":memory:":
            self._is_memory = True
            self._uri = True
            self._conn_str = f"file:mem_{id(self)}?mode=memory&cache=shared"
            self._keepalive: sqlite3.Connection | None = sqlite3.connect(
                self._conn_str, uri=True, timeout=timeout_seconds
            )
        else:
            self._is_memory = False
            self._db_path = Path(db_path)
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn_str = str(self._db_path)
            self._uri = False
            self._keepalive = None

        self._init_db()

    def _configure_pragmas(self, conn: sqlite3.Connection) -> None:
        """Apply required performance and concurrency pragmas."""
        if not self._is_memory:
            conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA foreign_keys = ON;")

    def _init_db(self) -> None:
        """Run initialization DDL schema."""
        conn = self._get_connection()
        with conn:
            conn.executescript(_SCHEMA_DDL)

    def _get_connection(self) -> sqlite3.Connection:
        """Get or initialize thread-local SQLite connection."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(
                self._conn_str,
                uri=self._uri,
                timeout=self._timeout_seconds,
            )
            conn.row_factory = sqlite3.Row
            self._configure_pragmas(conn)
            self._local.conn = conn
            with self._lock:
                self._connections.append(conn)
        return conn

    @staticmethod
    def _parse_session_row(row: sqlite3.Row) -> SessionRecord:
        metadata = json.loads(row["metadata"]) if row["metadata"] else {}
        return SessionRecord(
            session_id=row["session_id"],
            user_type=row["user_type"],
            auth_subject=row["auth_subject"],
            ip_hash=row["ip_hash"],
            user_agent=row["user_agent"],
            summary=row["summary"] or "",
            status=row["status"] or "active",
            created_at=_parse_datetime(row["created_at"]),
            last_active_at=_parse_datetime(row["last_active_at"]),
            metadata=metadata,
        )

    @staticmethod
    def _parse_message_row(row: sqlite3.Row) -> MessageRecord:
        citations = json.loads(row["quoted_citations"]) if row["quoted_citations"] else []
        return MessageRecord(
            message_id=row["message_id"],
            session_id=row["session_id"],
            role=row["role"],
            content=row["content"],
            tokens=int(row["tokens"]),
            quoted_citations=citations,
            diagnostic_code=row["diagnostic_code"],
            latency_ms=int(row["latency_ms"]) if row["latency_ms"] is not None else None,
            created_at=_parse_datetime(row["created_at"]),
        )

    def get_or_create_session(
        self,
        session_id: str,
        ip_hash: str,
        user_type: str = "guest",
        user_agent: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SessionRecord:
        """Fetch existing session or initialize a new record idempotently."""
        conn = self._get_connection()
        with conn:
            cur = conn.execute(
                "SELECT session_id, user_type, auth_subject, ip_hash, user_agent, "
                "status, summary, created_at, last_active_at, metadata "
                "FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            row = cur.fetchone()
            if row:
                return self._parse_session_row(row)

            now_iso = datetime.now(UTC).isoformat()
            meta_json = json.dumps(metadata or {})
            conn.execute(
                "INSERT INTO sessions ("
                "session_id, user_type, auth_subject, ip_hash, user_agent, "
                "status, summary, created_at, last_active_at, metadata"
                ") VALUES (?, ?, NULL, ?, ?, 'active', '', ?, ?, ?) "
                "ON CONFLICT(session_id) DO NOTHING",
                (session_id, user_type, ip_hash, user_agent, now_iso, now_iso, meta_json),
            )
            cur = conn.execute(
                "SELECT session_id, user_type, auth_subject, ip_hash, user_agent, "
                "status, summary, created_at, last_active_at, metadata "
                "FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            created_row = cur.fetchone()
            if not created_row:
                raise RuntimeError(f"Failed to create or retrieve session '{session_id}'.")
            return self._parse_session_row(created_row)

    def append_message(self, message: MessageRecord) -> None:
        """Persist a dialogue turn message to SQLite and update session last_active_at."""
        conn = self._get_connection()
        citations_json = json.dumps(message.quoted_citations)
        created_at_iso = message.created_at.isoformat()
        with conn:
            conn.execute(
                "INSERT INTO messages ("
                "message_id, session_id, role, content, tokens, "
                "quoted_citations, diagnostic_code, latency_ms, created_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    message.message_id,
                    message.session_id,
                    message.role,
                    message.content,
                    message.tokens,
                    citations_json,
                    message.diagnostic_code,
                    message.latency_ms,
                    created_at_iso,
                ),
            )
            conn.execute(
                "UPDATE sessions SET last_active_at = ? WHERE session_id = ?",
                (created_at_iso, message.session_id),
            )

    def get_context_window(
        self,
        session_id: str,
        window_turns: int = 4,
    ) -> tuple[str, list[MessageRecord]]:
        """Fetch rolling summary and recent messages (last 2*N turns) in chronological order."""
        if window_turns <= 0:
            return self.get_latest_summary(session_id) or "", []

        conn = self._get_connection()
        limit = window_turns * 2

        # 1. Fetch rolling summary
        cur_sum = conn.execute(
            "SELECT summary FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        row_sum = cur_sum.fetchone()
        summary = ""
        if row_sum and row_sum["summary"]:
            summary = row_sum["summary"]
        else:
            cur_fallback = conn.execute(
                "SELECT summary_text FROM session_summaries "
                "WHERE session_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
                (session_id,),
            )
            row_fallback = cur_fallback.fetchone()
            if row_fallback and row_fallback["summary_text"]:
                summary = row_fallback["summary_text"]

        # 2. Fetch last limit messages
        cur_msgs = conn.execute(
            "SELECT message_id, session_id, role, content, tokens, "
            "quoted_citations, diagnostic_code, latency_ms, created_at "
            "FROM messages WHERE session_id = ? "
            "ORDER BY created_at DESC, rowid DESC "
            "LIMIT ?",
            (session_id, limit),
        )
        rows = cur_msgs.fetchall()
        recent_messages = [self._parse_message_row(r) for r in reversed(rows)]
        return summary, recent_messages

    def update_session_summary(self, session_id: str, summary: str) -> None:
        """Update rolling summary of older conversation turns."""
        conn = self._get_connection()
        now_iso = datetime.now(UTC).isoformat()
        with conn:
            cur = conn.execute(
                "UPDATE sessions SET summary = ?, last_active_at = ? WHERE session_id = ?",
                (summary, now_iso, session_id),
            )
            if cur.rowcount == 0:
                raise KeyError(f"Session '{session_id}' not found.")

    def get_session_history(self, session_id: str) -> list[MessageRecord]:
        """Fetch all historical messages for a session in chronological order."""
        conn = self._get_connection()
        cur = conn.execute(
            "SELECT message_id, session_id, role, content, tokens, "
            "quoted_citations, diagnostic_code, latency_ms, created_at "
            "FROM messages WHERE session_id = ? "
            "ORDER BY created_at ASC, rowid ASC",
            (session_id,),
        )
        return [self._parse_message_row(r) for r in cur.fetchall()]

    def delete_session(self, session_id: str) -> bool:
        """Purge session and cascade delete all associated messages and summaries."""
        conn = self._get_connection()
        with conn:
            cur = conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            return cur.rowcount > 0

    def get_recent_turns(
        self,
        session_id: str,
        limit_turns: int = 4,
    ) -> list[MessageRecord]:
        """Fetch the last N turns (2*N user/assistant messages) for prompt context."""
        _, messages = self.get_context_window(session_id, window_turns=limit_turns)
        return messages

    def get_latest_summary(self, session_id: str) -> str | None:
        """Retrieve the rolling summary for turns preceding the window."""
        conn = self._get_connection()
        cur = conn.execute(
            "SELECT summary FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        row = cur.fetchone()
        if row and row["summary"]:
            return str(row["summary"])

        cur_fallback = conn.execute(
            "SELECT summary_text FROM session_summaries "
            "WHERE session_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (session_id,),
        )
        row_fallback = cur_fallback.fetchone()
        if row_fallback and row_fallback["summary_text"]:
            return str(row_fallback["summary_text"])
        return None

    def save_summary(
        self,
        session_id: str,
        start_message_id: str,
        end_message_id: str,
        turns_covered: int,
        summary_text: str,
    ) -> None:
        """Persist compressed conversation history summary."""
        conn = self._get_connection()
        summary_id = str(uuid.uuid4())
        now_iso = datetime.now(UTC).isoformat()
        with conn:
            conn.execute(
                "INSERT INTO session_summaries ("
                "summary_id, session_id, start_message_id, end_message_id, "
                "turns_covered, summary_text, created_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    summary_id,
                    session_id,
                    start_message_id,
                    end_message_id,
                    turns_covered,
                    summary_text,
                    now_iso,
                ),
            )
            conn.execute(
                "UPDATE sessions SET summary = ?, last_active_at = ? WHERE session_id = ?",
                (summary_text, now_iso, session_id),
            )

    def close(self) -> None:
        """Close all connections held by this store instance."""
        with self._lock:
            for conn in self._connections:
                with contextlib.suppress(Exception):
                    conn.close()
            self._connections.clear()
            if self._keepalive:
                with contextlib.suppress(Exception):
                    self._keepalive.close()
                self._keepalive = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
