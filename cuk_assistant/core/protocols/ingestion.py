"""Abstract protocols for ingestion normalization, reconciliation, and delta sync."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from cuk_assistant.schemas.metadata import DocumentMetadataUnion


@runtime_checkable
class ReconcilerProtocol(Protocol):
    """Protocol for two-tier metadata reconciliation engines."""

    def reconcile(
        self,
        tier1_record: dict[str, Any],
        tier2_facts: dict[str, Any] | None = None,
        raw_text: str | None = None,
    ) -> DocumentMetadataUnion:
        """Harmonize Tier 1 provenance with Tier 2 intrinsic facts."""
        ...


@runtime_checkable
class DeltaDetectorProtocol(Protocol):
    """Protocol for crawl verification and incremental delta change detection."""

    def evaluate_document(
        self,
        doc_id: str,
        content_hash: str,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> Any:
        """Evaluate document against known state and return delta record."""
        ...

    def detect_tombstones(
        self,
        active_doc_ids: set[str],
    ) -> list[Any]:
        """Detect documents present in registry but missing from active crawl set."""
        ...
