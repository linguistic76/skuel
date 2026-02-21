"""
ExerciseKu - Curriculum Exercise Domain Model
===============================================

Frozen dataclass for exercise instruction templates. Inherits from CurriculumKu
since exercises are curriculum-carrying entities (they contain learning metadata
and substance tracking).

Formerly 'Assignment' — renamed to Exercise for clarity:
- Exercise = what teacher creates (instruction template)
- Submission = what student uploads (KuType.SUBMISSION)

Pipeline role: EXERCISE stage (Exercise → Submit → Analyze → Review)

Hierarchy:
    KuBase (~29 fields)
    └── CurriculumKu(KuBase) +21 fields
        └── ExerciseKu(CurriculumKu) +7 fields

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from core.models.enums.ku_enums import KuType, ProjectScope
from core.models.ku.ku_curriculum import CurriculumKu

if TYPE_CHECKING:
    from core.models.ku.ku_dto import KuDTO


@dataclass(frozen=True)
class ExerciseKu(CurriculumKu):
    """
    Immutable domain model for exercise instruction templates (KuType.EXERCISE).

    An Exercise defines:
    1. **Instructions** — Plain text prompt for LLM feedback
    2. **Context** — Optional reference materials (like project knowledge)
    3. **Model** — Which LLM to use (user-selectable)

    Transparency principles:
    - Instructions are visible and editable (no black box)
    - User controls the model
    - Feedback = instructions + entry content -> LLM -> response

    Exercise-specific fields (7):
    - instructions: LLM prompt for processing
    - model: Which LLM to use
    - scope: PERSONAL or ASSIGNED (teacher assignment)
    - due_date: Due date for ASSIGNED scope
    - group_uid: Target group for ASSIGNED scope
    - enrichment_mode: Processing strategy
    - context_notes: Reference materials
    """

    def __post_init__(self) -> None:
        """Force ku_type=EXERCISE, then delegate to CurriculumKu."""
        if self.ku_type != KuType.EXERCISE:
            object.__setattr__(self, "ku_type", KuType.EXERCISE)
        super().__post_init__()

    # =========================================================================
    # EXERCISE-SPECIFIC FIELDS (7)
    # =========================================================================
    instructions: str | None = None  # LLM prompt for processing
    model: str = "claude-3-5-sonnet-20241022"  # Which LLM to use
    scope: ProjectScope = ProjectScope.PERSONAL
    due_date: date | None = None
    group_uid: str | None = None  # Target group for ASSIGNED scope
    enrichment_mode: str | None = None  # activity_tracking, idea_articulation, etc.
    context_notes: tuple[str, ...] = ()  # Reference materials (tuple, not list — frozen)

    # =========================================================================
    # EXERCISE-SPECIFIC METHODS
    # =========================================================================

    def get_feedback_prompt(self, entry_content: str) -> str:
        """
        Generate the complete prompt for LLM feedback.

        This is the FULL transparency — user can see exactly what goes to the LLM.

        Args:
            entry_content: The Ku entry text to analyze

        Returns:
            Complete prompt: instructions + context + entry
        """
        prompt_parts: list[str] = []

        prompt_parts.append("## Instructions")
        prompt_parts.append(self.instructions or "")
        prompt_parts.append("")

        if self.context_notes:
            prompt_parts.append("## Context Notes")
            prompt_parts.extend([f"- {note}" for note in self.context_notes])
            prompt_parts.append("")

        prompt_parts.append("## Entry")
        prompt_parts.append(entry_content)
        prompt_parts.append("")

        return "\n".join(prompt_parts)

    def is_valid(self) -> bool:
        """Check if exercise has minimum required fields."""
        base_valid = bool(self.title and self.instructions and self.model)
        if self.scope == ProjectScope.ASSIGNED:
            return base_valid and bool(self.group_uid)
        return base_valid

    def is_exercise(self) -> bool:
        """Check if this is a teacher-assigned exercise."""
        return self.scope == ProjectScope.ASSIGNED

    def is_overdue(self) -> bool:
        """Check if exercise is past due date."""
        if not self.due_date:
            return False
        return date.today() > self.due_date

    def get_summary(self, max_length: int = 200) -> str:
        """Get one-line summary of exercise."""
        text = self.instructions or self.description or self.title or ""
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."

    # =========================================================================
    # CONVERSION
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "KuDTO") -> "ExerciseKu":
        """Create ExerciseKu from a KuDTO."""
        return cls._from_dto(dto)

    def __str__(self) -> str:
        return f"ExerciseKu(uid={self.uid}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"ExerciseKu(uid='{self.uid}', title='{self.title}', "
            f"scope={self.scope}, model={self.model})"
        )
