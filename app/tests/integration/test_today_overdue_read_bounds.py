"""The day view's overdue read is unbounded below.

``TodayOrchestrator._overdue_candidates`` asks the Tasks range read for every
task due before today from ``date.min`` on — a historical vault task dated in
any past year is overdue too, and the query must accept the calendar's first
day as a bound rather than a year SKUEL happens to have started in.

Requires: Docker running with Neo4j testcontainer.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from core.utils.uid_generator import UIDGenerator

pytestmark = pytest.mark.asyncio


async def _seed_task(driver, user_uid: str, *, due: str, status: str = "active") -> str:
    uid = UIDGenerator.generate_random_uid("task")
    await driver.execute_query(
        """
        MATCH (user:User {uid: $user_uid})
        CREATE (t:Entity:Task {uid: $uid, title: $uid, entity_type: 'task',
                               status: $status, user_uid: $user_uid, due_date: $due,
                               created_at: '2026-06-01T09:00:00',
                               updated_at: '2026-06-01T09:00:00'})
        CREATE (user)-[:OWNS]->(t)
        """,
        {"uid": uid, "user_uid": user_uid, "due": due, "status": status},
    )
    return uid


@pytest.mark.integration
class TestOverdueReadBounds:
    async def test_a_historical_task_is_read_from_the_calendars_first_day(
        self, clean_neo4j, services, test_user
    ) -> None:
        driver = services.tasks.core.backend.driver
        historical = await _seed_task(driver, test_user.uid, due="1999-05-05")
        recent = await _seed_task(
            driver, test_user.uid, due=(date.today() - timedelta(days=3)).isoformat()
        )
        done = await _seed_task(driver, test_user.uid, due="2001-01-01", status="completed")

        result = await services.tasks.get_user_items_in_range(
            test_user.uid,
            date.min,
            date.today() - timedelta(days=1),
            include_completed=False,
            date_field="due_date",
        )

        assert result.is_ok, f"range read failed: {result.error}"
        uids = {t.uid for t in result.value}
        assert historical in uids, "a task due in 1999 must be readable from date.min"
        assert recent in uids
        assert done not in uids, "completed rows are excluded in the query"
