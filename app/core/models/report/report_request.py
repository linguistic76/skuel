"""
Report Request Models
======================

Pydantic models for API boundary validation (Tier 1).
Includes journal-type report request models (merged February 2026).
"""

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field

from core.models.enums.report_enums import (
    JournalCategory,
    JournalType,
    ProcessorType,
    ReportStatus,
    ReportType,
)


class ReportCreateRequest(BaseModel):
    """
    Request model for creating a report via API.

    Used when metadata is provided upfront (e.g., manual text submission).
    For file uploads, use the file upload endpoint directly.
    """

    user_uid: str = Field(..., description="User submitting the report")
    report_type: ReportType = Field(..., description="Type of report")
    processor_type: ProcessorType = Field(
        default=ProcessorType.AUTOMATIC,
        description="Processor type (LLM, human, hybrid, automatic)",
    )

    # File metadata (if known upfront)
    original_filename: str | None = Field(None, description="Original filename")
    file_type: str | None = Field(None, description="MIME type")

    # Optional metadata
    metadata: dict[str, Any] | None = Field(None, description="Additional metadata for the report")

    # Knowledge application (MVP - Phase C)
    applies_knowledge_uids: list[str] = Field(
        default_factory=list,
        description="Knowledge Units being applied/demonstrated in this report",
    )


class ReportUpdateRequest(BaseModel):
    """
    Request model for updating a report.

    Allows updating:
    - Status
    - Processed content
    - Processing metadata
    - Custom metadata
    """

    status: ReportStatus | None = Field(None, description="New status")
    processed_content: str | None = Field(None, description="Processed content")
    processed_file_path: str | None = Field(None, description="Path to processed file")
    processing_error: str | None = Field(None, description="Error message if failed")
    metadata: dict[str, Any] | None = Field(None, description="Additional metadata")


class ReportProcessRequest(BaseModel):
    """
    Request model for initiating processing of a report.

    Used to start processing with specific instructions.
    """

    report_uid: str = Field(..., description="Report UID to process")
    processor_type: ProcessorType = Field(..., description="Type of processor to use")
    instructions: dict[str, Any] | None = Field(
        None, description="Processing instructions (processor-specific)"
    )


class ReportQueryRequest(BaseModel):
    """
    Request model for querying reports.

    Supports filtering by type, status, date range.
    """

    user_uid: str = Field(..., description="User UID")
    report_type: ReportType | None = Field(None, description="Filter by type")
    status: ReportStatus | None = Field(None, description="Filter by status")
    start_date: datetime | None = Field(None, description="Start date filter")
    end_date: datetime | None = Field(None, description="End date filter")
    limit: int = Field(50, ge=1, le=500, description="Max results")
    offset: int = Field(0, ge=0, description="Pagination offset")


# ========================================================================
# CONTENT MANAGEMENT REQUEST MODELS
# ========================================================================


class CategorizeReportRequest(BaseModel):
    """Request to categorize a report."""

    category: str = Field(
        ...,
        description="Category from ReportCategory constants",
        examples=["daily", "weekly", "reflection", "work"],
    )


class AddTagsRequest(BaseModel):
    """Request to add tags to a report."""

    tags: list[str] = Field(
        ...,
        min_length=1,
        description="List of tags to add",
        examples=[["work", "priority", "review"]],
    )


class RemoveTagsRequest(BaseModel):
    """Request to remove tags from a report."""

    tags: list[str] = Field(..., min_length=1, description="List of tags to remove")


class BulkCategorizeRequest(BaseModel):
    """Request to categorize multiple reports."""

    report_uids: list[str] = Field(..., min_length=1, description="List of report UIDs")
    category: str = Field(..., description="Category to assign")


class BulkTagRequest(BaseModel):
    """Request to tag multiple reports."""

    report_uids: list[str] = Field(..., min_length=1, description="List of report UIDs")
    tags: list[str] = Field(..., min_length=1, description="List of tags to add")


class BulkDeleteRequest(BaseModel):
    """Request to delete multiple reports."""

    report_uids: list[str] = Field(..., min_length=1, description="List of report UIDs to delete")
    soft_delete: bool = Field(
        default=True,
        description="If True, archive instead of permanent delete",
    )


# ========================================================================
# JOURNAL-TYPE REPORT REQUEST MODELS
# ========================================================================


class JournalReportCreateRequest(BaseModel):
    """
    Request model for creating a journal-type report.

    Journals are reports with report_type=JOURNAL.
    """

    title: str = Field(..., min_length=1, max_length=500, description="Journal entry title")
    content: str = Field(..., min_length=1, description="Journal body text")
    journal_type: JournalType = Field(
        default=JournalType.CURATED, description="VOICE (ephemeral) or CURATED (permanent)"
    )
    category: JournalCategory = Field(default=JournalCategory.DAILY, description="Journal category")
    entry_date: date | None = Field(None, description="Date of the journal entry")
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")
    mood: str | None = Field(None, description="Current mood")
    energy_level: int | None = Field(None, ge=1, le=10, description="Energy level 1-10")
    key_topics: list[str] = Field(default_factory=list, description="Key topics")
    action_items: list[str] = Field(default_factory=list, description="Action items")
    project_uid: str | None = Field(None, description="Associated report project UID")
    metadata: dict[str, Any] | None = Field(None, description="Additional metadata")


class JournalReportUpdateRequest(BaseModel):
    """
    Request model for updating a journal-type report.

    All fields optional for PATCH-style updates.
    """

    title: str | None = Field(None, min_length=1, max_length=500, description="Journal title")
    content: str | None = Field(None, min_length=1, description="Journal body text")
    category: JournalCategory | None = Field(None, description="Journal category")
    tags: list[str] | None = Field(None, description="Tags for categorization")
    mood: str | None = Field(None, description="Current mood")
    energy_level: int | None = Field(None, ge=1, le=10, description="Energy level 1-10")
    key_topics: list[str] | None = Field(None, description="Key topics")
    action_items: list[str] | None = Field(None, description="Action items")
    status: ReportStatus | None = Field(None, description="New status")
    metadata: dict[str, Any] | None = Field(None, description="Additional metadata")
