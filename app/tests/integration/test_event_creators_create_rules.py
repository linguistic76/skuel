"""Every Events creator writes through the domain's create door, so its rules hold.

The create door (``EventsCoreService.create``) runs ``_validate_create`` — the span
rule: ``end_time - start_time`` within ``EventSpan`` — then writes the event's link
edges, then announces it. The facade's four other creators reach no route; each
persists through that door, so none writes an event the doors refuse:

- ``create_event_with_context`` — a request whose span is out of bounds;
- ``create_recurring_instances`` — copies of a source event stored out of bounds;
- ``create_recurring_events`` — a ``duration_minutes`` out of bounds, or a start
  whose end wraps past midnight;
- ``create_recurring_events_for_habit`` — its events carry no times, so the span
  has nothing to judge; its habit link rides on the entity and the door writes it.

Each refusal has its control: the same creator with a span in bounds writes, and a
habit link it carries lands as the ``REINFORCES_HABIT`` edge.
"""

from __future__ import annotations

from datetime import time, timedelta
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.models.enums import RecurrencePattern
from core.models.event.event_request import EventCreateRequest, RecurringInstancesRequest
from core.models.type_hints import UserUID
from core.services.user import UserContext
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone
from tests.integration._activity_link_rig import create, signed_in_client

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from neo4j import AsyncDriver

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "evcreate"
USER = f"user_{MARK}_caller"


@pytest_asyncio.fixture(loop_scope="session", scope="module")
async def habit(skuel_app: Any) -> AsyncIterator[str]:  # boundary: fasthtml-app
    async with signed_in_client(skuel_app, USER, MARK) as client:
        yield await create(client, "habits", f"{MARK} habit")


@pytest_asyncio.fixture(loop_scope="session")
async def driver(
    skuel_app,
    habit: str,
) -> AsyncIterator[AsyncDriver]:
    """The graph, with every event the caller owns removed before each test."""
    graph: AsyncDriver = skuel_app.state.services.neo4j_driver
    async with graph.session() as session:
        await session.run("MATCH (e:Event {user_uid: $user}) DETACH DELETE e", user=USER)
    yield graph


