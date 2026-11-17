"""Sliding-window IP rate limiter middleware for FastAPI.

Governed by NFR-4.2, FR-7.2, and docs/api_contracts.md Section 3.
Enforces hourly request quotas per client IP (20 req/hour for guest, 100 req/hour for institutional).
"""

from __future__ import annotations

import hashlib
import threading
import time
import uuid
from collections import defaultdict, deque
from typing import Any

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from cuk_assistant.api import ApiErrorEnvelope

DEFAULT_EXEMPT_PATHS: set[str] = {
    "/api/v1/health",
    "/health",
    "/health/ready",
    "/api/v1/menu/starter",
    "/docs",
    "/openapi.json",
    "/redoc",
}


class RateLimiterMiddleware:
    """Sliding-window IP rate limiter ASGI middleware."""

    def __init__(
        self,
        app: ASGIApp,
        max_requests: int = 20,
        window_seconds: int = 3600,
        exempt_paths: set[str] | None = None,
    ) -> None:
        self.app = app
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.exempt_paths = exempt_paths if exempt_paths is not None else DEFAULT_EXEMPT_PATHS
        self._requests: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def reset(self) -> None:
        """Reset rate limiter state (used in test fixtures)."""
        with self._lock:
            self._requests.clear()

    def _extract_ip(self, scope: Scope) -> str:
        """Extract remote client IP from headers or ASGI client tuple."""
        headers = Headers(scope=scope)
        x_forwarded_for = headers.get("x-forwarded-for")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        client = scope.get("client")
        if client and client[0]:
            return str(client[0])
        return "127.0.0.1"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        # Check exemption for health, starter menu, and docs
        if any(path == p or path.startswith(f"{p}/") for p in self.exempt_paths):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        user_email = headers.get("x-user-email", "")
        auth_header = headers.get("authorization", "")
        is_institutional = user_email.endswith("@cukashmir.ac.in") or bool(auth_header)
        limit = 100 if is_institutional else self.max_requests

        client_ip = self._extract_ip(scope)
        now = time.monotonic()
        cutoff = now - self.window_seconds
        trace_id = uuid.uuid4().hex

        with self._lock:
            timestamps = self._requests[client_ip]
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()

            if len(timestamps) >= limit:
                oldest = timestamps[0]
                retry_after = max(1, int(oldest + self.window_seconds - now))
                ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()

                envelope = ApiErrorEnvelope(
                    error_code="RATE_LIMIT_EXCEEDED",
                    message="Hourly query quota exceeded for unauthenticated client.",
                    trace_id=trace_id,
                    details={
                        "ip_hash": ip_hash,
                        "limit": limit,
                        "window": "1 hour",
                        "retry_after_seconds": retry_after,
                    },
                )

                response = JSONResponse(
                    status_code=429,
                    content=envelope.model_dump(),
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": "0",
                    },
                )
                await response(scope, receive, send)
                return

            timestamps.append(now)
            remaining = max(0, limit - len(timestamps))

        async def send_wrapper(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                resp_headers = list(message.get("headers", []))
                resp_headers.append((b"x-ratelimit-limit", str(limit).encode()))
                resp_headers.append((b"x-ratelimit-remaining", str(remaining).encode()))
                message["headers"] = resp_headers
            await send(message)

        await self.app(scope, receive, send_wrapper)
