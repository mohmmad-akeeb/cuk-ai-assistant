"""cuk_assistant/evals/cli.py

CLI entry-point for the regression benchmark evaluator pipeline (cuk-eval).
Evaluates retrieval Hit Rate@K, MRR, keyword recall, slot accuracy,
and failure attribution diagnostics against the golden evaluation dataset.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from cuk_assistant.core.factory import create_retrieval_coordinator
from cuk_assistant.evals.evaluator import RAGEvaluator
from cuk_assistant.evals.query_miner import MenuHierarchyMiner
from cuk_assistant.evals.schemas import TestCaseEvalResult

logger = logging.getLogger(__name__)
console = Console()

app = typer.Typer(
    name="cuk-eval",
    help="Central University of Kashmir RAG Regression Benchmark Evaluator.",
    no_args_is_help=False,
)


@app.command(name="run")
def run(
    dataset: Annotated[
        Path,
        typer.Option(
            "--dataset",
            "-d",
            help="Path to golden evaluation dataset (.jsonl).",
            exists=False,
            dir_okay=False,
            readable=True,
        ),
    ] = Path("evals/golden_dataset.jsonl"),
    top_k: Annotated[
        int,
        typer.Option(
            "--top-k",
            "-k",
            help="Top-K cutoff rank for Hit Rate@K and retrieval metrics.",
            min=1,
            max=50,
        ),
    ] = 5,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Optional file path to output structured JSON evaluation results.",
            dir_okay=False,
        ),
    ] = None,
    strict: Annotated[
        bool,
        typer.Option(
            "--strict",
            help="Fail with exit code 1 if Hit Rate@K is below minimum threshold.",
        ),
    ] = False,
    min_hit_rate: Annotated[
        float,
        typer.Option(
            "--min-hit-rate",
            help="Minimum Hit Rate@K threshold for strict evaluation (0.0 to 1.0).",
            min=0.0,
            max=1.0,
        ),
    ] = 0.5,
) -> None:
    """Run regression benchmark evaluation across the golden dataset."""
    console.print(
        Panel.fit(
            f"[bold cyan]CUK RAG Assistant — Benchmark Evaluation Harness[/bold cyan]\n"
            f"[dim]Dataset:[/dim] [yellow]{dataset}[/yellow] | [dim]Top-K:[/dim] [green]{top_k}[/green]",
            border_style="cyan",
        )
    )

    if not dataset.exists():
        console.print(
            f"[bold red]Error:[/bold red] Dataset file not found at [yellow]{dataset}[/yellow]"
        )
        raise typer.Exit(code=1)

    # Initialize Retrieval Coordinator and Evaluator Harness
    with console.status("[bold green]Initializing hybrid retrieval coordinator...[/bold green]"):
        try:
            coordinator = create_retrieval_coordinator()
            evaluator = RAGEvaluator(retrieval_coordinator=coordinator)
        except Exception as exc:
            console.print(f"[bold red]Failed to initialize retrieval coordinator:[/bold red] {exc}")
            raise typer.Exit(code=1) from exc

    # Count total cases in dataset
    with open(dataset, encoding="utf-8") as f:
        total_cases = sum(1 for line in f if line.strip())

    if total_cases == 0:
        console.print(
            f"[bold red]Error:[/bold red] Evaluation dataset [yellow]{dataset}[/yellow] is empty."
        )
        raise typer.Exit(code=1)

    console.print(
        f"Loaded [bold green]{total_cases}[/bold green] test cases from [yellow]{dataset}[/yellow]."
    )

    # Run evaluation with Rich progress bar
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    )

    with progress:
        task_id = progress.add_task("[cyan]Evaluating QA benchmarks...", total=total_cases)

        def on_case_done(current: int, total: int, result: TestCaseEvalResult) -> None:
            status_text = "[green]HIT[/green]" if result.hit_at_k else "[red]MISS[/red]"
            progress.update(
                task_id,
                advance=1,
                description=f"[cyan]Evaluating QA benchmarks... ({status_text} {result.eval_id})",
            )

        summary = evaluator.evaluate_dataset(
            dataset_path_or_cases=dataset,
            top_k=top_k,
            progress_callback=on_case_done,
        )

    # Render Results Table
    table = Table(
        title=f"Evaluation Benchmark Summary (Top-K = {top_k})", header_style="bold magenta"
    )
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Score / Result", style="bold green")
    table.add_column("Target / Notes", style="dim")

    hit_rate_pct = summary.hit_rate_at_k * 100
    hit_rate_color = "green" if hit_rate_pct >= 70 else ("yellow" if hit_rate_pct >= 40 else "red")
    hit_count = (
        sum(1 for r in summary.results if r.hit_at_k)
        if summary.results
        else round(summary.hit_rate_at_k * summary.total_cases)
    )
    table.add_row(
        f"Retrieval Hit Rate@{top_k}",
        f"[{hit_rate_color}]{hit_rate_pct:.1f}%[/{hit_rate_color}]",
        f"{hit_count} / {summary.total_cases} queries hit",
    )

    mrr_color = "green" if summary.mrr >= 0.6 else ("yellow" if summary.mrr >= 0.3 else "red")
    table.add_row(
        "Mean Reciprocal Rank (MRR)",
        f"[{mrr_color}]{summary.mrr:.3f}[/{mrr_color}]",
        "Higher is better (1.0 = top rank)",
    )

    table.add_row(
        "Mean Keyword Recall",
        f"{summary.mean_keyword_recall * 100:.1f}%",
        "Proportion of expected keywords in retrieved chunks",
    )

    slot_color = (
        "green"
        if summary.mean_slot_accuracy >= 0.8
        else ("yellow" if summary.mean_slot_accuracy >= 0.5 else "red")
    )
    table.add_row(
        "Slot Extraction Accuracy",
        f"[{slot_color}]{summary.mean_slot_accuracy * 100:.1f}%[/{slot_color}]",
        "Faceted slot filler precision across entities",
    )

    console.print()
    console.print(table)

    # Render Failure Attribution Breakdown
    if summary.failure_attribution_counts:
        fail_table = Table(
            title="Diagnostic Failure Attribution Breakdown", header_style="bold red"
        )
        fail_table.add_column("Diagnostic Code", style="bold red")
        fail_table.add_column("Count", style="yellow", justify="right")
        fail_table.add_column("Percentage", style="dim", justify="right")

        for code, count in sorted(
            summary.failure_attribution_counts.items(), key=lambda x: x[1], reverse=True
        ):
            pct = (count / summary.total_cases) * 100
            fail_table.add_row(code, str(count), f"{pct:.1f}%")

        console.print()
        console.print(fail_table)
    else:
        console.print(
            "\n[bold green]Zero retrieval failures detected! Perfect recall.[/bold green]"
        )

    # Output JSON report if requested
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w", encoding="utf-8") as f:
            f.write(summary.model_dump_json(indent=2))
        console.print(f"\n[green]Saved detailed evaluation report to [bold]{output}[/bold][/green]")

    # Check strict criteria
    if strict and summary.hit_rate_at_k < min_hit_rate:
        console.print(
            f"\n[bold red]FAILED:[/bold red] Hit Rate@{top_k} ({summary.hit_rate_at_k:.2f}) "
            f"is below required threshold ({min_hit_rate:.2f})."
        )
        raise typer.Exit(code=1)


@app.command(name="mine-queries")
def mine_queries(
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Path where mined menu hierarchy JSON will be saved.",
            dir_okay=False,
        ),
    ] = Path("configs/menu_hierarchy.json"),
    documents: Annotated[
        Path | None,
        typer.Option(
            "--documents",
            "-d",
            help="Optional path to documents.jsonl file.",
            exists=False,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
    chunks: Annotated[
        Path | None,
        typer.Option(
            "--chunks",
            "-c",
            help="Optional path to chunks.jsonl file.",
            exists=False,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
) -> None:
    """Analyze document and chunk metadata, dynamically generating menu hierarchy."""
    console.print(
        Panel.fit(
            f"[bold cyan]CUK Starter Menu Hierarchy Generator[/bold cyan]\n"
            f"[dim]Output Target:[/dim] [yellow]{output}[/yellow]",
            border_style="cyan",
        )
    )

    miner = MenuHierarchyMiner()
    if documents or chunks:
        console.print(f"Loading metadata from: documents={documents}, chunks={chunks}")
        miner.load_from_files(documents_path=documents, chunks_path=chunks)

    saved_path = miner.export_json(output)
    mined_resp = miner.mine()
    total_prompts = sum(len(c.prompts) for c in mined_resp.categories)

    console.print(
        f"[bold green]Successfully generated menu hierarchy with "
        f"{len(mined_resp.categories)} categories and {total_prompts} prompt chips![/bold green]"
    )
    console.print(f"Output saved to: [bold]{saved_path}[/bold]")


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
) -> None:
    """CUK Assistant Evaluation Benchmark CLI."""
    if ctx.invoked_subcommand is None:
        # Default behavior: display help
        console.print(ctx.get_help())


if __name__ == "__main__":
    app()
