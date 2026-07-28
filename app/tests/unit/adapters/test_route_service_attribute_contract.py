"""
Wiring guard: a route factory may not read a service attribute that does not exist.

WHY THIS GUARD EXISTS
---------------------
``adapters/inbound/timeline_routes.py`` shipped two registered endpoints
(``/api/tasks/timeline`` and ``/api/tasks/timeline/preview``) whose handlers both
called ``tasks_service.export_to_markwhen(...)``. ``TasksService`` has never had
that method — ``git log -S export_to_markwhen`` returns exactly one commit (the
initial import), and that commit's tree contains the two call sites and no
definition. Both endpoints raised ``AttributeError`` on every request from the
day the repository was created, and every gate stayed green for eighteen months.

Three mechanisms that *look* like they should have caught it, and why none did:

1. **MyPy.** The injected service was annotated ``Any``
   (``def create_timeline_api_routes(_app, rt, tasks_service: Any)``), and ``Any``
   absorbs every attribute read. Note this is not fixable by annotating the
   parameter alone: ``register_domain_routes`` calls
   ``config.api_factory(app, rt, primary_service, **api_related)`` where
   ``primary_service`` came out of ``getattr(services, ...)``, so the concrete
   type is only recoverable from the ``Services`` container's own annotations —
   which is exactly what this guard reads.

2. **The route tests.** The house harness (``tests/unit/adapters/test_*_api_routes.py``)
   injects a bare ``MagicMock()``. An unspecced ``MagicMock`` answers *every*
   attribute, so a handler calling a method that exists nowhere is
   indistinguishable from one calling a real method. That test tranche is
   structurally blind to this defect class — and timeline_routes.py had no tests
   at all.

3. **The bloat detector.** ``scripts/detect_bloat.py`` finds *definitions with no
   callers*. This is the mirror image — a *call with no definition* — so no
   detector in the tree was looking in this direction.

WHAT IS CHECKED
---------------
For every module-level ``DomainRouteConfig`` in ``adapters/inbound``:

* resolve ``primary_service_attr`` through the ``Services`` container's
  annotations to the class the composition root injects;
* take the third positional parameter of ``api_factory`` / ``ui_factory``
  (``register_domain_routes`` passes the primary service there positionally);
* AST-collect every ``<that param>.<attr>`` read inside the factory;
* assert each ``<attr>`` is reachable on the class.

"Reachable" is ``dir(cls)`` **plus** every ``self.<name> = ...`` target across the
MRO's source. The class-only form is unsound: sub-service handles like
``.core`` / ``.intelligence`` / ``.completions`` are bound in ``__init__``, and
checking ``hasattr(cls, ...)`` alone reports 24 false positives against 1 real
defect.

COVERAGE BOUND (deliberate, not silent)
---------------------------------------
Configs whose ``Services`` annotation is a **Protocol** (``*Operations``) are
skipped: the concrete object the composition root builds is wider than the
protocol names, so a miss there is ISP drift rather than an ``AttributeError``,
and it cannot be adjudicated without resolving the composition root. At the time
of writing that is 16 configs skipped against 41 factories checked.
``test_audit_coverage_floor`` pins the checked count so the audit cannot quietly
go vacuous, and ``test_audit_detects_a_planted_missing_attribute`` proves the
checker actually fires.
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
import sys
import textwrap
import typing
from dataclasses import dataclass
from pathlib import Path

import pytest

import adapters.inbound
from adapters.inbound.route_factories import DomainRouteConfig
from services_bootstrap._container import Services

# Measured floor: 41 factories over 26 concrete-service configs (2026-07-27).
# A floor, not an equality — new domains raise it, and a config migrating to a
# Protocol annotation lowers it by one. If this trips, read the skip reasons in
# the failure message before relaxing it.
_MIN_CHECKED_FACTORIES = 35


@dataclass(frozen=True)
class Read:
    """One ``<service param>.<attr>`` read inside a route factory."""

    module: str
    config: str
    factory: str
    expression: str
    service_class: str


@dataclass(frozen=True)
class Audit:
    missing: list[Read]
    checked: list[str]
    skipped: list[tuple[str, str]]


def _container_type_hints() -> dict[str, object]:
    """Resolve ``Services``' annotations, including its TYPE_CHECKING-only imports.

    ``services_bootstrap._container`` imports every service class under
    ``if TYPE_CHECKING``, so ``get_type_hints`` cannot resolve them from the
    module's runtime globals. Read the file's own import statements and import
    those modules for real rather than hand-maintaining a name -> class map.
    """
    module = sys.modules[Services.__module__]
    source_file = inspect.getsourcefile(Services)
    assert source_file is not None, "Services must have resolvable source"
    namespace = dict(vars(module))
    for node in ast.walk(ast.parse(Path(source_file).read_text(encoding="utf-8"))):
        if not isinstance(node, ast.If) or "TYPE_CHECKING" not in ast.unparse(node.test):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.ImportFrom) and sub.module:
                imported = importlib.import_module(sub.module)
                for alias in sub.names:
                    namespace[alias.asname or alias.name] = getattr(imported, alias.name)
    return typing.get_type_hints(Services, globalns=namespace)


def _strip_optional(annotation: object) -> object:
    """``X | None`` -> ``X``; anything else is returned unchanged."""
    args = typing.get_args(annotation)
    if not args:
        return annotation
    real = [arg for arg in args if arg is not type(None)]
    return real[0] if len(real) == 1 else None


def _reachable_attributes(cls: type) -> set[str]:
    """``dir(cls)`` plus every ``self.<name> = ...`` target across the MRO's source."""
    names = set(dir(cls))
    for base in cls.__mro__:
        if base is object:
            continue
        try:
            source = textwrap.dedent(inspect.getsource(base))
        except OSError, TypeError:
            continue
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Assign):
                targets: list[ast.expr] = list(node.targets)
            elif isinstance(node, ast.AnnAssign):
                targets = [node.target]
            else:
                continue
            for target in targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                ):
                    names.add(target.attr)
    return names


