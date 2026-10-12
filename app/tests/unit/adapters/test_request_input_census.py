"""Two ways FastHTML hands a handler something other than what the client sent.

1. **It casts a bound parameter by calling its annotation.** A handler parameter
   typed ``bool`` / ``int`` / ``float`` / ``date`` / an enum is cast from the raw
   text before the handler runs: an unreadable ``bool`` raises (a 500), an
   unreadable ``int`` answers a bare-text 404. A route reads such a value itself
   (the query-param helpers in ``route_helpers``) — or names it in its path, where a
   segment that does not read is a URL that names nothing (404).
2. **It merges the query string into the JSON body it caches.** Its parameter
   extraction does ``data |= dict(conn.query_params)`` on the dict
   ``request.json()`` returns, so a body read through that cache takes ``?uid=``
   over the body's ``uid``. Every JSON body read goes through
   ``form_helpers.read_json_body``, which reads the body's bytes.

3. **A value a route cannot read is never swapped for a default.** One rule at every
   door: missing or blank is the default, malformed is a 400. A ``try`` that converts a
   value and whose ``except`` falls through (no ``return`` / ``raise``) answers the
   client a value it did not send — the silent fallback the ``route_helpers`` strict
   readers replace. A path segment is exempt: a URL that names a day is navigation
   (``/today/{date_str}`` degrades to today), not a parameter.

Each census walks ``adapters/inbound`` and fails on a site it would let through; each
is run once against a sample that must fail, so a walk that finds nothing is caught.
"""

from __future__ import annotations

import ast
import enum
import importlib
import re
from pathlib import Path

from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.fasthtml_types import Request
from adapters.inbound.form_helpers import read_json_body

_APP = Path(__file__).resolve().parents[3]
_INBOUND = _APP / "adapters" / "inbound"

#: Types FastHTML casts by calling them on the raw text.
_CAST_SCALARS = frozenset({"bool", "int", "float", "date", "datetime", "time", "Decimal"})

#: ``app.<method>(path)`` registers a route too.
_ROUTE_METHODS = frozenset({"get", "post", "put", "patch", "delete", "route"})


# =============================================================================
# 1. Typed handler parameters
# =============================================================================


def _rt_path(call: ast.Call) -> str | None:
    """The route path of a registration — ``rt(...)`` or ``app.get(...)`` and its
    siblings — with an f-string's literal parts kept."""
    func = call.func
    registers = (isinstance(func, ast.Name) and func.id == "rt") or (
        isinstance(func, ast.Attribute)
        and func.attr in _ROUTE_METHODS
        and isinstance(func.value, ast.Name)
        and func.value.id in {"app", "rt"}
    )
    if not registers or not call.args:
        return None
    first = call.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    if isinstance(first, ast.JoinedStr):
        return "".join(
            part.value
            for part in first.values
            if isinstance(part, ast.Constant) and isinstance(part.value, str)
        )
    return None


def _registered_function(
    node: ast.expr,
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    assigned: dict[str, ast.expr],
    depth: int = 0,
) -> str | None:
    """The function a registration hands ``rt(...)`` — through wrapper calls
    (``csrf_protected(boundary_handler()(link))``) and a local it was assigned to
    (``instrumented = self._instrument_handler(update, ...)``)."""
    if depth > 8:
        return None
    if isinstance(node, ast.Name):
        if node.id in functions:
            return node.id
        if node.id in assigned:
            return _registered_function(assigned[node.id], functions, assigned, depth + 1)
        return None
    if isinstance(node, ast.Call):
        for argument in node.args:
            if (
                found := _registered_function(argument, functions, assigned, depth + 1)
            ) is not None:
                return found
    return None


def _own_nodes(scope: ast.AST) -> list[ast.AST]:
    """A scope's nodes in source order, not descending into a nested function."""
    found: list[ast.AST] = []
    for child in ast.iter_child_nodes(scope):
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            continue
        found.append(child)
        found.extend(_own_nodes(child))
    return found


def _handlers(tree: ast.Module) -> list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, str]]:
    """Every function a module registers as a route, with its path."""
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    decorated = [
        (function, path)
        for function in functions.values()
        for decorator in function.decorator_list
        if isinstance(decorator, ast.Call) and (path := _rt_path(decorator)) is not None
    ]
    # rt(path, ...)(handler) — the registration as a call, the handler resolved within
    # the scope that registers it (a factory reuses one local name per route).
    called: list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, str]] = []
    for scope in [tree, *functions.values()]:
        nodes = list(_own_nodes(scope))
        assigned: dict[str, ast.expr] = {}
        for node in nodes:
            if isinstance(node, ast.Assign):
                assigned.update(
                    (target.id, node.value)
                    for target in node.targets
                    if isinstance(target, ast.Name)
                )
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Call)
                and (path := _rt_path(node.func)) is not None
                and node.args
                and (name := _registered_function(node.args[0], functions, assigned)) is not None
            ):
                called.append((functions[name], path))
    return decorated + called


