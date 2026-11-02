"""Route parameter types: ``rt`` and ``app`` name the protocols, and the protocols name
the real framework.

Five pins:

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
* **Every app a test holds names the protocol.** Under ``tests/``, a parameter named
  ``skuel_app`` (the bootstrapped app) is a ``FastHTMLApp``, and one named ``app`` is
  never ``Any`` or unannotated.
* **No ``Any`` is excused at the ASGI boundary.** Starlette exports the types of
  ``scope`` / ``receive`` / ``send`` (``starlette.types``) and of the router, so no
  tracked file in the repository carries a boundary tag for an ``Any`` there.
"""

from __future__ import annotations

import ast
import functools
import inspect
import re
import subprocess
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
}


def _route_sources() -> list[Path]:
    return [*sorted(_INBOUND.rglob("*.py")), _BOOTSTRAP]


def _parameters(path: Path) -> list[tuple[int, str, ast.arg]]:
    """Every named parameter of every function in the file: (line, function, arg)."""
    return _parameters_in(path.read_text(encoding="utf-8"))


def _parameters_in(source: str) -> list[tuple[int, str, ast.arg]]:
    """Every named parameter of every function in ``source``: (line, function, arg)."""
    found: list[tuple[int, str, ast.arg]] = []
    for node in ast.walk(ast.parse(source)):
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
    """How ``real`` fails to carry what ``protocol`` declares.

    A stringized annotation (``from __future__ import annotations``) is evaluated, so an
    attribute's class is checked whichever way its module spells it; a name that does not
    resolve raises rather than skipping the check.
    """
    annotations = get_annotations(protocol, eval_str=True)
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
    """Control: a protocol claiming a member the app lacks, a member of another class, or a
    call it refuses, fails."""
    from typing import Protocol

    class Overclaims(Protocol):
        absent_member: int
        router: int

        def get(self, path: str, extra: int, more: int, still_more: int) -> object: ...

    app, _rt = real_app
    defects = conformance_defects(Overclaims, app)
    assert len(defects) == 3, defects
    assert "Overclaims.router: Router, not int" in defects, defects


# ---------------------------------------------------------------------------
# The app a test holds
# ---------------------------------------------------------------------------

_TESTS = _REPO / "tests"


def held_app_defects(sources: dict[str, str]) -> list[str]:
    """Every ``skuel_app`` not typed ``FastHTMLApp``, and every ``app`` typed ``Any`` or bare."""
    defects: list[str] = []
    for name, source in sources.items():
        for line, function, arg in _parameters_in(source):
            annotation = _annotation(arg)
            if (arg.arg == "skuel_app" and annotation != "FastHTMLApp") or (
                arg.arg == "app" and annotation in {None, "Any"}
            ):
                defects.append(f"{name}:{line} {function}({arg.arg}: {annotation})")
    return defects


#: A parameter named ``app`` or ``skuel_app`` — the prefilter that keeps the AST pass to
#: the files that can hold one.
_HELD_APP = re.compile(r"\b(?:skuel_)?app\s*[:,)=]")


@functools.cache
def _test_sources() -> dict[str, str]:
    """Every test module that can name an app parameter, by its path under the app root."""
    sources: dict[str, str] = {}
    for path in sorted(_TESTS.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if _HELD_APP.search(source):
            sources[str(path.relative_to(_REPO))] = source
    return sources


def test_every_app_a_test_holds_names_the_protocol() -> None:
    assert held_app_defects(_test_sources()) == []


def test_the_test_app_scan_refuses_an_untyped_app() -> None:
    """Control: an ``Any``, a bare ``skuel_app`` and an ``app: Any`` are each refused."""
    source = (
        "async def typed_any(skuel_app: Any) -> None: ...\n"
        "def bare(skuel_app): ...\n"
        "def built(app: Any) -> None: ...\n"
        "def fine(skuel_app: FastHTMLApp, app: object) -> None: ...\n"
    )
    assert [defect.split(" ", 1)[1] for defect in held_app_defects({"fixture.py": source})] == [
        "typed_any(skuel_app: Any)",
        "bare(skuel_app: None)",
        "built(app: Any)",
    ]


def test_the_test_app_scan_reads_the_integration_fixtures() -> None:
    """Control: the scan sees the ``skuel_app`` the integration tests take."""
    held = [
        arg
        for source in _test_sources().values()
        for _line, _function, arg in _parameters_in(source)
        if arg.arg == "skuel_app"
    ]
    assert len(held) >= 150, len(held)


# ---------------------------------------------------------------------------
# No boundary tag at the ASGI boundary
# ---------------------------------------------------------------------------

#: Built from two parts so this file does not carry the tag it refuses.
_ASGI_TAG = ("# boundary: " + "fasthtml-app").encode()


def tag_sites(files: dict[str, bytes]) -> list[str]:
    """Every ``path:line`` whose line carries the ASGI boundary tag."""
    return [
        f"{path}:{number}"
        for path, content in files.items()
        if _ASGI_TAG in content
        for number, line in enumerate(content.splitlines(), 1)
        if _ASGI_TAG in line
    ]


def _tracked_files() -> dict[str, bytes]:
    """Every file git tracks in the repository, by its path from the repository root."""
    root = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=_REPO,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )
    listed = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True
    ).stdout
    files: dict[str, bytes] = {}
    for raw in listed.split(b"\0"):
        path = root / raw.decode()
        if raw and path.is_file():
            files[raw.decode()] = path.read_bytes()
    return files


def test_no_tracked_file_carries_the_asgi_boundary_tag() -> None:
    assert tag_sites(_tracked_files()) == []


def test_the_tag_scan_finds_the_tag() -> None:
    """Control: a line carrying the tag is reported, a line without it is not."""
    fixture = b"x = 1\nasync def f(scope: Any) -> None:  " + _ASGI_TAG + b"\n"
    assert tag_sites({"fixture.py": fixture, "clean.py": b"x = 1\n"}) == ["fixture.py:2"]


def test_the_tag_scan_reads_the_tracked_tree() -> None:
    """Control: the tracked files include this module and the protocol it pins."""
    tracked = _tracked_files()
    assert {
        "app/tests/unit/adapters/test_route_param_types.py",
        "app/adapters/inbound/fasthtml_types.py",
    } <= set(tracked)
    assert len(tracked) >= 3000, len(tracked)
