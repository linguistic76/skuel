"""
RevisedExercise - Five-Phase Learning Loop Domain Model
========================================================

Frozen dataclass for teacher-created revised exercise instructions that
address specific feedback gaps. Part of the five-phase learning loop:

    Article → Exercise v1 → Submission v1 → SubmissionFeedback v1
                                                  ↓
                                            RevisedExercise v2 → Submission v2 → ...

RevisedExercise is teacher-owned but student-targeted: the teacher creates
targeted revision instructions based on feedback, and the student submits
against them.

Hierarchy:
    Entity (~19 fields)
    └── UserOwnedEntity(Entity) +2 fields (user_uid, priority)
        └── RevisedExercise(UserOwnedEntity) +9 fields

See: /docs/architecture/FEEDBACK_ARCHITECTURE.md
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.models.enums.entity_enums import EntityType
from core.models.user_owned_entity import UserOwnedEntity

if TYPE_CHECKING:
    from core.models.curriculum.revised_exercise_dto import RevisedExerciseDTO
    from core.models.entity_dto import EntityDTO


@dataclass(frozen=True)
class RevisedExercise(UserOwnedEntity):
    """
    Immutable domain model for revised exercise instructions (EntityType.REVISED_EXERCISE).

    A RevisedExercise defines targeted revision instructions that address specific
    feedback gaps from a SubmissionFeedback entity. It links back to:
    - The original Exercise it revises (via REVISES_EXERCISE)
    - The SubmissionFeedback it responds to (via RESPONDS_TO_FEEDBACK)

    Fields (9 exercise-specific):
    - revision_number: Which revision iteration (1, 2, 3, ...)
    - original_exercise_uid: UID of the original Exercise being revised
    - feedback_uid: UID of the SubmissionFeedback this addresses
    - student_uid: UID of the student this revision targets
    - instructions: Plain text instructions for the revision
    - model: Which LLM to use for feedback generation
    - context_notes: Reference materials (tuple, not list — frozen)
    - feedback_points_addressed: Specific feedback points this revision targets
    - revision_rationale: Why this revision was created
    """

    def __post_init__(self) -> None:
        """Force entity_type=REVISED_EXERCISE."""
        object.__setattr__(self, "entity_type", EntityType.REVISED_EXERCISE)
        super().__post_init__()

    # =========================================================================
    # REVISED EXERCISE-SPECIFIC FIELDS (9)
    # =========================================================================
    revision_number: int = 1
    original_exercise_uid: str | None = None
    feedback_uid: str | None = None
    student_uid: str | None = None
    instructions: str | None = None
    model: str = "claude-sonnet-4-6"
    context_notes: tuple[str, ...] = ()
    feedback_points_addressed: tuple[str, ...] = ()
    revision_rationale: str | None = None

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

        if self.feedback_points_addressed:
            prompt_parts.append("## Feedback Points Being Addressed")
            prompt_parts.extend([f"- {point}" for point in self.feedback_points_addressed])
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
            and self.feedback_uid
            and self.student_uid
        )

    # =========================================================================
    # CONVERSION
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "EntityDTO | RevisedExerciseDTO") -> "RevisedExercise":  # type: ignore[override]
        """Create RevisedExercise from an EntityDTO or RevisedExerciseDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> "RevisedExerciseDTO":  # type: ignore[override]
        """Convert RevisedExercise to domain-specific RevisedExerciseDTO."""
        import dataclasses
        from typing import Any

        from core.models.curriculum.revised_exercise_dto import RevisedExerciseDTO

        dto_field_names = {f.name for f in dataclasses.fields(RevisedExerciseDTO)}
        kwargs: dict[str, Any] = {}
        for f in dataclasses.fields(self):
            if f.name.startswith("_"):
                continue
            if f.name not in dto_field_names:
                continue
            value = getattr(self, f.name)
            if isinstance(value, tuple):
                value = list(value)
            kwargs[f.name] = value
        return RevisedExerciseDTO(**kwargs)

    def __str__(self) -> str:
        return f"RevisedExercise(uid={self.uid}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"RevisedExercise(uid='{self.uid}', title='{self.title}', "
            f"revision_number={self.revision_number}, student_uid={self.student_uid})"
        )
