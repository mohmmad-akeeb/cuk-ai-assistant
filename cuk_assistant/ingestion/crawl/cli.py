"""CLI entry-point for the CUK scraper.

Commands:
  crawl        — Full site crawl (school tree + nav + faculty + global lists + PDFs).
                 Writes data/processed/nodes.jsonl, data/processed/documents.jsonl,
                 reports/scrape_summary.md, reports/coverage.md.
  build-nodes  — Build the node table only (data/processed/nodes.jsonl).
"""

from __future__ import annotations

import logging

import typer
from rich.console import Console

app = typer.Typer(
    name="cuk-explore",
    help="CUK website scraper — produces documents.jsonl for the RAG pipeline.",
    no_args_is_help=True,
)
console = Console()
logger = logging.getLogger(__name__)


def _bootstrap():
    from cuk_assistant.core.config import load_settings
    from cuk_assistant.core.logging_setup import setup_logging

    settings = load_settings()
    setup_logging(log_file=settings.log_file, level=settings.log_level)
    return settings


@app.command("crawl")
def crawl(
    force: bool = typer.Option(False, "--force", help="Re-crawl even if output exists."),
) -> None:
    """Full site crawl — school tree, nav tree, faculty, global lists, PDFs.

    Outputs:
      data/processed/nodes.jsonl       — every page on the site with status
      data/processed/documents.jsonl   — all extracted text with rich metadata
      reports/scrape_summary.md        — counts by content type and school
      reports/coverage.md              — node counts, unmapped routes, failures
    """
    settings = _bootstrap()
    import asyncio

    from cuk_assistant.ingestion.crawl.runner import run as _run

    asyncio.run(_run(settings, force=force))


@app.command("build-nodes")
def build_nodes(
    force: bool = typer.Option(False, "--force", help="Rebuild even if output exists."),
) -> None:
    """Build the node table (data/processed/nodes.jsonl) without extracting content.

    Useful for inspecting site structure before committing to a full scrape.
    """
    settings = _bootstrap()
    import asyncio

    from cuk_assistant.core.http_cache import CachedClient
    from cuk_assistant.ingestion.crawl.node_crawler import (
        build_node_table,
        fetch_all_nodes,
        nodes_to_jsonl,
    )

    nodes_path = settings.processed_dir / "nodes.jsonl"
    if nodes_path.exists() and not force:
        console.print(
            f"[green]nodes: already exists at {nodes_path}. Pass --force to rebuild.[/green]"
        )
        return

    async def _run() -> None:
        async with CachedClient.from_settings(settings) as client:
            nodes = await build_node_table(settings, client)
            await fetch_all_nodes(nodes, client, settings)
        nodes_to_jsonl(nodes, nodes_path)
        console.print(f"[green]✓ {len(nodes)} nodes written to {nodes_path}[/green]")

    asyncio.run(_run())


@app.command("save-pdfs")
def save_pdfs() -> None:
    """Save all PDFs from the HTTP cache to data/raw/pdf/.

    Scans data/cache/ for cached responses that start with %PDF
    and writes them to data/raw/pdf/<filename>.  No network calls.
    Useful after a crawl that didn't save raw PDFs.
    """
    import json as _json

    settings = _bootstrap()
    cache_dir = settings.cache_dir
    raw_dir = settings.project_root / "data" / "raw" / "pdf"
    raw_dir.mkdir(parents=True, exist_ok=True)

    saved = 0
    skipped = 0

    # Walk cache directory for .body files
    for body_path in cache_dir.rglob("*.body"):
        meta_path = body_path.with_suffix(".meta.json")
        if not meta_path.exists():
            continue
        try:
            body = body_path.read_bytes()
            if not body.startswith(b"%PDF"):
                continue
            meta = _json.loads(meta_path.read_text())
            url = meta.get("url", "")
            # Derive filename from URL
            fname = url.split("/")[-1].split("?")[0]
            # URL-decode
            from urllib.parse import unquote

            fname = unquote(fname)
            if not fname or fname == "":
                fname = body_path.stem + ".pdf"
            out_path = raw_dir / fname
            if out_path.exists():
                skipped += 1
                continue
            out_path.write_bytes(body)
            saved += 1
        except Exception:
            continue

    console.print(f"[green]✓ Saved {saved} PDFs to {raw_dir}[/green]")
    if skipped:
        console.print(f"  ({skipped} already existed, skipped)")


if __name__ == "__main__":
    app()
