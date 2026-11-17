"""Unit tests for SQLite WAL multi-turn session store and context memory engine."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cuk_assistant.agent.session_store import SQLiteSessionStore
from cuk_assistant.core.protocols.session import (
    MessageRecord,
    SessionRecord,
    SessionStoreProtocol,
)


def test_protocol_conformance() -> None:
    """Verify SQLiteSessionStore conforms to SessionStoreProtocol."""
    with SQLiteSessionStore(":memory:") as store:
        assert isinstance(store, SessionStoreProtocol)


def test_get_or_create_session() -> None:
    """Verify creating a session and idempotent retrieval."""
    with SQLiteSessionStore(":memory:") as store:
        sess = store.get_or_create_session(
            session_id="sess-001",
            ip_hash="hash-123",
            user_type="student",
            user_agent="Mozilla/5.0",
            metadata={"department": "CSE"},
        )
        assert isinstance(sess, SessionRecord)
        assert sess.session_id == "sess-001"
        assert sess.user_type == "student"
        assert sess.ip_hash == "hash-123"
        assert sess.user_agent == "Mozilla/5.0"
        assert sess.status == "active"
        assert sess.summary == ""
        assert sess.metadata == {"department": "CSE"}
        assert isinstance(sess.created_at, datetime)
        assert isinstance(sess.last_active_at, datetime)

        # Retrieve idempotently
        sess2 = store.get_or_create_session(
            session_id="sess-001",
            ip_hash="hash-123",
        )
        assert sess2.session_id == sess.session_id
        assert sess2.user_type == "student"
        assert sess2.metadata == {"department": "CSE"}
        assert sess2.created_at == sess.created_at


def test_append_message_and_get_session_history() -> None:
    """Verify storing messages with citations, diagnostics, and chronological retrieval."""
    with SQLiteSessionStore(":memory:") as store:
        store.get_or_create_session(session_id="sess-002", ip_hash="ip-abc")

        now = datetime.now(UTC)
        msg1 = MessageRecord(
            message_id="msg-1",
            session_id="sess-002",
            role="user",
            content="What are the admission requirements?",
            tokens=8,
            created_at=now,
        )
        msg2 = MessageRecord(
            message_id="msg-2",
            session_id="sess-002",
            role="assistant",
            content="Admissions require CUET-PG scores.",
            tokens=12,
            quoted_citations=[
                {
                    "doc_id": "doc-adm-2024",
                    "chunk_id": "c-001",
                    "title": "Admission Prospectus 2024",
                    "page": 5,
                    "quote": "Eligible candidates must have appeared in CUET-PG.",
                }
            ],
            diagnostic_code=None,
            latency_ms=145,
            created_at=now + timedelta(seconds=1),
        )

        store.append_message(msg1)
        store.append_message(msg2)

        history = store.get_session_history("sess-002")
        assert len(history) == 2
        assert history[0].message_id == "msg-1"
        assert history[0].role == "user"
        assert history[0].content == "What are the admission requirements?"
        assert history[0].tokens == 8

        assert history[1].message_id == "msg-2"
        assert history[1].role == "assistant"
        assert len(history[1].quoted_citations) == 1
        assert history[1].quoted_citations[0]["doc_id"] == "doc-adm-2024"
        assert history[1].latency_ms == 145


def test_context_window_sliding_memory() -> None:
    """Verify sliding window context retrieval of last 4 turns (8 messages) and rolling summary."""
    with SQLiteSessionStore(":memory:") as store:
        session_id = "sess-003"
        store.get_or_create_session(session_id=session_id, ip_hash="ip-xyz")

        base_time = datetime.now(UTC)
        # Add 6 turns (12 messages)
        for i in range(12):
            role = "user" if i % 2 == 0 else "assistant"
            msg = MessageRecord(
                message_id=f"m-{i:02d}",
                session_id=session_id,
                role=role,
                content=f"Message {i} content",
                tokens=10,
                created_at=base_time + timedelta(seconds=i),
            )
            store.append_message(msg)

        store.update_session_summary(
            session_id,
            "User asked about previous academic sessions.",
        )

        # Window of 4 turns = 8 messages
        summary, recent = store.get_context_window(session_id, window_turns=4)
        assert summary == "User asked about previous academic sessions."
        assert len(recent) == 8

        # Must be messages 4 through 11 in chronological ascending order
        expected_ids = [f"m-{i:02d}" for i in range(4, 12)]
        actual_ids = [m.message_id for m in recent]
        assert actual_ids == expected_ids

        # get_recent_turns should return the same messages
        recent_turns = store.get_recent_turns(session_id, limit_turns=4)
        assert [m.message_id for m in recent_turns] == expected_ids


def test_save_summary_and_get_latest_summary() -> None:
    """Verify structured summary storage in session_summaries table and latest summary retrieval."""
    with SQLiteSessionStore(":memory:") as store:
        session_id = "sess-004"
        store.get_or_create_session(session_id=session_id, ip_hash="ip-sum")

        m1 = MessageRecord(
            message_id="m-start",
            session_id=session_id,
            role="user",
            content="Start",
        )
        m2 = MessageRecord(
            message_id="m-end",
            session_id=session_id,
            role="assistant",
            content="End",
        )
        store.append_message(m1)
        store.append_message(m2)

        store.save_summary(
            session_id=session_id,
            start_message_id="m-start",
            end_message_id="m-end",
            turns_covered=1,
            summary_text="Rolling summary of turn 1.",
        )

        latest_summary = store.get_latest_summary(session_id)
        assert latest_summary == "Rolling summary of turn 1."


def test_delete_session_cascades() -> None:
    """Verify session deletion cascades to messages and summaries."""
    with SQLiteSessionStore(":memory:") as store:
        session_id = "sess-005"
        store.get_or_create_session(session_id=session_id, ip_hash="ip-del")

        store.append_message(
            MessageRecord(
                message_id="m-del-1",
                session_id=session_id,
                role="user",
                content="Hello to be deleted",
            )
        )

        # Deleting existing session returns True
        assert store.delete_session(session_id) is True

        # Messages must be cascade-deleted
        history = store.get_session_history(session_id)
        assert len(history) == 0

        # Second deletion returns False (not found)
        assert store.delete_session(session_id) is False


def test_rate_limiting() -> None:
    """Verify sliding-window rate limit checks and increments."""
    with SQLiteSessionStore(":memory:") as store:
        ip = "salt-hashed-ip-1"

        allowed, count, remaining = store.check_and_increment_rate_limit(
            ip_hash=ip,
            max_requests=3,
            window_seconds=3600,
        )
        assert allowed is True
        assert count == 1
        assert remaining == 2

        allowed, count, remaining = store.check_and_increment_rate_limit(
            ip_hash=ip,
            max_requests=3,
            window_seconds=3600,
        )
        assert allowed is True
        assert count == 2
        assert remaining == 1

        allowed, count, remaining = store.check_and_increment_rate_limit(
            ip_hash=ip,
            max_requests=3,
            window_seconds=3600,
        )
        assert allowed is True
        assert count == 3
        assert remaining == 0

        # 4th request exceeds max_requests of 3
        allowed, count, remaining = store.check_and_increment_rate_limit(
            ip_hash=ip,
            max_requests=3,
            window_seconds=3600,
        )
        assert allowed is False
        assert count == 4
        assert remaining == 0


def test_error_handling_and_edge_cases() -> None:
    """Verify error conditions on non-existent sessions and invalid windows."""
    with SQLiteSessionStore(":memory:") as store:
        with pytest.raises(KeyError):
            store.update_session_summary("non-existent-session", "Some summary")

        summary, msgs = store.get_context_window("non-existent-session", window_turns=4)
        assert summary == ""
        assert msgs == []

        # Zero or negative window turns
        store.get_or_create_session("sess-zero", ip_hash="ip-zero")
        summary_zero, msgs_zero = store.get_context_window("sess-zero", window_turns=0)
        assert msgs_zero == []


def test_concurrent_writes_wal(tmp_path: Path) -> None:
    """Verify SQLite WAL mode handles multi-threaded concurrent writes without locking errors."""
    db_file = tmp_path / "concurrent_sessions.db"
    store = SQLiteSessionStore(db_file)

    session_id = "concurrent-sess"
    store.get_or_create_session(session_id=session_id, ip_hash="ip-concurrent")

    num_threads = 10
    messages_per_thread = 20

    def worker(worker_id: int) -> int:
        written = 0
        for i in range(messages_per_thread):
            msg = MessageRecord(
                message_id=f"msg-w{worker_id}-{i}",
                session_id=session_id,
                role="user" if i % 2 == 0 else "assistant",
                content=f"Worker {worker_id} message {i}",
                tokens=5,
            )
            store.append_message(msg)
            store.check_and_increment_rate_limit(
                ip_hash=f"ip-worker-{worker_id}",
                max_requests=1000,
                window_seconds=3600,
            )
            written += 1
        return written

    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker, i) for i in range(num_threads)]
        results = [f.result() for f in futures]

    assert sum(results) == num_threads * messages_per_thread

    history = store.get_session_history(session_id)
    assert len(history) == num_threads * messages_per_thread

    store.close()
