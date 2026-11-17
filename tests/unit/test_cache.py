"""Tests for CachedClient disk-cache behaviour — no real network calls.

Uses httpx's built-in MockTransport to intercept requests.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from cuk_assistant.core.http_cache import (
    CachedClient,
    CachedResponse,
    _cache_paths,
    _read_cache,
    _write_cache,
    cache_key,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

UA = "TestAgent/1.0"
TEST_URL = "https://example.com/page"
TEST_BODY = b"<html>hello</html>"


def _make_client(tmp_path: Path, responses: list[httpx.Response]) -> CachedClient:
    """Build a CachedClient backed by a mock transport."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        resp = responses[min(call_count, len(responses) - 1)]
        call_count += 1
        return resp

    client = CachedClient(
        cache_dir=tmp_path / "cache",
        user_agent=UA,
        rate_limit_rps=100.0,  # effectively no rate limit in tests
        max_connections=10,
        circuit_breaker_threshold=5,
    )
    # Inject mock transport
    client._client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        headers={"User-Agent": UA},
        follow_redirects=False,
    )
    return client


# ---------------------------------------------------------------------------
# _write_cache / _read_cache round-trip
# ---------------------------------------------------------------------------


class TestCacheReadWrite:
    def test_round_trip(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "cache"
        key = cache_key(TEST_URL)
        headers = {"content-type": "text/html", "etag": '"abc123"'}

        _write_cache(cache_dir, key, TEST_BODY, 200, headers, TEST_URL)
        result = _read_cache(cache_dir, key)

        assert result is not None
        assert result.body == TEST_BODY
        assert result.status == 200
        assert result.headers["etag"] == '"abc123"'
        assert result.from_cache is True

    def test_missing_returns_none(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "cache"
        assert _read_cache(cache_dir, "nonexistent" * 4) is None

    def test_body_stored_under_prefix_dir(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "cache"
        key = cache_key(TEST_URL)
        _write_cache(cache_dir, key, TEST_BODY, 200, {}, TEST_URL)
        body_path, _ = _cache_paths(cache_dir, key)
        assert body_path.exists()
        assert body_path.parent.name == key[:2]

    def test_corrupt_meta_returns_none(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "cache"
        key = cache_key(TEST_URL)
        _write_cache(cache_dir, key, TEST_BODY, 200, {}, TEST_URL)
        _, meta_path = _cache_paths(cache_dir, key)
        meta_path.write_text("{ broken json", encoding="utf-8")
        assert _read_cache(cache_dir, key) is None


# ---------------------------------------------------------------------------
# CachedClient.get — cache hit / miss
# ---------------------------------------------------------------------------


class TestCachedClientGet:
    @pytest.mark.asyncio
    async def test_first_call_hits_network(self, tmp_path: Path) -> None:
        responses = [httpx.Response(200, content=TEST_BODY)]
        client = _make_client(tmp_path, responses)

        resp = await client.get(TEST_URL)
        assert resp.status == 200
        assert resp.body == TEST_BODY
        assert resp.from_cache is False

    @pytest.mark.asyncio
    async def test_second_call_hits_cache(self, tmp_path: Path) -> None:
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, content=TEST_BODY)

        client = CachedClient(
            cache_dir=tmp_path / "cache",
            user_agent=UA,
            rate_limit_rps=100.0,
            max_connections=10,
            circuit_breaker_threshold=5,
        )
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            headers={"User-Agent": UA},
            follow_redirects=False,
        )

        await client.get(TEST_URL)
        resp2 = await client.get(TEST_URL)

        assert call_count == 1  # second call served from cache
        assert resp2.from_cache is True
        assert resp2.body == TEST_BODY

    @pytest.mark.asyncio
    async def test_force_bypasses_cache(self, tmp_path: Path) -> None:
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(200, content=TEST_BODY)

        client = CachedClient(
            cache_dir=tmp_path / "cache",
            user_agent=UA,
            rate_limit_rps=100.0,
            max_connections=10,
            circuit_breaker_threshold=5,
        )
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            headers={"User-Agent": UA},
            follow_redirects=False,
        )

        await client.get(TEST_URL)
        await client.get(TEST_URL, force=True)  # should hit network again

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_conditional_get_headers_sent(self, tmp_path: Path) -> None:
        """If cached entry has ETag, If-None-Match must be sent on next fetch."""
        sent_headers: list[dict[str, str]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            sent_headers.append(dict(request.headers))
            return httpx.Response(200, content=TEST_BODY, headers={"ETag": '"v1"'})

        client = CachedClient(
            cache_dir=tmp_path / "cache",
            user_agent=UA,
            rate_limit_rps=100.0,
            max_connections=10,
            circuit_breaker_threshold=5,
        )
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            headers={"User-Agent": UA},
            follow_redirects=False,
        )

        # First fetch — populates cache with ETag
        await client.get(TEST_URL)
        # Second fetch forced — should send If-None-Match
        await client.get(TEST_URL, force=True)

        assert len(sent_headers) == 2
        assert "if-none-match" in sent_headers[1] or "If-None-Match" in sent_headers[1]

    @pytest.mark.asyncio
    async def test_304_serves_cached_body(self, tmp_path: Path) -> None:
        call_count = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(200, content=TEST_BODY, headers={"ETag": '"v1"'})
            return httpx.Response(304, content=b"")

        client = CachedClient(
            cache_dir=tmp_path / "cache",
            user_agent=UA,
            rate_limit_rps=100.0,
            max_connections=10,
            circuit_breaker_threshold=5,
        )
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            headers={"User-Agent": UA},
            follow_redirects=False,
        )

        await client.get(TEST_URL)
        resp = await client.get(TEST_URL, force=True)

        assert resp.body == TEST_BODY
        assert resp.from_cache is True


# ---------------------------------------------------------------------------
# HEAD method
# ---------------------------------------------------------------------------


class TestCachedClientHead:
    @pytest.mark.asyncio
    async def test_head_returns_no_body(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"", headers={"Content-Length": "42"})

        client = CachedClient(
            cache_dir=tmp_path / "cache",
            user_agent=UA,
            rate_limit_rps=100.0,
            max_connections=10,
            circuit_breaker_threshold=5,
        )
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            headers={"User-Agent": UA},
            follow_redirects=False,
        )

        resp = await client.head(TEST_URL)
        assert resp.status == 200
        assert resp.body is None or resp.body == b""


# ---------------------------------------------------------------------------
# CachedResponse helpers
# ---------------------------------------------------------------------------


class TestCachedResponse:
    def test_text_decodes_body(self) -> None:
        resp = CachedResponse(
            url=TEST_URL,
            status=200,
            headers={},
            body=b"hello world",
            from_cache=False,
            fetched_at=datetime.now(tz=UTC),
        )
        assert resp.text() == "hello world"

    def test_text_none_body(self) -> None:
        resp = CachedResponse(
            url=TEST_URL,
            status=200,
            headers={},
            body=None,
            from_cache=False,
            fetched_at=datetime.now(tz=UTC),
        )
        assert resp.text() == ""

    def test_is_redirect_true(self) -> None:
        for status in (301, 302, 303, 307, 308):
            resp = CachedResponse(
                url=TEST_URL,
                status=status,
                headers={},
                body=None,
                from_cache=False,
                fetched_at=datetime.now(tz=UTC),
            )
            assert resp.is_redirect, f"Expected {status} to be a redirect"

    def test_is_redirect_false(self) -> None:
        resp = CachedResponse(
            url=TEST_URL,
            status=200,
            headers={},
            body=None,
            from_cache=False,
            fetched_at=datetime.now(tz=UTC),
        )
        assert not resp.is_redirect
