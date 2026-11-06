"""Each domain backend defines every member of the protocol services type it against.

A protocol member no backend implements type-checks at its call site and raises
``AttributeError`` at runtime. Nothing else holds the two together: composition hands
backends over untyped, so this module is what says ``PsBackend`` is a ``PsOperations``.
The check reads the class, not an instance, so a member cannot pass by being resolved
dynamically.
"""

from __future__ import annotations

import inspect

import pytest

from adapters.persistence.neo4j.backends.activity_backends import (
    ChoicesBackend,
    EventsBackend,
    GoalsBackend,
    HabitsBackend,
    PrinciplesBackend,
    TasksBackend,
)
from adapters.persistence.neo4j.backends.curriculum_backends import (
    KuBackend,
    LpBackend,
    PsBackend,
)
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.ports import (
    ChoicesOperations,
    EventsOperations,
    GoalsOperations,
    HabitsOperations,
    KuOperations,
    LpOperations,
    PrinciplesOperations,
    PsOperations,
    TasksOperations,
)

_ABSENT = object()

_PAIRS: list[tuple[type, type]] = [
    (TasksBackend, TasksOperations),
    (GoalsBackend, GoalsOperations),
    (HabitsBackend, HabitsOperations),
    (EventsBackend, EventsOperations),
    (ChoicesBackend, ChoicesOperations),
    (PrinciplesBackend, PrinciplesOperations),
    (KuBackend, KuOperations),
    (PsBackend, PsOperations),
    (LpBackend, LpOperations),
]


def _protocol_members(protocol: type) -> set[str]:
    return {
        name
        for klass in protocol.__mro__
        if getattr(klass, "_is_protocol", False)
        for name, member in vars(klass).items()
        if not name.startswith("_") and inspect.isfunction(member)
    }


@pytest.mark.parametrize(
    ("backend", "protocol"), _PAIRS, ids=[backend.__name__ for backend, _ in _PAIRS]
)
def test_the_backend_defines_every_member_of_its_protocol(backend: type, protocol: type) -> None:
    members = _protocol_members(protocol)

    assert members, f"{protocol.__name__} read as empty, so this test would prove nothing"
    missing = sorted(
        name for name in members if inspect.getattr_static(backend, name, _ABSENT) is _ABSENT
    )
    assert not missing, f"{protocol.__name__} declares what {backend.__name__} lacks: {missing}"


def test_no_backend_answers_an_attribute_it_does_not_define() -> None:
    """A ``__getattr__`` here makes mypy accept any member on any backend."""
    assert "__getattr__" not in vars(UniversalNeo4jBackend)