def _cast_type(annotation: ast.expr) -> ast.expr:
    """The type FastHTML calls: a union's first member that is not ``None``."""
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        members: list[ast.expr] = []
        stack: list[ast.expr] = [annotation]
        while stack:
            node = stack.pop()
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
                stack.extend([node.right, node.left])
            else:
                members.append(node)
        return next(
            member
            for member in members
            if not (isinstance(member, ast.Constant) and member.value is None)
        )
    return annotation


def _is_enum(module: object, name: str) -> bool:
    value = getattr(module, name, None)
    return isinstance(value, type) and issubclass(value, enum.Enum)


def cast_parameters(source: str, module: object = None) -> list[str]:
    """``"<function>:<parameter>: <type>"`` for every handler parameter FastHTML casts
    from text that the route's path does not name."""
    tree = ast.parse(source)
    flagged: list[str] = []
    for function, path in _handlers(tree):
        in_path = set(re.findall(r"\{(\w+)\}", path))
        arguments = function.args.args + function.args.kwonlyargs
        for argument in arguments:
            if argument.annotation is None or argument.arg in in_path:
                continue
            cast = _cast_type(argument.annotation)
            name = cast.id if isinstance(cast, ast.Name) else None
            if name is not None and (name in _CAST_SCALARS or _is_enum(module, name)):
                flagged.append(
                    f"{function.name}:{argument.arg}: {ast.unparse(argument.annotation)}"
                )
    return flagged


def _inbound_modules() -> list[tuple[str, str, object]]:
    modules: list[tuple[str, str, object]] = []
    for path in sorted(_INBOUND.rglob("*.py")):
        relative = path.relative_to(_APP).with_suffix("")
        modules.append(
            (
                relative.as_posix(),
                path.read_text(),
                importlib.import_module(".".join(relative.parts)),
            )
        )
    return modules


def test_no_handler_parameter_is_cast_from_text() -> None:
    flagged = [
        f"{name} {site}"
        for name, source, module in _inbound_modules()
        for site in cast_parameters(source, module)
    ]
    assert flagged == [], (
        "read these through route_helpers (parse_*_query_param / parse_*_value / "
        "parse_*_strict) instead of a typed parameter:\n" + "\n".join(flagged)
    )


def test_the_census_walks_the_handlers() -> None:
    """The walk sees both registrations and keeps a path segment."""
    registered = [
        (function.name, path)
        for _, source, _ in _inbound_modules()
        for function, path in _handlers(ast.parse(source))
    ]
    names = {name for name, _ in registered}
    assert "list_users" in names, "a decorated handler"
    assert "update" in names, "a handler registered as rt(...)(update)"
    assert ("exercises_dashboard", "/exercises") in registered, "a handler under @app.get"
    assert len(registered) > 400


class _Shade(enum.Enum):
    LIGHT = "light"


_SAMPLE = """
def register(rt):
    @rt("/a/{year}")
    async def a(request: Request, year: int, flag: bool = False, n: int | None = None):
        ...

    @app.get(f"/api/{domain}/{{uid}}/b")
    async def b(request: Request, uid: int, score: float = 0.5, shade: _Shade = _Shade.LIGHT):
        ...

    async def c(request: Request, when: date, text: str | int = ""):
        ...

    rt("/c", methods=["POST"])(csrf_protected(c))
"""


def test_the_census_flags_a_sample_that_casts() -> None:
    """The instrument's own control: every cast the sample makes is flagged — and
    only those (a path segment, and a ``str``-first union, pass)."""
    sample_module = type("Sample", (), {"_Shade": _Shade})
    assert sorted(cast_parameters(_SAMPLE, sample_module)) == [
        "a:flag: bool",
        "a:n: int | None",
        "b:score: float",
        "b:shade: _Shade",
        "c:when: date",
    ]


# =============================================================================
# 2. JSON body reads
# =============================================================================


def json_cache_reads(source: str) -> list[int]:
    """Lines that read FastHTML's merged JSON cache: ``<request>.json()``."""
    return [
        node.lineno
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "json"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id in {"request", "req", "conn"}
    ]


