"""
Exercise - Curriculum Exercise Domain Model
===============================================

Frozen dataclass for exercise instruction templates. Inherits from Curriculum
since exercises are curriculum-carrying entities (they contain learning metadata
and substance tracking).

Formerly 'Assignment' — renamed to Exercise for clarity:
- Exercise = what teacher creates (instruction template)
- Submission = what student uploads (EntityType.SUBMISSION)

Pipeline role: EXERCISE stage (Exercise → Submit → Analyze → Review)

Hierarchy:
    Entity (~29 fields)
    └── Curriculum(Entity) +21 fields
        └── Exercise(Curriculum) +7 fields

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from core.models.curriculum.curriculum import Curriculum
from core.models.enums.entity_enums import EntityType
from core.models.enums.reports_enums import ProjectScope

if TYPE_CHECKING:
    from core.models.curriculum.exercise_dto import ExerciseDTO
    from core.models.entity_dto import EntityDTO


@dataclass(frozen=True)
class Exercise(Curriculum):
    """
    Immutable domain model for exercise instruction templates (EntityType.EXERCISE).

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
        """Force ku_type=EXERCISE (must run after super() so Curriculum's override doesn't win)."""
        super().__post_init__()
        object.__setattr__(self, "ku_type", EntityType.EXERCISE)

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
            entry_content: The report entry text to analyze

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
    def from_dto(cls, dto: "EntityDTO | ExerciseDTO") -> "Exercise":  # type: ignore[override]
        """Create Exercise from an EntityDTO or ExerciseDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> "ExerciseDTO":  # type: ignore[override]
        """Convert Exercise to domain-specific ExerciseDTO."""
        import dataclasses
        from typing import Any

        from core.models.curriculum.exercise_dto import ExerciseDTO

        dto_field_names = {f.name for f in dataclasses.fields(ExerciseDTO)}
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
        return ExerciseDTO(**kwargs)

    def __str__(self) -> str:
        return f"Exercise(uid={self.uid}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"Exercise(uid='{self.uid}', title='{self.title}', "
            f"scope={self.scope}, model={self.model})"
        )
