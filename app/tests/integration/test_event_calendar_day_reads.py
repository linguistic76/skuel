"""An event's day is its ``event_date``: the today stat, "upcoming", and reschedules.

``start_time`` is a LOCAL TIME — a time of day with no date in it — so it cannot say
which day an event is on. ``EventsBackend.get_stats_for_user``'s "today" and
``PsApplicationDiscoveryService.find_events_applying_knowledge``'s "upcoming" both
read ``event_date``, the event's calendar day, against a ``$today`` parameter.

``count_recent_reschedules`` counts the ``rescheduled_at`` stamps ``update_event``
writes when an update moves the date. Every row here is written by the real
writers; each test first reads the raw properties back and asserts their types.
"""

from __future__ import annotations

from datetime import date, time, timedelta

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.backends.activity_backends import EventsBackend
from adapters.persistence.neo4j.backends.curriculum_backends import PsBackend
from core.models.enums.neo_labels import NeoLabel
from core.models.event.event import Event
from core.models.event.event_update_intent import EventUpdateIntent
from core.models.pathways.path_step import PathStep
from core.models.relationship_names import RelationshipName
from core.services.events.events_core_service import EventsCoreService
from core.services.ps.ps_application_discovery_service import PsApplicationDiscoveryService

pytestmark = [pytest.mark.asyncio(loop_scope="session"), pytest.mark.integration]

USER = "user_event_calendar_days"
PATH_STEP = "ps.utc-arc.event-days"
TODAY = date.today()


def _event(uid: str, event_date: date, start: time = time(9, 30)) -> Event:
    return Event(uid=uid, user_uid=USER, title=uid, event_date=event_date, start_time=start)


@pytest_asyncio.fixture
async def events_backend(neo4j_driver, clean_neo4j) -> EventsBackend:
    return EventsBackend(neo4j_driver, NeoLabel.EVENT, Event, base_label=NeoLabel.ENTITY)


async def _create(backend: EventsBackend, *events: Event) -> None:
    for event in events:
        created = await backend.create(event)
        assert created.is_ok, created


async def _raw_types(neo4j_driver, uid: str) -> dict[str, str]:
    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MATCH (e:Event {uid: $uid})
            RETURN valueType(e.event_date) AS event_date,
                   valueType(e.start_time) AS start_time,
                   valueType(e.rescheduled_at) AS rescheduled_at,
                   e.rescheduled_at AS rescheduled_value
            """,
            uid=uid,
        )
        record = await result.single()
        assert record is not None, uid
        return dict(record)


class TestTodayStat:
    async def test_an_event_dated_today_counts_as_today(self, events_backend, neo4j_driver) -> None:
        await _create(
            events_backend,
            _event("event.utc.today", TODAY),
            _event("event.utc.tomorrow", TODAY + timedelta(days=1)),
        )
        types = await _raw_types(neo4j_driver, "event.utc.today")
        # The premise: a calendar day stored as a string, a time of day as a LOCAL TIME.
        assert types["event_date"].startswith("STRING"), types
        assert types["start_time"].startswith("LOCAL TIME"), types

        stats = await events_backend.get_stats_for_user(USER)

        assert stats.is_ok, stats
        assert stats.value["total"] == 2
        assert stats.value["today"] == 1


class TestUpcomingEventsApplyingKnowledge:
    async def test_events_dated_today_or_later_are_upcoming(
        self, events_backend, neo4j_driver
    ) -> None:
        ps_backend = PsBackend(
            neo4j_driver, NeoLabel.PATH_STEP, PathStep, base_label=NeoLabel.ENTITY
        )
        step = await ps_backend.create(PathStep(uid=PATH_STEP, title="Event days"))
        assert step.is_ok, step
        dated = {
            "event.utc.yesterday": TODAY - timedelta(days=1),
            "event.utc.today": TODAY,
            "event.utc.next_week": TODAY + timedelta(days=7),
        }
        await _create(events_backend, *(_event(uid, day) for uid, day in dated.items()))
        linked = await events_backend.create_relationships_batch(
            [(uid, PATH_STEP, RelationshipName.APPLIES_KNOWLEDGE.value, None) for uid in dated]
        )
        assert linked.is_ok, linked

        discovery = PsApplicationDiscoveryService(repo=ps_backend)
        upcoming = await discovery.find_events_applying_knowledge(PATH_STEP, USER)
        every = await discovery.find_events_applying_knowledge(PATH_STEP, USER, upcoming_only=False)

        assert upcoming.is_ok, upcoming
        assert set(upcoming.value) == {"event.utc.today", "event.utc.next_week"}
        assert every.is_ok, every
        assert set(every.value) == set(dated)


class TestRecentReschedules:
    async def test_moving_an_event_counts_as_a_reschedule(
        self, events_backend, neo4j_driver
    ) -> None:
        service = EventsCoreService(backend=events_backend, event_bus=InMemoryEventBus())
        booked = TODAY + timedelta(days=3)
        await _create(
            events_backend,
            _event("event.utc.moved", booked),
            _event("event.utc.renamed", booked),
        )

        moved = await service.update_event(
            "event.utc.moved", EventUpdateIntent(event_date=booked + timedelta(days=2))
        )
        renamed = await service.update_event(
            "event.utc.renamed", EventUpdateIntent(title="Renamed, same day")
        )
        assert moved.is_ok and renamed.is_ok, (moved, renamed)

        types = await _raw_types(neo4j_driver, "event.utc.moved")
        # An aware UTC instant, stored through the mapper as an offset string.
        assert types["rescheduled_at"].startswith("STRING"), types
        assert str(types["rescheduled_value"]).endswith("+00:00"), types
        assert (await _raw_types(neo4j_driver, "event.utc.renamed"))["rescheduled_at"] == "NULL"

        count = await events_backend.count_recent_reschedules(USER)

        assert count.is_ok, count
        assert count.value == 1
