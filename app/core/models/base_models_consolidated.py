"""
Base Models - Consolidated & Relationship-Centric
==================================================

Unified base classes for the three-tier architecture with relationship support:
1. Pure Domain Models (frozen dataclasses) - Core business logic with relationships
2. API Schemas (Pydantic) - External interface validation
3. DTOs (regular dataclasses) - Data transfer between layers

This module establishes a relationship-centric architecture where EVERYTHING
has relationships - aligning with the base_service.py philosophy.

Architecture Pattern:
--------------------
    External World
         ↓
    [Pydantic Models] - Validation & Serialization at boundaries
         ↓
    [DTOs] - Data transfer with relationship metadata
         ↓
    [Pure Domain Models] - Immutable entities with relationships
         ↓
    Core Business Logic (Graph-based)

Key Principles:
--------------
- Everything has relationships (graph-centric design)
- Domain models are ALWAYS frozen dataclasses (immutable)
- Pydantic ONLY at external boundaries (APIs, files, databases)
- DTOs are mutable for transformation between layers
- Validation returns Result[T], never raises exceptions
- Clear separation of concerns
"""

__version__ = "3.0"

import uuid
from abc import ABC
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Import Relationship from graph_models (extracted from base_service for reusability)
from core.models.graph_models import Relationship

# Import protocols to replace hasattr usage
from core.services.protocols import (
    EnumLike,
    HasCreatedAt,
    HasUID,
    HasUpdatedAt,
    HasValidate,
    get_enum_value,
)

# Import Result pattern for harmonized validation
from core.utils.result_simplified import Errors, Result

# ============================================================================
# SECTION 1: MIXINS FOR PURE DOMAIN MODELS
# ============================================================================


@dataclass(frozen=True)
class IdentifiableMixin:
    """Mixin for entities with unique identifiers"""

    uid: str = ""

    @classmethod
    def generate_uid(cls, prefix: str) -> str:
        """Generate a unique identifier with prefix"""
        return f"{prefix}_{uuid.uuid4().hex[:8]}"


@dataclass(frozen=True)
class TimestampMixin:
    """Mixin for entities with timestamps"""

    created_at: datetime = (field(default_factory=datetime.now),)
    updated_at: datetime = field(default_factory=datetime.now)

    def with_updated_timestamp(self, **kwargs: Any) -> "TimestampMixin":
        """Create updated copy with new timestamp"""
        return replace(self, updated_at=datetime.now(), **kwargs)


@dataclass(frozen=True)
class RelationshipMixin:
    """
    Mixin for entities that participate in relationships.
    Core to SKUEL's graph-based architecture.
    """

    # Stores relationship UIDs by type for offline/YAML operations
    relationship_uids: dict[str, list[str]] = field(default_factory=dict)

    def add_relationship(self, rel_type: str, target_uid: str) -> "RelationshipMixin":
        """Add a relationship (creates new immutable copy)"""
        new_rels = self.relationship_uids.copy()
        if rel_type not in new_rels:
            new_rels[rel_type] = []
        if target_uid not in new_rels[rel_type]:
            new_rels[rel_type].append(target_uid)
        return replace(self, relationship_uids=new_rels)

    def remove_relationship(self, rel_type: str, target_uid: str) -> "RelationshipMixin":
        """Remove a relationship (creates new immutable copy)"""
        new_rels = self.relationship_uids.copy()
        if rel_type in new_rels and target_uid in new_rels[rel_type]:
            new_rels[rel_type].remove(target_uid)
            if not new_rels[rel_type]:
                del new_rels[rel_type]
        return replace(self, relationship_uids=new_rels)

    def get_relationships(self, rel_type: str | None = None) -> dict[str, list[str]]:
        """Get relationships by type or all relationships"""
        if rel_type:
            return {rel_type: self.relationship_uids.get(rel_type, [])}
        return self.relationship_uids.copy()


@dataclass(frozen=True)
class ContentMixin:
    """Mixin for entities with content (markdown, notes, descriptions)"""

    content: str | None = None

    content_type: str = "text/plain"

    def has_content(self) -> bool:
        """Check if entity has content"""
        return self.content is not None and len(self.content.strip()) > 0


