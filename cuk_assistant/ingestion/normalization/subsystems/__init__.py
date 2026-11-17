from cuk_assistant.ingestion.normalization.subsystems.aggregator import aggregate_asset_references
from cuk_assistant.ingestion.normalization.subsystems.delta_detector import DeltaDetector
from cuk_assistant.ingestion.normalization.subsystems.metadata_normalizer import (
    MetadataNormalizer,
    clean_guid,
    extract_batch_year,
    extract_circular_reference,
    extract_course_code,
    normalize_academic_year,
    normalize_iso_date,
    normalize_title,
)
from cuk_assistant.ingestion.normalization.subsystems.pipeline import parse_manifest
from cuk_assistant.ingestion.normalization.subsystems.reconciler import TwoTierReconciler
from cuk_assistant.ingestion.normalization.subsystems.sanitizer import Sanitizer, scrub_pii
