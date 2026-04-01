"""
Exercise - Curriculum Exercise Domain Model
===============================================

Frozen dataclass for exercise instruction templates. Inherits from Curriculum
since exercises are curriculum-carrying entities (they contain learning metadata
and substance tracking).

The Educational Loop
---------------------
Exercise is the shared, reusable instruction template side of SKUEL's core loop:

    Exercise (shared template — this file)
        ↓  user submits work against it
    ExerciseSubmission (user-owned work product — EntityType.EXERCISE_SUBMISSION)
        ↓  FULFILLS_EXERCISE relationship in Neo4j
        ↓  auto-shared with teacher
    ExerciseReport (teacher's response — EntityType.EXERCISE_REPORT)

The Exercise belongs to curriculum (shared, admin/teacher-created).
The ExerciseSubmission is entirely user-owned the moment it is created.

Terminology
-----------
- Exercise = what the teacher/admin creates (instruction template, scope=ASSIGNED)
             or what a user creates for personal AI feedback (scope=PERSONAL)
- ExerciseSubmission = the user's work product in response to an Exercise
- ExerciseReport = the teacher's or AI's response to the ExerciseSubmission

Hierarchy:
    Entity (~29 fields)
    └── Curriculum(Entity) +21 fields
        └── Exercise(Curriculum) +9 fields

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

import json
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

from core.models.curriculum import Curriculum
from core.models.enums.entity_enums import EntityType
from core.models.enums.learning_enums import MasteryImpact
from core.models.enums.submissions_enums import EnrichmentMode, ExerciseScope, SubmissionModality

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.exercises.exercise_dto import ExerciseDTO


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
    - ExerciseReport = instructions + entry content -> LLM -> response

    Exercise-specific fields (12):
    - instructions: LLM prompt for processing
    - model: Which LLM to use
    - scope: ExerciseScope.PERSONAL (user's own template), ASSIGNED (teacher → group), or ASSESSMENT (formal test)
    - due_date: Due date for ASSIGNED/ASSESSMENT scope
    - group_uid: Target group for ASSIGNED scope
    - enrichment_mode: Processing strategy
    - context_notes: Reference materials
    - form_schema: Optional inline form definition for structured submissions
    - expected_modality: What submission format this exercise expects (FILE_UPLOAD or STRUCTURED_FORM)
    - mastery_impact: How aggressively completing this exercise advances mastery (MINOR → CERTIFICATION)
    - scoring_rubric: Assessment criteria with weights (required for ASSESSMENT scope)
    - pass_threshold: Minimum score (0.0-1.0) to pass an assessment
    """

    def __post_init__(self) -> None:
        """Force entity_type=EXERCISE, parse JSON form_schema, derive expected_modality."""
        super().__post_init__()
        object.__setattr__(self, "entity_type", EntityType.EXERCISE)
        # Neo4j stores form_schema as JSON string — parse on construction
        if isinstance(self.form_schema, str):
            try:
                parsed = json.loads(self.form_schema)
                object.__setattr__(self, "form_schema", tuple(parsed) if parsed else None)
            except (json.JSONDecodeError, TypeError):
                object.__setattr__(self, "form_schema", None)
        # Convert string enrichment_mode from DTO to enum
        if isinstance(self.enrichment_mode, str) and not isinstance(
            self.enrichment_mode, EnrichmentMode
        ):
            object.__setattr__(self, "enrichment_mode", EnrichmentMode(self.enrichment_mode))
        # Neo4j stores scoring_rubric as JSON string — parse on construction
        if isinstance(self.scoring_rubric, str):
            try:
                parsed_rubric = json.loads(self.scoring_rubric)
                object.__setattr__(
                    self, "scoring_rubric", tuple(parsed_rubric) if parsed_rubric else None
                )
            except (json.JSONDecodeError, TypeError):
                object.__setattr__(self, "scoring_rubric", None)
        # Auto-derive expected_modality from form_schema when not explicitly set
        if self.expected_modality is None:
            derived = (
                SubmissionModality.STRUCTURED_FORM
                if self.form_schema
                else SubmissionModality.FILE_UPLOAD
            )
            object.__setattr__(self, "expected_modality", derived)

    # =========================================================================
    # EXERCISE-SPECIFIC FIELDS (11)
    # =========================================================================
    exercise_number: int | None = None  # Human-readable exercise number (set in YAML, embedded in downloaded .md)
    instructions: str | None = None  # LLM prompt for processing
    model: str = "claude-sonnet-4-6"  # Which LLM to use
    scope: ExerciseScope = ExerciseScope.PERSONAL
    due_date: date | None = None
    group_uid: str | None = None  # Target group for ASSIGNED scope
    enrichment_mode: EnrichmentMode | None = None
    context_notes: tuple[str, ...] = ()  # Reference materials (tuple, not list — frozen)
    form_schema: tuple[dict[str, Any], ...] | None = None  # Inline form definition
    expected_modality: SubmissionModality | None = None  # Auto-derived in __post_init__
    mastery_impact: MasteryImpact = MasteryImpact.MODERATE  # How much mastery this exercise carries
    scoring_rubric: tuple[dict[str, Any], ...] | None = (
        None  # Assessment rubric: criteria, weights, pass threshold
    )
    pass_threshold: float | None = None  # Minimum score (0.0-1.0) to pass an assessment

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

    def has_inline_form(self) -> bool:
        """Check if this exercise expects structured form submissions."""
        return self.expected_modality == SubmissionModality.STRUCTURED_FORM

    def is_valid(self) -> bool:
        """Check if exercise has minimum required fields."""
        base_valid = bool(self.title and self.instructions and self.model)
        if self.scope == ExerciseScope.ASSIGNED:
            return base_valid and bool(self.group_uid)
        if self.scope == ExerciseScope.ASSESSMENT:
            return base_valid and bool(self.scoring_rubric)
        return base_valid

    def is_assigned(self) -> bool:
        """Check if this is a teacher-assigned exercise (scope == ASSIGNED)."""
        return self.scope == ExerciseScope.ASSIGNED

    def is_assessment(self) -> bool:
        """Check if this is a formal assessment/test (scope == ASSESSMENT)."""
        return self.scope == ExerciseScope.ASSESSMENT

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

        from core.models.exercises.exercise_dto import ExerciseDTO

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