@dataclass(frozen=True)
class ProgressMixin:
    """Mixin for entities with progress/status tracking"""

    status: str | None = None
    progress: float = 0.0  # 0-100 percentage

    def update_progress(self, new_progress: float) -> "ProgressMixin":
        """Update progress (creates new immutable copy)"""
        clamped = max(0.0, min(100.0, new_progress))
        return replace(self, progress=clamped)  # ProgressMixin doesn't have updated_at field

    def is_complete(self) -> bool:
        """Check if progress is complete"""
        return self.progress >= 100.0


@dataclass(frozen=True)
class AuditableMixin(TimestampMixin):
    """Mixin for entities with full audit trail"""

    created_by: str | None = None

    updated_by: str | None = None

    def with_update(self, updated_by: str | None = None, **kwargs: Any) -> "AuditableMixin":
        """Create updated copy with audit info"""
        return replace(self, updated_at=datetime.now(), updated_by=updated_by, **kwargs)


class ValidatableMixin:
    """
    Mixin for dataclass validation using Result pattern.
    Harmonized with base_service.py error handling.
    """

    def validate(self) -> Result[bool]:
        """
        Validate the entity and return Result.
        Override in subclasses to add specific validations.
        """
        errors = []

        # Common validations
        if isinstance(self, HasUID) and not self.uid:
            errors.append("UID is required")

        # Check if object has title attribute directly
        title = getattr(self, "title", None)
        if title is not None:
            if not title or (isinstance(title, str) and not title.strip()):
                errors.append("Title cannot be empty")
            elif isinstance(title, str) and len(title) > 200:
                errors.append("Title cannot exceed 200 characters")

        # Check for required timestamps
        if isinstance(self, HasCreatedAt) and not self.created_at:
            errors.append("Created timestamp is required")

        # Validate progress bounds
        progress = getattr(self, "progress", None)
        if progress is not None and (progress < 0 or progress > 100):
            errors.append("Progress must be between 0 and 100")

        # Return Result pattern
        if errors:
            return Result.fail(
                Errors.validation(message="; ".join(errors), field="entity_validation")
            )
        return Result.ok(True)

    def is_valid(self) -> bool:
        """Check if entity is valid"""
        result = self.validate()
        return result.is_ok


# ============================================================================
# SECTION 2: PURE DOMAIN MODELS (Frozen Dataclasses)
# ============================================================================
# These are the core business entities - immutable and framework-agnostic


