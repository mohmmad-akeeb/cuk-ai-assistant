"""cuk_assistant/schemas/llm.py

Structured LLM generation schemas.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class AnswerWithCitations(BaseModel):
    """Mandatory structured output returned by all generative LLM adapters."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    direct_answer: str = Field(..., description="Direct factual synthesized response")
    quoted_snippets: list[str] = Field(
        default_factory=list,
        description="Exact verbatim substrings extracted from context chunks",
    )
    citation_chunk_ids: list[str] = Field(
        default_factory=list,
        description="List of chunk_ids backing the quoted snippets",
    )
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Model self-reported confidence",
    )


__all__ = ["AnswerWithCitations"]
