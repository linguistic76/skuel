"""A habit's learned state accumulates on its node and reaches the analytics a client reads.

ADR-048's habit learning — the completion-hour histogram, the preferred hour, the on-time
rate, the completion count, the difficulty level — is stored as properties on the habit's
node and read back raw, never through the ``Habit`` model, which declares none of them.

- Two completions through the real completion door accumulate: the second builds on the
  first instead of starting over.
- A completion that arrives while another one's write is still open waits for it and builds
  on what it wrote — held here with a real open transaction on the node.
- ``GET /api/habits/analytics`` counts the learned state in ``learned_insights``; a user
  whose habit has learned nothing reads zeros there.

Habits are created at the real create door (``_activity_link_rig.py``); completions go through
``POST /api/context/habit/complete``, whose ``HabitCompleted`` the bootstrapped bus delivers
to the learning handler before the response returns.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.events.habit_events import HabitCompleted, HabitMissed
from core.models.type_hints import UserUID
from tests.integration._activity_link_rig import create, signed_in_client

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import httpx

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "zzzhablearn"
USER = UserUID(f"user_{MARK}")
QUIET_MARK = "zzzhabquiet"
QUIET_USER = UserUID(f"user_{QUIET_MARK}")


async def _props(skuel_app: Any, uid: str) -> dict[str, Any]:  # boundary: fasthtml-app
    """The habit node's stored properties, read raw."""
    async with skuel_app.state.services.neo4j_driver.session() as session:
        record = await (
            await session.run(
                "MATCH (h:Entity:Habit {uid: $uid}) RETURN properties(h) AS p", uid=uid
            )
        ).single()
    assert record is not None, uid
    props: dict[str, Any] = record["p"]  # boundary: raw neo4j node properties
    return props


def _histogram_total(props: dict[str, Any]) -> int:  # boundary: raw neo4j node properties
    return sum(json.loads(props["completion_hours_json"]).values())


async def _complete(http: httpx.AsyncClient, habit_uid: str) -> None:
    response = await http.post(
        "/api/context/habit/complete", params={"habit_uid": habit_uid}, json={"quality": "good"}
    )
    assert response.status_code == 200, response.text


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def client(skuel_app: Any) -> AsyncIterator[httpx.AsyncClient]:  # boundary: fasthtml-app
    async with signed_in_client(skuel_app, USER, MARK) as http:
        yield http


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def quiet_client(
    skuel_app: Any,  # boundary: fasthtml-app
) -> AsyncIterator[httpx.AsyncClient]:
    async with signed_in_client(skuel_app, QUIET_USER, QUIET_MARK) as http:
        yield http


async def test_two_completions_accumulate(
    skuel_app: Any,  # boundary: fasthtml-app
    client: httpx.AsyncClient,
) -> None:
    habit = await create(client, "habits", f"{MARK} accumulates")

    await _complete(client, habit)
    first = await _props(skuel_app, habit)
    assert first["learned_completion_count"] == 1
    assert _histogram_total(first) == 1

    await _complete(client, habit)
    second = await _props(skuel_app, habit)
    assert second["learned_completion_count"] == 2
    assert _histogram_total(second) == 2
    assert second["learned_on_time_rate"] == 1.0
    assert second["learned_preferred_hour"] in {
        int(h) for h in json.loads(second["completion_hours_json"])
    }


async def test_a_completion_waits_for_one_in_flight(
    skuel_app: Any,  # boundary: fasthtml-app
    client: httpx.AsyncClient,
) -> None:
    """The learning write takes the node's lock before it reads. A completion whose write
    is still open holds that lock; the next one waits, then builds on it — never on the
    state from before it."""
    habit = await create(client, "habits", f"{MARK} in flight")
    handler = skuel_app.state.services.habits.event_handler
    driver = skuel_app.state.services.neo4j_driver

    async with driver.session() as session:
        tx = await session.begin_transaction()
        try:
            # The first completion's write, as the handler makes it — not yet committed.
            await tx.run(
                """
                MATCH (h:Entity:Habit {uid: $uid})
                SET h.completion_hours_json = '{"3": 1}', h.learned_preferred_hour = 3,
                    h.learned_on_time_rate = 1.0, h.learned_completion_count = 1
                """,
                uid=habit,
            )
            second = asyncio.create_task(
                handler.handle_habit_completed(HabitCompleted(habit_uid=habit, user_uid=USER))
            )
            await asyncio.sleep(1.0)
            assert not second.done(), "the second completion must wait for the open write"
            await tx.commit()
        except BaseException:  # rollback, then re-raise: an open transaction must not leak
            await tx.rollback()
            raise
    await second

    props = await _props(skuel_app, habit)
    assert props["learned_completion_count"] == 2
    assert _histogram_total(props) == 2
    assert "_hl_lock" not in props


async def test_analytics_count_the_learned_state(
    skuel_app: Any,  # boundary: fasthtml-app
    client: httpx.AsyncClient,
    quiet_client: httpx.AsyncClient,
) -> None:
    learned = await create(client, "habits", f"{MARK} learned")
    await _complete(client, learned)
    await _complete(client, learned)
    # The difficulty a run of misses leaves, as the missed-habit handler writes it.
    await skuel_app.state.services.habits.event_handler.handle_habit_missed(
        HabitMissed(
            habit_uid=learned,
            user_uid=USER,
            scheduled_date=datetime(2026, 10, 1, 9, tzinfo=UTC),
            consecutive_misses=3,
        )
    )
    await create(quiet_client, "habits", f"{QUIET_MARK} untouched")

    response = await client.get("/api/habits/analytics")
    assert response.status_code == 200, response.text
    insights = response.json()["learned_insights"]
    assert insights["habits_with_timing_data"] >= 1
    assert insights["habits_with_difficulty"] == 1
    assert insights["avg_on_time_rate"] == 1.0

    # The control: a user whose habit has learned nothing reads nothing learned.
    quiet = await quiet_client.get("/api/habits/analytics")
    assert quiet.status_code == 200, quiet.text
    assert quiet.json()["learned_insights"] == {
        "habits_with_difficulty": 0,
        "habits_with_timing_data": 0,
        "avg_on_time_rate": None,
    }
