"""
Habit Completion Domain Model (Tier 3 - Core)
==============================================

Immutable domain model with business logic for habit completions.
This is the core business entity that encapsulates all completion-related rules.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from .completion_dto import HabitCompletionDTO


@dataclass(frozen=True)
class HabitCompletion:
    """
    Immutable domain model for habit completions.

    This model contains all business logic for habit completion operations
    and maintains referential integrity through immutability.
    """

    # Identity (required fields first)
    uid: str
    habit_uid: str
    completed_at: datetime
    created_at: datetime
    updated_at: datetime

    # Completion Details (optional fields last)
    notes: str | None = None
    quality: int | None = None  # 1-5 rating
    duration_actual: int | None = None  # minutes

    def __post_init__(self) -> None:
        """Validate the domain model after creation."""
        if self.quality is not None and not (1 <= self.quality <= 5):
            raise ValueError("Quality must be between 1 and 5")

        if self.duration_actual is not None and self.duration_actual < 0:
            raise ValueError("Duration cannot be negative")

    # ========================================================================
    # FACTORY METHODS
    # ========================================================================

    @classmethod
    def from_dto(cls, dto: HabitCompletionDTO) -> "HabitCompletion":
        """Create domain model from DTO."""
        return cls(
            uid=dto.uid,
            habit_uid=dto.habit_uid,
            completed_at=dto.completed_at,
            notes=dto.notes,
            quality=dto.quality,
            duration_actual=dto.duration_actual,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
        )

    def to_dto(self) -> HabitCompletionDTO:
        """Convert to DTO for transfer operations."""
        return HabitCompletionDTO(
            uid=self.uid,
            habit_uid=self.habit_uid,
            completed_at=self.completed_at,
            notes=self.notes,
            quality=self.quality,
            duration_actual=self.duration_actual,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    # ========================================================================
    # BUSINESS LOGIC METHODS
    # ========================================================================

    def is_high_quality(self) -> bool:
        """Check if this completion represents a high-quality effort."""
        return self.quality is not None and self.quality >= 4

    def is_excellent_quality(self) -> bool:
        """Check if this completion represents excellent quality."""
        return self.quality is not None and self.quality == 5

    def has_meaningful_notes(self) -> bool:
        """Check if this completion has substantive notes."""
        if not self.notes:
            return False

        # Consider notes meaningful if they're more than just a few words
        cleaned_notes = self.notes.strip()
        return len(cleaned_notes) > 10 and len(cleaned_notes.split()) > 2

    def was_extended_session(self, target_duration: int | None = None) -> bool:
        """
        Check if actual duration exceeded target duration.

        Args:
            target_duration: Expected duration in minutes

        Returns:
            True if session was extended beyond target
        """
        if not self.duration_actual or not target_duration:
            return False
        return self.duration_actual > target_duration

    def was_shortened_session(self, target_duration: int | None = None) -> bool:
        """
        Check if actual duration was significantly less than target.

        Args:
            target_duration: Expected duration in minutes

        Returns:
            True if session was shortened (< 75% of target)
        """
        if not self.duration_actual or not target_duration:
            return False
        return self.duration_actual < (target_duration * 0.75)

    def completion_score(self, target_duration: int | None = None) -> float:
        """
        Calculate an overall completion score (0.0-1.0).

        Factors in:
        - Quality rating (if provided)
        - Duration relative to target
        - Presence of meaningful notes

        Args:
            target_duration: Expected duration in minutes

        Returns:
            Score from 0.0 to 1.0
        """
        score = 0.5  # Base score for completing at all

        # Quality component (0.3 weight)
        if self.quality:
            quality_score = (self.quality - 1) / 4  # Normalize 1-5 to 0-1
            score += quality_score * 0.3

        # Duration component (0.15 weight)
        if self.duration_actual and target_duration:
            duration_ratio = min(self.duration_actual / target_duration, 1.5)  # Cap at 150%
            duration_score = min(duration_ratio, 1.0)  # No penalty for going over
            score += duration_score * 0.15

        # Notes component (0.05 weight)
        if self.has_meaningful_notes():
            score += 0.05

        return min(score, 1.0)

    def was_completed_today(self) -> bool:
        """Check if this completion happened today."""
        return self.completed_at.date() == date.today()

    def was_completed_on(self, target_date: date) -> bool:
        """Check if this completion happened on a specific date."""
        return self.completed_at.date() == target_date

    def days_since_completion(self) -> int:
        """Calculate days since this completion."""
        return (datetime.now().date() - self.completed_at.date()).days

    def completion_time_of_day(self) -> str:
        """Get time of day category for this completion."""
        hour = self.completed_at.hour

        if 5 <= hour < 12:
            return "morning"
        elif 12 <= hour < 17:
            return "afternoon"
        elif 17 <= hour < 21:
            return "evening"
        else:
            return "night"

    def is_streak_eligible(self, previous_completion: Optional["HabitCompletion"] = None) -> bool:
        """
        Check if this completion is eligible for streak counting.

        Rules:
        - Must have some quality (>= 2) if quality is provided
        - Cannot be too far in the past (within 36 hours of target)
        - Cannot be duplicate day if previous completion exists

        Args:
            previous_completion: Previous completion to check against

        Returns:
            True if eligible for streak counting
        """
        # Quality gate
        if self.quality is not None and self.quality < 2:
            return False

        # Recency gate (within 36 hours of today)
        if self.days_since_completion() > 1:
            return False

        # No duplicate days
        return not (
            previous_completion and self.was_completed_on(previous_completion.completed_at.date())
        )

    def contributes_to_consistency(self, habit_frequency: str = "daily") -> bool:
        """
        Check if this completion contributes to habit consistency.

        Args:
            habit_frequency: Frequency pattern of the habit

        Returns:
            True if completion contributes to consistency
        """
        # For daily habits, any completion counts
        if habit_frequency.lower() == "daily":
            return True

        # For weekly habits, check if it's within the current week
        if habit_frequency.lower() == "weekly":
            today = date.today()
            week_start = today - timedelta(days=today.weekday())
            completion_date = self.completed_at.date()
            return week_start <= completion_date <= today

        # For other frequencies, default to true
        return True

    def satisfaction_level(self) -> str:
        """
        Get user satisfaction level based on quality and notes.

        Returns:
            String description of satisfaction level
        """
        if not self.quality:
            return "neutral"

        if self.quality >= 5:
            return "excellent"
        elif self.quality >= 4:
            return "good"
        elif self.quality >= 3:
            return "satisfactory"
        elif self.quality >= 2:
            return "below_average"
        else:
            return "poor"

    # ========================================================================
    # COMPARISON AND ANALYSIS
    # ========================================================================

    def is_better_than(self, other: "HabitCompletion", target_duration: int | None = None) -> bool:
        """
        Compare this completion to another completion.

        Args:
            other: Another completion to compare against
            target_duration: Target duration for scoring

        Returns:
            True if this completion is better than the other
        """
        return self.completion_score(target_duration) > other.completion_score(target_duration)

    def __str__(self) -> str:
        """Human-readable string representation."""
        quality_str = f" (quality: {self.quality})" if self.quality else ""
        duration_str = f" ({self.duration_actual}min)" if self.duration_actual else ""
        return f"Completion {self.uid} on {self.completed_at.date()}{quality_str}{duration_str}"

    def __repr__(self) -> str:
        """Technical string representation."""
        return f"HabitCompletion(uid='{self.uid}', habit_uid='{self.habit_uid}', completed_at={self.completed_at})"
