"""Unit tests for DeltaDetector and incremental crawl verification."""

from __future__ import annotations

from pathlib import Path

from cuk_assistant.core.protocols.ingestion import DeltaDetectorProtocol
from cuk_assistant.ingestion.normalize.delta_detector import (
    DeltaDetector,
    DeltaStatus,
)


class TestDeltaDetectorProtocol:
    def test_protocol_conformance(self) -> None:
        detector = DeltaDetector()
        assert isinstance(detector, DeltaDetectorProtocol)


class TestDeltaEvaluation:
    """Test evaluation logic for NEW, UNCHANGED, and MODIFIED records."""

    def test_new_document_detection(self) -> None:
        detector = DeltaDetector()
        record = detector.evaluate_document(
            doc_id="doc_001",
            content_hash="hash_v1",
            etag='"etag-123"',
            last_modified="Wed, 21 Oct 2025 07:28:00 GMT",
        )
        assert record.doc_id == "doc_001"
        assert record.status == DeltaStatus.NEW
        assert record.content_hash == "hash_v1"
        assert record.previous_hash is None
        assert record.etag == '"etag-123"'
        assert "Newly discovered" in record.reason
        assert "doc_001" in detector.get_known_doc_ids()

    def test_unchanged_document_detection(self) -> None:
        detector = DeltaDetector()
        detector.evaluate_document(
            doc_id="doc_001",
            content_hash="hash_v1",
            etag='"etag-123"',
            last_modified="Wed, 21 Oct 2025 07:28:00 GMT",
        )

        record = detector.evaluate_document(
            doc_id="doc_001",
            content_hash="hash_v1",
            etag='"etag-123"',
            last_modified="Wed, 21 Oct 2025 07:28:00 GMT",
        )
        assert record.status == DeltaStatus.UNCHANGED
        assert record.previous_hash == "hash_v1"
        assert record.content_hash == "hash_v1"

    def test_unchanged_document_with_http_header_change(self) -> None:
        """When HTTP headers change but SHA-256 is identical, must return UNCHANGED."""
        detector = DeltaDetector()
        detector.evaluate_document(
            doc_id="doc_001",
            content_hash="hash_v1",
            etag='"etag-old"',
            last_modified="Wed, 21 Oct 2025 07:28:00 GMT",
        )

        record = detector.evaluate_document(
            doc_id="doc_001",
            content_hash="hash_v1",
            etag='"etag-new"',
            last_modified="Thu, 22 Oct 2025 09:00:00 GMT",
        )
        assert record.status == DeltaStatus.UNCHANGED
        assert record.etag == '"etag-new"'
        assert "HTTP headers changed but content hash is identical" in record.reason

    def test_modified_document_detection(self) -> None:
        detector = DeltaDetector()
        detector.evaluate_document(
            doc_id="doc_001",
            content_hash="hash_v1",
        )

        record = detector.evaluate_document(
            doc_id="doc_001",
            content_hash="hash_v2",
            etag='"etag-v2"',
        )
        assert record.status == DeltaStatus.MODIFIED
        assert record.content_hash == "hash_v2"
        assert record.previous_hash == "hash_v1"
        assert "Content hash changed" in record.reason


class TestTombstoneDetection:
    """Test detection of deleted/tombstoned documents missing from active crawl."""

    def test_tombstone_detection(self) -> None:
        detector = DeltaDetector()
        detector.evaluate_document(doc_id="doc_001", content_hash="hash_1")
        detector.evaluate_document(doc_id="doc_002", content_hash="hash_2")
        detector.evaluate_document(doc_id="doc_003", content_hash="hash_3")

        # Active crawl only encountered doc_001 and doc_003
        active_ids = {"doc_001", "doc_003"}
        tombstones = detector.detect_tombstones(active_ids)

        assert len(tombstones) == 1
        assert tombstones[0].doc_id == "doc_002"
        assert tombstones[0].status == DeltaStatus.TOMBSTONED
        assert tombstones[0].content_hash == "hash_2"
        assert "absent from active crawl" in tombstones[0].reason

    def test_no_tombstones_when_all_active(self) -> None:
        detector = DeltaDetector()
        detector.evaluate_document(doc_id="doc_001", content_hash="hash_1")
        detector.evaluate_document(doc_id="doc_002", content_hash="hash_2")

        tombstones = detector.detect_tombstones({"doc_001", "doc_002", "doc_003"})
        assert len(tombstones) == 0


class TestStateManagementAndPersistence:
    """Test state serialization, export/load, and file persistence."""

    def test_export_and_load_state(self) -> None:
        detector = DeltaDetector()
        detector.register("doc_a", "hash_a", etag="etag_a")
        detector.register("doc_b", "hash_b", last_modified="lm_b")

        exported = detector.export_state()
        assert "doc_a" in exported
        assert exported["doc_a"]["content_hash"] == "hash_a"

        new_detector = DeltaDetector(initial_registry=exported)
        assert new_detector.get_known_doc_ids() == {"doc_a", "doc_b"}
        assert new_detector.get_record("doc_a")["etag"] == "etag_a"

    def test_file_persistence_roundtrip(self, tmp_path: Path) -> None:
        state_file = tmp_path / "delta_state.json"
        detector = DeltaDetector()
        detector.evaluate_document("doc_100", "hash_100", etag="etag_100")
        detector.save_to_file(state_file)

        loaded_detector = DeltaDetector()
        loaded_detector.load_from_file(state_file)

        assert loaded_detector.get_known_doc_ids() == {"doc_100"}
        record = loaded_detector.get_record("doc_100")
        assert record is not None
        assert record["content_hash"] == "hash_100"
        assert record["etag"] == "etag_100"

    def test_remove_and_clear(self) -> None:
        detector = DeltaDetector()
        detector.register("doc_1", "hash_1")
        assert detector.remove("doc_1") is True
        assert detector.remove("doc_1") is False
        assert len(detector.get_known_doc_ids()) == 0

        detector.register("doc_2", "hash_2")
        detector.clear()
        assert len(detector.get_known_doc_ids()) == 0
