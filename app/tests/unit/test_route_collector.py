"""The one stand-in ``rt`` (``tests/helpers/route_collector.py``) and the pin that keeps it the one.

Two halves. The helper's doors are FastHTML's: one door per method a route registers,
held against a real ``fast_app()``; a lookup names its method; a door taken twice refuses.
Then the census: no test hand-writes its own ``rt``, hands a route function anything
but the helper's ``rt`` or a real app's, or binds a mock as one. Each census arm has a
control that makes it fail.

The census's blind spot: a route function called through a variable (a parametrized
``factory(rt, ...)``) is not resolved, so the value it is handed is read only when it is a
mock bound to the name ``rt``. A stand-in that is neither a path-first decorator factory nor
a class with a decorator-factory ``__call__``, handed through such a call, passes.
"""

from __future__ import annotations

import ast
import functools
import re
import subprocess
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fasthtml.common import fast_app

from tests.helpers.route_collector import Door, route_collector

_APP = Path(__file__).resolve().parents[2]
_HELPER = "tests/helpers/route_collector.py"


def handler(request: object) -> str:
    return "handled"


def post(request: object) -> str:
    """Named for a verb: FastHTML registers a methods-less route under that verb alone."""
    return "posted"


#: (methods passed to ``rt``, the handler) — every shape a route registers with.
_SHAPES: tuple[tuple[list[str] | None, Callable[[object], str]], ...] = (
    (["POST"], handler),
    (["get"], handler),
    (["GET", "POST"], handler),
    (None, handler),
    (None, post),
)


def _real_doors(path: str, methods: list[str] | None, func: Callable[[object], str]) -> set[Door]:
    """The doors a real FastHTML app registers ``func`` at, without Starlette's HEAD answer."""
    _app, rt = fast_app()
    rt(path, methods=methods)(func)
    return {
        (route.path, method)
        for route in _app.routes
        if getattr(route, "path", None) == path
        for method in route.methods
        if method != "HEAD"
    }


@pytest.mark.parametrize(("methods", "func"), _SHAPES)
def test_the_collector_records_the_doors_fasthtml_registers(
    methods: list[str] | None, func: Callable[[object], str]
) -> None:
    rt, registered = route_collector()
    rt("/collector/door", methods=methods)(func)

    assert set(registered) == _real_doors("/collector/door", methods, func)
    assert all(registered[door] is func for door in registered)


def test_the_real_app_registers_more_than_one_door_for_a_methods_less_route() -> None:
    """Control: the comparison above can tell one door from two."""
    assert _real_doors("/collector/door", None, handler) == {
        ("/collector/door", "GET"),
        ("/collector/door", "POST"),
    }


def test_the_decorator_hands_back_the_handler_itself() -> None:
    rt, _ = route_collector()
    assert rt("/collector/door")(handler) is handler


def test_a_lookup_by_a_method_the_path_does_not_answer_misses_loudly() -> None:
    rt, registered = route_collector()
    rt("/collector/door", methods=["POST"])(handler)

    with pytest.raises(KeyError, match=r"no GET /collector/door registered; .*\['POST'\]"):
        registered["/collector/door", "GET"]
    assert ("/collector/door", "GET") not in registered
    assert ("/collector/door", "POST") in registered


@pytest.mark.parametrize(
    "key",
    [
        "/collector/door",
        ("/collector/door", "get"),
        ("/collector/door",),
        ("/collector/door", "FETCH"),
    ],
)
def test_a_lookup_that_names_no_door_refuses(key: object) -> None:
    """A path alone, a lowercase method or no method is no door: ``[]`` and ``in`` refuse,
    so a negative assertion cannot pass by asking the wrong question."""
    rt, registered = route_collector()
    rt("/collector/door", methods=["GET"])(handler)

    with pytest.raises(TypeError, match=r"registered\[path, METHOD\]"):
        registered[key]  # type: ignore[index]
    with pytest.raises(TypeError, match=r"registered\[path, METHOD\]"):
        _ = key in registered


def test_a_door_registered_twice_refuses() -> None:
    rt, registered = route_collector()
    rt("/collector/door", methods=["POST"])(handler)

    with pytest.raises(ValueError, match="POST /collector/door is registered twice"):
        rt("/collector/door", methods=["POST"])(post)
    rt("/collector/door", methods=["GET"])(post)

    assert registered.methods("/collector/door") == {"GET", "POST"}
    assert registered["/collector/door", "POST"] is handler


