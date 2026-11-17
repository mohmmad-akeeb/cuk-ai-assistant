#!/usr/bin/env python3
"""Consolidate page-level crawled PDF slices and HTML documents into canonical records.

Reads data/processed/documents.jsonl, groups multi-page PDF slices and multi-route links
into single complete documents with associated_departments, associated_schools,
and associated_routes, and outputs to data/processed/documents_canonical.jsonl.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import urllib.parse
from collections import defaultdict
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Consolidate crawler page slices into canonical documents.")
console = Console()


def _get_pdf_key(meta: dict) -> str:
    """Derive canonical identifier for a PDF document."""
    file_name = meta.get("file_name", "")
    if file_name:
        clean = urllib.parse.unquote(file_name).split("?")[0].strip()
        if clean:
            return clean

    file_url = meta.get("file_url", "") or meta.get("source_url", "")
    if file_url:
        clean = urllib.parse.unquote(file_url.split("/")[-1]).split("?")[0].strip()
        if clean:
            return clean

    return meta.get("content_hash", "")


def _get_html_key(meta: dict) -> str:
    """Derive canonical key for an HTML document."""
    page_url = meta.get("page_url", "") or meta.get("source_url", "")
    can = page_url.split("#")[-1] if "#" in page_url else page_url
    return can or meta.get("doc_id", "")


def _is_more_complete(new_doc: dict, existing_doc: dict) -> bool:
    """Check if new_doc is more complete / newer than existing_doc."""
    new_text = new_doc.get("text", "").strip()
    existing_text = existing_doc.get("text", "").strip()

    # Prefer non-empty text
    if bool(new_text) != bool(existing_text):
        return bool(new_text)

    # Prefer substantially longer text
    if len(new_text) > len(existing_text) + 20:
        return True
    if len(existing_text) > len(new_text) + 20:
        return False

    # Prefer later scraped_at / created_on
    new_scraped = new_doc.get("metadata", {}).get("scraped_at", "")
    existing_scraped = existing_doc.get("metadata", {}).get("scraped_at", "")
    return new_scraped >= existing_scraped


def _consolidate_pdf_group(key: str, group: list[dict]) -> dict:
    """Merge a group of PDF slices/routes into one canonical PDF document."""
    metas = [d.get("metadata", {}) for d in group]

    # Select base metadata with most complete fields
    base_meta: dict = {}
    for m in metas:
        if not base_meta:
            base_meta = dict(m)
        else:
            for k, v in m.items():
                if (base_meta.get(k) is None or base_meta.get(k) == "") and v not in (None, ""):
                    base_meta[k] = v

    merged_metadata = dict(base_meta)

    # Cross-route merging
    all_departments = sorted({m.get("department") for m in metas if m.get("department")})
    all_schools = sorted({m.get("school") for m in metas if m.get("school")})

    unique_routes: list[list[str]] = []
    for m in metas:
        route = m.get("node_path")
        if route and route not in unique_routes:
            unique_routes.append(route)

    merged_metadata["associated_departments"] = all_departments
    merged_metadata["associated_schools"] = all_schools
    merged_metadata["associated_routes"] = unique_routes

    # If linked in >= 3 departments or >= 2 schools, mark university-wide
    is_univ = (
        bool(base_meta.get("is_university_wide", False))
        or len(all_departments) >= 3
        or len(all_schools) >= 2
    )
    if is_univ:
        merged_metadata["is_university_wide"] = True
        merged_metadata["primary_department"] = "University-Wide"
    else:
        merged_metadata["is_university_wide"] = False
        merged_metadata["primary_department"] = all_departments[0] if all_departments else "General"

    # Text reassembly
    slices = [d for d in group if isinstance(d.get("metadata", {}).get("page_number"), int)]
    if slices:
        # Deduplicate slices by page_number if multiple routes crawled same page
        unique_slices_by_page: dict[int, dict] = {}
        for s in slices:
            pn = s["metadata"]["page_number"]
            if pn not in unique_slices_by_page or len(s.get("text", "")) > len(
                unique_slices_by_page[pn].get("text", "")
            ):
                unique_slices_by_page[pn] = s

        sorted_slices = [unique_slices_by_page[pn] for pn in sorted(unique_slices_by_page.keys())]
        unified_text = "\n\n".join(
            f"--- Page {s['metadata']['page_number']} ---\n{s.get('text', '').strip()}"
            for s in sorted_slices
            if s.get("text", "").strip()
        ).strip()
        page_count = max(unique_slices_by_page.keys()) if unique_slices_by_page else 1
    else:
        # Non-sliced PDF (e.g. short PDF <= 4 pages)
        non_empty = [d for d in group if d.get("text", "").strip()]
        if non_empty:
            best_doc = max(non_empty, key=lambda d: len(d.get("text", "")))
            raw_text = best_doc.get("text", "").strip()
            unified_text = raw_text if "--- Page" in raw_text else f"--- Page 1 ---\n{raw_text}"
        else:
            # Sensitive or purely scanned PDF without extractable text
            unified_text = group[0].get("text", "")

        page_count = base_meta.get("pdf_pages") or base_meta.get("page_count") or 1

    file_name = (
        merged_metadata.get("file_name")
        or (merged_metadata.get("file_url", "").split("/")[-1].split("?")[0])
        or key
    )
    merged_metadata["file_name"] = file_name
    canonical_doc_id = hashlib.sha256(f"pdf::{file_name}".encode()).hexdigest()[:24]
    merged_metadata["doc_id"] = canonical_doc_id
    merged_metadata["content_hash"] = hashlib.sha256(unified_text.encode()).hexdigest()
    merged_metadata["page_count"] = page_count
    merged_metadata["page_number"] = None
    merged_metadata["chunk_index"] = 0

    return {"text": unified_text, "metadata": merged_metadata}


@app.command()
def main(
    input_file: Path = typer.Option(
        Path("data/processed/documents.jsonl"),
        "--input",
        "-i",
        help="Path to input documents.jsonl",
    ),
    output_file: Path = typer.Option(
        Path("data/processed/documents_canonical.jsonl"),
        "--output",
        "-o",
        help="Path to output documents_canonical.jsonl",
    ),
    replace: bool = typer.Option(
        False,
        "--replace",
        help="Back up documents.jsonl to documents_raw_crawl.jsonl and replace documents.jsonl",
    ),
) -> None:
    """Consolidate crawled page-level documents into unified canonical records."""
    if not input_file.exists():
        console.print(f"[bold red]Error:[/bold red] Input file {input_file} does not exist.")
        raise typer.Exit(code=1)

    console.print(f"[bold cyan]Reading records from:[/bold cyan] {input_file}")

    pdf_groups: dict[str, list[dict]] = defaultdict(list)
    html_groups: dict[str, dict] = {}
    original_line_count = 0
    original_pdf_count = 0
    original_html_count = 0

    with input_file.open("r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if not line_str:
                continue
            original_line_count += 1
            doc = json.loads(line_str)
            meta = doc.get("metadata", {})
            if meta.get("is_pdf"):
                original_pdf_count += 1
                key = _get_pdf_key(meta)
                pdf_groups[key].append(doc)
            else:
                original_html_count += 1
                key = _get_html_key(meta)
                if key not in html_groups or _is_more_complete(doc, html_groups[key]):
                    html_groups[key] = doc

    console.print(
        f"[green]Grouped {original_line_count} records into "
        f"{len(pdf_groups)} unique PDFs and {len(html_groups)} unique HTML documents.[/green]"
    )

    # Reassemble and consolidate PDF groups
    consolidated_records: list[dict] = []

    # First add HTML documents
    for doc in html_groups.values():
        consolidated_records.append(doc)

    # Next add consolidated PDF documents
    for key, group in pdf_groups.items():
        canonical_doc = _consolidate_pdf_group(key, group)
        consolidated_records.append(canonical_doc)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as out:
        for doc in consolidated_records:
            out.write(json.dumps(doc, ensure_ascii=False) + "\n")

    consolidated_line_count = len(consolidated_records)
    redundant_pdf_slices = original_pdf_count - len(pdf_groups)
    redundant_html_records = original_html_count - len(html_groups)
    total_redundant = original_line_count - consolidated_line_count

    orig_size_bytes = input_file.stat().st_size
    cons_size_bytes = output_file.stat().st_size
    bytes_saved = orig_size_bytes - cons_size_bytes
    pct_saved = (bytes_saved / orig_size_bytes * 100) if orig_size_bytes > 0 else 0.0

    if replace:
        backup_path = input_file.parent / "documents_raw_crawl.jsonl"
        console.print(f"[yellow]Backing up {input_file} -> {backup_path}[/yellow]")
        shutil.copy2(input_file, backup_path)
        console.print(f"[yellow]Replacing {input_file} with {output_file}[/yellow]")
        shutil.copy2(output_file, input_file)

    # Render summary table
    table = Table(title="CUK RAG Assistant — Document Consolidation Summary")
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Value", style="magenta")

    table.add_row("Original Lines", f"{original_line_count:,}")
    table.add_row("Consolidated Lines", f"{consolidated_line_count:,}")
    table.add_row("Unique PDFs", f"{len(pdf_groups):,}")
    table.add_row("Unique HTML Documents", f"{len(html_groups):,}")
    table.add_row("Redundant PDF Slices Removed", f"{redundant_pdf_slices:,}")
    table.add_row("Redundant HTML Records Merged", f"{redundant_html_records:,}")
    table.add_row("Total Redundant Records Pruned", f"{total_redundant:,}")
    table.add_row("Original File Size", f"{orig_size_bytes / (1024 * 1024):.2f} MB")
    table.add_row("Consolidated File Size", f"{cons_size_bytes / (1024 * 1024):.2f} MB")
    table.add_row("Storage Space Saved", f"{bytes_saved / (1024 * 1024):.2f} MB ({pct_saved:.1f}%)")
    table.add_row("Canonical Output Path", str(output_file))
    if replace:
        table.add_row("Active Documents Replaced", "Yes (backup at documents_raw_crawl.jsonl)")

    console.print(table)


if __name__ == "__main__":
    app()
