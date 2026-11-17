"""Polite, disk-cached async HTTP client.

Every outbound request goes through ``CachedClient``, which enforces:

* ≤ 1 request/second via a ``TokenBucket`` rate limiter
* ≤ 2 concurrent connections via an ``asyncio.Semaphore``
* Disk cache (SHA-256 of normalised URL → body + JSON sidecar)
* Conditional GET (If-None-Match / If-Modified-Since) on refresh
* Tenacity-based exponential back-off on 429 / 5xx
* Circuit breaker: raises ``CircuitBreakerError`` after N consecutive errors

Usage
-----
    async with CachedClient.from_settings(settings) as client:
        resp = await client.get("https://www.cukashmir.ac.in/")
        html = resp.body.decode()
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from tenacity import (
    RetryError,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class CircuitBreakerError(RuntimeError):
    """Raised when consecutive errors exceed the configured threshold."""


# ---------------------------------------------------------------------------
# URL normalizing function
# ---------------------------------------------------------------------------
def normalise_url(url: str) -> str:
    """Normalize a URL to ensure equivalent URLs produce the same cache key.

    - Parse the URL into scheme, host, port, path, query and fragment.
    - Convert the scheme and hostname to lowercase.
    - Remove default HTTP (80) and HTTPS (443) ports.
    - Sort query parameters alphabetically by name, then by value.
    - Preserve query parameters with empty values.
    - Encode query parameters consistently, using %20 for spaces.
    - Replace an empty path with '/'.
    - Remove the fragment identifier.
    - Reconstruct the URL using the normalized components.

    Example:
        Input:  https://EXAMPLE.com:443?b=2&c=""&a=1#section
        Output: https://example.com/?a=1&b=2&c=""
    """
    parsed = urllib.parse.urlparse(url)

    scheme = parsed.scheme.lower()
    host = parsed.hostname or ""
    port = parsed.port

    # Strip default ports
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        port = None

    netloc = host if port is None else f"{host}:{port}"

    # Sort query params for determinism
    qs = urllib.parse.urlencode(
        sorted(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)),
        quote_via=urllib.parse.quote,
    )

    path = parsed.path or "/"

    return urllib.parse.urlunparse((scheme, netloc, path, parsed.params, qs, ""))


def cache_key(url: str) -> str:
    """Return the SHA-256 hex digest of the normalised *url*."""
    return hashlib.sha256(normalise_url(url).encode()).hexdigest()


# ---------------------------------------------------------------------------
# Disk cache helpers
# ---------------------------------------------------------------------------


def _cache_paths(cache_dir: Path, key: str) -> tuple[Path, Path]:
    """Return (body_path, meta_path) for a given cache key.

    Files are stored under a two-character prefix sub-directory to avoid
    very large flat directories.
    """
    # sub-directory name - two-character prefix of hash string
    prefix = cache_dir / key[:2]
    return prefix / f"{key}.body", prefix / f"{key}.meta.json"


def _write_cache(
    cache_dir: Path, key: str, body: bytes, status: int, headers: dict[str, str], url: str
) -> None:
    body_path, meta_path = _cache_paths(cache_dir, key)
    body_path.parent.mkdir(parents=True, exist_ok=True)

    body_path.write_bytes(body)

    meta: dict[str, Any] = {
        "url": url,
        "status": status,
        "headers": headers,
        "fetched_at": datetime.now(tz=UTC).isoformat(),
        "etag": headers.get("etag") or headers.get("ETag"),
        "last_modified": headers.get("last-modified") or headers.get("Last-Modified"),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _read_cache(cache_dir: Path, key: str) -> CachedResponse | None:
    body_path, meta_path = _cache_paths(cache_dir, key)
    if not body_path.exists() or not meta_path.exists():
        return None

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        body = body_path.read_bytes()
        return CachedResponse(
            url=meta["url"],
            status=meta["status"],
            headers=meta.get("headers", {}),
            body=body,
            from_cache=True,
            fetched_at=datetime.fromisoformat(meta["fetched_at"]),
        )
    except Exception:
        logger.warning("Corrupt cache entry for key %s; will re-fetch", key)
        return None


def _update_meta_fetched_at(cache_dir: Path, key: str) -> None:
    """Touch fetched_at in the sidecar without re-downloading the body (304 case)."""
    _, meta_path = _cache_paths(cache_dir, key)
    if not meta_path.exists():
        return
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["fetched_at"] = datetime.now(tz=UTC).isoformat()
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    except Exception:
        pass  # non-fatal


# ---------------------------------------------------------------------------
# CachedResponse
# ---------------------------------------------------------------------------


@dataclass
class CachedResponse:
    url: str
    status: int
    headers: dict[str, str]
    body: bytes | None
    from_cache: bool
    fetched_at: datetime

    @property
    def is_redirect(self) -> bool:
        return self.status in (301, 302, 303, 307, 308)

    def text(self, encoding: str = "utf-8", errors: str = "replace") -> str:
        if self.body is None:
            return ""
        return self.body.decode(encoding, errors=errors)


# ---------------------------------------------------------------------------
# TokenBucket rate limiter
# ---------------------------------------------------------------------------


class TokenBucket:
    """Async token-bucket rate limiter.

    Calling ``acquire()`` blocks until one token is available.
    Tokens refill at *rate* per second (fractional seconds are fine).
    """

    def __init__(self, rate: float) -> None:
        if rate <= 0:
            raise ValueError(f"rate must be > 0, got {rate}")
        self.rate = rate
        self._tokens: float = 1.0  # start with one token so first call is instant
        self._last: float = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._tokens = min(1.0, self._tokens + elapsed * self.rate)
            self._last = now

            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return

            # Need to wait for the next token.
            # We stay inside the lock while sleeping so that subsequent callers
            # queue behind it.  When each one enters, self._last reflects the
            # real wake-up time of its predecessor, so elapsed is correct and
            # tokens refill properly — enforcing the rate limit under concurrency.
            wait = (1.0 - self._tokens) / self.rate
            self._tokens = 0.0
            self._last = now + wait
            await asyncio.sleep(wait)


# ---------------------------------------------------------------------------
# CachedClient
# ---------------------------------------------------------------------------


class CachedClient:
    """Polite async HTTP client with disk caching and circuit breaker."""

    def __init__(
        self,
        cache_dir: Path,
        user_agent: str,
        rate_limit_rps: float = 1.0,
        max_connections: int = 2,
        circuit_breaker_threshold: int = 5,
    ) -> None:
        self._cache_dir = cache_dir
        self._user_agent = user_agent
        self._bucket = TokenBucket(rate_limit_rps)
        self._semaphore = asyncio.Semaphore(max_connections)
        self._circuit_threshold = circuit_breaker_threshold
        self._consecutive_errors = 0
        self._client: httpx.AsyncClient | None = None

    # ── context manager ─────────────────────────────────────────────────────

    async def __aenter__(self) -> CachedClient:
        self._client = httpx.AsyncClient(
            headers={"User-Agent": self._user_agent},
            follow_redirects=False,
            timeout=httpx.Timeout(30.0),
        )
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @classmethod
    def from_settings(cls, settings: Any) -> CachedClient:
        """Construct from a ``Settings`` object (avoids importing config here)."""
        return cls(
            cache_dir=settings.cache_dir,
            user_agent=settings.user_agent,
            rate_limit_rps=settings.rate_limit_rps,
            max_connections=settings.max_connections,
            circuit_breaker_threshold=settings.circuit_breaker_threshold,
        )

    # ── public API ───────────────────────────────────────────────────────────

    async def get(self, url: str, *, force: bool = False) -> CachedResponse:
        """Fetch *url* via GET; return cached body on cache hit."""
        return await self._fetch(url, method="GET", force=force)

    async def head(self, url: str, *, force: bool = False) -> CachedResponse:
        """Fetch *url* via HEAD; cache the metadata (body=None)."""
        return await self._fetch(url, method="HEAD", force=force)

    # ── internals ────────────────────────────────────────────────────────────

    async def _fetch(self, url: str, *, method: str, force: bool) -> CachedResponse:
        if self._client is None:
            raise RuntimeError("CachedClient must be used as an async context manager.")

        key = cache_key(url)

        # ── cache hit (single read; reused below for conditional headers) ───
        existing = _read_cache(self._cache_dir, key)
        # For GET, don't serve a cache entry that has no body (written by a prior HEAD)
        if not force and existing is not None:
            if method == "GET" and not existing.body:
                existing = None  # force a real GET
            else:
                logger.debug("Cache hit", extra={"url": url, "key": key})
                return existing

        # ── build conditional request headers ───────────────────────────────
        extra_headers: dict[str, str] = {}
        if existing:
            if etag := existing.headers.get("etag") or existing.headers.get("ETag"):
                extra_headers["If-None-Match"] = etag
            if lm := (
                existing.headers.get("last-modified") or existing.headers.get("Last-Modified")
            ):
                extra_headers["If-Modified-Since"] = lm

        # ── send (with retry + back-off) ─────────────────────────────────────
        try:
            resp = await self._send_with_retry(url, method=method, headers=extra_headers)
        except (RetryError, httpx.HTTPError) as exc:
            self._consecutive_errors += 1
            logger.error(
                "Request failed",
                extra={"url": url, "error": str(exc), "consecutive": self._consecutive_errors},
            )
            if self._consecutive_errors >= self._circuit_threshold:
                raise CircuitBreakerError(
                    f"Circuit breaker tripped after {self._consecutive_errors} "
                    f"consecutive errors (last URL: {url})"
                ) from exc
            raise

        # ── 304 Not Modified ─────────────────────────────────────────────────
        if resp.status_code == 304:
            if existing:
                _update_meta_fetched_at(self._cache_dir, key)
                logger.debug("304 Not Modified — serving from cache", extra={"url": url})
                existing.from_cache = True
                return existing
            # Cache was deleted between our read and the server's 304 response;
            # fall through to re-fetch without conditional headers.
            logger.warning(
                "304 received but no cached entry found — will re-fetch without "
                "conditional headers",
                extra={"url": url},
            )
            try:
                resp = await self._send_with_retry(url, method=method, headers={})
            except (RetryError, httpx.HTTPError) as exc:
                self._consecutive_errors += 1
                if self._consecutive_errors >= self._circuit_threshold:
                    raise CircuitBreakerError(
                        f"Circuit breaker tripped after {self._consecutive_errors} "
                        f"consecutive errors (last URL: {url})"
                    ) from exc
                raise

        # ── success ──────────────────────────────────────────────────────────
        self._consecutive_errors = 0
        headers_dict = dict(resp.headers)
        body = resp.content if method == "GET" else None

        _write_cache(
            self._cache_dir,
            key,
            body if body is not None else b"",
            resp.status_code,
            headers_dict,
            url,
        )

        return CachedResponse(
            url=url,
            status=resp.status_code,
            headers=headers_dict,
            body=body,
            from_cache=False,
            fetched_at=datetime.now(tz=UTC),
        )

    async def _send_with_retry(
        self,
        url: str,
        *,
        method: str,
        headers: dict[str, str],
    ) -> httpx.Response:
        """Send one HTTP request; retry on 429 / 5xx with exponential back-off."""

        def _is_retryable(exc: BaseException) -> bool:
            if isinstance(exc, httpx.HTTPStatusError):
                return exc.response.status_code in (429, 500, 502, 503, 504)
            if isinstance(exc, _RetryableStatusError):
                return True
            return isinstance(exc, (httpx.TimeoutException, httpx.ConnectError))

        @retry(
            retry=retry_if_exception(_is_retryable),
            wait=wait_exponential(multiplier=1, min=1, max=30),
            stop=stop_after_attempt(3),
            reraise=True,
        )
        async def _attempt() -> httpx.Response:
            await self._bucket.acquire()
            async with self._semaphore:
                logger.info("Fetching", extra={"method": method, "url": url})
                r = await self._client.request(method, url, headers=headers)  # type: ignore[union-attr]

                # Raise for 429 / 5xx so tenacity can retry
                if r.status_code == 429:
                    retry_after = int(r.headers.get("retry-after", "60"))
                    logger.warning(
                        "429 Too Many Requests — waiting %ds", retry_after, extra={"url": url}
                    )
                    await asyncio.sleep(retry_after)
                    raise _RetryableStatusError(f"429 from {url}")

                if r.status_code >= 500:
                    raise _RetryableStatusError(f"HTTP {r.status_code} from {url}")

                return r

        return await _attempt()


# ---------------------------------------------------------------------------
# Internal sentinel exception for retryable HTTP status codes
# ---------------------------------------------------------------------------


class _RetryableStatusError(Exception):
    """Signals tenacity to retry on a specific HTTP status code."""
