"""Crawl verification and incremental delta sync detection.

Tracks document content hashes (SHA-256) and HTTP cache validators (ETag, Last-Modified)
to detect newly discovered, modified, unchanged, and tombstoned documents (FR-1.6).
"""

from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DeltaStatus(StrEnum):
    """Categorical synchronization state of an ingested document."""

    NEW = "NEW"
    MODIFIED = "MODIFIED"
    UNCHANGED = "UNCHANGED"
    TOMBSTONED = "TOMBSTONED"


class DeltaRecord(BaseModel):
    """Immutable audit record representing a synchronization delta evaluation."""

    model_config = ConfigDict(frozen=True)

    doc_id: str = Field(..., description="Unique document identifier")
    status: DeltaStatus = Field(..., description="Evaluation outcome status")
    reason: str = Field(..., description="Human-readable rationale for assigned status")
    content_hash: str = Field(..., description="Current evaluated SHA-256 content hash")
    previous_hash: str | None = Field(
        default=None, description="Previously known content hash if document existed"
    )
    etag: str | None = Field(default=None, description="HTTP ETag validator header")
    last_modified: str | None = Field(
        default=None, description="HTTP Last-Modified validator header"
    )


class DeltaDetector:
    """Incremental Delta Detection & Sync Engine.

    Maintains a thread-safe in-memory or persisted index of known document hashes
    and HTTP headers to eliminate redundant vectorization and table updates.
    """

    def __init__(
        self,
        initial_registry: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._registry: dict[str, dict[str, Any]] = {}
        if initial_registry:
            self.load_state(initial_registry)

    def evaluate_document(
        self,
        doc_id: str,
        content_hash: str,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> DeltaRecord:
        """Evaluate a document candidate against the known document registry.

        Args:
            doc_id: Deterministic document identifier.
            content_hash: Extracted clean text SHA-256 hash.
            etag: Optional HTTP ETag header string.
            last_modified: Optional HTTP Last-Modified header string.

        Returns:
            DeltaRecord with DeltaStatus (NEW, UNCHANGED, or MODIFIED).
        """
        clean_doc_id = str(doc_id).strip()
        clean_hash = str(content_hash).strip()
        clean_etag = str(etag).strip() if etag else None
        clean_lm = str(last_modified).strip() if last_modified else None

        if clean_doc_id not in self._registry:
            # Newly discovered document
            self._registry[clean_doc_id] = {
                "content_hash": clean_hash,
                "etag": clean_etag,
                "last_modified": clean_lm,
            }
            return DeltaRecord(
                doc_id=clean_doc_id,
                status=DeltaStatus.NEW,
                reason="Newly discovered document not present in registry",
                content_hash=clean_hash,
                previous_hash=None,
                etag=clean_etag,
                last_modified=clean_lm,
            )

        known = self._registry[clean_doc_id]
        prev_hash = str(known.get("content_hash", "")).strip()
        prev_etag = known.get("etag")
        prev_lm = known.get("last_modified")

        if clean_hash == prev_hash:
            # Content is identical
            if (clean_etag and clean_etag != prev_etag) or (clean_lm and clean_lm != prev_lm):
                reason = "HTTP headers changed but content hash is identical"
                # Update headers in registry
                if clean_etag:
                    known["etag"] = clean_etag
                if clean_lm:
                    known["last_modified"] = clean_lm
            else:
                reason = "Content hash and HTTP headers match existing record"

            return DeltaRecord(
                doc_id=clean_doc_id,
                status=DeltaStatus.UNCHANGED,
                reason=reason,
                content_hash=clean_hash,
                previous_hash=prev_hash,
                etag=clean_etag or prev_etag,
                last_modified=clean_lm or prev_lm,
            )

        # Content hash differs -> Document was updated
        self._registry[clean_doc_id] = {
            "content_hash": clean_hash,
            "etag": clean_etag,
            "last_modified": clean_lm,
        }
        return DeltaRecord(
            doc_id=clean_doc_id,
            status=DeltaStatus.MODIFIED,
            reason=f"Content hash changed from {prev_hash} to {clean_hash}",
            content_hash=clean_hash,
            previous_hash=prev_hash,
            etag=clean_etag,
            last_modified=clean_lm,
        )

    def detect_tombstones(self, active_doc_ids: set[str]) -> list[DeltaRecord]:
        """Detect indexed documents missing from the current active crawl set.

        Args:
            active_doc_ids: Set of document IDs encountered during the current crawl.

        Returns:
            List of DeltaRecord instances marked with DeltaStatus.TOMBSTONED.
        """
        clean_active = {str(d).strip() for d in active_doc_ids}
        tombstones: list[DeltaRecord] = []

        for doc_id, meta in sorted(self._registry.items()):
            if doc_id not in clean_active:
                h = meta.get("content_hash", "")
                tombstones.append(
                    DeltaRecord(
                        doc_id=doc_id,
                        status=DeltaStatus.TOMBSTONED,
                        reason="Document absent from active crawl set",
                        content_hash=h,
                        previous_hash=h,
                        etag=meta.get("etag"),
                        last_modified=meta.get("last_modified"),
                    )
                )

        return tombstones

    def register(
        self,
        doc_id: str,
        content_hash: str,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> None:
        """Seed or directly register a document state without triggering delta evaluation."""
        self._registry[str(doc_id).strip()] = {
            "content_hash": str(content_hash).strip(),
            "etag": str(etag).strip() if etag else None,
            "last_modified": str(last_modified).strip() if last_modified else None,
        }

    def remove(self, doc_id: str) -> bool:
        """Remove a document from registry (e.g. after purging tombstone)."""
        clean_id = str(doc_id).strip()
        if clean_id in self._registry:
            del self._registry[clean_id]
            return True
        return False

    def get_known_doc_ids(self) -> set[str]:
        """Return all tracked document IDs."""
        return set(self._registry.keys())

    def get_record(self, doc_id: str) -> dict[str, Any] | None:
        """Retrieve stored metadata for a document ID."""
        rec = self._registry.get(str(doc_id).strip())
        return dict(rec) if rec else None

    def export_state(self) -> dict[str, dict[str, Any]]:
        """Export registry state as a dictionary."""
        return {k: dict(v) for k, v in self._registry.items()}

    def load_state(self, state: dict[str, dict[str, Any]]) -> None:
        """Load registry state from dictionary."""
        for doc_id, data in state.items():
            self._registry[str(doc_id).strip()] = {
                "content_hash": str(data.get("content_hash", "")).strip(),
                "etag": str(data.get("etag")).strip() if data.get("etag") else None,
                "last_modified": str(data.get("last_modified")).strip()
                if data.get("last_modified")
                else None,
            }

    def clear(self) -> None:
        """Reset the internal registry."""
        self._registry.clear()

    def save_to_file(self, file_path: Path | str) -> None:
        """Persist registry state to a JSON file."""
        p = Path(file_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8") as f:
            json.dump(self.export_state(), f, indent=2)

    def load_from_file(self, file_path: Path | str) -> None:
        """Load registry state from a JSON file."""
        p = Path(file_path)
        if not p.is_file():
            raise FileNotFoundError(f"State file not found: {file_path}")
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        self.load_state(data)
