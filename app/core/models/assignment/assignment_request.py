"""
Assignment Request Models
=========================

Pydantic models for API boundary validation (Tier 1).
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from core.models.assignment.assignment import AssignmentStatus, AssignmentType, ProcessorType


class AssignmentCreateRequest(BaseModel):
    """
    Request model for creating an assignment via API.

    Used when metadata is provided upfront (e.g., manual text submission).
    For file uploads, use the file upload endpoint directly.
    """

    user_uid: str = Field(..., description="User submitting the assignment")
    assignment_type: AssignmentType = Field(..., description="Type of assignment")
    processor_type: ProcessorType = Field(
        default=ProcessorType.AUTOMATIC,
        description="Processor type (LLM, human, hybrid, automatic)",
    )

    # File metadata (if known upfront)
    original_filename: str | None = Field(None, description="Original filename")
    file_type: str | None = Field(None, description="MIME type")

    # Optional metadata
    metadata: dict[str, Any] | None = Field(
        None, description="Additional metadata for the assignment"
    )


class AssignmentUpdateRequest(BaseModel):
    """
    Request model for updating an assignment.

    Allows updating:
    - Status
    - Processed content
    - Processing metadata
    - Custom metadata
    """

    status: AssignmentStatus | None = Field(None, description="New status")
    processed_content: str | None = Field(None, description="Processed content")
    processed_file_path: str | None = Field(None, description="Path to processed file")
    processing_error: str | None = Field(None, description="Error message if failed")
    metadata: dict[str, Any] | None = Field(None, description="Additional metadata")


class AssignmentProcessRequest(BaseModel):
    """
    Request model for initiating processing of an assignment.

    Used to start processing with specific instructions.
    """

    assignment_uid: str = Field(..., description="Assignment UID to process")
    processor_type: ProcessorType = Field(..., description="Type of processor to use")
    instructions: dict[str, Any] | None = Field(
        None, description="Processing instructions (processor-specific)"
    )


class AssignmentQueryRequest(BaseModel):
    """
    Request model for querying assignments.

    Supports filtering by type, status, date range.
    """

    user_uid: str = Field(..., description="User UID")
    assignment_type: AssignmentType | None = Field(None, description="Filter by type")
    status: AssignmentStatus | None = Field(None, description="Filter by status")
    start_date: datetime | None = Field(None, description="Start date filter")
    end_date: datetime | None = Field(None, description="End date filter")
    limit: int = Field(50, ge=1, le=500, description="Max results")
    offset: int = Field(0, ge=0, description="Pagination offset")
