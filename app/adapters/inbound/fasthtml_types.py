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

# Re-export the concrete Starlette Request class.
# FastHTML resolves route-handler type annotations at runtime and instantiates
# the annotated class (anno(**cargs)).  A Protocol cannot be instantiated, so
# route handlers MUST annotate with the real class.  Re-exporting here keeps
# all imports centralized through the hexagonal boundary.
from starlette.requests import Request as Request


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

    # Starlette router — FastHTML's @rt registers HTTP routes only, so
    # WebSocket endpoints mount here directly (see device_routes.py /ws/agent).
    # boundary: fasthtml-app — starlette Router, untyped through FastHTML.
    router: Any

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        """ASGI interface."""
        ...

    def get(self, path: str) -> Any:
        """Register a GET route handler (Starlette-style decorator)."""
        ...

    def add_exception_handler(self, exc_class_or_status_code: Any, handler: Any) -> None:
        """Register a Starlette exception handler (see boundary.install_malformed_json_guard)."""
        ...
