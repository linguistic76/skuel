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

import itertools

import pytest

from adapters.infrastructure.event_bus import InMemoryEventBus
from core.events import TaskUpdated
from core.models.enums import EntityStatus, Priority
from core.models.relationship_names import RelationshipName
from core.models.task.task import Task
from tests.helpers.seed_uids import seed_user_uid


@pytest.mark.asyncio
class TestTaskDependencyEdgeRoundTrip:
    """End-to-end (real Neo4j) coverage for the DEPENDS_ON dependency edge."""

    async def _create_task(self, services, uid: str, title: str) -> None:
        """Persist a task node through the real backend."""
        task = Task(
            uid=uid,
            title=title,
            description=f"{title} (dependency round-trip fixture)",
            user_uid=seed_user_uid("test"),
            priority=Priority.MEDIUM,
            status=EntityStatus.DRAFT,
        )
        assert (await services.tasks.backend.create(task)).is_ok

    async def test_create_task_dependency_persists_depends_on_edge(self, services, clean_neo4j):
        """create_task_dependency writes a real ``(dependent)-[:DEPENDS_ON]->(blocks)`` edge."""
        await self._create_task(services, "task.dep-dependent", "Dependent Task")
        await self._create_task(services, "task.dep-blocks", "Blocking Task")

        # ACT: the facade method that previously called the broken dynamic path.
        result = await services.tasks.create_task_dependency(
            dependent_task_uid="task.dep-dependent",
            blocks_task_uid="task.dep-blocks",
            is_hard_dependency=True,
            dependency_type="blocks",
        )
        assert result.is_ok, f"create_task_dependency failed: {result}"
        assert result.value is True

        # ASSERT: read the edge back from real Neo4j.
        edges = await services.tasks.backend.get_relationships(
            "task.dep-dependent",
            rel_type=RelationshipName.DEPENDS_ON,
            direction="outgoing",
        )
        assert edges.is_ok
        assert [r["type"] for r in edges.value] == ["DEPENDS_ON"]
        assert edges.value[0]["target_uid"] == "task.dep-blocks"

    async def test_create_task_dependency_edge_is_directional(self, services, clean_neo4j):
        """The edge is created from dependent → blocks, not the reverse."""
        await self._create_task(services, "task.dir-dependent", "Dependent Task")
        await self._create_task(services, "task.dir-blocks", "Blocking Task")

        assert (
            await services.tasks.create_task_dependency(
                dependent_task_uid="task.dir-dependent",
                blocks_task_uid="task.dir-blocks",
            )
        ).is_ok

        # The blocking task has NO outgoing DEPENDS_ON edge.
        reverse = await services.tasks.backend.get_relationships(
            "task.dir-blocks",
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

        await self._create_task(services, "task.evt-dependent", "Dependent Task")
        await self._create_task(services, "task.evt-blocks", "Blocking Task")

        assert (
            await services.tasks.create_task_dependency(
                dependent_task_uid="task.evt-dependent",
                blocks_task_uid="task.evt-blocks",
            )
        ).is_ok

        updates = [e for e in bus.get_event_history() if isinstance(e, TaskUpdated)]
        assert len(updates) == 1  # both tasks owned by user_test → deduped to one owner
        assert updates[0].task_uid == "task.evt-dependent"
        assert updates[0].user_uid == seed_user_uid("test")
        assert "dependencies" in updates[0].updated_fields

    async def test_delete_task_dependency_removes_edge(self, services, clean_neo4j):
        """delete_task_dependency removes the ``(dependent)-[:DEPENDS_ON]->(blocks)`` edge."""
        await self._create_task(services, "task.del-dependent", "Dependent Task")
        await self._create_task(services, "task.del-blocks", "Blocking Task")

        assert (
            await services.tasks.create_task_dependency(
                dependent_task_uid="task.del-dependent",
                blocks_task_uid="task.del-blocks",
            )
        ).is_ok

        removed = await services.tasks.delete_task_dependency(
            dependent_task_uid="task.del-dependent",
            blocks_task_uid="task.del-blocks",
        )
        assert removed.is_ok, f"delete_task_dependency failed: {removed}"

        edges = await services.tasks.backend.get_relationships(
            "task.del-dependent",
            rel_type=RelationshipName.DEPENDS_ON,
            direction="outgoing",
        )
        assert edges.is_ok
        assert edges.value == []

    async def test_get_task_dependency_neighbors_both_directions(self, services, clean_neo4j):
        """Direct neighbours resolve to depends_on (outgoing) and required_by (incoming)."""
        await self._create_task(services, "task.nb-dependent", "Dependent Task")
        await self._create_task(services, "task.nb-blocks", "Blocking Task")
        assert (
            await services.tasks.create_task_dependency(
                dependent_task_uid="task.nb-dependent",
                blocks_task_uid="task.nb-blocks",
            )
        ).is_ok

        # From the dependent's side: it depends on the blocker, nothing requires it.
        dependent_view = await services.tasks.get_task_dependency_neighbors(
            "task.nb-dependent", seed_user_uid("test")
        )
        assert dependent_view.is_ok, dependent_view
        assert [n["uid"] for n in dependent_view.value["depends_on"]] == ["task.nb-blocks"]
        assert dependent_view.value["required_by"] == []

        # From the blocker's side: nothing it depends on, the dependent requires it.
        blocks_view = await services.tasks.get_task_dependency_neighbors(
            "task.nb-blocks", seed_user_uid("test")
        )
        assert blocks_view.is_ok, blocks_view
        assert blocks_view.value["depends_on"] == []
        assert [n["uid"] for n in blocks_view.value["required_by"]] == ["task.nb-dependent"]
        assert blocks_view.value["required_by"][0]["title"] == "Dependent Task"

    async def test_dependency_neighbors_omits_foreign_owned(self, services, clean_neo4j):
        """A DEPENDS_ON edge to another user's task is omitted, not disclosed."""
        await self._create_task(services, "task.own-dependent", "My Task")
        foreign = Task(
            uid="task.foreign-blocks",
            title="Someone Else's Secret Task",
            description="foreign-owned",
            user_uid=seed_user_uid("other"),
            priority=Priority.MEDIUM,
            status=EntityStatus.DRAFT,
        )
        assert (await services.tasks.backend.create(foreign)).is_ok
        # A cross-owner edge can exist from ingestion / a non-UI caller.
        assert (
            await services.tasks.create_task_dependency(
                dependent_task_uid="task.own-dependent",
                blocks_task_uid="task.foreign-blocks",
            )
        ).is_ok

        view = await services.tasks.get_task_dependency_neighbors(
            "task.own-dependent", seed_user_uid("test")
        )
        assert view.is_ok
        # The foreign-owned neighbour is filtered out — no title/status disclosure.
        assert view.value["depends_on"] == []

    async def test_would_create_dependency_cycle(self, services, clean_neo4j):
        """The cycle guard flags self-links and back-edges, and clears independent pairs."""
        await self._create_task(services, "task.cyc-a", "Task A")
        await self._create_task(services, "task.cyc-b", "Task B")
        await self._create_task(services, "task.cyc-c", "Task C")

        # A depends on B.
        assert (
            await services.tasks.create_task_dependency(
                dependent_task_uid="task.cyc-a", blocks_task_uid="task.cyc-b"
            )
        ).is_ok

        # Adding B → A would close the loop (A already reaches B).
        back_edge = await services.tasks.would_create_dependency_cycle("task.cyc-b", "task.cyc-a")
        assert back_edge.is_ok and back_edge.value is True

        # A self-link is always a cycle.
        self_link = await services.tasks.would_create_dependency_cycle("task.cyc-a", "task.cyc-a")
        assert self_link.is_ok and self_link.value is True

        # An unrelated pair is fine.
        independent = await services.tasks.would_create_dependency_cycle("task.cyc-a", "task.cyc-c")
        assert independent.is_ok and independent.value is False

    async def test_cycle_guard_catches_chains_deeper_than_ten(self, services, clean_neo4j):
        """The cycle guard is unbounded — it catches a loop that closes beyond 10 hops.

        A depth-capped reachability check (get_transitive_dependencies clamps at 10)
        would miss the back-edge on a 12-long chain and silently admit a cycle. Build
        t0 → t1 → … → t12 and confirm adding t12 → t0 is flagged.
        """
        chain = [f"task.deep-{i}" for i in range(13)]
        for i, uid in enumerate(chain):
            await self._create_task(services, uid, f"Deep Task {i}")
        # t0 depends on t1 depends on … depends on t12 (12 edges).
        for dependent, blocks in itertools.pairwise(chain):
            assert (
                await services.tasks.create_task_dependency(
                    dependent_task_uid=dependent, blocks_task_uid=blocks
                )
            ).is_ok

        # Adding t12 → t0 closes a 13-node loop (path t0→…→t12 is 12 hops, > the cap of 10).
        deep_cycle = await services.tasks.would_create_dependency_cycle(chain[-1], chain[0])
        assert deep_cycle.is_ok and deep_cycle.value is True
