"""No test or script builds a backend the composition root builds, except through it.

``create_all_backends`` (``services_bootstrap/_backends.py``) is the one constructor
of every backend the application runs: which class serves a domain or a service
family, under which label, over which base label and entity class, over the driver
or the shared executor. A test or script that copies those arguments runs a backend
production never runs the moment the two drift — a generic
``UniversalNeo4jBackend[Task]`` lacks every read ``TasksBackend`` adds, and an
``"Entity"``-labelled one writes nodes no production writer makes. So a test gets
its backend from ``build_production_backends(driver)`` (``tests/helpers``) or the
``production_backends`` fixture, both of which call ``create_all_backends``; a
script opens its own driver and takes its backend from
``create_all_backends(driver, Neo4jQueryExecutor(driver))["<key>"]``.

The set this census refuses is read from ``create_all_backends`` itself, called over
a mock driver — a backend added there is covered here without an edit:

- a call to any class it returns other than ``UniversalNeo4jBackend``
  (``TasksBackend(...)``, ``UserBackend(...)``, ``CrossDomainBackend(executor)``);
- a ``UniversalNeo4jBackend`` call whose label is one a production backend carries,
  primary or base (``"Entity"``), or whose entity class is one a production backend
  serves (``UniversalNeo4jBackend[HabitCompletion](driver, ..., HabitCompletion)``).

A generic backend over a test's own model and label (``SampleTask``) is not refused:
it tests the generic class, not a domain. Nor is a backend only a script builds
(``TelemetryRetentionBackend``): ``create_all_backends`` does not return it.
"""

from __future__ import annotations

import ast
from enum import Enum
from pathlib import Path
from unittest.mock import MagicMock

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums.neo_labels import NeoLabel
from services_bootstrap._backends import create_all_backends

TESTS_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = TESTS_ROOT.parent
SCRIPTS_ROOT = APP_ROOT / "scripts"

_GENERIC = UniversalNeo4jBackend.__name__


def _label_value(label: object) -> str | None:
    if label is None:
        return None
    return str(label.value) if isinstance(label, Enum) else str(label)


def _production_shape() -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    """The subclass names, labels and entity class names ``create_all_backends`` builds."""
    backends = create_all_backends(MagicMock(), MagicMock()).values()
    classes = frozenset(type(b).__name__ for b in backends) - {_GENERIC}
    labels = frozenset(
        value
        for b in backends
        for value in (
            _label_value(getattr(b, "label", None)),
            _label_value(getattr(b, "base_label", None)),
        )
        if value
    )
    entity_classes = frozenset(
        b.entity_class.__name__ for b in backends if getattr(b, "entity_class", None)
    )
    return classes, labels, entity_classes


PRODUCTION_CLASSES, PRODUCTION_LABELS, PRODUCTION_ENTITY_CLASSES = _production_shape()


def _callee(func: ast.expr) -> tuple[str | None, str | None]:
    """The class a call constructs, and the subscripted type when it is ``X[T](...)``."""
    subscript = None
    if isinstance(func, ast.Subscript):
        if isinstance(func.slice, ast.Name):
            subscript = func.slice.id
        func = func.value
    if isinstance(func, ast.Name):
        return func.id, subscript
    if isinstance(func, ast.Attribute):
        return func.attr, subscript
    return None, subscript


def _argument(call: ast.Call, position: int, keyword: str) -> ast.expr | None:
    for kw in call.keywords:
        if kw.arg == keyword:
            return kw.value
    return call.args[position] if len(call.args) > position else None


