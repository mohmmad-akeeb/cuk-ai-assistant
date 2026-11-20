# Chainlit UI

> **The web chat interface.** Chainlit handles the chat lifecycle: starter prompts, slot-filling chips, streaming responses, citation cards, and feedback buttons.
>
> Related: [API](./api.md) · [Pipeline Overview](../pipeline/overview.md) · [Routing + Slots](../pipeline/routing-slots.md)

---

## 1. Purpose

The Chainlit UI (`ui/app.py`) is the primary user-facing interface. It builds a `RAGOrchestrator` singleton, handles chat lifecycle events, renders slot-filling chips, streams tokens, displays side-panel citation cards, and records user feedback.

---

## 2. Interaction Flow

```mermaid
flowchart TD
    START["User opens chat page"]
    ON_START["on_chat_start()<br/>Initialize session_id<br/>Set active_slots = {}"]
    STARTERS["Display starter chips:<br/>• B.Tech CSE Syllabus<br/>• Admissions & CUET<br/>• CBCS Ordinances<br/>• Exam Date Sheets"]

    USER_MSG["User types or clicks starter"]
    ON_MSG["on_message()<br/>Set last_query = query_text<br/>Get active_slots from session"]
    PROCESS["process_query(query, updated_slots)"]
    CREATE_MSG["Create empty cl.Message<br/>await msg.send()"]

    STREAM["async for event in orchestrator.stream_turn()"]

    TOKEN["event.type == 'token'<br/>await msg.stream_token(token)"]
    SLOT["event.type == 'slot_prompt'<br/>Build cl.Action chips<br/>from event.options"]
    CIT["event.type == 'citation_card'<br/>Build cl.Text side-panel card<br/>with title, source, page, snippet"]
    ERR["event.type == 'error'<br/>Stream error message"]
    DONE["event.type == 'done'<br/>Set trace_id"]

    FINALLY["finally:<br/>Attach citation elements to msg<br/>Attach slot actions OR feedback buttons"]
    UPDATE["await msg.update()"]

    CLICK_SLOT["User clicks slot chip"]
    ON_SLOT["on_slot_selected()<br/>Update active_slots[target_slot] = value<br/>Echo 'Selected: {label}'<br/>Get last_query from session<br/>Call process_query(last_query, active_slots)"]

    CLICK_FB["User clicks 👍 or 👎"]
    ON_FB["on_feedback_upvote/downvote()<br/>Record to telemetry sink<br/>Display thank you message"]

    START --> ON_START --> STARTERS
    STARTERS --> USER_MSG
    USER_MSG --> ON_MSG --> PROCESS --> CREATE_MSG --> STREAM
    STREAM --> TOKEN
    STREAM --> SLOT
    STREAM --> CIT
    STREAM --> ERR
    STREAM --> DONE
    TOKEN --> STREAM
    CIT --> STREAM
    DONE --> FINALLY
    SLOT --> FINALLY
    FINALLY --> UPDATE

    UPDATE -.->|"If slot chips"| CLICK_SLOT
    UPDATE -.->|"If no slots, no error"| CLICK_FB
    CLICK_SLOT --> ON_SLOT --> PROCESS
    CLICK_FB --> ON_FB

    style STARTERS fill:#1a2a3a,color:#fff
    style SLOT fill:#3a2a1a,color:#fff
    style CIT fill:#1a3a1a,color:#fff
    style CLICK_SLOT fill:#3a2a1a,color:#fff
```

---

## 3. Event Handling Lifecycle

```mermaid
flowchart TD
    subgraph LIFECYCLE["Chainlit event callbacks"]
        CS["on_chat_start<br/>Session init + starters"]
        MSG["on_message<br/>User typed message"]
        SP["on_starter_prompt (action)<br/>User clicked starter"]
        FS["on_slot_selected (action)<br/>User clicked slot chip"]
        UP["on_feedback_upvote (action)<br/>User clicked 👍"]
        DOWN["on_feedback_downvote (action)<br/>User clicked 👎"]
    end

    subgraph PROCESS["process_query()"]
        ORC["orchestrator.stream_turn()"]
        ITER["Iterate events"]
        RENDER["Render tokens, chips, cards"]
        PERSIST["Persist to session"]
    end

    CS -->|"First visit"| STARTERS["Show starter chips"]
    MSG --> ORC
    SP -->|"Auto-send"| ORC
    FS -->|"Update slots + re-send"| ORC
    ORC --> ITER --> RENDER --> PERSIST

    UP --> FB_SINK["telemetry_sink.record_feedback(score=+1)"]
    DOWN --> FB_SINK2["telemetry_sink.record_feedback(score=-1)"]

    style LIFECYCLE fill:#3a2a1a,color:#fff
    style PROCESS fill:#1a2a3a,color:#fff
```

---

## 4. Slot-Filling Chip Flow

