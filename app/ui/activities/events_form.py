"""
Event create / edit form
========================

FormGenerator-rendered Event forms used by ``adapters/inbound/events_ui.py``
(``GET /events/create`` and ``GET /events/edit``).

Wires the searchable cross-domain :class:`~ui.patterns.entity_picker.EntityPicker`
for the two single-UID fields on EventCreateRequest / EventUpdateRequest:

- ``reinforces_habit_uid`` — habit this event reinforces
- ``milestone_celebration_for_goal`` — goal milestone being celebrated

List-typed cross-domain fields (``practices_knowledge_uids``, ``executes_tasks``,
``attendee_emails``, ``tags``) are intentionally omitted; assign those via the
detail-page relationship picker.
"""

from __future__ import annotations

from typing import Any

from core.models.event.event import Event
from core.models.event.event_request import EventCreateRequest, EventUpdateRequest
from ui.patterns.activity_form_helper import render_activity_form
from ui.patterns.entity_picker import EntityPicker

_CREATE_SECTIONS: dict[str, dict[str, Any]] = {
    "Basics": {"icon": "info", "accent": "blue", "fields": ["title", "description"]},
    "Scheduling": {
        "icon": "calendar",
        "accent": "amber",
        "fields": [
            "event_date",
            "start_time",
            "end_time",
            "recurrence_pattern",
            "recurrence_end_date",
        ],
    },
    "Type & Visibility": {
        "icon": "tag",
        "accent": "violet",
        "fields": ["event_type", "visibility", "priority"],
    },
    "Location": {
        "icon": "map-pin",
        "accent": "emerald",
        "fields": ["location", "is_online", "meeting_url"],
    },
    "Attendees": {"icon": "users", "accent": "cyan", "fields": ["max_attendees"]},
    "Reminder": {"icon": "bell", "accent": "rose", "fields": ["reminder_minutes"]},
    "Connections": {
        "icon": "link-2",
        "accent": "violet",
        "fields": ["reinforces_habit_uid", "milestone_celebration_for_goal"],
    },
    "Tracking": {
        "icon": "check-circle",
        "accent": "emerald",
        "fields": ["habit_completion_quality", "knowledge_retention_check"],
    },
}

_EDIT_SECTIONS: dict[str, dict[str, Any]] = {
    "Basics": {"icon": "info", "accent": "blue", "fields": ["title", "description"]},
    "Scheduling": {
        "icon": "calendar",
        "accent": "amber",
        "fields": ["event_date", "start_time", "end_time"],
    },
    "Type & Visibility": {
        "icon": "tag",
        "accent": "violet",
        "fields": ["event_type", "visibility", "status", "priority"],
    },
    "Location": {
        "icon": "map-pin",
        "accent": "emerald",
        "fields": ["location", "is_online", "meeting_url"],
    },
    "Reminder": {"icon": "bell", "accent": "rose", "fields": ["reminder_minutes"]},
    "Connections": {
        "icon": "link-2",
        "accent": "violet",
        "fields": ["reinforces_habit_uid", "milestone_celebration_for_goal"],
    },
    "Tracking": {
        "icon": "check-circle",
        "accent": "emerald",
        "fields": ["habit_completion_quality", "knowledge_retention_check"],
    },
}

_FIELD_LABELS: dict[str, str] = {
    "title": "Title",
    "description": "Description",
    "event_date": "Date",
    "start_time": "Start time",
    "end_time": "End time",
    "recurrence_pattern": "Recurrence",
    "recurrence_end_date": "Recurrence end date",
    "event_type": "Event type",
    "visibility": "Visibility",
    "status": "Status",
    "priority": "Priority",
    "location": "Location",
    "is_online": "Online event",
    "meeting_url": "Meeting URL",
    "max_attendees": "Max attendees",
    "reminder_minutes": "Reminder (minutes before)",
    "reinforces_habit_uid": "Habit reinforced",
    "milestone_celebration_for_goal": "Milestone for goal",
    "habit_completion_quality": "Habit completion quality (1-5)",
    "knowledge_retention_check": "Knowledge retention check",
}

_FIELD_HELP: dict[str, str] = {
    "meeting_url": "Required when 'Online event' is checked.",
    "reminder_minutes": "How long before the event to remind you (0–10080 / one week).",
    "reinforces_habit_uid": "Link this event to a habit it reinforces.",
    "milestone_celebration_for_goal": "Link this event to a goal milestone it celebrates.",
    "habit_completion_quality": "If this completes a habit, rate the quality 1-5.",
    "knowledge_retention_check": "Mark if this event tests retention of knowledge.",
}


def EventCreateForm() -> Any:
    """Render the Event create form with EntityPicker for cross-domain UIDs."""
    return render_activity_form(
        domain_slug="events",
        entity_name="Event",
        request_model=EventCreateRequest,
        operation="create",
        sections=_CREATE_SECTIONS,
        labels=_FIELD_LABELS,
        help_texts=_FIELD_HELP,
        custom_widgets={
            "reinforces_habit_uid": EntityPicker("reinforces_habit_uid", target_type="habit"),
            "milestone_celebration_for_goal": EntityPicker(
                "milestone_celebration_for_goal", target_type="goal"
            ),
        },
    )


def EventEditForm(
    event: Event,
    *,
    habit_display: str | None = None,
    goal_display: str | None = None,
) -> Any:
    """Render the Event edit form prefilled from an existing event.

    Args:
        event: Event being edited (UID context + field prefill).
        habit_display: Human-readable title for ``event.reinforces_habit_uid``
            resolved by the route layer (powers the picker's visible input).
        goal_display: Same as ``habit_display`` but for
            ``event.milestone_celebration_for_goal``.
    """
    return render_activity_form(
        domain_slug="events",
        entity_name="Event",
        request_model=EventUpdateRequest,
        operation="edit",
        sections=_EDIT_SECTIONS,
        labels=_FIELD_LABELS,
        help_texts=_FIELD_HELP,
        entity=event,
        custom_widgets={
            "reinforces_habit_uid": EntityPicker(
                "reinforces_habit_uid",
                target_type="habit",
                value=event.reinforces_habit_uid,
                display=habit_display,
            ),
            "milestone_celebration_for_goal": EntityPicker(
                "milestone_celebration_for_goal",
                target_type="goal",
                value=event.milestone_celebration_for_goal,
                display=goal_display,
            ),
        },
    )


__all__ = ["EventCreateForm", "EventEditForm"]
