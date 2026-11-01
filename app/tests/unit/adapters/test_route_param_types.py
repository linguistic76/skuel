"""Route parameter types: ``rt`` and ``app`` name the protocols, and the protocols name
the real framework.

Three pins:

* **Every route function types ``rt`` and ``app``.** Under ``adapters/inbound`` and in
  the script that builds them (``scripts/dev/bootstrap.py``), a parameter named ``rt``
  is a ``RouteDecorator`` and one named ``app`` a ``FastHTMLApp`` — or ``ASGIApp`` in
  ASGI middleware, which wraps whatever app sits inside it. ``Any`` or no annotation
  leaves mypy blind to how the body uses the parameter.
* **Every page wrapper takes FT content.** No function under ``ui/`` declares a
  non-variadic ``content`` parameter as ``Any`` or leaves it unannotated.
* **The protocols describe the real objects.** FastHTML ships no types, so mypy takes
  ``fast_app()``'s result as whatever its annotation claims. A real app is built here and
  every protocol member checked against it: an attribute exists (and is an instance of
  its annotated class when that is a class), a method accepts the arguments the
  protocol declares.
"""

from __future__ import annotations

import ast
import inspect
from annotationlib import Format, get_annotations
from collections.abc import Callable
from pathlib import Path
from typing import Any, get_protocol_members

import pytest
from fasthtml.common import fast_app

import adapters.inbound
import ui
from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator

_INBOUND = Path(adapters.inbound.__file__).parent
_UI = Path(ui.__file__).parent
_REPO = _INBOUND.parent.parent
_BOOTSTRAP = _REPO / "scripts" / "dev" / "bootstrap.py"

_ALLOWED = {
    "rt": {"RouteDecorator"},
    "_rt": {"RouteDecorator"},
    "app": {"FastHTMLApp", "ASGIApp"},
    "_app": {"FastHTMLApp", "ASGIApp"},
}


def _route_sources() -> list[Path]:
    return [*sorted(_INBOUND.rglob("*.py")), _BOOTSTRAP]


def _parameters(path: Path) -> list[tuple[int, str, ast.arg]]:
    """Every named parameter of every function in the file: (line, function, arg)."""
    found: list[tuple[int, str, ast.arg]] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        arguments = node.args
        found.extend(
            (node.lineno, node.name, arg)
            for arg in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs)
        )
    return found


def _annotation(arg: ast.arg) -> str | None:
    return ast.unparse(arg.annotation) if arg.annotation is not None else None


def _untyped_route_parameters() -> list[str]:
    defects: list[str] = []
    for path in _route_sources():
        for line, function, arg in _parameters(path):
            allowed = _ALLOWED.get(arg.arg)
            if allowed is None:
                continue
            annotation = _annotation(arg)
            if annotation not in allowed:
                defects.append(
                    f"{path.relative_to(_REPO)}:{line} {function}({arg.arg}: {annotation})"
                )
    return defects


def test_every_rt_and_app_parameter_names_its_protocol() -> None:
    assert _untyped_route_parameters() == []


def test_the_route_scan_reads_the_route_modules() -> None:
    """Control: the scan sees the ``rt`` every route module declares."""
    declared = [
        arg
        for path in _route_sources()
        for _line, _function, arg in _parameters(path)
        if arg.arg == "rt"
    ]
    assert len(declared) >= 150, len(declared)


def _untyped_content_parameters() -> list[str]:
    defects: list[str] = []
    for path in sorted(_UI.rglob("*.py")):
        for line, function, arg in _parameters(path):
            if arg.arg == "content" and _annotation(arg) in {None, "Any"}:
                defects.append(f"{path.relative_to(_REPO)}:{line} {function}")
    return defects


def test_every_page_wrapper_takes_ft_content() -> None:
    assert _untyped_content_parameters() == []


def test_the_content_scan_reads_the_page_wrappers() -> None:
    """Control: the scan sees the page wrappers' ``content`` parameter."""
    wrappers = [
        function
        for path in sorted(_UI.rglob("*.py"))
        for _line, function, arg in _parameters(path)
        if arg.arg == "content"
    ]
    assert {"BasePage", "AuthPage", "SidebarPage", "render_activity_sidebar_page"} <= set(
        wrappers
    ), wrappers


# ---------------------------------------------------------------------------
# The protocols against a real FastHTML app
# ---------------------------------------------------------------------------


def _dummy_call(protocol_method: Callable[..., object]) -> tuple[list[object], dict[str, object]]:
    """Arguments shaped like the protocol method's parameters (``self`` excluded)."""
    signature = inspect.signature(protocol_method, annotation_format=Format.FORWARDREF)
    positional: list[object] = []
    keywords: dict[str, object] = {}
    for parameter in list(signature.parameters.values())[1:]:
        if parameter.kind is inspect.Parameter.KEYWORD_ONLY or (
            parameter.default is not inspect.Parameter.empty
        ):
            keywords[parameter.name] = object()
        else:
            positional.append(object())
    return positional, keywords


def conformance_defects(protocol: type, real: object) -> list[str]:
    """How ``real`` fails to carry what ``protocol`` declares."""
    annotations = get_annotations(protocol, format=Format.FORWARDREF)
    defects: list[str] = []
    for name in sorted(get_protocol_members(protocol)):
        sentinel = object()
        value = getattr(real, name, sentinel)
        if value is sentinel:
            defects.append(f"{protocol.__name__}.{name}: the real object has no {name!r}")
            continue
        if name in annotations:
            expected = annotations[name]
            if (
                expected is not Any
                and isinstance(expected, type)
                and not isinstance(value, expected)
            ):
                defects.append(
                    f"{protocol.__name__}.{name}: {type(value).__name__}, not {expected.__name__}"
                )
            continue
        positional, keywords = _dummy_call(getattr(protocol, name))
        target = real if name == "__call__" else value
        try:
            inspect.signature(target).bind(*positional, **keywords)
        except TypeError as refusal:
            defects.append(f"{protocol.__name__}.{name}: {refusal}")
    return defects


@pytest.fixture(scope="module")
def real_app() -> tuple[object, object]:
    app, rt = fast_app()
    return app, rt


def test_fasthtml_app_protocol_describes_the_real_app(real_app: tuple[object, object]) -> None:
    app, _rt = real_app
    assert conformance_defects(FastHTMLApp, app) == []


def test_route_decorator_protocol_describes_the_real_rt(real_app: tuple[object, object]) -> None:
    _app, rt = real_app
    assert conformance_defects(RouteDecorator, rt) == []


def test_the_conformance_check_refuses_a_false_claim(real_app: tuple[object, object]) -> None:
    """Control: a protocol claiming a member the app lacks, or a call it refuses, fails."""
    from typing import Protocol

    class Overclaims(Protocol):
        absent_member: int

        def get(self, path: str, extra: int, more: int, still_more: int) -> object: ...

    app, _rt = real_app
    defects = conformance_defects(Overclaims, app)
    assert len(defects) == 2, defects