def test_the_collector_is_a_route_decorator_by_its_annotation() -> None:
    """mypy checks the helper's ``rt`` against ``RouteDecorator`` through this return
    annotation; tests run with ``arg-type`` off, so no other site checks it."""
    assert route_collector.__annotations__["return"] == "tuple[RouteDecorator, RegisteredHandlers]"


# ---------------------------------------------------------------------------
# One stand-in
# ---------------------------------------------------------------------------

_PATH_NAMES = frozenset({"path", "_path"})
_REAL_RTS = frozenset({"route_collector", "fast_app"})
_MOCKS = frozenset({"MagicMock", "Mock", "AsyncMock", "NonCallableMagicMock", "create_autospec"})
_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


def _git_ls(*patterns: str) -> list[str]:
    listed = subprocess.run(
        ["git", "ls-files", *patterns], cwd=_APP, capture_output=True, text=True, check=True
    )
    return listed.stdout.split()


@functools.cache
def route_functions() -> dict[str, frozenset[int]]:
    """Every first-party callable that takes ``rt``, by the name a caller writes → the
    positional slot ``rt`` holds. A constructor is called by its class name."""
    slots: dict[str, set[int]] = {}
    for name in _git_ls("adapters/*.py", "ui/*.py", "services_bootstrap/*.py"):
        tree = ast.parse((_APP / name).read_text())
        owner = {
            item: node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef)
            for item in node.body
        }
        for node in ast.walk(tree):
            if isinstance(node, _FUNCTIONS):
                params = [arg.arg for arg in node.args.posonlyargs + node.args.args]
                if "rt" in params:
                    slot = params.index("rt") - (params[0] in {"self", "cls"})
                    called = owner[node] if node.name == "__init__" else node.name
                    slots.setdefault(called, set()).add(slot)
    return {name: frozenset(found) for name, found in slots.items()}


def _returns_its_own_def(func: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda) -> bool:
    """The decorator-factory shape: a function that returns a function defined inside it."""
    if isinstance(func, ast.Lambda):
        return isinstance(func.body, ast.Lambda)
    inner = {node.name for node in func.body if isinstance(node, _FUNCTIONS)}
    return any(
        isinstance(node, ast.Return) and isinstance(node.value, ast.Name) and node.value.id in inner
        for node in ast.walk(func)
    )


def _first_param(func: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda, skip: int) -> str:
    params = func.args.posonlyargs + func.args.args
    return params[skip].arg if len(params) > skip else ""


def _hand_written(nodes: list[ast.AST]) -> Iterator[tuple[int, str]]:
    """A class whose ``__call__`` is a decorator factory, or a function or lambda taking
    ``path`` first that returns one."""
    for node in nodes:
        if isinstance(node, ast.ClassDef):
            calls = [item for item in node.body if isinstance(item, _FUNCTIONS)]
            if any(
                item.name == "__call__"
                and (_first_param(item, 1) in _PATH_NAMES or _returns_its_own_def(item))
                for item in calls
            ):
                yield node.lineno, f"class {node.name} is a hand-written rt"
        elif (
            isinstance(node, (*_FUNCTIONS, ast.Lambda))
            and _first_param(node, 0) in _PATH_NAMES
            and _returns_its_own_def(node)
        ):
            yield node.lineno, f"{getattr(node, 'name', '<lambda>')} is a hand-written rt"


def _calls(node: ast.AST, names: frozenset[str]) -> bool:
    return any(
        isinstance(call, ast.Call) and _callee(call.func) in names for call in ast.walk(node)
    )


def _is_call_to(node: ast.expr, names: frozenset[str]) -> bool:
    return isinstance(node, ast.Call) and _callee(node.func) in names


