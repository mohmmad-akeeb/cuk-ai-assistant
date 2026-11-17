"""CUK Assistant FastAPI application package."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ApiErrorEnvelope(BaseModel):
    """Universal RFC 7807-compatible error envelope."""

    model_config = ConfigDict(extra="ignore")

    error_code: str = Field(..., description="Canonical diagnostic or HTTP error code")
    message: str = Field(..., description="User-safe descriptive explanation")
    trace_id: str = Field(..., description="32-character hex trace correlation UUID")
    details: dict[str, Any] = Field(default_factory=dict, description="Diagnostic error details")


__all__ = ["ApiErrorEnvelope"]
