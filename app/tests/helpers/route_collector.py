"""A stand-in ``rt`` that records each handler it registers — for tests that call a route
function's handlers directly, without an app.

It keeps ``RouteDecorator``'s promise as the real ``rt`` does: the decorator takes any
handler and hands back a callable of the same type (the real one forwards every call to
it). ``route_collector()`` returns it as a ``RouteDecorator``, so mypy checks that promise
here, where tests' disabled ``arg-type`` cannot see it at the call that hands it to a
route function.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar

from adapters.inbound.fasthtml_types import RouteDecorator

P = ParamSpec("P")
R = TypeVar("R")

# boundary: heterogeneous — each registered handler has its own parameters and return
RegisteredHandlers = dict[str, Callable[..., Any]]


def route_collector() -> tuple[RouteDecorator, RegisteredHandlers]:
    """An ``rt`` and the path → handler map it fills as a route function registers."""
    registered: RegisteredHandlers = {}

    def rt(
        path: str, methods: list[str] | None = None
    ) -> Callable[[Callable[P, R]], Callable[P, R]]:
        def register(handler: Callable[P, R]) -> Callable[P, R]:
            registered[path] = handler
            return handler

        return register

    return rt, registered