@dataclass(frozen=True)
class BasePureModel(IdentifiableMixin, TimestampMixin, RelationshipMixin, ABC):
    """
    Base for all pure domain models with common fields.
    Now includes relationship support as fundamental.
    """

    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization"""
        result = {}
        for key, value in self.__dict__.items():
            if value is not None:
                if isinstance(value, datetime):
                    result[key] = value.isoformat()
                elif isinstance(value, EnumLike):
                    result[key] = get_enum_value(value)
                elif isinstance(value, list | dict):
                    result[key] = value
                else:
                    result[key] = value
        return result


@dataclass(frozen=True)
class BaseEntity(BasePureModel, ContentMixin, ProgressMixin, ValidatableMixin):
    """
    Enhanced base for domain entities with all common fields.
    Includes relationships, content, progress - everything services expect.
    """

    title: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)

    def update_content(self, new_content: str) -> "BaseEntity":
        """Update content (creates new immutable copy)"""
        return replace(self, content=new_content, updated_at=datetime.now())

    def update_status(self, new_status: str) -> "BaseEntity":
        """Update status (creates new immutable copy)"""
        return replace(self, status=new_status, updated_at=datetime.now())


@dataclass(frozen=True)
class BaseUserOwnedModel(BaseEntity):
    """Base for models owned by a user"""

    user_uid: str = ""

    def validate(self) -> Result[bool]:
        """Extended validation for user-owned models"""
        # Call parent validation first
        parent_result = super().validate()
        if not parent_result.is_ok:
            return parent_result

        # Additional validation
        if not self.user_uid:
            return Result.fail(
                Errors.validation(
                    message="User UID is required for user-owned models", field="user_uid"
                )
            )
        return Result.ok(True)


@dataclass(frozen=True)
class BaseTaggedModel(BaseEntity):
    """Base for models with enhanced tagging and notes"""

    notes: str | None = None

    categories: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BaseVersionedModel(BaseEntity):
    """Base for models with version tracking"""

    version: int = 1
    version_notes: str | None = None
    previous_version_uid: str | None = None

    def increment_version(self, notes: str | None = None) -> "BaseVersionedModel":
        """Create new version with incremented number"""
        return replace(
            self,
            version=self.version + 1,
            version_notes=notes,
            previous_version_uid=self.uid,
            uid=self.generate_uid(self.uid.split("_")[0]),  # Keep prefix
            updated_at=datetime.now(),
        )


@dataclass(frozen=True)
class BaseRecurringModel(BaseEntity):
    """Base for models with recurrence (habits, recurring tasks)"""

    recurrence_pattern: str | None = None

    recurrence_end_date: datetime | None = None  # type: ignore[assignment]
    skip_dates: list[datetime] = field(default_factory=list)

    def is_recurring(self) -> bool:
        """Check if entity is recurring"""
        return self.recurrence_pattern is not None

    def should_skip_date(self, date: datetime) -> bool:
        """Check if should skip on given date"""
        return date in self.skip_dates


# ============================================================================
# SECTION 3: DTOs (Regular Dataclasses)
# ============================================================================
# Mutable data transfer objects for moving data between layers


@dataclass
class BaseDTO:
    """
    Base for all DTO models.
    DTOs are mutable and used for transferring data between layers.
    Now includes relationship information for graph operations.
    """

    uid: str
    created_at: datetime | None = None
    updated_at: datetime | None = None  # type: ignore[assignment]
    metadata: dict[str, Any] = field(default_factory=dict)

    # Relationship information for transfer
    relationships_out: list[Relationship] = (field(default_factory=list),)
    relationships_in: list[Relationship] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert DTO to dictionary"""
        result = {}
        for k, v in self.__dict__.items():
            if v is not None:
                if isinstance(v, datetime):
                    result[k] = v.isoformat()
                elif isinstance(v, EnumLike):
                    result[k] = get_enum_value(v)
                elif isinstance(v, Relationship):
                    # Convert Relationship to dict
                    result[k] = {
                        "from_uid": v.from_uid,
                        "rel_type": v.rel_type,
                        "to_uid": v.to_uid,
                        "properties": v.properties,
                    }
                elif isinstance(v, list) and v and isinstance(v[0], Relationship):
                    # Convert list of Relationships
                    result[k] = [
                        {
                            "from_uid": rel.from_uid,
                            "rel_type": rel.rel_type,
                            "to_uid": rel.to_uid,
                            "properties": rel.properties,
                        }
                        for rel in v
                    ]
                else:
                    result[k] = v
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BaseDTO":
        """Create DTO from dictionary"""
        # Parse datetime strings
        for field_name in ["created_at", "updated_at"]:
            if field_name in data and isinstance(data[field_name], str):
                data[field_name] = datetime.fromisoformat(data[field_name])

        # Parse relationship data if present
        for rel_field in ["relationships_out", "relationships_in"]:
            if rel_field in data and isinstance(data[rel_field], list):
                relationships = [
                    Relationship(
                        from_uid=rel_data["from_uid"],
                        rel_type=rel_data["rel_type"],
                        to_uid=rel_data["to_uid"],
                        properties=rel_data.get("properties"),
                    )
                    for rel_data in data[rel_field]
                    if isinstance(rel_data, dict)
                ]
                data[rel_field] = relationships

        return cls(**data)

    def merge_with(self, other: dict[str, Any]) -> "BaseDTO":
        """Merge with another dict, updating this DTO"""
        for key, value in other.items():
            # Try to set attribute if it exists
            try:
                if value is not None:
                    setattr(self, key, value)
            except AttributeError:
                # Skip if attribute doesn't exist
                pass
        return self


