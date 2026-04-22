"""
RevisedExercise - Four-Phase Learning Loop Domain Model
========================================================

Frozen dataclass for teacher-created revised exercise instructions that
address specific feedback gaps. Part of the four-phase learning loop:

    Exercise v1 → UserEntry v1 → ExerciseReport v1
                                      ↓
                                RevisedExercise v2 → UserEntry v2 → ...

PathStep is the curriculum anchor, linked via ``(PathStep)-[:RELATED_TO]->(Exercise)``
(denormalized as ``Exercise.path_step_uid`` for PERSONAL scope).

RevisedExercise is teacher-owned but student-targeted: the teacher creates
targeted revision instructions based on feedback, and the student submits
against them.

Hierarchy:
    Entity (~19 fields)
    └── UserOwnedEntity(Entity) +2 fields (user_uid, priority)
        └── RevisedExercise(UserOwnedEntity) +12 fields

See: /docs/architecture/LEARNING_LOOP_ARCHITECTURE.md
"""

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.models.enums.entity_enums import EntityType
from core.models.enums.learning_enums import FeedbackCategory
from core.models.enums.user_entry_enums import SubmissionModality
from core.models.user_owned_entity import UserOwnedEntity

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.exercises.revised_exercise_dto import RevisedExerciseDTO


@dataclass(frozen=True)
class FeedbackPoint:
    """
    A single typed feedback point: category + free-text detail.

    The category enables pattern tracking (what *kind* of gap was identified).
    The detail provides the specific, actionable feedback for the student.
    """

    category: FeedbackCategory
    detail: str

    def to_dict(self) -> dict[str, str]:
        """Serialize for Neo4j JSON storage."""
        return {"category": self.category.value, "detail": self.detail}


@dataclass(frozen=True)
class RevisedExercise(UserOwnedEntity):
    """
    Immutable domain model for revised exercise instructions (EntityType.REVISED_EXERCISE).

    A RevisedExercise defines targeted revision instructions that address specific
    feedback gaps from an ExerciseReport entity. It links back to:
    - The original Exercise it revises (via REVISES_EXERCISE)
    - The ExerciseReport it responds to (via RESPONDS_TO_REPORT)
    - The UserEntry that was evaluated (via submission_uid)

    Fields (12 exercise-specific):
    - revision_number: Which revision iteration (1, 2, 3, ...)
    - original_exercise_uid: UID of the original Exercise being revised
    - report_uid: UID of the ExerciseReport this addresses
    - submission_uid: UID of the UserEntry that was evaluated
    - student_uid: UID of the student this revision targets
    - instructions: Plain text instructions for the revision
    - model: Which LLM to use for feedback generation
    - context_notes: Reference materials (tuple, not list — frozen)
    - feedback_points: Typed feedback points (FeedbackCategory + detail)
    - revision_rationale: Why this revision was created
    - expected_modality: What submission format to expect (inherited from original Exercise)
    """

    def __post_init__(self) -> None:
        """Force entity_type=REVISED_EXERCISE, parse JSON feedback_points."""
        object.__setattr__(self, "entity_type", EntityType.REVISED_EXERCISE)
        # Neo4j stores feedback_points as JSON string — parse on construction
        if isinstance(self.feedback_points, str):
            object.__setattr__(
                self, "feedback_points", _parse_feedback_points_json(self.feedback_points)
            )
        # Neo4j stores expected_modality as string — parse on construction
        if isinstance(self.expected_modality, str):
            try:
                object.__setattr__(
                    self, "expected_modality", SubmissionModality(self.expected_modality)
                )
            except ValueError:
                object.__setattr__(self, "expected_modality", None)
        super().__post_init__()

    # =========================================================================
    # REVISED EXERCISE-SPECIFIC FIELDS (12)
    # =========================================================================
    revision_number: int = 1
    original_exercise_uid: str | None = None
    report_uid: str | None = None
    submission_uid: str | None = None
    student_uid: str | None = None
    instructions: str | None = None
    model: str = "claude-sonnet-4-6"
    context_notes: tuple[str, ...] = ()
    feedback_points: (
        tuple[FeedbackPoint, ...] | tuple[Any, ...]
    ) = ()  # boundary: Neo4j JSON string parsed in __post_init__
    revision_rationale: str | None = None
    expected_modality: SubmissionModality | None = None

    # =========================================================================
    # METHODS
    # =========================================================================

    def get_feedback_prompt(self, entry_content: str) -> str:
        """
        Generate the complete prompt for LLM feedback on revised submission.

        Args:
            entry_content: The student's revised submission text

        Returns:
            Complete prompt: instructions + context + addressed points + entry
        """
        prompt_parts: list[str] = []

        prompt_parts.append("## Revision Instructions")
        prompt_parts.append(self.instructions or "")
        prompt_parts.append("")

        if self.feedback_points:
            prompt_parts.append("## Feedback Points Being Addressed")
            prompt_parts.extend(
                f"- [{point.category.get_label()}] {point.detail}" for point in self.feedback_points
            )
            prompt_parts.append("")

        if self.context_notes:
            prompt_parts.append("## Context Notes")
            prompt_parts.extend([f"- {note}" for note in self.context_notes])
            prompt_parts.append("")

        if self.revision_rationale:
            prompt_parts.append("## Revision Rationale")
            prompt_parts.append(self.revision_rationale)
            prompt_parts.append("")

        prompt_parts.append("## Revised Submission")
        prompt_parts.append(entry_content)
        prompt_parts.append("")

        return "\n".join(prompt_parts)

    def is_valid(self) -> bool:
        """Check if revised exercise has minimum required fields."""
        return bool(
            self.title
            and self.instructions
            and self.original_exercise_uid
            and self.report_uid
            and self.student_uid
            and self.submission_uid
        )

    # =========================================================================
    # CONVERSION
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "EntityDTO | RevisedExerciseDTO") -> "RevisedExercise":
        """Create RevisedExercise from an EntityDTO or RevisedExerciseDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> "RevisedExerciseDTO":
        """Convert RevisedExercise to domain-specific RevisedExerciseDTO."""

        from core.models.dto_helpers import domain_to_dto
        from core.models.exercises.revised_exercise_dto import RevisedExerciseDTO

        return domain_to_dto(self, RevisedExerciseDTO)

    def __str__(self) -> str:
        return f"RevisedExercise(uid={self.uid}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"RevisedExercise(uid='{self.uid}', title='{self.title}', "
            f"revision_number={self.revision_number}, student_uid={self.student_uid})"
        )


def _parse_feedback_points_json(raw: str) -> tuple[FeedbackPoint, ...]:
    """Parse feedback_points from Neo4j JSON string.

    Handles both new format (list of {category, detail} dicts) and
    legacy format (list of plain strings, assigned ACCURACY default).
    """
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return ()

    if not isinstance(parsed, list):
        return ()

    points: list[FeedbackPoint] = []
    for item in parsed:
        if isinstance(item, dict) and "category" in item and "detail" in item:
            try:
                points.append(
                    FeedbackPoint(
                        category=FeedbackCategory(item["category"]),
                        detail=str(item["detail"]),
                    )
                )
            except ValueError:
                continue
        elif isinstance(item, str):
            # Legacy: plain string → default category
            points.append(FeedbackPoint(category=FeedbackCategory.ACCURACY, detail=item))
    return tuple(points)
