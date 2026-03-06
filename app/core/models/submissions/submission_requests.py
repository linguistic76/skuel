"""
Submission & LifePath Domain Request Models
============================================

Pydantic models for:
- Submissions domain: file uploads, AI reports
- LifePath domain: life path creation

SubmissionFeedback request models live in core.models.feedback.feedback_requests.

See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
"""

from pydantic import Field

from core.models.enums import Domain
from core.models.enums.entity_enums import ProcessorType
from core.models.request_base import CreateRequestBase

# =============================================================================
# CREATE REQUESTS — Content Processing (Reports)
# =============================================================================


class SubmissionCreateRequest(CreateRequestBase):
    """Create a student submission (SUBMISSION type)."""

    title: str = Field(min_length=1, max_length=200, description="Submission title")

    # Content (at least one of content or file expected)
    content: str | None = Field(None, description="Text content of submission")
    domain: Domain = Field(default=Domain.KNOWLEDGE, description="Knowledge domain")
    tags: list[str] = Field(default_factory=list, description="Tags")

    # Derivation
    parent_entity_uid: str | None = Field(None, description="Curriculum Ku this assignment is based on")

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


class ActivityReportCreateRequest(CreateRequestBase):
    """Create an AI-derived report (AI_FEEDBACK type). System-initiated."""

    title: str = Field(min_length=1, max_length=200, description="Report title")
    parent_entity_uid: str = Field(description="Assignment Ku this report derives from")

    # Content
    content: str | None = Field(None, description="AI-generated analysis")
    processed_content: str | None = Field(None, description="Processed output")
    summary: str | None = Field(None, max_length=500, description="Brief summary")
    domain: Domain = Field(default=Domain.KNOWLEDGE, description="Knowledge domain")

    # Processing
    processor_type: ProcessorType = Field(default=ProcessorType.LLM, description="Processing type")
    instructions: str | None = Field(None, description="Instructions used for generation")


# =============================================================================
# CREATE REQUESTS — Destination (LifePath)
# =============================================================================


class LifePathCreateRequest(CreateRequestBase):
    """Create a LIFE_PATH entity (knowledge about your life direction)."""

    title: str = Field(min_length=1, max_length=200, description="Life path title")
    description: str | None = Field(None, max_length=2000, description="Life path description")
    vision_statement: str = Field(min_length=10, max_length=2000, description="Vision statement")
    domain: Domain = Field(default=Domain.PERSONAL, description="Domain")
    tags: list[str] = Field(default_factory=list, description="Tags")
