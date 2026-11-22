"""A write never stores a key that names no field of the class its node is read as.

``to_neo4j_patch`` refuses such a patch (``UnknownFieldError``) before any statement
runs, naming the class, every such key and the field each most likely meant: stored,
the key would be a property no read reads. An app door's write answers SYSTEM; the
vault door (``prepare_batch_items``) refuses the one file, its relationship keys
exempt (they are edge sources) and the embedding writer's properties dropped first.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from adapters.persistence.neo4j.batch_preparer import prepare_batch_items
from adapters.persistence.neo4j.neo4j_mapper import (
    UnknownFieldError,
    UnstorableValueError,
    nearest_field_names,
    to_neo4j_patch,
)
from core.ingestion.ingestion_types import UnstorableValue
from core.models.enums.entity_enums import EntityStatus, EntityType, NonKuDomain
from core.models.event.event import Event
from core.models.habit.habit import Habit
from core.models.pathways.learning_path import LearningPath
from core.models.pathways.path_step import PathStep
from core.models.principle.principle import Principle
from core.models.task.task import Task
from core.models.task.task_request import TaskUpdateRequest
from core.models.update_contracts import StatusWriteGuard
from core.services.ingestion.config import ENTITY_CONFIGS
from core.services.ingestion.preparer import prepare_entity_data
from core.services.ingestion.vault_policy import unstorable_value_reason
from core.services.tasks_service import TasksService
from core.utils.result_simplified import ErrorCategory
from tests.helpers.ingestion_owner import INGESTION_TEST_OWNER
from tests.helpers.production_backends import build_production_backends

_UID = "task_0123456789abcdef"
_OWNER = "user_0123456789abcdef"


def _unknown(changes: dict[str, Any], entity_class: type) -> UnknownFieldError:  # boundary: a patch
    with pytest.raises(UnknownFieldError) as refused:
        to_neo4j_patch(changes, entity_class, uid=_UID)
    return refused.value


class TestThePatchRefusesAKeyNamingNoField:
    def test_a_misspelled_key_is_refused_naming_the_field_it_meant(self) -> None:
        refusal = _unknown({"title": "T", "titel": "T"}, Task)

        assert (refusal.entity_class, refusal.uid, refusal.field) == ("Task", _UID, "titel")
        assert refusal.suggestions == {"titel": ("title",)}
        assert "Task has no field 'titel' (did you mean 'title'?)" in str(refusal)

    def test_every_such_key_is_named_in_one_refusal(self) -> None:
        refusal = _unknown({"category": "x", "difficulty": "easy", "total_attempts": 0}, Habit)

        assert list(refusal.unknown) == ["category", "difficulty", "total_attempts"]
        assert refusal.reason == (
            "Habit has no field 'category' (did you mean 'habit_category'?), "
            "'difficulty' (did you mean 'habit_difficulty'?), 'total_attempts'"
        )

    def test_a_key_the_mapper_would_drop_as_a_relationship_is_refused_too(self) -> None:
        # ``prerequisites`` is on the mapper's relationship skip list; the gate reads the
        # patch's own keys before that list is applied, so the key is refused, not dropped.
        assert _unknown({"prerequisites": ["lp.a"]}, LearningPath).field == "prerequisites"

    def test_the_refusal_is_a_write_refusal(self) -> None:
        assert issubclass(UnknownFieldError, UnstorableValueError)

    @pytest.mark.parametrize(
        ("entity_class", "key", "nearest"),
        [
            pytest.param(Habit, "category", ("habit_category",), id="the-classes-own-prefix"),
            pytest.param(
                Principle,
                "source",
                ("principle_source", "original_source"),
                id="the-classes-own-word-first",
            ),
            pytest.param(PathStep, "difficulty", ("step_difficulty",), id="another-prefix"),
            pytest.param(Task, "titel", ("title",), id="a-misspelling"),
            pytest.param(LearningPath, "goal", (), id="nothing-near"),
        ],
    )
    def test_the_nearest_field(
        self, entity_class: type, key: str, nearest: tuple[str, ...]
    ) -> None:
        assert nearest_field_names(key, entity_class) == nearest

    def test_the_two_event_fields_the_app_writes_are_declared(self) -> None:
        moved = datetime(2026, 11, 22, 9, 30, tzinfo=UTC)

        stored = to_neo4j_patch(
            {"status": EntityStatus.CANCELLED.value, "notes": "Missed", "rescheduled_at": moved},
            Event,
        )

        assert stored == {
            "status": "cancelled",
            "notes": "Missed",
            "rescheduled_at": moved.isoformat(),
        }


def _mock_driver() -> tuple[Mock, AsyncMock]:
    driver = Mock()
    driver._closed = False
    session = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__.return_value = session
    ctx.__aexit__.return_value = None
    driver.session.return_value = ctx
    return driver, session


class TestAnAppDoorAnswersSystemAndWritesNothing:
    @pytest.mark.asyncio
    async def test_update(self) -> None:
        driver, session = _mock_driver()
        backend = build_production_backends(driver)["tasks_backend"]

        result = await backend.update(_UID, {"title": "T", "titel": "T"})

        assert result.is_error
        error = result.expect_error()
        assert error.category is ErrorCategory.SYSTEM
        assert "Task" in error.message and "'titel'" in error.message
        session.run.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_with_status_guard(self) -> None:
        driver, session = _mock_driver()
        backend = build_production_backends(driver)["tasks_backend"]

        result = await backend.update_with_status_guard(
            _UID, {"predicted_duration_minutes": 30}, StatusWriteGuard()
        )

        assert result.is_error
        assert result.expect_error().category is ErrorCategory.SYSTEM
        assert "'predicted_duration_minutes'" in result.expect_error().message
        session.run.assert_not_called()


class TestTheVaultDoorRefusesTheFile:
    def test_a_file_authoring_a_key_naming_no_field_is_left_out(self) -> None:
        good = {"uid": "habit.good", "title": "Good", "user_uid": _OWNER}
        bad = {"uid": "habit.bad", "title": "Bad", "user_uid": _OWNER, "category": "x"}

        items, refused = prepare_batch_items([good, bad], Habit)

        assert [item["uid"] for item in items] == ["habit.good"]
        assert [(type(r), r.uid, r.field) for r in refused] == [
            (UnknownFieldError, "habit.bad", "category")
        ]

    def test_its_report_names_the_field_it_meant(self) -> None:
        _, refused = prepare_batch_items(
            [{"uid": "habit.bad", "title": "Bad", "user_uid": _OWNER, "category": "x"}], Habit
        )
        refusal = refused[0]
        assert isinstance(refusal, UnknownFieldError)

        reason = unstorable_value_reason(
            UnstorableValue(refusal.field, refusal.value, refusal.reason, names_no_field=True)
        )

        assert reason == (
            "Habit has no field 'category' (did you mean 'habit_category'?) "
            "— rename or remove each such line"
        )

    def test_relationship_keys_are_edge_sources_not_unknown_keys(self) -> None:
        rel_config = ENTITY_CONFIGS[EntityType.PATH_STEP].relationship_config
        assert rel_config is not None
        step = {
            "uid": "ps.x.y",
            "title": "S",
            "uses_kus": ["ku.x.a"],
            "prerequisite_step_uids": ["ps.x.z"],
            "connections.enables": ["ps.x.w"],
        }

        items, refused = prepare_batch_items([step], PathStep, rel_config=rel_config)

        assert refused == []
        (item,) = items
        assert (item["uses_kus"], item["prerequisite_step_uids"], item["connections.enables"]) == (
            ["ku.x.a"],
            ["ps.x.z"],
            ["ps.x.w"],
        )
        assert not {"uses_kus", "prerequisite_step_uids", "connections.enables"} & set(
            item["_node_props"]
        )

    def test_a_key_outside_the_relationship_config_is_refused_even_when_dotted(self) -> None:
        rel_config = ENTITY_CONFIGS[EntityType.PATH_STEP].relationship_config
        step = {"uid": "ps.x.y", "title": "S", "connections.requires": ["ps.x.z"]}

        items, refused = prepare_batch_items([step], PathStep, rel_config=rel_config)

        assert items == []
        assert [r.field for r in refused] == ["connections.requires"]

    def test_the_embedding_writers_keys_are_dropped_before_the_check(self) -> None:
        ku_like = {
            "uid": "habit.x",
            "title": "H",
            "user_uid": _OWNER,
            "embedding_text_hash": "abc",
            "embedding_version": 3,
        }

        items, refused = prepare_batch_items([ku_like], Habit)

        assert refused == []
        assert "embedding_text_hash" not in items[0]


class TestThePreparerHandsTheGateOnlyFields:
    def test_the_moc_switch_is_read_and_goes_no_further(self) -> None:
        prepared = prepare_entity_data(
            EntityType.KU,
            {"type": "ku", "title": "M", "uid": "ku.x.map", "moc": True},
            "[[ku.x.a]]",
            Path("map.md"),
            INGESTION_TEST_OWNER,
        )

        assert "moc" not in prepared
        assert prepared["_moc_links"] == ["/ku.x.a.md"]

    def test_an_ungoverned_group_naming_its_owner_stores_no_user_uid(self) -> None:
        prepared = prepare_entity_data(
            NonKuDomain.GROUP,
            {"type": "group", "name": "G", "uid": "group.g", "owner_uid": _OWNER},
            None,
            Path("g.md"),
            INGESTION_TEST_OWNER,
        )

        assert prepared["owner_uid"] == _OWNER
        assert "user_uid" not in prepared


class TestATaskUpdatesPrerequisitesAsEdges:
    def test_the_facade_splits_them_off_the_property_patch(self) -> None:
        intent = TaskUpdateRequest(
            title="T",
            prerequisite_task_uids=["task_aaaaaaaaaaaaaaaa"],
            prerequisite_knowledge_uids=["ku.x.a"],
        ).to_intent()

        edges, properties = TasksService._split_relationship_intent(intent)

        assert properties.to_changes() == {"title": "T"}
        assert edges.prerequisite_task_uids == ["task_aaaaaaaaaaaaaaaa"]
        assert edges.prerequisite_knowledge_uids == ["ku.x.a"]
        assert edges.any_set()
