"""
Entity Model Converters
=======================

Conversion functions for domain models to API response format.

Following SKUEL's three-tier type system:
- Entity (Domain Model) -> dict (API response)
"""

from typing import Any

from core.models.entity import Entity
from core.models.feedback.submission_feedback import SubmissionFeedback
from core.models.submissions.submission import Submission
from core.models.user_owned_entity import UserOwnedEntity


def entity_to_response(entity: Entity) -> dict[str, Any]:
    """
    Convert any Entity subclass to API response format.

    Uses isinstance checks for subclass-specific fields (Submission, SubmissionFeedback).
    user_uid and priority only exist on UserOwnedEntity subclasses.
    """
    response: dict[str, Any] = {
        "uid": entity.uid,
        "title": entity.title,
        "entity_type": ku.entity_type.value,
        "user_uid": entity.user_uid if isinstance(entity, UserOwnedEntity) else None,
        "parent_entity_uid": ku.parent_entity_uid,
        "domain": entity.domain.value,
        "created_by": entity.created_by,
        "status": entity.status.value,
        "created_at": entity.created_at.isoformat(),
        "updated_at": entity.updated_at.isoformat(),
        "metadata": entity.metadata,
        "visibility": entity.visibility.value if entity.visibility else "private",
        "content": entity.content,
        "summary": entity.summary,
        "word_count": entity.word_count,
        "tags": list(entity.tags) if entity.tags else [],
        "is_user_owned": entity.is_user_owned,
        "is_derived": entity.is_derived,
        "is_recent": entity.is_recent(),
    }

    # Submission-specific fields (file uploads, processing)
    if isinstance(entity, Submission):
        response.update(
            {
                "subject_uid": entity.subject_uid,
                "original_filename": entity.original_filename,
                "file_size": entity.file_size,
                "file_type": entity.file_type,
                "processor_type": entity.processor_type.value if entity.processor_type else None,
                "processing_started_at": entity.processing_started_at.isoformat()
                if entity.processing_started_at
                else None,
                "processing_completed_at": entity.processing_completed_at.isoformat()
                if entity.processing_completed_at
                else None,
                "processing_error": entity.processing_error,
                "has_processed_content": bool(entity.processed_content),
                "has_processed_file": bool(entity.processed_file_path),
                "processing_duration_seconds": entity.get_processing_duration(),
            }
        )

    # SubmissionFeedback-specific fields
    if isinstance(entity, SubmissionFeedback):
        response.update(
            {
                "feedback": entity.feedback,
                "feedback_generated_at": entity.feedback_generated_at.isoformat()
                if entity.feedback_generated_at
                else None,
            }
        )

    # Include journal metadata fields when present
    if entity.metadata:
        journal_type = entity.metadata.get("journal_type")
        if journal_type:
            response.update(
                {
                    "journal_type": journal_type,
                    "journal_category": entity.metadata.get("journal_category"),
                    "entry_date": entity.metadata.get("entry_date"),
                    "mood": entity.metadata.get("mood"),
                    "energy_level": entity.metadata.get("energy_level"),
                    "key_topics": entity.metadata.get("key_topics"),
                    "action_items": entity.metadata.get("action_items"),
                    "source_type": entity.metadata.get("source_type"),
                    "source_file": entity.metadata.get("source_file"),
                    "transcription_uid": entity.metadata.get("transcription_uid"),
                }
            )

    return response
