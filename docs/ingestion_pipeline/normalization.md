# Ingestion Normalization

The normalization subsystem reconciles metadata and detects changes (deltas) in the ingested content.

## Architectural Design
- Uses `ReconcilerProtocol` for metadata reconciliation.
- Uses `DeltaDetectorProtocol` for incremental synchronization.
- Decouples logic into subsystems (aggregator, reconciler, delta detector, sanitizer).

## Key Components
- `cuk_assistant/core/protocols/ingestion.py`: Defines the `ReconcilerProtocol` and `DeltaDetectorProtocol`.
- `cuk_assistant/ingestion/normalization/subsystems/reconciler.py`: Implements metadata harmonization.

- `cuk_assistant/ingestion/normalization/subsystems/delta_detector.py`: Implements incremental detection logic.

---

## Related Documentation
- [System Requirements](../requirements.md)
- [System Architecture](../architecture.md)
