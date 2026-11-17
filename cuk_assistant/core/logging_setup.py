"""Structured JSON-lines logging for the CUK exploration toolkit.

Every log record is written as a single JSON object on one line to
``data/logs/explore.jsonl``.  A human-readable handler is also attached to
stderr so the user can watch progress in the terminal.

Usage
-----
    from cuk_assistant.core.logging_setup import setup_logging
    from cuk_assistant.core.config import load_settings

    settings = load_settings()
    setup_logging(settings)

After that, every module uses the standard ``logging`` API:

    import logging
    logger = logging.getLogger(__name__)
    logger.info("Fetching", extra={"url": url, "method": "GET"})
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# JSON-lines handler
# ---------------------------------------------------------------------------


class JsonLinesHandler(logging.Handler):
    """Writes one JSON object per log record to a .jsonl file.

    The JSON object always contains:
        level, logger, message, timestamp (ISO-8601 UTC)

    Any key/value pairs passed via ``extra={...}`` are merged in at the
    top level, so callers can attach structured context without embedding
    it in the message string.
    """

    def __init__(self, path: Path) -> None:
        super().__init__()
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        # Open in append mode so restarts don't overwrite previous runs.
        self._file = path.open("a", encoding="utf-8")

    def emit(self, record: logging.LogRecord) -> None:
        try:
            record_dict: dict[str, Any] = {
                "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            }

            # Merge any extra fields the caller injected.
            # LogRecord stores caller-supplied extras as direct attributes;
            # we pull them out by diffing against the standard attribute set.
            for key, value in record.__dict__.items():
                if key not in _STANDARD_LOG_ATTRS and not key.startswith("_"):
                    record_dict[key] = value

            if record.exc_info:
                record_dict["exc_info"] = self.formatException(record.exc_info)

            self._file.write(json.dumps(record_dict, default=str) + "\n")
            self._file.flush()
        except Exception:  # noqa: BLE001
            self.handleError(record)

    def close(self) -> None:
        self._file.close()
        super().close()


# Standard LogRecord attributes we do NOT want to re-emit as extra fields.
_STANDARD_LOG_ATTRS: frozenset[str] = frozenset(
    {
        "args",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


# ---------------------------------------------------------------------------
# Public setup function
# ---------------------------------------------------------------------------

_configured = False  # guard against double-initialisation


def setup_logging(log_file: Path, level: str = "INFO") -> None:
    """Configure root logger with a JSON-lines file handler + stderr handler.

    Safe to call multiple times; subsequent calls are no-ops unless
    *force=True* is added in future.

    Parameters
    ----------
    log_file:
        Absolute path to the ``.jsonl`` file (parent dirs created if needed).
    level:
        Log level string, e.g. ``"INFO"``, ``"DEBUG"``.
    """
    global _configured
    if _configured:
        return
    _configured = True

    numeric_level = getattr(logging, level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(numeric_level)

    # Remove any handlers pytest or the import machinery already attached.
    root.handlers.clear()

    # ── JSON-lines file handler ──────────────────────────────────────────────
    file_handler = JsonLinesHandler(log_file)
    file_handler.setLevel(numeric_level)
    root.addHandler(file_handler)

    # ── Human-readable stderr handler ───────────────────────────────────────
    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(numeric_level)
    stderr_handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root.addHandler(stderr_handler)

    # Silence noisy third-party loggers at WARNING unless we're in DEBUG.
    for noisy in ("httpx", "httpcore", "playwright", "asyncio"):
        logging.getLogger(noisy).setLevel(
            logging.DEBUG if numeric_level == logging.DEBUG else logging.WARNING
        )
