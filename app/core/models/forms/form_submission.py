"""
FormSubmission - User Response to a FormTemplate
=================================================

Frozen dataclass for user-submitted form data. Extends UserOwnedEntity
(not Submission) — stores structured JSON, not uploaded files.

Hierarchy:
    Entity (~19 fields)
    └── UserOwnedEntity(Entity) +2 fields (user_uid, priority)
        └── FormSubmission(UserOwnedEntity) +3 fields

See: /docs/user-guides/form-submissions.md
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Self

from core.models.enums.entity_enums import EntityType
from core.models.user_owned_entity import UserOwnedEntity

if TYPE_CHECKING:
    from core.models.forms.form_submission_dto import FormSubmissionDTO


@dataclass(frozen=True)
class FormSubmission(UserOwnedEntity):
    """
    Immutable domain model for form submissions (EntityType.FORM_SUBMISSION).

    Stores structured form data as a dict, linked to a FormTemplate
    via RESPONDS_TO_FORM relationship.

    User-owned: requires user_uid.
    """

    # =========================================================================
    # FORM SUBMISSION FIELDS
    # =========================================================================
    form_template_uid: str | None = None
    form_data: dict[str, Any] | None = None
    processed_content: str | None = None  # Flattened text for search/embedding
    template_schema_hash: str | None = None  # SHA-256 of template schema at submit time

    # =========================================================================
    # INITIALIZATION
    # =========================================================================

    def __post_init__(self) -> None:
        """Force entity_type to FORM_SUBMISSION."""
        object.__setattr__(self, "entity_type", EntityType.FORM_SUBMISSION)
        super().__post_init__()

    # =========================================================================
    # QUERIES
    # =========================================================================

    def has_data(self) -> bool:
        """Check if this submission has form data."""
        return self.form_data is not None and len(self.form_data) > 0

    # =========================================================================
    # CONVERSION
    # =========================================================================

    @classmethod
    def _from_dto(cls, dto: "FormSubmissionDTO") -> Self:
        """Create FormSubmission from DTO."""
        return cls(
            uid=dto.uid,
            title=dto.title,
            entity_type=EntityType.FORM_SUBMISSION,
            parent_entity_uid=dto.parent_entity_uid,
            domain=dto.domain,
            created_by=dto.created_by,
            content=dto.content,
            summary=dto.summary,
            description=dto.description,
            word_count=dto.word_count,
            status=dto.status,
            tags=tuple(dto.tags) if dto.tags else (),
            created_at=dto.created_at,
            updated_at=dto.updated_at,
            metadata=dto.metadata or {},
            user_uid=dto.user_uid,
            priority=dto.priority,
            visibility=dto.visibility,
            form_template_uid=dto.form_template_uid,
            form_data=dict(dto.form_data) if dto.form_data else None,
            processed_content=dto.processed_content,
            template_schema_hash=dto.template_schema_hash,
        )

    def to_dto(self) -> "FormSubmissionDTO":
        """Convert to FormSubmissionDTO."""
        from core.models.forms.form_submission_dto import FormSubmissionDTO

        return FormSubmissionDTO(
            uid=self.uid,
            title=self.title,
            entity_type=self.entity_type,
            parent_entity_uid=self.parent_entity_uid,
            domain=self.domain,
            created_by=self.created_by,
            content=self.content,
            summary=self.summary,
            description=self.description,
            word_count=self.word_count,
            status=self.status,
            tags=list(self.tags),
            created_at=self.created_at,
            updated_at=self.updated_at,
            metadata=dict(self.metadata) if self.metadata else {},
            user_uid=self.user_uid,
            priority=self.priority,
            visibility=self.visibility,
            form_template_uid=self.form_template_uid,
            form_data=dict(self.form_data) if self.form_data else None,
            processed_content=self.processed_content,
            template_schema_hash=self.template_schema_hash,
        )

    # =========================================================================
    # DISPLAY
    # =========================================================================

    def __str__(self) -> str:
        return (
            f"FormSubmission(uid={self.uid}, title='{self.title}', "
            f"template={self.form_template_uid})"
        )

    def __repr__(self) -> str:
        return (
            f"FormSubmission(uid='{self.uid}', user_uid='{self.user_uid}', "
            f"form_template_uid='{self.form_template_uid}', status={self.status})"
        )
