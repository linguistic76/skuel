"""
User Progress Domain Model
===========================

Represents user progress tracking for learning, tasks, habits, and goals.
This model enables storing progress data using UniversalNeo4jBackend.

Following SKUEL three-tier type system:
- This is Tier 3: Domain Model (frozen, immutable business logic)
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from core.models.enums import Domain


@dataclass(frozen=True)
class UserProgress:
    """
    User progress tracking for any domain.

    Can represent:
    - Learning progress (knowledge mastery, learning steps)
    - Task completion metrics
    - Habit consistency tracking
    - Goal achievement milestones

    Stored in Neo4j with label "UserProgress".
    """

    # Identity
    uid: str  # Format: "progress.{user_uid}.{entity_uid}.{timestamp}"
    user_uid: str  # User who achieved this progress
    entity_uid: str  # What was progressed (task, habit, goal, knowledge, etc.)
    entity_type: str  # "task", "habit", "goal", "knowledge", "learning_step"

    # Progress metrics
    progress_value: float  # 0.0-1.0 for percentage, or specific metric
    status: str  # "in_progress", "completed", "mastered", "abandoned"

    # Timestamps
    tracked_at: datetime  # When this progress was recorded
    started_at: datetime | None = None  # type: ignore[assignment]
    completed_at: datetime | None = None  # type: ignore[assignment]

    # Quality metrics
    mastery_score: float | None = None  # 0.0-1.0 mastery level (for learning),
    confidence_level: float | None = None  # User's confidence (0.0-1.0),
    difficulty_rating: float | None = None  # User's perceived difficulty (0.0-1.0)

    # Time tracking
    time_invested_minutes: int = 0  # Total time invested,
    practice_count: int = 0  # Number of practice sessions (for learning)

    # Context
    domain: Domain | None = None  # Domain classification,
    metadata: dict[str, Any] | None = None  # type: ignore[assignment]

    # Review scheduling (spaced repetition)
    last_reviewed: datetime | None = None  # type: ignore[assignment]
    next_review_due: date | None = None  # type: ignore[assignment]
    review_interval_days: int | None = None

    def __post_init__(self) -> None:
        """Validate progress data."""
        # Validate progress_value
        if not 0.0 <= self.progress_value <= 1.0:
            raise ValueError(f"progress_value must be 0.0-1.0, got {self.progress_value}")

        # Validate mastery_score if present
        if self.mastery_score is not None and not 0.0 <= self.mastery_score <= 1.0:
            raise ValueError(f"mastery_score must be 0.0-1.0, got {self.mastery_score}")

        # Validate confidence_level if present
        if self.confidence_level is not None and not 0.0 <= self.confidence_level <= 1.0:
            raise ValueError(f"confidence_level must be 0.0-1.0, got {self.confidence_level}")

        # Validate timestamps
        if self.completed_at and self.started_at and self.completed_at < self.started_at:
            raise ValueError("completed_at cannot be before started_at")

    @property
    def is_completed(self) -> bool:
        """Check if progress is completed."""
        return self.status == "completed" or self.progress_value >= 1.0

    @property
    def is_mastered(self) -> bool:
        """Check if entity is mastered (for learning)."""
        return self.status == "mastered" and (self.mastery_score or 0.0) >= 0.8

    @property
    def needs_review(self) -> bool:
        """Check if entity needs review."""
        if not self.next_review_due:
            return False
        return self.next_review_due <= date.today()

    @property
    def completion_percentage(self) -> float:
        """Get completion percentage (0-100)."""
        return self.progress_value * 100.0

    def with_updated_progress(self, new_progress: float, time_invested: int = 0) -> "UserProgress":
        """
        Create new instance with updated progress.

        Args:
            new_progress: New progress value (0.0-1.0)
            time_invested: Additional time invested in minutes

        Returns:
            New UserProgress instance with updated values
        """
        from dataclasses import replace

        new_status = "completed" if new_progress >= 1.0 else "in_progress"
        new_completed_at = datetime.now() if new_progress >= 1.0 else self.completed_at

        return replace(
            self,
            progress_value=new_progress,
            status=new_status,
            completed_at=new_completed_at,
            time_invested_minutes=self.time_invested_minutes + time_invested,
            tracked_at=datetime.now(),
        )

    def with_mastery(self, mastery_score: float, confidence: float = 0.8) -> "UserProgress":
        """
        Create new instance marking as mastered.

        Args:
            mastery_score: Mastery level (0.8-1.0)
            confidence: Confidence level (0.0-1.0)

        Returns:
            New UserProgress instance marked as mastered
        """
        from dataclasses import replace

        if mastery_score < 0.8:
            raise ValueError("Mastery score must be >= 0.8")

        return replace(
            self,
            progress_value=1.0,
            mastery_score=mastery_score,
            confidence_level=confidence,
            status="mastered",
            completed_at=datetime.now(),
            tracked_at=datetime.now(),
        )


@dataclass(frozen=True)
class ProgressAggregate:
    """
    Aggregated progress statistics for a user across a domain or entity type.

    Read-only computed view, not stored directly.
    """

    user_uid: str
    entity_type: str | None = None  # Filter by type, or None for all,
    domain: Domain | None = None  # Filter by domain, or None for all

    # Counts
    total_items: int = 0

    completed_items: int = 0
    in_progress_items: int = 0

    mastered_items: int = 0

    # Averages
    average_progress: float = 0.0  # 0.0-1.0,
    average_mastery: float = 0.0  # 0.0-1.0,
    average_confidence: float = 0.0  # 0.0-1.0

    # Time metrics
    total_time_minutes: int = 0

    total_practice_sessions: int = 0

    # Period
    period_start: date | None = None  # type: ignore[assignment]
    period_end: date | None = None  # type: ignore[assignment]

    @property
    def completion_rate(self) -> float:
        """Calculate completion rate (0.0-1.0)."""
        if self.total_items == 0:
            return 0.0
        return self.completed_items / self.total_items

    @property
    def mastery_rate(self) -> float:
        """Calculate mastery rate (0.0-1.0) for learning items."""
        if self.total_items == 0:
            return 0.0
        return self.mastered_items / self.total_items


# ============================================================================
# UID GENERATION
# ============================================================================


def generate_progress_uid(user_uid: str, entity_uid: str, timestamp: datetime | None = None) -> str:
    """
    Generate unique UID for progress record.

    Format: progress.{user_uid}.{entity_uid}.{timestamp_ms}

    Args:
        user_uid: User identifier
        entity_uid: Entity identifier
        timestamp: Optional timestamp (defaults to now)

    Returns:
        Generated UID
    """
    if not timestamp:
        timestamp = datetime.now()

    timestamp_ms = int(timestamp.timestamp() * 1000)
    return f"progress.{user_uid}.{entity_uid}.{timestamp_ms}"


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = ["ProgressAggregate", "UserProgress", "generate_progress_uid"]
