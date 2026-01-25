"""
Habit Completion DTO (Tier 2 - Transfer)
=========================================

Mutable data transfer object for habit completion operations.
Used internally by services for data manipulation.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from core.utils.uid_generator import UIDGenerator


@dataclass
class HabitCompletionDTO:
    """
    Mutable data transfer object for Habit Completion.

    Used by services to:
    - Create new habit completions
    - Update existing habit completions
    - Transfer data between layers
    """

    # Identity
    uid: str
    habit_uid: str

    # Completion Details
    completed_at: datetime
    notes: str | None = (None,)
    quality: int | None = None  # 1-5 rating,
    duration_actual: int | None = None  # minutes

    # Metadata
    created_at: datetime = (field(default_factory=datetime.now),)
    updated_at: datetime = field(default_factory=datetime.now)

    # Additional data for Neo4j/extensions
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        habit_uid: str,
        completed_at: datetime | None = None,
        notes: str | None = None,
        quality: int | None = None,
        duration_actual: int | None = None,
    ) -> "HabitCompletionDTO":
        """Factory method to create new HabitCompletionDTO with generated UID."""
        return cls(
            uid=UIDGenerator.generate_random_uid("completion"),
            habit_uid=habit_uid,
            completed_at=completed_at or datetime.now(),
            notes=notes,
            quality=quality,
            duration_actual=duration_actual,
        )

    def update_from(self, updates: dict[str, Any]) -> None:
        """Update fields from dictionary."""
        from core.models.dto_helpers import update_from_dict

        update_from_dict(self, updates)

    def validate_quality(self) -> None:
        """Validate quality rating if provided."""
        if self.quality is not None and not (1 <= self.quality <= 5):
            raise ValueError("Quality must be between 1 and 5")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database operations."""
        from dataclasses import asdict

        from core.models.dto_helpers import convert_datetimes_to_iso

        data = asdict(self)

        # Convert datetimes to ISO format
        convert_datetimes_to_iso(data, ["completed_at", "created_at", "updated_at"])

        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HabitCompletionDTO":
        """Create DTO from dictionary."""
        from core.models.dto_helpers import ensure_dict_field, parse_datetime_fields

        # Parse datetimes
        parse_datetime_fields(data, ["completed_at", "created_at", "updated_at"])

        # Ensure metadata dict
        ensure_dict_field(data, "metadata")

        return cls(**data)

    def is_high_quality(self) -> bool:
        """Check if this completion has high quality rating."""
        return self.quality is not None and self.quality >= 4

    def has_notes(self) -> bool:
        """Check if this completion has notes."""
        return self.notes is not None and len(self.notes.strip()) > 0

    def was_extended_session(self, target_duration: int | None = None) -> bool:
        """Check if actual duration exceeded target duration."""
        if not self.duration_actual or not target_duration:
            return False
        return self.duration_actual > target_duration