@dataclass
class BaseContentDTO(BaseDTO):
    """DTO for entities with content"""

    content: str | None = None

    content_type: str = "text/plain"
    content_length: int = 0

    def __post_init__(self) -> None:
        """Calculate content length after initialization"""
        if self.content:
            self.content_length = len(self.content)


@dataclass
class BaseProgressDTO(BaseDTO):
    """DTO for entities with progress tracking"""

    status: str | None = None
    progress: float = 0.0
    completed_at: datetime | None = None

    def mark_complete(self):
        """Mark as complete (mutable operation)"""
        self.progress = 100.0
        self.completed_at = datetime.now()
        self.status = "completed"


@dataclass
class BaseSearchDTO(BaseDTO):
    """DTO for search results with additional metadata"""

    score: float | None = None

    highlights: dict[str, str] = (field(default_factory=dict),)
    matched_fields: list[str] = (field(default_factory=list),)
    relationship_paths: list[list[str]] = field(default_factory=list)  # Paths through graph


# ============================================================================
# SECTION 4: API SCHEMAS (Pydantic Models)
# ============================================================================
# Used ONLY at external boundaries for validation and serialization


class BaseSchema(BaseModel):
    """
    Base for all Pydantic schemas.
    Used at API boundaries for validation and serialization.
    """

    model_config = ConfigDict(
        from_attributes=True,  # Allows creation from ORM models
        # Pydantic V2 serializes datetimes automatically
        validate_assignment=True,  # Validate on attribute assignment
        use_enum_values=True,  # Serialize enums as values
    )


class BaseCreateSchema(BaseSchema):
    """Base schema for creation requests"""

    title: str = (Field(..., min_length=1, max_length=200, description="Title of the entity"),)
    description: str | None = (Field(None, max_length=2000, description="Description"),)
    content: str | None = (Field(None, description="Main content (markdown, text, etc)"),)
    tags: list[str] = (Field(default_factory=list, description="Tags for categorization"),)
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    # Optional relationship specifications
    relationships: dict[str, list[str]] | None = Field(
        None, description="Initial relationships by type"
    )


class BaseUpdateSchema(BaseSchema):
    """Base schema for update requests - all fields optional"""

    title: str | None = (Field(None, min_length=1, max_length=200),)
    description: str | None = (Field(None, max_length=2000),)
    content: str | None = (Field(None),)
    status: str | None = (Field(None),)
    progress: float | None = (Field(None, ge=0, le=100),)
    tags: list[str] | None = None

    notes: str | None = None
    metadata: dict[str, Any] | None = None


class BaseResponseSchema(BaseSchema):
    """Base schema for API responses"""

    uid: str = (Field(..., description="Unique identifier"),)
    title: str = (Field(..., description="Title"),)
    description: str | None = (Field(None, description="Description"),)
    content: str | None = (Field(None, description="Content"),)
    status: str | None = (Field(None, description="Current status"),)
    progress: float = (Field(0.0, description="Progress percentage (0-100)"),)
    tags: list[str] = (Field(default_factory=list),)
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    # Include relationship summary
    relationship_counts: dict[str, int] | None = Field(
        None, description="Count of relationships by type"
    )


class BaseRelationshipSchema(BaseSchema):
    """Schema for relationship data"""

    from_uid: str = (Field(..., description="Source entity UID"),)
    rel_type: str = (Field(..., description="Relationship type"),)
    to_uid: str = (Field(..., description="Target entity UID"),)
    properties: dict[str, Any] | None = Field(None, description="Relationship properties")


class BasePaginatedResponseSchema(BaseSchema):
    """Base schema for paginated responses"""

    items: list[BaseResponseSchema] = (Field(..., description="List of items"),)
    total: int = (Field(..., description="Total number of items"),)
    page: int = (Field(1, description="Current page number"),)
    per_page: int = (Field(20, description="Items per page"),)
    pages: int = Field(..., description="Total number of pages")


# ============================================================================
# SECTION 5: FACTORY & HELPER FUNCTIONS
# ============================================================================


