"""
ASGI Middleware for SKUEL
=========================

Web framework middleware that belongs in the adapter layer, not in core utilities.
"""

from typing import Any

from core.utils.logging import generate_request_id, request_id_context


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
