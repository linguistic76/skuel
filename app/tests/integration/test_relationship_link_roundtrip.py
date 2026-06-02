"""Real-Neo4j guard tests for the UnifiedRelationshipService single-edge path.

`UnifiedRelationshipService.create_relationship` (and the typed `link_to_*` wrappers
that call it, and every facade `link_{domain}_to_{key}` that delegates to those) used
to dispatch to a dynamically-named `link_{domain}_to_{key}` *backend* method. Only two
such methods ever existed (`link_habit_to_knowledge`, `link_habit_to_principle`), so the
call failed at runtime ("Backend method not found") for every other domain — including
reachable routes (`POST /goals/generate-tasks` → `link_task_to_knowledge`). The fix
routes the single method through the proven `backend.create_relationships_batch` path,
keyed off the registry spec.

Mocked unit tests structurally cannot catch this (an `AsyncMock` resolves any attribute),
which is why it survived. These tests create the edge against a real Neo4j and read it
back. Each fails against the pre-fix dynamic-dispatch body and passes against the fix.
"""

from typing import Any

import pytest

from core.models.curriculum import Curriculum
from core.models.enums import Domain, EntityStatus, Priority, RecurrencePattern, SELCategory
from core.models.enums.entity_enums import EntityType
from core.models.enums.habit_enums import HabitCategory
from core.models.habit.habit import Habit
from core.models.relationship_names import RelationshipName
from core.models.relationship_registry import HABITS_CONFIG
from core.models.task.task import Task
from core.services.relationships.unified_relationship_service import UnifiedRelationshipService


@pytest.mark.asyncio
class TestRelationshipLinkRoundTrip:
    """End-to-end (real Neo4j) coverage for the single create_relationship path."""

    async def _make_ku(self, ku_backend, uid: str) -> None:
        ku = Curriculum(
            uid=uid, title=uid, domain=Domain.TECH, sel_category=SELCategory.SELF_AWARENESS
        )
        assert (await ku_backend.create(ku)).is_ok

    async def _make_task(self, services, uid: str) -> None:
        task = Task(
            uid=uid,
            title=uid,
            description="link round-trip fixture",
            user_uid="user_test",
            priority=Priority.MEDIUM,
            status=EntityStatus.DRAFT,
        )
        assert (await services.tasks.backend.create(task)).is_ok

    async def test_link_task_to_knowledge_creates_applies_knowledge_edge(
        self, services, ku_backend, clean_neo4j
    ):
        """The facade method that the /goals/generate-tasks route uses now writes a real edge.

        Pre-fix this dispatched to a non-existent `link_task_to_knowledge` backend method
        and failed at runtime.
        """
        await self._make_task(services, "task:link_ku_src")
        await self._make_ku(ku_backend, "ku:link_target")

        result = await services.tasks.link_task_to_knowledge("task:link_ku_src", "ku:link_target")
        assert result.is_ok, f"link_task_to_knowledge failed: {result}"

        edges = await services.tasks.backend.get_relationships(
            "task:link_ku_src", rel_type=RelationshipName.APPLIES_KNOWLEDGE, direction="outgoing"
        )
        assert edges.is_ok
        assert [r["type"] for r in edges.value] == ["APPLIES_KNOWLEDGE"]
        assert edges.value[0]["target_uid"] == "ku:link_target"

    async def test_create_relationship_single_persists_properties(
        self, services, ku_backend, clean_neo4j
    ):
        """The single create_relationship writes the registry-typed edge and persists properties."""
        await self._make_task(services, "task:link_props_src")
        await self._make_ku(ku_backend, "ku:link_props_target")

        result = await services.tasks.relationships.create_relationship(
            "knowledge",
            "task:link_props_src",
            "ku:link_props_target",
            properties={"confidence": 0.9},
        )
        assert result.is_ok
        assert result.value is True

        meta = await services.tasks.backend.get_relationship_metadata(
            from_uid="task:link_props_src",
            to_uid="ku:link_props_target",
            relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
        )
        assert meta.is_ok
        assert meta.value is not None
        assert meta.value["confidence"] == 0.9

    async def test_habit_knowledge_link_still_reinforces_knowledge(
        self, habits_backend, ku_backend, clean_neo4j
    ):
        """No regression for the two cases that worked pre-fix via hand-written backend methods.

        The deleted `link_habit_to_knowledge` backend method created `REINFORCES_KNOWLEDGE`;
        the registry maps the habit `"knowledge"` key to the same edge type, so routing
        through the batch path is behaviour-preserving.
        """
        habit = Habit(
            uid="habit:link_ku_src",
            user_uid="user_test",
            entity_type=EntityType.HABIT,
            title="Habit",
            description="link round-trip fixture",
            habit_category=HabitCategory.LEARNING,
            status=EntityStatus.ACTIVE,
            recurrence_pattern=RecurrencePattern.DAILY,
        )
        assert (await habits_backend.create(habit)).is_ok
        await self._make_ku(ku_backend, "ku:habit_target")

        habits_relationships: UnifiedRelationshipService[Any, Any, Any] = (
            UnifiedRelationshipService(backend=habits_backend, config=HABITS_CONFIG)
        )
        result = await habits_relationships.create_relationship(
            "knowledge", "habit:link_ku_src", "ku:habit_target"
        )
        assert result.is_ok
        assert result.value is True

        edges = await habits_backend.get_relationships(
            "habit:link_ku_src",
            rel_type=RelationshipName.REINFORCES_KNOWLEDGE,
            direction="outgoing",
        )
        assert edges.is_ok
        assert [r["type"] for r in edges.value] == ["REINFORCES_KNOWLEDGE"]
        assert edges.value[0]["target_uid"] == "ku:habit_target"