class EntityFactory:
    """Factory for creating entities with consistent defaults"""

    @staticmethod
    def create_uid(prefix: str) -> str:
        """Create a unique identifier with prefix"""
        return f"{prefix}_{uuid.uuid4().hex[:8]}"

    @staticmethod
    def create_entity(
        entity_class: type[BaseEntity], title: str, prefix: str, **kwargs: Any
    ) -> BaseEntity:
        """Generic entity creation with defaults"""
        defaults = {
            "uid": EntityFactory.create_uid(prefix),
            "title": title,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "relationship_uids": {},
            "progress": 0.0,
        }
        defaults.update(kwargs)
        return entity_class(**defaults)

    @staticmethod
    def create_with_relationships(
        entity_class: type[BaseEntity],
        title: str,
        prefix: str,
        relationships: dict[str, list[str]],
        **kwargs: Any,
    ) -> BaseEntity:
        """Create entity with initial relationships"""
        entity = EntityFactory.create_entity(entity_class, title, prefix, **kwargs)
        # Add relationships
        for rel_type, target_uids in relationships.items():
            for target_uid in target_uids:
                entity = entity.add_relationship(rel_type, target_uid)
        return entity


def update_entity(entity: BaseEntity, **updates: Any) -> BaseEntity:
    """
    Generic update function for immutable entities.
    Automatically updates the updated_at timestamp.
    """
    if isinstance(entity, HasUpdatedAt):
        updates["updated_at"] = datetime.now()
    return replace(entity, **updates)


def validate_entity_graph(entity: BaseEntity) -> Result[bool]:
    """
    Validate an entity including its relationships.
    Ensures relationship consistency.
    """
    # First validate the entity itself
    entity_result = entity.validate() if isinstance(entity, HasValidate) else Result.ok(True)
    if not entity_result.is_ok:
        return entity_result

    # Validate relationships if present
    relationship_uids = getattr(entity, "relationship_uids", None)
    if relationship_uids is not None:
        for rel_type, target_uids in entity.relationship_uids.items():
            if not isinstance(target_uids, list):
                return Result.fail(
                    Errors.validation(
                        message=f"Relationship {rel_type} must map to a list of UIDs",
                        field="relationship_uids",
                    )
                )
            for uid in target_uids:
                if not uid or not isinstance(uid, str):
                    return Result.fail(
                        Errors.validation(
                            message=f"Invalid UID in relationship {rel_type}",
                            field="relationship_uids",
                        )
                    )

    return Result.ok(True)


# ============================================================================
# SECTION 6: TYPE ALIASES & DOCUMENTATION
# ============================================================================

"""
Usage Guide - Relationship-Centric Models:
------------------------------------------

1. Pure Domain Models with Relationships:
   ```python
   @dataclass(frozen=True)
   class KnowledgeUnit(BaseEntity):
       domain: str
       # Inherits relationship_uids, content, progress, status

   # Create with relationships
   unit = EntityFactory.create_with_relationships(
       KnowledgeUnit,
       title="Linear Algebra",
       prefix="ku",
       relationships={
           "REQUIRES_KNOWLEDGE": ["ku_calculus", "ku_matrices"],
           "ENABLES_KNOWLEDGE": ["ku_ml_basics"]
       }
   )
   ```

2. DTOs with Relationship Transfer:
   ```python
   @dataclass
   class KnowledgeUnitDTO(BaseContentDTO):
       domain: str
       # Inherits relationships_in, relationships_out
   ```

3. API Schemas with Relationship Support:
   ```python
   class KuCreateRequest(BaseCreateSchema):
       domain: str = Field(..., description="Knowledge domain")
       # Inherits relationships field for initial setup
   ```

Relationship Philosophy:
-----------------------
- Everything in SKUEL has relationships
- Relationships are first-class citizens
- Models store relationship UIDs for offline operations
- Services manage actual graph connections
- DTOs transfer relationship metadata between layers

Validation Philosophy:
---------------------
- ALL validation returns Result[T]
- NEVER throw exceptions from validation
- Harmonized with base_service.py error handling
- Consistent error messages via Errors factory

Progress & Status:
-----------------
- All entities can track progress (0-100%)
- Status field for state management
- Content field for rich text/markdown
- Unified with service layer expectations
"""
