#!/usr/bin/env python3
"""Bootstrap the Raw Data Lake and manifest.jsonl from existing offline assets.

Populates:
  data/raw/manifest.jsonl
  data/raw/html/
  data/raw/api/
using the existing data/raw/pdf/ files and data/processed/documents.jsonl / nodes.jsonl.
Zero network access required.
"""

from __future__ import annotations

import hashlib
import json
import urllib.parse
from datetime import UTC, datetime
from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(help="Bootstrap raw lake from local assets.")
console = Console()


def _make_asset_id(url_or_key: str) -> str:
    """Deterministic 24-character asset ID."""
    return hashlib.sha256(url_or_key.encode("utf-8")).hexdigest()[:24]


def _find_pdf_path(raw_pdf_dir: Path, meta: dict) -> Path | None:
    fn = meta.get("file_name", "")
    fu = meta.get("file_url", "") or meta.get("source_url", "")
    candidates = [
        fn,
        urllib.parse.unquote(fn),
        fn.split("?")[0],
        urllib.parse.unquote(fn).split("?")[0],
        fu.split("/")[-1],
        urllib.parse.unquote(fu.split("/")[-1]),
        fu.split("/")[-1].split("?")[0],
        urllib.parse.unquote(fu.split("/")[-1]).split("?")[0],
    ]
    for c in candidates:
        if c:
            p = raw_pdf_dir / c
            if p.exists():
                return p
    return None


@app.command()
def main(
    processed_docs: Path = typer.Option(
        Path("data/processed/documents.jsonl"),
        "--docs",
        help="Path to processed documents.jsonl",
    ),
    raw_dir: Path = typer.Option(
        Path("data/raw"),
        "--raw-dir",
        help="Path to raw lake directory",
    ),
) -> None:
    manifest_path = raw_dir / "manifest.jsonl"
    pdf_dir = raw_dir / "pdf"
    html_dir = raw_dir / "html"
    api_dir = raw_dir / "api"

    html_dir.mkdir(parents=True, exist_ok=True)
    api_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"[bold cyan]Bootstrapping raw lake from {processed_docs} ...[/bold cyan]")

    seen_asset_ids: set[str] = set()
    manifest_entries: list[dict] = []

    pdf_count = 0
    html_count = 0
    api_count = 0

    if processed_docs.exists():
        with processed_docs.open("r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if not line_str:
                    continue
                doc = json.loads(line_str)
                meta = doc.get("metadata", {})
                is_pdf = meta.get("is_pdf", False)

                if is_pdf:
                    # PDF Asset
                    source_url = meta.get("file_url") or meta.get("source_url") or ""
                    clean_name = meta.get("file_name", "") or source_url.split("/")[-1]
                    clean_name = clean_name.split("?")[0]
                    canonical_key = f"pdf::{clean_name}"
                    asset_id = _make_asset_id(canonical_key)

                    if asset_id in seen_asset_ids:
                        # Append any new route/department to existing manifest entry
                        for entry in manifest_entries:
                            if entry["asset_id"] == asset_id:
                                dept = meta.get("department")
                                if (
                                    dept
                                    and dept not in entry["provenance"]["associated_departments"]
                                ):
                                    entry["provenance"]["associated_departments"].append(dept)
                                route = meta.get("node_path")
                                if route and route not in entry["provenance"]["associated_routes"]:
                                    entry["provenance"]["associated_routes"].append(route)
                                break
                        continue

                    seen_asset_ids.add(asset_id)
                    local_pdf = _find_pdf_path(pdf_dir, meta)
                    if local_pdf:
                        rel_path = f"data/raw/pdf/{local_pdf.name}"
                    else:
                        rel_path = f"data/raw/pdf/{clean_name}"

                    manifest_entries.append(
                        {
                            "asset_id": asset_id,
                            "asset_type": "pdf",
                            "source_url": source_url,
                            "local_path": rel_path,
                            "scraped_at": meta.get("scraped_at")
                            or datetime.now(tz=UTC).isoformat(),
                            "provenance": {
                                "school": meta.get("school", ""),
                                "department": meta.get("department", ""),
                                "node_path": meta.get("node_path", []),
                                "associated_departments": [meta.get("department")]
                                if meta.get("department")
                                else [],
                                "associated_routes": [meta.get("node_path")]
                                if meta.get("node_path")
                                else [],
                            },
                            "raw_meta": meta,
                        }
                    )
                    pdf_count += 1

                else:
                    # HTML / API Asset
                    source_url = meta.get("page_url") or meta.get("source_url") or ""
                    rec_id = meta.get("record_id", "")
                    endpoint = meta.get("raw_api_endpoint", "")
                    canonical_key = f"{source_url}::{endpoint}::{rec_id}"
                    asset_id = _make_asset_id(canonical_key)

                    if asset_id in seen_asset_ids:
                        continue
                    seen_asset_ids.add(asset_id)

                    text_content = doc.get("text", "")
                    is_api_record = bool(
                        endpoint
                        and rec_id
                        and meta.get("content_type") in ("faculty", "notice", "tender")
                    )

                    if is_api_record:
                        local_file = api_dir / f"{asset_id}.json"
                        if not local_file.exists():
                            local_file.write_text(
                                json.dumps(
                                    {"raw_record": meta, "extracted_text": text_content}, indent=2
                                ),
                                encoding="utf-8",
                            )
                        rel_path = f"data/raw/api/{asset_id}.json"
                        asset_type = "api_json"
                        api_count += 1
                    else:
                        local_file = html_dir / f"{asset_id}.html"
                        if not local_file.exists():
                            local_file.write_text(text_content, encoding="utf-8")
                        rel_path = f"data/raw/html/{asset_id}.html"
                        asset_type = "html"
                        html_count += 1

                    manifest_entries.append(
                        {
                            "asset_id": asset_id,
                            "asset_type": asset_type,
                            "source_url": source_url,
                            "local_path": rel_path,
                            "scraped_at": meta.get("scraped_at")
                            or datetime.now(tz=UTC).isoformat(),
                            "provenance": {
                                "school": meta.get("school", ""),
                                "department": meta.get("department", ""),
                                "node_path": meta.get("node_path", []),
                                "associated_departments": [meta.get("department")]
                                if meta.get("department")
                                else [],
                                "associated_routes": [meta.get("node_path")]
                                if meta.get("node_path")
                                else [],
                            },
                            "raw_meta": meta,
                        }
                    )

    # Write manifest.jsonl
    with manifest_path.open("w", encoding="utf-8") as out:
        for entry in manifest_entries:
            out.write(json.dumps(entry, ensure_ascii=False) + "\n")

    console.print(
        f"[bold green]Successfully bootstrapped raw lake with {len(manifest_entries)} assets:[/bold green]\n"
        f"  - PDFs: {pdf_count}\n"
        f"  - HTML: {html_count}\n"
        f"  - API JSON: {api_count}\n"
        f"  - Manifest: {manifest_path}"
    )


if __name__ == "__main__":
    app()
