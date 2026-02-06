"""
Report Model Converters
========================

Conversion functions for Report models.

Following SKUEL's three-tier type system:
- Report (Pure/Domain) -> ReportDTO -> API Response
"""

from typing import Any

from .report import Report


def report_to_response(report: Report) -> dict[str, Any]:
    """
    Convert Report domain model to API response format.

    Args:
        report: Report domain model (frozen dataclass)

    Returns:
        Dictionary suitable for JSON API response

    Note:
        This follows the same pattern as journal_dto_to_response().
        Converts domain model directly to response dict for API endpoints.
    """
    return {
        "uid": report.uid,
        "user_uid": report.user_uid,
        "report_type": report.report_type.value,
        "status": report.status.value,
        "original_filename": report.original_filename,
        "file_size": report.file_size,
        "file_type": report.file_type,
        "processor_type": report.processor_type.value,
        "processing_started_at": report.processing_started_at.isoformat()
        if report.processing_started_at
        else None,
        "processing_completed_at": report.processing_completed_at.isoformat()
        if report.processing_completed_at
        else None,
        "processing_error": report.processing_error,
        "has_processed_content": bool(report.processed_content),
        "has_processed_file": bool(report.processed_file_path),
        "created_at": report.created_at.isoformat(),
        "updated_at": report.updated_at.isoformat(),
        "processing_duration_seconds": report.get_processing_duration(),
        "metadata": report.metadata,
    }
