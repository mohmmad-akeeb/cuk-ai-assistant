"""cuk_assistant/ui/app.py

Interactive Chainlit Web Application for Central University of Kashmir AI Assistant (`cuk-ui`).
Implements:
1. Real-time streaming response synthesis with markdown tables and bullet formatting.
2. Interactive Action Chips for faceted slot-filling (Departments, Batches, Semesters).
3. Side-panel inspection cards for verified verbatim citations with PDF page numbers.
4. Thumbs up/down user feedback loop recording to `/api/v1/chat/feedback`.
"""

from __future__ import annotations

import logging
import os
import sys
import uuid
from typing import Any

from cuk_assistant.core.factory import create_rag_orchestrator, create_telemetry_sink
from cuk_assistant.pipeline.orchestrator import RAGOrchestrator

logger = logging.getLogger(__name__)

# Lazy initialization of shared orchestrator and sink
_orchestrator: RAGOrchestrator | None = None
_telemetry_sink: Any | None = None


def get_ui_orchestrator() -> RAGOrchestrator:
    """Retrieve or initialize singleton orchestrator for UI session."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = create_rag_orchestrator()
    return _orchestrator


def get_ui_telemetry_sink() -> Any:
    """Retrieve or initialize singleton telemetry sink for feedback."""
    global _telemetry_sink
    if _telemetry_sink is None:
        _telemetry_sink = create_telemetry_sink()
    return _telemetry_sink


# ---------------------------------------------------------------------------
# Chainlit Application Lifecycle & Event Callbacks
# ---------------------------------------------------------------------------

try:
    import chainlit as cl

    @cl.on_chat_start
    async def on_chat_start() -> None:
        """Initialize user session state and present starter recommendation chips."""
        session_id = f"sess_{uuid.uuid4().hex}"
        cl.user_session.set("session_id", session_id)
        cl.user_session.set("active_slots", {})

        # Starter recommendation chips
        starter_actions = [
            cl.Action(
                name="starter_prompt",
                value="What is the detailed syllabus for B.Tech CSE Semester 4?",
                label="📚 B.Tech CSE Syllabus",
                description="Explore course syllabus and credits",
                payload={},
            ),
            cl.Action(
                name="starter_prompt",
                value="What are the CUET-UG eligibility criteria and intake for admissions?",
                label="📝 Admissions & CUET",
                description="Check entrance requirements and seat matrix",
                payload={},
            ),
            cl.Action(
                name="starter_prompt",
                value="What are the passing criteria and attendance rules under CUK CBCS ordinances?",
                label="⚖️ CBCS Ordinances",
                description="University academic rules and regulations",
                payload={},
            ),
            cl.Action(
                name="starter_prompt",
                value="Show me the latest exam date sheets and notifications.",
                label="📅 Exam Date Sheets",
                description="Examination schedules and alerts",
                payload={},
            ),
        ]

        welcome_text = (
            "### Welcome to Central University of Kashmir (CUK) AI Assistant! 🎓\n\n"
            "I provide factual answers grounded in official university documents. "
            "Select a common topic below or type your inquiry:"
        )
        await cl.Message(content=welcome_text, actions=starter_actions).send()

    @cl.action_callback("starter_prompt")
    async def on_starter_prompt(action: cl.Action) -> None:
        """Handle click on quick starter recommendation button."""
        await action.remove()
        user_message = cl.Message(content=str(action.value or ""))
        await user_message.send()
        await process_query(str(action.value or ""))

    @cl.action_callback("fill_slot")
    async def on_slot_selected(action: cl.Action) -> None:
        """Handle user selection of an interactive slot-filling disambiguation chip."""
        await action.remove()
        raw_slots = cl.user_session.get("active_slots")
        active_slots: dict[str, Any] = dict(raw_slots) if isinstance(raw_slots, dict) else {}

        payload = action.payload if isinstance(action.payload, dict) else {}
        target_slot = payload.get("target_slot")
        if target_slot:
            active_slots[str(target_slot)] = action.value
            cl.user_session.set("active_slots", active_slots)

        label = action.label or action.value or "Selected"
        echo_msg = f"Selected: **{label}**"
        await cl.Message(content=echo_msg).send()
        
        # Explicitly dispatch the slot update to the orchestration pipeline
        query = str(cl.user_session.get("last_query", "") or action.value or "")
        await process_query(query, updated_slots=active_slots)

    @cl.action_callback("feedback_upvote")
    async def on_feedback_upvote(action: cl.Action) -> None:
        """Record positive satisfaction feedback for a dialogue turn."""
        trace_id = str(action.value or "")
        sink = get_ui_telemetry_sink()
        if hasattr(sink, "record_feedback"):
            sink.record_feedback(trace_id=trace_id, score=1, feedback_category="helpful")
        await cl.Message(content="*Thank you for your feedback! (Marked as helpful 👍)*").send()
        await action.remove()

    @cl.action_callback("feedback_downvote")
    async def on_feedback_downvote(action: cl.Action) -> None:
        """Record negative satisfaction feedback for a dialogue turn."""
        trace_id = str(action.value or "")
        sink = get_ui_telemetry_sink()
        if hasattr(sink, "record_feedback"):
            sink.record_feedback(trace_id=trace_id, score=-1, feedback_category="unhelpful")
        await cl.Message(content="*Thank you for your feedback! (Marked as unhelpful 👎)*").send()
        await action.remove()

    @cl.on_message
    async def on_message(message: cl.Message) -> None:
        """Main chat dispatch handling incoming user queries."""
        query_text = (message.content or "").strip()
        if not query_text:
            return

        cl.user_session.set("last_query", query_text)
        raw_slots = cl.user_session.get("active_slots")
        active_slots: dict[str, Any] = dict(raw_slots) if isinstance(raw_slots, dict) else {}
        await process_query(query_text, updated_slots=active_slots)

    async def process_query(
        query: str,
        updated_slots: dict[str, Any] | None = None,
    ) -> None:
        """Execute turn through orchestrator and stream synthesized answer to UI."""
        session_id = cl.user_session.get("session_id") or f"sess_{uuid.uuid4().hex}"
        orchestrator = get_ui_orchestrator()

        msg = cl.Message(content="")
        await msg.send()

        citation_elements: list[cl.Text] = []
        slot_actions: list[cl.Action] = []
        turn_trace_id: str = uuid.uuid4().hex
        has_error: bool = False

        try:
            async for event in orchestrator.stream_turn(
                query=query,
                session_id=session_id,
                slots=updated_slots,
                trace_id=turn_trace_id,
            ):
                ev_type = event.get("type")

                if ev_type == "token":
                    token = event.get("token") or event.get("text") or ""
                    if token:
                        await msg.stream_token(token)

                elif ev_type == "slot_prompt":
                    prompt = event.get("prompt") or "Please specify missing information:"
                    await msg.stream_token(f"\n\n**{prompt}**\n\n")
                    
                    target_slot = event.get("target_slot") or "slot"
                    options = event.get("options") or []
                    for opt in options:
                        if isinstance(opt, dict):
                            val = str(opt.get("value") or "")
                            lbl = str(opt.get("label") or val)
                            desc = opt.get("description")
                        else:
                            val = str(opt)
                            lbl = str(opt)
                            desc = None

                        if not val and not lbl:
                            continue

                        slot_actions.append(
                            cl.Action(
                                name="fill_slot",
                                value=val,
                                label=lbl,
                                description=desc or f"Select {lbl}",
                                payload={"target_slot": target_slot},
                            )
                        )

                elif ev_type == "citation_card":
                    idx = len(citation_elements) + 1
                    title = event.get("title") or "Official University Document"
                    source_url = event.get("source_url") or "https://cukashmir.ac.in"
                    page_num = event.get("page_number") or 1
                    sec_heading = event.get("section_heading") or "General"
                    snippet = event.get("quoted_snippet") or ""
                    is_table = bool(event.get("is_table", False))
                    table_md = event.get("table_markdown")

                    if is_table and table_md:
                        card_content = (
                            f"### {title} (Page {page_num})\n"
                            f"**Source:** [{source_url}]({source_url})\n\n"
                            f"{table_md}"
                        )
                    else:
                        card_content = (
                            f"**Document:** [{title}]({source_url})\n\n"
                            f"**Page:** {page_num} | **Section:** {sec_heading}\n\n"
                            f'> "{snippet}"'
                        )

                    citation_elements.append(
                        cl.Text(
                            name=f"[{idx}] {title[:32]}... (p. {page_num})",
                            content=card_content,
                            display="side",
                        )
                    )

                elif ev_type == "error":
                    has_error = True
                    err_msg = (
                        event.get("message")
                        or event.get("error")
                        or event.get("error_code")
                        or "An error occurred while processing your request."
                    )
                    await msg.stream_token(f"\n\n⚠️ **Error:** {err_msg}")
                    if event.get("trace_id"):
                        turn_trace_id = str(event["trace_id"])

                elif ev_type == "done":
                    turn_trace_id = event.get("trace_id") or turn_trace_id

        except Exception as exc:
            has_error = True
            logger.exception("Error during turn streaming: %s", exc)
            await msg.stream_token(f"\n\n⚠️ **System Error:** {exc}")

        finally:
            # Attach side-panel citation cards if any were returned
            if citation_elements:
                msg.elements = citation_elements

            # Attach interactive slot chips if clarification is required
            if slot_actions:
                msg.actions = slot_actions
            elif not has_error:
                # Attach feedback buttons for verified completed turns
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

            await msg.update()

except ImportError:
    cl = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# CLI Entrypoint (`cuk-ui`)
# ---------------------------------------------------------------------------


def run() -> None:
    """Launch the Chainlit Web UI server for Central University of Kashmir Assistant."""
    if cl is None:
        print(
            "ERROR: 'chainlit' is not installed in the environment.\n"
            "Please run: uv add chainlit\n"
            "Then re-launch: cuk-ui",
            file=sys.stderr,
        )
        sys.exit(1)

    import subprocess
    from pathlib import Path

    app_path = Path(__file__).resolve()
    raw_port = os.environ.get("CHAINLIT_PORT", "").strip()
    port = raw_port if (raw_port.isdigit() and 1 <= int(raw_port) <= 65535) else "8001"
    raw_host = os.environ.get("CHAINLIT_HOST", "").strip()
    host = raw_host or "0.0.0.0"

    cmd = [
        sys.executable,
        "-m",
        "chainlit",
        "run",
        str(app_path),
        "--host",
        host,
        "--port",
        port,
    ]
    logger.info("Starting Chainlit UI: %s", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        logger.info("Chainlit server stopped by user.")
    except subprocess.CalledProcessError as exc:
        logger.error("Chainlit server exited with code %s: %s", exc.returncode, exc)
        sys.exit(exc.returncode)


if __name__ == "__main__":
    run()
