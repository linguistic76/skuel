"""
Guidance Relationship Model
===========================

Captures HOW a principle guides an entity (goal, habit, or choice).

Example:
--------
Principle: "Small steps > big plans"
Goal: "Establish daily meditation practice"

Guidance captures:
- manifestation: "By starting with just 2 minutes daily instead of 30"
- strength: 0.9 (this principle strongly guides this goal)

This makes the principle's influence explicit and visible to the user.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Guidance:
    """
    A principle guiding an entity.

    Represents the relationship between a principle and the entity it guides,
    with explicit context about HOW the guidance manifests.

    Attributes:
        uid: Unique identifier for this guidance relationship
        principle_uid: UID of the guiding principle
        entity_uid: UID of the entity being guided (goal, habit, or choice)
        entity_type: Type of entity ("goal", "habit", "choice")
        manifestation: HOW the principle guides this entity (human-readable)
        strength: How strongly this principle guides (0-1 scale)
        created_at: When this guidance was established
        updated_at: When this guidance was last updated
    """

    uid: str
    principle_uid: str
    entity_uid: str
    entity_type: str
    manifestation: str
    strength: float = 1.0
    created_at: datetime | None = None  # type: ignore[assignment]
    updated_at: datetime | None = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        """Validate guidance data."""
        # Validate entity_type
        valid_types = {"goal", "habit", "choice", "task"}
        if self.entity_type not in valid_types:
            raise ValueError(f"entity_type must be one of {valid_types}, got '{self.entity_type}'")

        # Validate strength
        if not 0.0 <= self.strength <= 1.0:
            raise ValueError(f"strength must be between 0 and 1, got {self.strength}")

        # Validate manifestation is not empty
        if not self.manifestation or not self.manifestation.strip():
            raise ValueError("manifestation cannot be empty")

    def is_strong_guidance(self) -> bool:
        """Check if this is strong guidance (strength >= 0.7)."""
        return self.strength >= 0.7

    def is_weak_guidance(self) -> bool:
        """Check if this is weak guidance (strength < 0.4)."""
        return self.strength < 0.4

    def get_strength_label(self) -> str:
        """
        Get human-readable strength label.

        Returns:
            "Strong", "Moderate", or "Weak"
        """
        if self.strength >= 0.7:
            return "Strong"
        elif self.strength >= 0.4:
            return "Moderate"
        else:
            return "Weak"

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "uid": self.uid,
            "principle_uid": self.principle_uid,
            "entity_uid": self.entity_uid,
            "entity_type": self.entity_type,
            "manifestation": self.manifestation,
            "strength": self.strength,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Guidance":
        """Create Guidance from dictionary."""
        from datetime import datetime

        return cls(
            uid=data["uid"],
            principle_uid=data["principle_uid"],
            entity_uid=data["entity_uid"],
            entity_type=data["entity_type"],
            manifestation=data["manifestation"],
            strength=data.get("strength", 1.0),
            created_at=datetime.fromisoformat(data["created_at"])
            if data.get("created_at")
            else None,
            updated_at=datetime.fromisoformat(data["updated_at"])
            if data.get("updated_at")
            else None,
        )

    def __str__(self) -> str:
        """Human-readable representation."""
        return f"Guidance({self.get_strength_label()}): {self.manifestation}"
