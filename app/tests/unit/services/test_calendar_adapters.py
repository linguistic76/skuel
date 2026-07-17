"""Smoke tests for calendar_adapters.

The CalendarTrackable adapter classes had 0% coverage. These tests verify
construction, basic delegation, and the create_adapter factory's error path.
Mock entities are SimpleNamespace, matching the style of test_calendar_converters.
"""

from datetime import date, datetime, time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from adapters.calendar_adapters import (
    EventAdapter,
    HabitAdapter,
    TaskAdapter,
    adapt_entities,
    create_adapter,
)
from core.models.enums import (
    ActivityType,
    EntityStatus,
    Priority,
    Visibility,
)
from core.models.event.event_request import EventType
from core.ports.calendar_protocol import WindowKind


def _make_event(**overrides):
    """Build a minimal mock event the EventAdapter can wrap."""
    base = SimpleNamespace(
        uid="event_test_1",
        title="Sprint planning",
        event_type=EventType.MEETING,
        priority="MEDIUM",
        status="SCHEDULED",
        event_date=date(2026, 1, 15),
        start_time=time(10, 0),
        end_time=time(11, 0),
        location="Room 101",
        description="Weekly sync",
        related_uids=["task_a"],
        tags=["work"],
        visibility=Visibility.PRIVATE,
        recurrence_pattern=None,
        color=None,
    )
    for key, value in overrides.items():
        setattr(base, key, value)

    # Mirror Event.start_datetime()/end_datetime(): the adapter combines
    # event_date + start/end time into datetimes (None when either is missing).
    base.start_datetime = lambda: (
        datetime.combine(base.event_date, base.start_time)
        if base.event_date and base.start_time
        else None
    )
    base.end_datetime = lambda: (
        datetime.combine(base.event_date, base.end_time)
        if base.event_date and base.end_time
        else None
    )
    return base


# ============================================================================
# EventAdapter
# ============================================================================


class TestEventAdapterIdentity:
    def test_uid_and_title(self) -> None:
        adapter = EventAdapter(_make_event())
        assert adapter.uid == "event_test_1"
        assert adapter.title == "Sprint planning"


class TestEventAdapterActivityType:
    def test_meeting_type(self) -> None:
        adapter = EventAdapter(_make_event(event_type=EventType.MEETING))
        assert adapter.get_activity_type() == ActivityType.MEETING

    def test_deadline_type(self) -> None:
        adapter = EventAdapter(_make_event(event_type=EventType.DEADLINE))
        assert adapter.get_activity_type() == ActivityType.DEADLINE

    def test_learning_type(self) -> None:
        adapter = EventAdapter(_make_event(event_type=EventType.LEARNING))
        assert adapter.get_activity_type() == ActivityType.LEARNING

    def test_unknown_falls_back_to_event(self) -> None:
        adapter = EventAdapter(_make_event(event_type="UNRECOGNIZED"))
        assert adapter.get_activity_type() == ActivityType.EVENT


class TestEventAdapterPriority:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("LOW", Priority.LOW),
            ("MEDIUM", Priority.MEDIUM),
            ("HIGH", Priority.HIGH),
            ("CRITICAL", Priority.CRITICAL),
            ("garbage", Priority.MEDIUM),
        ],
    )
    def test_priority_mapping(self, raw, expected) -> None:
        adapter = EventAdapter(_make_event(priority=raw))
        assert adapter.get_priority() == expected


class TestEventAdapterStatus:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("DRAFT", EntityStatus.DRAFT),
            ("SCHEDULED", EntityStatus.SCHEDULED),
            ("IN_PROGRESS", EntityStatus.ACTIVE),
            ("COMPLETED", EntityStatus.COMPLETED),
            ("CANCELLED", EntityStatus.CANCELLED),
            ("POSTPONED", EntityStatus.PAUSED),
            ("NO_SHOW", EntityStatus.CANCELLED),
            ("MYSTERY", EntityStatus.DRAFT),
        ],
    )
    def test_status_mapping(self, raw, expected) -> None:
        adapter = EventAdapter(_make_event(status=raw))
        assert adapter.get_status() == expected


class TestEventAdapterTimeWindows:
    def test_returns_single_window_event_kind(self) -> None:
        adapter = EventAdapter(_make_event())
        windows = adapter.get_calendar_windows()
        assert len(windows) == 1
        window = windows[0]
        assert window.kind == WindowKind.EVENT
        assert window.is_all_day is False


class TestEventAdapterMetadata:
    def test_metadata_contains_entity_and_event_type(self) -> None:
        adapter = EventAdapter(_make_event())
        meta = adapter.get_metadata()
        assert meta["entity_type"] == "Event"
        assert "event_type" in meta
        assert meta["location"] == "Room 101"
        assert meta["description"] == "Weekly sync"

    def test_optional_fields_omitted(self) -> None:
        adapter = EventAdapter(_make_event(location=None, description=None))
        meta = adapter.get_metadata()
        assert "location" not in meta
        assert "description" not in meta


class TestEventAdapterIcons:
    @pytest.mark.parametrize(
        ("event_type", "expected"),
        [
            (EventType.MEETING, "👥"),
            (EventType.DEADLINE, "⏰"),
            (EventType.LEARNING, "📚"),
            ("OTHER", "📅"),
        ],
    )
    def test_icon_mapping(self, event_type, expected) -> None:
        adapter = EventAdapter(_make_event(event_type=event_type))
        assert adapter.get_icon() == expected


