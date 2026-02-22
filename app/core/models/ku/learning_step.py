"""
LearningStep - Learning Step Domain Model
=============================================

Frozen dataclass for learning step entities (EntityType.LEARNING_STEP).

Inherits common fields from Entity via Curriculum. Adds 9 learning-step-specific fields:
- Intent (1): intent
- Knowledge references (2): primary_knowledge_uids, supporting_knowledge_uids
- Path relationship (2): learning_path_uid, sequence
- Mastery (4): mastery_threshold, current_mastery, estimated_hours, step_difficulty

Learning-step-specific methods: get_combined_knowledge_uids, get_all_knowledge_uids,
calculate_mastery_progress, is_mastered, calculate_learning_impact, get_summary, from_dto.

See: /.claude/plans/crispy-spinning-wozniak.md
See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.ku.ku_dto import KuDTO

from core.models.enums.ku_enums import EntityType, StepDifficulty
from core.models.ku.curriculum import Curriculum


@dataclass(frozen=True)
class LearningStep(Curriculum):
    """
    Immutable domain model for learning steps (EntityType.LEARNING_STEP).

    Inherits ~50 fields from Curriculum (Entity fields + learning metadata
    + substance tracking). Adds 9 learning-step-specific fields for intent,
    knowledge references, path relationship, and mastery tracking.
    """

    def __post_init__(self) -> None:
        """Force ku_type=LEARNING_STEP, then delegate to Entity."""
        if self.ku_type != EntityType.LEARNING_STEP:
            object.__setattr__(self, "ku_type", EntityType.LEARNING_STEP)
        super().__post_init__()

    # =========================================================================
    # INTENT
    # =========================================================================
    intent: str | None = None  # Learning intent for this step

    # =========================================================================
    # KNOWLEDGE REFERENCES
    # =========================================================================
    primary_knowledge_uids: tuple[str, ...] = ()  # Primary KU references
    supporting_knowledge_uids: tuple[str, ...] = ()  # Supporting KU references

    # =========================================================================
    # PATH RELATIONSHIP
    # =========================================================================
    learning_path_uid: str | None = None  # LS → LP relationship
    sequence: int | None = None  # Order within learning path

    # =========================================================================
    # MASTERY
    # =========================================================================
    mastery_threshold: float = 0.7  # Target mastery level
    current_mastery: float = 0.0  # Current progress toward mastery
    estimated_hours: float | None = None  # Estimated time to complete
    step_difficulty: StepDifficulty | None = None  # Difficulty rating

    # =========================================================================
    # LEARNING-STEP-SPECIFIC METHODS
    # =========================================================================

    def get_combined_knowledge_uids(self) -> set[str]:
        """Get all knowledge UIDs related to this step."""
        uids: set[str] = set()
        if self.primary_knowledge_uids:
            uids.update(self.primary_knowledge_uids)
        if self.supporting_knowledge_uids:
            uids.update(self.supporting_knowledge_uids)
        return uids

    def get_all_knowledge_uids(self) -> set[str]:
        """Alias for get_combined_knowledge_uids."""
        return self.get_combined_knowledge_uids()

    def calculate_mastery_progress(self) -> float:
        """Calculate progress toward mastery threshold (0.0-1.0)."""
        if self.mastery_threshold <= 0:
            return 0.0
        return min(1.0, self.current_mastery / self.mastery_threshold)

    def is_mastered(self) -> bool:
        """Check if step mastery target has been reached."""
        return self.current_mastery >= self.mastery_threshold

    def calculate_learning_impact(self) -> float:
        """Calculate learning impact score (0.0-1.0)."""
        score = 0.0
        if self.primary_knowledge_uids:
            score += min(0.4, len(self.primary_knowledge_uids) * 0.1)
        if self.supporting_knowledge_uids:
            score += min(0.3, len(self.supporting_knowledge_uids) * 0.1)
        score += self.difficulty_rating * 0.3
        return min(1.0, score)

    # =========================================================================
    # OVERRIDES
    # =========================================================================

    def get_summary(self, max_length: int = 200) -> str:
        """Get a summary of the learning step."""
        text = self.intent or self.description or self.content or self.summary or ""
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."

    # =========================================================================
    # CONVERSION (generic -- uses Entity._from_dto / to_dto)
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "KuDTO") -> "LearningStep":
        """Create LearningStep from a KuDTO."""
        return cls._from_dto(dto)

    def __str__(self) -> str:
        return f"LearningStep(uid={self.uid}, sequence={self.sequence}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"LearningStep(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, sequence={self.sequence}, "
            f"mastery={self.current_mastery}/{self.mastery_threshold}, "
            f"user_uid={self.user_uid})"
        )
