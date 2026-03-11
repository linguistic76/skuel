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
