"""
Assignment Model Converters
============================

Conversion functions for Assignment models.

Following SKUEL's three-tier type system:
- Assignment (Pure/Domain) -> AssignmentDTO -> API Response
"""

from typing import Any

from .assignment import Assignment


def assignment_to_response(assignment: Assignment) -> dict[str, Any]:
    """
    Convert Assignment domain model to API response format.

    Args:
        assignment: Assignment domain model (frozen dataclass)

    Returns:
        Dictionary suitable for JSON API response

    Note:
        This follows the same pattern as journal_dto_to_response().
        Converts domain model directly to response dict for API endpoints.
    """
    return {
        "uid": assignment.uid,
        "user_uid": assignment.user_uid,
        "assignment_type": assignment.assignment_type.value,
        "status": assignment.status.value,
        "original_filename": assignment.original_filename,
        "file_size": assignment.file_size,
        "file_type": assignment.file_type,
        "processor_type": assignment.processor_type.value,
        "processing_started_at": assignment.processing_started_at.isoformat()
        if assignment.processing_started_at
        else None,
        "processing_completed_at": assignment.processing_completed_at.isoformat()
        if assignment.processing_completed_at
        else None,
        "processing_error": assignment.processing_error,
        "has_processed_content": bool(assignment.processed_content),
        "has_processed_file": bool(assignment.processed_file_path),
        "created_at": assignment.created_at.isoformat(),
        "updated_at": assignment.updated_at.isoformat(),
        "processing_duration_seconds": assignment.get_processing_duration(),
        "metadata": assignment.metadata,
    }
