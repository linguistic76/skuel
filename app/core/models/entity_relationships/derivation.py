"""
Derivation Relationship Model
=============================

Captures WHY a choice created an entity (goal or habit).

Example:
--------
Choice: "Start meditation practice right now (2 minutes)"
Goal: "Establish daily meditation habit"

Derivation captures:
- reasoning: "Chose to start immediately with minimal friction rather than wait for 'perfect' conditions"
- confidence: 0.8 (how confident was this choice?)

This makes the choice's impact explicit and traceable.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Derivation:
    """
    A choice creating an entity.

    Represents the relationship between a choice and the entity it spawned,
    with explicit reasoning about WHY this choice led to this entity.

    Attributes:
        uid: Unique identifier for this derivation relationship
        choice_uid: UID of the originating choice
        created_entity_uid: UID of the entity created by this choice
        created_entity_type: Type of created entity ("goal", "habit", "task")
        reasoning: WHY this choice led to this entity (human-readable)
        confidence: How confident was this choice (0-1 scale)
        created_at: When this derivation occurred
        updated_at: When this derivation was last updated
    """

    uid: str
    choice_uid: str
    created_entity_uid: str
    created_entity_type: str
    reasoning: str
    confidence: float = 0.8
    created_at: datetime | None = None  # type: ignore[assignment]
    updated_at: datetime | None = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        """Validate derivation data."""
        # Validate entity_type
        valid_types = {"goal", "habit", "task", "principle"}
        if self.created_entity_type not in valid_types:
            raise ValueError(
                f"created_entity_type must be one of {valid_types}, got '{self.created_entity_type}'"
            )

        # Validate confidence
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be between 0 and 1, got {self.confidence}")

        # Validate reasoning is not empty
        if not self.reasoning or not self.reasoning.strip():
            raise ValueError("reasoning cannot be empty")

    def is_high_confidence(self) -> bool:
        """Check if this was a high-confidence choice (>= 0.7)."""
        return self.confidence >= 0.7

    def is_low_confidence(self) -> bool:
        """Check if this was a low-confidence choice (< 0.4)."""
        return self.confidence < 0.4

    def get_confidence_label(self) -> str:
        """
        Get human-readable confidence label.

        Returns:
            "High confidence", "Moderate confidence", or "Low confidence"
        """
        if self.confidence >= 0.7:
            return "High confidence"
        elif self.confidence >= 0.4:
            return "Moderate confidence"
        else:
            return "Low confidence"

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "uid": self.uid,
            "choice_uid": self.choice_uid,
            "created_entity_uid": self.created_entity_uid,
            "created_entity_type": self.created_entity_type,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Derivation":
        """Create Derivation from dictionary."""
        from datetime import datetime

        return cls(
            uid=data["uid"],
            choice_uid=data["choice_uid"],
            created_entity_uid=data["created_entity_uid"],
            created_entity_type=data["created_entity_type"],
            reasoning=data["reasoning"],
            confidence=data.get("confidence", 0.8),
            created_at=datetime.fromisoformat(data["created_at"])
            if data.get("created_at")
            else None,
            updated_at=datetime.fromisoformat(data["updated_at"])
            if data.get("updated_at")
            else None,
        )

    def __str__(self) -> str:
        """Human-readable representation."""
        return f"Derivation({self.get_confidence_label()}): {self.reasoning}"
