"""A read that builds its models through the DTO answers with the driver's temporals converted.

The search, traversal and range reads turn raw node records into models through
``{Domain}DTO.from_dict``. A raw record carries the driver's own temporal types: the
mapper writes a ``time`` as a native LOCAL TIME (an Event's ``start_time``), and Cypher
``datetime()`` stamps a native (bulk upsert's ``updated_at`` when a vault file is
re-ingested). The JSON boundary refuses a driver temporal, so each door below answers
only because the DTO parsers convert one as ``from_neo4j_node`` does; without that, a
door answers 500.

Each door is read over the bootstrapped app. The entities come from the domains' real
create and link doors; only the re-ingest stamp is written by hand, in the shape its
writer stores (a native ``datetime()``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from adapters.inbound.fasthtml_types import FastHTMLApp
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from tests.helpers.seed_uids import seed_user_uid
from tests.integration._activity_link_rig import (
    create,
    seed_published_path_step,
    signed_in_client,
)

if TYPE_CHECKING:
    from neo4j import AsyncDriver

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

READER = seed_user_uid("dtotemporal_reader")
MARK = "dtotemporal"
STEP = "ps.dtotemporal.step"
EVENT_DAY = {"event_date": "2026-11-20", "start_time": "09:30:00", "end_time": "10:15:00"}


async def _stamp_as_reingest(driver: AsyncDriver, uid: str) -> None:
    """``updated_at`` as bulk upsert writes it on a re-ingest: a native ``datetime()``."""
    async with driver.session() as session:
        record = await (
            await session.run(
                "MATCH (n:Entity {uid: $uid}) SET n.updated_at = datetime() "
                "RETURN n.updated_at AS stamp",
                uid=uid,
            )
        ).single()
    assert record is not None
    assert type(record["stamp"]).__module__ == "neo4j.time"


async def test_the_events_a_habit_reinforces_answer_with_their_times(
    skuel_app: FastHTMLApp,
) -> None:
    async with signed_in_client(skuel_app, READER, MARK) as client:
        habit = await create(client, "habits", "Stretch daily")
        event = await create(
            client, "events", "Stretch class", reinforces_habit_uid=habit, **EVENT_DAY
        )
        # The create door stores the times as native LOCAL TIMEs.
        driver: AsyncDriver = skuel_app.state.services.neo4j_driver
        async with driver.session() as session:
            record = await (
                await session.run(
                    "MATCH (e:Event {uid: $uid})-[:REINFORCES_HABIT]->(:Habit {uid: $habit}) "
                    "RETURN e.start_time AS start_time",
                    uid=event,
                    habit=habit,
                )
            ).single()
        assert record is not None
        assert type(record["start_time"]).__name__ == "Time"

        response = await client.get("/api/events/habit", params={"habit_uid": habit})

    assert response.status_code == 200, response.text
    [answered] = response.json()
    assert answered["uid"] == event
    assert (answered["start_time"], answered["end_time"]) == ("09:30:00", "10:15:00")
    assert answered["event_date"] == "2026-11-20"


async def test_a_reingested_principle_answers_for_the_goal_it_supports(
    skuel_app: FastHTMLApp,
) -> None:
    async with signed_in_client(skuel_app, READER, MARK) as client:
        goal = await create(client, "goals", "Run a 10k")
        principle = await create(client, "principles", "Consistency over intensity")
        linked = await client.post(
            "/api/goals/link-principle", json={"goal_uid": goal, "principle_uid": principle}
        )
        assert linked.status_code == 200, linked.text
        await _stamp_as_reingest(skuel_app.state.services.neo4j_driver, principle)

        response = await client.get("/api/principles/goal", params={"goal_uid": goal})

    assert response.status_code == 200, response.text
    [answered] = response.json()
    assert answered["uid"] == principle
    assert answered["updated_at"].startswith("20")


async def test_a_reingested_path_step_is_found_by_search(skuel_app: FastHTMLApp) -> None:
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    async with signed_in_client(skuel_app, READER, MARK) as client:
        await seed_published_path_step(driver, STEP, "Dtotemporal breathing basics")
        await _stamp_as_reingest(driver, STEP)

        response = await client.get("/api/path-steps/search", params={"q": "Dtotemporal"})

    assert response.status_code == 200, response.text
    assert [step["uid"] for step in response.json()] == [STEP]
