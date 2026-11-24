"""
PathStep - THE Curriculum Content Entity
=========================================

Frozen dataclass for path step entities (EntityType.PATH_STEP).
A PathStep is THE unit for learning — it composes atomic Kus into coherent
learning content and sits within a LearningPath.

3-level hierarchy: LearningPath -> PathStep -> Ku

Inherits common fields from Entity via Curriculum. Adds 9 path-step-specific fields:
- Intent (1): intent
- NOUS membership (2): nous, nous_subtopic
- Knowledge references (1): knowledge_uids (graph-native, reconstructed from CONTAINS_KNOWLEDGE)
- Path relationship (2): learning_path_uid, sequence
- Mastery (3): mastery_threshold, estimated_hours, step_difficulty

Key relationships:
- USES_KU -> Ku (content composition)
- CONTAINS_KNOWLEDGE -> Ku (knowledge reference)
- TRAINS_KU -> Ku (learning objectives)
- ORGANIZES -> PathStep (emergent MOC identity)
- Activity Templates: HAS_TASK_TEMPLATE, HAS_HABIT_TEMPLATE, … (a learner's own
  Activities spawn from them on engagement and carry ``source_path_step_uid``)
- Learning states: VIEWED, IN_PROGRESS, MASTERED, BOOKMARKED (on user relationships)

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, ClassVar

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
    for intent, knowledge references, path relationship, and authored mastery metadata.
    """

    # Node state: properties the node carries that the class does not declare
    # (core/models/node_state.py):
    # ``hub_score``, the cached degree centrality (``compute_hub_scores``, read by the
    # foundational-knowledge query).
    NODE_STATE: ClassVar[frozenset[str]] = frozenset({"hub_score"})

    # Activity-instance keys a step names no field for, each with the template key an
    # author who writes it means; the write gate refuses the file and suggests that key
    # (``nearest_field_names``). A step names Activities at the template grain only — a
    # template is nobody's, and a learner who engages the step gets their own Activity
    # from it — so no step names one user's Activity on shared curriculum.
    SUGGESTED_KEYS: ClassVar[Mapping[str, str]] = MappingProxyType(
        {
            "habit_uids": "habit_template_uids",
            "task_uids": "task_template_uids",
            "event_uids": "event_template_uids",
            "goal_uids": "goal_template_uids",
            "principle_uids": "principle_template_uids",
            "choice_uids": "choice_template_uids",
        }
    )

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
    # Authored metadata on the shared step, the same for every learner — not
    # learner state. A learner's mastery of a step is their own
    # (User)-[:MASTERED]->(PathStep) edge (UserContext.mastered_path_steps).
    mastery_threshold: float = 0.7  # Target mastery level the author sets
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
    def from_dto(cls, dto: EntityDTO | PathStepDTO) -> PathStep:
        """Create PathStep from an EntityDTO or PathStepDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> PathStepDTO:
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
            f"mastery_threshold={self.mastery_threshold})"
        )
