"""Real-Neo4j round-trip tests for the Gantt aggregation endpoints.

These guard two phantom-method bugs in ``VisualizationAggregationService`` of the
exact class fixed for choices in #198 — a service calling a relationship method
that was never implemented:

* ``get_tasks_gantt_data`` called ``tasks_service.relationships.get_task_prerequisites()``
  (defined nowhere), wrapped in a bare ``except Exception: pass`` — so every Gantt
  dependency arrow was silently dropped.
* ``get_goal_gantt_data`` called ``goals_service.relationships.get_goal_tasks()``
  (only a backend-protocol declaration, no implementation anywhere) with no guard —
  an unhandled ``AttributeError`` → 500 on ``GET /api/visualizations/gantt/goal/{uid}``.

The fixes route through real methods: ``relationships.get_related_uids("prerequisite_tasks", uid)``
(the generic DEPENDS_ON reader) and ``tasks_service.get_tasks_for_goal(uid)`` (the
canonical FULFILLS_GOAL reader returning Task models). A mocked service can't catch
either bug — the only proof is data flowing through real Neo4j, which is what these do.
"""

from datetime import date, timedelta

import pytest

from core.models.goal.goal_request import GoalCreateRequest
from core.models.task.task_request import TaskCreateRequest
from core.services.analytics.visualization_aggregation_service import (
    VisualizationAggregationService,
)
from core.services.visualization_service import VisualizationService


@pytest.mark.asyncio
class TestGanttAggregationRoundTrip:
    """End-to-end (real Neo4j) coverage for the two Gantt aggregation methods."""

    def _vis(self, services):
        """Build the aggregation service from real facades (Gantt uses tasks + goals only)."""
        return VisualizationAggregationService(
            tasks_service=services.tasks,
            habits_service=None,
            goals_service=services.goals,
            visualization_service=VisualizationService(),
        )

    async def _user(self, neo4j_driver, uid: str) -> str:
        async with neo4j_driver.session() as session:
            await session.run(
                "MERGE (u:User {uid: $uid}) ON CREATE SET u.created_at = datetime()",
                uid=uid,
            )
        return uid

    async def test_tasks_gantt_includes_prerequisite_dependencies(
        self, services, neo4j_driver, clean_neo4j
    ):
        """get_tasks_gantt_data surfaces the (Task)-[:DEPENDS_ON]->(prereq) edge as a Gantt dependency."""
        user = await self._user(neo4j_driver, "user_gantt_deps")
        soon = date.today() + timedelta(days=3)

        prereq = (
            await services.tasks.create_task(
                TaskCreateRequest(title="Prerequisite task", due_date=soon), user
            )
        ).value
        dependent = (
            await services.tasks.create_task(
                TaskCreateRequest(title="Dependent task", due_date=soon), user
            )
        ).value

        # A second prerequisite that falls OUTSIDE the [today-7, +60] window — it is
        # not rendered, so it must not appear as a dangling dependency id (Frappe Gantt
        # crashes dereferencing a missing dependency bar).
        far_prereq = (
            await services.tasks.create_task(
                TaskCreateRequest(
                    title="Far prerequisite", due_date=date.today() + timedelta(days=120)
                ),
                user,
            )
        ).value

        # (dependent)-[:DEPENDS_ON]->(prereq): prereq is the prerequisite.
        for blocker in (prereq.uid, far_prereq.uid):
            assert (
                await services.tasks.create_task_dependency(
                    dependent_task_uid=dependent.uid, blocks_task_uid=blocker
                )
            ).is_ok

        result = await self._vis(services).get_tasks_gantt_data(user_uid=user)
        assert result.is_ok, f"get_tasks_gantt_data failed: {result}"

        by_id = {t["id"]: t for t in result.value["tasks"]}
        assert dependent.uid in by_id
        deps = by_id[dependent.uid]["dependencies"]
        # The in-window prerequisite is named; the out-of-window one is dropped.
        assert prereq.uid in deps
        assert far_prereq.uid not in deps
        assert far_prereq.uid not in by_id  # not rendered at all

    async def test_goal_gantt_includes_fulfilling_tasks(self, services, neo4j_driver, clean_neo4j):
        """get_goal_gantt_data returns the goal plus its FULFILLS_GOAL tasks (was a 500)."""
        user = await self._user(neo4j_driver, "user_gantt_goal")
        soon = date.today() + timedelta(days=5)

        goal = (
            await services.goals.create_goal(GoalCreateRequest(title="Ship the feature"), user)
        ).value
        task = (
            await services.tasks.create_task(
                TaskCreateRequest(
                    title="Implement the feature", due_date=soon, fulfills_goal_uid=goal.uid
                ),
                user,
            )
        ).value

        # A DIFFERENT user's task linked to the same goal UID must NOT leak into the
        # response — get_tasks_for_goal is not user-scoped, so the service must filter.
        other = await self._user(neo4j_driver, "user_gantt_intruder")
        foreign = (
            await services.tasks.create_task(
                TaskCreateRequest(title="Foreign task", due_date=soon, fulfills_goal_uid=goal.uid),
                other,
            )
        ).value

        result = await self._vis(services).get_goal_gantt_data(user_uid=user, goal_uid=goal.uid)
        assert result.is_ok, f"get_goal_gantt_data failed: {result}"

        ids = {t["id"] for t in result.value["tasks"]}
        assert goal.uid in ids  # the goal bar itself
        assert task.uid in ids  # its fulfilling task — absent under the old phantom call
        assert foreign.uid not in ids  # cross-user leak guard (Codex P1)
