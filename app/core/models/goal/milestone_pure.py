"""
Milestone Domain Model (Tier 3 - Core)
=======================================

Immutable domain model with business logic for standalone milestones.
This is the core business entity that encapsulates all milestone-related rules.

Note: This is for standalone milestone management. The Goal model
also contains embedded Milestone objects for goal-specific milestones.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .milestone_dto import MilestoneDTO


@dataclass(frozen=True)
class Milestone:
    """
    Immutable domain model for standalone milestones.

    This model contains all business logic for milestone operations
    and maintains referential integrity through immutability.
    """

    # Identity (required fields first)
    uid: str
    goal_uid: str
    title: str
    created_at: datetime
    updated_at: datetime

    # Content (optional fields last)
    description: str | None = None
    target_date: date | None = None  # type: ignore[assignment]
    completed_date: datetime | None = None  # type: ignore[assignment]
    is_completed: bool = False
    order: int = 0

    def __post_init__(self) -> None:
        """Validate the domain model after creation."""
        if not self.title.strip():
            raise ValueError("Title cannot be empty")

        if self.order < 0:
            raise ValueError("Order cannot be negative")

        if self.target_date and self.completed_date:
            # If both dates are present, validate logical consistency
            completion_date = self.completed_date.date()
            if completion_date < date(2020, 1, 1):  # Reasonable lower bound
                raise ValueError("Completion date is unrealistic")

    # ========================================================================
    # FACTORY METHODS
    # ========================================================================

    @classmethod
    def from_dto(cls, dto: MilestoneDTO) -> "Milestone":
        """Create domain model from DTO."""
        return cls(
            uid=dto.uid,
            goal_uid=dto.goal_uid,
            title=dto.title,
            description=dto.description,
            target_date=dto.target_date,
            completed_date=dto.completed_date,
            is_completed=dto.is_completed,
            order=dto.order,
            created_at=dto.created_at,
            updated_at=dto.updated_at,
        )

    def to_dto(self) -> MilestoneDTO:
        """Convert to DTO for transfer operations."""
        return MilestoneDTO(
            uid=self.uid,
            goal_uid=self.goal_uid,
            title=self.title,
            description=self.description,
            target_date=self.target_date,
            completed_date=self.completed_date,
            is_completed=self.is_completed,
            order=self.order,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    # ========================================================================
    # BUSINESS LOGIC METHODS
    # ========================================================================

    def is_overdue(self) -> bool:
        """Check if milestone is overdue."""
        if self.is_completed or not self.target_date:
            return False
        return date.today() > self.target_date

    def is_due_soon(self, days: int = 7) -> bool:
        """
        Check if milestone is due within specified days.

        Args:
            days: Number of days to look ahead

        Returns:
            True if milestone is due within the specified period
        """
        if self.is_completed or not self.target_date:
            return False

        cutoff_date = date.today() + timedelta(days=days)
        return self.target_date <= cutoff_date

    def days_until_target(self) -> int | None:
        """
        Calculate days until target date.

        Returns:
            Number of days (negative if overdue, None if no target date)
        """
        if not self.target_date:
            return None
        delta = self.target_date - date.today()
        return delta.days

    def days_since_completion(self) -> int | None:
        """Calculate days since completion."""
        if not self.completed_date:
            return None
        delta = datetime.now() - self.completed_date
        return delta.days

    def completion_percentage(self) -> float:
        """
        Calculate completion percentage based on status.

        Returns:
            1.0 if completed, 0.0 if not completed
        """
        return 1.0 if self.is_completed else 0.0

    def progress_score(self) -> float:
        """
        Calculate a progress score (0.0-1.0) considering timing.

        Factors in:
        - Completion status (primary factor)
        - Whether completion was on time
        - Time remaining if not completed

        Returns:
            Score from 0.0 to 1.0
        """
        if self.is_completed:
            # Completed milestones get high scores
            if self.was_completed_on_time():
                return 1.0
            elif self.was_completed_early():
                return 1.0  # Early completion is excellent
            else:
                return 0.9  # Late completion still good

        # Not completed - score based on time factors
        if not self.target_date:
            return 0.5  # No deadline = moderate score

        days_remaining = self.days_until_target()
        if days_remaining is None:
            return 0.5

        if days_remaining < 0:
            # Overdue - score decreases with time
            days_overdue = abs(days_remaining)
            penalty = min(days_overdue * 0.05, 0.4)  # Up to 40% penalty
            return max(0.1, 0.5 - penalty)

        # Future deadline - score based on urgency
        if days_remaining <= 3:
            return 0.7  # Urgent but not overdue
        elif days_remaining <= 7:
            return 0.6  # Due soon
        else:
            return 0.5  # Not urgent

    def was_completed_on_time(self) -> bool | None:
        """Check if milestone was completed by target date."""
        if not self.is_completed or not self.completed_date or not self.target_date:
            return None
        return self.completed_date.date() <= self.target_date

    def was_completed_early(self) -> bool | None:
        """Check if milestone was completed before target date."""
        if not self.is_completed or not self.completed_date or not self.target_date:
            return None
        return self.completed_date.date() < self.target_date

    def was_completed_late(self) -> bool | None:
        """Check if milestone was completed after target date."""
        if not self.is_completed or not self.completed_date or not self.target_date:
            return None
        return self.completed_date.date() > self.target_date

    def urgency_level(self) -> str:
        """
        Get urgency level based on target date and completion status.

        Returns:
            String description of urgency level
        """
        if self.is_completed:
            return "completed"

        if not self.target_date:
            return "no_deadline"

        days_remaining = self.days_until_target()
        if days_remaining is None:
            return "no_deadline"

        if days_remaining < 0:
            return "overdue"
        elif days_remaining == 0:
            return "due_today"
        elif days_remaining <= 1:
            return "due_tomorrow"
        elif days_remaining <= 3:
            return "due_soon"
        elif days_remaining <= 7:
            return "due_this_week"
        elif days_remaining <= 30:
            return "due_this_month"
        else:
            return "future"

    def is_critical(self) -> bool:
        """
        Check if this milestone is critical (overdue or due very soon).

        Returns:
            True if milestone requires immediate attention
        """
        urgency = self.urgency_level()
        return urgency in ["overdue", "due_today", "due_tomorrow", "due_soon"]

    def time_performance(self) -> str | None:
        """
        Analyze time performance for completed milestones.

        Returns:
            Performance description or None if not completed
        """
        if not self.is_completed:
            return None

        if self.was_completed_early():
            return "early"
        elif self.was_completed_on_time():
            return "on_time"
        elif self.was_completed_late():
            return "late"
        else:
            return "no_deadline"

    def estimated_effort_remaining(self) -> str:
        """
        Estimate effort remaining based on completion status and timing.

        Returns:
            Effort estimate description
        """
        if self.is_completed:
            return "none"

        urgency = self.urgency_level()

        if urgency == "overdue":
            return "high"  # Need to catch up
        elif urgency in ["due_today", "due_tomorrow"]:
            return "high"  # Urgent completion needed
        elif urgency == "due_soon":
            return "medium"  # Focused effort needed
        elif urgency == "due_this_week":
            return "medium"  # Regular progress needed
        else:
            return "low"  # Can work steadily

    # ========================================================================
    # COMPARISON AND ANALYSIS
    # ========================================================================

    def is_more_urgent_than(self, other: "Milestone") -> bool:
        """
        Compare urgency with another milestone.

        Args:
            other: Another milestone to compare against

        Returns:
            True if this milestone is more urgent
        """
        # Completed milestones are not urgent
        if self.is_completed and not other.is_completed:
            return False
        if not self.is_completed and other.is_completed:
            return True

        # Both completed or both not completed
        self_days = self.days_until_target()
        other_days = other.days_until_target()

        # No target dates
        if self_days is None and other_days is None:
            return False  # Equal urgency
        if self_days is None:
            return False  # Other has deadline, this doesn't
        if other_days is None:
            return True  # This has deadline, other doesn't

        # Compare days remaining (less is more urgent)
        return self_days < other_days

    def priority_score(self) -> float:
        """
        Calculate overall priority score considering multiple factors.

        Returns:
            Score from 0.0 to 1.0 (higher = more important)
        """

        # Completion status
        if self.is_completed:
            return 0.1  # Completed items have low priority

        # Urgency factor
        urgency = self.urgency_level()
        urgency_scores = {
            "overdue": 1.0,
            "due_today": 0.9,
            "due_tomorrow": 0.8,
            "due_soon": 0.7,
            "due_this_week": 0.6,
            "due_this_month": 0.5,
            "future": 0.4,
            "no_deadline": 0.3,
        }
        urgency_score = urgency_scores.get(urgency, 0.3)

        # Order factor (lower order = higher priority)
        order_factor = max(0.1, 1.0 - (self.order * 0.1))

        # Combine factors
        priority = (urgency_score * 0.7) + (order_factor * 0.3)
        return min(1.0, priority)

    def __str__(self) -> str:
        """Human-readable string representation."""
        status = "✓" if self.is_completed else "○"
        date_str = f" (due {self.target_date})" if self.target_date else ""
        return f"{status} {self.title}{date_str}"

    def __repr__(self) -> str:
        """Technical string representation."""
        return (
            f"Milestone(uid='{self.uid}', title='{self.title}', is_completed={self.is_completed})"
        )
