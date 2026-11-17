"""tests/unit/test_ingestion_runner.py

Unit tests for IngestionPipelineRunner and cuk-ingest CLI:
- End-to-end processing from documents.jsonl to chunks.jsonl
- Markdown table preservation within atomic chunks
- Hierarchical parent-child chunk links
- Deterministic chunk_id, non-empty text, doc_id, and content_hash
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from cuk_assistant.ingestion.cli.ingest import app
from cuk_assistant.ingestion.runner import IngestionPipelineRunner
from cuk_assistant.schemas.chunks import ChunkType


class TestIngestionPipelineRunner:
    """Validate IngestionPipelineRunner behavior and invariants."""

    def test_run_generates_valid_chunks_jsonl(self, tmp_path: Path) -> None:
        input_docs = tmp_path / "documents.jsonl"
        output_chunks = tmp_path / "chunks.jsonl"

        doc1 = {
            "text": (
                "# School of Technology\n\n"
                "Overview of programs offered by the School of Technology.\n\n"
                "## Computer Science & Engineering\n\n"
                "The curriculum covers advanced data structures and algorithms.\n\n"
                "| Course Code | Title | Credits |\n"
                "|---|---|---|\n"
                "| CS-101 | Intro to Programming | 4 |\n"
                "| CS-102 | Data Structures | 4 |\n"
            ),
            "metadata": {
                "doc_id": "tech_school_01",
                "title": "School of Technology Guide",
                "source_url": "https://cukashmir.ac.in/tech",
            },
        }

        doc2 = {
            "text": (
                "CENTRAL UNIVERSITY OF KASHMIR\n"
                "F.No. CUK/Admn/2024/55\n"
                "Dated: 12-04-2024\n\n"
                "Notice regarding campus holiday schedule.\n\n"
                "Sd/-\n"
                "Registrar"
            ),
            "metadata": {
                "doc_id": "holiday_notice_02",
                "title": "Holiday Notice",
                "source_url": "https://cukashmir.ac.in/notice",
            },
        }

        with input_docs.open("w", encoding="utf-8") as f:
            f.write(json.dumps(doc1) + "\n")
            f.write(json.dumps(doc2) + "\n")

        runner = IngestionPipelineRunner()
        stats = runner.run(documents_path=input_docs, output_chunks_path=output_chunks)

        assert stats.total_documents == 2
        assert stats.total_chunks > 0
        assert stats.table_chunks >= 1
        assert stats.errors == 0
        assert output_chunks.is_file()

        # Read and verify generated chunks
        chunks = []
        with output_chunks.open("r", encoding="utf-8") as f:
            for line in f:
                chunks.append(json.loads(line))

        assert len(chunks) == stats.total_chunks

        # Invariant Verification:
        for chunk in chunks:
            # 1. Non-empty required fields
            assert chunk.get("doc_id"), f"Missing doc_id in {chunk}"
            assert chunk.get("chunk_id"), f"Missing chunk_id in {chunk}"
            assert chunk.get("text"), f"Missing text in {chunk}"
            assert chunk.get("content_hash"), f"Missing content_hash in {chunk}"

            # 2. Table atomicity: table chunks must retain complete markdown table
            if chunk.get("chunk_type") == ChunkType.MARKDOWN_TABLE:
                assert "| Course Code | Title | Credits |" in chunk["text"]
                assert "| CS-102 | Data Structures | 4 |" in chunk["text"]

            # 3. Child chunks must carry parent_chunk_id
            if chunk.get("chunk_type") in (ChunkType.PARAGRAPH, ChunkType.MARKDOWN_TABLE):
                assert chunk.get("parent_chunk_id") is not None, (
                    f"Child chunk {chunk['chunk_id']} has no parent_chunk_id"
                )

        # Check doc2 intrinsic fact enrichment
        doc2_chunks = [c for c in chunks if c["doc_id"] == "holiday_notice_02"]
        assert len(doc2_chunks) > 0
        for c in doc2_chunks:
            meta = c.get("metadata", {})
            assert meta.get("reference_number") == "F.No. CUK/Admn/2024/55"
            assert meta.get("notification_date") == "2024-04-12"
            assert meta.get("issuing_authority") == "Registrar"


class TestCukIngestCli:
    """Validate Typer CLI runner for cuk-ingest."""

    def test_cli_execution_with_temp_files(self, tmp_path: Path) -> None:
        input_docs = tmp_path / "documents.jsonl"
        output_chunks = tmp_path / "chunks.jsonl"

        doc = {
            "text": "# Admissions 2024\n\nAdmissions are now open for B.Tech programs.",
            "metadata": {"doc_id": "adm_2024", "title": "Admissions"},
        }
        input_docs.write_text(json.dumps(doc) + "\n", encoding="utf-8")

        cli_runner = CliRunner()
        result = cli_runner.invoke(
            app,
            ["-i", str(input_docs), "-o", str(output_chunks), "-w", "1"],
        )

        assert result.exit_code == 0
        assert "Ingestion completed successfully!" in result.output
        assert output_chunks.is_file()
