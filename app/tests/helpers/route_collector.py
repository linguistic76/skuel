"""The one stand-in ``rt``: it records each handler a route function registers, by the door
the handler answers — for tests that call a route function's handlers directly, without an
app.

``route_collector()`` returns the ``rt`` and the ``RegisteredHandlers`` it fills. A test
looks a handler up by its door, ``registered["/api/tasks/create", "POST"]``. A path alone is
not a door: one handler can answer GET and POST, and two handlers can share a path. So a
lookup that names no method, or names a method the path does not answer, fails loudly
instead of handing back a handler.

The methods recorded are FastHTML's own: ``methods`` given → each, uppercased; none → the
verb a handler is named for (``get``, ``post``, …), else GET and POST. That is
``fasthtml.core._add_route``'s rule, read through the same two names it reads
(``all_meths``, ``nested_name``); ``tests/unit/test_route_collector.py`` holds the doors
against a real ``fast_app()``'s router. Starlette answers HEAD for every GET route on its
own; that is an answer, not a registration, and is not recorded.

The ``rt`` keeps ``RouteDecorator``'s promise as the real one does: its decorator takes any
handler and hands back a callable of the same type. ``route_collector()`` returns it as a
``RouteDecorator``, so mypy checks that promise here. Tests run with ``arg-type`` disabled,
so the call that hands a stand-in to a route function is checked nowhere.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from typing import Any, ParamSpec, TypeVar

from fasthtml.core import all_meths, nested_name

from adapters.inbound.fasthtml_types import RouteDecorator

P = ParamSpec("P")
R = TypeVar("R")

#: A door: the path a handler is registered at and one method it answers there, uppercased.
Door = tuple[str, str]

# boundary: heterogeneous — each registered handler has its own parameters and return
Handler = Callable[..., Any]

_METHODS = frozenset(meth.upper() for meth in all_meths)


def registered_methods(handler: Handler, methods: list[str] | None) -> list[str]:
    """The methods FastHTML registers ``handler`` under, uppercased, in its order."""
    if methods:
        return [method.upper() for method in methods]
    name = nested_name(handler)
    if name in all_meths:
        return [name.upper()]
    return ["GET", "POST"]


def _door(key: object) -> Door:
    """``key`` as a door, or a refusal that says how a handler is looked up."""
    if isinstance(key, tuple) and len(key) == 2 and isinstance(key[0], str) and key[1] in _METHODS:
        return key[0], key[1]
    raise TypeError(
        f"look a handler up by its door, registered[path, METHOD] with METHOD one of "
        f"{sorted(_METHODS)} — not {key!r}"
    )


class RegisteredHandlers(Mapping[Door, Handler]):
    """The handlers a route function registered, keyed by the door each answers."""

    def __init__(self) -> None:
        self._handlers: dict[Door, Handler] = {}

    def register(self, path: str, methods: list[str], handler: Handler) -> None:
        """Record ``handler`` at each of its doors; a door already taken refuses."""
        for method in methods:
            if (path, method) in self._handlers:
                raise ValueError(
                    f"{method} {path} is registered twice: in the app, the first handler "
                    f"answers and the second is never reached"
                )
            self._handlers[path, method] = handler

    def methods(self, path: str) -> set[str]:
        """Every method registered at ``path``."""
        return {method for door_path, method in self._handlers if door_path == path}

    def __getitem__(self, key: Door) -> Handler:
        path, method = _door(key)
        try:
            return self._handlers[path, method]
        except KeyError:
            answered = sorted(self.methods(path)) or "nothing"
            raise KeyError(f"no {method} {path} registered; that path answers {answered}") from None

    def __contains__(self, key: object) -> bool:
        return _door(key) in self._handlers

    def __iter__(self) -> Iterator[Door]:
        return iter(self._handlers)

    def __len__(self) -> int:
        return len(self._handlers)


def route_collector() -> tuple[RouteDecorator, RegisteredHandlers]:
    """An ``rt`` and the doors it fills as a route function registers."""
    registered = RegisteredHandlers()

    def rt(
        path: str, methods: list[str] | None = None
    ) -> Callable[[Callable[P, R]], Callable[P, R]]:
        def register(handler: Callable[P, R]) -> Callable[P, R]:
            registered.register(path, registered_methods(handler, methods), handler)
            return handler

        return register

    return rt, registered
