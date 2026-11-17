"""Shim re-exporting from cuk_assistant.ingestion.parsers.html_parser."""

from cuk_assistant.ingestion.parsers.html_parser import (
    LinkOut,
    OfflineHtmlParser,
    ParsedHTML,
    parse_html,
)

__all__ = ["LinkOut", "OfflineHtmlParser", "ParsedHTML", "parse_html"]
