"""Metadata normalization, two-tier reconciliation, and delta sync utilities."""

from typing import Any

from cuk_assistant.ingestion.normalization.subsystems.aggregator import aggregate_asset_references
from cuk_assistant.ingestion.normalization.subsystems.delta_detector import (
    DeltaDetector,
    DeltaRecord,
    DeltaStatus,
)
from cuk_assistant.ingestion.normalization.subsystems.metadata_normalizer import (
    clean_guid,
    extract_batch_year,
    extract_circular_reference,
    extract_course_code,
    normalize_academic_year,
    normalize_iso_date,
    normalize_semester,
    normalize_title,
)
from cuk_assistant.ingestion.normalization.subsystems.reconciler import TwoTierReconciler
from cuk_assistant.ingestion.normalization.subsystems.sanitizer import (
    mask_email,
    sanitize_record_dict,
    scrub_dob,
    scrub_phone_numbers,
    scrub_pii,
    scrub_roll_numbers,
)


def __getattr__(name: str) -> Any:
    if name in ("ParseStats", "parse_manifest"):
        from cuk_assistant.ingestion.normalization.subsystems.pipeline import ParseStats, parse_manifest

        if name == "ParseStats":
            return ParseStats
        return parse_manifest
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "DeltaDetector",
    "DeltaRecord",
    "DeltaStatus",
    "ParseStats",
    "TwoTierReconciler",
    "aggregate_asset_references",
    "clean_guid",
    "extract_batch_year",
    "extract_circular_reference",
    "extract_course_code",
    "mask_email",
    "normalize_academic_year",
    "normalize_iso_date",
    "normalize_semester",
    "normalize_title",
    "parse_manifest",
    "sanitize_record_dict",
    "scrub_dob",
    "scrub_phone_numbers",
    "scrub_pii",
    "scrub_roll_numbers",
]
