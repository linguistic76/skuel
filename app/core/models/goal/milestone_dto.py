"""
Milestone DTO (Tier 2 - Transfer)
==================================

Mutable data transfer object for standalone milestone operations.
Used internally by services for data manipulation.

Note: This is for standalone milestone management. The Goal model
also contains embedded Milestone objects for goal-specific milestones.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from core.utils.uid_generator import UIDGenerator


@dataclass
class MilestoneDTO:
    """
    Mutable data transfer object for standalone Milestone.

    Used by services to:
    - Create new milestones
    - Update existing milestones
    - Transfer data between layers
    """

    # Identity
    uid: str
    goal_uid: str
    title: str

    # Content
    description: str | None = (None,)
    target_date: date | None = (None,)
    completed_date: datetime | None = None  # type: ignore[assignment]
    is_completed: bool = False
    order: int = 0

    # Metadata
    created_at: datetime = (field(default_factory=datetime.now),)
    updated_at: datetime = field(default_factory=datetime.now)

    # Additional data for Neo4j/extensions
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        goal_uid: str,
        title: str,
        description: str | None = None,
        target_date: date | None = None,
        order: int = 0,
    ) -> "MilestoneDTO":
        """Factory method to create new MilestoneDTO with generated UID."""
        return cls(
            uid=UIDGenerator.generate_random_uid("milestone"),
            goal_uid=goal_uid,
            title=title,
            description=description,
            target_date=target_date,
            order=order,
        )

    def update_from(self, updates: dict[str, Any]) -> None:
        """Update fields from dictionary."""
        from core.models.dto_helpers import update_from_dict

        update_from_dict(self, updates)

    def complete(self, completed_date: datetime | None = None, notes: str | None = None) -> None:
        """Mark milestone as completed."""
        self.is_completed = True
        self.completed_date = completed_date or datetime.now()
        if notes:
            self.metadata["completion_notes"] = notes
        self.updated_at = datetime.now()

    def uncomplete(self) -> None:
        """Mark milestone as not completed."""
        self.is_completed = False
        self.completed_date = None
        if "completion_notes" in self.metadata:
            del self.metadata["completion_notes"]
        self.updated_at = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database operations."""
        from dataclasses import asdict

        from core.models.dto_helpers import convert_dates_to_iso, convert_datetimes_to_iso

        data = asdict(self)

        # Convert dates to ISO format
        convert_dates_to_iso(data, ["target_date"])

        # Convert datetimes to ISO format
        convert_datetimes_to_iso(data, ["completed_date", "created_at", "updated_at"])

        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MilestoneDTO":
        """Create DTO from dictionary."""
        from core.models.dto_helpers import (
            ensure_dict_field,
            parse_date_fields,
            parse_datetime_fields,
        )

        # Parse dates
        parse_date_fields(data, ["target_date"])

        # Parse datetimes
        parse_datetime_fields(data, ["completed_date", "created_at", "updated_at"])

        # Ensure metadata dict
        ensure_dict_field(data, "metadata")

        return cls(**data)

    def is_overdue(self) -> bool:
        """Check if milestone is overdue."""
        if self.is_completed or not self.target_date:
            return False
        return date.today() > self.target_date

    def days_until_target(self) -> int | None:
        """Calculate days until target date."""
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

    def has_completion_notes(self) -> bool:
        """Check if milestone has completion notes."""
        return "completion_notes" in self.metadata and bool(self.metadata["completion_notes"])

    def get_completion_notes(self) -> str | None:
        """Get completion notes."""
        return self.metadata.get("completion_notes")

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
