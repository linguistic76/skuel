"""
Habit Enums - Habit Classification and Completion Tracking
===========================================================

Enums for habit polarity, category, difficulty, and completion status.
"""

from enum import StrEnum


class HabitPolarity(StrEnum):
    """
    Direction of habit change.

    BUILD: Creating a new positive habit
    BREAK: Eliminating a negative habit
    NEUTRAL: Tracking without direction
    """

    BUILD = "build"
    BREAK = "break"
    NEUTRAL = "neutral"


class HabitCategory(StrEnum):
    """Category classification for habits."""

    HEALTH = "health"
    FITNESS = "fitness"
    MINDFULNESS = "mindfulness"
    LEARNING = "learning"
    PRODUCTIVITY = "productivity"
    CREATIVE = "creative"
    SOCIAL = "social"
    FINANCIAL = "financial"
    OTHER = "other"


class HabitDifficulty(StrEnum):
    """Difficulty level of maintaining a habit."""

    TRIVIAL = "trivial"
    EASY = "easy"
    MODERATE = "moderate"
    CHALLENGING = "challenging"
    HARD = "hard"


class CompletionStatus(StrEnum):
    """
    Status for tracking completion of activities, especially habits.

    More nuanced than just complete/incomplete to track quality.
    """

    DONE = "done"
    PARTIAL = "partial"
    SKIPPED = "skipped"
    MISSED = "missed"
    PAUSED = "paused"

    def counts_as_success(self) -> bool:
        """Check if this counts toward success metrics."""
        return self in {CompletionStatus.DONE, CompletionStatus.PARTIAL}

    def get_emoji(self) -> str:
        """Get emoji representation."""
        emojis = {
            CompletionStatus.DONE: "✅",
            CompletionStatus.PARTIAL: "⚡",
            CompletionStatus.SKIPPED: "⏭️",
            CompletionStatus.MISSED: "❌",
            CompletionStatus.PAUSED: "⏸️",
        }
        return emojis.get(self, "❓")
