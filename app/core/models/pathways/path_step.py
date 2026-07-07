"""
PathStep - THE Curriculum Content Entity
=========================================

Frozen dataclass for path step entities (EntityType.PATH_STEP).
A PathStep is THE unit for learning — it composes atomic Kus into coherent
learning content and sits within a LearningPath.

3-level hierarchy: LearningPath -> PathStep -> Ku

Inherits common fields from Entity via Curriculum. Adds 9 path-step-specific fields:
- Intent (1): intent
- NOUS membership (1): nous
- Knowledge references (1): knowledge_uids (graph-native, reconstructed from CONTAINS_KNOWLEDGE)
- Path relationship (2): learning_path_uid, sequence
- Mastery (4): mastery_threshold, current_mastery, estimated_hours, step_difficulty

Key relationships:
- USES_KU -> Ku (content composition)
- CONTAINS_KNOWLEDGE -> Ku (knowledge reference)
- TRAINS_KU -> Ku (learning objectives)
- ORGANIZES -> PathStep (emergent MOC identity)
- Activity wiring: BUILDS_HABIT, ASSIGNS_TASK, SCHEDULES_EVENT, etc.
- Learning states: VIEWED, IN_PROGRESS, MASTERED, BOOKMARKED (on user relationships)

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.pathways.path_step_dto import PathStepDTO

from core.models.curriculum import Curriculum
from core.models.enums.curriculum_enums import StepDifficulty
from core.models.enums.entity_enums import EntityType


@dataclass(frozen=True)
class PathStep(Curriculum):
    """
    THE curriculum content entity (EntityType.PATH_STEP).

    A PathStep composes atomic Kus into coherent learning content and sits
    within a LearningPath. Inherits ~50 fields from Curriculum. Adds 9 fields
    for intent, knowledge references, path relationship, and mastery tracking.
    """

    # Honest leaf identity (G6): defaults to its own type; __post_init__
    # rejects a mismatch instead of silently correcting it.
    entity_type: EntityType = field(default=EntityType.PATH_STEP, kw_only=True)

    def __post_init__(self) -> None:
        """Validate entity_type=PATH_STEP, then delegate to Entity."""
        if self.entity_type != EntityType.PATH_STEP:
            raise ValueError(
                f"PathStep constructed with entity_type={self.entity_type!r} "
                f"(uid={self.uid!r}) — the writer persisted a wrong type (G6)"
            )
        # Normalize list-authored nous/nous_subtopic to tuple (frozen — mirrors Ku)
        if isinstance(self.nous, list):
            object.__setattr__(self, "nous", tuple(self.nous))
        if isinstance(self.nous_subtopic, list):
            object.__setattr__(self, "nous_subtopic", tuple(self.nous_subtopic))
        super().__post_init__()

    # =========================================================================
    # INTENT
    # =========================================================================
    intent: str | None = None  # Learning intent for this step

    # =========================================================================
    # NOUS TOPIC MEMBERSHIP
    # =========================================================================
    # Which of the 11 official NOUS topic sections this PathStep belongs to
    # (stories, body, self-awareness, ...). Multi-topic allowed; empty =
    # deliberately unassigned (rawness principle). Authored in vault YAML
    # as `nous:`.
    nous: tuple[str, ...] = ()
    # NOUS sub-topic membership — 2nd taxonomy level beneath `nous` (mirrors Ku).
    # Multi-valued; empty = unassigned. Authored in vault YAML as `nous_subtopic:`.
    # Symmetric with `nous` so subtopic-scoped search/RAG includes PathStep content
    # (else the subtopic predicate would drop every PathStep card + body chunk).
    nous_subtopic: tuple[str, ...] = ()

    # =========================================================================
    # KNOWLEDGE REFERENCES (graph-native: reconstructed from CONTAINS_KNOWLEDGE)
    # =========================================================================
    knowledge_uids: tuple[str, ...] = ()  # KU references via CONTAINS_KNOWLEDGE

    # =========================================================================
    # PATH RELATIONSHIP
    # =========================================================================
    learning_path_uid: str | None = None  # PS → LP relationship
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
        return set(self.knowledge_uids)

    def get_all_knowledge_uids(self) -> set[str]:
        """Alias for get_combined_knowledge_uids."""
        return set(self.knowledge_uids)

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
        if self.knowledge_uids:
            score += min(0.7, len(self.knowledge_uids) * 0.1)
        score += self.difficulty_rating * 0.3
        return min(1.0, score)

    # =========================================================================
    # OVERRIDES
    # =========================================================================

    def get_summary(self, max_length: int = 200) -> str:
        """Get a summary of the path step."""
        text = self.intent or self.description or self.content or self.summary or ""
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."

    # =========================================================================
    # CONVERSION (generic -- uses Entity._from_dto / to_dto)
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "EntityDTO | PathStepDTO") -> "PathStep":
        """Create PathStep from an EntityDTO or PathStepDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> "PathStepDTO":
        """Convert PathStep to domain-specific PathStepDTO."""

        from core.models.dto_helpers import domain_to_dto
        from core.models.pathways.path_step_dto import PathStepDTO

        return domain_to_dto(self, PathStepDTO)

    def __str__(self) -> str:
        return f"PathStep(uid={self.uid}, sequence={self.sequence}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"PathStep(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, sequence={self.sequence}, "
            f"mastery={self.current_mastery}/{self.mastery_threshold})"
        )