def _callee(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


class _Scopes:
    """Where a name in one module is bound: assignments and parameters, per enclosing scope."""

    def __init__(self, tree: ast.Module) -> None:
        self.parent: dict[ast.AST, ast.AST] = {
            child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)
        }
        self.fixtures = {
            node.name: node
            for node in self.parent.values()
            if isinstance(node, _FUNCTIONS)
            and any("fixture" in ast.unparse(decorator) for decorator in node.decorator_list)
        }
        self._assigns: dict[ast.AST, list[ast.Assign]] = {}

    def _assignments(self, scope: ast.AST) -> list[ast.Assign]:
        if scope not in self._assigns:
            body = scope.body if isinstance(scope, ast.Module) else ast.walk(scope)
            self._assigns[scope] = [node for node in body if isinstance(node, ast.Assign)]
        return self._assigns[scope]

    def _scopes(self, node: ast.AST) -> Iterator[ast.AST]:
        while node in self.parent:
            node = self.parent[node]
            if isinstance(node, (*_FUNCTIONS, ast.Module)):
                yield node

    def is_real_rt(self, name: str, at: ast.AST, seen: frozenset[str] = frozenset()) -> bool:
        """``name`` holds the helper's ``rt`` or a real app's: bound from ``route_collector()``
        / ``fast_app()``, or a parameter filled by a fixture that is."""
        for scope in self._scopes(at):
            for node in self._assignments(scope):
                if any(
                    isinstance(target, ast.Name) and target.id == name
                    for target_node in node.targets
                    for target in ast.walk(target_node)
                ):
                    return _calls(node.value, _REAL_RTS)
            if isinstance(scope, _FUNCTIONS):
                params = scope.args.posonlyargs + scope.args.args + scope.args.kwonlyargs
                if any(param.arg == name for param in params):
                    return self.fixture_is_real(name, seen)
        return False

    def fixture_is_real(self, name: str, seen: frozenset[str] = frozenset()) -> bool:
        fixture = self.fixtures.get(name)
        if fixture is None or name in seen:
            return False
        if _calls(fixture, _REAL_RTS):
            return True
        params = fixture.args.posonlyargs + fixture.args.args
        return any(self.fixture_is_real(param.arg, seen | {name}) for param in params)


def _handed(
    tree: ast.Module, nodes: list[ast.AST], functions: dict[str, frozenset[int]]
) -> Iterator[tuple[int, str]]:
    """Each value a route function's ``rt`` slot receives that is not the helper's ``rt``
    or a real app's; and every mock bound to ``rt`` or passed as ``rt=``."""
    scopes: _Scopes | None = None
    imported = {
        alias.asname or alias.name
        for node in nodes
        if isinstance(node, ast.ImportFrom)
        and (node.module or "").split(".")[0] in {"adapters", "ui", "services_bootstrap"}
        for alias in node.names
    }
    local = {node.name for node in nodes if isinstance(node, _FUNCTIONS)}
    for node in nodes:
        if isinstance(node, ast.Assign) and _is_call_to(node.value, _MOCKS):
            for target_node in node.targets:
                if any(isinstance(t, ast.Name) and t.id == "rt" for t in ast.walk(target_node)):
                    yield node.lineno, f"rt is a mock: {ast.unparse(node.value)}"
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg == "rt" and _is_call_to(keyword.value, _MOCKS):
                yield node.lineno, f"rt= is a mock: {ast.unparse(keyword.value)}"
        name = _callee(node.func)
        if name not in functions:
            continue
        if isinstance(node.func, ast.Name) and name not in imported:
            continue
        if isinstance(node.func, ast.Attribute) and name in local:
            continue
        value = next((kw.value for kw in node.keywords if kw.arg == "rt"), None)
        if value is None:
            value = next(
                (node.args[slot] for slot in sorted(functions[name]) if slot < len(node.args)),
                None,
            )
        if value is None:
            continue
        scopes = scopes or _Scopes(tree)
        if not (isinstance(value, ast.Name) and scopes.is_real_rt(value.id, node)):
            yield node.lineno, f"{name} is handed rt={ast.unparse(value)}"


_WORDS = re.compile(r"\w+")
_PATH_FIRST = re.compile(r"def \w+\(\s*_?path\b|lambda\s+_?path\b")


def candidates(sources: dict[str, str]) -> dict[str, str]:
    """The sources the census parses: those holding a ``__call__``, the name ``rt``, a call
    to a route function's name, or a ``path``-first def or lambda — the prefilter that
    keeps the census to a fraction of a second."""
    names = route_functions().keys() | {"rt", "__call__"}
    return {
        name: source
        for name, source in sources.items()
        if names & set(_WORDS.findall(source)) or _PATH_FIRST.search(source)
    }


