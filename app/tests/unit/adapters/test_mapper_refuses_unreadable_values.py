"""The backend's mapper reads every field as its declared type, or refuses the read.

``from_neo4j_node`` is every backend's node reader. A stored value its field's type
cannot read raises ``UnreadableStoredValueError`` naming the class, uid and field —
never a model holding the raw value, a default, or ``None`` for a required field.
Each conversion kind is pinned, with the three shapes a lax reader hands back without a
word (a non-string on an enum field, a non-temporal on a date field, an unmatched item in
an enum collection). The DTO path reads an enum string by
the same rule (``read_enum_value``), so one stored value answers the same on both.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any

import pytest

from adapters.persistence.neo4j.neo4j_mapper import (
    UnreadableStoredValueError,
    from_neo4j_node,
    unreadable_fields,
)
from core.models.dto_helpers import parse_enum_field
from core.models.enums import KuComplexity
from core.models.enums.entity_enums import EntityStatus
from core.models.event.event import Event
from core.models.goal.goal import Goal
from core.models.goal.milestone import Milestone
from core.models.ku.ku import Ku
from core.models.task.task import Task

_UID = "task_0123456789abcdef"


def _task(**properties: Any) -> dict[str, Any]:  # boundary: neo4j node properties
    return {
        "uid": _UID,
        "title": "Probe",
        "entity_type": "task",
        "user_uid": "user_x",
        **properties,
    }


def _refusal(
    node: dict[str, Any], entity_class: type
) -> UnreadableStoredValueError:  # boundary: node
    with pytest.raises(UnreadableStoredValueError) as refused:
        from_neo4j_node(node, entity_class)
    return refused.value


@pytest.mark.parametrize(
    ("field", "stored"),
    [
        pytest.param("status", "bogus", id="enum-string-outside-the-vocabulary"),
        pytest.param("status", 7, id="enum-holding-a-number"),
        pytest.param("status", "none", id="enum-required-read-as-absent"),
        pytest.param("due_date", "garbage", id="date-unparseable"),
        pytest.param("due_date", 20261114, id="date-holding-a-number"),
        pytest.param("created_at", "garbage", id="datetime-unparseable"),
        pytest.param("created_at", 3.5, id="datetime-holding-a-number"),
        pytest.param("tags", "[not json", id="collection-unparseable-json"),
        pytest.param("metadata", "[1, 2]", id="dict-whose-json-is-a-list"),
        pytest.param("metadata", 42, id="dict-holding-a-number"),
    ],
)
def test_a_value_its_type_cannot_read_refuses_the_read(field: str, stored: object) -> None:
    refusal = _refusal(_task(**{field: stored}), Task)

    assert (refusal.entity_class, refusal.uid, refusal.field, refusal.value) == (
        "Task",
        _UID,
        field,
        stored,
    )


def test_a_time_it_cannot_parse_refuses_the_read() -> None:
    refusal = _refusal(
        {
            "uid": "event_0123456789abcdef",
            "title": "E",
            "user_uid": "user_x",
            "start_time": "25:99",
        },
        Event,
    )

    assert refusal.field == "start_time"
    assert from_neo4j_node(
        {
            "uid": "event_0123456789abcdef",
            "title": "E",
            "user_uid": "user_x",
            "start_time": "09:30:00",
        },
        Event,
    ).start_time == time(9, 30)


def test_an_unauthored_optional_enum_written_none_reads_as_absent() -> None:
    ku = from_neo4j_node({"uid": "ku.test.x", "title": "X", "complexity": "none"}, Ku)

    assert ku.complexity is None


def test_a_nested_item_it_cannot_read_refuses_the_outer_read() -> None:
    """A milestone authored without its ``uid`` cannot build a ``Milestone``; the goal
    read refuses, naming the goal and its field, not the milestone."""
    node = {
        "uid": "goal_0123456789abcdef",
        "title": "G",
        "user_uid": "user_x",
        "milestones": '[{"title": "M1"}]',
    }

    refusal = _refusal(node, Goal)

    assert (refusal.entity_class, refusal.uid, refusal.field) == (
        "Goal",
        "goal_0123456789abcdef",
        "milestones",
    )


def test_a_nested_item_that_is_not_an_object_refuses_the_read() -> None:
    node = {
        "uid": "goal_0123456789abcdef",
        "title": "G",
        "user_uid": "user_x",
        "milestones": '["M1"]',
    }

    assert _refusal(node, Goal).field == "milestones"


def test_readable_values_still_read() -> None:
    task = from_neo4j_node(
        _task(
            status="ACTIVE",
            due_date="2026-11-14T09:00:00",
            created_at="2026-11-14T09:00:00+00:00",
            tags='["a", "b"]',
            metadata='{"k": 1}',
        ),
        Task,
    )
    milestones = from_neo4j_node(
        {
            "uid": "goal_x",
            "title": "G",
            "user_uid": "user_x",
            "milestones": '[{"uid": "ms.1", "title": "M1"}]',
        },
        Goal,
    ).milestones

    assert task.status is EntityStatus.ACTIVE
    assert task.due_date == date(2026, 11, 14)
    assert isinstance(task.created_at, datetime)
    assert task.tags == ("a", "b")
    assert task.metadata == {"k": 1}
    assert milestones == (Milestone(uid="ms.1", title="M1"),)


@dataclass(frozen=True)
class _Tagged:
    uid: str
    statuses: tuple[EntityStatus, ...] = ()


def test_an_enum_collection_item_outside_the_vocabulary_refuses_the_read() -> None:
    assert _refusal({"uid": "x", "statuses": '["active", "bogus"]'}, _Tagged).field == "statuses"
    assert _refusal({"uid": "x", "statuses": ["active", "bogus"]}, _Tagged).field == "statuses"


def test_an_enum_collection_reads_its_items_as_members() -> None:
    assert from_neo4j_node({"uid": "x", "statuses": ["active"]}, _Tagged).statuses == (
        EntityStatus.ACTIVE,
    )


def test_the_census_reads_every_refusal_without_stopping_at_the_first() -> None:
    refusals = unreadable_fields(_task(status="bogus", due_date="garbage", title="fine"), Task)

    assert sorted(refusal.field for refusal in refusals) == ["due_date", "status"]
    assert unreadable_fields(_task(status="active"), Task) == []


class TestBothPathsAnswerTheSame:
    """The mapper and a DTO's ``parse_enum_field`` read an enum string by one rule."""

    @pytest.mark.parametrize("stored", ["basic", "BASIC", "Basic"])
    def test_casing_and_member_names(self, stored: str) -> None:
        data = {"complexity": stored}
        parse_enum_field(data, "complexity", KuComplexity)
        ku = from_neo4j_node({"uid": "ku.test.x", "title": "X", "complexity": stored}, Ku)

        assert data["complexity"] is ku.complexity is KuComplexity.BASIC

    def test_an_alias_its_parser_knows(self) -> None:
        data = {"status": "pending"}
        parse_enum_field(data, "status", EntityStatus)

        assert data["status"] is from_neo4j_node(_task(status="pending"), Task).status

    def test_a_value_outside_the_vocabulary(self) -> None:
        with pytest.raises(ValueError):
            parse_enum_field({"complexity": "bogus"}, "complexity", KuComplexity)
        with pytest.raises(UnreadableStoredValueError):
            from_neo4j_node({"uid": "ku.test.x", "title": "X", "complexity": "bogus"}, Ku)

    def test_a_required_status_written_none(self) -> None:
        with pytest.raises(ValueError):
            parse_enum_field({"status": "none"}, "status", EntityStatus)
        with pytest.raises(UnreadableStoredValueError):
            from_neo4j_node(_task(status="none"), Task)


def test_the_refusal_is_not_taken_for_bad_input() -> None:
    """Not a ``ValueError``: ``with_error_handling`` would answer it as a validation
    failure, and a ``DATA_CONVERSION_EXCEPTIONS`` catch would swallow it."""
    from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS

    assert not issubclass(UnreadableStoredValueError, DATA_CONVERSION_EXCEPTIONS)
