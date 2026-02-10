"""
Ku Model Converters
====================

Conversion functions for Ku domain model to API response format.

Following SKUEL's three-tier type system:
- Ku (Domain Model) -> dict (API response)
"""

from typing import Any

from .ku import Ku


def ku_to_response(ku: Ku) -> dict[str, Any]:
    """
    Convert Ku domain model to API response format.

    Args:
        ku: Ku domain model (frozen dataclass)

    Returns:
        Dictionary suitable for JSON API response
    """
    response: dict[str, Any] = {
        "uid": ku.uid,
        "title": ku.title,
        "ku_type": ku.ku_type.value,
        "user_uid": ku.user_uid,
        "parent_ku_uid": ku.parent_ku_uid,
        "domain": ku.domain.value,
        "created_by": ku.created_by,
        "status": ku.status.value,
        "subject_uid": ku.subject_uid,
        "original_filename": ku.original_filename,
        "file_size": ku.file_size,
        "file_type": ku.file_type,
        "processor_type": ku.processor_type.value if ku.processor_type else None,
        "processing_started_at": ku.processing_started_at.isoformat()
        if ku.processing_started_at
        else None,
        "processing_completed_at": ku.processing_completed_at.isoformat()
        if ku.processing_completed_at
        else None,
        "processing_error": ku.processing_error,
        "has_processed_content": bool(ku.processed_content),
        "has_processed_file": bool(ku.processed_file_path),
        "created_at": ku.created_at.isoformat(),
        "updated_at": ku.updated_at.isoformat(),
        "processing_duration_seconds": ku.get_processing_duration(),
        "metadata": ku.metadata,
        "visibility": ku.visibility.value if ku.visibility else "private",
        "content": ku.content,
        "summary": ku.get_summary(),
        "word_count": ku.word_count,
        "tags": list(ku.tags) if ku.tags else [],
        "is_user_owned": ku.is_user_owned,
        "is_derived": ku.is_derived,
        "is_recent": ku.is_recent(),
    }

    # Include journal metadata fields when present
    if ku.metadata:
        journal_type = ku.metadata.get("journal_type")
        if journal_type:
            response.update(
                {
                    "journal_type": journal_type,
                    "journal_category": ku.metadata.get("journal_category"),
                    "entry_date": ku.metadata.get("entry_date"),
                    "mood": ku.metadata.get("mood"),
                    "energy_level": ku.metadata.get("energy_level"),
                    "key_topics": ku.metadata.get("key_topics"),
                    "action_items": ku.metadata.get("action_items"),
                    "source_type": ku.metadata.get("source_type"),
                    "source_file": ku.metadata.get("source_file"),
                    "transcription_uid": ku.metadata.get("transcription_uid"),
                }
            )

    # Include feedback fields for FEEDBACK_REPORT
    if ku.is_feedback_report:
        response.update(
            {
                "feedback": ku.feedback,
                "feedback_generated_at": ku.feedback_generated_at.isoformat()
                if ku.feedback_generated_at
                else None,
            }
        )

    # Include AI report fields
    if ku.is_ai_report:
        response["processed_content"] = ku.processed_content

    return response
