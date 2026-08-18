"""Guard: every event class defined under ``core/events/`` reaches EVENT_REGISTRY.

WHY THIS EXISTS
---------------
``EVENT_REGISTRY`` is no longer hand-maintained. ``event_type`` is a
``ClassVar[str]`` on every event, so ``core/events/__init__.py`` derives the
mapping by walking ``BaseEvent.__subclasses__()`` transitively. That makes the
kind of drift this replaced — 92 hand-listed entries against 102 defined
classes, spotted by ``./dev bloat`` on 2026-08-17 — unrepresentable.

It leaves exactly one hole, and it is the hole the original drift fell through.
A comprehension over ``__subclasses__()`` can only see classes that have been
*imported*. Four of the ten missing events (``ExerciseCreated``,
``GroupCreated``, ``GroupMemberAdded``, ``GroupMemberRemoved``) did not exist at
runtime from ``import core.events`` at all, because ``__init__.py`` imported 17
of the 19 event modules and no static tool had a reason to notice the other two.
Adding a new ``core/events/foo_events.py`` and forgetting the import here would
reproduce that silently.

So this test does not trust the import graph. It parses every file under
``core/events/`` with ``ast`` — imports irrelevant — closes the inheritance
relation over ``BaseEvent`` transitively, and asserts the file-level truth
matches the runtime registry exactly.

WHY NOT THE OTHER GUARDS
------------------------
- ``./dev bloat`` computes the same AST universe and prints it beside the
  registry size, but the bloat report is advisory by contract and CI runs only
  ``detect_bloat.py --check``. Advisory is the right register for a report;
  a contract wants a test.
- ``tests/unit/test_package_exports.py`` (#1082) checks ``__all__`` -> module
  and never the inverse, so it cannot see a class the package forgot to
  advertise. The ``__all__`` completeness assertion below is deliberately kept
  here, scoped to ``core/events``, rather than inverting that repo-wide guard:
  plenty of packages legitimately import names they do not re-export.
"""

from __future__ import annotations

import ast
from pathlib import Path

import core.events
from core.events import EVENT_REGISTRY
from core.events.base import BaseEvent

EVENTS_DIR = Path(__file__).resolve().parents[2] / "core" / "events"
ROOT_BASE = "BaseEvent"


def _base_name(node: ast.expr) -> str | None:
    """Terminal name of a class base expression (``X`` or ``mod.X``)."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _defined_event_classes() -> dict[str, str]:
    """AST-derived {class name: event_type} for every event under core/events/.

    Pure file truth — never imports. Closure is transitive so indirect
    descendants (the 14 ``*EmbeddingRequested`` classes under
    ``EmbeddingRequested``) are included.
    """
    bases: dict[str, list[str]] = {}
    literals: dict[str, str] = {}

    for path in sorted(EVENTS_DIR.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.ClassDef):
                continue
            bases[node.name] = [b for b in map(_base_name, node.bases) if b]
            for item in node.body:
                if (
                    isinstance(item, ast.AnnAssign)
                    and isinstance(item.target, ast.Name)
                    and item.target.id == "event_type"
                    and isinstance(item.value, ast.Constant)
                    and isinstance(item.value.value, str)
                ):
                    literals[node.name] = item.value.value

    universe = {ROOT_BASE}
    changed = True
    while changed:
        changed = False
        for cls, cls_bases in bases.items():
            if cls not in universe and universe.intersection(cls_bases):
                universe.add(cls)
                changed = True
    universe.discard(ROOT_BASE)

    return {cls: literals[cls] for cls in universe if cls in literals}


def test_every_defined_event_is_registered() -> None:
    """No event class may exist on disk and be absent from the registry."""
    defined = _defined_event_classes()
    registered = {cls.__name__ for cls in EVENT_REGISTRY.values()}

    missing = sorted(set(defined) - registered)
    assert not missing, (
        f"{len(missing)} event class(es) defined under core/events/ never reach "
        f"EVENT_REGISTRY: {missing}. Most likely core/events/__init__.py does not "
        f"import the module that defines them — a comprehension over "
        f"__subclasses__() can only see imported classes."
    )


def test_every_defined_event_declares_its_own_event_type() -> None:
    """A ClassVar literal on the class itself, not one inherited from a base.

    ``BaseEvent.__init_subclass__`` enforces this at runtime; asserting it here
    too means a missing declaration fails as a readable list rather than as an
    import-time TypeError from whichever test imported first.
    """
    defined = _defined_event_classes()
    bases: dict[str, list[str]] = {}
    for path in sorted(EVENTS_DIR.rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ClassDef):
                bases[node.name] = [b for b in map(_base_name, node.bases) if b]

    subclasses = {
        cls for cls, bs in bases.items() if ROOT_BASE in bs or any(b in defined for b in bs)
    }
    undeclared = sorted(subclasses - set(defined))
    assert not undeclared, (
        f"Event class(es) with no own event_type ClassVar: {undeclared}. "
        f'Declare event_type: ClassVar[str] = "{{domain}}.{{action}}".'
    )


def test_registry_keys_match_class_literals() -> None:
    """Each key is its class's own declared literal — no aliasing, no typos."""
    mismatched = {key: cls.__name__ for key, cls in EVENT_REGISTRY.items() if cls.event_type != key}
    assert not mismatched, f"Registry keys diverge from their class literals: {mismatched}"


def test_event_types_are_unique() -> None:
    """Two events sharing an event_type would silently collide in the dict.

    The comprehension keeps whichever class is walked last, so a duplicate
    would drop an event from the registry without any error.
    """
    defined = _defined_event_classes()
    assert len(set(defined.values())) == len(defined), (
        "Duplicate event_type literals — the registry comprehension would drop one"
    )
    assert len(EVENT_REGISTRY) == len(defined)


def test_every_event_class_is_exported() -> None:
    """__all__ must advertise every event — the inverse of the #1082 guard.

    ``test_package_exports.py`` proves every advertised name resolves; nothing
    proves every resolvable event is advertised. The same 10 classes that
    drifted out of EVENT_REGISTRY were also missing from ``__all__``.
    """
    unexported = sorted(set(_defined_event_classes()) - set(core.events.__all__))
    assert not unexported, f"Event class(es) missing from core.events.__all__: {unexported}"


def test_base_event_itself_has_no_event_type() -> None:
    """The base declares the ClassVar without assigning it.

    A default on ``BaseEvent`` would let a subclass inherit a type instead of
    declaring one, which is the failure ``__init_subclass__`` exists to prevent.
    """
    assert "event_type" not in BaseEvent.__dict__