def _factory_definition(factory: object) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    try:
        source = textwrap.dedent(inspect.getsource(factory))  # type: ignore[arg-type]
    except OSError, TypeError:
        return None
    node = ast.parse(source).body[0]
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        return node
    return None


def _collect_module_configs() -> tuple[list[tuple[str, str, DomainRouteConfig]], list[str]]:
    """Every module-level ``DomainRouteConfig`` under ``adapters/inbound``."""
    configs: list[tuple[str, str, DomainRouteConfig]] = []
    import_failures: list[str] = []
    for info in pkgutil.iter_modules(adapters.inbound.__path__, "adapters.inbound."):
        try:
            module = importlib.import_module(info.name)
        except ImportError as exc:  # a route module that will not import is itself a defect
            import_failures.append(f"{info.name}: {exc}")
            continue
        for name, value in vars(module).items():
            if isinstance(value, DomainRouteConfig):
                configs.append((info.name, name, value))
    return configs, import_failures


def audit_configs(configs: list[tuple[str, str, DomainRouteConfig]]) -> Audit:
    """Check every factory's reads of its injected primary service."""
    hints = _container_type_hints()
    missing: list[Read] = []
    checked: list[str] = []
    skipped: list[tuple[str, str]] = []

    for module_name, config_name, config in configs:
        label = f"{module_name}.{config_name}"
        annotation = hints.get(config.primary_service_attr)
        service_class = _strip_optional(annotation) if annotation is not None else None
        if not isinstance(service_class, type):
            skipped.append((label, f"unresolvable Services annotation: {annotation!r}"))
            continue
        if getattr(service_class, "_is_protocol", False):
            skipped.append((label, f"{service_class.__name__} is a Protocol (see COVERAGE BOUND)"))
            continue
        if hasattr(service_class, "__getattr__"):
            skipped.append((label, f"{service_class.__name__} defines __getattr__"))
            continue

        reachable = _reachable_attributes(service_class)
        for kind in ("api_factory", "ui_factory"):
            factory = getattr(config, kind)
            if factory is None:
                continue
            definition = _factory_definition(factory)
            if definition is None:
                skipped.append((label, f"{kind} source unavailable"))
                continue
            params = [arg.arg for arg in definition.args.args]
            if len(params) < 3:
                skipped.append((label, f"{kind} takes fewer than 3 positional parameters"))
                continue
            service_param = params[2]
            checked.append(f"{label}.{kind} -> {service_class.__name__}")
            missing.extend(
                Read(
                    module=module_name,
                    config=config_name,
                    factory=kind,
                    expression=f"{service_param}.{node.attr}",
                    service_class=service_class.__name__,
                )
                for node in ast.walk(definition)
                if isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == service_param
                and node.attr not in reachable
            )

    return Audit(missing=missing, checked=checked, skipped=skipped)


