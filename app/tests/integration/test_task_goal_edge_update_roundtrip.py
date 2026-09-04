"""Real-Neo4j round-trip for the FULFILLS_GOAL edge on task UPDATE.

Sibling of the goal-edge chapter in ``test_task_create_edge_roundtrip.py``. The facade's
``update_task`` writes ``fulfills_goal_uid`` as a node property (it is a real column) AND
replaces the ``(Task)-[:FULFILLS_GOAL]->(Goal)`` edge: the old edge is deleted, the new one
is admitted through the same guard the create path uses. ``None`` clears both. A refused
goal clears the property core has just written, so the two halves never disagree.

Driven through ``TasksService`` — the object the UI edit route and the generated CRUD
update route both call — against a live graph, because the unit suite stubs the
relationship service and cannot prove the old edge is actually gone.
"""

import pytest

from core.models.enums import Domain, MeasurementType, Priority
from core.models.goal.goal_request import GoalCreateRequest
from core.models.relationship_names import RelationshipName
from core.models.task.task_request import TaskCreateRequest, TaskUpdateRequest
from core.models.task.task_update_intent import TaskUpdateIntent

USER = "user_test_goal_edge_update"
OTHER = "user_test_goal_edge_update_other"


async def _ensure_user(neo4j_driver, uid: str) -> str:
    async with neo4j_driver.session() as session:
        await session.run(
            "MERGE (u:User {uid: $uid}) ON CREATE SET u.created_at = datetime()", uid=uid
        )
    return uid


async def _goal_edge_targets(neo4j_driver, task_uid: str) -> list[str]:
    async with neo4j_driver.session() as session:
        result = await session.run(
            f"MATCH (t {{uid: $task}})-[:{RelationshipName.FULFILLS_GOAL.value}]->(g) "
            "RETURN collect(g.uid) AS uids",
            task=task_uid,
        )
        row = await result.single()
    return row["uids"]


async def _goal_property(neo4j_driver, task_uid: str):
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (t {uid: $uid}) RETURN t.fulfills_goal_uid AS goal", uid=task_uid
        )
        row = await result.single()
    assert row is not None
    return row["goal"]


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


@pytest.mark.asyncio
class TestGoalEdgeUpdateRoundTrip:
    async def test_replacing_the_goal_moves_the_edge_and_the_property(
        self, services, neo4j_driver, clean_neo4j
    ) -> None:
        await _ensure_user(neo4j_driver, USER)
        first = await _goal(services, USER, "First goal")
        second = await _goal(services, USER, "Second goal")

        task = await services.tasks.create_task(
            TaskCreateRequest(title="Move me", fulfills_goal_uid=first), USER
        )
        assert task.is_ok, f"create_task failed: {task.error}"
        assert await _goal_edge_targets(neo4j_driver, task.value.uid) == [first]

        updated = await services.tasks.update_task(
            task.value.uid, TaskUpdateIntent(fulfills_goal_uid=second)
        )
        assert updated.is_ok, f"update_task failed: {updated.error}"

        assert await _goal_edge_targets(neo4j_driver, task.value.uid) == [second], (
            "the old FULFILLS_GOAL edge survived the update, or the new one was not written"
        )
        assert await _goal_property(neo4j_driver, task.value.uid) == second
        assert updated.value.fulfills_goal_uid == second

    async def test_clearing_the_goal_removes_both_halves(
        self, services, neo4j_driver, clean_neo4j
    ) -> None:
        await _ensure_user(neo4j_driver, USER)
        goal = await _goal(services, USER, "Cleared goal")
        task = await services.tasks.create_task(
            TaskCreateRequest(title="Unlink me", fulfills_goal_uid=goal), USER
        )
        assert task.is_ok

        updated = await services.tasks.update_task(
            task.value.uid, TaskUpdateIntent(fulfills_goal_uid=None)
        )
        assert updated.is_ok, f"update_task failed: {updated.error}"

        assert await _goal_edge_targets(neo4j_driver, task.value.uid) == []
        assert await _goal_property(neo4j_driver, task.value.uid) is None
        assert updated.value.fulfills_goal_uid is None

    async def test_the_request_door_carries_the_field_through_to_intent(
        self, services, neo4j_driver, clean_neo4j
    ) -> None:
        """The edit form and the JSON route arrive as ``TaskUpdateRequest``; its
        ``to_intent()`` must carry the goal so the edge is replaced, not just the column."""
        await _ensure_user(neo4j_driver, USER)
        goal = await _goal(services, USER, "Form goal")
        task = await services.tasks.create_task(TaskCreateRequest(title="Form-linked"), USER)
        assert task.is_ok
        assert await _goal_edge_targets(neo4j_driver, task.value.uid) == []

        intent = TaskUpdateRequest(fulfills_goal_uid=goal).to_intent()
        updated = await services.tasks.update_task(task.value.uid, intent)
        assert updated.is_ok, f"update_task failed: {updated.error}"

        assert await _goal_edge_targets(neo4j_driver, task.value.uid) == [goal]
        assert await _goal_property(neo4j_driver, task.value.uid) == goal

    async def test_another_users_goal_is_refused_and_the_stamp_is_cleared(
        self, services, neo4j_driver, clean_neo4j
    ) -> None:
        """``update_for_user`` verifies the TASK's owner and nothing about the far end.
        The old edge is gone (replace semantics), the new one is refused, and the property
        core just wrote is cleared — the task ends with no goal, matching the graph."""
        await _ensure_user(neo4j_driver, USER)
        await _ensure_user(neo4j_driver, OTHER)
        mine = await _goal(services, USER, "My goal")
        theirs = await _goal(services, OTHER, "Their goal")
        task = await services.tasks.create_task(
            TaskCreateRequest(title="Redirected", fulfills_goal_uid=mine), USER
        )
        assert task.is_ok

        updated = await services.tasks.update_for_user(
            task.value.uid, TaskUpdateIntent(fulfills_goal_uid=theirs), USER
        )
        assert updated.is_ok, "the update itself is legitimate — only the edge is refused"

        assert await _goal_edge_targets(neo4j_driver, task.value.uid) == [], (
            "a cross-user FULFILLS_GOAL edge reached the graph through the update door"
        )
        assert await _goal_property(neo4j_driver, task.value.uid) is None, (
            "the refused goal is still stamped on the node — property and edge disagree"
        )
        assert updated.value.fulfills_goal_uid is None
