"""
FastHTML Type Protocols
=======================

Centralized Protocol definitions for the FastHTML framework.

FastHTML does not publish type stubs. These Protocols capture the minimal interface
actually used by SKUEL's route factories and UI modules — enough for type checkers
and IDE autocomplete without attempting to model the full framework.

Boundary note: `app` and `rt` are created at runtime by FastHTML's `fast_app()`,
which publishes no types. These protocols capture exactly what SKUEL calls — nothing
more — typed with Starlette's own types (`starlette.types`, `starlette.routing`).

Usage:
    from adapters.inbound.fasthtml_types import RouteDecorator, FastHTMLApp
"""

from collections.abc import Callable
from typing import ParamSpec, Protocol, TypeVar

from starlette.datastructures import State

# Re-export the concrete Starlette Request class.
# FastHTML resolves route-handler type annotations at runtime and instantiates
# the annotated class (anno(**cargs)).  A Protocol cannot be instantiated, so
# route handlers MUST annotate with the real class.  Re-exporting here keeps
# all imports centralized through the hexagonal boundary.
from starlette.requests import Request as Request
from starlette.responses import Response
from starlette.routing import Router
from starlette.types import Receive, Scope, Send

P = ParamSpec("P")
R = TypeVar("R")


class RouteDecorator(Protocol):
    """
    Protocol for FastHTML's `rt` route decorator.

    FastHTML creates `rt` via `fast_app()`. It is a callable that:
    - Accepts a path string and an optional list of HTTP methods
    - Returns a decorator that registers the given handler function as a route,
      and returns a callable that calls like the handler: same parameters, same
      return type

    What FastHTML hands back is its own wrapper (it forwards every call to the
    handler and also carries `.to()`, a `str()` of the path and `__wrapped__`);
    no SKUEL code reads those extras, so the protocol declares the call alone.
    `tests/unit/adapters/test_route_param_types.py` checks the forwarding
    against a real `fast_app()`.

    Example:
        @rt("/api/tasks/create", methods=["POST"])
        async def create_task(request): ...
    """

    def __call__(
        self, path: str, methods: list[str] | None = None
    ) -> Callable[[Callable[P, R]], Callable[P, R]]: ...


class FastHTMLApp(Protocol):
    """
    Minimal protocol for the FastHTML application object.

    FastHTML's app object inherits from Starlette. Route factories register their HTTP
    routes through `rt`; a function takes the app only to read one of the members
    below (or to hand it to a function that does) — `router` (the WebSocket endpoint
    `rt` cannot register), `state` (the lifespan's container) and
    `add_exception_handler`.

    Boundary note: FastHTML's app API is not stable enough to type fully without
    maintaining our own stubs. This protocol captures what SKUEL reads, not the full
    surface; `tests/unit/adapters/test_route_param_types.py` checks each member
    against a real `fast_app()`.
    """

    # Starlette router — FastHTML's @rt registers HTTP routes only, so
    # WebSocket endpoints mount here directly (see device_routes.py /ws/agent).
    router: Router

    # Starlette's attribute bag: bootstrap parks the app container, the services
    # and the embedding worker's task here; the lifespan and the integration
    # fixtures read them back.
    state: State

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI interface."""
        ...

    def add_exception_handler(
        self,
        exc_class_or_status_code: type[Exception] | int,
        handler: Callable[[Request, Exception], Response],
    ) -> None:
        """Register a Starlette exception handler (see boundary.install_malformed_body_guard).

        Starlette also accepts async handlers; this captures the sync form
        SKUEL actually registers.
        """
        ...
