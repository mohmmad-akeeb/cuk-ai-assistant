"""Tests for normalise_url and cache_key — pure functions, no I/O."""

from __future__ import annotations

import hashlib

from cuk_assistant.core.http_cache import cache_key, normalise_url


class TestNormaliseUrl:
    # ── scheme and host ──────────────────────────────────────────────────────

    def test_scheme_lowercased(self) -> None:
        assert normalise_url("HTTPS://Example.COM/").startswith("https://")

    def test_host_lowercased(self) -> None:
        assert "example.com" in normalise_url("https://EXAMPLE.COM/")

    # ── default port stripping ───────────────────────────────────────────────

    def test_strips_default_https_port(self) -> None:
        assert "443" not in normalise_url("https://example.com:443/path")

    def test_strips_default_http_port(self) -> None:
        assert "80" not in normalise_url("http://example.com:80/path")

    def test_keeps_non_default_port(self) -> None:
        assert ":8080" in normalise_url("https://example.com:8080/path")

    def test_keeps_non_default_http_port(self) -> None:
        assert ":8888" in normalise_url("http://example.com:8888/path")

    # ── query string ─────────────────────────────────────────────────────────

    def test_query_params_sorted(self) -> None:
        a = normalise_url("https://example.com/p?z=1&a=2")
        b = normalise_url("https://example.com/p?a=2&z=1")
        assert a == b

    def test_query_params_order_irrelevant(self) -> None:
        urls = [
            "https://example.com/?c=3&a=1&b=2",
            "https://example.com/?b=2&c=3&a=1",
            "https://example.com/?a=1&b=2&c=3",
        ]
        normalised = {normalise_url(u) for u in urls}
        assert len(normalised) == 1

    # ── fragment removal ─────────────────────────────────────────────────────

    def test_fragment_removed(self) -> None:
        assert "#section" not in normalise_url("https://example.com/page#section")

    def test_fragment_does_not_affect_key(self) -> None:
        a = normalise_url("https://example.com/page#foo")
        b = normalise_url("https://example.com/page#bar")
        assert a == b

    # ── path ─────────────────────────────────────────────────────────────────

    def test_empty_path_becomes_slash(self) -> None:
        result = normalise_url("https://example.com")
        assert result.endswith("/") or "example.com/" in result

    def test_path_preserved(self) -> None:
        assert "/some/path" in normalise_url("https://example.com/some/path")

    # ── idempotency ───────────────────────────────────────────────────────────

    def test_idempotent(self) -> None:
        url = "https://example.com/path?b=2&a=1#frag"
        assert normalise_url(normalise_url(url)) == normalise_url(url)

    # ── same URL different representations → equal ───────────────────────────

    def test_equivalent_urls_equal(self) -> None:
        assert normalise_url("HTTPS://Example.COM:443/Path?B=2&A=1#frag") == normalise_url(
            "https://example.com/Path?A=1&B=2"
        )


class TestCacheKey:
    def test_returns_64_char_hex(self) -> None:
        key = cache_key("https://example.com/")
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_deterministic(self) -> None:
        url = "https://example.com/page?x=1"
        assert cache_key(url) == cache_key(url)

    def test_same_as_sha256_of_normalised(self) -> None:
        url = "HTTPS://Example.COM:443/page?b=1&a=2#frag"
        expected = hashlib.sha256(normalise_url(url).encode()).hexdigest()
        assert cache_key(url) == expected

    def test_different_urls_different_keys(self) -> None:
        assert cache_key("https://example.com/a") != cache_key("https://example.com/b")

    def test_equivalent_urls_same_key(self) -> None:
        a = cache_key("HTTPS://Example.COM:443/?z=1&a=2#frag")
        b = cache_key("https://example.com/?a=2&z=1")
        assert a == b
