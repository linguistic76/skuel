"""
Goal Enums - Goal Classification and Measurement
==================================================

Enums for goal types, timeframes, measurement strategies,
and habit essentiality to goal achievement.
"""

from enum import StrEnum

from core.constants import HabitEssentialityWeight


class GoalType(StrEnum):
    """
    Classification of goal by nature.

    Determines measurement strategy and progress tracking approach.
    """

    OUTCOME = "outcome"
    PROCESS = "process"
    LEARNING = "learning"
    PROJECT = "project"
    MILESTONE = "milestone"
    MASTERY = "mastery"


class GoalTimeframe(StrEnum):
    """
    Expected duration/timeframe for goal achievement.

    Used for scheduling, priority calculation, and progress pacing.
    """

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    MULTI_YEAR = "multi_year"


class MeasurementType(StrEnum):
    """
    How goal progress is measured.

    Determines the progress tracking UI and calculation method.
    """

    BINARY = "binary"
    PERCENTAGE = "percentage"
    NUMERIC = "numeric"
    MILESTONE = "milestone"
    HABIT_BASED = "habit_based"
    KNOWLEDGE_BASED = "knowledge_based"
    TASK_BASED = "task_based"
    MIXED = "mixed"


class HabitEssentiality(StrEnum):
    """
    Classification of habit importance to goal achievement.

    Based on James Clear's Atomic Habits philosophy:
    "You do not rise to the level of your goals.
     You fall to the level of your systems."
    """

    ESSENTIAL = "essential"
    CRITICAL = "critical"
    SUPPORTING = "supporting"
    OPTIONAL = "optional"

    def get_badge_class(self) -> str:
        """Get Tailwind badge classes for essentiality display."""
        return {
            HabitEssentiality.ESSENTIAL: "bg-red-100 dark:bg-red-400/10 text-red-800 dark:text-red-300 border-red-200 dark:border-red-400/30",
            HabitEssentiality.CRITICAL: "bg-yellow-100 dark:bg-yellow-400/10 text-yellow-800 dark:text-yellow-300 border-yellow-200 dark:border-yellow-400/30",
            HabitEssentiality.SUPPORTING: "bg-blue-100 dark:bg-blue-400/10 text-blue-800 dark:text-blue-300 border-blue-200 dark:border-blue-400/30",
            HabitEssentiality.OPTIONAL: "bg-muted text-foreground/70 border-border",
        }.get(self, "bg-muted text-foreground/70 border-border")

    def get_styled(self) -> tuple[str, str, str]:
        """Get (emoji, border_class, bg_class) for essentiality display."""
        return {
            HabitEssentiality.ESSENTIAL: (
                "\U0001f534",
                "border-red-500",
                "bg-red-50 dark:bg-red-400/10",
            ),
            HabitEssentiality.CRITICAL: (
                "\U0001f7e0",
                "border-orange-500",
                "bg-orange-50 dark:bg-orange-400/10",
            ),
            HabitEssentiality.SUPPORTING: (
                "\U0001f7e1",
                "border-yellow-500",
                "bg-yellow-50 dark:bg-yellow-400/10",
            ),
            HabitEssentiality.OPTIONAL: (
                "\U0001f7e2",
                "border-green-500",
                "bg-green-50 dark:bg-green-400/10",
            ),
        }.get(self, ("\u26aa", "border-border", "bg-muted"))

    def get_weight(self) -> float:
        """How much this tier weighs in a goal's essentiality-weighted habit figure.

        The values are :class:`core.constants.HabitEssentialityWeight`.
        """
        return {
            HabitEssentiality.ESSENTIAL: HabitEssentialityWeight.ESSENTIAL,
            HabitEssentiality.CRITICAL: HabitEssentialityWeight.CRITICAL,
            HabitEssentiality.SUPPORTING: HabitEssentialityWeight.SUPPORTING,
            HabitEssentiality.OPTIONAL: HabitEssentialityWeight.OPTIONAL,
        }[self]

    @classmethod
    def from_stored(cls, value: str | None) -> HabitEssentiality:
        """The tier a ``SUPPORTS_GOAL`` edge's ``essentiality`` property names.

        Every link door writes ``supporting`` unless told otherwise, so an absent
        or unknown value reads as :attr:`SUPPORTING` — the tier it would have been
        written with.
        """
        try:
            return cls(value) if value is not None else cls.SUPPORTING
        except ValueError:
            return cls.SUPPORTING
