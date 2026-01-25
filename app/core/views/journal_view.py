"""
Journal View Transformations
============================

View layer for converting JournalPure domain models to API-friendly dictionaries.
Follows the three-tier type system pattern.

Architecture:
- JournalPure (Tier 3) → View Dict → API Response (Tier 1)
- Clean separation between domain models and API responses
- Multiple view formats: full, list, summary
"""

from typing import Any

from core.models.journal.journal_pure import JournalPure
from core.models.serialization_helpers import serialize_date_safe, serialize_datetime_safe
from core.services.protocols import get_enum_value

# Local alias to match existing naming convention
_serialize_date = serialize_date_safe

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

# Date/datetime serialization now uses centralized helpers:
# - serialize_datetime_safe: for datetime fields
# - serialize_date_safe: for date fields
# See: core/models/serialization_helpers.py


def _serialize_enum(enum_value) -> str | None:
    """Safely serialize enum to string value"""
    if enum_value is None:
        return None
    return get_enum_value(enum_value)


# ============================================================================
# VIEW TRANSFORMATION FUNCTIONS
# ============================================================================


def journal_pure_to_view(
    journal: JournalPure,
    related_journal_uids: list[str] | None = None,
    goal_uids: list[str] | None = None,
) -> dict[str, Any]:
    """
    Convert JournalPure domain model to full view dictionary.

    Use this for:
    - Single journal detail views
    - Complete journal data with all fields
    - When client needs full journal information

    Args:
        journal: JournalPure domain model,
        related_journal_uids: UIDs of related journals (fetched by service layer),
        goal_uids: UIDs of related goals (fetched by service layer),

    Returns:
        Dictionary with all journal fields serialized for API response

    Note:
        Service layer should fetch relationship UIDs using JournalsRelationshipService:
        - related_journal_uids = await journals_relationship_service.get_related_journals(journal.uid)
        - goal_uids = await journals_relationship_service.get_journal_goals(journal.uid)
    """
    # Default to empty lists if not provided
    related_journal_uids = related_journal_uids or []
    goal_uids = goal_uids or []
    return {
        # Identity
        "uid": journal.uid,
        # Core content
        "title": journal.title,
        "content": journal.content,
        # Classification
        "content_type": _serialize_enum(journal.content_type),
        "category": _serialize_enum(journal.category),
        # Metadata
        "entry_date": _serialize_date(journal.entry_date),
        "word_count": journal.word_count,
        "reading_time_minutes": round(journal.reading_time_minutes, 2),
        # Status
        "status": _serialize_enum(journal.status),
        "visibility": _serialize_enum(journal.visibility),
        # Source information (for transcribed content)
        "source_type": journal.source_type,
        "source_file": journal.source_file,
        "transcription_uid": journal.transcription_uid,
        # Extracted insights
        "mood": journal.mood,
        "energy_level": journal.energy_level,
        "key_topics": journal.key_topics or [],
        "mentioned_people": journal.mentioned_people or [],
        "mentioned_places": journal.mentioned_places or [],
        "action_items": journal.action_items or [],
        # Relations
        # GRAPH-NATIVE: related_journal_uids and goal_uids stored as graph relationships
        # Service layer passes these via function parameters
        "related_journal_uids": related_journal_uids,
        "project_uid": journal.project_uid,
        "goal_uids": goal_uids,
        # AI Feedback
        "feedback": journal.feedback,
        "feedback_generated_at": serialize_datetime_safe(journal.feedback_generated_at),
        # Metadata
        "tags": journal.tags or [],
        "metadata": journal.metadata or {},
        # Audit
        "created_at": serialize_datetime_safe(journal.created_at),
        "updated_at": serialize_datetime_safe(journal.updated_at),
        "created_by": journal.created_by,
        # Computed fields
        "is_recent": journal.is_recent(),
        "is_long_form": journal.is_long_form(),
        "has_insights": journal.has_insights(),
    }


