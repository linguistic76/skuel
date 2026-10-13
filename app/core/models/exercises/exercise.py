"""
Exercise - Applied Knowledge Domain Model
==========================================

Exercise is APPLIED KNOWLEDGE — the instruction template that operationalises
PathStep content into concrete practice. PathStep is knowledge; Exercise is how
that knowledge is practised. This hierarchy is fundamental to SKUEL:

    (PathStep)-[:HAS_EXERCISE]->(Exercise)

PathStep and Exercise are NOT peers. Exercise is subordinate to PathStep in the
same structural relationship as a sub-goal under a parent goal (Goal.fulfills_goal_uid).
The membership lives in the edge: the PathStep's vault file lists its exercises
(``exercise_uids``), and the content-vault sync writes ``HAS_EXERCISE`` from them.

Exercise inherits from Curriculum because it shares substance tracking, learning
metadata, and confidence fields with PathStep and LearningPath — not because it
occupies the same structural tier.

The Educational Loop
---------------------
Exercise initiates the four-phase learning loop as the applied-knowledge anchor:

    Exercise (shared template — this file)
        ↓  user submits work against it
    UserEntry (user-owned work product — EntityType.USER_ENTRY)
        ↓  FULFILLS_EXERCISE relationship in Neo4j
        ↓  auto-shared with teacher
    EntryReport (teacher's response — EntityType.ENTRY_REPORT)

The Exercise belongs to curriculum: authored only in the content vault, owned by no
user, and naming in its file the teacher who reviews work on it (ADR-091 S2-S4).
The UserEntry is entirely user-owned the moment it is created.

Terminology
-----------
- Exercise = the instruction template a vault file declares
- UserEntry = the user's work product in response to an Exercise (ADR-054)
- EntryReport = the teacher's or AI's response to the UserEntry

Hierarchy:
    Entity (~29 fields)
    └── Curriculum(Entity) +21 fields
        └── Exercise(Curriculum) + exercise-specific fields

See: /docs/decisions/ADR-091-one-door-for-curriculum.md
"""

import json
from dataclasses import dataclass, field
from datetime import date
from typing import TYPE_CHECKING, Any

from core.models.curriculum import Curriculum
from core.models.enums.entity_enums import EntityType
from core.models.enums.learning_enums import MasteryImpact
from core.models.enums.user_entry_enums import EnrichmentMode, ExerciseScope, SubmissionModality
from core.utils.timestamp_helpers import today_in
from core.utils.zone_context import current_zone

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
    - EntryReport = instructions + entry content -> LLM -> response

    Exercise-specific fields:
    - path_step_uid: Optional reverse anchor a vault file may author beside the step's
      ``HAS_EXERCISE`` edge (the edge is the membership)
    - exercise_number: Human-readable exercise number (embedded in the downloaded .md)
    - instructions: LLM prompt for processing
    - model: Which LLM to use
    - scope: ExerciseScope.CURRICULUM — the one scope, the vault's
    - due_date: Optional due date
    - enrichment_mode: Processing strategy
    - context_notes: Reference materials
    - form_schema: Optional inline form definition for structured submissions
    - expected_modality: What submission format this exercise expects (FILE_UPLOAD or STRUCTURED_FORM)
    - mastery_impact: How aggressively completing this exercise advances mastery (MINOR → CERTIFICATION)
    - scoring_rubric: Assessment criteria with weights
    - pass_threshold: Minimum score (0.0-1.0) to pass an assessment
    """

    # Honest leaf identity (G6): defaults to its own type; __post_init__
    # rejects a mismatch instead of silently correcting it.
    entity_type: EntityType = field(default=EntityType.EXERCISE, kw_only=True)

    def __post_init__(self) -> None:
        """Validate entity_type=EXERCISE, parse JSON form_schema, derive expected_modality."""
        super().__post_init__()
        if self.entity_type != EntityType.EXERCISE:
            raise ValueError(
                f"Exercise constructed with entity_type={self.entity_type!r} "
                f"(uid={self.uid!r}) — the writer persisted a wrong type (G6)"
            )
        # Neo4j stores form_schema as JSON string — parse on construction
        if isinstance(self.form_schema, str):
            try:
                parsed = json.loads(self.form_schema)
                object.__setattr__(self, "form_schema", tuple(parsed) if parsed else None)
            except json.JSONDecodeError, TypeError:
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
            except json.JSONDecodeError, TypeError:
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
    # EXERCISE-SPECIFIC FIELDS
    # =========================================================================
    path_step_uid: str | None = None  # Optional reverse anchor, authored in the vault file
    exercise_number: int | None = (
        None  # Human-readable exercise number (set in YAML, embedded in downloaded .md)
    )
    instructions: str | None = None  # LLM prompt for processing
    model: str = "claude-sonnet-4-6"  # Which LLM to use
    scope: ExerciseScope = ExerciseScope.CURRICULUM
    due_date: date | None = None
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
        """Check if exercise has minimum required fields: a title, instructions and a model."""
        return bool(self.title and self.instructions and self.model)

    def is_overdue(self) -> bool:
        """Check if exercise is past due date."""
        if not self.due_date:
            return False
        return today_in(current_zone()) > self.due_date

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
    def from_dto(cls, dto: EntityDTO | ExerciseDTO) -> Exercise:
        """Create Exercise from an EntityDTO or ExerciseDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> ExerciseDTO:
        """Convert Exercise to domain-specific ExerciseDTO."""

        from core.models.dto_helpers import domain_to_dto
        from core.models.exercises.exercise_dto import ExerciseDTO

        return domain_to_dto(self, ExerciseDTO)

    def __str__(self) -> str:
        return f"Exercise(uid={self.uid}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"Exercise(uid='{self.uid}', title='{self.title}', "
            f"scope={self.scope}, model={self.model})"
        )
