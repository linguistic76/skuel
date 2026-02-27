"""
Entity Model Converters
=======================

Conversion functions for domain models to API response format.

Following SKUEL's three-tier type system:
- Ku (Domain Model) -> dict (API response)
"""

from typing import Any

from core.models.entity import Entity
from core.models.feedback.feedback import Feedback
from core.models.submissions.submission import Submission
from core.models.user_owned_entity import UserOwnedEntity


def ku_to_response(ku: Entity) -> dict[str, Any]:
    """
    Convert any Entity subclass to API response format.

    Uses isinstance checks for subclass-specific fields (Submission, Feedback).
    user_uid and priority only exist on UserOwnedEntity subclasses.
    """
    response: dict[str, Any] = {
        "uid": ku.uid,
        "title": ku.title,
        "ku_type": ku.ku_type.value,
        "user_uid": ku.user_uid if isinstance(ku, UserOwnedEntity) else None,
        "parent_ku_uid": ku.parent_ku_uid,
        "domain": ku.domain.value,
        "created_by": ku.created_by,
        "status": ku.status.value,
        "created_at": ku.created_at.isoformat(),
        "updated_at": ku.updated_at.isoformat(),
        "metadata": ku.metadata,
        "visibility": ku.visibility.value if ku.visibility else "private",
        "content": ku.content,
        "summary": ku.summary,
        "word_count": ku.word_count,
        "tags": list(ku.tags) if ku.tags else [],
        "is_user_owned": ku.is_user_owned,
        "is_derived": ku.is_derived,
        "is_recent": ku.is_recent(),
    }

    # Submission-specific fields (file uploads, processing)
    if isinstance(ku, Submission):
        response.update(
            {
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
                "processing_duration_seconds": ku.get_processing_duration(),
            }
        )

    # Feedback-specific fields
    if isinstance(ku, Feedback):
        response.update(
            {
                "feedback": ku.feedback,
                "feedback_generated_at": ku.feedback_generated_at.isoformat()
                if ku.feedback_generated_at
                else None,
            }
        )

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

    return response