```mermaid
flowchart TD
    EVENT["slot_prompt event from orchestrator<br/>{target_slot, prompt, options}"]
    PROMPT["Stream prompt text to msg<br/>'Which admission batch...'"]
    BUILD["For each option in event.options:<br/>Create cl.Action(name='fill_slot',<br/>value=option.value,<br/>label=option.label,<br/>payload={'target_slot': target_slot})"]
    ATTACH["Attach actions to msg.actions"]
    UPDATE["await msg.update()"]
    WAIT["Wait for user to click a chip"]

    CLICK["User clicks chip (value='2024')"]
    CALLBACK["on_slot_selected(action)"]
    REMOVE["await action.remove()"]
    GET_SLOTS["Get active_slots from session<br/>{batch_year: '2024'} (was empty before)"]
    SET["active_slots[target_slot] = action.value<br/>{batch_year: '2024'}"]
    SAVE["cl.user_session.set('active_slots', active_slots)"]
    ECHO["Send echo: 'Selected: **2024**'"]
    REQUERY["Get last_query from session<br/>Call process_query(last_query, active_slots)"]

    EVENT --> PROMPT --> BUILD --> ATTACH --> UPDATE --> WAIT
    WAIT --> CLICK --> CALLBACK --> REMOVE --> GET_SLOTS --> SET --> SAVE --> ECHO --> REQUERY

    style EVENT fill:#3a2a1a,color:#fff
    style CLICK fill:#1a3a2a,color:#fff
    style REQUERY fill:#1a2a3a,color:#fff
```

### Known issue: Slot selection bug

When a user clicks a chip, `on_slot_selected` calls `process_query(query, updated_slots=active_slots)`. The `query` is retrieved from `cl.user_session.get("last_query", "")`. This should work correctly — the orchestrator receives the accumulated slots and re-evaluates the route.

However, the bug occurs when:
1. The user's first message is an academic query requiring slots
2. The orchestrator emits a `slot_prompt` event
3. The user clicks a chip
4. `process_query` is called with the original query + updated slots
5. The orchestrator's `route()` method calls `fill_slots(query, session_slots=slots)` which should merge the session slots with query-extracted slots
6. If the next slot is still missing, a new `slot_prompt` should be emitted

The flow appears correct in the code. The likely issue is either:
- `last_query` not being set in `on_slot_selected` (falls back to `action.value`)
- The orchestrator receiving `slots=None` instead of the accumulated dict
- The `FacetedSlotFiller.extract_slots()` not properly merging session slots

---

## 5. Citation Card Rendering

```mermaid
flowchart LR
    EVENT["citation_card event<br/>{citation_id, doc_id, title,<br/>source_url, page_number,<br/>section_heading, quoted_snippet,<br/>is_table, table_markdown}"]

    CHECK{"is_table?"}
    TABLE["Render as markdown table:<br/>### {title} (Page {page_num})<br/>**Source:** [{source_url}]({source_url})<br/><br/>{table_markdown}"]
    TEXT["Render as quote block:<br/>**Document:** [{title}]({source_url})<br/>**Page:** {page_num} | **Section:** {sec}<br/><br/>> '{snippet}'"]

    ELEMENT["cl.Text(name='[1] {title}... (p. {page_num})',<br/>content=card_content,<br/>display='side')"]
    COLLECT["Append to citation_elements list"]
    ATTACH["msg.elements = citation_elements<br/>(side-panel display)"]

    EVENT --> CHECK
    CHECK -->|"Yes"| TABLE
    CHECK -->|"No"| TEXT
    TABLE --> ELEMENT
    TEXT --> ELEMENT
    ELEMENT --> COLLECT --> ATTACH

    style TABLE fill:#1a3a1a,color:#fff
    style TEXT fill:#1a2a3a,color:#fff
    style ATTACH fill:#3a2a1a,color:#fff
```

Citation cards appear in the Chainlit side panel for verification. Each card shows the document title, source URL, page number, section heading, and a verbatim quoted snippet (or markdown table if the chunk is a table).

---

## 6. Feedback Buttons

After a completed turn (no slot chips, no error), the UI attaches feedback buttons:

```python
feedback_actions = [
    cl.Action(
        name="feedback_upvote",
        value=turn_trace_id,
        label="👍 Helpful",
        description="Answer is accurate and verified",
        payload={},
    ),
    cl.Action(
        name="feedback_downvote",
        value=turn_trace_id,
        label="👎 Inaccurate",
        description="Information is missing or outdated",
        payload={},
    ),
]
msg.actions = feedback_actions
```

When clicked, the callback records to the telemetry sink:

```python
sink.record_feedback(
    trace_id=action.value,  # The turn's trace_id
    score=1,  # or -1 for downvote
    feedback_category="helpful",  # or "unhelpful"
)
```

---

## 7. Singleton Orchestrator

The UI uses a module-level singleton orchestrator, initialized lazily on first use:

```python
_orchestrator: RAGOrchestrator | None = None

def get_ui_orchestrator() -> RAGOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = create_rag_orchestrator()
    return _orchestrator
```

This means all users share the same orchestrator instance (and its LanceDB connection, LLM pool, session store, etc.). This is fine for single-process deployment.

---

## 8. Key Files

| File | Responsibility |
|------|---------------|
| `ui/app.py` | Chainlit app — event handlers, process_query, run() |
| `.chainlit/config.toml` | Chainlit configuration |
| `core/factory.py` | `create_rag_orchestrator()` — builds the singleton |
