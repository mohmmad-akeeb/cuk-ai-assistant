"""Unit tests for offline parser pipeline and target ELT architecture."""

from __future__ import annotations

import json
from pathlib import Path

import pymupdf as fitz

from cuk_assistant.ingestion.collector.subsystems.manifest import ManifestEntry, ManifestWriter
from cuk_assistant.ingestion.normalize.aggregator import aggregate_asset_references
from cuk_assistant.ingestion.normalize.pipeline import parse_manifest
from cuk_assistant.ingestion.normalize.sanitizer import (
    mask_email,
    sanitize_record_dict,
    scrub_pii,
)
from cuk_assistant.ingestion.parsers.api_parser import OfflineApiParser, ParsedApiRecord
from cuk_assistant.ingestion.parsers.base import BaseParser, ParsedHTML, ParsedPdf
from cuk_assistant.ingestion.parsers.html_parser import OfflineHtmlParser
from cuk_assistant.ingestion.parsers.pdf_parser import OfflinePdfParser
from cuk_assistant.schemas.document import Document


class TestOfflineParsers:
    def test_protocol_conformance(self) -> None:
        assert isinstance(OfflineHtmlParser(), BaseParser)
        assert isinstance(OfflinePdfParser(), BaseParser)
        assert isinstance(OfflineApiParser(), BaseParser)

    def test_html_parser_extracts_markdown(self, tmp_path: Path) -> None:
        html_content = """
        <html>
            <body>
                <h1>Department of Mathematics</h1>
                <p>Welcome to our department.</p>
                <table>
                    <tr><th>Course</th><th>Credits</th></tr>
                    <tr><td>Calculus</td><td>4</td></tr>
                </table>
                <a href="https://example.com/syllabus.pdf">Syllabus PDF</a>
            </body>
        </html>
        """
        html_file = tmp_path / "test.html"
        html_file.write_text(html_content, encoding="utf-8")

        parser = OfflineHtmlParser()
        result = parser.parse_file(html_file)

        assert isinstance(result, ParsedHTML)
        assert "Department of Mathematics" in result.text
        assert "| Course | Credits |" in result.text
        assert "| Calculus | 4 |" in result.text
        assert len(result.links_out) == 1
        assert result.links_out[0].type == "pdf"

    def test_pdf_parser_extracts_full_text(self, tmp_path: Path) -> None:
        doc = fitz.open()
        for i in range(3):
            page = doc.new_page()
            page.insert_text((50, 50), f"Test content page {i + 1}")
        pdf_file = tmp_path / "sample.pdf"
        doc.save(pdf_file)
        doc.close()

        parser = OfflinePdfParser()
        result = parser.parse_file(pdf_file, fallback_title="Sample PDF")

        assert isinstance(result, ParsedPdf)
        assert result.page_count == 3
        assert "--- Page 1 ---" in result.text
        assert "Test content page 1" in result.text
        assert "--- Page 3 ---" in result.text
        assert "Test content page 3" in result.text

    def test_api_parser_scrubs_pii(self, tmp_path: Path) -> None:
        raw_record = {
            "content_type": "faculty",
            "school_name": "School of Engineering",
            "department_name": "Computer Science",
            "title": "Dr. John Doe",
            "designation": "Professor",
            "email": "johndoe@cukashmir.ac.in",
            "description": "DOB: 1980-05-15T00:00:00. Contact: 9876543210.",
        }
        api_file = tmp_path / "faculty.json"
        api_file.write_text(json.dumps({"raw_record": raw_record}), encoding="utf-8")

        parser = OfflineApiParser()
        result = parser.parse_file(api_file, raw_record)

        assert isinstance(result, ParsedApiRecord)
        assert "Dr. John Doe" in result.text
        assert "[REDACTED-DOB]" in result.text
        assert "[REDACTED-PHONE]" in result.text
        assert "9876543210" not in result.text
        assert "1980-05-15T00:00:00" not in result.text


