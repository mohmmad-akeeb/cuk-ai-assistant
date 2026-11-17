"""Thread-safe manifest manager for raw data lake assets.

Appends asset metadata entries to data/raw/manifest.jsonl.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class ManifestEntry:
    """Record describing a raw lake asset in data/raw/."""

    asset_id: str
    asset_type: str  # "html", "api_json", "pdf"
    source_url: str
    local_path: str
    scraped_at: str = field(default_factory=_utc_now_iso)
    provenance: dict[str, Any] = field(default_factory=dict)
    raw_meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ManifestWriter:
    """Thread-safe writer for data/raw/manifest.jsonl."""

    def __init__(self, manifest_path: Path) -> None:
        self.manifest_path = manifest_path
        self._lock = threading.Lock()
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, entry: ManifestEntry | dict[str, Any]) -> None:
        """Atomically append a single manifest entry."""
        data = entry.to_dict() if isinstance(entry, ManifestEntry) else entry
        line = json.dumps(data, ensure_ascii=False) + "\n"
        with self._lock, self.manifest_path.open("a", encoding="utf-8") as f:
            f.write(line)

    def append_batch(self, entries: list[ManifestEntry | dict[str, Any]]) -> None:
        """Atomically append multiple entries."""
        if not entries:
            return
        lines = [
            json.dumps(e.to_dict() if isinstance(e, ManifestEntry) else e, ensure_ascii=False)
            + "\n"
            for e in entries
        ]
        with self._lock, self.manifest_path.open("a", encoding="utf-8") as f:
            f.writelines(lines)


__all__ = [
    "ManifestEntry",
    "ManifestWriter",
]
