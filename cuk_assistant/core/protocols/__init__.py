"""Protocols package for abstract subsystem interfaces."""

from cuk_assistant.core.protocols.ingestion import (
    DeltaDetectorProtocol,
    ReconcilerProtocol,
)

__all__ = [
    "DeltaDetectorProtocol",
    "ReconcilerProtocol",
]
