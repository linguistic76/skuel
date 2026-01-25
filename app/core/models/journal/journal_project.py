"""
Journal Project Models
======================

Three-tier type system for Journal Projects.

A Journal Project is like Claude/ChatGPT Projects:
- Simple instruction set (visible, editable text)
- Optional context notes (reference materials)
- User controls LLM model selection
- Transparent feedback generation

Example use cases:
- Daily Reflection: "Read my journal and ask me one clarifying question about emotions"
- Principle Extraction: "Identify recurring values in my writing"
- Practice Log: "Analyze my meditation notes for progress patterns"
- Assignment Review: "Provide constructive feedback on this learning artifact"
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from core.models.shared_enums import Domain

# ============================================================================
# TIER 2 - DTO (Transfer Layer)
# ============================================================================


@dataclass
class JournalProjectDTO:
    """
    Mutable data transfer object for journal projects.

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
    context_notes: list[str] = (field(default_factory=list),)
    domain: Domain | None = (None,)
    is_active: bool = True
    created_at: datetime = (field(default_factory=datetime.now),)
    updated_at: datetime = (field(default_factory=datetime.now),)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage"""
        return {
            "uid": self.uid,
            "user_uid": self.user_uid,
            "name": self.name,
            "instructions": self.instructions,
            "model": self.model,
            "context_notes": self.context_notes,
            "domain": self.domain.value if isinstance(self.domain, Enum) else self.domain,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "metadata": self.metadata,
        }


# ============================================================================
# TIER 3 - Domain Model (Core Business Logic)
# ============================================================================


@dataclass(frozen=True)
class JournalProjectPure:
    """
    Immutable domain model for journal projects.

    A journal project defines:
    1. **Instructions** - Plain text prompt for LLM feedback
    2. **Context** - Optional reference materials (like project knowledge)
    3. **Model** - Which LLM to use (user-selectable)

    Transparency principles:
    - Instructions are visible and editable (no black box)
    - User controls the model
    - Feedback = instructions + entry content → LLM → response
    - Simple, clear, no hidden magic

    Examples:
        # Daily reflection project
        project = JournalProjectPure(
            uid="jp.daily_reflection",
            user_uid="user.mike",
            name="Daily Reflection",
            instructions="Read my journal entry and ask me one clarifying question about the emotions I describe.",
            model="claude-3-5-sonnet-20241022"
        )

        # Principle extraction project
        project = JournalProjectPure(
            uid="jp.principles",
            user_uid="user.mike",
            name="Principle Mining",
            instructions="Identify recurring values and beliefs in my writing. Surface patterns I might not see.",
            context_notes=["My core principles document", "Past reflections"]
        )
    """

    uid: str
    user_uid: str
    name: str
    instructions: str
    model: str = "claude-3-5-sonnet-20241022"
    context_notes: list[str] = (field(default_factory=list),)
    domain: Domain | None = (None,)

    is_active: bool = True
    created_at: datetime = (field(default_factory=datetime.now),)
    updated_at: datetime = (field(default_factory=datetime.now),)
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_feedback_prompt(self, entry_content: str) -> str:
        """
        Generate the complete prompt for LLM feedback.

        This is the FULL transparency - user can see exactly what goes to the LLM.

        Args:
            entry_content: The journal entry text

        Returns:
            Complete prompt: instructions + context + entry
        """
        prompt_parts = []

        # Add instructions
        prompt_parts.append("## Instructions")
        prompt_parts.append(self.instructions)
        prompt_parts.append("")

        # Add context if available
        if self.context_notes:
            prompt_parts.append("## Context Notes")
            prompt_parts.extend([f"- {note}" for note in self.context_notes])
            prompt_parts.append("")

        # Add journal entry
        prompt_parts.append("## Journal Entry")
        prompt_parts.append(entry_content)
        prompt_parts.append("")

        return "\n".join(prompt_parts)

    def is_valid(self) -> bool:
        """Check if project has minimum required fields"""
        return bool(self.name and self.instructions and self.model)

    def get_summary(self) -> str:
        """Get one-line summary of project"""
        instruction_preview = (
            self.instructions[:80] + "..." if len(self.instructions) > 80 else self.instructions
        )
        return f"{self.name}: {instruction_preview}"


# ============================================================================
# CONVERSION FUNCTIONS
# ============================================================================


def dto_to_pure(dto: JournalProjectDTO) -> JournalProjectPure:
    """Convert DTO to immutable domain model"""
    return JournalProjectPure(
        uid=dto.uid,
        user_uid=dto.user_uid,
        name=dto.name,
        instructions=dto.instructions,
        model=dto.model,
        context_notes=dto.context_notes.copy() if dto.context_notes else [],
        domain=dto.domain,
        is_active=dto.is_active,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
        metadata=dto.metadata.copy() if dto.metadata else {},
    )


def pure_to_dto(pure: JournalProjectPure) -> JournalProjectDTO:
    """Convert domain model to mutable DTO"""
    return JournalProjectDTO(
        uid=pure.uid,
        user_uid=pure.user_uid,
        name=pure.name,
        instructions=pure.instructions,
        model=pure.model,
        context_notes=list(pure.context_notes),
        domain=pure.domain,
        is_active=pure.is_active,
        created_at=pure.created_at,
        updated_at=pure.updated_at,
        metadata=dict(pure.metadata),
    )


# ============================================================================
# FACTORY FUNCTIONS
# ============================================================================


def create_journal_project(
    uid: str,
    user_uid: str,
    name: str,
    instructions: str,
    model: str = "claude-3-5-sonnet-20241022",
    context_notes: list[str] | None = None,
    domain: Domain | None = None,
) -> JournalProjectPure:
    """
    Factory function to create a new journal project.

    Args:
        uid: Unique identifier (e.g., "jp.daily_reflection"),
        user_uid: User who owns this project,
        name: Display name,
        instructions: Plain text instructions for LLM,
        model: LLM model to use,
        context_notes: Optional reference materials,
        domain: Optional domain categorization

    Returns:
        Immutable JournalProjectPure instance
    """
    return JournalProjectPure(
        uid=uid,
        user_uid=user_uid,
        name=name,
        instructions=instructions,
        model=model,
        context_notes=context_notes or [],
        domain=domain,
        is_active=True,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        metadata={},
    )
