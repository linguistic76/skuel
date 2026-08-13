"""
RelativeOffset — Engagement-Relative Timing
===========================================

Value type for the offset-from-engagement timing shape used by Activity Templates.
Templates can't commit to absolute dates at authoring time — they describe a
delay from the moment a student engages the owning PathStep, and the spawn
orchestrator resolves it to an absolute date when an instance is created.

Examples:
    TaskTemplate.due_offset = RelativeOffset(days=7)  # due 1 week after engaging
    EventTemplate.event_offset = RelativeOffset(days=14, hours=10)
    ChoiceTemplate.decision_deadline_offset = RelativeOffset(days=3)

Pinned design decisions (2026-05-09):
    - Timezone: arithmetic happens in the engagement anchor's tz. The engagement
      edge stores a UTC instant; the spawn orchestrator converts to user-local
      before passing as anchor.
    - Storage: resolved absolute dates are stored on the spawned instance at
      spawn (matches Task.due_date behavior). RelativeOffset is an authoring-side
      type — it does not appear on user-facing instances after spawn.

Out of scope (V1):
    - Negative offsets (rejected at construction).
    - Business-day arithmetic.
    - Sub-minute granularity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta


@dataclass(frozen=True)
class RelativeOffset:
    """Engagement-relative timing offset (days/hours/minutes).

    Components are non-negative. ``__post_init__`` rejects negatives so callers
    fail fast at authoring rather than producing surprising past-dated instances
    at spawn.
    """

    days: int = 0
    hours: int = 0
    minutes: int = 0

    def __post_init__(self) -> None:
        if self.days < 0 or self.hours < 0 or self.minutes < 0:
            raise ValueError(
                "RelativeOffset components must be non-negative "
                f"(got days={self.days}, hours={self.hours}, minutes={self.minutes})"
            )

    def as_timedelta(self) -> timedelta:
        """Return the offset as a :class:`datetime.timedelta`."""
        return timedelta(days=self.days, hours=self.hours, minutes=self.minutes)

    def is_zero(self) -> bool:
        """``True`` when the offset adds no duration (the spawn-on-engagement case)."""
        return self.days == 0 and self.hours == 0 and self.minutes == 0

    def resolve_to_datetime(self, anchor: datetime) -> datetime:
        """Resolve to an absolute datetime by adding the offset to ``anchor``.

        Preserves ``anchor.tzinfo`` (naive in, naive out). Callers handling
        cross-tz concerns should normalize the anchor first; the spawn
        orchestrator passes the engagement instant in user-local tz.
        """
        return anchor + self.as_timedelta()

    def resolve_to_date(self, anchor: date | datetime) -> date:
        """Resolve to an absolute date by adding the offset to ``anchor``.

        Hours and minutes overflow into days as expected — e.g.,
        ``RelativeOffset(days=2, hours=36).resolve_to_date(date(2026, 5, 9))``
        returns ``date(2026, 5, 12)``. Anchor may be a date (treated as midnight)
        or a datetime (time-of-day participates in overflow).
        """
        if isinstance(anchor, datetime):
            return (anchor + self.as_timedelta()).date()
        return (datetime.combine(anchor, datetime.min.time()) + self.as_timedelta()).date()
