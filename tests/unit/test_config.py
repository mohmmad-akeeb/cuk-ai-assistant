"""Tests for cuk_assistant.core.config — no network calls, no real .env file."""

from __future__ import annotations

from pathlib import Path

import pytest

from cuk_assistant.core.config import Settings, load_settings

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load(monkeypatch: pytest.MonkeyPatch, extra: dict[str, str] | None = None) -> Settings:
    """Load settings with a minimal env, skipping any on-disk .env."""
    for key in (
        "BASE_URL",
        "RATE_LIMIT_RPS",
        "MAX_CONNECTIONS",
        "CIRCUIT_BREAKER_THRESHOLD",
        "MAX_PDF_BYTES",
        "LOG_LEVEL",
        "CACHE_DIR",
        "RAW_DIR",
        "PROCESSED_DIR",
        "LOGS_DIR",
        "REPORTS_DIR",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CONTACT_EMAIL", "test@example.com")
    for k, v in (extra or {}).items():
        monkeypatch.setenv(k, v)
    # Pass a non-existent path so load_dotenv is a no-op.
    return load_settings(env_file=Path("/nonexistent/.env"))


# ---------------------------------------------------------------------------
# CONTACT_EMAIL is required
# ---------------------------------------------------------------------------


class TestContactEmailRequired:
    def test_missing_raises_value_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CONTACT_EMAIL", raising=False)
        with pytest.raises(ValueError, match="CONTACT_EMAIL"):
            load_settings(env_file=Path("/nonexistent/.env"))

    def test_present_does_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = _load(monkeypatch)
        assert s.contact_email == "test@example.com"


# ---------------------------------------------------------------------------
# User-Agent contains the email
# ---------------------------------------------------------------------------


class TestUserAgent:
    def test_email_substituted_in_ua(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = _load(monkeypatch)
        assert "test@example.com" in s.user_agent

    def test_ua_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = _load(monkeypatch)
        assert s.user_agent.startswith("CUK-RAG-assistant/0.1")

    def test_custom_email_reflected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CONTACT_EMAIL", "other@uni.ac.in")
        s = load_settings(env_file=Path("/nonexistent/.env"))
        assert "other@uni.ac.in" in s.user_agent


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


class TestDefaults:
    def test_base_url_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = _load(monkeypatch)
        assert s.base_url == "https://www.cukashmir.ac.in"

    def test_rate_limit_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = _load(monkeypatch)
        assert s.rate_limit_rps == 1.0

    def test_max_connections_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = _load(monkeypatch)
        assert s.max_connections == 2

    def test_circuit_breaker_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = _load(monkeypatch)
        assert s.circuit_breaker_threshold == 5

    def test_max_pdf_bytes_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = _load(monkeypatch)
        assert s.max_pdf_bytes == 20 * 1024 * 1024

    def test_log_level_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = _load(monkeypatch)
        assert s.log_level == "INFO"


# ---------------------------------------------------------------------------
# Overrides via env vars
# ---------------------------------------------------------------------------


class TestOverrides:
    def test_base_url_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = _load(monkeypatch, {"BASE_URL": "https://staging.example.com"})
        assert s.base_url == "https://staging.example.com"

    def test_rate_limit_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = _load(monkeypatch, {"RATE_LIMIT_RPS": "0.5"})
        assert s.rate_limit_rps == 0.5

    def test_log_level_uppercased(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = _load(monkeypatch, {"LOG_LEVEL": "debug"})
        assert s.log_level == "DEBUG"


# ---------------------------------------------------------------------------
# Paths are absolute and exist
# ---------------------------------------------------------------------------


class TestPaths:
    def test_paths_are_absolute(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = _load(monkeypatch)
        for attr in (
            "cache_dir",
            "processed_dir",
            "logs_dir",
            "reports_dir",
        ):
            p: Path = getattr(s, attr)
            assert p.is_absolute(), f"{attr} should be absolute, got {p}"

    def test_paths_exist(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = _load(monkeypatch)
        for attr in (
            "cache_dir",
            "processed_dir",
            "logs_dir",
            "reports_dir",
        ):
            p: Path = getattr(s, attr)
            assert p.exists(), f"{attr} directory should have been created: {p}"

    def test_log_file_derived(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = _load(monkeypatch)
        assert s.log_file == s.logs_dir / "crawl.jsonl"

    def test_custom_cache_dir(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        custom = tmp_path / "my_cache"
        s = _load(monkeypatch, {"CACHE_DIR": str(custom)})
        # When the path is absolute it should be used as-is.
        assert s.cache_dir == custom
        assert s.cache_dir.exists()

    def test_settings_is_frozen(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = _load(monkeypatch)
        with pytest.raises((AttributeError, TypeError)):
            s.base_url = "mutated"  # type: ignore[misc]
