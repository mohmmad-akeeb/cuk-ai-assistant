"""cuk_assistant/ingestion/parsers package.

Offline parsers transforming raw assets into structured dataclasses.
"""

from cuk_assistant.ingestion.parsers.api_parser import OfflineApiParser, ParsedApiRecord
from cuk_assistant.ingestion.parsers.base import BaseParser, LinkOut, ParsedHTML, ParsedPdf
from cuk_assistant.ingestion.parsers.html_parser import OfflineHtmlParser, parse_html
from cuk_assistant.ingestion.parsers.pdf_parser import OfflinePdfParser

__all__ = [
    "BaseParser",
    "LinkOut",
    "OfflineApiParser",
    "OfflineHtmlParser",
    "OfflinePdfParser",
    "ParsedApiRecord",
    "ParsedHTML",
    "ParsedPdf",
    "parse_html",
]
