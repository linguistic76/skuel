"""Route-module signatures: a route function declares exactly what its caller sends.

Four pins over ``adapters/inbound`` (and, for ``app``, the bootstrap that wires it):

* **No ``_sync_service``.** No function declares the parameter: a route function
  declares only what its caller passes.
* **An ``app`` parameter is read.** A function takes the app only to read one of
  its members — directly, through the ``self`` attribute it stores it on, or in the
  function it hands it to. A route function that registers through ``rt`` does not
  take the app at all.
* **No ``_app``.** No first-party function declares the placeholder: a parameter
  that is not read is not declared.
* **Every config binds its factories exactly.** ``register_domain_routes`` calls
  ``factory(rt, primary_service, **mapping)`` with the config's
  ``api_related_services`` / ``ui_related_services`` mapping. A factory's first
  parameter is ``rt``, each mapping key must name a parameter of its factory, each
  parameter after the first two without a default must have a key, and no factory
  may take ``**kwargs`` — a ``**kwargs`` sink there accepts a mistyped or misrouted
  key without a word.
"""

from __future__ import annotations

import ast
import inspect
import re
from annotationlib import Format
from collections.abc import Callable
from pathlib import Path

import pytest

import adapters.inbound
from adapters.inbound.route_factories import DomainRouteConfig
from tests.helpers.route_configs import collect_module_configs

_INBOUND = Path(adapters.inbound.__file__).parent
_REPO = _INBOUND.parent.parent
_BOOTSTRAP = _REPO / "scripts" / "dev" / "bootstrap.py"
#: Every first-party tree a function could declare ``_app`` in.
_FIRST_PARTY = ("adapters", "core", "ui", "services_bootstrap", "scripts", "tests", "main.py")

# Measured: 54 factory bindings over 34 configs (pathways_routes re-exports
# PS_CONFIG, so its two factories are bound twice). A floor, not an equality —
# a new config raises it; if it trips, a config stopped being discovered.
_MIN_BOUND_FACTORIES = 50

_NAMED_KINDS = (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)


def _functions_declaring(parameter: str) -> list[str]:
    """Every function under ``adapters/inbound`` with a parameter of that name."""
    found: list[str] = []
    for path in sorted(_INBOUND.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            arguments = node.args
            names = [
                a.arg for a in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs)
            ]
            if parameter in names:
                found.append(f"{path.relative_to(_REPO)}:{node.lineno} {node.name}")
    return found


def test_no_route_function_declares_sync_service() -> None:
    assert _functions_declaring("_sync_service") == []


def test_the_parameter_scan_reads_the_route_modules() -> None:
    """Control: the scan finds a parameter every ``create_*_routes`` declares."""
    declaring_services = [
        hit for hit in _functions_declaring("services") if hit.endswith("_routes")
    ]
    assert len(declaring_services) >= 30, declaring_services


def binding_defects(factory: Callable[..., None], mapping: dict[str, str]) -> list[str]:
    """How ``factory(rt, primary, **mapping)`` fails to bind exactly."""
    parameters = list(
        inspect.signature(factory, annotation_format=Format.FORWARDREF).parameters.values()
    )
    first = parameters[0].name if parameters else None
    defects = [] if first == "rt" else [f"first parameter is {first!r}, not 'rt'"]
    defects += [f"takes **{p.name}" for p in parameters if p.kind is inspect.Parameter.VAR_KEYWORD]
    injected = [p for p in parameters[2:] if p.kind in _NAMED_KINDS]
    names = {p.name for p in injected}
    defects += [f"mapping key {key!r} names no parameter" for key in mapping if key not in names]
    defects += [
        f"parameter {p.name!r} has no default and no mapping key"
        for p in injected
        if p.default is inspect.Parameter.empty and p.name not in mapping
    ]
    return defects


def _config_factories(
    config: DomainRouteConfig,
) -> list[tuple[str, Callable[..., None], dict[str, str]]]:
    pairs = (
        ("api", config.api_factory, config.api_related_services),
        ("ui", config.ui_factory, config.ui_related_services),
    )
    return [(side, factory, mapping) for side, factory, mapping in pairs if factory is not None]


@pytest.fixture(scope="module")
def bound() -> list[tuple[str, list[str]]]:
    configs, import_failures = collect_module_configs()
    assert not import_failures, "\n".join(import_failures)
    return [
        (f"{module}.{name} {side}={factory.__name__}", binding_defects(factory, mapping))
        for module, name, config in configs
        for side, factory, mapping in _config_factories(config)
    ]


