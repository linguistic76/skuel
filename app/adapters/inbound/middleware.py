"""
ASGI Middleware for SKUEL
=========================

Web framework middleware that belongs in the adapter layer, not in core utilities.
"""

import time
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

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
    TECHNICAL_DEBT.md item 11 and the TODO at the static mount in
    ``scripts/dev/bootstrap.py``.
    """

    _STATIC_PREFIX = "/static/"

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith(self._STATIC_PREFIX):
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                if not any(key.lower() == b"cache-control" for key, _ in headers):
                    headers.append((b"cache-control", b"no-cache"))
                    message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


class SecurityHeadersMiddleware:
    """ASGI middleware that stamps browser security headers on every response.

    Public-facing hardening (security-hardening-deferred roadmap item 7):

    - ``X-Frame-Options: DENY`` — SKUEL is never embedded in a frame.
    - ``X-Content-Type-Options: nosniff`` — no MIME sniffing.
    - ``Referrer-Policy: strict-origin-when-cross-origin`` — no path leakage
      to external origins.
    - ``Permissions-Policy`` — journals records audio, so ``microphone=(self)``;
      camera/geolocation are never used and are denied outright.
    - ``Content-Security-Policy-Report-Only`` — observe-first CSP. All assets
      are self-hosted (vendored Alpine/HTMX/Lucide under /static), but Alpine
      evaluates ``x-data`` expressions (``unsafe-eval``) and FastHTML pages
      carry inline scripts/styles (``unsafe-inline``), so the policy starts in
      report-only mode; promote to enforcing only after the console stays clean.

    HSTS is deliberately absent — TLS termination (and therefore HSTS) is
    Caddy's job at the edge, not the app's.

    Registered in ``main.py`` as the OUTERMOST ASGI wrapper, not via
    ``add_middleware`` — that would sit inside Starlette's
    ServerErrorMiddleware and leave unhandled-exception 500s unstamped
    (Codex #794).

    Existing headers are never overwritten (mirrors StaticCacheHeadersMiddleware).
    """

    _HEADERS: tuple[tuple[bytes, bytes], ...] = (
        (b"x-frame-options", b"DENY"),
        (b"x-content-type-options", b"nosniff"),
        (b"referrer-policy", b"strict-origin-when-cross-origin"),
        (b"permissions-policy", b"microphone=(self), camera=(), geolocation=()"),
        (
            b"content-security-policy-report-only",
            b"default-src 'self'; "
            b"script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            b"style-src 'self' 'unsafe-inline'; "
            b"img-src 'self' data: blob:; "
            b"font-src 'self' data:; "
            b"connect-src 'self'; "
            b"frame-ancestors 'none'; "
            b"base-uri 'self'; "
            b"form-action 'self'",
        ),
    )

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {key.lower() for key, _ in headers}
                for key, value in self._HEADERS:
                    if key not in present:
                        headers.append((key, value))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)
