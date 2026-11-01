"""Route-module signatures: a route function declares exactly what its caller sends.

Two pins over ``adapters/inbound``:

* **No ``_sync_service``.** No function declares the parameter: bootstrap filled
  it with ``None`` and no body read it.
* **Every config binds its factories exactly.** ``register_domain_routes`` calls
  ``factory(app, rt, primary_service, **mapping)`` with the config's
  ``api_related_services`` / ``ui_related_services`` mapping. Each mapping key
  must name a parameter of its factory, each parameter after the first three
  without a default must have a key, and no factory may take ``**kwargs`` — a
  ``**kwargs`` sink there accepts a mistyped or misrouted key without a word.
"""

from __future__ import annotations

import ast
import inspect
from annotationlib import Format
from collections.abc import Callable
from pathlib import Path

import pytest

import adapters.inbound
from adapters.inbound.route_factories import DomainRouteConfig
from tests.helpers.route_configs import collect_module_configs

_INBOUND = Path(adapters.inbound.__file__).parent
_REPO = _INBOUND.parent.parent

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
    """How ``factory(app, rt, primary, **mapping)`` fails to bind exactly."""
    parameters = list(
        inspect.signature(factory, annotation_format=Format.FORWARDREF).parameters.values()
    )
    defects = [f"takes **{p.name}" for p in parameters if p.kind is inspect.Parameter.VAR_KEYWORD]
    injected = [p for p in parameters[3:] if p.kind in _NAMED_KINDS]
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


def _factory_with_a_sink(app: object, rt: object, primary: object, **_kwargs: object) -> None:
    pass


def _factory_needing_goals(app: object, rt: object, primary: object, goals_service: object) -> None:
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
