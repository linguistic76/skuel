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
    """
    response: dict[str, Any] = {
        "uid": report.uid,
        "user_uid": report.user_uid,
        "report_type": report.report_type.value,
        "status": report.status.value,
        "subject_uid": report.subject_uid,
        "original_filename": report.original_filename,
        "file_size": report.file_size,
        "file_type": report.file_type,
        "processor_type": report.processor_type.value if report.processor_type else None,
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
        "visibility": report.visibility.value if report.visibility else "private",
    }

    # Include journal fields when report_type is JOURNAL
    if report.is_journal:
        response.update(
            {
                "title": report.title,
                "content": report.content,
                "tags": report.tags,
                "journal_category": report.journal_category.value
                if report.journal_category
                else None,
                "journal_type": report.journal_type.value if report.journal_type else None,
                "content_type": report.content_type.value if report.content_type else None,
                "entry_date": report.entry_date.isoformat() if report.entry_date else None,
                "word_count": report.word_count,
                "reading_time_minutes": report.reading_time_minutes,
                "mood": report.mood,
                "energy_level": report.energy_level,
                "key_topics": report.key_topics,
                "action_items": report.action_items,
                "has_insights": report.has_insights(),
                "is_recent": report.is_recent(),
                "summary": report.get_summary(),
                "is_voice_journal": report.is_voice_journal,
                "is_curated_journal": report.is_curated_journal,
            }
        )

    # Include progress report fields
    if report.is_progress_report:
        response.update(
            {
                "title": report.title,
                "processed_content": report.processed_content,
                "summary": report.get_summary(),
            }
        )
        # Include metadata stats if available
        if report.metadata:
            response["stats"] = report.metadata

    # Include assessment fields
    if report.is_assessment:
        response.update(
            {
                "title": report.title,
                "content": report.content,
                "subject_uid": report.subject_uid,
                "summary": report.get_summary(),
            }
        )

    return response