@pytest.fixture(scope="module")
def audit() -> Audit:
    configs, import_failures = _collect_module_configs()
    assert not import_failures, "adapters/inbound modules failed to import:\n" + "\n".join(
        import_failures
    )
    assert configs, "no DomainRouteConfig found — config discovery is broken, not clean"
    return audit_configs(configs)


def test_no_route_factory_reads_a_nonexistent_service_attribute(audit: Audit) -> None:
    """Every attribute a route factory reads off its service must exist on it."""
    detail = "\n".join(
        f"  {read.module}.{read.config} [{read.factory}]: "
        f"{read.expression} — {read.service_class} has no such attribute"
        for read in audit.missing
    )
    assert not audit.missing, (
        "Route factories read service attributes that do not exist. Each of these "
        "raises AttributeError at request time:\n" + detail
    )


def test_audit_coverage_floor(audit: Audit) -> None:
    """The audit must not quietly stop checking things.

    Without this, a change that makes every config skip (a renamed container
    attribute, a factory signature shift) would leave the guard passing while
    checking nothing.
    """
    reasons = "\n".join(f"  {label}: {why}" for label, why in audit.skipped)
    assert len(audit.checked) >= _MIN_CHECKED_FACTORIES, (
        f"only {len(audit.checked)} route factories were checked, expected at least "
        f"{_MIN_CHECKED_FACTORIES}. Skip reasons:\n{reasons}"
    )


# --- non-vacuity proof ------------------------------------------------------
#
# A guard that has never been observed to fail may be checking nothing. Plant the
# exact shape of the defect this file exists for and assert the checker reports
# it. `tasks` resolves to the concrete TasksService, the same class the real
# timeline routes were injected with.


def _factory_reading_a_missing_method(_app: object, _rt: object, tasks_service: object) -> None:
    """Stand-in for the deleted markwhen handler — reads a method that does not exist."""
    tasks_service.export_to_markwhen()  # type: ignore[attr-defined]


def _factory_reading_a_real_sub_service(_app: object, _rt: object, tasks_service: object) -> None:
    """Control: `.core` is bound in __init__, not on the class — must NOT be reported."""
    tasks_service.core  # type: ignore[attr-defined]  # noqa: B018


def test_audit_detects_a_planted_missing_attribute() -> None:
    planted = DomainRouteConfig(
        domain_name="planted",
        primary_service_attr="tasks",
        api_factory=_factory_reading_a_missing_method,  # type: ignore[arg-type]
    )
    result = audit_configs([("tests.planted", "PLANTED_CONFIG", planted)])

    assert len(result.checked) == 1, f"planted config was skipped, not checked: {result.skipped}"
    assert [read.expression for read in result.missing] == ["tasks_service.export_to_markwhen"]


def test_audit_does_not_flag_an_init_bound_sub_service() -> None:
    """The `self.<name> = ...` half of the reachability set is load-bearing."""
    planted = DomainRouteConfig(
        domain_name="planted",
        primary_service_attr="tasks",
        api_factory=_factory_reading_a_real_sub_service,  # type: ignore[arg-type]
    )
    result = audit_configs([("tests.planted", "PLANTED_CONFIG", planted)])

    assert len(result.checked) == 1, f"planted config was skipped, not checked: {result.skipped}"
    assert not result.missing, f"`.core` is bound in TasksService.__init__: {result.missing}"
