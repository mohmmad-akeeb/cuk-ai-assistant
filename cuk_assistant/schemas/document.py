"""Canonical Document schema for ingestion and RAG pipeline.

Zero external database/vendor dependencies. Guarantees immutable contract
for documents persisted to documents.jsonl and fed into retrieval/chunking.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Document(BaseModel):
    """Canonical document representation written to documents.jsonl."""

    model_config = ConfigDict(extra="ignore")

    text: str = Field(..., description="Clean textual or markdown content")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Document metadata")


__all__ = ["Document"]
