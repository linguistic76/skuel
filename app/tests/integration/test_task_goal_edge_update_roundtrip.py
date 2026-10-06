"""Real-Neo4j round-trip for the CONTRIBUTES_TO_GOAL edges on task UPDATE.

Sibling of the goal-edge chapter in ``test_task_create_edge_roundtrip.py``. The facade's
``update_task`` takes ``contributes_to_goal_uids`` as a FULL REPLACE of the task's
``(Task)-[:CONTRIBUTES_TO_GOAL]->(Goal)`` edges: every old edge is deleted, each new one
is admitted through the same guard the create path uses, ``[]`` clears them and an
absent field leaves them alone. No node property names a goal. A changed goal set
announces the goals the task left, and the task itself, so every affected tally is
recounted.

Driven through ``TasksService`` — the object the generated CRUD update route calls —
against a live graph, because the unit suite stubs the relationship service and cannot
prove the old edge is actually gone.
"""

import pytest

from adapters.infrastructure.event_bus import InMemoryEventBus
from core.events.goal_events import GoalContributionsChanged
from core.models.enums import Domain, MeasurementType, Priority
from core.models.goal.goal_request import GoalCreateRequest
from core.models.relationship_names import RelationshipName
from core.models.task.task_request import TaskCreateRequest, TaskUpdateRequest
from core.models.task.task_update_intent import TaskUpdateIntent

USER = "user_test_goal_edge_update"
OTHER = "user_test_goal_edge_update_other"

#: The node properties that would name a task's goal link — none may be written.
_GOAL_LINK_PROPERTIES = frozenset(
    {"fulfills_goal_uid", "contributes_to_goal_uid", "contributes_to_goal_uids"}
)


async def _ensure_user(neo4j_driver, uid: str) -> str:
    async with neo4j_driver.session() as session:
        await session.run(
            "MERGE (u:User {uid: $uid}) ON CREATE SET u.created_at = datetime()", uid=uid
        )
    return uid


async def _goal_edge_targets(neo4j_driver, task_uid: str) -> list[str]:
    async with neo4j_driver.session() as session:
        result = await session.run(
            f"MATCH (t {{uid: $task}})-[:{RelationshipName.CONTRIBUTES_TO_GOAL.value}]->(g) "
            "RETURN g.uid AS uid ORDER BY uid",
            task=task_uid,
        )
        return [record["uid"] async for record in result]


async def _goal_named_properties(neo4j_driver, task_uid: str) -> list[str]:
    async with neo4j_driver.session() as session:
        result = await session.run("MATCH (t {uid: $uid}) RETURN keys(t) AS keys", uid=task_uid)
        row = await result.single()
    assert row is not None
    return sorted(set(row["keys"]) & _GOAL_LINK_PROPERTIES)


async def _goal(services, user: str, title: str) -> str:
    created = await services.goals.create_goal(
        GoalCreateRequest(
            title=title,
            description=f"{title} — goal for the update round-trip",
            domain=Domain.TECH,
            priority=Priority.HIGH,
            measurement_type=MeasurementType.NUMERIC,
            target_value=10.0,
        ),
        user,
    )
    assert created.is_ok, f"goal create failed: {created.error}"
    return created.value.uid


async def _task(services, title: str, *goal_uids: str) -> str:
    task = await services.tasks.create_task(
        TaskCreateRequest(title=title, contributes_to_goal_uids=list(goal_uids)), USER
    )
    assert task.is_ok, f"create_task failed: {task.error}"
    return task.value.uid


