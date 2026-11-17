"""scripts/interactive_chat.py

Interactive terminal chat interface for Central University of Kashmir (CUK) RAG Assistant.
Streams responses, manages multi-turn memory, prompts for missing academic slots,
and displays verified citations and PII scrubbing.
"""

from __future__ import annotations

import asyncio
import logging
import sys

import logfire
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cuk_assistant.core.factory import create_rag_orchestrator

logfire.configure()
logfire.instrument_httpx()
logfire.instrument_pydantic()

# Suppress verbose HTTP and pipeline trace logging in interactive console
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("cuk_assistant").setLevel(logging.ERROR)

console = Console()


async def run_interactive_session() -> None:
    """Run an interactive conversational loop with the RAG orchestrator."""
    console.print(
        Panel.fit(
            "[bold cyan]Central University of Kashmir (CUK)[/bold cyan]\n"
            "[green]Official AI Academic & Campus Assistant[/green]\n"
            "[dim]Hybrid LanceDB (Vector + BM25) · FlashRank Reranker · Guardrails Active[/dim]\n\n"
            "Type your questions below. Type [bold red]'exit'[/bold red] or [bold red]'quit'[/bold red] to stop.",
            title="[bold yellow]CUK RAG Assistant[/bold yellow]",
            border_style="cyan",
        )
    )

    console.print("\n[dim]Initializing RAG pipeline and connecting to LanceDB...[/dim]")
    orchestrator = create_rag_orchestrator()
    session_id = None
    active_slots: dict[str, str] = {}
    pending_slot: str | None = None
    pending_query: str | None = None
    pending_options: list[dict] = []

    console.print("[bold green]System Ready![/bold green]\n")

    while True:
        try:
            raw_input = console.input("[bold cyan]You > [/bold cyan]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Exiting CUK Assistant. Goodbye![/yellow]")
            break

        if not raw_input:
            continue
        if raw_input.lower() in ("exit", "quit", "q"):
            console.print("[yellow]Exiting CUK Assistant. Goodbye![/yellow]")
            break

        # Check if user is answering a pending slot prompt
        query_to_send = raw_input
        if pending_slot and pending_options:
            resolved_value = raw_input
            # If user entered an option index like 1, 2, 3
            if raw_input.isdigit():
                idx = int(raw_input) - 1
                if 0 <= idx < len(pending_options):
                    opt = pending_options[idx]
                    resolved_value = opt.get("value") if isinstance(opt, dict) else str(opt)

            active_slots[pending_slot] = resolved_value
            if pending_query:
                query_to_send = f"{pending_query} for {resolved_value}"

            pending_slot = None
            pending_options = []

        console.print("[dim]Thinking & retrieving verified sources...[/dim]")

        # Stream response from orchestrator
        full_text = ""
        citations: list[dict] = []
        quick_replies = None

        try:
            async for event in orchestrator.stream_turn(
                query=query_to_send,
                session_id=session_id,
                slots=active_slots or None,
            ):
                event_type = event.get("type")
                if event_type == "token":
                    tok = event.get("token", "")
                    sys.stdout.write(tok)
                    sys.stdout.flush()
                    full_text += tok
                elif event_type == "slot_prompt":
                    quick_replies = event
                elif event_type == "done":
                    session_id = event.get("session_id", session_id)
                    citations = event.get("citations", [])

            sys.stdout.write("\n\n")
            sys.stdout.flush()

            # If slot chips are presented, prompt the user
            if quick_replies:
                pending_slot = quick_replies.get("target_slot", "slot")
                pending_options = quick_replies.get("options", [])
                if not pending_query:
                    pending_query = raw_input
                if pending_options:
                    chip_table = Table(
                        title=f"Recommended Options for {pending_slot.replace('_', ' ').title()}",
                        show_header=True,
                        header_style="bold magenta",
                    )
                    chip_table.add_column("#", style="dim", width=4)
                    chip_table.add_column("Option Value", style="cyan")

                    for idx, opt in enumerate(pending_options, 1):
                        val = opt.get("value") if isinstance(opt, dict) else str(opt)
                        chip_table.add_row(str(idx), str(val))
                    console.print(chip_table)
                    console.print("[dim]Type your choice number or value below...[/dim]\n")
            else:
                pending_query = None

            # Render citation cards if citations exist
            if citations:
                citation_table = Table(
                    title="Verified University Citations",
                    show_header=True,
                    header_style="bold green",
                    border_style="dim",
                )
                citation_table.add_column("#", style="dim", width=4)
                citation_table.add_column("Document Title", style="bold white")
                citation_table.add_column("Official Source Link", style="blue")

                for idx, c in enumerate(citations[:5], 1):
                    title = c.get("title") or "University Document"
                    url = c.get("source_url") or c.get("page_url") or "https://www.cukashmir.ac.in"
                    citation_table.add_row(str(idx), title, url)

                console.print(citation_table)
                console.print("")

        except Exception as exc:
            console.print(f"[bold red]Turn Error:[/bold red] {exc}\n")


if __name__ == "__main__":
    asyncio.run(run_interactive_session())
