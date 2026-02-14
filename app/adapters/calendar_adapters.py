"""
Calendar Adapters
=================

Adapter classes to ensure entities conform to the CalendarTrackable protocol.
This provides a uniform interface for different entity types in the calendar system.
"""

from datetime import date, datetime
from typing import Any, cast

from core.models.enums import (
    KuStatus,
    ActivityType,
    Priority,
    RecurrencePattern,
    Visibility,
)

# Import from three-tier models
from core.models.ku.ku import Ku as EventPure
from core.models.event.event_request import EventType
from core.models.ku.ku import Ku as HabitPure
from core.models.ku.ku import Ku as TaskPure

# Protocols
from core.services.protocols.calendar_protocol import CalendarTrackable, TimeWindow, WindowKind


class EventAdapter:
    """Adapter for EventPure to ensure CalendarTrackable compliance"""

    def __init__(self, event: EventPure) -> None:
        self._event = event

    @property
    def uid(self) -> str:
        return self._event.uid

    @property
    def title(self) -> str:
        return self._event.title

    def get_activity_type(self) -> ActivityType:
        """Map EventType to ActivityType"""
        if self._event.event_type == EventType.MEETING:
            return ActivityType.MEETING
        elif self._event.event_type == EventType.DEADLINE:
            return ActivityType.DEADLINE
        elif self._event.event_type == EventType.LEARNING:
            return ActivityType.LEARNING
        else:
            return ActivityType.EVENT

    def get_priority(self) -> Priority:
        """Convert event priority to general Priority"""
        # EventPure uses uppercase priority strings
        priority_map = {
            "LOW": Priority.LOW,
            "MEDIUM": Priority.MEDIUM,
            "HIGH": Priority.HIGH,
            "CRITICAL": Priority.CRITICAL,
        }
        # Get the priority string value if it's an enum/literal
        priority_str = str(self._event.priority).upper()
        return priority_map.get(priority_str, Priority.MEDIUM)

    def get_status(self) -> KuStatus:
        """Convert event status to KuStatus"""
        # Map EventStatus literals to KuStatus
        status_map = {
            "DRAFT": KuStatus.DRAFT,
            "SCHEDULED": KuStatus.SCHEDULED,
            "IN_PROGRESS": KuStatus.ACTIVE,
            "COMPLETED": KuStatus.COMPLETED,
            "CANCELLED": KuStatus.CANCELLED,
            "POSTPONED": KuStatus.PAUSED,
            "NO_SHOW": KuStatus.CANCELLED,
        }
        status_str = str(self._event.status).upper()
        return status_map.get(status_str, KuStatus.DRAFT)

    def get_calendar_windows(self) -> list[TimeWindow]:
        """
        Get time windows for calendar display.

        Note: Event model does not have an all_day field.
        All events use start_time/end_time for scheduling.
        """
        windows = []
        # GRAPH-NATIVE: Event model doesn't have all_day field, always use EVENT kind
        windows.append(
            TimeWindow(
                start=self._event.start_time,
                end=self._event.end_time,
                kind=WindowKind.EVENT,
                is_all_day=False,
            )
        )
        return windows

    def get_metadata(self) -> dict[str, Any]:
        """Get additional metadata"""
        metadata = {
            "entity_type": "Event",
            "event_type": f"EventType.{getattr(self._event.event_type, 'name', self._event.event_type)}",
        }
        if getattr(self._event, "location", None):
            metadata["location"] = self._event.location
        if getattr(self._event, "description", None):
            metadata["description"] = self._event.description
        return metadata

    def get_icon(self) -> str:
        """Get icon based on event type"""
        if self._event.event_type == EventType.MEETING:
            return "👥"
        elif self._event.event_type == EventType.DEADLINE:
            return "⏰"
        elif self._event.event_type == EventType.LEARNING:
            return "📚"
        else:
            return "📅"

    def can_edit(self) -> bool:
        """Check if event can be edited"""
        return self.get_status() not in {KuStatus.CANCELLED, KuStatus.COMPLETED}

    def can_delete(self) -> bool:
        """Check if event can be deleted"""
        return self.get_status() != KuStatus.ACTIVE

    def can_reschedule(self) -> bool:
        """Check if event can be rescheduled"""
        return self.get_status() not in {
            KuStatus.COMPLETED,
            KuStatus.CANCELLED,
            KuStatus.ACTIVE,
        }

    def get_completion_percentage(self) -> float:
        """Get completion percentage"""
        status = self.get_status()
        if status == KuStatus.COMPLETED:
            return 100.0
        elif status == KuStatus.ACTIVE:
            # Could calculate based on time elapsed
            return 50.0
        else:
            return 0.0

    # Additional CalendarTrackable methods with defaults
    def get_related_uids(self) -> list[str]:
        return getattr(self._event, "related_uids", [])

    def get_tags(self) -> list[str]:
        return getattr(self._event, "tags", [])

    def get_visibility(self) -> Visibility:
        return getattr(self._event, "visibility", Visibility.PRIVATE)

    def get_recurrence_pattern(self) -> RecurrencePattern | None:
        return getattr(self._event, "recurrence_pattern", None)

    def get_color(self) -> str | None:
        return getattr(self._event, "color", None)

    def get_estimated_duration_minutes(self) -> int | None:
        start_time = getattr(self._event, "start_time", None)
        end_time = getattr(self._event, "end_time", None)
        if start_time and end_time:
            # time objects don't support subtraction; convert to datetime
            start = datetime.combine(date.today(), start_time)
            end = datetime.combine(date.today(), end_time)
            delta = end - start
            return int(delta.total_seconds() / 60)
        return None

    def get_actual_duration_minutes(self) -> int | None:
        if self.get_status() == KuStatus.COMPLETED:
            return self.get_estimated_duration_minutes()
        return None

    def get_description(self) -> str | None:
        return getattr(self._event, "description", None)