class TestSanitizerAndAggregator:
    def test_sanitizer_scrubs_all_pii(self) -> None:
        raw = "Phone: 9876543210. DOB: 1990-01-01T00:00:00. Roll Number: BT-2022-001."
        sanitized = scrub_pii(raw)
        assert "9876543210" not in sanitized
        assert "1990-01-01T00:00:00" not in sanitized
        assert "[REDACTED-PHONE]" in sanitized
        assert "[REDACTED-DOB]" in sanitized
        assert "[REDACTED-ROLL-NO]" in sanitized

    def test_mask_email(self) -> None:
        assert mask_email("johndoe@cukashmir.ac.in") == "j*****e@cukashmir.ac.in"
        assert mask_email("ab@cukashmir.ac.in") == "a*@cukashmir.ac.in"

    def test_sanitize_record_dict(self) -> None:
        rec = {
            "Name": "Alice",
            "MobileNo": "9876543210",
            "DOB": "1995-04-12T00:00:00",
            "Details": "Call at 9876543210",
        }
        cleaned = sanitize_record_dict(rec)
        assert "MobileNo" not in cleaned
        assert "DOB" not in cleaned
        assert cleaned["Name"] == "Alice"
        assert "[REDACTED-PHONE]" in cleaned["Details"]

    def test_multi_route_aggregation(self) -> None:
        entries = [
            {
                "provenance": {
                    "department": "Mathematics",
                    "school": "Physical Sciences",
                    "node_path": ["Home", "Math"],
                },
                "raw_meta": {"title": "Syllabus 2026", "is_pdf": True},
            },
            {
                "provenance": {
                    "department": "Physics",
                    "school": "Physical Sciences",
                    "node_path": ["Home", "Physics"],
                },
                "raw_meta": {"title": "Syllabus 2026", "is_pdf": True},
            },
            {
                "provenance": {
                    "department": "Chemistry",
                    "school": "Physical Sciences",
                    "node_path": ["Home", "Chemistry"],
                },
                "raw_meta": {"title": "Syllabus 2026", "is_pdf": True},
            },
        ]
        agg = aggregate_asset_references(entries)
        assert len(agg["associated_departments"]) == 3
        assert "Mathematics" in agg["associated_departments"]
        assert "Physics" in agg["associated_departments"]
        assert "Chemistry" in agg["associated_departments"]
        assert len(agg["associated_routes"]) == 3
        # 3 departments means is_university_wide is set to True
        assert agg["is_university_wide"] is True
        assert agg["primary_department"] == "University-Wide"


class TestManifestWriter:
    def test_manifest_writer_appends(self, tmp_path: Path) -> None:
        mfile = tmp_path / "manifest.jsonl"
        writer = ManifestWriter(mfile)

        entry1 = ManifestEntry(
            asset_id="a1",
            asset_type="html",
            source_url="https://cuk.ac.in",
            local_path="data/raw/html/a1.html",
        )
        writer.append(entry1)

        entry2 = ManifestEntry(
            asset_id="a2",
            asset_type="pdf",
            source_url="https://cuk.ac.in/f.pdf",
            local_path="data/raw/pdf/a2.pdf",
        )
        writer.append(entry2)

        lines = [json.loads(line) for line in mfile.read_text().splitlines() if line]
        assert len(lines) == 2
        assert lines[0]["asset_id"] == "a1"
        assert lines[1]["asset_id"] == "a2"


class TestDocumentSchemaValidation:
    def test_document_model(self) -> None:
        doc = Document(text="Sample content", metadata={"key": "val"})
        assert doc.text == "Sample content"
        assert doc.metadata["key"] == "val"
        dumped = doc.model_dump()
        assert dumped["text"] == "Sample content"


class TestParseManifestEndToEnd:
    def test_parse_manifest_end_to_end(self, tmp_path: Path) -> None:
        doc = fitz.open()
        p = doc.new_page()
        p.insert_text((50, 50), "Ordinance 2026")
        pdf_file = tmp_path / "ord.pdf"
        doc.save(pdf_file)
        doc.close()

        manifest_file = tmp_path / "manifest.jsonl"
        entries = [
            {
                "asset_id": "pdf001",
                "asset_type": "pdf",
                "source_url": "https://cuk.ac.in/ord.pdf",
                "local_path": str(pdf_file),
                "scraped_at": "2026-11-16T12:00:00Z",
                "provenance": {
                    "school": "Administration",
                    "department": "Registrar",
                    "node_path": ["Admin", "Registrar"],
                },
                "raw_meta": {"title": "Ordinance 2026", "is_pdf": True, "file_name": "ord.pdf"},
            }
        ]
        manifest_file.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")

        out_file = tmp_path / "out_docs.jsonl"
        stats = parse_manifest(manifest_file, out_file, project_root=tmp_path)

        assert stats.output_count == 1
        assert stats.pdf_count == 1
        assert out_file.exists()

        records = [json.loads(line) for line in out_file.read_text().splitlines() if line]
        assert len(records) == 1
        assert "Ordinance 2026" in records[0]["text"]
        assert records[0]["metadata"]["page_count"] == 1
        assert records[0]["metadata"]["page_number"] is None
