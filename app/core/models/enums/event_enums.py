"""
Event Enums - Event Domain Classification
=========================================

Canonical vocabulary for the Event activity domain.
"""

from enum import StrEnum


class EventType(StrEnum):
    """
    Kind of calendar event — the `event_type` property on :Event nodes.

    Canonical member values are lowercase (house convention for every enum in
    this package); persisted rows were migrated to lowercase in 2026-08
    (scripts/migrations/lowercase_event_type_2026_08.cypher). Recurrence is
    NOT a type — it is modeled by `recurrence_pattern` (RecurrencePattern).
    """

    MEETING = "meeting"
    CONFERENCE = "conference"
    WORKSHOP = "workshop"
    DEADLINE = "deadline"
    REMINDER = "reminder"
    PERSONAL = "personal"
    WORK = "work"
    SOCIAL = "social"
    LEARNING = "learning"
    HEALTH = "health"
