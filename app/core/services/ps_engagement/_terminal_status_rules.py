"""Per-domain rules for when an Activity instance counts as 'done' for engagement closure.

Distinct from :meth:`EntityStatus.is_terminal` because the engagement check has
a different shape than the generic terminal-status check:

- ``HABIT`` ``PAUSED`` is *not* engagement-terminal — a paused habit may resume
  mid-engagement; the engagement isn't done until the habit reaches a final
  conclusion.
- ``PRINCIPLE`` is exposure-only and never blocks. A spawned Principle is in
  ``ACTIVE`` from the moment of engagement and stays that way as the student
  embodies it; the engagement closes based on the action-y siblings, not the
  Principle's status.

Auto-completion triggers (``GATES_AUTO_COMPLETION``) is the narrower set of
domains whose own completion events can *fire* the check. Action-y domains
(Task / Goal / Event / Choice) publish a clean ``*Completed`` / ``*Achieved`` /
``*Made`` event when their entity status reaches terminal. ``HabitCompleted``
is per-occurrence, not per-entity-terminal, so we don't subscribe to it; a
Habit's entity-status transition to ``COMPLETED`` is checked when a sibling
instance's terminal event fires.

Consequence: engagements containing only Habits or Principles never
auto-complete — they require a student-declared ``complete_pathstep`` call.
This is intentional for V1; those domains run on student-declared rhythms by
nature.
"""

from __future__ import annotations

from core.models.enums.entity_enums import EntityStatus, EntityType

_TASK_TERMINAL = frozenset(
    {
        EntityStatus.COMPLETED,
        EntityStatus.CANCELLED,
        EntityStatus.FAILED,
        EntityStatus.ARCHIVED,
    }
)
_GOAL_TERMINAL = frozenset(
    {
        EntityStatus.COMPLETED,
        EntityStatus.CANCELLED,
        EntityStatus.FAILED,
        EntityStatus.ARCHIVED,
    }
)
_HABIT_TERMINAL = frozenset({EntityStatus.COMPLETED, EntityStatus.CANCELLED, EntityStatus.ARCHIVED})
_EVENT_TERMINAL = frozenset({EntityStatus.COMPLETED, EntityStatus.CANCELLED})
_CHOICE_TERMINAL = frozenset({EntityStatus.COMPLETED, EntityStatus.ARCHIVED})


ENGAGEMENT_TERMINAL_STATUSES: dict[EntityType, frozenset[EntityStatus]] = {
    EntityType.TASK: _TASK_TERMINAL,
    EntityType.GOAL: _GOAL_TERMINAL,
    EntityType.HABIT: _HABIT_TERMINAL,
    EntityType.EVENT: _EVENT_TERMINAL,
    EntityType.CHOICE: _CHOICE_TERMINAL,
    # PRINCIPLE handled specially in is_engagement_terminal — always passes.
}


GATES_AUTO_COMPLETION: frozenset[EntityType] = frozenset(
    {EntityType.TASK, EntityType.GOAL, EntityType.EVENT, EntityType.CHOICE}
)


def is_engagement_terminal(entity_type: EntityType, status: EntityStatus) -> bool:
    """Return whether this instance counts as 'done' for engagement closure.

    Principles are always considered done — they are exposure-only and the
    engagement should not wait on them. For the other five Activity Domains,
    the per-domain ``ENGAGEMENT_TERMINAL_STATUSES`` set governs.
    """
    if entity_type is EntityType.PRINCIPLE:
        return True
    return status in ENGAGEMENT_TERMINAL_STATUSES.get(entity_type, frozenset())


__all__ = [
    "ENGAGEMENT_TERMINAL_STATUSES",
    "GATES_AUTO_COMPLETION",
    "is_engagement_terminal",
]
