"""CLI entry-point for the vector indexing pipeline (cuk-index).

Indexes canonical hierarchical chunks from data/processed/chunks.jsonl
into embedded LanceDB hybrid store with FastEmbed dense vectors and Tantivy BM25.
"""

from __future__ import annotations

import json
import logging
import time
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
from cuk_assistant.ingestion.embedding.fastembed_adapter import FastEmbedAdapter
from cuk_assistant.retrieval.subsystems.lancedb_store import LanceDBStore
from cuk_assistant.schemas.chunks import ChunkRecord, ChunkType, ParentChunkContainer

app = typer.Typer(
    name="cuk-index",
    help="Index chunks.jsonl into embedded LanceDB with FastEmbed dense vectors and Tantivy BM25.",
    no_args_is_help=False,
)
console = Console()
logger = logging.getLogger(__name__)


def _compute_dir_size_mb(path: Path) -> float:
    """Compute total directory size in megabytes."""
    if not path.exists():
        return 0.0
    if path.is_file():
        return path.stat().st_size / (1024 * 1024)
    total_bytes = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return total_bytes / (1024 * 1024)


@app.callback(invoke_without_command=True)
def index_main(
    ctx: typer.Context,
    chunks_file: Path = typer.Option(
        Path("data/processed/chunks.jsonl"),
        "--chunks-file",
        "-i",
        help="Path to input chunks.jsonl",
    ),
    db_dir: Path = typer.Option(
        Path("data/lancedb"),
        "--db-dir",
        "-o",
        help="Directory for LanceDB embedded database",
    ),
    table_name: str = typer.Option(
        "chunks",
        "--table-name",
        "-t",
        help="Name of LanceDB table",
    ),
    batch_size: int = typer.Option(
        64,
        "--batch-size",
        "-b",
        help="Batch size for embedding generation and storage writes",
    ),
    overwrite: bool = typer.Option(
        True,
        "--overwrite/--append",
        "-f",
        help="Overwrite existing LanceDB table or append",
    ),
    threads: int | None = typer.Option(
        None,
        "--threads",
        help="Number of CPU worker threads for FastEmbed ONNX",
    ),
    stats: bool = typer.Option(
        False,
        "--stats",
        "-s",
        help="Display index health, vector counts, table size, and index status without re-indexing",
    ),
) -> None:
    """Index chunks.jsonl into LanceDB hybrid store with FastEmbed dense vectors."""
    if ctx.invoked_subcommand is not None:
        return

    settings = load_settings()
    setup_logging(log_file=settings.log_file, level=settings.log_level)

    input_path = chunks_file if chunks_file.is_absolute() else settings.project_root / chunks_file
    output_db = db_dir if db_dir.is_absolute() else settings.project_root / db_dir

    if stats:
        table_path = output_db / f"{table_name}.lance"
        if not table_path.exists():
            console.print(
                f"[bold red]Error: LanceDB table '{table_name}' not found at {output_db}[/bold red]"
            )
            raise typer.Exit(code=1)
        store = LanceDBStore(db_path=output_db, table_name=table_name)
        stats_info = store.get_stats()
        table_size_mb = _compute_dir_size_mb(output_db)

        console.print("[bold cyan]LanceDB Index Health & Diagnostics:[/bold cyan]")
        console.print(f"  Database Dir:    {output_db}")
        console.print(f"  Table Name:      {table_name}")
        console.print(f"  Total Chunks:    {stats_info['total_chunks']}")
        console.print(f"  Parent Sections: {stats_info['total_parents']}")
        console.print(f"  Storage Size:    {table_size_mb:.2f} MB")
        console.print("  Indices:")
        for idx in stats_info.get("indices", []):
            console.print(f"    - {idx['name']} ({idx['index_type']}) on columns: {idx['columns']}")
        return

    if not input_path.exists():
        console.print(f"[bold red]Error: Chunks file not found: {input_path}[/bold red]")
        raise typer.Exit(code=1)

    console.print(
        "[bold cyan]Starting hybrid vector indexing pipeline (LanceDB + FastEmbed)...[/bold cyan]"
    )
    console.print(f"  Input Chunks: {input_path}")
    console.print(f"  LanceDB Dir:  {output_db}")
    console.print(f"  Table Name:   {table_name}")
    console.print(f"  Batch Size:   {batch_size}")
    console.print(f"  Overwrite:    {overwrite}")

    # Initialize FastEmbed dense embedding adapter
    embedder = FastEmbedAdapter(threads=threads)

    # Initialize LanceDB Store
    if overwrite and output_db.exists():
        import shutil

        logger.info("Removing existing LanceDB directory for overwrite: %s", output_db)
        shutil.rmtree(output_db, ignore_errors=True)

    output_db.mkdir(parents=True, exist_ok=True)
    vector_store = LanceDBStore(db_path=output_db, table_name=table_name)

    start_time = time.monotonic()
    total_chunks = 0
    total_parent_sections = 0

    # Count total lines in chunks.jsonl
    with input_path.open("r", encoding="utf-8") as f:
        total_lines = sum(1 for line in f if line.strip())

    chunk_batch: list[ChunkRecord] = []
    parent_containers: dict[str, ParentChunkContainer] = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[green]Indexing chunks...", total=total_lines)

        with input_path.open("r", encoding="utf-8") as in_f:
            for line in in_f:
                line = line.strip()
                if not line:
                    continue

                raw_data = json.loads(line)
                chunk_rec = ChunkRecord.model_validate(raw_data)
                chunk_batch.append(chunk_rec)
                total_chunks += 1

                # If this chunk is a heading, build a parent section representation
                if chunk_rec.chunk_type == ChunkType.HEADING:
                    parent_id = chunk_rec.chunk_id.replace("::c", "::p")
                    parent_containers[parent_id] = ParentChunkContainer(
                        parent_chunk_id=parent_id,
                        doc_id=chunk_rec.doc_id,
                        heading_title=chunk_rec.text_content,
                        heading_level=1,
                        section_token_count=chunk_rec.token_count,
                        full_section_text=chunk_rec.text_content,
                        child_chunk_ids=[chunk_rec.chunk_id],
                    )
                elif chunk_rec.parent_chunk_id:
                    pid = chunk_rec.parent_chunk_id
                    alt_pid = (
                        pid.replace("::c", "::p") if "::c" in pid else pid.replace("::p", "::c")
                    )
                    target_pid = (
                        pid
                        if pid in parent_containers
                        else (alt_pid if alt_pid in parent_containers else None)
                    )
                    if target_pid:
                        p_cont = parent_containers[target_pid]
                        parent_containers[target_pid] = ParentChunkContainer(
                            parent_chunk_id=p_cont.parent_chunk_id,
                            doc_id=p_cont.doc_id,
                            heading_title=p_cont.heading_title,
                            heading_level=p_cont.heading_level,
                            section_token_count=p_cont.section_token_count + chunk_rec.token_count,
                            full_section_text=f"{p_cont.full_section_text}\n\n{chunk_rec.text_content}",
                            child_chunk_ids=[*p_cont.child_chunk_ids, chunk_rec.chunk_id],
                        )

                # Ensure root section container exists for document if chunk_index == 0
                root_parent_id = f"{chunk_rec.doc_id}::p0"
                root_chunk_id = f"{chunk_rec.doc_id}::c0"
                if (
                    chunk_rec.chunk_index == 0
                    and root_parent_id not in parent_containers
                    and root_chunk_id not in parent_containers
                ):
                    title = chunk_rec.metadata.get("title") or chunk_rec.text_content[:80]
                    parent_containers[root_parent_id] = ParentChunkContainer(
                        parent_chunk_id=root_parent_id,
                        doc_id=chunk_rec.doc_id,
                        heading_title=str(title),
                        heading_level=1,
                        section_token_count=chunk_rec.token_count,
                        full_section_text=chunk_rec.text_content,
                        child_chunk_ids=[chunk_rec.chunk_id],
                    )

                if len(chunk_batch) >= batch_size:
                    texts = [c.text_content for c in chunk_batch]
                    embeddings = embedder.embed_documents(texts, batch_size=batch_size)
                    vector_store.add_chunks(chunk_batch, embeddings, create_indices=False)
                    progress.update(task, advance=len(chunk_batch))
                    chunk_batch.clear()

            # Process remaining batch
            if chunk_batch:
                texts = [c.text_content for c in chunk_batch]
                embeddings = embedder.embed_documents(texts, batch_size=len(texts))
                vector_store.add_chunks(chunk_batch, embeddings, create_indices=False)
                progress.update(task, advance=len(chunk_batch))
                chunk_batch.clear()

    # Index parent sections if any were collected
    if parent_containers:
        total_parent_sections = len(parent_containers)
        vector_store.add_parent_chunks(list(parent_containers.values()))

    # Build final indices (FTS, BTree scalar, IVF-PQ vector)
    vector_store.create_indices()
    elapsed = time.monotonic() - start_time
    throughput = total_chunks / elapsed if elapsed > 0 else 0.0

    table_size_mb = _compute_dir_size_mb(output_db)
    stats_info = vector_store.get_stats()
    index_names = [f"{idx['name']} ({idx['index_type']})" for idx in stats_info.get("indices", [])]
    indices_str = ", ".join(index_names) if index_names else "None"

    # Perform a test hybrid query to verify latency & retrieval
    test_query = "Biotechnology syllabus"
    q_start = time.perf_counter()
    test_vec = embedder.embed_query(test_query)
    test_results = vector_store.hybrid_search(
        query_text=test_query,
        query_vector=test_vec,
        top_k=3,
    )
    test_latency_ms = (time.perf_counter() - q_start) * 1000

    console.print(
        f"\n[bold green]Indexing completed successfully![/bold green]\n"
        f"  Total Chunks:        {total_chunks}\n"
        f"  Parent Sections:     {total_parent_sections}\n"
        f"  Duration:            {elapsed:.2f}s\n"
        f"  Throughput:          {throughput:.1f} chunks/sec\n"
        f"  LanceDB Storage:     {table_size_mb:.2f} MB\n"
        f"  Indices Built:       {indices_str}\n"
        f"  Test Query Latency:  {test_latency_ms:.2f} ms ({len(test_results)} candidates found)"
    )


if __name__ == "__main__":
    app()
