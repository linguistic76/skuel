"""The report's period counters are fed by the domain writers, not by seeded rows.

Each test drives a production writer — the goal progress door, the principle
reflection door, a choice decided in the period — then builds the rich
UserContext and runs the Activity Report mapper over it, asserting the counter
that reads the stamp the writer left. A seeded stamp would pass a mapper test
while production counted zero; these tests can only pass when the writer writes.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from core.models.enums import EntityStatus
from core.models.goal.goal import Goal
from core.models.principle.principle import Principle
from core.services.report.progress_report_generator import ProgressReportGenerator

pytestmark = pytest.mark.integration

_USER = "user_report_counters"


async def _seed_user(driver) -> None:
    async with driver.session() as session:
        await session.run(
            """
            MATCH (n) WHERE n.uid STARTS WITH 'counters:' OR n.uid = $user_uid
            DETACH DELETE n
            """,
            user_uid=_USER,
        )
        await session.run(
            """
            CREATE (u:User {
                uid: $uid, title: 'Report Counters User', email: 'counters@test.local',
                display_name: 'Report Counters User', created_at: datetime(), updated_at: datetime()
            })
            """,
            uid=_USER,
        )


async def _mapped(services) -> dict:
    """Build the rich context and map it the way ``generate()`` does for a 7d report."""
    builder = services.users.context_builder
    assert builder is not None
    context_result = await builder.build_rich(_USER, window="7d")
    assert context_result.is_ok, context_result.error
    generator = ProgressReportGenerator(
        executor=MagicMock(),
        activity_report_service=MagicMock(),
        context_builder=builder,
    )
    now = datetime.now()
    return generator._completions_from_context(
        context_result.value,
        None,
        window_start=now - timedelta(days=7),
        window_end=now + timedelta(minutes=5),
    )


@pytest.mark.asyncio
async def test_goal_progress_door_counts_as_progressed(services, neo4j_driver, clean_neo4j):
    await _seed_user(neo4j_driver)
    created = await services.goals.create(
        Goal(uid="counters:goal", user_uid=_USER, title="Ship it", status=EntityStatus.ACTIVE)
    )
    assert created.is_ok, created.error

    moved = await services.goals.update_goal_progress("counters:goal", 40.0)
    assert moved.is_ok, moved.error

    completions = await _mapped(services)
    assert completions["goals_progressed"] == 1
    assert completions["goals_details"][0]["progress"] == 40.0


@pytest.mark.asyncio
async def test_principle_reflection_door_counts_as_reviewed(services, neo4j_driver, clean_neo4j):
    await _seed_user(neo4j_driver)
    created = await services.principles.create(
        Principle(
            uid="counters:principle",
            user_uid=_USER,
            title="Honesty",
            statement="Say the true thing",
            status=EntityStatus.ACTIVE,
        )
    )
    assert created.is_ok, created.error

    reflected = await services.principles.record_principle_reflection(
        "counters:principle", _USER, "aligned", "Told the client the real timeline"
    )
    assert reflected.is_ok, reflected.error

    completions = await _mapped(services)
    assert completions["principles_reviewed"] == 1


@pytest.mark.asyncio
async def test_choice_decided_in_period_counts_even_when_old_and_closed(
    services, neo4j_driver, clean_neo4j
):
    """A choice created before the window, decided inside it and already completed is
    admitted by its decision stamp — the draft/active-or-created-in-window predicate
    alone would drop it before the mapper could see ``decided_at``."""
    await _seed_user(neo4j_driver)
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MATCH (u:User {uid: $user_uid})
            CREATE (c:Entity:Choice {
                uid: 'counters:choice', user_uid: $user_uid, entity_type: 'choice',
                title: 'Take the job', status: 'completed',
                created_at: datetime() - duration({days: 40}),
                updated_at: datetime() - duration({days: 40}),
                decided_at: datetime() - duration({days: 2})
            })
            CREATE (u)-[:OWNS]->(c)
            """,
            user_uid=_USER,
        )

    completions = await _mapped(services)
    assert completions["choices_made"] == 1
    assert [c["uid"] for c in completions["choices_details"]] == ["counters:choice"]
