"""Offline parser pipeline for CUK RAG assistant.

Transforms raw assets from data/raw/ via manifest.jsonl into
canonical, structured documents for ingestion.
"""

from __future__ import annotations

from cuk_assistant.ingestion.parse.pipeline import parse_manifest

__all__ = ["parse_manifest"]
