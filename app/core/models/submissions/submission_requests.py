"""
Submission Domain Request Models
================================

Pydantic models for student submission creation.

ExerciseReport request models live in core.models.report.report_requests.
Form submission request models live in core.models.forms.form_submission_request.
LifePath request models live in core.models.lifepath_request.

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from pydantic import Field

from core.models.enums import Domain
from core.models.enums.entity_enums import ProcessorType
from core.models.request_base import CreateRequestBase
from core.models.type_hints import EntityUID

# =============================================================================
# CREATE REQUESTS — Student Submissions
# =============================================================================


class SubmissionCreateRequest(CreateRequestBase):
    """Create a student submission (SUBMISSION type)."""

    title: str = Field(min_length=1, max_length=200, description="Submission title")

    # Content (at least one of content or file expected)
    content: str | None = Field(None, description="Text content of submission")
    domain: Domain = Field(default=Domain.KNOWLEDGE, description="Knowledge domain")
    tags: list[str] = Field(default_factory=list, description="Tags")

    # Derivation
    parent_entity_uid: EntityUID | None = Field(
        None, description="Exercise this submission is based on"
    )

    # Processing
    processor_type: ProcessorType | None = Field(
        None, description="How to process (LLM, HUMAN, etc.)"
    )
    instructions: str | None = Field(
        None, description="Processing instructions (absorbed from ReportProject)"
    )

    # File metadata (populated by upload handler, not user input)
    original_filename: str | None = Field(None, description="Uploaded filename")
    file_path: str | None = Field(None, description="Server file path")
    file_size: int | None = Field(None, ge=0, description="File size in bytes")
    file_type: str | None = Field(None, description="MIME type")
