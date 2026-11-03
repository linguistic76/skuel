"""Every route handler declares what it returns, and that is what FastHTML reads.

FastHTML evaluates a handler's signature as it registers the route (``_endp`` →
``signature_ex(f, True)``) and keeps it: a single ``Response``-class return annotation
makes it build that class from a returned value. This pin reads, for every route the
application registers, the signature FastHTML holds, and refuses a handler that declares
no return type, returns ``Any`` (alone or in a union) or returns ``Result[Any]``.

The routes come from the route catalog's real-app wiring (``scripts/health/route_catalog.py``
``runtime_routes``: the whole tree on a bare ``fast_app()``, every service a truthy mock,
so every tier's routes register). Reading the registration rather than the source covers
every way a route is registered (``@rt``, ``@self.rt``, ``rt(path)(handler)``) and every
wrapper between (``csrf_protected`` and ``boundary_handler`` keep ``__wrapped__``;
``require_role`` publishes the handler's signature minus the user it injects). The same
wiring raises the ``NameError`` a boot would on an annotation naming a ``TYPE_CHECKING``-only
name.

mypy checks each annotation against its handler's body; FT is a real type to it
(``typings/``), so ``-> Response`` over a returned ``Div()`` is refused there, not here.
"""

from __future__ import annotations

import importlib.util
import inspect
import sys
import textwrap
from collections.abc import Awaitable, Callable
from pathlib import Path
from types import UnionType
from typing import Any, NoReturn, Union, get_args, get_origin

import pytest
from fasthtml.common import FT, Div, fast_app

from adapters.inbound.auth import require_role
from adapters.inbound.fasthtml_types import Request
from core.models.enums import UserRole
from core.utils.result_simplified import Result
from ui.layouts.base_page import HtmlDocument

# scripts/health/ has no __init__.py — imported the way its own test imports it.
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts" / "health"))
import route_catalog  # type: ignore[import-not-found]


def fasthtml_signature(route: object) -> inspect.Signature | None:
    """The signature FastHTML evaluated when it registered ``route``'s handler.

    ``_endp`` closes over it as ``sig``; a route whose endpoint carries none (a
    WebSocket route) answers None.
    """
    endpoint = getattr(route, "endpoint", None)
    code = getattr(endpoint, "__code__", None)
    closure = getattr(endpoint, "__closure__", None)
    if code is None or closure is None or "sig" not in code.co_freevars:
        return None
    cells = dict(zip(code.co_freevars, closure, strict=True))
    signature = cells["sig"].cell_contents
    assert isinstance(signature, inspect.Signature)
    return signature


def return_defect(annotation: object) -> str | None:
    """Why a handler's return annotation says nothing, or None when it says something."""
    if annotation is inspect.Signature.empty:
        return "declares no return type"
    is_union = isinstance(annotation, UnionType) or get_origin(annotation) is Union
    for member in get_args(annotation) if is_union else (annotation,):
        if member is Any:
            return "returns Any"
        if get_origin(member) is Result and get_args(member) == (Any,):
            return "returns Result[Any]"
    return None


def _where(route: object) -> str:
    cells = dict(zip(route.endpoint.__code__.co_freevars, route.endpoint.__closure__, strict=True))  # type: ignore[attr-defined]
    handler = inspect.unwrap(cells["f"].cell_contents)
    source = inspect.getsourcefile(handler) or "?"
    return f"{Path(source).name}:{handler.__code__.co_firstlineno} {handler.__qualname__}"


def _is_fasthtml_static(route: object) -> bool:
    """``fast_app()``'s own root static catch-all, which bootstrap strips before wiring."""
    return route_catalog.CATCH_ALL_MARKER in getattr(route, "path", "")


def handler_defects(routes: tuple[object, ...]) -> list[str]:
    defects = []
    for route in routes:
        signature = fasthtml_signature(route)
        if signature is None or _is_fasthtml_static(route):
            continue
        reason = return_defect(signature.return_annotation)
        if reason is not None:
            defects.append(f"{getattr(route, 'path', '?')}: {_where(route)} {reason}")
    return sorted(set(defects))


