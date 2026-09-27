"""A reschedule is recorded on the event: ``update_event`` stamps ``rescheduled_at``.

``EventsBackend.count_recent_reschedules`` counts events whose ``rescheduled_at`` is
inside the last 30 days, and the rescheduling-pattern handler classifies that count
(rare / occasional / chronic, and a chronic insight). Nothing wrote the property, so
the count was always 0. The writer is the chokepoint that already decides "this is a
reschedule" to publish ``CalendarEventRescheduled``: a patch that moves
``event_date`` carries the stamp in the same write, and one decision drives both.

The count against a real graph is ``tests/integration/test_event_calendar_day_reads.py``.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from core.events.base import BaseEvent
from core.events.calendar_event_events import CalendarEventRescheduled, CalendarEventUpdated
from core.models.event.event import Event
from core.models.event.event_update_intent import EventUpdateIntent
from core.services.events.events_core_service import EventsCoreService
from tests.helpers.status_guarded_backend import guarded_backend

USER = "user_event_reschedule"
EVENT = "event_reschedule"
BOOKED = date.today() + timedelta(days=5)
MOVED = date.today() + timedelta(days=8)


class _RecordingBus:
    def __init__(self) -> None:
        self.events: list[BaseEvent] = []

    async def publish_async(self, event: BaseEvent) -> None:
        self.events.append(event)

    def of[E: BaseEvent](self, event_type: type[E]) -> list[E]:
        return [event for event in self.events if isinstance(event, event_type)]


def _event(event_date: date, title: str = "Study group") -> Event:
    return Event(uid=EVENT, user_uid=USER, title=title, event_date=event_date)


def _service(after: Event):
    backend, recorder = guarded_backend(_event(BOOKED), after)
    bus = _RecordingBus()
    return EventsCoreService(backend=backend, event_bus=bus), recorder, bus


@pytest.mark.asyncio
class TestRescheduleStamp:
    async def test_moving_the_date_stamps_rescheduled_at_in_the_same_write(self) -> None:
        service, recorder, bus = _service(_event(MOVED))

        result = await service.update_event(EVENT, EventUpdateIntent(event_date=MOVED))

        assert result.is_ok, result
        assert len(recorder.calls) == 1
        stamp = recorder.last_updates["rescheduled_at"]
        # An aware UTC instant — stored as an offset string, it reads as the true moment.
        assert stamp.tzinfo is not None and stamp.utcoffset() == timedelta(0)
        assert recorder.last_updates["event_date"] == MOVED
        rescheduled = bus.of(CalendarEventRescheduled)
        assert [(e.old_date, e.new_date) for e in rescheduled] == [(BOOKED, MOVED)]

    async def test_an_edit_that_keeps_the_date_writes_no_stamp(self) -> None:
        service, recorder, bus = _service(_event(BOOKED, title="Study group (room 4)"))

        result = await service.update_event(EVENT, EventUpdateIntent(title="Study group (room 4)"))

        assert result.is_ok, result
        assert "rescheduled_at" not in recorder.last_updates
        assert bus.of(CalendarEventRescheduled) == []
        assert len(bus.of(CalendarEventUpdated)) == 1

    async def test_re_posting_the_same_date_is_not_a_reschedule(self) -> None:
        service, recorder, bus = _service(_event(BOOKED))

        result = await service.update_event(EVENT, EventUpdateIntent(event_date=BOOKED))

        assert result.is_ok, result
        assert "rescheduled_at" not in recorder.last_updates
        assert bus.of(CalendarEventRescheduled) == []

    async def test_the_stamp_stays_out_of_the_updated_fields(self) -> None:
        """``updated_fields`` names what the caller changed; the stamp is the service's."""
        service, _recorder, bus = _service(_event(BOOKED))

        await service.update_event(EVENT, EventUpdateIntent(event_date=BOOKED, title="Renamed"))

        updated = bus.of(CalendarEventUpdated)
        assert len(updated) == 1
        assert "rescheduled_at" not in updated[0].updated_fields
