"""CLI entry-point for the offline parser pipeline (cuk-parse).

Parses data/raw/manifest.jsonl into data/processed/documents.jsonl.
Dispatches assets across BS4, PyMuPDF, and JSON parsers, applies
PII sanitization and multi-route reference aggregation, and validates
against the canonical Document schema.
"""

from __future__ import annotations

import logging
from pathlib import Path

import typer
from rich.console import Console

from cuk_assistant.core.config import load_settings
from cuk_assistant.core.logging_setup import setup_logging
from cuk_assistant.ingestion.normalization.subsystems.pipeline import parse_manifest

app = typer.Typer(
    name="cuk-parse",
    help="Offline parser — converts raw lake assets into canonical documents.jsonl.",
    no_args_is_help=False,
)
console = Console()
logger = logging.getLogger(__name__)


@app.callback(invoke_without_command=True)
def parse_main(
    ctx: typer.Context,
    manifest: Path = typer.Option(
        Path("data/raw/manifest.jsonl"),
        "--manifest",
        "-m",
        help="Path to raw manifest.jsonl",
    ),
    output: Path = typer.Option(
        Path("data/processed/documents.jsonl"),
        "--output",
        "-o",
        help="Path to output documents.jsonl",
    ),
    workers: int = typer.Option(
        None,
        "--workers",
        "-w",
        help="Number of concurrent workers for asset parsing.",
    ),
) -> None:
    """Parse raw lake assets from manifest.jsonl into documents.jsonl."""
    if ctx.invoked_subcommand is not None:
        return

    settings = load_settings()
    setup_logging(log_file=settings.log_file, level=settings.log_level)

    manifest_path = manifest if manifest.is_absolute() else settings.project_root / manifest
    output_path = output if output.is_absolute() else settings.project_root / output

    console.print("[bold]Starting offline parser pipeline...[/bold]")
    console.print(f"  Manifest: {manifest_path}")
    console.print(f"  Output:   {output_path}")

    stats = parse_manifest(
        manifest_path=manifest_path,
        output_path=output_path,
        project_root=settings.project_root,
        max_workers=workers,
    )

    console.print(
        f"[bold green]Parsed successfully![/bold green]\n"
        f"  Total Assets: {stats.total_assets}\n"
        f"  HTML Assets:  {stats.html_count}\n"
        f"  API Assets:   {stats.api_count}\n"
        f"  PDF Assets:   {stats.pdf_count}\n"
        f"  Output Docs:  {stats.output_count}\n"
        f"  Errors:       {stats.errors}"
    )


if __name__ == "__main__":
    app()
