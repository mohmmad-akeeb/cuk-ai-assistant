"""CLI entrypoints package."""

from cuk_assistant.ingestion.cli.crawl import app as crawl_app
from cuk_assistant.ingestion.cli.ingest import app as ingest_app
from cuk_assistant.ingestion.cli.parse import app as parse_app

__all__ = ["crawl_app", "ingest_app", "parse_app"]
