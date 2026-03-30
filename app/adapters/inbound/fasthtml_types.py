"""
FastHTML Type Protocols
=======================

Centralized Protocol definitions for the FastHTML framework.

FastHTML does not publish type stubs. These Protocols capture the minimal interface
actually used by SKUEL's route factories and UI modules — enough for type checkers
and IDE autocomplete without attempting to model the full framework.

Boundary note: `app` and `rt` are created at runtime by FastHTML's `fast_app()`.
Their full type hierarchy (Starlette subclass, dynamic decorator) cannot be expressed
without maintaining complete FastHTML stubs. These protocols capture exactly what
SKUEL calls — nothing more.

Usage:
    from adapters.inbound.fasthtml_types import RouteDecorator, FastHTMLApp
"""

from typing import Any, Protocol


class RouteDecorator(Protocol):
    """
    Protocol for FastHTML's `rt` route decorator.

    FastHTML creates `rt` via `fast_app()`. It is a callable that:
    - Accepts a path string and an optional list of HTTP methods
    - Returns a decorator that registers the given handler function as a route

    Example:
        @rt("/api/tasks/create", methods=["POST"])
        async def create_task(request): ...
    """

    def __call__(self, path: str, methods: list[str] | None = None) -> Any: ...


class FastHTMLApp(Protocol):
    """
    Minimal protocol for the FastHTML application object.

    FastHTML's app object inherits from Starlette. SKUEL route factories receive it
    as a parameter but delegate all route registration to `rt`. This protocol exists
    to give the parameter a name that is not `Any`.

    Boundary note: FastHTML's app API is not stable enough to type fully without
    maintaining our own stubs. This protocol captures intent, not the full surface.
    """

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        """ASGI interface."""
        ...

    def get(self, path: str) -> Any:
        """Register a GET route handler (Starlette-style decorator)."""
        ...


class _HeadersLike(Protocol):
    """Protocol for request headers (Starlette's Headers)."""

    def get(self, key: str, default: str | None = None) -> str | None: ...


class _ClientLike(Protocol):
    """Protocol for request client info (Starlette's Address)."""

    host: str


class _URLLike(Protocol):
    """Protocol for request URL (Starlette's URL)."""

    path: str


class _FormDataLike(Protocol):
    """Protocol for Starlette's FormData (multidict with file upload support)."""

    def get(self, key: str, default: Any = None) -> Any: ...
    def getlist(self, key: str) -> list[Any]: ...
    def __getitem__(self, key: str) -> Any: ...


class Request(Protocol):
    """
    Protocol for Starlette/FastHTML request objects.

    Captures the fields that SKUEL route handlers actually access.
    FastHTML wraps Starlette's Request; using a Protocol here avoids importing
    Starlette directly and keeps the dependency lightweight.

    Note: ``session`` is intentionally omitted — it is middleware-injected,
    not part of the base Request.  Access via ``getattr(request, "session", None)``.
    """

    query_params: dict[str, str]
    headers: _HeadersLike
    method: str
    url: _URLLike
    path_params: dict[str, str]
    client: _ClientLike | None

    async def form(self) -> _FormDataLike: ...
    async def json(self) -> Any: ...


# Type alias for the return value of route factory functions.
# FastHTML route objects are internal implementation details — not exported.
# boundary: fasthtml-route-objects — FastHTML does not expose a Route type.
RouteList = list[Any]