def _app_routes(*handlers: tuple[str, Callable[..., Awaitable[object]]]) -> tuple[object, ...]:
    """The routes ``handlers`` register on a real ``fast_app()``, its static catch-all left out."""
    app, rt = fast_app(pico=False, default_hdrs=False)
    for path, handler in handlers:
        rt(path, methods=["GET"])(handler)
    return tuple(r for r in app.routes if not _is_fasthtml_static(r))


# --- the pin ------------------------------------------------------------------------


def test_every_registered_handler_declares_what_it_returns() -> None:
    assert handler_defects(route_catalog.runtime_routes()) == []


def test_the_read_covers_every_http_route() -> None:
    """Every route but a WebSocket one carries FastHTML's signature: a FastHTML that
    stopped closing over ``sig`` would make the pin above pass on nothing."""
    routes = route_catalog.runtime_routes()
    unread = [
        getattr(r, "path", repr(r))
        for r in routes
        if fasthtml_signature(r) is None and type(r).__name__ != "WebSocketRoute"
    ]
    assert unread == []
    assert sum(fasthtml_signature(r) is not None for r in routes) > 800


# --- controls ------------------------------------------------------------------------


async def _returns_any(request: Request) -> Any:  # boundary: test-control — the planted defect
    return Div()


async def _returns_nothing_declared(request: Request):  # type: ignore[no-untyped-def]
    return Div()


async def _returns_result_any(request: Request) -> Result[Any]:  # boundary: test-control
    return Result.ok(1)


async def _returns_ft_or_any(request: Request) -> FT | Any:  # boundary: test-control
    return Div()


async def _returns_ft(request: Request) -> FT:
    return Div()


def test_control_each_defect_is_found() -> None:
    routes = _app_routes(
        ("/any", _returns_any),
        ("/bare", _returns_nothing_declared),
        ("/result-any", _returns_result_any),
        ("/ft-or-any", _returns_ft_or_any),
        ("/ft", _returns_ft),
    )
    found = {d.split(":", 1)[0]: d.rsplit(" ", 2)[-2:] for d in handler_defects(routes)}
    assert found == {
        "/any": ["returns", "Any"],
        "/bare": ["return", "type"],
        "/result-any": ["returns", "Result[Any]"],
        "/ft-or-any": ["returns", "Any"],
    }


def _no_user_service() -> NoReturn:
    raise AssertionError("registration does not read the user service")


@require_role(UserRole.ADMIN, _no_user_service)
async def _role_gated_page(request: Request, current_user: Any = None) -> HtmlDocument:
    raise AssertionError("not called")


def test_a_role_gated_handlers_return_reaches_fasthtml() -> None:
    """``require_role`` publishes the handler's signature for FastHTML to bind; the
    return annotation it publishes is the handler's own."""
    (route,) = _app_routes(("/gated", _role_gated_page))
    signature = fasthtml_signature(route)
    assert signature is not None
    assert signature.return_annotation is HtmlDocument
    assert "current_user" not in signature.parameters


def test_control_a_wrapper_that_drops_the_return_is_found() -> None:
    """The pin reads what FastHTML reads, not the handler underneath: a wrapper that
    publishes a signature without the return annotation is a handler declaring none."""

    async def wrapper(request: Request) -> FT:
        return await _returns_ft(request)

    wrapper.__signature__ = inspect.signature(_returns_ft).replace(  # type: ignore[attr-defined]
        return_annotation=inspect.Signature.empty
    )
    wrapper.__wrapped__ = _returns_ft  # type: ignore[attr-defined]
    defects = handler_defects(_app_routes(("/dropped", wrapper)))
    assert len(defects) == 1 and defects[0].endswith("declares no return type")


def test_a_type_checking_only_annotation_fails_registration(tmp_path: Path) -> None:
    """The wiring is the instrument for runtime imports: FastHTML evaluates the
    annotation at registration, so a name bound only under TYPE_CHECKING raises."""
    module_file = tmp_path / "type_checking_only_handler.py"
    module_file.write_text(
        textwrap.dedent(
            """
            from typing import TYPE_CHECKING

            if TYPE_CHECKING:
                from fasthtml.common import FT


            async def handler(request) -> FT:
                raise AssertionError("not called")
            """
        )
    )
    spec = importlib.util.spec_from_file_location("type_checking_only_handler", module_file)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(NameError, match="'FT'"):
        _app_routes(("/tc", module.handler))
