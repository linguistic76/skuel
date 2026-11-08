"""No JSON response carries an entity's embedding fields.

``jsonable_content`` is the JSON boundary every ``Result`` route answers through. Every
``Entity`` it serializes leaves out ``embedding``, ``embedding_model`` and
``embedding_updated_at``, wherever the entity sits in the value: alone, in a list, in a
list route's payload, or inside a dataclass a context or insights route returns. The
keys are absent, not null. Everything else serializes as ``to_jsonable_python`` would.
The model itself keeps the fields, because AI ranking reads ``entity.embedding``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType

import pytest
from pydantic_core import to_jsonable_python

from adapters.inbound.boundary import ENTITY_EMBEDDING_FIELDS, jsonable_content
from core.models.goal.goal import Goal
from core.models.task.task import Task

_KEYS = frozenset({"embedding", "embedding_model", "embedding_updated_at"})

_EMBEDDED = {
    "embedding": tuple([0.25] * 1024),
    "embedding_model": "text-embedding-3-small",
    "embedding_updated_at": datetime(2026, 11, 7, 12, tzinfo=UTC),
}


def _task(uid: str = "task_0000000000000001") -> Task:
    return Task(
        uid=uid,
        title="Embedded",
        user_uid="user_0000000000000001",
        metadata={"source": "embedded"},  # held as a MappingProxyType
        **_EMBEDDED,
    )


def _expected(entity: Task | Goal) -> dict[str, object]:
    """``to_jsonable_python``'s answer for ``entity``, minus the three keys."""
    full = to_jsonable_python(entity, fallback=dict)
    return {key: value for key, value in full.items() if key not in _KEYS}


@dataclass(frozen=True)
class _Context:
    """The shape of a context route's answer: an entity with what surrounds it."""

    entity: Task
    related: tuple[Goal, ...]
    note: str


def test_the_fields_left_out_are_the_three_entity_declares() -> None:
    assert ENTITY_EMBEDDING_FIELDS == _KEYS


def test_an_embedded_entity_answers_without_the_three_keys() -> None:
    task = _task()
    body = jsonable_content(task)
    assert _KEYS.isdisjoint(body)
    assert body == _expected(task)
    assert task.embedding is not None  # the model keeps them


_FIRST, _SECOND = _task(), _task("task_0000000000000002")


@pytest.mark.parametrize(
    ("value", "rows_key"),
    [
        pytest.param([_FIRST, _SECOND], None, id="list"),
        pytest.param((_FIRST, _SECOND), None, id="tuple"),
        pytest.param(
            {"items": [_FIRST, _SECOND], "total": 2, "limit": 100, "offset": 0},
            "items",
            id="list-payload",
        ),
        pytest.param(MappingProxyType({"tasks": [_FIRST, _SECOND]}), "tasks", id="mapping-proxy"),
    ],
)
def test_every_entity_in_a_container_leaves_them_out(value: object, rows_key: str | None) -> None:
    body = jsonable_content(value)
    rows = body if rows_key is None else body[rows_key]
    assert rows == [_expected(_FIRST), _expected(_SECOND)]


def test_an_entity_inside_a_dataclass_leaves_them_out() -> None:
    goal = Goal(
        uid="goal_0000000000000001", title="Goal", user_uid="user_0000000000000001", **_EMBEDDED
    )
    body = jsonable_content({"context": _Context(entity=_FIRST, related=(goal,), note="n")})
    assert body == {
        "context": {"entity": _expected(_FIRST), "related": [_expected(goal)], "note": "n"}
    }


def test_a_value_holding_no_entity_serializes_as_before() -> None:
    @dataclass(frozen=True)
    class _Row:
        uid: str
        scores: MappingProxyType[str, float]
        at: datetime

    value = {"rows": (_Row("r", MappingProxyType({"a": 1.0}), _EMBEDDED["embedding_updated_at"]),)}
    assert jsonable_content(value) == to_jsonable_python(value, fallback=dict)
