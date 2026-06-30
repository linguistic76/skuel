"""
ASGI Middleware for SKUEL
=========================

Web framework middleware that belongs in the adapter layer, not in core utilities.
"""

import time
from typing import Any

from core.utils.logging import generate_request_id, get_logger, request_id_context

logger = get_logger("skuel.middleware.timing")

# Paths to skip timing (static assets, health checks)
_SKIP_PREFIXES = ("/static/", "/favicon", "/manifest", "/service-worker")


class RequestTimingMiddleware:
    """ASGI middleware to log request duration for performance diagnosis."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if any(path.startswith(p) for p in _SKIP_PREFIXES):
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status_code = 0

        async def send_wrapper(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message.get("status", 0)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            method = scope.get("method", "?")
            if elapsed_ms > 100:
                logger.warning(
                    "SLOW %s %s → %d in %.0fms",
                    method,
                    path,
                    status_code,
                    elapsed_ms,
                )
            else:
                logger.info(
                    "%s %s → %d in %.0fms",
                    method,
                    path,
                    status_code,
                    elapsed_ms,
                )


class RequestIDMiddleware:
    """ASGI middleware to inject request IDs for log correlation"""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            # Generate unique request ID
            request_id = generate_request_id()

            # Set in context for this request
            token = request_id_context.set(request_id)

            # Add to response headers for debugging
            async def send_wrapper(message: dict[str, Any]) -> None:
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append([b"x-request-id", request_id.encode()])
                    message["headers"] = headers
                await send(message)

            try:
                await self.app(scope, receive, send_wrapper)
            finally:
                request_id_context.reset(token)
        else:
            await self.app(scope, receive, send)


class StaticCacheHeadersMiddleware:
    """ASGI middleware that forces browser revalidation of static assets.

    FastHTML serves static files via a catch-all route that emits ETag but no
    Cache-Control. Without Cache-Control, browsers apply *heuristic* caching and
    can serve a stale asset WITHOUT revalidating against the server — which once
    hid a fixed ``skuel.js`` behind a cached broken (infinite-looping) version,
    so the page kept running the old script even after the server restarted.

    ``Cache-Control: no-cache`` forces the browser to revalidate on every load,
    so it always receives the real current asset and can never be stuck on a
    stale copy. Applied as middleware (not a StaticFiles subclass) because
    FastHTML's catch-all route — not the Starlette mount — is what actually serves
    ``/static/*``.

    NOTE: deliberately blunt but always-correct, with a known inefficiency:
    FastHTML's static route emits an ETag but does NOT honor ``If-None-Match``,
    so revalidation re-downloads the full body (200) rather than returning a cheap
    304. A smarter scheme (immutable long-lived caching for version-stamped vendor
    assets, content hashing + 304 for app assets) is a planned follow-up — see
    TECHNICAL_DEBT.md item 11, the TODO at the static mount in
    ``scripts/dev/bootstrap.py``, and memory
    ``project_lucide_mutationobserver_infinite_loop``.
    """

    _STATIC_PREFIX = "/static/"

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith(self._STATIC_PREFIX):
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                if not any(key.lower() == b"cache-control" for key, _ in headers):
                    headers.append((b"cache-control", b"no-cache"))
                    message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


def log_middleware_factory(app: Any) -> Any:
    """Create logging middleware for ASGI applications"""
    return RequestIDMiddleware(app)
