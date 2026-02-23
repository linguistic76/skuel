"""
Resource - Resource Domain Model
====================================

Frozen dataclass for resource entities (EntityType.RESOURCE).

Tier A (Raw Content): Independent curated content — books, talks, films, music.
Inherits common fields from Entity. Adds 7 resource-specific fields:
- Source (3): source_url, author, publisher
- Publication (2): publication_year, isbn
- Media (2): media_type, resource_duration_minutes

Resources are admin-curated shared content that feeds Askesis recommendations.
They do NOT carry learning/substance fields (those belong to Curriculum).

See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.models.entity_dto import EntityDTO
    from core.models.resource.resource_dto import ResourceDTO

from core.models.entity import Entity
from core.models.enums.entity_enums import EntityType


@dataclass(frozen=True)
class Resource(Entity):
    """
    Immutable domain model for resources (EntityType.RESOURCE).

    Tier A (Raw Content): Books, talks, films, music — independent curated
    content that feeds Askesis recommendations. Admin-created, publicly readable.

    Inherits common fields from Entity (identity, content, status, sharing,
    meta, embedding). Does NOT inherit learning/substance fields.
    """

    def __post_init__(self) -> None:
        """Force ku_type=RESOURCE, then delegate to Entity."""
        if self.ku_type != EntityType.RESOURCE:
            object.__setattr__(self, "ku_type", EntityType.RESOURCE)
        super().__post_init__()

    # =========================================================================
    # SOURCE
    # =========================================================================
    source_url: str | None = None  # URL to the original resource
    author: str | None = None  # Author / creator name
    publisher: str | None = None  # Publisher or platform

    # =========================================================================
    # PUBLICATION
    # =========================================================================
    publication_year: int | None = None  # Year published
    isbn: str | None = None  # ISBN for books

    # =========================================================================
    # MEDIA
    # =========================================================================
    media_type: str | None = None  # book, talk, film, music, article, podcast
    resource_duration_minutes: int | None = None  # Duration for time-based media

    # =========================================================================
    # RESOURCE-SPECIFIC METHODS
    # =========================================================================

    def get_summary(self, max_length: int = 200) -> str:
        """Get a summary of the resource."""
        text = self.description or self.content or self.summary or ""
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."

    def explain_existence(self) -> str:
        """Explain why this resource exists."""
        parts = []
        if self.author:
            parts.append(f"by {self.author}")
        if self.publisher:
            parts.append(f"published by {self.publisher}")
        if self.publication_year:
            parts.append(f"({self.publication_year})")
        attribution = " ".join(parts)
        base = self.title
        if attribution:
            base = f"{base} — {attribution}"
        return base

    @property
    def is_time_based(self) -> bool:
        """Check if this resource has a time duration (talk, film, podcast)."""
        return self.resource_duration_minutes is not None

    # =========================================================================
    # CONVERSION (generic -- uses Entity._from_dto / to_dto)
    # =========================================================================

    @classmethod
    def from_dto(cls, dto: "EntityDTO | ResourceDTO") -> "Resource":
        """Create Resource from an EntityDTO or ResourceDTO."""
        return cls._from_dto(dto)

    def to_dto(self) -> "ResourceDTO":  # type: ignore[override]
        """Convert Resource to domain-specific ResourceDTO."""
        import dataclasses
        from typing import Any

        from core.models.resource.resource_dto import ResourceDTO

        dto_field_names = {f.name for f in dataclasses.fields(ResourceDTO)}
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
        return ResourceDTO(**kwargs)

    def __str__(self) -> str:
        return f"Resource(uid={self.uid}, title='{self.title}', media_type={self.media_type})"

    def __repr__(self) -> str:
        return (
            f"Resource(uid='{self.uid}', title='{self.title}', "
            f"status={self.status}, media_type={self.media_type}, "
            f"author={self.author})"
        )
