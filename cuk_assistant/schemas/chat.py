"""cuk_assistant/schemas/chat.py

Pure Pydantic v2 data models for conversational chat, user feedback,
interactive citation cards, and turn results.
Governed by PROJECT.md:55, docs/requirements.md, and docs/api_contracts.md.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FeedbackRequest(BaseModel):
    """Payload for user thumbs up/down reaction."""

    model_config = ConfigDict(extra="ignore")

    trace_id: str = Field(..., description="Trace identifier for the rated dialogue turn")
    message_id: str | None = Field(default=None, description="Optional message identifier")
    score: int = Field(..., description="Rating score: -1 for downvote, +1 for upvote")
    feedback_category: str | None = Field(default=None, description="Optional categorization")
    comment: str | None = Field(default=None, max_length=500, description="Optional feedback note")

    @field_validator("score")
    @classmethod
    def validate_score(cls, v: int) -> int:
        if v not in (-1, 1):
            raise ValueError("Score must be strictly -1 or 1.")
        return v


class ChatRequest(BaseModel):
    """Payload for conversational chat queries."""

    model_config = ConfigDict(extra="ignore")

    query: str | None = Field(default=None, description="User query prompt")
    message: str | None = Field(default=None, description="Alternative alias for query")
    session_id: str | None = Field(default=None, description="Conversation session UUID")
    slots: dict[str, Any] | None = Field(default=None, description="Pre-filled slot parameters")
    user_context: dict[str, Any] | None = Field(default=None, description="Client user context")

    @model_validator(mode="before")
    @classmethod
    def harmonize_fields(cls, values: Any) -> Any:
        if isinstance(values, dict):
            if not values.get("query") and values.get("message"):
                values["query"] = values["message"]
            elif not values.get("message") and values.get("query"):
                values["message"] = values["query"]
        return values


class ChatResponse(BaseModel):
    """Synchronous chat response model."""

    model_config = ConfigDict(extra="ignore")

    message_id: str
    session_id: str
    role: str = "assistant"
    content: str
    quick_replies: dict[str, Any] | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CitationCard(BaseModel):
    """Interactive citation card payload for side-by-side inspection."""

    model_config = ConfigDict(extra="ignore")

    citation_id: str = Field(..., description="Unique citation handle (e.g. cite_1)")
    doc_id: str = Field(..., description="Parent document identifier")
    chunk_id: str = Field(..., description="Specific chunk identifier")
    title: str = Field(..., description="Document title")
    source_url: str = Field(..., description="Public link to document")
    doc_type: str = Field(default="document", description="Document type classification")
    page_number: int = Field(default=1, description="1-indexed PDF or document page number")
    section_heading: str | None = Field(default=None, description="Section heading")
    quoted_snippet: str = Field(..., description="Verified verbatim excerpt from document")
    is_table: bool = Field(default=False, description="Flag indicating table content")
    table_markdown: str | None = Field(default=None, description="Markdown table if applicable")


class TurnResult(BaseModel):
    """Structured result of a completed RAG dialogue turn."""

    model_config = ConfigDict(extra="ignore")

    message_id: str
    session_id: str
    role: str = "assistant"
    content: str
    quick_replies: dict[str, Any] | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    diagnostic_code: str | None = None


__all__ = [
    "ChatRequest",
    "ChatResponse",
    "CitationCard",
    "FeedbackRequest",
    "TurnResult",
]
