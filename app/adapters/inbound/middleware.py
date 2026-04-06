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
                (await self.app(scope, receive, send_wrapper),)
            finally:
                request_id_context.reset(token)
        else:
            await self.app(scope, receive, send)


def log_middleware_factory(app: Any) -> Any:
    """Create logging middleware for ASGI applications"""
    return RequestIDMiddleware(app)
