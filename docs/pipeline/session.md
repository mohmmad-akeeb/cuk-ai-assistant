# Session Memory

> **SQLite WAL conversation store with rolling context window and summary management.**
>
> Related: [Pipeline Overview](./overview.md)

---

## 1. Purpose

The `SQLiteSessionStore` persists every user and assistant message, maintains a rolling context window for LLM prompts, and supports conversation summaries for long-running sessions. It runs in WAL (Write-Ahead Logging) mode for high concurrency.

---

## 2. Database Schema

```mermaid
erDiagram
    sessions ||--o{ messages : "has many"
    sessions ||--o{ session_summaries : "has many"
    messages ||--|| session_summaries : "start/end references"

    sessions {
        TEXT session_id PK
        TEXT user_type "guest|student|faculty|staff"
        TEXT auth_subject
        TEXT ip_hash
        TEXT user_agent
        TEXT status "active"
        TEXT summary "rolling 2-sentence summary"
        TIMESTAMP created_at
        TIMESTAMP last_active_at
        TEXT metadata "JSON"
    }

    messages {
        TEXT message_id PK
        TEXT session_id FK
        TEXT role "user|assistant|system"
        TEXT content
        INTEGER tokens
        TEXT quoted_citations "JSON"
        TEXT diagnostic_code
        INTEGER latency_ms
        TIMESTAMP created_at
    }

    session_summaries {
        TEXT summary_id PK
        TEXT session_id FK
        TEXT start_message_id FK
        TEXT end_message_id FK
        INTEGER turns_covered
        TEXT summary_text
        TIMESTAMP created_at
    }
```

### SQLite pragmas

| Pragma | Value | Purpose |
|--------|-------|---------|
| `journal_mode` | `WAL` | Write-Ahead Logging for concurrent reads + writes |
| `busy_timeout` | `5000ms` | Wait up to 5s on lock contention |
| `synchronous` | `NORMAL` | Balance durability and speed (safe with WAL) |
| `foreign_keys` | `ON` | Enforce cascade delete on session removal |

### Indexes

| Index | Table | Columns | Purpose |
|-------|-------|---------|---------|
| `idx_sessions_last_active` | sessions | `last_active_at DESC` | Recent session lookup |
| `idx_sessions_ip_hash` | sessions | `ip_hash, created_at DESC` | IP-based rate limit queries |
| `idx_messages_session_time` | messages | `session_id, created_at ASC` | Chronological message retrieval |
| `idx_summaries_session_recent` | session_summaries | `session_id, created_at DESC` | Latest summary lookup |

---

## 3. Session Lifecycle

```mermaid
flowchart TD
    START["New user message"]
    CREATE["get_or_create_session()"]
    CHECK{"Session exists?"}
    FETCH["Fetch existing session record<br/>Return SessionRecord"]
    INSERT["INSERT INTO sessions<br/>session_id, user_type, ip_hash<br/>ON CONFLICT DO NOTHING<br/>Return new SessionRecord"]

    USER_MSG["append_message()<br/>role='user', content, tokens<br/>INSERT INTO messages<br/>UPDATE sessions last_active_at"]

    RECENT["get_recent_turns(limit_turns=4)<br/>→ get_context_window()"]
    CONTEXT_WINDOW["Fetch last 8 messages<br/>(4 turns × 2 messages)<br/>ORDER BY created_at DESC LIMIT 8<br/>Reverse to chronological"]
    SUMMARY["Fetch rolling summary<br/>FROM sessions.summary<br/>or latest session_summaries row"]
    RETURN["Return (summary, messages)<br/>→ Used as LLM chat_history"]

    PIPELINE["... RAG pipeline executes ..."]

    ASST_MSG["append_message()<br/>role='assistant', content, tokens,<br/>quoted_citations, diagnostic_code, latency_ms<br/>INSERT INTO messages<br/>UPDATE sessions last_active_at"]

    START --> CREATE --> CHECK
    CHECK -->|"Yes"| FETCH
    CHECK -->|"No"| INSERT
    FETCH --> USER_MSG
    INSERT --> USER_MSG
    USER_MSG --> RECENT
    RECENT --> CONTEXT_WINDOW --> SUMMARY --> RETURN
    RETURN --> PIPELINE
    PIPELINE --> ASST_MSG

    style RETURN fill:#1a2a3a,color:#fff
    style PIPELINE fill:#1a3a1a,color:#fff
```

