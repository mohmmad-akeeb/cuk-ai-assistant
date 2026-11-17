"""CLI entry-point for the document ingestion and hierarchical chunking pipeline (cuk-ingest).

Transforms canonical Document records in data/processed/documents.jsonl into
hierarchical ChunkRecord models in data/processed/chunks.jsonl.
"""

from __future__ import annotations

import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)

from cuk_assistant.core.config import load_settings
from cuk_assistant.core.logging_setup import setup_logging
from cuk_assistant.ingestion.runner import IngestionPipelineRunner

app = typer.Typer(
    name="cuk-ingest",
    help="Ingestion pipeline — chunks canonical documents into hierarchical parent-child ChunkRecords.",
    no_args_is_help=False,
)
console = Console()
logger = logging.getLogger(__name__)


@app.callback(invoke_without_command=True)
def ingest_main(
    ctx: typer.Context,
    input_file: Path = typer.Option(
        Path("data/processed/documents.jsonl"),
        "--input",
        "-i",
        help="Path to canonical documents.jsonl",
    ),
    output_file: Path = typer.Option(
        Path("data/processed/chunks.jsonl"),
        "--output",
        "-o",
        help="Path to output chunks.jsonl",
    ),
    workers: int = typer.Option(
        1,
        "--workers",
        "-w",
        help="Worker concurrency for chunking execution.",
    ),
) -> None:
    """Run hierarchical chunking and fact extraction on documents.jsonl."""
    if ctx.invoked_subcommand is not None:
        return

    settings = load_settings()
    setup_logging(log_file=settings.log_file, level=settings.log_level)

    input_path = input_file if input_file.is_absolute() else settings.project_root / input_file
    output_path = output_file if output_file.is_absolute() else settings.project_root / output_file

    console.print("[bold cyan]Starting document chunking & ingestion pipeline...[/bold cyan]")
    console.print(f"  Input:   {input_path}")
    console.print(f"  Output:  {output_path}")
    console.print(f"  Workers: {workers}")

    runner = IngestionPipelineRunner()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[green]Processing documents...", total=None)

        def on_progress(current: int, total: int) -> None:
            if progress.tasks[task].total is None and total > 0:
                progress.update(task, total=total)
            progress.update(task, completed=current)

        stats = runner.run(
            documents_path=input_path,
            output_chunks_path=output_path,
            max_workers=workers,
            progress_callback=on_progress,
        )

    console.print(
        f"\n[bold green]Ingestion completed successfully![/bold green]\n"
        f"  Total Documents:  {stats.total_documents}\n"
        f"  Total Chunks:     {stats.total_chunks}\n"
        f"  Parent Sections:  {stats.parent_sections}\n"
        f"  Table Chunks:     {stats.table_chunks}\n"
        f"  Execution Time:   {stats.duration_seconds:.2f}s\n"
        f"  Errors:           {stats.errors}"
    )


if __name__ == "__main__":
    app()
