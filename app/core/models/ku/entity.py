"""
Entity - Common Fields and Methods for All Knowledge Types
==========================================================

Base frozen dataclass shared by all 15 EntityType domain subclasses.
Contains ~29 fields genuinely common to every manifestation of knowledge:
Identity (7), Content (4), Status (2), Sharing (1), Meta (6), Embedding (3).

Learning metadata, substance tracking, and curriculum-specific methods live
on Curriculum (the intermediate class for curriculum-carrying types).

Domain subclasses (Task, Goal, Habit, etc.) inherit from Entity
and add their own fields and methods. The dispatcher `Entity.from_dto(dto)`
routes to the correct subclass based on dto.ku_type.

See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
See: /.claude/plans/crispy-spinning-wozniak.md
"""

import dataclasses
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar, Self

if TYPE_CHECKING:
    from core.models.ku.ku_dto import KuDTO

from core.models.enums import Domain
from core.models.enums.ku_enums import EntityStatus, EntityType
from core.models.enums.metadata_enums import Visibility


@dataclass(frozen=True)
class Entity:
    """
    Base frozen dataclass for all knowledge types.

    Contains ~29 fields shared by every EntityType manifestation:
    Identity (7), Content (4), Status (2), Sharing (1), Meta (6), Embedding (3).

    Learning metadata (7), substance tracking (10), and cache (2) fields
    live on Curriculum — they only apply to curriculum-carrying types.

    Domain-specific subclasses (Task, Goal, Habit, etc.) inherit
    from Entity and add their own fields and methods.
    """

    # Neo4j node label — all EntityType subclasses share the :Ku label
    _neo4j_label: ClassVar[str] = "Ku"

    # =========================================================================
    # IDENTITY
    # =========================================================================
    uid: str
    title: str
    ku_type: EntityType = EntityType.CURRICULUM
    user_uid: str | None = None  # None for shared types (CURRICULUM, LS, LP)
    parent_ku_uid: str | None = None  # Derivation chain — what Ku this was based on
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
    priority: str | None = None  # Priority enum value (LOW/MEDIUM/HIGH/CRITICAL)

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

        # Default visibility: shared types are PUBLIC, others are PRIVATE
        if self.visibility is None:
            if self.ku_type in {
                EntityType.CURRICULUM,
                EntityType.LEARNING_STEP,
                EntityType.LEARNING_PATH,
                EntityType.EXERCISE,
            }:
                object.__setattr__(self, "visibility", Visibility.PUBLIC)
            else:
                object.__setattr__(self, "visibility", Visibility.PRIVATE)

        # Compute word_count from content if not set
        if self.word_count == 0 and self.content:
            object.__setattr__(self, "word_count", len(self.content.split()))

    @property
    def is_user_owned(self) -> bool:
        """Check if this Ku has an owner (non-shared type)."""
        return self.user_uid is not None

    @property
    def is_derived(self) -> bool:
        """Check if this Ku was derived from another Ku."""
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
        """Only completed Ku can be shared (quality control)."""
        return self.status == EntityStatus.COMPLETED

    def can_view(self, viewer_uid: str, shared_user_uids: set[str] | None = None) -> bool:
        """
        Check if a user can view this Ku.

        Access granted if:
        - Ku is PUBLIC (all curriculum)
        - Viewer is the owner
        - Ku is SHARED and viewer is in shared_user_uids
        """
        if self.visibility == Visibility.PUBLIC:
            return True
        if self.user_uid and viewer_uid == self.user_uid:
            return True
        if self.visibility == Visibility.SHARED and shared_user_uids:
            return viewer_uid in shared_user_uids
        return False

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
    # GENERIC BUSINESS LOGIC (applies to all KuTypes)
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
    def from_dto(cls, dto: "KuDTO") -> "Entity":
        """
        Dispatch to appropriate domain subclass based on dto.ku_type.

        Routes EntityType.TASK → Task, EntityType.GOAL → Goal, etc.
        Falls back to Curriculum for unmapped types.
        """
        from core.models.ku.ku import ENTITY_TYPE_CLASS_MAP

        target_class = ENTITY_TYPE_CLASS_MAP.get(dto.ku_type)
        if target_class is None:
            from core.models.ku.curriculum import Curriculum

            target_class = Curriculum
        return target_class._from_dto(dto)

    @classmethod
    def _from_dto(cls, dto: "KuDTO") -> Self:
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

    def to_dto(self) -> "KuDTO":
        """
        Generic: convert any Entity subclass to unified KuDTO.

        Creates KuDTO with fields from this instance. Fields not present on
        the subclass get KuDTO defaults (None, 0, empty list, etc.).
        Converts tuples back to lists for DTO mutability.

        Skips infrastructure fields (embedding, cache) that don't exist on KuDTO
        per ADR-037 (embedding infrastructure separation).
        """
        from core.models.ku.ku_dto import KuDTO

        dto_field_names = {f.name for f in dataclasses.fields(KuDTO)}
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
        return KuDTO(**kwargs)

    # =========================================================================
    # DISPLAY
    # =========================================================================

    def __str__(self) -> str:
        return f"Ku(uid={self.uid}, type={self.ku_type.value}, title='{self.title}')"

    def __repr__(self) -> str:
        return (
            f"Ku(uid='{self.uid}', ku_type={self.ku_type}, "
            f"title='{self.title}', domain={self.domain}, "
            f"status={self.status}, user_uid={self.user_uid})"
        )
