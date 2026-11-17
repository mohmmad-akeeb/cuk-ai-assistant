"""Settings for the CUK assistant.

All values are read from environment variables (and an optional .env file).
No literals are scattered through the rest of the codebase.

Usage
-----
    from cuk_assistant.core.config import load_settings

    settings = load_settings()
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


def _project_root() -> Path:
    """Return the project root (the directory that contains pyproject.toml)."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


def _resolve(base: Path, rel: str) -> Path:
    """Resolve *rel* against *base*, creating the directory if needed."""
    p = (base / rel).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _env(key: str, default: str | None = None) -> str:
    value = os.environ.get(key, default)
    if value is None:
        raise ValueError(
            f"Required environment variable '{key}' is not set. "
            f"Copy .env.example to .env and fill in the value."
        )
    return value


@dataclass(frozen=True)
class Settings:
    """All tuneable values for the CUK assistant."""

    # ── identity ─────────────────────────────────────────────────────────────
    base_url: str
    contact_email: str
    user_agent: str

    # ── politeness ───────────────────────────────────────────────────────────
    rate_limit_rps: float
    max_connections: int
    circuit_breaker_threshold: int

    # ── size limits ───────────────────────────────────────────────────────────
    max_pdf_bytes: int

    # ── paths (all absolute) ─────────────────────────────────────────────────
    project_root: Path
    cache_dir: Path  # data/cache  — HTTP response cache
    processed_dir: Path  # data/processed — final documents.jsonl
    logs_dir: Path  # data/logs
    reports_dir: Path  # reports/

    # ── logging ───────────────────────────────────────────────────────────────
    log_level: str

    # ── derived & raw lakehouse ───────────────────────────────────────────────
    log_file: Path = field(init=False)
    raw_dir: Path = field(default_factory=lambda: Path("data/raw"))

    def __post_init__(self) -> None:
        object.__setattr__(self, "log_file", self.logs_dir / "crawl.jsonl")
        if not self.raw_dir.is_absolute():
            object.__setattr__(self, "raw_dir", (self.project_root / self.raw_dir).resolve())


def load_settings(env_file: Path | None = None) -> Settings:
    """Load settings from environment (and optional .env file)."""
    root = _project_root()

    if env_file is None:
        env_file = root / ".env"
    if env_file and Path(env_file).exists():
        load_dotenv(env_file, override=False)

    contact_email = _env("CONTACT_EMAIL")
    base_url = _env("BASE_URL", "https://www.cukashmir.ac.in")
    rate_limit_rps = float(_env("RATE_LIMIT_RPS", "1.0"))
    max_connections = int(_env("MAX_CONNECTIONS", "2"))
    circuit_breaker_threshold = int(_env("CIRCUIT_BREAKER_THRESHOLD", "5"))
    max_pdf_bytes = int(_env("MAX_PDF_BYTES", str(20 * 1024 * 1024)))
    log_level = _env("LOG_LEVEL", "INFO").upper()

    cache_dir = _resolve(root, _env("CACHE_DIR", "data/cache"))
    raw_dir = _resolve(root, _env("RAW_DIR", "data/raw"))
    processed_dir = _resolve(root, _env("PROCESSED_DIR", "data/processed"))
    logs_dir = _resolve(root, _env("LOGS_DIR", "data/logs"))
    reports_dir = _resolve(root, _env("REPORTS_DIR", "reports"))

    user_agent = f"CUK-RAG-assistant/0.1 (student project; contact: {contact_email})"

    return Settings(
        base_url=base_url,
        contact_email=contact_email,
        user_agent=user_agent,
        rate_limit_rps=rate_limit_rps,
        max_connections=max_connections,
        circuit_breaker_threshold=circuit_breaker_threshold,
        max_pdf_bytes=max_pdf_bytes,
        project_root=root,
        cache_dir=cache_dir,
        raw_dir=raw_dir,
        processed_dir=processed_dir,
        logs_dir=logs_dir,
        reports_dir=reports_dir,
        log_level=log_level,
    )