def test_no_route_reads_the_merged_json_cache() -> None:
    reads = [
        f"{name}:{line}"
        for name, source, _ in _inbound_modules()
        for line in json_cache_reads(source)
    ]
    assert reads == [], "read the body through form_helpers.read_json_body:\n" + "\n".join(reads)


def test_the_json_census_flags_a_sample_that_reads_the_cache() -> None:
    sample = "async def h(request):\n    a = await read_json_body(request)\n    b = await request.json()\n"
    assert json_cache_reads(sample) == [3]


def _app() -> TestClient:
    app, rt = fast_app(pico=False, default_hdrs=False)

    @rt("/body", methods=["POST"])
    async def body(request: Request) -> dict[str, object]:
        return {"read": await read_json_body(request)}

    @rt("/cache", methods=["POST"])
    async def cache(request: Request) -> dict[str, object]:
        return {"read": await request.json()}

    return TestClient(app)


def test_the_body_reader_reads_the_body_not_the_query() -> None:
    client = _app()

    read = client.post("/body?uid=QUERY&extra=1", json={"uid": "BODY"}).json()["read"]

    assert read == {"uid": "BODY"}


def test_the_merge_the_reader_avoids_is_real() -> None:
    """The control: FastHTML's cache does hand back the query string's ``uid``."""
    read = _app().post("/cache?uid=QUERY", json={"uid": "BODY"}).json()["read"]

    assert read["uid"] == "QUERY"


# =============================================================================
# 3. Silent fallbacks
# =============================================================================

#: Calls that read text as a number or a date.
_CONVERTERS = frozenset({"int", "float", "fromisoformat", "Decimal"})


def _converted_names(statement: ast.stmt) -> set[str] | None:
    """The names a statement converts, or ``None`` when it converts nothing; an
    argument that is not a bare name counts as the empty-string name."""
    names: set[str] | None = None
    for node in ast.walk(statement):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        called = (
            func.id
            if isinstance(func, ast.Name)
            else func.attr
            if isinstance(func, ast.Attribute)
            else None
        )
        if called in _CONVERTERS:
            names = names or set()
            names.update(arg.id if isinstance(arg, ast.Name) else "" for arg in node.args)
    return names


def _falls_through(handler: ast.ExceptHandler) -> bool:
    return not any(
        isinstance(node, ast.Return | ast.Raise | ast.Continue)
        for statement in handler.body
        for node in ast.walk(statement)
    )


def silent_fallbacks(source: str) -> list[str]:
    """``"<function>:<line>"`` for every ``try`` that converts a value other than a
    path segment and lets an ``except`` fall through to carry on with a default."""
    tree = ast.parse(source)
    path_segments: dict[str, set[str]] = {}
    for function, path in _handlers(tree):
        path_segments.setdefault(function.name, set()).update(re.findall(r"\{(\w+)\}", path))
    flagged: list[str] = []
    for scope in ast.walk(tree):
        if not isinstance(scope, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        in_path = path_segments.get(scope.name, set())
        for node in _own_nodes(scope):
            if not isinstance(node, ast.Try):
                continue
            converted: set[str] = set()
            for statement in node.body:
                converted |= _converted_names(statement) or set()
            if converted and not converted <= in_path and any(map(_falls_through, node.handlers)):
                flagged.append(f"{scope.name}:{node.lineno}")
    return flagged


def test_no_route_swaps_an_unreadable_value_for_a_default() -> None:
    flagged = [
        f"{name} {site}"
        for name, source, _ in _inbound_modules()
        for site in silent_fallbacks(source)
    ]
    assert flagged == [], (
        "read the value through route_helpers' parse_*_param_strict — malformed is a 400:\n"
        + "\n".join(flagged)
    )


_FALLBACK_SAMPLE = """
def register(rt):
    @rt("/days/{date_str}")
    async def day(request, date_str: str):
        try:
            when = date.fromisoformat(date_str)
        except ValueError:
            when = today()

    @rt("/list")
    async def listing(request):
        raw = request.query_params.get("period_days", "90")
        try:
            period = int(raw)
        except ValueError:
            period = 90
        try:
            limit = int(request.query_params.get("limit"))
        except ValueError:
            return refuse()


def _helper(params):
    try:
        offset = int(params.get("offset"))
    except (TypeError, ValueError):
        offset = 0
"""


def test_the_fallback_census_flags_a_sample_that_falls_back() -> None:
    """The instrument's own control: a query value swapped for a default is flagged,
    in a handler and in a helper; a path segment and a refusal pass."""
    assert sorted(silent_fallbacks(_FALLBACK_SAMPLE)) == ["_helper:24", "listing:13"]