def stand_in_defects(sources: dict[str, str]) -> list[str]:
    """Every hand-written ``rt``, every non-helper value in a route function's ``rt`` slot,
    every mock bound as ``rt`` — outside the helper."""
    functions = route_functions()
    defects: list[str] = []
    for name, source in candidates(sources).items():
        if name == _HELPER:
            continue
        tree = ast.parse(source)
        nodes = list(ast.walk(tree))
        found = {*_hand_written(nodes), *_handed(tree, nodes, functions)}
        for line, defect in sorted(found):
            defects.append(f"{name}:{line} {defect}")
    return defects


@functools.cache
def _test_sources() -> dict[str, str]:
    return {name: (_APP / name).read_text() for name in _git_ls("tests/*.py")}


def test_no_test_has_its_own_rt() -> None:
    assert stand_in_defects(_test_sources()) == []


def test_the_census_reads_the_route_functions_and_the_test_tree() -> None:
    """Control: the census sees the route functions and the tests that use the helper."""
    assert {"create_calendar_ui_routes", "register_routes"} <= route_functions().keys()
    users = {name for name, source in _test_sources().items() if "route_collector()" in source}
    assert len(users) >= 40, users
    assert users <= candidates(_test_sources()).keys()


_ROUTE = "from adapters.inbound.calendar_ui import create_calendar_ui_routes\n"


@pytest.mark.parametrize(
    ("source", "found"),
    [
        (
            "class Stand:\n    def __call__(self, path, methods=None):\n"
            "        def deco(f):\n            return f\n        return deco\n",
            "class Stand is a hand-written rt",
        ),
        (
            "class Router:\n    def __call__(self, route):\n"
            "        def deco(f):\n            return f\n        return deco\n",
            "class Router is a hand-written rt",
        ),
        (
            "def rt(path, *a, **k):\n    def deco(f):\n        return f\n    return deco\n",
            "rt is a hand-written rt",
        ),
        ("fake = lambda path, methods=None: (lambda f: f)\n", "<lambda> is a hand-written rt"),
        ("from unittest.mock import MagicMock\nrt = MagicMock()\n", "rt is a mock: MagicMock()"),
        (
            _ROUTE + "from unittest.mock import MagicMock\n"
            "create_calendar_ui_routes(rt=MagicMock(), calendar_service=None)\n",
            "rt= is a mock: MagicMock()",
        ),
        (
            _ROUTE + "import functools\nrecord = functools.partial(dict.setdefault, {})\n"
            "create_calendar_ui_routes(record, None)\n",
            "create_calendar_ui_routes is handed rt=record",
        ),
        (
            _ROUTE + 'create_calendar_ui_routes("rt", None)\n',
            "create_calendar_ui_routes is handed rt='rt'",
        ),
        (
            _ROUTE + "import pytest\n@pytest.fixture\ndef router():\n    return object()\n"
            "def test_x(router):\n    create_calendar_ui_routes(router, None)\n",
            "create_calendar_ui_routes is handed rt=router",
        ),
    ],
    ids=[
        "class-path",
        "class-other-name",
        "closure",
        "lambda",
        "mock-bound",
        "mock-keyword",
        "partial-handed",
        "string-handed",
        "fixture-handed",
    ],
)
def test_the_census_finds_each_stand_in_shape(source: str, found: str) -> None:
    defects = stand_in_defects({"tests/unit/scratch.py": source})
    assert any(defect.endswith(found) for defect in defects), defects


def test_the_census_passes_the_helper_and_a_real_app() -> None:
    """Control: the two real ``rt``s — the helper's, a real app's, each direct and through a
    fixture — are not stand-ins."""
    source = (
        _ROUTE + "import pytest\nfrom fasthtml.common import fast_app\n"
        "from tests.helpers.route_collector import route_collector\n"
        "@pytest.fixture\ndef collected():\n    return route_collector()\n"
        "@pytest.fixture\ndef router(collected):\n    return collected[0]\n"
        "def test_a(router):\n    create_calendar_ui_routes(router, None)\n"
        "def test_b():\n    rt, registered = route_collector()\n"
        "    create_calendar_ui_routes(rt=rt, calendar_service=None)\n"
        "def test_c():\n    app, rt = fast_app()\n    create_calendar_ui_routes(rt, None)\n"
    )
    assert stand_in_defects({"tests/unit/scratch.py": source}) == []


def test_the_helper_is_the_one_exemption() -> None:
    source = (_APP / _HELPER).read_text()
    assert stand_in_defects({"tests/unit/elsewhere.py": source}) != []
    assert stand_in_defects({_HELPER: source}) == []
