"""CLI entry-point for the CUK raw collector (cuk-crawl).

Pure Raw Collector (Extract & Load):
  - Extracts pristine HTML, API JSON, and PDF binaries into data/raw/.
  - Produces data/raw/nodes.jsonl and data/raw/manifest.jsonl.
  - Zero markdown conversion, zero regex stripping, and zero parsing.
"""

from __future__ import annotations

import asyncio
import logging

import typer
from rich.console import Console

from cuk_assistant.core.config import load_settings
from cuk_assistant.core.logging_setup import setup_logging
from cuk_assistant.ingestion.collector.runner import run as _run

app = typer.Typer(
    name="cuk-crawl",
    help="CUK raw collector CLI — extracts pristine web/API assets and writes manifest.jsonl.",
    no_args_is_help=False,
)
console = Console()
logger = logging.getLogger(__name__)


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    force: bool = typer.Option(False, "--force", help="Re-crawl even if raw assets exist."),
    skip_pdf: bool = typer.Option(
        False,
        "--skip-pdf",
        help="Bypass PDF HEAD/GET requests entirely during HTML/API recrawls.",
    ),
    nodes_only: bool = typer.Option(
        False,
        "--nodes-only",
        help="Build the node table (data/raw/nodes.jsonl) without downloading assets.",
    ),
) -> None:
    """Execute raw CUK extraction and lake population."""
    if ctx.invoked_subcommand is not None:
        return

    settings = load_settings()
    setup_logging(log_file=settings.log_file, level=settings.log_level)

    if nodes_only:
        from cuk_assistant.core.http_cache import CachedClient
        from cuk_assistant.ingestion.collector.route_walker import (
            build_node_table,
            fetch_all_nodes,
            nodes_to_jsonl,
        )

        async def _build():
            async with CachedClient.from_settings(settings) as client:
                nodes = await build_node_table(settings, client)
                await fetch_all_nodes(nodes, client, settings)
            out_path = settings.raw_dir / "nodes.jsonl"
            nodes_to_jsonl(nodes, out_path)
            console.print(f"Nodes table written to {out_path}")

        asyncio.run(_build())
        return

    asyncio.run(_run(settings, force=force, skip_pdf=skip_pdf))


@app.command("crawl")
def crawl_command(
    force: bool = typer.Option(False, "--force", help="Re-crawl even if raw assets exist."),
    skip_pdf: bool = typer.Option(
        False,
        "--skip-pdf",
        help="Bypass PDF HEAD/GET requests entirely during HTML/API recrawls.",
    ),
) -> None:
    """Full raw site crawl — extract pristine HTML, API JSON, and PDF assets."""
    settings = load_settings()
    setup_logging(log_file=settings.log_file, level=settings.log_level)
    asyncio.run(_run(settings, force=force, skip_pdf=skip_pdf))


@app.command("build-nodes")
def build_nodes_command() -> None:
    """Build the node table (data/raw/nodes.jsonl) only."""
    settings = load_settings()
    setup_logging(log_file=settings.log_file, level=settings.log_level)

    from cuk_assistant.core.http_cache import CachedClient
    from cuk_assistant.ingestion.collector.route_walker import (
        build_node_table,
        fetch_all_nodes,
        nodes_to_jsonl,
    )

    async def _build():
        async with CachedClient.from_settings(settings) as client:
            nodes = await build_node_table(settings, client)
            await fetch_all_nodes(nodes, client, settings)
        out_path = settings.raw_dir / "nodes.jsonl"
        nodes_to_jsonl(nodes, out_path)
        console.print(f"Nodes table written to {out_path}")

    asyncio.run(_build())


if __name__ == "__main__":
    app()
