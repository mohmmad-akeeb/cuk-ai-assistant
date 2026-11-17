"""Shim re-exporting from cuk_assistant.ingestion.collector.subsystems.client for backward compatibility."""

from cuk_assistant.ingestion.collector.subsystems.client import (
    _API_HEADERS,
    API_BASE,
    DirectApiClient,
    _payload_suffix,
    _sanitize_guid,
    _unpack_list,
    download_pdf_cached,
)

__all__ = [
    "API_BASE",
    "DirectApiClient",
    "_API_HEADERS",
    "_payload_suffix",
    "_sanitize_guid",
    "_unpack_list",
    "download_pdf_cached",
]
