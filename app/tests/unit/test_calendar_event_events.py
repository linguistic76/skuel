"""Smoke tests for calendar_event_events domain events.

Calendar event dataclasses had 0% coverage. These tests verify each event
is constructible and that its `event_type` discriminator string is stable —
downstream subscribers route on these strings.
"""

from datetime import date

from core.events.calendar_event_events import (
    CalendarEventCompleted,
    CalendarEventCreated,
    CalendarEventDeleted,
    CalendarEventRescheduled,
    CalendarEventUpdated,
    EventAttendeeAdded,
    EventAttendeeRemoved,
)


class TestCalendarEventCreated:
    def test_construct_and_event_type(self) -> None:
        evt = CalendarEventCreated(
            event_uid="event_test_1",
            user_uid="user_alice",
            title="Sprint planning",
            event_date=date(2026, 5, 15),
            calendar_event_type="meeting",
        )
        assert evt.event_type == "calendar_event.created"
        assert evt.event_uid == "event_test_1"
        assert evt.user_uid == "user_alice"
        assert evt.title == "Sprint planning"
        assert evt.event_date == date(2026, 5, 15)
        assert evt.calendar_event_type == "meeting"
        assert evt.metadata is None
        # BaseEvent auto-stamps occurred_at
        assert evt.occurred_at is not None

    def test_metadata_optional(self) -> None:
        evt = CalendarEventCreated(
            event_uid="event_x",
            user_uid="user_x",
            title="x",
            event_date=date(2026, 1, 1),
            calendar_event_type="deadline",
            metadata={"source": "manual"},
        )
        assert evt.metadata == {"source": "manual"}


class TestCalendarEventUpdated:
    def test_construct_and_event_type(self) -> None:
        evt = CalendarEventUpdated(
            event_uid="event_2",
            user_uid="user_alice",
            updated_fields={"title": "Renamed"},
        )
        assert evt.event_type == "calendar_event.updated"
        assert evt.updated_fields == {"title": "Renamed"}


class TestCalendarEventCompleted:
    def test_construct_with_quality_score(self) -> None:
        evt = CalendarEventCompleted(
            event_uid="event_3",
            user_uid="user_alice",
            completion_date=date(2026, 5, 16),
            quality_score=8,
        )
        assert evt.event_type == "calendar_event.completed"
        assert evt.quality_score == 8

    def test_quality_score_optional(self) -> None:
        evt = CalendarEventCompleted(
            event_uid="event_4",
            user_uid="user_alice",
            completion_date=date(2026, 5, 16),
            quality_score=None,
        )
        assert evt.quality_score is None


class TestCalendarEventDeleted:
    def test_construct_and_event_type(self) -> None:
        evt = CalendarEventDeleted(
            event_uid="event_5",
            user_uid="user_alice",
            title="Cancelled meeting",
        )
        assert evt.event_type == "calendar_event.deleted"
        assert evt.title == "Cancelled meeting"


class TestCalendarEventRescheduled:
    def test_construct_and_event_type(self) -> None:
        evt = CalendarEventRescheduled(
            event_uid="event_6",
            user_uid="user_alice",
            old_date=date(2026, 5, 15),
            new_date=date(2026, 5, 17),
        )
        assert evt.event_type == "calendar_event.rescheduled"
        assert evt.old_date == date(2026, 5, 15)
        assert evt.new_date == date(2026, 5, 17)


class TestEventAttendeeAdded:
    def test_construct_and_event_type(self) -> None:
        evt = EventAttendeeAdded(
            event_uid="event_7",
            event_title="Standup",
            attendee_uid="user_bob",
            added_by_uid="user_alice",
            role="attendee",
        )
        assert evt.event_type == "calendar_event.attendee_added"
        assert evt.attendee_uid == "user_bob"
        assert evt.role == "attendee"


class TestEventAttendeeRemoved:
    def test_construct_and_event_type(self) -> None:
        evt = EventAttendeeRemoved(
            event_uid="event_7",
            event_title="Standup",
            attendee_uid="user_bob",
            removed_by_uid="user_alice",
        )
        assert evt.event_type == "calendar_event.attendee_removed"
        assert evt.attendee_uid == "user_bob"


class TestEventTypeStringsAreUnique:
    def test_all_event_types_distinct(self) -> None:
        """Subscribers route on event_type strings — collisions would be a bug."""
        types = {
            CalendarEventCreated(
                event_uid="x",
                user_uid="u",
                title="t",
                event_date=date(2026, 1, 1),
                calendar_event_type="meeting",
            ).event_type,
            CalendarEventUpdated(event_uid="x", user_uid="u", updated_fields={}).event_type,
            CalendarEventCompleted(
                event_uid="x",
                user_uid="u",
                completion_date=date(2026, 1, 1),
                quality_score=None,
            ).event_type,
            CalendarEventDeleted(event_uid="x", user_uid="u", title="t").event_type,
            CalendarEventRescheduled(
                event_uid="x",
                user_uid="u",
                old_date=date(2026, 1, 1),
                new_date=date(2026, 1, 2),
            ).event_type,
            EventAttendeeAdded(
                event_uid="x",
                event_title="t",
                attendee_uid="a",
                added_by_uid="b",
                role="attendee",
            ).event_type,
            EventAttendeeRemoved(
                event_uid="x",
                event_title="t",
                attendee_uid="a",
                removed_by_uid="b",
            ).event_type,
        }
        assert len(types) == 7