class TestEventAdapterPermissions:
    def test_completed_cannot_edit(self) -> None:
        adapter = EventAdapter(_make_event(status="COMPLETED"))
        assert adapter.can_edit() is False
        assert adapter.can_delete() is True
        assert adapter.can_reschedule() is False

    def test_active_cannot_delete_or_reschedule(self) -> None:
        adapter = EventAdapter(_make_event(status="IN_PROGRESS"))
        assert adapter.can_delete() is False
        assert adapter.can_reschedule() is False

    def test_scheduled_can_do_everything(self) -> None:
        adapter = EventAdapter(_make_event(status="SCHEDULED"))
        assert adapter.can_edit() is True
        assert adapter.can_delete() is True
        assert adapter.can_reschedule() is True


class TestEventAdapterCompletion:
    def test_completed_returns_100(self) -> None:
        adapter = EventAdapter(_make_event(status="COMPLETED"))
        assert adapter.get_completion_percentage() == 100.0

    def test_active_returns_50(self) -> None:
        adapter = EventAdapter(_make_event(status="IN_PROGRESS"))
        assert adapter.get_completion_percentage() == 50.0

    def test_other_returns_0(self) -> None:
        adapter = EventAdapter(_make_event(status="DRAFT"))
        assert adapter.get_completion_percentage() == 0.0


class TestEventAdapterDuration:
    def test_estimated_from_start_end(self) -> None:
        adapter = EventAdapter(_make_event(start_time=time(9, 0), end_time=time(10, 30)))
        assert adapter.get_estimated_duration_minutes() == 90

    def test_actual_only_when_completed(self) -> None:
        scheduled = EventAdapter(_make_event(status="SCHEDULED"))
        completed = EventAdapter(_make_event(status="COMPLETED"))
        assert scheduled.get_actual_duration_minutes() is None
        assert completed.get_actual_duration_minutes() == 60


class TestEventAdapterDefaults:
    def test_related_uids_tags_visibility(self) -> None:
        adapter = EventAdapter(_make_event())
        assert adapter.get_related_uids() == ["task_a"]
        assert adapter.get_tags() == ["work"]
        assert adapter.get_visibility() == Visibility.PRIVATE
        assert adapter.get_recurrence_pattern() is None
        assert adapter.get_color() is None
        assert adapter.get_description() == "Weekly sync"


# ============================================================================
# TaskAdapter / HabitAdapter — pure delegation
# ============================================================================


class TestTaskAdapterDelegation:
    def test_delegates_attribute_access(self) -> None:
        task = SimpleNamespace(uid="task_1", title="Write tests", due_date=date(2026, 5, 20))
        adapter = TaskAdapter(task)  # type: ignore[arg-type]
        assert adapter.uid == "task_1"
        assert adapter.title == "Write tests"
        assert adapter.due_date == date(2026, 5, 20)


class TestHabitAdapterDelegation:
    def test_delegates_attribute_access(self) -> None:
        habit = SimpleNamespace(uid="habit_1", name="Daily run", current_streak=7)
        adapter = HabitAdapter(habit)  # type: ignore[arg-type]
        assert adapter.uid == "habit_1"
        assert adapter.name == "Daily run"
        assert adapter.current_streak == 7


# ============================================================================
# create_adapter / adapt_entities
# ============================================================================


class TestCreateAdapter:
    def test_unsupported_type_raises(self) -> None:
        with pytest.raises(ValueError, match="No adapter available"):
            create_adapter(SimpleNamespace(uid="unknown"))  # type: ignore[arg-type]

    def test_dispatches_event_to_event_adapter(self) -> None:
        """Patch the Event symbol the factory checks against to a stand-in class."""

        class FakeEvent:
            def __init__(self) -> None:
                ev = _make_event()
                for k, v in ev.__dict__.items():
                    setattr(self, k, v)

        sentinel = FakeEvent()
        with patch("adapters.calendar_adapters.Event", FakeEvent):
            adapter = create_adapter(sentinel)  # type: ignore[arg-type]
        assert isinstance(adapter, EventAdapter)

    def test_dispatches_task_passthrough(self) -> None:
        class FakeTask:
            def __init__(self) -> None:
                self.uid = "task_1"
                self.title = "t"

        task = FakeTask()
        with patch("adapters.calendar_adapters.Task", FakeTask):
            adapter = create_adapter(task)  # type: ignore[arg-type]
        # Tasks pass through (cast to CalendarTrackable), so we get the entity itself.
        assert adapter is task  # type: ignore[comparison-overlap]

    def test_dispatches_habit_passthrough(self) -> None:
        class FakeHabit:
            def __init__(self) -> None:
                self.uid = "habit_1"
                self.name = "h"

        habit = FakeHabit()
        with patch("adapters.calendar_adapters.Habit", FakeHabit):
            adapter = create_adapter(habit)  # type: ignore[arg-type]
        assert adapter is habit  # type: ignore[comparison-overlap]


class TestAdaptEntities:
    def test_skips_unsupported_silently(self) -> None:
        unsupported = [SimpleNamespace(uid="x"), SimpleNamespace(uid="y")]
        assert adapt_entities(unsupported) == []  # type: ignore[arg-type]

    def test_keeps_supported_drops_unsupported(self) -> None:
        class FakeEvent:
            def __init__(self) -> None:
                ev = _make_event()
                for k, v in ev.__dict__.items():
                    setattr(self, k, v)

        sentinel_event = FakeEvent()
        with patch("adapters.calendar_adapters.Event", FakeEvent):
            adapted = adapt_entities([sentinel_event, SimpleNamespace(uid="garbage")])  # type: ignore[arg-type]
        assert len(adapted) == 1
        assert isinstance(adapted[0], EventAdapter)
