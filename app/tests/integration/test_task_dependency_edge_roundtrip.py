"""Real-Neo4j round-trip test for ``TasksService.create_task_dependency``.

This guards a class of bug that a mocked unit test structurally cannot catch:
``create_task_dependency`` previously delegated to
``UnifiedRelationshipService.create_relationship("prerequisite_tasks", ...)``,
which builds a dynamic backend method name ``link_task_to_prerequisite_tasks``
and ``getattr``s it off the backend. No such method exists on task backends, so
the call failed at runtime — but an ``AsyncMock`` backend happily returns success
for *any* attribute access, hiding the missing-method failure entirely.

The fix routes the edge through ``backend.create_relationships_batch`` (the same
proven path create/update use) with an explicit ``RelationshipName.DEPENDS_ON``
value. The only way to prove that round-trips is to create the edge against a
real Neo4j and read it back — exactly what this test does. Against the broken
code it fails (no edge is created); against the fix it passes.
"""

import pytest

from adapters.infrastructure.event_bus import InMemoryEventBus
from core.events import TaskUpdated
from core.models.enums import EntityStatus, Priority
from core.models.relationship_names import RelationshipName
from core.models.task.task import Task


@pytest.mark.asyncio
class TestTaskDependencyEdgeRoundTrip:
    """End-to-end (real Neo4j) coverage for the DEPENDS_ON dependency edge."""

    async def _create_task(self, services, uid: str, title: str) -> None:
        """Persist a task node through the real backend."""
        task = Task(
            uid=uid,
            title=title,
            description=f"{title} (dependency round-trip fixture)",
            user_uid="user_test",
            priority=Priority.MEDIUM,
            status=EntityStatus.DRAFT,
        )
        assert (await services.tasks.backend.create(task)).is_ok

    async def test_create_task_dependency_persists_depends_on_edge(self, services, clean_neo4j):
        """create_task_dependency writes a real ``(dependent)-[:DEPENDS_ON]->(blocks)`` edge."""
        await self._create_task(services, "task:dep_dependent", "Dependent Task")
        await self._create_task(services, "task:dep_blocks", "Blocking Task")

        # ACT: the facade method that previously called the broken dynamic path.
        result = await services.tasks.create_task_dependency(
            dependent_task_uid="task:dep_dependent",
            blocks_task_uid="task:dep_blocks",
            is_hard_dependency=True,
            dependency_type="blocks",
        )
        assert result.is_ok, f"create_task_dependency failed: {result}"
        assert result.value is True

        # ASSERT: read the edge back from real Neo4j.
        edges = await services.tasks.backend.get_relationships(
            "task:dep_dependent",
            rel_type=RelationshipName.DEPENDS_ON,
            direction="outgoing",
        )
        assert edges.is_ok
        assert [r["type"] for r in edges.value] == ["DEPENDS_ON"]
        assert edges.value[0]["target_uid"] == "task:dep_blocks"

    async def test_create_task_dependency_edge_is_directional(self, services, clean_neo4j):
        """The edge is created from dependent → blocks, not the reverse."""
        await self._create_task(services, "task:dir_dependent", "Dependent Task")
        await self._create_task(services, "task:dir_blocks", "Blocking Task")

        assert (
            await services.tasks.create_task_dependency(
                dependent_task_uid="task:dir_dependent",
                blocks_task_uid="task:dir_blocks",
            )
        ).is_ok

        # The blocking task has NO outgoing DEPENDS_ON edge.
        reverse = await services.tasks.backend.get_relationships(
            "task:dir_blocks",
            rel_type=RelationshipName.DEPENDS_ON,
            direction="outgoing",
        )
        assert reverse.is_ok
        assert reverse.value == []

    async def test_create_task_dependency_publishes_invalidation_event(self, services, clean_neo4j):
        """A successful edge-only mutation publishes TaskUpdated so context caches invalidate.

        DEPENDS_ON data feeds UnifiedUserContext.task_dependencies; without this event,
        the owner's cached rich context keeps stale dependency data until the TTL expires.
        Both endpoints share an owner here, so the per-owner dedup yields exactly one event.
        """
        bus = InMemoryEventBus(capture_history=True)
        services.tasks.event_bus = bus

        await self._create_task(services, "task:evt_dependent", "Dependent Task")
        await self._create_task(services, "task:evt_blocks", "Blocking Task")

        assert (
            await services.tasks.create_task_dependency(
                dependent_task_uid="task:evt_dependent",
                blocks_task_uid="task:evt_blocks",
            )
        ).is_ok

        updates = [e for e in bus.get_event_history() if isinstance(e, TaskUpdated)]
        assert len(updates) == 1  # both tasks owned by user_test → deduped to one owner
        assert updates[0].task_uid == "task:evt_dependent"
        assert updates[0].user_uid == "user_test"
        assert "dependencies" in updates[0].updated_fields
