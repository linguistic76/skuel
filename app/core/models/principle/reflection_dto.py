"""
Principle Reflection DTO (Tier 2 - Transfer)
=============================================

Mutable data transfer object for principle reflection operations.
Used internally by services for data manipulation before converting
to the immutable domain model.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from core.models.enums.principle_enums import AlignmentLevel
from core.utils.uid_generator import UIDGenerator


@dataclass
class PrincipleReflectionDTO:
    """
    Mutable data transfer object for Principle Reflection.

    Used by services to:
    - Create new principle reflections
    - Update existing reflections
    - Transfer data between layers
    """

    # Identity
    uid: str
    principle_uid: str
    user_uid: str
    reflection_date: date

    # Assessment
    alignment_level: AlignmentLevel
    evidence: str

    # Reflection details
    reflection_notes: str | None = None

    # Quality metrics
    reflection_quality_score: float = 0.0

    # Trigger context
    trigger_type: str | None = None  # "goal", "habit", "event", "choice", "manual"
    trigger_uid: str | None = None
    trigger_context: str | None = None

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    # Metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        principle_uid: str,
        user_uid: str,
        alignment_level: AlignmentLevel,
        evidence: str,
        reflection_notes: str | None = None,
        trigger_type: str | None = None,
        trigger_uid: str | None = None,
        trigger_context: str | None = None,
        reflection_date: date | None = None,
    ) -> "PrincipleReflectionDTO":
        """
        Factory method to create new PrincipleReflectionDTO with generated UID.

        Args:
            principle_uid: UID of the principle being reflected on
            user_uid: UID of the user making the reflection
            alignment_level: How well actions aligned with the principle
            evidence: What was observed
            reflection_notes: Optional additional thoughts
            trigger_type: What triggered this reflection
            trigger_uid: UID of triggering entity
            trigger_context: Context description
            reflection_date: Date of reflection (defaults to today)

        Returns:
            New PrincipleReflectionDTO instance
        """
        dto = cls(
            uid=UIDGenerator.generate_random_uid("reflection"),
            principle_uid=principle_uid,
            user_uid=user_uid,
            reflection_date=reflection_date or date.today(),
            alignment_level=alignment_level,
            evidence=evidence,
            reflection_notes=reflection_notes,
            trigger_type=trigger_type,
            trigger_uid=trigger_uid,
            trigger_context=trigger_context,
        )

        # Calculate quality score
        dto.reflection_quality_score = dto._calculate_quality_score()

        return dto

    def _calculate_quality_score(self) -> float:
        """
        Calculate reflection quality score (0-1).

        Factors:
        - Evidence depth (0.4 weight)
        - Notes depth (0.3 weight)
        - Has trigger context (0.2 weight)
        - Has trigger UID (0.1 weight)
        """
        score = 0.0

        # Evidence depth (0.4 weight)
        if self.evidence:
            evidence_words = len(self.evidence.strip().split())
            if evidence_words >= 20:
                score += 0.4
            elif evidence_words >= 10:
                score += 0.3
            elif evidence_words >= 5:
                score += 0.2
            else:
                score += 0.1

        # Notes depth (0.3 weight)
        if self.reflection_notes:
            notes_words = len(self.reflection_notes.strip().split())
            if notes_words >= 15:
                score += 0.3
            elif notes_words >= 8:
                score += 0.2
            elif notes_words >= 3:
                score += 0.1

        # Has trigger context (0.2 weight)
        if self.trigger_context and len(self.trigger_context.strip()) > 10:
            score += 0.2

        # Has trigger UID (0.1 weight)
        if self.trigger_uid:
            score += 0.1

        return min(1.0, score)

    def update_from(self, updates: dict[str, Any]) -> None:
        """Update fields from dictionary."""
        from core.models.dto_helpers import update_from_dict

        update_from_dict(self, updates)
        # Recalculate quality score after updates
        self.reflection_quality_score = self._calculate_quality_score()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database operations."""
        from dataclasses import asdict

        from core.models.dto_helpers import convert_datetimes_to_iso

        data = asdict(self)

        # Convert alignment_level enum to string
        data["alignment_level"] = self.alignment_level.value

        # Convert dates and datetimes
        if isinstance(data.get("reflection_date"), date):
            data["reflection_date"] = data["reflection_date"].isoformat()

        convert_datetimes_to_iso(data, ["created_at", "updated_at"])

        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PrincipleReflectionDTO":
        """Create DTO from dictionary (e.g., from database)."""
        from core.models.dto_helpers import ensure_dict_field, parse_datetime_fields

        # Make a copy to avoid modifying input
        data = dict(data)

        # Parse alignment_level from string
        if isinstance(data.get("alignment_level"), str):
            data["alignment_level"] = AlignmentLevel(data["alignment_level"])

        # Parse reflection_date
        if isinstance(data.get("reflection_date"), str):
            data["reflection_date"] = date.fromisoformat(data["reflection_date"])

        # Parse timestamps
        parse_datetime_fields(data, ["created_at", "updated_at"])

        # Ensure metadata dict
        ensure_dict_field(data, "metadata")

        # Filter to only known fields
        known_fields = {
            "uid",
            "principle_uid",
            "user_uid",
            "reflection_date",
            "alignment_level",
            "evidence",
            "reflection_notes",
            "reflection_quality_score",
            "trigger_type",
            "trigger_uid",
            "trigger_context",
            "created_at",
            "updated_at",
            "metadata",
        }
        filtered_data = {k: v for k, v in data.items() if k in known_fields}

        return cls(**filtered_data)

    # ========================================================================
    # HELPER METHODS
    # ========================================================================

    def is_positive_alignment(self) -> bool:
        """Check if alignment is positive."""
        return self.alignment_level in [AlignmentLevel.ALIGNED, AlignmentLevel.MOSTLY_ALIGNED]

    def has_trigger(self) -> bool:
        """Check if reflection has a trigger."""
        return self.trigger_type is not None and self.trigger_type != "manual"

    def has_notes(self) -> bool:
        """Check if reflection has notes."""
        return self.reflection_notes is not None and len(self.reflection_notes.strip()) > 0

    def quality_level(self) -> str:
        """Get quality level description."""
        if self.reflection_quality_score >= 0.7:
            return "deep"
        elif self.reflection_quality_score >= 0.4:
            return "moderate"
        else:
            return "shallow"