async def _events(driver: AsyncDriver) -> list[dict[str, Any]]:  # boundary: neo4j rows
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (e:Event {user_uid: $user})
            OPTIONAL MATCH (e)-[:REINFORCES_HABIT]->(h:Habit)
            RETURN e.uid AS uid, e.event_type AS event_type, h.uid AS habit
            ORDER BY e.event_date
            """,
            user=USER,
        )
        return [dict(row) async for row in result]


def _day() -> str:
    return (today_in(current_zone()) + timedelta(days=3)).isoformat()


async def _context(skuel_app: Any) -> UserContext:  # boundary: fasthtml-app
    built = await skuel_app.state.services.user.context_builder.build(UserUID(USER))
    assert built.is_ok, built.error
    return built.value


class TestCreateEventWithContext:
    async def test_a_span_out_of_bounds_is_refused(
        self,
        skuel_app,
        driver: AsyncDriver,
    ) -> None:
        request = EventCreateRequest(
            title=f"{MARK} blink",
            event_date=_day(),
            start_time=time(9, 0),
            end_time=time(9, 1),
        )

        result = await skuel_app.state.services.events.create_event_with_context(
            request, await _context(skuel_app)
        )

        assert result.is_error
        assert "at least" in result.expect_error().message
        assert await _events(driver) == []

    async def test_a_span_in_bounds_is_written_with_its_habit_link(
        self,
        skuel_app,
        driver: AsyncDriver,
        habit: str,
    ) -> None:
        request = EventCreateRequest(
            title=f"{MARK} hour",
            event_date=_day(),
            start_time=time(9, 0),
            end_time=time(10, 0),
            reinforces_habit_uid=habit,
        )

        result = await skuel_app.state.services.events.create_event_with_context(
            request, await _context(skuel_app)
        )

        assert result.is_ok, result.error
        assert [(row["uid"], row["habit"]) for row in await _events(driver)] == [
            (result.value.uid, habit)
        ]


class TestCreateRecurringInstances:
    async def _source(self, skuel_app, driver: AsyncDriver, end: time) -> str:
        """A recurring event written through the create door, then its end moved —
        an event stored before the span rule held."""
        request = EventCreateRequest(
            title=f"{MARK} weekly",
            event_date=_day(),
            start_time=time(9, 0),
            end_time=time(10, 0),
            recurrence_pattern=RecurrencePattern.WEEKLY,
        )
        created = await skuel_app.state.services.events.create_event(request, UserUID(USER))
        assert created.is_ok, created.error
        async with driver.session() as session:
            await session.run(
                "MATCH (e:Event {uid: $uid}) SET e.end_time = $end",
                uid=created.value.uid,
                end=end.isoformat(),
            )
        return created.value.uid

    async def test_a_source_out_of_bounds_writes_no_instance(
        self,
        skuel_app,
        driver: AsyncDriver,
    ) -> None:
        source = await self._source(skuel_app, driver, time(9, 2))

        result = await skuel_app.state.services.events.create_recurring_instances(
            RecurringInstancesRequest(event_uid=source, count=2)
        )

        assert result.is_error
        assert [row["uid"] for row in await _events(driver)] == [source]

    async def test_a_source_in_bounds_writes_its_instances(
        self,
        skuel_app,
        driver: AsyncDriver,
    ) -> None:
        source = await self._source(skuel_app, driver, time(10, 0))

        result = await skuel_app.state.services.events.create_recurring_instances(
            RecurringInstancesRequest(event_uid=source, count=2)
        )

        assert result.is_ok, result.error
        assert len(await _events(driver)) == 3


class TestCreateRecurringEvents:
    @pytest.mark.parametrize(
        ("preferred", "minutes"), [(time(9, 0), 1), (time(9, 0), 13 * 60), (time(23, 30), 60)]
    )
    async def test_a_span_out_of_bounds_is_refused(
        self,
        skuel_app,
        driver: AsyncDriver,
        habit: str,
        preferred: time,
        minutes: int,
    ) -> None:
        result = await skuel_app.state.services.events.create_recurring_events(
            UserUID(USER),
            f"{MARK} practice",
            RecurrencePattern.DAILY,
            duration_minutes=minutes,
            preferred_time=preferred,
            days_to_create=2,
            reinforces_habit_uid=habit,
        )

        assert result.is_error
        assert await _events(driver) == []

    async def test_a_span_in_bounds_is_written_with_its_habit_link(
        self,
        skuel_app,
        driver: AsyncDriver,
        habit: str,
    ) -> None:
        result = await skuel_app.state.services.events.create_recurring_events(
            UserUID(USER),
            f"{MARK} practice",
            RecurrencePattern.DAILY,
            duration_minutes=45,
            preferred_time=time(9, 0),
            days_to_create=2,
            reinforces_habit_uid=habit,
        )

        assert result.is_ok, result.error
        rows = await _events(driver)
        assert rows, "nothing was written"
        assert {row["uid"] for row in rows} == {event.uid for event in result.value}
        assert {row["habit"] for row in rows} == {habit}


class TestCreateRecurringEventsForHabit:
    async def test_each_event_is_written_with_its_habit_link_and_kind(
        self,
        skuel_app,
        driver: AsyncDriver,
        habit: str,
    ) -> None:
        result = await skuel_app.state.services.events.create_recurring_events_for_habit(
            habit, await _context(skuel_app), RecurrencePattern.DAILY, days_to_create=1
        )

        assert result.is_ok, result.error
        rows = await _events(driver)
        assert {row["uid"] for row in rows} == {event.uid for event in result.value}
        assert len(rows) == 2
        assert {(row["habit"], row["event_type"]) for row in rows} == {(habit, "personal")}
