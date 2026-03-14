"""
Goal Enums - Goal Classification and Measurement
==================================================

Enums for goal types, timeframes, measurement strategies,
and habit essentiality to goal achievement.
"""

from enum import StrEnum


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
            HabitEssentiality.ESSENTIAL: "bg-red-100 text-red-800 border-red-200",
            HabitEssentiality.CRITICAL: "bg-yellow-100 text-yellow-800 border-yellow-200",
            HabitEssentiality.SUPPORTING: "bg-blue-100 text-blue-800 border-blue-200",
            HabitEssentiality.OPTIONAL: "bg-gray-100 text-gray-600 border-gray-200",
        }.get(self, "bg-gray-100 text-gray-600 border-gray-200")

    def get_styled(self) -> tuple[str, str, str]:
        """Get (emoji, border_class, bg_class) for essentiality display."""
        return {
            HabitEssentiality.ESSENTIAL: ("\U0001f534", "border-red-500", "bg-red-50"),
            HabitEssentiality.CRITICAL: ("\U0001f7e0", "border-orange-500", "bg-orange-50"),
            HabitEssentiality.SUPPORTING: ("\U0001f7e1", "border-yellow-500", "bg-yellow-50"),
            HabitEssentiality.OPTIONAL: ("\U0001f7e2", "border-green-500", "bg-green-50"),
        }.get(self, ("\u26aa", "border-border", "bg-muted"))