def test_every_config_binds_its_factories_exactly(bound: list[tuple[str, list[str]]]) -> None:
    failures = [f"{label}: {'; '.join(defects)}" for label, defects in bound if defects]
    assert failures == [], "\n".join(failures)


def test_binding_coverage_floor(bound: list[tuple[str, list[str]]]) -> None:
    labels = [label for label, _ in bound]
    assert len(labels) >= _MIN_BOUND_FACTORIES, labels
    assert any("tasks_routes.TASKS_CONFIG api=" in label for label in labels)
    assert any("hierarchy_routes.HIERARCHY_CONFIG api=" in label for label in labels)


# --- non-vacuity: each defect shape is reported -----------------------------


def _factory_with_a_sink(rt: object, primary: object, **_kwargs: object) -> None:
    pass


def _factory_needing_goals(rt: object, primary: object, goals_service: object) -> None:
    pass


def test_a_kwargs_sink_is_reported() -> None:
    assert binding_defects(_factory_with_a_sink, {}) == ["takes **_kwargs"]


def test_a_misrouted_key_is_reported() -> None:
    assert binding_defects(
        _factory_needing_goals, {"goals_service": "goals", "user_service": "user"}
    ) == ["mapping key 'user_service' names no parameter"]


def test_a_required_parameter_without_a_key_is_reported() -> None:
    assert binding_defects(_factory_needing_goals, {}) == [
        "parameter 'goals_service' has no default and no mapping key"
    ]


def _factory_taking_the_app(app: object, rt: object, primary: object) -> None:
    pass


def test_a_factory_taking_the_app_is_reported() -> None:
    """Called as ``factory(rt, primary)``, its ``primary`` would arrive as ``rt``."""
    assert binding_defects(_factory_taking_the_app, {}) == [
        "first parameter is 'app', not 'rt'",
        "parameter 'primary' has no default and no mapping key",
    ]


# --- an ``app`` parameter is read ------------------------------------------


def _callee_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _positional_names(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    return [a.arg for a in (*function.args.posonlyargs, *function.args.args)]


def _all_names(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    return {*_positional_names(function), *(a.arg for a in function.args.kwonlyargs)}


def _reads_an_attribute(node: ast.AST, name: str) -> bool:
    return any(
        isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name) and sub.value.id == name
        for sub in ast.walk(node)
    )


def _stored_and_read(
    function: ast.FunctionDef | ast.AsyncFunctionDef, owner: ast.ClassDef | None
) -> bool:
    """``self.<x> = app`` and the class loads ``self.<x>`` (ASGI middleware calls it)."""
    if owner is None:
        return False
    stored = {
        target.attr
        for sub in ast.walk(function)
        if isinstance(sub, ast.Assign) and isinstance(sub.value, ast.Name) and sub.value.id == "app"
        for target in sub.targets
        if isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Name)
        and target.value.id == "self"
    }
    return any(
        isinstance(sub, ast.Attribute)
        and isinstance(sub.ctx, ast.Load)
        and isinstance(sub.value, ast.Name)
        and sub.value.id == "self"
        and sub.attr in stored
        for sub in ast.walk(owner)
    )


def _handed_on(function: ast.FunctionDef | ast.AsyncFunctionDef) -> list[tuple[str, int | str]]:
    """Each (callee, position or keyword) the function passes its ``app`` to."""
    handed: list[tuple[str, int | str]] = []
    for call in ast.walk(function):
        if not isinstance(call, ast.Call) or (callee := _callee_name(call)) is None:
            continue
        handed.extend(
            (callee, index)
            for index, arg in enumerate(call.args)
            if isinstance(arg, ast.Name) and arg.id == "app"
        )
        handed.extend(
            (callee, keyword.arg)
            for keyword in call.keywords
            if keyword.arg is not None
            and isinstance(keyword.value, ast.Name)
            and keyword.value.id == "app"
        )
    return handed


