"""Node state: the properties a node carries that its class does not declare.

The registry (``core/models/node_state.py``) is what the stored-value census reads a
stored key against: a key that is neither a field nor registered node state of its
node's class is one no read reads. These pin the registry's shape — a registered key is
no field, a class reads its bases' registrations, each shared group has one source — the
mapper's two reads of it, and the poller's WARNING.
"""

from __future__ import annotations

from dataclasses import fields

import pytest

from adapters.persistence.neo4j.neo4j_mapper import (
    UnknownFieldError,
    to_neo4j_node,
    undeclared_keys,
)
from adapters.persistence.neo4j.stored_value_census_backend import mapper_readers
from core.infrastructure.monitoring import stored_value_check
from core.infrastructure.monitoring.stored_value_check import (
    UndeclaredStoredKeys,
    check_undeclared_keys,
)
from core.models.curriculum import SUBSTANCE_COUNTERS, SUBSTANCE_TIMESTAMPS, Curriculum
from core.models.enums import Domain
from core.models.enums.learning_enums import SELCategory
from core.models.habit.habit import Habit
from core.models.habit.learning_state import HABIT_LEARNING_PROPERTIES
from core.models.ku.ku import Ku
from core.models.node_state import EMBEDDING_STAMPS, GROUNDING_STAMPS, node_state
from core.models.pathways.path_step import PathStep
from core.models.task.task import Task
from core.models.user.learning_state import (
    TASK_DURATION_LEARNING_PROPERTIES,
    TEACHER_FEEDBACK_PROPERTIES,
)
from core.models.user.user import User
from core.models.user_entry.user_entry import UserEntry
from core.services import ps_service
from tests.helpers.production_backends import build_production_backends


def _field_names(cls: type) -> set[str]:
    return {f.name for f in fields(cls)}


def _census_classes() -> list[type]:
    backends = build_production_backends(object())
    return [cls for _, cls in mapper_readers(backends.values())]


@pytest.mark.parametrize("cls", _census_classes(), ids=lambda cls: cls.__name__)
def test_a_registered_key_is_no_field_of_its_class(cls: type) -> None:
    assert node_state(cls) & _field_names(cls) == set()


def test_node_state_is_no_dataclass_field() -> None:
    assert "NODE_STATE" not in _field_names(Task)
    assert "NODE_STATE" not in _field_names(User)


def test_a_class_reads_its_bases_registrations() -> None:
    assert node_state(Task) >= EMBEDDING_STAMPS
    assert node_state(Ku) >= EMBEDDING_STAMPS
    assert node_state(Task) >= GROUNDING_STAMPS
    assert node_state(UserEntry) >= GROUNDING_STAMPS
    assert "predicted_duration_minutes" in node_state(Task)
    assert "predicted_duration_minutes" not in node_state(UserEntry)


def test_each_learning_state_group_is_its_class_node_state() -> None:
    assert frozenset(HABIT_LEARNING_PROPERTIES) <= node_state(Habit)
    assert node_state(User) >= TASK_DURATION_LEARNING_PROPERTIES
    assert node_state(User) >= TEACHER_FEEDBACK_PROPERTIES


def test_a_substance_credit_is_a_curriculum_field_and_ku_node_state() -> None:
    substance = SUBSTANCE_COUNTERS | SUBSTANCE_TIMESTAMPS
    assert substance <= _field_names(Curriculum)
    assert substance <= _field_names(PathStep)
    assert substance <= node_state(Ku)
    assert ps_service._VALID_SUBSTANCE_METRICS is SUBSTANCE_COUNTERS
    assert ps_service._VALID_SUBSTANCE_TIMESTAMP_FIELDS is SUBSTANCE_TIMESTAMPS


def test_undeclared_keys_names_a_key_neither_a_field_nor_node_state() -> None:
    stored = {
        "uid": "task_0123456789abcdef",
        "title": "T",
        "grounded_at": "2026-11-23T00:00:00+00:00",
        "predicted_duration_minutes": 30,
        "embedding_text_hash": "h",
        "titel": "typo",
    }

    assert undeclared_keys(stored, Task) == ["titel"]
    assert undeclared_keys({"uid": "task_0123456789abcdef", "title": "T"}, Task) == []


def test_a_model_its_backend_does_not_read_refuses_the_write() -> None:
    curriculum = Curriculum(
        uid="ku.test.another-class",
        title="Not a Ku",
        domain=Domain.TECH,
        sel_category=SELCategory.SELF_AWARENESS,
    )

    with pytest.raises(UnknownFieldError) as refused:
        to_neo4j_node(curriculum, Ku)

    assert refused.value.entity_class == "Ku"
    assert {"learning_level", "quality_score", "times_applied_in_tasks"} <= set(
        refused.value.unknown
    )


def test_a_model_its_backend_reads_is_stored() -> None:
    ku = Ku(uid="ku.test.its-own-class", title="A Ku", domain=Domain.TECH)

    assert to_neo4j_node(ku, Ku)["uid"] == "ku.test.its-own-class"


class RecordingLogger:
    """Captures warnings in place of the module structlog logger."""

    def __init__(self) -> None:
        self.records: list[str] = []

    def warning(self, message: str) -> None:
        self.records.append(message)


def _run(found: UndeclaredStoredKeys, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    recorder = RecordingLogger()
    monkeypatch.setattr(stored_value_check, "logger", recorder)
    check_undeclared_keys(found)
    return recorder.records


def test_the_check_is_silent_on_a_graph_whose_every_key_is_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert _run(UndeclaredStoredKeys(count=0), monkeypatch) == []


def test_a_key_no_read_reads_is_a_warning_naming_it(monkeypatch: pytest.MonkeyPatch) -> None:
    records = _run(
        UndeclaredStoredKeys(count=2, sample=("Task task_x.titel", "Ku ku.a.b.heading")),
        monkeypatch,
    )

    assert len(records) == 1
    assert "stored keys no read reads: 2" in records[0]
    assert "Task task_x.titel, Ku ku.a.b.heading" in records[0]
    assert "./dev stored-value-census" in records[0]
