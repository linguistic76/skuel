"""An event's span — ``end_time - start_time`` on its one day — lies within 5-720 minutes.

The rule has two halves in ``core.models.validation_rules``:

- ``event_span_error`` — judged at create by ``EventsCoreService._validate_create``,
  which both service doors reach (the entity door and ``create_event``; see
  ``test_activity_create_validation_reach.py``). With either time missing there is no
  span, and nothing to refuse.
- ``patch_span_error`` — ``EventsCoreService._validate_update`` judges the merged
  times, and only when the patch names ``start_time`` or ``end_time``: a status change,
  a date move or a title edit of an event already stored out of bounds is not refused.
"""

from __future__ import annotations

from datetime import date, time, timedelta

import pytest

from core.constants import EventSpan
from core.events.base import BaseEvent
from core.models.event.event import Event
from core.models.event.event_update_intent import EventUpdateIntent
from core.models.validation_rules import event_span_error, patch_span_error
from core.services.events.events_core_service import EventsCoreService
from tests.helpers.status_guarded_backend import StatusGuardedWriteRecorder, guarded_backend

USER = "user_span"
EVENT = "event_span"
BOOKED = date.today() + timedelta(days=5)


# =============================================================================
# The bounds
# =============================================================================


class TestEventSpanError:
    @pytest.mark.parametrize(
        ("start", "end"),
        [
            (time(9, 0), time(9, 5)),
            (time(9, 0), time(10, 30)),
            (time(9, 0), time(21, 0)),
        ],
        ids=["min", "mid", "max"],
    )
    def test_a_span_within_the_bounds_passes(self, start: time, end: time) -> None:
        assert event_span_error(start, end) is None

    @pytest.mark.parametrize(
        ("start", "end", "fragment"),
        [
            (time(9, 0), time(9, 4), f"at least {EventSpan.MIN_MINUTES} minutes"),
            (time(9, 0), time(9, 0), f"at least {EventSpan.MIN_MINUTES} minutes"),
            (time(10, 0), time(9, 0), f"at least {EventSpan.MIN_MINUTES} minutes"),
            (time(9, 0), time(21, 1), "at most 12 hours"),
        ],
        ids=["4-min", "zero", "end-before-start", "721-min"],
    )
    def test_a_span_outside_the_bounds_is_named(
        self, start: time, end: time, fragment: str
    ) -> None:
        message = event_span_error(start, end)
        assert message is not None
        assert fragment in message

    @pytest.mark.parametrize(
        ("start", "end"), [(None, time(9, 0)), (time(9, 0), None), (None, None)]
    )
    def test_no_span_without_both_times(self, start: time | None, end: time | None) -> None:
        assert event_span_error(start, end) is None


class TestPatchSpanError:
    def test_a_patch_naming_neither_time_is_never_judged(self) -> None:
        """The stored span is out of bounds, and a status change still passes."""
        assert (
            patch_span_error({"status": "completed"}, start_time=time(9), end_time=time(9, 1))
            is None
        )

    def test_the_merged_times_are_judged(self) -> None:
        """Moving only the end judges it against the STORED start."""
        assert patch_span_error(
            {"end_time": time(9, 2)}, start_time=time(9), end_time=time(10)
        ) == event_span_error(time(9), time(9, 2))

    def test_clearing_a_time_leaves_no_span(self) -> None:
        assert patch_span_error({"end_time": None}, start_time=time(9), end_time=time(10)) is None


# =============================================================================
# Event update — the merged times, only when the patch names one
# =============================================================================


class _RecordingBus:
    def __init__(self) -> None:
        self.events: list[BaseEvent] = []

    async def publish_async(self, event: BaseEvent) -> None:
        self.events.append(event)


def _event(start: time, end: time) -> Event:
    return Event(
        uid=EVENT,
        user_uid=USER,
        title="Study group",
        event_date=BOOKED,
        start_time=start,
        end_time=end,
    )


def _events_core(stored: Event) -> tuple[EventsCoreService, StatusGuardedWriteRecorder[Event]]:
    backend, recorder = guarded_backend(stored, stored)
    return EventsCoreService(backend=backend, event_bus=_RecordingBus()), recorder


@pytest.mark.asyncio
class TestEventUpdate:
    @pytest.mark.parametrize(
        ("stored", "patch"),
        [
            pytest.param(
                _event(time(9), time(10)),
                EventUpdateIntent(end_time=time(9, 2)),
                id="shortening-the-end-below-the-floor",
            ),
            pytest.param(
                _event(time(9), time(10)),
                EventUpdateIntent(start_time=time(9, 58)),
                id="moving-the-start-up-to-the-end",
            ),
            pytest.param(
                _event(time(9), time(10)),
                EventUpdateIntent(end_time=time(22, 0)),
                id="stretching-past-twelve-hours",
            ),
            pytest.param(
                _event(time(9), time(10)),
                EventUpdateIntent(
                    event_date=BOOKED + timedelta(days=1), start_time=time(23), end_time=time(1)
                ),
                id="a-reschedule-across-midnight",
            ),
        ],
    )
    async def test_a_patch_leaving_the_span_out_of_bounds_is_refused(
        self, stored: Event, patch: EventUpdateIntent
    ) -> None:
        service, recorder = _events_core(stored)

        result = await service.update_event(EVENT, patch)

        assert result.is_error
        assert result.expect_error().details["field"] == "end_time"
        assert recorder.calls == [], "a refused patch must not reach the write"

    @pytest.mark.parametrize(
        ("stored", "patch"),
        [
            pytest.param(
                _event(time(9), time(10)),
                EventUpdateIntent(start_time=time(14), end_time=time(15, 30)),
                id="a-reschedule-within-the-bounds",
            ),
            pytest.param(
                _event(time(9), time(9, 1)),
                EventUpdateIntent(status="completed"),
                id="completing-an-event-stored-out-of-bounds",
            ),
            pytest.param(
                _event(time(9), time(9, 1)),
                EventUpdateIntent(event_date=BOOKED + timedelta(days=1)),
                id="moving-the-date-of-an-event-stored-out-of-bounds",
            ),
            pytest.param(
                _event(time(9), time(10)),
                EventUpdateIntent(end_time=None),
                id="clearing-the-end-time",
            ),
        ],
    )
    async def test_a_patch_leaving_the_span_in_bounds_or_untouched_is_written(
        self, stored: Event, patch: EventUpdateIntent
    ) -> None:
        service, recorder = _events_core(stored)

        result = await service.update_event(EVENT, patch)

        assert result.is_ok, result
        assert len(recorder.calls) == 1