def journal_pure_to_summary_view(
    journal: JournalPure,
    related_journal_uids: list[str] | None = None,
) -> dict[str, Any]:
    """
    Convert JournalPure domain model to summary view dictionary.

    Use this for:
    - List views where full content isn't needed
    - Search results
    - Calendar/timeline views
    - Performance-optimized responses

    Args:
        journal: JournalPure domain model,
        related_journal_uids: UIDs of related journals (fetched by service layer),

    Returns:
        Dictionary with essential journal fields only

    Note:
        Service layer should fetch relationship UIDs using JournalsRelationshipService:
        - related_journal_uids = await journals_relationship_service.get_related_journals(journal.uid)
    """
    # Default to empty list if not provided
    related_journal_uids = related_journal_uids or []
    return {
        # Identity
        "uid": journal.uid,
        # Core content (summary only)
        "title": journal.title,
        "summary": journal.get_summary(max_length=200),
        # Classification
        "content_type": _serialize_enum(journal.content_type),
        "category": _serialize_enum(journal.category),
        # Metadata
        "entry_date": _serialize_date(journal.entry_date),
        "word_count": journal.word_count,
        "reading_time_minutes": round(journal.reading_time_minutes, 2),
        # Status
        "status": _serialize_enum(journal.status),
        # Quick insights
        "mood": journal.mood,
        "energy_level": journal.energy_level,
        "key_topics": journal.key_topics[:5] if journal.key_topics else [],  # Top 5 topics
        "tags": journal.tags[:5] if journal.tags else [],  # Top 5 tags
        # Relations (counts only)
        # GRAPH-NATIVE: related_journal_uids stored as graph relationship
        # Service layer passes these via function parameters
        "related_count": len(related_journal_uids),
        "action_items_count": len(journal.action_items or []),
        # Audit
        "created_at": serialize_datetime_safe(journal.created_at),
        "updated_at": serialize_datetime_safe(journal.updated_at),
        # Computed fields
        "is_recent": journal.is_recent(),
        "is_long_form": journal.is_long_form(),
        "has_insights": journal.has_insights(),
    }


def journals_pure_to_view_list(journals: list[JournalPure]) -> list[dict[str, Any]]:
    """
    Convert list of JournalPure models to full view dictionaries.

    Use this for:
    - Date range queries where full content is needed
    - Export operations
    - Detailed list views

    Args:
        journals: List of JournalPure domain models,

    Returns:
        List of view dictionaries with all fields
    """
    return [journal_pure_to_view(journal) for journal in journals]


def journals_pure_to_summary_list(journals: list[JournalPure]) -> list[dict[str, Any]]:
    """
    Convert list of JournalPure models to summary view dictionaries.

    Use this for:
    - Search results
    - List views
    - Performance-optimized responses
    - Calendar/timeline views

    Args:
        journals: List of JournalPure domain models,

    Returns:
        List of summary view dictionaries (lighter weight)
    """
    return [journal_pure_to_summary_view(journal) for journal in journals]


# ============================================================================
# SPECIALIZED VIEW TRANSFORMATIONS
# ============================================================================


def journal_pure_to_markdown_view(journal: JournalPure) -> dict[str, Any]:
    """
    Convert JournalPure to view with markdown content.

    Use this for:
    - Export operations
    - Markdown preview
    - Publishing workflows

    Args:
        journal: JournalPure domain model,

    Returns:
        Dictionary with markdown representation
    """
    return {
        "uid": journal.uid,
        "title": journal.title,
        "markdown": journal.to_markdown(),
        "entry_date": _serialize_date(journal.entry_date),
        "word_count": journal.word_count,
        "category": _serialize_enum(journal.category),
    }


def journal_pure_to_calendar_view(journal: JournalPure) -> dict[str, Any]:
    """
    Convert JournalPure to calendar event view.

    Use this for:
    - Calendar integrations
    - Timeline views
    - Date-based visualizations

    Args:
        journal: JournalPure domain model,

    Returns:
        Dictionary optimized for calendar display
    """
    return {
        "uid": journal.uid,
        "title": journal.title,
        "date": _serialize_date(journal.entry_date),
        "category": _serialize_enum(journal.category),
        "mood": journal.mood,
        "energy_level": journal.energy_level,
        "word_count": journal.word_count,
        "has_insights": journal.has_insights(),
        "status": _serialize_enum(journal.status),
    }


def journals_pure_to_analytics_view(journals: list[JournalPure]) -> dict[str, Any]:
    """
    Convert list of JournalPure models to analytics view.

    Use this for:
    - Dashboard analytics
    - Statistical summaries
    - Progress tracking

    Args:
        journals: List of JournalPure domain models,

    Returns:
        Dictionary with aggregated analytics data
    """
    if not journals:
        return {
            "total_entries": 0,
            "total_words": 0,
            "average_words": 0,
            "entries_with_insights": 0,
            "categories": {},
            "moods": {},
        }

    total_words = sum(j.word_count for j in journals)
    entries_with_insights = sum(1 for j in journals if j.has_insights())

    # Category breakdown
    categories = {}
    for journal in journals:
        cat = _serialize_enum(journal.category)
        categories[cat] = categories.get(cat, 0) + 1

    # Mood breakdown
    moods = {}
    for journal in journals:
        if journal.mood:
            moods[journal.mood] = moods.get(journal.mood, 0) + 1

    return {
        "total_entries": len(journals),
        "total_words": total_words,
        "average_words": round(total_words / len(journals), 2) if journals else 0,
        "entries_with_insights": entries_with_insights,
        "insight_percentage": round(entries_with_insights / len(journals) * 100, 2)
        if journals
        else 0,
        "categories": categories,
        "moods": moods,
        "date_range": {
            "earliest": _serialize_date(min(j.entry_date for j in journals)),
            "latest": _serialize_date(max(j.entry_date for j in journals)),
        },
    }