def unread_app_parameters(sources: dict[str, str]) -> list[str]:
    """Functions in ``sources`` (label → source) declaring an ``app`` nobody reads.

    Read means an attribute of it is read in the function, or it is stored on
    ``self`` and the class loads that attribute, or it is handed to a function in
    ``sources`` whose own ``app`` parameter is read.
    """
    declaring: list[tuple[str, ast.FunctionDef | ast.AsyncFunctionDef, bool]] = []
    by_name: dict[str, list[ast.FunctionDef | ast.AsyncFunctionDef]] = {}
    for label, source in sources.items():
        tree = ast.parse(source)
        owners = {
            id(child): node
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef)
            for child in node.body
        }
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            by_name.setdefault(node.name, []).append(node)
            if "app" in _all_names(node):
                read = _reads_an_attribute(node, "app") or _stored_and_read(
                    node, owners.get(id(node))
                )
                declaring.append((f"{label}:{node.lineno} {node.name}", node, read))

    reading = {id(node) for _, node, read in declaring if read}

    def reads_its_app(callee: ast.FunctionDef | ast.AsyncFunctionDef, slot: int | str) -> bool:
        names = _positional_names(callee)
        if names[:1] == ["self"]:
            names = names[1:]
        name = names[slot] if isinstance(slot, int) and slot < len(names) else slot
        return name == "app" and id(callee) in reading

    changed = True
    while changed:
        changed = False
        for _, node, _read in declaring:
            if id(node) in reading:
                continue
            if any(
                reads_its_app(callee, slot)
                for name, slot in _handed_on(node)
                for callee in by_name.get(name, [])
            ):
                reading.add(id(node))
                changed = True
    return [label for label, node, _ in declaring if id(node) not in reading]


def _route_sources() -> dict[str, str]:
    paths = [*sorted(_INBOUND.rglob("*.py")), _BOOTSTRAP]
    return {str(path.relative_to(_REPO)): path.read_text(encoding="utf-8") for path in paths}


def test_every_app_parameter_is_read() -> None:
    assert unread_app_parameters(_route_sources()) == []


def test_the_app_scan_sees_each_way_a_parameter_is_read() -> None:
    """Control: the readers the tree holds are each found, and kept for their read."""
    sources = _route_sources()
    declaring = {
        label.rsplit(" ", 1)[1]
        for label in unread_app_parameters(
            {k: v.replace("app.", "_unread.") for k, v in sources.items()}
        )
    }
    # With every ``app.<member>`` read renamed away, the direct readers and the
    # bootstrap functions that only hand the app on to one are all reported...
    assert {
        "create_device_routes",
        "install_malformed_body_guard",
        "skuel_lifespan",
        "_wire_all_routes",
        "_wire_routes",
    } <= declaring, declaring
    # ...and ASGI middleware, which calls the ``self.app`` it stores, is not.
    assert "__init__" not in declaring, declaring


_PLANTED = """
def registers_through_rt(app, rt):
    @rt("/x")
    def x(request): ...

def reads_the_router(app, rt):
    app.router.routes.append(None)

def hands_it_on(app, rt):
    reads_the_router(app, rt)

def hands_it_to_one_that_ignores_it(app, rt):
    registers_through_rt(app=app, rt=rt)

class Stores:
    def __init__(self, app):
        self.app = app

class StoresAndCalls:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        await self.app(scope, receive, send)
"""


def test_an_unread_app_parameter_is_reported() -> None:
    assert unread_app_parameters({"planted": _PLANTED}) == [
        "planted:2 registers_through_rt",
        "planted:12 hands_it_to_one_that_ignores_it",
        "planted:16 __init__",
    ]


# --- no ``_app`` -------------------------------------------------------------


def _declarations_of(parameter: str, sources: dict[str, str]) -> list[str]:
    """Each function declaring the parameter; a source that never spells it is not parsed."""
    spelled = re.compile(rf"\b{re.escape(parameter)}\b")
    return [
        f"{label}:{node.lineno} {node.name}"
        for label, source in sources.items()
        if spelled.search(source)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and parameter in _all_names(node)
    ]


@pytest.fixture(scope="module")
def first_party() -> dict[str, str]:
    paths: list[Path] = []
    for root in _FIRST_PARTY:
        path = _REPO / root
        paths.extend([path] if path.is_file() else sorted(path.rglob("*.py")))
    return {str(path.relative_to(_REPO)): path.read_text(encoding="utf-8") for path in paths}


def test_no_function_declares_an_app_placeholder(first_party: dict[str, str]) -> None:
    assert _declarations_of("_app", first_party) == []


def test_the_placeholder_scan_reads_the_first_party_trees(first_party: dict[str, str]) -> None:
    """Control: the scan covers every tree, and finds a declaration where one is."""
    roots = {label.split("/", 1)[0] for label in first_party}
    assert roots == set(_FIRST_PARTY), roots
    assert sum(label.startswith("tests/") for label in first_party) > 500, len(first_party)
    inbound = {k: v for k, v in first_party.items() if k.startswith("adapters/inbound/")}
    assert len(_declarations_of("rt", inbound)) >= 150
    assert _declarations_of("_app", {"planted": "def f(_app, rt): ..."}) == ["planted:1 f"]
