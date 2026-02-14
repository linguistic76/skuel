"""
Journal Processing Types
=========================

Type definitions for multi-modal journal processing.

See: ACTIVITY_EXTRACTION_ENABLED.md for architecture overview.
"""

from dataclasses import dataclass
from typing import Any

from core.models.enums.ku_enums import JournalMode


@dataclass(frozen=True)
class JournalWeights:
    """
    Weight distribution across three journal processing modes.

    Typical journal: 80% one mode + 20% mixed.
    Weights sum to 1.0 (normalized by classifier).

    Attributes:
        activity: Weight for activity tracking mode (0.0-1.0)
        articulation: Weight for idea articulation mode (0.0-1.0)
        exploration: Weight for critical thinking mode (0.0-1.0)
    """

    activity: float  # Activity tracking (DSL extraction)
    articulation: float  # Idea articulation (verbatim preservation)
    exploration: float  # Critical thinking (question organization)

    def __post_init__(self) -> None:
        """Validate weights are in valid range and sum to ~1.0."""
        if not (0.0 <= self.activity <= 1.0):
            raise ValueError(f"activity weight must be 0.0-1.0, got {self.activity}")
        if not (0.0 <= self.articulation <= 1.0):
            raise ValueError(f"articulation weight must be 0.0-1.0, got {self.articulation}")
        if not (0.0 <= self.exploration <= 1.0):
            raise ValueError(f"exploration weight must be 0.0-1.0, got {self.exploration}")

        total = self.activity + self.articulation + self.exploration
        if not (0.95 <= total <= 1.05):  # Allow small floating point variance
            raise ValueError(f"Weights must sum to 1.0, got {total}")

    def get_primary_mode(self) -> JournalMode:
        """Return the dominant mode based on highest weight."""
        if self.activity >= self.articulation and self.activity >= self.exploration:
            return JournalMode.ACTIVITY_TRACKING
        if self.articulation >= self.exploration:
            return JournalMode.IDEA_ARTICULATION
        return JournalMode.CRITICAL_THINKING

    def should_extract_activities(self, threshold: float = 0.2) -> bool:
        """Check if activity weight exceeds threshold for DSL extraction."""
        return self.activity > threshold

    def should_format_articulation(self, threshold: float = 0.2) -> bool:
        """Check if articulation weight exceeds threshold for verbatim formatting."""
        return self.articulation > threshold

    def should_organize_questions(self, threshold: float = 0.2) -> bool:
        """Check if exploration weight exceeds threshold for question organization."""
        return self.exploration > threshold

    def to_dict(self) -> dict[str, float | str]:
        """Convert to dictionary for JSON serialization."""
        return {
            "activity": self.activity,
            "articulation": self.articulation,
            "exploration": self.exploration,
            "primary_mode": self.get_primary_mode().value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, float]) -> "JournalWeights":
        """Create from dictionary (deserialization from metadata)."""
        return cls(
            activity=data["activity"],
            articulation=data["articulation"],
            exploration=data["exploration"],
        )

    @classmethod
    def balanced(cls) -> "JournalWeights":
        """Create balanced weights (33/33/33) for testing."""
        return cls(activity=0.33, articulation=0.34, exploration=0.33)

    @classmethod
    def activity_dominant(cls) -> "JournalWeights":
        """Create activity-dominant weights (80/10/10) for testing."""
        return cls(activity=0.8, articulation=0.1, exploration=0.1)

    @classmethod
    def articulation_dominant(cls) -> "JournalWeights":
        """Create articulation-dominant weights (10/80/10) for testing."""
        return cls(activity=0.1, articulation=0.8, exploration=0.1)

    @classmethod
    def exploration_dominant(cls) -> "JournalWeights":
        """Create exploration-dominant weights (10/10/80) for testing."""
        return cls(activity=0.1, articulation=0.1, exploration=0.8)


@dataclass(frozen=True)
class JournalProcessingResult:
    """
    Result of journal processing pipeline.

    Tracks what happened during multi-modal processing.
    """

    report_uid: str
    weights: JournalWeights
    je_output_path: str  # Path to formatted output file on disk
    activities_extracted: int = 0  # Count if activity mode triggered
    extraction_errors: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for metadata storage."""
        return {
            "report_uid": self.report_uid,
            "weights": self.weights.to_dict(),
            "je_output_path": self.je_output_path,
            "activities_extracted": self.activities_extracted,
            "extraction_errors": self.extraction_errors or [],
        }