def _literal_label(node: ast.expr | None) -> str | None:
    """A label written as a string or as ``NeoLabel.X``; ``None`` for anything computed."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == NeoLabel.__name__
        and node.attr in NeoLabel.__members__
    ):
        return NeoLabel[node.attr].value
    return None


def is_production_copy(call: ast.Call) -> bool:
    """Whether ``call`` builds, by hand, a backend ``create_all_backends`` builds."""
    name, subscript = _callee(call.func)
    if name in PRODUCTION_CLASSES:
        return True
    if name != _GENERIC:
        return False
    entity = _argument(call, 2, "entity_class")
    entity_name = entity.id if isinstance(entity, ast.Name) else subscript
    label = _literal_label(_argument(call, 1, "label"))
    return label in PRODUCTION_LABELS or entity_name in PRODUCTION_ENTITY_CLASSES


def production_copies(source: str) -> list[ast.Call]:
    """Every call in ``source`` that builds a production backend by hand."""
    return [
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and is_production_copy(node)
    ]


def test_create_all_backends_is_read() -> None:
    """A census over an empty set refuses nothing; the set must hold what it claims."""
    assert {
        "TasksBackend",
        "UserBackend",
        "ConnectionFetchBackend",
        "CrossDomainBackend",
        "VectorSearchBackend",
        "BulkUpsertBackend",
        "LpBackend",
        "SharingBackend",
    } <= PRODUCTION_CLASSES
    assert {"Task", "Entity", "HabitCompletion", "User", "Group", "Exercise"} <= PRODUCTION_LABELS
    assert {"Task", "HabitCompletion", "PathStep", "LearningPath", "FormTemplate"} <= (
        PRODUCTION_ENTITY_CLASSES
    )


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def _offenders(root: Path) -> list[str]:
    return [
        f"{path.relative_to(APP_ROOT)}:{call.lineno}"
        for path in _python_files(root)
        for call in production_copies(path.read_text(encoding="utf-8"))
    ]


def test_each_root_is_walked() -> None:
    """A walk over the wrong directory finds no copy and passes; each root must hold its files."""
    assert Path(__file__).resolve() in _python_files(TESTS_ROOT)
    assert SCRIPTS_ROOT / "uid_census.py" in _python_files(SCRIPTS_ROOT)


def test_no_test_builds_a_production_backend_by_hand() -> None:
    offenders = _offenders(TESTS_ROOT)
    assert not offenders, (
        "These build a backend the composition root builds, by hand. Take it from "
        'build_production_backends(driver)["<key>"] (tests/helpers/production_backends.py) '
        "or the production_backends fixture:\n  " + "\n  ".join(offenders)
    )


def test_no_script_builds_a_production_backend_by_hand() -> None:
    offenders = _offenders(SCRIPTS_ROOT)
    assert not offenders, (
        "These build a backend the composition root builds, by hand. Take it from "
        'create_all_backends(driver, Neo4jQueryExecutor(driver))["<key>"] '
        "(services_bootstrap/_backends.py):\n  " + "\n  ".join(offenders)
    )


def test_the_census_refuses_each_copy() -> None:
    """Each shape the census names is found; a walk that finds nothing proves nothing."""
    refused = [
        "TasksBackend(driver, NeoLabel.TASK, Task, base_label=NeoLabel.ENTITY)",
        "backends.KuBackend(driver, NeoLabel.KU, Ku, base_label=NeoLabel.ENTITY)",
        "UserBackend(neo4j_driver)",
        "ConnectionFetchBackend(executor)",
        "CrossDomainBackend(Neo4jQueryExecutor(neo4j_driver))",
        "VectorSearchBackend(executor=executor)",
        "EmbeddingsBackend(executor=Neo4jQueryExecutor(driver))",
        "SessionBackend(driver)",
        "BulkUpsertBackend(neo4j_driver)",
        "SharingBackend(driver, NeoLabel.ENTITY, Entity, base_label=NeoLabel.ENTITY)",
        "UniversalNeo4jBackend[Group](driver, NeoLabel.GROUP, Group)",
        "UniversalNeo4jBackend[Task](driver, NeoLabel.TASK, Task, base_label=NeoLabel.ENTITY)",
        "UniversalNeo4jBackend(driver, NeoLabel.TASK, Task)",
        'UniversalNeo4jBackend[GoalDTO](driver, "Entity", GoalDTO)',
        "UniversalNeo4jBackend[Curriculum](driver, 'PathStep', Curriculum, base_label='Entity')",
        "UniversalNeo4jBackend[HabitCompletion](d, NeoLabel.HABIT_COMPLETION, HabitCompletion)",
        "UniversalNeo4jBackend[Askesis](driver=d, label='Askesis', entity_class=Askesis)",
    ]
    for sample in refused:
        assert len(production_copies(sample)) == 1, sample


def test_the_census_passes_a_generic_backend_over_a_test_model() -> None:
    passed = [
        "UniversalNeo4jBackend[SampleTask](driver=d, label='SampleTask', entity_class=SampleTask)",
        "UniversalNeo4jBackend[Example](driver, 'Example', Example, validate_label=False)",
        'build_production_backends(neo4j_driver)["tasks_backend"]',
        'create_all_backends(driver, Neo4jQueryExecutor(driver))["uid_census_backend"]',
        "TelemetryRetentionBackend(executor)",
        "MagicMock(spec=TasksBackend)",
    ]
    for sample in passed:
        assert production_copies(sample) == [], sample
