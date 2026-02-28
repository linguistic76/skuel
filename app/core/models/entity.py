"""
Entity - Common Fields and Methods for All Knowledge Types
==========================================================

Base frozen dataclass shared by all 15 EntityType domain subclasses.
Contains ~19 fields genuinely common to every manifestation of knowledge:
Identity (5), Content (4), Status (1), Sharing (1), Meta (6), Embedding (3).

User ownership fields (user_uid, priority) live on UserOwnedEntity — the
intermediate class for user-owned types (Activity Domains, Submissions, LifePath).

Learning metadata, substance tracking, and curriculum-specific methods live
on Curriculum (the intermediate class for curriculum-carrying types).

Hierarchy:
    Entity (~19 fields)
    ├── UserOwnedEntity(Entity) +2 fields (user_uid, priority)
    │   ├── Task, Goal, Habit, Event, Choice, Principle
    │   ├── Submission → Journal, AiFeedback, Feedback
    │   └── LifePath
    ├── Curriculum(Entity) → LearningStep, LearningPath, Exercise
    └── Resource(Entity)

See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
"""

import dataclasses
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar, Self

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO

from core.models.enums import Domain
from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.enums.metadata_enums import Visibility


@dataclass(frozen=True)
class Entity:
    """
    Base frozen dataclass for all knowledge types.

    Contains ~19 fields shared by every EntityType manifestation:
    Identity (5), Content (4), Status (1), Sharing (1), Meta (6), Embedding (3).

    User ownership (user_uid, priority) lives on UserOwnedEntity.
    Learning metadata and substance tracking live on Curriculum.

    Domain-specific subclasses inherit from Entity (shared types) or
    UserOwnedEntity (user-owned types) and add their own fields.
    """

    # Neo4j node label — all EntityType subclasses share the :Entity label
    _neo4j_label: ClassVar[str] = "Entity"

    # =========================================================================
    # IDENTITY
    # =========================================================================
    uid: str
    title: str
    ku_type: EntityType = EntityType.KU
    parent_ku_uid: str | None = None  # Derivation chain — what Entity this was based on
    domain: Domain = Domain.KNOWLEDGE
    created_by: str | None = None

    # =========================================================================
    # CONTENT
    # =========================================================================
    content: str | None = None  # Body text (submissions, AI output, feedback)
    summary: str = ""  # Brief description
    description: str | None = None  # Extended description (used by all activity domains)
    word_count: int = 0

    # =========================================================================
    # STATUS
    # =========================================================================
    status: EntityStatus = None  # type: ignore[assignment]  # Set in __post_init__

    # =========================================================================
    # SHARING
    # =========================================================================
    visibility: Visibility = None  # type: ignore[assignment]  # Set in __post_init__

    # =========================================================================
    # META
    # =========================================================================
    tags: tuple[str, ...] = ()
    created_at: datetime = None  # type: ignore[assignment]
    updated_at: datetime = None  # type: ignore[assignment]
    metadata: dict[str, Any] = None  # type: ignore[assignment]

    # Embedding fields for Neo4j GenAI vector search
    embedding: tuple[float, ...] | None = None
    embedding_model: str | None = None
    embedding_updated_at: datetime | None = None  # type: ignore[assignment]

    # =========================================================================
    # INITIALIZATION
    # =========================================================================

    def __post_init__(self) -> None:
        """Set conditional defaults based on ku_type."""
        now = datetime.now()

        if self.created_at is None:
            object.__setattr__(self, "created_at", now)
        if self.updated_at is None:
            object.__setattr__(self, "updated_at", now)
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})

        # Default status from EntityType (type-aware)
        if self.status is None:
            object.__setattr__(self, "status", self.ku_type.default_status())

        # Default visibility: PUBLIC for shared types (Entity direct children).
        # UserOwnedEntity overrides to PRIVATE before calling super().__post_init__().
        if self.visibility is None:
            object.__setattr__(self, "visibility", Visibility.PUBLIC)

        # Compute word_count from content if not set
        if self.word_count == 0 and self.content:
            object.__setattr__(self, "word_count", len(self.content.split()))

    # =========================================================================
    # USER OWNERSHIP COMPATIBILITY
    # Properties for backward compatibility with code accessing user_uid/priority
    # on any Entity subclass. UserOwnedEntity overrides with real fields.
    # =========================================================================

    @property
    def user_uid(self) -> str | None:
        """Shared types have no owner. UserOwnedEntity overrides with a field."""
        return None

    @property
    def priority(self) -> str | None:
        """Shared types have no priority. UserOwnedEntity overrides with a field."""
        return None

    @property
    def is_user_owned(self) -> bool:
        """Check if this entity has an owner. Overridden by UserOwnedEntity."""
        return False

    @property
    def is_derived(self) -> bool:
        """Check if this entity was derived from another entity."""
        return self.parent_ku_uid is not None

    # =========================================================================
    # STATUS / PROCESSING
    # =========================================================================

    @property
    def is_completed(self) -> bool:
        return self.status == EntityStatus.COMPLETED

    @property
    def is_processing(self) -> bool:
        return self.status == EntityStatus.PROCESSING

    @property
    def is_failed(self) -> bool:
        return self.status == EntityStatus.FAILED

    @property
    def is_draft(self) -> bool:
        return self.status == EntityStatus.DRAFT

    @property
    def is_archived(self) -> bool:
        return self.status == EntityStatus.ARCHIVED

    # =========================================================================
    # SHARING
    # =========================================================================

    def is_shareable(self) -> bool:
        """Only completed entities can be shared (quality control)."""
        return self.status == EntityStatus.COMPLETED

    def can_view(self, _viewer_uid: str, _shared_user_uids: set[str] | None = None) -> bool:
        """
        Check if a user can view this entity.

        Base implementation checks visibility only (no user ownership).
        UserOwnedEntity overrides with full ownership + sharing logic.
        Shared types (Curriculum, Resource) are always PUBLIC.
        """
        return self.visibility == Visibility.PUBLIC

    # =========================================================================
    # KNOWLEDGE CARRIER PROTOCOL
    # =========================================================================

    def knowledge_relevance(self) -> float:
        """KU IS knowledge — always returns 1.0."""
        return 1.0

    def get_knowledge_uids(self) -> tuple[str, ...]:
        """KU IS knowledge — returns its own UID."""
        return (self.uid,)

    # =========================================================================
    # GENERIC BUSINESS LOGIC (applies to all entity types)
    # =========================================================================

    def has_tag(self, tag: str) -> bool:
        return tag.lower() in [t.lower() for t in self.tags]

    def matches_domain(self, domain: Domain) -> bool:
        return self.domain == domain

    def is_recent(self, days: int = 7) -> bool:
        if not self.created_at:
            return False
        return (datetime.now() - self.created_at).days <= days

    def is_updated(self) -> bool:
        if not self.created_at or not self.updated_at:
            return False
        return self.updated_at > self.created_at

    # =========================================================================
    # SUBSTANCE / REVIEW STUBS
    # Non-curriculum types carry no substance and never need review.
    # Curriculum overrides these with real implementations.
    # =========================================================================

    def substance_score(self, _force_recalculate: bool = False) -> float:
        """Non-curriculum types carry no substance. Override on Curriculum."""
        return 0.0

    def needs_review(self) -> bool:
        """Non-curriculum types never need spaced repetition review."""
        return False

    # =========================================================================
    # DISPLAY
    # =========================================================================

    @property
    def name(self) -> str:
        """Alias for title — backward compat for code referencing old domain models."""
        return self.title

    @property
    def key_topics(self) -> tuple[str, ...]:
        """Key topics — alias for tags."""
        return self.tags

    # =========================================================================
    # CONVERSION — DISPATCHER + GENERIC EXTRACTION
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "EntityDTO") -> "Entity":
        """
        Dispatch to appropriate domain subclass based on dto.ku_type.

        Routes EntityType.TASK → Task, EntityType.GOAL → Goal, etc.
        Falls back to Curriculum for unmapped types.
        """
        from core.models.entity_types import ENTITY_TYPE_CLASS_MAP

        target_class = ENTITY_TYPE_CLASS_MAP.get(dto.ku_type)
        if target_class is None:
            from core.models.curriculum.curriculum import Curriculum

            target_class = Curriculum
        return target_class._from_dto(dto)

    @classmethod
    def _from_dto(cls, dto: "EntityDTO") -> Self:
        """
        Generic: extract only fields defined on THIS class from the unified DTO.

        Uses dataclasses.fields(cls) to determine which fields to extract,
        ensuring each subclass only gets its own fields + inherited Entity fields.
        Converts lists to tuples for frozen dataclass compatibility.
        """
        field_names = {f.name for f in dataclasses.fields(cls) if not f.name.startswith("_")}
        kwargs: dict[str, Any] = {}
        for name in field_names:
            value = getattr(dto, name, None)
            if isinstance(value, list):
                value = tuple(value)
            kwargs[name] = value
        return cls(**kwargs)

    def to_dto(self) -> "EntityDTO":
        """
        Convert Entity to EntityDTO with common fields.

        Per-domain subclasses override this to return their specific DTOs
        (TaskDTO, GoalDTO, etc.) with full domain-specific fields.
        This base implementation returns EntityDTO with ~18 common fields.

        Converts tuples back to lists for DTO mutability.
        """
        from core.models.entity_dto import EntityDTO

        dto_field_names = {f.name for f in dataclasses.fields(EntityDTO)}
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
        return EntityDTO(**kwargs)

    # =========================================================================
    # DISPLAY
    # =========================================================================

    def __str__(self) -> str:
        return f"Ku(uid={self.uid}, type={self.ku_type.value}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"Ku(uid='{self.uid}', ku_type={self.ku_type}, "
            f"title='{self.title}', domain={self.domain}, "
            f"status={self.status})"
        )