---

## 4. Context Window

The orchestrator calls `get_recent_turns(session_id, limit_turns=4)` to build the LLM's chat history:

```mermaid
flowchart LR
    DB["SQLite messages table"]
    QUERY["SELECT * FROM messages<br/>WHERE session_id = ?<br/>ORDER BY created_at DESC<br/>LIMIT 8"]
    REVERSE["Reverse to chronological order"]
    FILTER["Filter: only role IN ('user', 'assistant')"]
    FORMAT["Format as chat_history:<br/>[{role, content}, ...]"]
    LLM["Passed to LLM as chat_history<br/>in generate_answer()"]

    DB --> QUERY --> REVERSE --> FILTER --> FORMAT --> LLM

    style LLM fill:#1a2a3a,color:#fff
```

### Example chat history

```python
# After user selects batch_year chip:
[
    {"role": "user", "content": "What is the syllabus of DBMS?"},
    {"role": "assistant", "content": "Which admission batch or regulation cohort year?"},
    {"role": "user", "content": "2024"},
    {"role": "assistant", "content": "Which semester syllabus do you need?"},
]
```

The LLM receives this context along with the retrieved chunks, allowing it to understand multi-turn conversations where slots are filled incrementally.

---

## 5. Thread-Local Connections

Each thread gets its own SQLite connection (via `threading.local`):

```mermaid
flowchart TD
    THREAD1["Thread 1 (API request A)"]
    THREAD2["Thread 2 (API request B)"]
    LOCAL1["threading.local().conn"]
    LOCAL2["threading.local().conn"]
    CONN1["sqlite3.Connection<br/>WAL mode + pragmas"]
    CONN2["sqlite3.Connection<br/>WAL mode + pragmas"]
    DB["sessions.db<br/>(shared file)"]

    THREAD1 --> LOCAL1 --> CONN1 --> DB
    THREAD2 --> LOCAL2 --> CONN2 --> DB

    style DB fill:#1a3a1a,color:#fff
```

This avoids SQLite's threading limitations while allowing concurrent reads (WAL mode) and serialized writes.

---

## 6. Summary Management

Long conversations use a rolling summary to compress older turns:

```mermaid
flowchart LR
    TURNS["Turns 1-N (older)"]
    SUMMARY["save_summary()<br/>2-sentence rolling summary<br/>Stored in sessions.summary<br/>+ session_summaries table"]
    WINDOW["Turns N+1 to N+4 (recent)"]
    LLM["LLM receives:<br/>summary + recent 4 turns"]

    TURNS --> SUMMARY
    SUMMARY --> LLM
    WINDOW --> LLM

    style SUMMARY fill:#3a2a1a,color:#fff
    style LLM fill:#1a2a3a,color:#fff
```

The `get_context_window()` method returns a tuple of `(summary_string, list[MessageRecord])`. The summary compresses turns outside the 4-turn window, while recent turns are passed verbatim.

---

## 7. MessageRecord Fields

```python
class MessageRecord(BaseModel):
    message_id: str                    # Unique message ID (msg_XXXXXXXX)
    session_id: str                     # Session this message belongs to
    role: str                           # "user" | "assistant" | "system"
    content: str                        # Message text
    tokens: int                          # Token count (word count approximation)
    quoted_citations: list[dict]         # Citation cards (assistant only)
    diagnostic_code: str | None         # Failure diagnostic (if any)
    latency_ms: int | None              # Total turn latency (assistant only)
    created_at: datetime                # UTC timestamp
```

### What gets persisted per turn

| Role | Persisted fields |
|------|-----------------|
| user | `message_id`, `session_id`, `role="user"`, `content`, `tokens` |
| assistant | All fields including `quoted_citations`, `diagnostic_code`, `latency_ms` |

---

## 8. Key Files

| File | Responsibility |
|------|---------------|
| `agent/session_store.py` | `SQLiteSessionStore` — WAL mode, thread-local connections |
| `core/protocols/session.py` | `SessionStoreProtocol`, `MessageRecord`, `SessionRecord` |
| `core/factory.py` | `create_session_store()` — instantiates with env config |
