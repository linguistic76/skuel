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


class AttendanceStatus(StrEnum):
    """
    Consent state on the ``(User)-[:ATTENDS]->(Event)`` edge (ADR-086).

    The invite→accept state machine: an organizer may only ever create
    ``INVITED``; the target user is the only actor who transitions the status
    (``invited → accepted / declined``); a self-add writes ``ACCEPTED`` because
    it IS the attendee's consent. Lowercase values per package convention.
    """

    INVITED = "invited"
    ACCEPTED = "accepted"
    DECLINED = "declined"