class TaskAdapter:
    """Adapter for TaskPure - mostly just passes through since TaskPure implements CalendarTrackable"""

    def __init__(self, task: TaskPure) -> None:
        self._task = task

    def __getattr__(self, name: str) -> Any:
        """Delegate all CalendarTrackable methods to the task"""
        return getattr(self._task, name)


class HabitAdapter:
    """Adapter for HabitPure - mostly just passes through since HabitPure implements CalendarTrackable"""

    def __init__(self, habit: HabitPure) -> None:
        self._habit = habit

    def __getattr__(self, name: str) -> Any:
        """Delegate all CalendarTrackable methods to the habit"""
        return getattr(self._habit, name)


def create_adapter(entity: EventPure | TaskPure | HabitPure) -> CalendarTrackable:
    """
    Factory function to create appropriate adapter for an entity.

    Args:
        entity: The entity to adapt

    Returns:
        An adapter that implements CalendarTrackable

    Raises:
        ValueError: If entity type is not supported
    """
    if isinstance(entity, EventPure):
        return cast("CalendarTrackable", EventAdapter(entity))
    elif isinstance(entity, TaskPure):
        # TaskPure already implements CalendarTrackable, return as-is
        return cast("CalendarTrackable", entity)
    elif isinstance(entity, HabitPure):
        # HabitPure already implements CalendarTrackable, return as-is
        return cast("CalendarTrackable", entity)
    else:
        raise ValueError(f"No adapter available for entity type: {type(entity).__name__}")


def adapt_entities(entities: list[Any]) -> list[CalendarTrackable]:
    """
    Adapt multiple entities to CalendarTrackable protocol.

    Args:
        entities: List of entities to adapt

    Returns:
        List of adapted entities implementing CalendarTrackable
    """
    adapted = []
    for entity in entities:
        try:
            adapted.append(create_adapter(entity))
        except ValueError:
            # Skip entities that can't be adapted
            continue
    return adapted
