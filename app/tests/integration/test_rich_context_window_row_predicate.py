"""The rich context's "touched since window start" selection is real.

``build_rich(window=…)`` admits a closed task or goal only when it was touched
since the period's start; the predicate sits on the ROW (a list comprehension
before the neighbourhood matches), with ``updated_at`` — stored as an ISO
string — coerced for the comparison. An untouched closed task must be absent
from ``entities_rich`` for the period; a touched one present; an open one
present regardless — and a user whose every task is untouched still gets a
context (the null-row guard), not zero rows.

Requires: Docker running with Neo4j testcontainer.
"""

from __future__ import annotations

import pytest

from core.utils.uid_generator import UIDGenerator

pytestmark = pytest.mark.asyncio


async def _seed_task(driver, user_uid: str, *, status: str, updated_at: str) -> str:
    uid = UIDGenerator.generate_random_uid("task")
    await driver.execute_query(
        """
        MATCH (user:User {uid: $user_uid})
        CREATE (t:Entity:Task {uid: $uid, title: $uid, entity_type: 'task',
                               status: $status, user_uid: $user_uid,
                               created_at: '2026-06-01T09:00:00',
                               updated_at: $updated_at})
        CREATE (user)-[:OWNS]->(t)
        """,
        {"uid": uid, "user_uid": user_uid, "status": status, "updated_at": updated_at},
    )
    return uid


async def _seed_goal(driver, user_uid: str, *, status: str, updated_at: str) -> str:
    uid = UIDGenerator.generate_random_uid("goal")
    await driver.execute_query(
        """
        MATCH (user:User {uid: $user_uid})
        CREATE (g:Entity:Goal {uid: $uid, title: $uid, entity_type: 'goal',
                               status: $status, user_uid: $user_uid,
                               progress_percentage: 100.0,
                               created_at: '2026-06-01T09:00:00',
                               updated_at: $updated_at})
        CREATE (user)-[:OWNS]->(g)
        """,
        {"uid": uid, "user_uid": user_uid, "status": status, "updated_at": updated_at},
    )
    return uid


def _rich_uids(context, domain: str) -> set[str]:
    return {row["entity"]["uid"] for row in context.entities_rich.get(domain, [])}


@pytest.mark.integration
class TestWindowRowPredicate:
    async def test_untouched_closed_task_is_absent_and_touched_one_present(
        self, clean_neo4j, services, test_user
    ) -> None:
        driver = services.tasks.core.backend.driver
        untouched = await _seed_task(
            driver, test_user.uid, status="completed", updated_at="2026-07-01T10:00:00"
        )
        touched = await _seed_task(
            driver, test_user.uid, status="completed", updated_at="2026-09-05T10:00:00"
        )
        open_task = await _seed_task(
            driver, test_user.uid, status="active", updated_at="2026-07-01T10:00:00"
        )

        result = await services.users.context_builder.build_rich(test_user.uid, window="2026-09")

        assert result.is_ok, f"rich context failed: {result.error}"
        uids = _rich_uids(result.value, "tasks")
        assert touched in uids, "a task completed inside the period must reach the mapper"
        assert open_task in uids, "an open task is always in play"
        assert untouched not in uids, (
            "a task closed and untouched before the period reached entities_rich — "
            "the touched predicate is not gating the row"
        )

    async def test_a_user_with_only_untouched_tasks_still_gets_a_context(
        self, clean_neo4j, services, test_user
    ) -> None:
        driver = services.tasks.core.backend.driver
        await _seed_task(
            driver, test_user.uid, status="completed", updated_at="2026-07-01T10:00:00"
        )

        result = await services.users.context_builder.build_rich(test_user.uid, window="2026-09")

        assert result.is_ok, f"rich context failed: {result.error}"
        assert _rich_uids(result.value, "tasks") == set()

    async def test_untouched_completed_goal_is_absent_and_touched_one_present(
        self, clean_neo4j, services, test_user
    ) -> None:
        driver = services.goals.core.backend.driver
        untouched = await _seed_goal(
            driver, test_user.uid, status="completed", updated_at="2026-07-01T10:00:00"
        )
        touched = await _seed_goal(
            driver, test_user.uid, status="completed", updated_at="2026-09-05T10:00:00"
        )

        result = await services.users.context_builder.build_rich(test_user.uid, window="2026-09")

        assert result.is_ok, f"rich context failed: {result.error}"
        uids = _rich_uids(result.value, "goals")
        assert touched in uids
        assert untouched not in uids