@pytest.mark.asyncio
class TestGoalEdgeUpdateRoundTrip:
    async def test_a_new_goal_set_replaces_every_old_edge(
        self, services, neo4j_driver, clean_neo4j
    ) -> None:
        await _ensure_user(neo4j_driver, USER)
        first = await _goal(services, USER, "First goal")
        second = await _goal(services, USER, "Second goal")
        third = await _goal(services, USER, "Third goal")
        task_uid = await _task(services, "Move me", first, second)
        assert await _goal_edge_targets(neo4j_driver, task_uid) == sorted([first, second])

        updated = await services.tasks.update_task(
            task_uid, TaskUpdateIntent(contributes_to_goal_uids=[second, third])
        )
        assert updated.is_ok, f"update_task failed: {updated.error}"

        assert await _goal_edge_targets(neo4j_driver, task_uid) == sorted([second, third]), (
            "an old CONTRIBUTES_TO_GOAL edge survived the update, or a new one was not written"
        )
        assert await _goal_named_properties(neo4j_driver, task_uid) == []

    async def test_an_empty_list_clears_every_goal(
        self, services, neo4j_driver, clean_neo4j
    ) -> None:
        await _ensure_user(neo4j_driver, USER)
        first = await _goal(services, USER, "Cleared goal")
        second = await _goal(services, USER, "Also cleared")
        task_uid = await _task(services, "Unlink me", first, second)

        updated = await services.tasks.update_task(
            task_uid, TaskUpdateIntent(contributes_to_goal_uids=[])
        )
        assert updated.is_ok, f"update_task failed: {updated.error}"

        assert await _goal_edge_targets(neo4j_driver, task_uid) == []

    async def test_an_update_without_the_field_leaves_the_goals(
        self, services, neo4j_driver, clean_neo4j
    ) -> None:
        await _ensure_user(neo4j_driver, USER)
        goal = await _goal(services, USER, "Kept goal")
        task_uid = await _task(services, "Rename me", goal)

        updated = await services.tasks.update_task(task_uid, TaskUpdateIntent(title="Renamed"))
        assert updated.is_ok, f"update_task failed: {updated.error}"

        assert await _goal_edge_targets(neo4j_driver, task_uid) == [goal]

    async def test_the_request_door_carries_the_field_through_to_intent(
        self, services, neo4j_driver, clean_neo4j
    ) -> None:
        """The JSON route arrives as ``TaskUpdateRequest``; its ``to_intent()`` must carry
        the goal set so the edges are replaced — and ``None`` (absent) must not clear them."""
        await _ensure_user(neo4j_driver, USER)
        goal = await _goal(services, USER, "Request goal")
        task_uid = await _task(services, "Request-linked")
        assert await _goal_edge_targets(neo4j_driver, task_uid) == []

        intent = TaskUpdateRequest(contributes_to_goal_uids=[goal]).to_intent()
        updated = await services.tasks.update_task(task_uid, intent)
        assert updated.is_ok, f"update_task failed: {updated.error}"
        assert await _goal_edge_targets(neo4j_driver, task_uid) == [goal]

        untouched = TaskUpdateRequest(title="Renamed").to_intent()
        assert (await services.tasks.update_task(task_uid, untouched)).is_ok
        assert await _goal_edge_targets(neo4j_driver, task_uid) == [goal]

    async def test_the_change_announces_the_goals_left_and_the_task(
        self, services, neo4j_driver, clean_neo4j
    ) -> None:
        """The goals the task left are named (their edges are gone, so nothing could find
        them afterwards); the task is named for the goals it contributes to now."""
        await _ensure_user(neo4j_driver, USER)
        left = await _goal(services, USER, "Left goal")
        joined = await _goal(services, USER, "Joined goal")
        task_uid = await _task(services, "Announce me", left)
        bus = InMemoryEventBus(capture_history=True)
        services.tasks.event_bus = bus

        updated = await services.tasks.update_task(
            task_uid, TaskUpdateIntent(contributes_to_goal_uids=[joined])
        )
        assert updated.is_ok, f"update_task failed: {updated.error}"

        [changed] = [e for e in bus.get_event_history() if isinstance(e, GoalContributionsChanged)]
        assert changed.goal_uids == (left,)
        assert changed.contributor_uids == (task_uid,)

    async def test_another_users_goal_is_refused(self, services, neo4j_driver, clean_neo4j) -> None:
        """``update_for_user`` verifies the TASK's owner and nothing about the far end. The
        old edge is gone (replace semantics) and the foreign one is never written."""
        await _ensure_user(neo4j_driver, USER)
        await _ensure_user(neo4j_driver, OTHER)
        mine = await _goal(services, USER, "My goal")
        theirs = await _goal(services, OTHER, "Their goal")
        task_uid = await _task(services, "Redirected", mine)

        updated = await services.tasks.update_for_user(
            task_uid, TaskUpdateIntent(contributes_to_goal_uids=[theirs]), USER
        )
        assert updated.is_ok, "the update itself is legitimate — only the edge is refused"

        assert await _goal_edge_targets(neo4j_driver, task_uid) == [], (
            "a cross-user CONTRIBUTES_TO_GOAL edge reached the graph through the update door"
        )
        assert await _goal_named_properties(neo4j_driver, task_uid) == []
