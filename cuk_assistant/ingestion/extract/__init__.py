"""cuk_assistant/ingestion/extract/__init__.py

Layout-aware PDF parsing adapters and intrinsic document fact extractors.
"""

from cuk_assistant.ingestion.extract.docling_adapter import (
    DoclingAdapter,
    DoclingPdfParser,
)
from cuk_assistant.ingestion.extract.pdf_fact_extractor import (
    PdfFactExtractor,
    PdfIntrinsicFacts,
)

__all__ = [
    "DoclingAdapter",
    "DoclingPdfParser",
    "PdfFactExtractor",
    "PdfIntrinsicFacts",
]
