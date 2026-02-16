"""
Assignment Models (Tier 2 + Tier 3)
====================================

"Ku is the heartbeat of SKUEL."

An Assignment is an instruction template for LLM processing of Ku content.
Like Claude/ChatGPT Projects — simple instruction set, optional context,
user-controlled model selection, transparent feedback generation.

Pipeline role: ASSIGN stage (Assign → Submit → Analyze → Review)

Three-tier type system:
- AssignmentDTO (Tier 2) — Mutable transfer object
- Assignment (Tier 3) — Immutable domain model

Works with any KuType, not just SUBMISSION. Provides the `instructions`
that drive AI processing of user-submitted content.

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any

from core.models.enums import Domain
from core.models.enums.ku_enums import ProcessorType, ProjectScope

# ============================================================================
# TIER 2 - DTO (Transfer Layer)
# ============================================================================


@dataclass
class AssignmentDTO:
    """
    Mutable data transfer object for Ku projects.

    Used for:
    - Moving data between service and persistence layers
    - Constructing projects before freezing into domain models
    - Database serialization/deserialization
    """

    uid: str
    user_uid: str
    name: str
    instructions: str
    model: str = "claude-3-5-sonnet-20241022"
    context_notes: list[str] = field(default_factory=list)
    domain: Domain | None = None
    is_active: bool = True
    # Assignment fields (ADR-040)
    scope: str = "personal"  # ProjectScope value
    due_date: date | None = None
    processor_type: str = "llm"  # ProcessorType value
    group_uid: str | None = None
    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "uid": self.uid,
            "user_uid": self.user_uid,
            "name": self.name,
            "instructions": self.instructions,
            "model": self.model,
            "context_notes": self.context_notes,
            "domain": self.domain.value if isinstance(self.domain, Enum) else self.domain,
            "is_active": self.is_active,
            "scope": self.scope,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "processor_type": self.processor_type,
            "group_uid": self.group_uid,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "metadata": self.metadata,
        }


# ============================================================================
# TIER 3 - Domain Model (Core Business Logic)
# ============================================================================


@dataclass(frozen=True)
class Assignment:
    """
    Immutable domain model for Ku projects (instruction templates).

    A Assignment defines:
    1. **Instructions** — Plain text prompt for LLM feedback
    2. **Context** — Optional reference materials (like project knowledge)
    3. **Model** — Which LLM to use (user-selectable)

    Transparency principles:
    - Instructions are visible and editable (no black box)
    - User controls the model
    - Feedback = instructions + entry content -> LLM -> response
    """

    uid: str
    user_uid: str
    name: str
    instructions: str
    model: str = "claude-3-5-sonnet-20241022"
    context_notes: list[str] = field(default_factory=list)
    domain: Domain | None = None

    is_active: bool = True
    # Assignment fields (ADR-040)
    scope: ProjectScope = ProjectScope.PERSONAL
    due_date: date | None = None
    processor_type: ProcessorType = ProcessorType.LLM
    group_uid: str | None = None
    # Timestamps
    created_at: datetime = None  # type: ignore[assignment]
    updated_at: datetime = None  # type: ignore[assignment]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialize timestamps with proper defaults."""
        now = datetime.now()
        if self.created_at is None:
            object.__setattr__(self, "created_at", now)
        if self.updated_at is None:
            object.__setattr__(self, "updated_at", now)

    def get_feedback_prompt(self, entry_content: str) -> str:
        """
        Generate the complete prompt for LLM feedback.

        This is the FULL transparency — user can see exactly what goes to the LLM.

        Args:
            entry_content: The Ku entry text to analyze

        Returns:
            Complete prompt: instructions + context + entry
        """
        prompt_parts = []

        prompt_parts.append("## Instructions")
        prompt_parts.append(self.instructions)
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
        """Check if project has minimum required fields."""
        base_valid = bool(self.name and self.instructions and self.model)
        if self.scope == ProjectScope.ASSIGNED:
            return base_valid and bool(self.group_uid)
        return base_valid

    def is_assignment(self) -> bool:
        """Check if this is a teacher-assigned project."""
        return self.scope == ProjectScope.ASSIGNED

    def is_overdue(self) -> bool:
        """Check if assignment is past due date."""
        if not self.due_date:
            return False
        return date.today() > self.due_date

    def get_summary(self) -> str:
        """Get one-line summary of project."""
        instruction_preview = (
            self.instructions[:80] + "..." if len(self.instructions) > 80 else self.instructions
        )
        return f"{self.name}: {instruction_preview}"


# ============================================================================
# CONVERSION FUNCTIONS
# ============================================================================


def assignment_dto_to_domain(dto: AssignmentDTO) -> Assignment:
    """Convert AssignmentDTO (Tier 2) to Assignment (Tier 3)."""
    return Assignment(
        uid=dto.uid,
        user_uid=dto.user_uid,
        name=dto.name,
        instructions=dto.instructions,
        model=dto.model,
        context_notes=dto.context_notes.copy() if dto.context_notes else [],
        domain=dto.domain,
        is_active=dto.is_active,
        scope=ProjectScope(dto.scope) if dto.scope else ProjectScope.PERSONAL,
        due_date=dto.due_date,
        processor_type=ProcessorType(dto.processor_type)
        if dto.processor_type
        else ProcessorType.LLM,
        group_uid=dto.group_uid,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
        metadata=dto.metadata.copy() if dto.metadata else {},
    )


def assignment_domain_to_dto(project: Assignment) -> AssignmentDTO:
    """Convert Assignment (Tier 3) to AssignmentDTO (Tier 2)."""
    return AssignmentDTO(
        uid=project.uid,
        user_uid=project.user_uid,
        name=project.name,
        instructions=project.instructions,
        model=project.model,
        context_notes=list(project.context_notes),
        domain=project.domain,
        is_active=project.is_active,
        scope=project.scope.value if isinstance(project.scope, ProjectScope) else project.scope,
        due_date=project.due_date,
        processor_type=project.processor_type.value
        if isinstance(project.processor_type, ProcessorType)
        else project.processor_type,
        group_uid=project.group_uid,
        created_at=project.created_at,
        updated_at=project.updated_at,
        metadata=dict(project.metadata),
    )


# ============================================================================
# FACTORY FUNCTION
# ============================================================================


def create_assignment(
    uid: str,
    user_uid: str,
    name: str,
    instructions: str,
    model: str = "claude-3-5-sonnet-20241022",
    context_notes: list[str] | None = None,
    domain: Domain | None = None,
    scope: ProjectScope = ProjectScope.PERSONAL,
    due_date: date | None = None,
    processor_type: ProcessorType = ProcessorType.LLM,
    group_uid: str | None = None,
) -> Assignment:
    """
    Factory function to create a new Assignment.

    Args:
        uid: Unique identifier
        user_uid: User who owns this project
        name: Display name
        instructions: Plain text instructions for LLM
        model: LLM model to use
        context_notes: Optional reference materials
        domain: Optional domain categorization
        scope: PERSONAL (default) or ASSIGNED (teacher assignment)
        due_date: Due date for ASSIGNED scope
        processor_type: LLM, HUMAN, or HYBRID
        group_uid: Target group UID for ASSIGNED scope

    Returns:
        Immutable Assignment instance
    """
    return Assignment(
        uid=uid,
        user_uid=user_uid,
        name=name,
        instructions=instructions,
        model=model,
        context_notes=context_notes or [],
        domain=domain,
        is_active=True,
        scope=scope,
        due_date=due_date,
        processor_type=processor_type,
        group_uid=group_uid,
    )
