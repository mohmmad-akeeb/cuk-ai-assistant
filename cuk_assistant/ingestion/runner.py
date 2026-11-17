"""cuk_assistant/ingestion/runner.py

Ingestion pipeline orchestration runner.
Transforms canonical Document records from documents.jsonl into hierarchical,
parent-child ChunkRecords written atomically to chunks.jsonl.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cuk_assistant.ingestion.chunking.hierarchical_chunker import HierarchicalChunker
from cuk_assistant.ingestion.parsers.subsystems.pdf_fact_extractor import PdfFactExtractor
from cuk_assistant.schemas.chunks import ChunkRecord, ChunkType

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionStats:
    """Metrics and statistics for the ingestion pipeline execution."""

    total_documents: int
    total_chunks: int
    parent_sections: int
    table_chunks: int
    duration_seconds: float
    errors: int


class IngestionPipelineRunner:
    """Orchestrates document reading, fact extraction, hierarchical chunking, and atomic output."""

    def __init__(
        self,
        chunker: HierarchicalChunker | None = None,
        fact_extractor: PdfFactExtractor | None = None,
    ) -> None:
        # Default ~120 tokens yields ~300-500 characters for child chunks
        self.chunker = chunker or HierarchicalChunker(
            target_chunk_tokens=120,
            max_chunk_tokens=180,
            token_overlap=25,
        )
        self.fact_extractor = fact_extractor or PdfFactExtractor()

    def process_document(self, doc_data: dict[str, Any]) -> list[ChunkRecord]:
        """Process a single document record into enriched ChunkRecord instances."""
        text = str(doc_data.get("text") or "").strip()
        if not text:
            return []

        raw_meta = dict(doc_data.get("metadata") or {})
        doc_id = str(raw_meta.get("doc_id") or "")
        if not doc_id:
            logger.warning("Document record missing doc_id; skipping.")
            return []

        doc_title = str(raw_meta.get("title") or "Document")

        # 1. Enrich document metadata with intrinsic facts
        enriched_meta = self.fact_extractor.enrich_document_metadata(
            raw_meta, text, title=doc_title
        )

        # 2. Ensure layout-aware section heading hierarchy exists
        # Prepend a root title heading if text has no heading markers
        prepared_text = text
        if not text.startswith("#"):
            prepared_text = f"# {doc_title}\n\n{text}"

        # 3. Perform hierarchical AST chunking
        chunks = self.chunker.chunk_markdown(
            doc_id=doc_id,
            markdown_text=prepared_text,
            base_metadata=enriched_meta,
        )

        # If after chunking child chunks have no parent_chunk_id (e.g. if root header was missing),
        # guarantee link to the document's primary root chunk
        root_chunk_id = chunks[0].chunk_id if chunks else None
        adjusted_chunks: list[ChunkRecord] = []
        for c in chunks:
            if c.chunk_type != ChunkType.HEADING and not c.parent_chunk_id and root_chunk_id:
                # Ensure child chunk carries parent link
                c = c.model_copy(update={"parent_chunk_id": root_chunk_id})
            adjusted_chunks.append(c)

        return adjusted_chunks

    def run(
        self,
        documents_path: Path,
        output_chunks_path: Path,
        max_workers: int = 1,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> IngestionStats:
        """Stream documents from documents_path, chunk them, and atomically write chunks_path."""
        start_time = time.monotonic()

        if not documents_path.is_file():
            raise FileNotFoundError(f"Documents file not found: {documents_path}")

        output_chunks_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_output_path = output_chunks_path.with_suffix(".jsonl.tmp")

        total_documents = 0
        total_chunks = 0
        parent_sections = 0
        table_chunks = 0
        errors = 0

        # Count lines for accurate progress tracking if progress_callback is set
        total_lines = 0
        if progress_callback:
            with documents_path.open("r", encoding="utf-8") as f:
                for _ in f:
                    total_lines += 1

        with (
            documents_path.open("r", encoding="utf-8") as in_f,
            tmp_output_path.open("w", encoding="utf-8") as out_f,
        ):
            for line_idx, line in enumerate(in_f):
                line = line.strip()
                if not line:
                    continue

                total_documents += 1
                try:
                    doc_data = json.loads(line)
                    chunks = self.process_document(doc_data)

                    for chunk in chunks:
                        total_chunks += 1
                        if chunk.chunk_type == ChunkType.HEADING:
                            parent_sections += 1
                        elif chunk.chunk_type == ChunkType.MARKDOWN_TABLE:
                            table_chunks += 1

                        # Serialize chunk conforming to ChunkRecord schema
                        dumped = chunk.model_dump()
                        out_f.write(json.dumps(dumped, ensure_ascii=False) + "\n")

                except Exception as exc:
                    logger.warning("Error processing document at line %d: %s", line_idx + 1, exc)
                    errors += 1

                if progress_callback and total_lines > 0:
                    progress_callback(total_documents, total_lines)

        # Atomic rename
        os.replace(tmp_output_path, output_chunks_path)

        duration = time.monotonic() - start_time
        return IngestionStats(
            total_documents=total_documents,
            total_chunks=total_chunks,
            parent_sections=parent_sections,
            table_chunks=table_chunks,
            duration_seconds=duration,
            errors=errors,
        )


__all__ = [
    "IngestionPipelineRunner",
    "IngestionStats",
]
