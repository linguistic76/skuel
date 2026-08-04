"""
Scheduling Enums - Time, Recurrence, and Energy Management
==========================================================

Enums for scheduling preferences, recurrence patterns, and energy levels.
"""

from datetime import time
from enum import StrEnum


class RecurrencePattern(StrEnum):
    """
    Universal recurrence patterns for any repeating activity.

    Used by habits, recurring tasks, events, and learning sessions.
    """

    NONE = "none"  # One-time only
    DAILY = "daily"  # Every day
    WEEKDAYS = "weekdays"  # Monday-Friday
    WEEKENDS = "weekends"  # Saturday-Sunday
    WEEKLY = "weekly"  # Once a week
    BIWEEKLY = "biweekly"  # Every two weeks
    MONTHLY = "monthly"  # Once a month
    QUARTERLY = "quarterly"  # Every three months
    YEARLY = "yearly"  # Once a year
    CUSTOM = "custom"  # Custom RRULE pattern

    def to_rrule_base(self) -> str:
        """Convert to basic RRULE string (without interval)"""
        rrules = {
            RecurrencePattern.DAILY: "FREQ=DAILY",
            RecurrencePattern.WEEKDAYS: "FREQ=DAILY;BYDAY=MO,TU,WE,TH,FR",
            RecurrencePattern.WEEKENDS: "FREQ=DAILY;BYDAY=SA,SU",
            RecurrencePattern.WEEKLY: "FREQ=WEEKLY",
            RecurrencePattern.BIWEEKLY: "FREQ=WEEKLY;INTERVAL=2",
            RecurrencePattern.MONTHLY: "FREQ=MONTHLY",
            RecurrencePattern.QUARTERLY: "FREQ=MONTHLY;INTERVAL=3",
            RecurrencePattern.YEARLY: "FREQ=YEARLY",
        }
        return rrules.get(self, "")

    def get_interval_days(self) -> int:
        """Get approximate interval in days for simple calculations"""
        intervals = {
            RecurrencePattern.DAILY: 1,
            RecurrencePattern.WEEKDAYS: 1,
            RecurrencePattern.WEEKENDS: 1,
            RecurrencePattern.WEEKLY: 7,
            RecurrencePattern.BIWEEKLY: 14,
            RecurrencePattern.MONTHLY: 30,
            RecurrencePattern.QUARTERLY: 90,
            RecurrencePattern.YEARLY: 365,
        }
        return intervals.get(self, 1)


class TimeOfDay(StrEnum):
    """
    Preferred time of day for activities.

    THE one vocabulary of habitual time (habit-rhythm arc M1/M3): a habit is
    anchored to a fuzzy *slot*, never to a clock time. Every consumer that needs
    a concrete hour derives it here — ``get_default_hour`` /
    ``get_representative_time`` going out, ``from_hour`` coming in — so the
    hour↔slot mapping exists exactly once.

    Also used for the user's own scheduling preference
    (``User.preferences.preferred_time_of_day``).
    """

    EARLY_MORNING = "early_morning"  # 5:00 - 7:00
    MORNING = "morning"  # 7:00 - 12:00
    AFTERNOON = "afternoon"  # 12:00 - 17:00
    EVENING = "evening"  # 17:00 - 21:00
    NIGHT = "night"  # 21:00 - 24:00
    LATE_NIGHT = "late_night"  # 0:00 - 5:00
    ANYTIME = "anytime"  # No preference

    def get_hour_range(self) -> tuple[int, int]:
        """Get the hour range (start, end) for this time period"""
        ranges = {
            TimeOfDay.EARLY_MORNING: (5, 7),
            TimeOfDay.MORNING: (7, 12),
            TimeOfDay.AFTERNOON: (12, 17),
            TimeOfDay.EVENING: (17, 21),
            TimeOfDay.NIGHT: (21, 24),
            TimeOfDay.LATE_NIGHT: (0, 5),
            TimeOfDay.ANYTIME: (0, 24),
        }
        return ranges.get(self, (9, 17))

    def get_default_hour(self) -> int:
        """Get a default hour for scheduling in this time period"""
        defaults = {
            TimeOfDay.EARLY_MORNING: 6,
            TimeOfDay.MORNING: 9,
            TimeOfDay.AFTERNOON: 14,
            TimeOfDay.EVENING: 19,
            TimeOfDay.NIGHT: 22,
            TimeOfDay.LATE_NIGHT: 2,
            TimeOfDay.ANYTIME: 9,
        }
        return defaults.get(self, 9)

    def get_representative_time(self) -> time:
        """The slot's representative clock time — its default hour, on the hour.

        The single answer to "where in the day does this slot sit?". Callers that
        must place a slot on a timeline (day spine, habit→event scheduling,
        calendar chips) derive from this rather than parsing the slot as a clock
        value; ANYTIME resolves to a stable 09:00 rather than to nothing.
        """
        return time(self.get_default_hour(), 0)

    @classmethod
    def from_hour(cls, hour: int) -> "TimeOfDay":
        """Classify a clock hour into the slot whose range contains it.

        Inverse of :meth:`get_hour_range` — the one place an observed hour
        (a completion timestamp, a ``@when()`` datetime) becomes slot
        vocabulary. Hours outside 0-23 raise, because a caller holding one has a
        bug rather than a preference.
        """
        if not 0 <= hour <= 23:
            raise ValueError(f"hour must be 0-23, got {hour!r}")
        for member in cls:
            if member is cls.ANYTIME:
                continue  # spans the whole day; only reachable as an explicit choice
            start, end = member.get_hour_range()
            if start <= hour < end:
                return member
        raise ValueError(f"no TimeOfDay slot covers hour {hour!r}")


class EnergyLevel(StrEnum):
    """
    Energy level required or available for activities.

    Used for matching tasks to energy states and optimal scheduling.
    """

    LOW = "low"  # Can do when tired
    MEDIUM = "medium"  # Normal energy required
    HIGH = "high"  # Requires peak energy/focus
    VARIABLE = "variable"  # Depends on context

    def matches(self, available_energy: "EnergyLevel") -> bool:
        """Check if required energy matches available energy"""
        if self == EnergyLevel.VARIABLE or available_energy == EnergyLevel.VARIABLE:
            return True

        energy_values = {EnergyLevel.LOW: 1, EnergyLevel.MEDIUM: 2, EnergyLevel.HIGH: 3}
        return energy_values.get(available_energy, 0) >= energy_values.get(self, 0)
