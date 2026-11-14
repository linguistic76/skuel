"""A write never stores a value its field's type cannot read.

``to_neo4j_node`` (a model) and ``to_neo4j_patch`` (a partial update) read every
property they serialize for a field of the class by the read's own rule, and refuse
the write (``UnstorableValueError``) before anything is stored — so no write leaves a
node that every later read refuses (``UnreadableStoredValueError``). An enum field is
stored as its member's value; a key that names no field passes. The vault door refuses
one file, not its batch (``prepare_batch_items``).
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from adapters.persistence.neo4j.batch_preparer import prepare_batch_items
from adapters.persistence.neo4j.neo4j_mapper import (
    UnreadableStoredValueError,
    UnstorableValueError,
    _field_specs,
    from_neo4j_node,
    to_neo4j_node,
    to_neo4j_patch,
)
from core.models.entity_types import ENTITY_TYPE_CLASS_MAP
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.event.event import Event
from core.models.forms.form_template_request import FormTemplateUpdateRequest
from core.models.goal.goal import Goal
from core.models.pathways.path_step import PathStep
from core.models.task.task import Task
from core.services.ingestion.config import ENTITY_CONFIGS, ingested_model_class
from core.services.ingestion.preparer import prepare_entity_data
from core.utils.error_boundary import safe_backend_operation
from core.utils.exception_types import DATA_CONVERSION_EXCEPTIONS, UnreadableValueError
from core.utils.result_simplified import ErrorCategory, Result
from tests.helpers.ingestion_owner import INGESTION_TEST_OWNER

_UID = "task_0123456789abcdef"
_OWNER = "user_0123456789abcdef"


def _refusal(
    changes: dict[str, Any], entity_class: type = Task
) -> UnstorableValueError:  # boundary: a patch
    with pytest.raises(UnstorableValueError) as refused:
        to_neo4j_patch(changes, entity_class, uid=_UID)
    return refused.value


@pytest.mark.parametrize(
    ("entity_class", "field", "value"),
    [
        pytest.param(Task, "recurrence_pattern", "bogus", id="enum-outside-the-vocabulary"),
        pytest.param(Task, "status", 7, id="enum-holding-a-number"),
        pytest.param(Task, "due_date", "soon", id="date-unparseable"),
        pytest.param(Task, "created_at", "yesterday", id="datetime-unparseable"),
        pytest.param(Task, "tags", "work", id="collection-a-bare-string"),
        pytest.param(Task, "metadata", "hello", id="dict-not-json"),
        pytest.param(Task, "metadata", [1, 2], id="dict-holding-a-list"),
        pytest.param(Event, "start_time", "9am", id="time-unparseable"),
        pytest.param(Event, "start_time", datetime(2026, 11, 14, 9), id="time-holding-a-datetime"),
        pytest.param(Goal, "milestones", [{"title": "no uid"}], id="nested-item-missing-a-field"),
        pytest.param(Task, "title", None, id="null-on-a-field-that-requires-a-value"),
    ],
)
def test_a_value_its_type_cannot_read_refuses_the_patch(
    entity_class: type, field: str, value: object
) -> None:
    refusal = _refusal({field: value}, entity_class)

    assert (refusal.entity_class, refusal.uid, refusal.field) == (
        entity_class.__name__,
        _UID,
        field,
    )
    assert field in str(refusal)


@pytest.mark.parametrize(
    ("changes", "stored"),
    [
        pytest.param({"due_date": date(2026, 11, 20)}, {"due_date": "2026-11-20"}, id="a-date"),
        pytest.param({"due_date": None}, {"due_date": None}, id="a-null-on-an-optional-field"),
        pytest.param({"tags": None}, {"tags": None}, id="a-null-on-a-field-with-a-default"),
        pytest.param({"tags": ["work"]}, {"tags": ["work"]}, id="a-list"),
        pytest.param({"metadata": {"k": 1}}, {"metadata": '{"k": 1}'}, id="a-mapping"),
        pytest.param({"rescheduled_at": "x"}, {"rescheduled_at": "x"}, id="a-key-naming-no-field"),
    ],
)
def test_a_value_its_type_reads_is_stored_as_serialized(
    changes: dict[str, Any], stored: dict[str, Any]
) -> None:
    assert to_neo4j_patch(changes, Task, uid=_UID) == stored


@pytest.mark.parametrize(
    ("authored", "stored"),
    [
        pytest.param("WEEKLY", "weekly", id="casing"),
        pytest.param("Weekly", "weekly", id="mixed-casing"),
    ],
)
def test_an_enum_is_stored_as_its_members_value(authored: str, stored: str) -> None:
    assert to_neo4j_patch({"recurrence_pattern": authored}, Task)["recurrence_pattern"] == stored


def test_an_enum_alias_is_stored_as_the_member_it_names() -> None:
    assert to_neo4j_patch({"status": "pending"}, Task)["status"] == "draft"


def test_a_model_holding_a_value_of_another_type_refuses_the_write() -> None:
    event = Event(
        uid="event_0123456789abcdef", title="E", user_uid=_OWNER, start_time=datetime.now()
    )  # type: ignore[arg-type]  # the wrong type is the point

    with pytest.raises(UnstorableValueError) as refused:
        to_neo4j_node(event)

    assert (refused.value.entity_class, refused.value.field) == ("Event", "start_time")


def test_a_model_holding_its_own_types_is_stored() -> None:
    task = Task(uid=_UID, title="T", user_uid=_OWNER, due_date=date(2026, 11, 20))

    assert to_neo4j_node(task)["due_date"] == "2026-11-20"


def test_a_patch_is_not_a_model() -> None:
    with pytest.raises(TypeError):
        to_neo4j_node({"title": "T"})


def test_the_refusal_is_not_taken_for_bad_input() -> None:
    assert issubclass(UnstorableValueError, UnreadableValueError)
    assert issubclass(UnreadableStoredValueError, UnreadableValueError)
    assert not issubclass(UnreadableValueError, DATA_CONVERSION_EXCEPTIONS)


@pytest.mark.asyncio
async def test_a_backend_operation_answers_a_refusal_with_its_own_words() -> None:
    @safe_backend_operation("update")
    async def write() -> Result[None]:
        to_neo4j_patch({"due_date": "soon"}, Task, uid=_UID)
        return Result.ok(None)

    result = await write()

    assert result.is_error
    error = result.expect_error()
    assert error.category is ErrorCategory.SYSTEM
    assert "due_date" in error.message and _UID in error.message


@pytest.mark.asyncio
async def test_the_backend_boundary_logs_a_write_refusal_and_not_a_read_one_again(
    caplog: pytest.LogCaptureFixture,
) -> None:
    @safe_backend_operation("update")
    async def write() -> Result[None]:
        to_neo4j_patch({"due_date": "soon"}, Task, uid=_UID)
        return Result.ok(None)

    @safe_backend_operation("get")
    async def read() -> Result[None]:
        raise UnreadableStoredValueError(Task, _UID, "due_date", "soon", "not a date")

    with caplog.at_level("ERROR", logger="core.utils.error_boundary"):
        await write()
        await read()

    refusals = [r for r in caplog.records if r.name == "core.utils.error_boundary"]
    assert [r.getMessage().split(":")[0] for r in refusals] == ["Backend operation update refused"]


def test_a_node_missing_a_field_that_requires_a_value_refuses_the_read() -> None:
    with pytest.raises(UnreadableStoredValueError) as refused:
        from_neo4j_node({"uid": _UID, "user_uid": _OWNER}, Task)

    assert (refused.value.field, refused.value.value) == ("title", None)


def test_a_class_resolves_its_fields_once() -> None:
    assert _field_specs(Task) is _field_specs(Task)


class TestTheVaultDoorRefusesTheFileNotTheBatch:
    def test_an_entity_holding_an_unreadable_value_is_left_out(self) -> None:
        good = {"uid": "task.good", "title": "Good", "user_uid": _OWNER, "due_date": "2026-11-20"}
        bad = {"uid": "task.bad", "title": "Bad", "user_uid": _OWNER, "due_date": "soon"}

        items, refused = prepare_batch_items([good, bad], Task)

        assert [item["uid"] for item in items] == ["task.good"]
        assert [(refusal.uid, refusal.field) for refusal in refused] == [("task.bad", "due_date")]

    @pytest.mark.parametrize("authored", ["unknown", "2026-13-45", ["a", "b"], 12345])
    def test_an_unparseable_created_at_is_refused(self, authored: object) -> None:
        prepared = prepare_entity_data(
            EntityType.PATH_STEP,
            {"type": "lesson", "title": "T", "uid": "ps.x.y", "created_at": authored},
            "body",
            Path("t.md"),
            INGESTION_TEST_OWNER,
        )

        items, refused = prepare_batch_items([prepared], PathStep)

        assert items == []
        assert [refusal.field for refusal in refused] == ["created_at"]

    @pytest.mark.parametrize(
        "authored",
        [
            "2026-03-29T00:00:00Z",
            "2026-03-29T00:00:00+00:00",
            "2026-03-29",
            datetime(2026, 3, 29),
            date(2026, 3, 29),
        ],
    )
    def test_a_created_at_the_read_takes_is_written(self, authored: object) -> None:
        prepared = prepare_entity_data(
            EntityType.PATH_STEP,
            {"type": "lesson", "title": "T", "uid": "ps.x.y", "created_at": authored},
            "body",
            Path("t.md"),
            INGESTION_TEST_OWNER,
        )

        items, refused = prepare_batch_items([prepared], PathStep)

        assert refused == []
        assert len(items) == 1

    def test_every_ingested_type_names_the_class_its_nodes_are_read_as(self) -> None:
        for entity_type in ENTITY_CONFIGS:
            model_class = ingested_model_class(entity_type)
            if isinstance(entity_type, EntityType):
                assert model_class is ENTITY_TYPE_CLASS_MAP[entity_type]


class TestFormTemplateStatusIsReadAtTheBoundary:
    @pytest.mark.parametrize("status", ["bogus", "paused"])
    def test_a_status_a_form_template_cannot_hold_is_refused(self, status: str) -> None:
        with pytest.raises(ValueError):
            FormTemplateUpdateRequest(status=status)  # type: ignore[arg-type]  # the wire value

    def test_a_status_it_can_hold_is_read_as_the_enum(self) -> None:
        assert FormTemplateUpdateRequest(status="archived").status is EntityStatus.ARCHIVED  # type: ignore[arg-type]  # the wire value
