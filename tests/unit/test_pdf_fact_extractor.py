"""tests/unit/test_pdf_fact_extractor.py

Unit tests for PdfFactExtractor:
- Reference / circular numbers (F.No., NIT No., Result Notification No., CUK/...)
- Issuance and notification dates normalized to ISO-8601
- Issuing authority and signatory extraction
- Metadata and chunk enrichment
"""

from __future__ import annotations

from cuk_assistant.ingestion.chunking.hierarchical_chunker import HierarchicalChunker
from cuk_assistant.ingestion.extract.pdf_fact_extractor import (
    PdfFactExtractor,
    PdfIntrinsicFacts,
)
from cuk_assistant.schemas.chunks import ChunkRecord


class TestPdfFactExtractorReferenceNumbers:
    """Validate extraction of various official circular, order, and notification numbers."""

    def test_extract_file_number(self) -> None:
        extractor = PdfFactExtractor()
        text = """
        CENTRAL UNIVERSITY OF KASHMIR
        Green Campus, Ganderbal

        F.No. CUKMR/Exam/22/45
        Dated: 12-05-2023

        NOTIFICATION
        It is notified for the information of all concerned...
        """
        facts = extractor.extract_facts(text)
        assert facts.reference_number == "F.No. CUKMR/Exam/22/45"
        assert facts.notification_date == "2023-05-12"

    def test_extract_nit_number(self) -> None:
        extractor = PdfFactExtractor()
        text = """
        CENTRAL UNIVERSITY OF KASHMIR
        NOTICE INVITING TENDER
        NIT No 04 of 2026
        Dated: 15-01-2026

        E-Tenders are invited from registered contractors...
        """
        facts = extractor.extract_facts(text)
        assert facts.reference_number == "NIT No 04 of 2026"
        assert facts.notification_date == "2026-01-15"

    def test_extract_result_notification_number(self) -> None:
        extractor = PdfFactExtractor()
        text = """
        CENTRAL UNIVERSITY OF KASHMIR
        Result Notification No. 2428
        Dated: 05-10-2023

        The result of students of Integrated B.Sc-M.Sc Physics is declared as under:
        """
        facts = extractor.extract_facts(text)
        assert facts.reference_number == "Result Notification No. 2428"
        assert facts.notification_date == "2023-10-05"

    def test_extract_direct_cuk_path(self) -> None:
        extractor = PdfFactExtractor()
        text = """
        Circular No. CUK/Acad/2023/123
        Date: 2023-08-20

        Subject: Semester Registration
        """
        facts = extractor.extract_facts(text)
        assert facts.reference_number is not None
        assert "CUK/Acad/2023/123" in facts.reference_number
        assert facts.notification_date == "2023-08-20"
        assert facts.subject == "Semester Registration"


class TestPdfFactExtractorDatesAndAuthorities:
    """Validate date normalization and signatory authority detection."""

    def test_various_date_formats(self) -> None:
        extractor = PdfFactExtractor()

        text1 = "Notification Dated: 25.04.2024\nDetails..."
        facts1 = extractor.extract_facts(text1)
        assert facts1.notification_date == "2024-04-25"

        text2 = "Date: May 12, 2023\nDetails..."
        facts2 = extractor.extract_facts(text2)
        assert facts2.notification_date == "2023-05-12"

        text3 = "Dated: 1st October 2023\nDetails..."
        facts3 = extractor.extract_facts(text3)
        assert facts3.notification_date == "2023-10-01"

    def test_extract_signatories_and_authority(self) -> None:
        extractor = PdfFactExtractor()
        text = """
        CENTRAL UNIVERSITY OF KASHMIR
        F.No. CUK/Gen/2024/01
        Dated: 10-02-2024

        CIRCULAR
        All departments are requested to submit reports.

        Sd/-
        (Prof. M. A. Shah)
        Dean Academic Affairs

        Copy to:
        1. Controller of Examinations
        2. Registrar
        """
        facts = extractor.extract_facts(text)
        assert facts.issuing_authority in (
            "Dean Academic Affairs",
            "Registrar",
            "Controller of Examinations",
        )
        assert any("Dean Academic Affairs" in s for s in facts.signatories)


class TestMetadataAndChunkEnrichment:
    """Validate document metadata and ChunkRecord enrichment."""

    def test_enrich_document_metadata(self) -> None:
        extractor = PdfFactExtractor()
        raw_meta = {
            "doc_id": "cuk_doc_42",
            "title": "Tender Notice for Supply of Lab Equipment",
        }
        text = """
        CENTRAL UNIVERSITY OF KASHMIR
        NIT No. 02/CUK/2024
        Dated: 14-03-2024

        Tender document for laboratory instruments.

        Sd/-
        Registrar
        """
        enriched = extractor.enrich_document_metadata(raw_meta, text)

        assert enriched["doc_id"] == "cuk_doc_42"
        assert enriched["reference_number"] == "NIT No. 02/CUK/2024"
        assert enriched["circular_number"] == "NIT No. 02/CUK/2024"
        assert enriched["notification_date"] == "2024-03-14"
        assert enriched["published_date"] == "2024-03-14"
        assert enriched["issuing_authority"] == "Registrar"

    def test_enrich_chunks(self) -> None:
        extractor = PdfFactExtractor()
        facts = PdfIntrinsicFacts(
            reference_number="F.No. CUK/Exam/2024/99",
            notification_date="2024-05-10",
            issuing_authority="Controller of Examinations",
        )

        chunker = HierarchicalChunker()
        markdown = "# Exam Timetable\n\nExam schedule for Semester 4.\n\n| Date | Subject |\n|---|---|\n| 15-05 | AI |"
        chunks = chunker.chunk_markdown("exam_doc_01", markdown)

        enriched_chunks = extractor.enrich_chunks(chunks, facts)

        assert len(enriched_chunks) == len(chunks)
        for chunk in enriched_chunks:
            assert isinstance(chunk, ChunkRecord)
            assert chunk.metadata["reference_number"] == "F.No. CUK/Exam/2024/99"
            assert chunk.metadata["notification_date"] == "2024-05-10"
            assert chunk.metadata["issuing_authority"] == "Controller of Examinations"
