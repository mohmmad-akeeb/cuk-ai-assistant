"""cuk_assistant/schemas/chunks.py

Hierarchical chunk schemas with parent-child pointer graph.
"""

import hashlib
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChunkType(StrEnum):
    """Taxonomy of structural chunk blocks."""

    PARAGRAPH = "paragraph"
    MARKDOWN_TABLE = "markdown_table"
    HEADING = "heading"
    LIST_ITEM = "list_item"
    CODE_OR_FORMULA = "code_or_formula"


class ChunkRecord(BaseModel):
    """Normalized chunk representation passed across internal interfaces."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: str = Field(..., description="Deterministic chunk hash: {doc_id}::c{chunk_index}")
    doc_id: str = Field(..., description="Parent document identifier")
    chunk_index: int = Field(..., description="Sequential position within document (0-indexed)")
    chunk_type: ChunkType = Field(..., description="Structural classification")
    text_content: str = Field(..., description="Clean text or Markdown table")
    token_count: int = Field(..., description="Estimated token count")
    text: str | None = Field(default=None, description="Direct text alias for text_content")
    content_hash: str | None = Field(
        default=None, description="Deterministic content hash of text_content"
    )
    page_number: int = Field(default=1, description="Physical 1-indexed page number")
    start_line: int | None = Field(default=None)
    end_line: int | None = Field(default=None)
    table_bbox: list[float] | None = Field(default=None)
    section_heading: str | None = Field(default=None)
    heading_path: list[str] = Field(
        default_factory=list, description="Breadcrumb hierarchy of headings"
    )
    parent_chunk_id: str | None = Field(
        default=None, description="Parent section container chunk ID"
    )
    prev_chunk_id: str | None = Field(default=None)
    next_chunk_id: str | None = Field(default=None)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _fill_text_and_hash(cls, data: Any) -> Any:
        if isinstance(data, dict):
            d = dict(data)
            tc = d.get("text_content")
            t = d.get("text")
            if tc is None and t is not None:
                d["text_content"] = t
                tc = t
            elif t is None and tc is not None:
                d["text"] = tc
            if not d.get("content_hash"):
                raw = d.get("text_content") or d.get("text") or ""
                d["content_hash"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            return d
        return data


class ParentChunkContainer(BaseModel):
    """Parent Section Context Model.

    Stored in LanceDB parent_sections table; retrieved in O(1) to expand top-5 child chunks.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    parent_chunk_id: str = Field(
        ...,
        description="Deterministic parent section fingerprint ({doc_id}::p{parent_index})",
    )
    doc_id: str = Field(
        ...,
        description="Parent document identifier",
    )
    heading_title: str = Field(
        ...,
        description="Section heading text",
    )
    heading_level: int = Field(
        ...,
        ge=1,
        le=6,
        description="Markdown heading level (1 for #, 2 for ##, etc.)",
    )
    section_token_count: int = Field(
        ...,
        description="Cumulative token count of the entire section container",
    )
    full_section_text: str = Field(
        ...,
        description="Complete section markdown text spanning all child paragraphs and tables",
    )
    child_chunk_ids: list[str] = Field(
        default_factory=list,
        description="Ordered list of child Chunk.chunk_id belonging to this section",
    )


# Alias for compatibility
Chunk = ChunkRecord

__all__ = [
    "Chunk",
    "ChunkRecord",
    "ChunkType",
    "ParentChunkContainer",
]
