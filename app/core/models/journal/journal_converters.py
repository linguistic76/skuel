"""
Journal Model Converters
========================

Conversion functions between the three tiers:
- Request (Pydantic) <-> DTO <-> Pure (Domain)
"""

import uuid
from datetime import date, datetime
from typing import Any

from .journal_dto import (
    AnalysisDepth,
    ContentStatus,
    ContentType,
    ContentVisibility,
    ContextEnrichmentLevel,
    FormattingStyle,
    JournalCategory,
    JournalDTO,
    JournalType,
    TranscriptProcessingInstructionsDTO,
)
from .journal_pure import JournalPure
from .journal_request import JournalCreateRequest, JournalUpdateRequest, TranscriptProcessingRequest

# ============================================================================
# JOURNAL CONVERTERS
# ============================================================================


def journal_create_request_to_dto(
    request: JournalCreateRequest, user_uid: str | None = None
) -> JournalDTO:
    """Convert JournalCreateRequest to JournalDTO"""
    return JournalDTO(
        uid=str(uuid.uuid4()),  # Generate new UID
        user_uid=user_uid or "unknown",  # REQUIRED field
        title=request.title,
        content=request.content,
        content_type=ContentType(request.content_type),
        category=JournalCategory(request.category),
        entry_date=request.entry_date,
        status=ContentStatus(request.status),
        visibility=ContentVisibility(request.visibility),
        project_uid=request.project_uid,
        goal_uids=request.goal_uids,
        related_journal_uids=request.related_journal_uids,
        mood=request.mood,
        energy_level=request.energy_level,
        key_topics=request.key_topics,
        mentioned_people=request.mentioned_people,
        mentioned_places=request.mentioned_places,
        action_items=request.action_items,
        tags=request.tags,
        source_type=request.source_type,
        source_file=request.source_file,
        transcription_uid=request.transcription_uid,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        created_by=user_uid,
    )


def journal_update_request_to_dto(
    request: JournalUpdateRequest, existing: JournalDTO
) -> JournalDTO:
    """Apply JournalUpdateRequest to existing JournalDTO"""
    # Update only provided fields
    if request.title is not None:
        existing.title = request.title
    if request.content is not None:
        existing.content = request.content
        # Recalculate word count and reading time
        existing.word_count = len(request.content.split())
        existing.reading_time_minutes = existing.word_count / 225
    if request.category is not None:
        existing.category = JournalCategory(request.category)
    if request.entry_date is not None:
        existing.entry_date = request.entry_date
    if request.status is not None:
        existing.status = ContentStatus(request.status)
    if request.visibility is not None:
        existing.visibility = ContentVisibility(request.visibility)
    if request.project_uid is not None:
        existing.project_uid = request.project_uid
    if request.goal_uids is not None:
        existing.goal_uids = request.goal_uids
    if request.related_journal_uids is not None:
        existing.related_journal_uids = request.related_journal_uids
    if request.mood is not None:
        existing.mood = request.mood
    if request.energy_level is not None:
        existing.energy_level = request.energy_level
    if request.key_topics is not None:
        existing.key_topics = request.key_topics
    if request.mentioned_people is not None:
        existing.mentioned_people = request.mentioned_people
    if request.mentioned_places is not None:
        existing.mentioned_places = request.mentioned_places
    if request.action_items is not None:
        existing.action_items = request.action_items
    if request.tags is not None:
        existing.tags = request.tags

    existing.updated_at = datetime.now()
    return existing


def journal_dto_to_pure(dto: JournalDTO) -> JournalPure:
    """
    Convert JournalDTO to JournalPure.

    Note: related_journal_uids and goal_uids are graph relationships,
    not fields on JournalPure. They're stored as Neo4j edges.
    """
    return JournalPure(
        uid=dto.uid,
        user_uid=dto.user_uid,  # Now JournalDTO has user_uid
        title=dto.title,
        content=dto.content,
        content_type=dto.content_type,
        journal_type=dto.journal_type,
        category=dto.category,
        entry_date=dto.entry_date,
        word_count=dto.word_count,
        reading_time_minutes=dto.reading_time_minutes,
        status=dto.status,
        visibility=dto.visibility,
        source_type=dto.source_type,
        source_file=dto.source_file,
        transcription_uid=dto.transcription_uid,
        mood=dto.mood,
        energy_level=dto.energy_level,
        key_topics=dto.key_topics.copy() if dto.key_topics else [],
        mentioned_people=dto.mentioned_people.copy() if dto.mentioned_people else [],
        mentioned_places=dto.mentioned_places.copy() if dto.mentioned_places else [],
        action_items=dto.action_items.copy() if dto.action_items else [],
        # Note: related_journal_uids and goal_uids are graph relationships, not fields
        project_uid=dto.project_uid,
        tags=dto.tags.copy() if dto.tags else [],
        metadata=dto.metadata.copy() if dto.metadata else {},
        created_at=dto.created_at,
        updated_at=dto.updated_at,
        created_by=dto.created_by,
    )


def journal_pure_to_dto(pure: JournalPure) -> JournalDTO:
    """
    Convert JournalPure to JournalDTO.

    GRAPH-NATIVE: Relationship fields (related_journal_uids, goal_uids) set to empty lists.
    Service layer must populate via graph queries:
    - related_journal_uids: backend.get_related_uids(uid, "RELATED_TO", "both")
    - goal_uids: backend.get_related_uids(uid, "SUPPORTS_GOAL", "outgoing")
    """
    return JournalDTO(
        uid=pure.uid,
        user_uid=pure.user_uid,  # Now JournalDTO has user_uid
        title=pure.title,
        content=pure.content,
        content_type=pure.content_type,
        journal_type=pure.journal_type,
        category=pure.category,
        entry_date=pure.entry_date,
        word_count=pure.word_count,
        reading_time_minutes=pure.reading_time_minutes,
        status=pure.status,
        visibility=pure.visibility,
        source_type=pure.source_type,
        source_file=pure.source_file,
        transcription_uid=pure.transcription_uid,
        mood=pure.mood,
        energy_level=pure.energy_level,
        key_topics=pure.key_topics.copy() if pure.key_topics else [],
        mentioned_people=pure.mentioned_people.copy() if pure.mentioned_people else [],
        mentioned_places=pure.mentioned_places.copy() if pure.mentioned_places else [],
        action_items=pure.action_items.copy() if pure.action_items else [],
        related_journal_uids=[],  # GRAPH QUERY: backend.get_related_uids(uid, "RELATED_TO", "both")
        project_uid=pure.project_uid,
        goal_uids=[],  # GRAPH QUERY: backend.get_related_uids(uid, "SUPPORTS_GOAL", "outgoing")
        tags=pure.tags.copy() if pure.tags else [],
        metadata=pure.metadata.copy() if pure.metadata else {},
        created_at=pure.created_at,
        updated_at=pure.updated_at,
        created_by=pure.created_by,
    )


def journal_dto_to_response(dto: JournalDTO) -> dict[str, Any]:
    """Convert JournalDTO to API response format"""
    return {
        "uid": dto.uid,
        "title": dto.title,
        "content": dto.content,
        "content_type": dto.content_type.value,
        "journal_type": dto.journal_type.value,
        "category": dto.category.value,
        "entry_date": dto.entry_date.isoformat(),
        "word_count": dto.word_count,
        "reading_time_minutes": dto.reading_time_minutes,
        "status": dto.status.value,
        "visibility": dto.visibility.value,
        "source_type": dto.source_type,
        "source_file": dto.source_file,
        "transcription_uid": dto.transcription_uid,
        "mood": dto.mood,
        "energy_level": dto.energy_level,
        "key_topics": dto.key_topics,
        "mentioned_people": dto.mentioned_people,
        "mentioned_places": dto.mentioned_places,
        "action_items": dto.action_items,
        "related_journal_uids": dto.related_journal_uids,
        "project_uid": dto.project_uid,
        "goal_uids": dto.goal_uids,
        "tags": dto.tags,
        "is_recent": (date.today() - dto.entry_date).days <= 7,
        "is_long_form": dto.word_count > 500,
        "is_ephemeral": dto.journal_type.is_ephemeral(),
        "has_insights": bool(dto.mood or dto.energy_level or dto.key_topics or dto.action_items),
        "summary": dto.content[:200] + "..." if len(dto.content) > 200 else dto.content,
        "created_at": dto.created_at.isoformat(),
        "updated_at": dto.updated_at.isoformat(),
        "created_by": dto.created_by,
    }


# ============================================================================
# TRANSCRIPT PROCESSING CONVERTERS
# ============================================================================


def transcript_request_to_instructions_dto(
    request: TranscriptProcessingRequest,
) -> TranscriptProcessingInstructionsDTO:
    """Convert TranscriptProcessingRequest to TranscriptProcessingInstructionsDTO"""
    return TranscriptProcessingInstructionsDTO(
        formatting_style=FormattingStyle(request.formatting_style),
        analysis_depth=AnalysisDepth(request.analysis_depth),
        enterprise_integration=request.enterprise_integration,
        context_enrichment=ContextEnrichmentLevel(request.context_enrichment),
        auto_categorization=request.auto_categorization,
        extract_action_items=request.extract_action_items,
        identify_entities=request.identify_entities,
        suggest_connections=request.suggest_connections,
        include_summary=request.include_summary,
        preserve_original=request.preserve_original,
        generate_title=request.generate_title,
    )


def create_journal_from_transcript(
    request: TranscriptProcessingRequest,
    processed_title: str,
    processed_content: str,
    detected_category: JournalCategory = JournalCategory.DAILY,
    journal_type: JournalType = JournalType.VOICE,
    user_uid: str | None = None,
) -> JournalDTO:
    """Create a JournalDTO from a processed transcript.

    Args:
        request: Original transcript processing request
        processed_title: AI-generated title
        processed_content: AI-formatted content
        detected_category: Detected category from AI processing
        journal_type: VOICE (ephemeral) or CURATED (permanent). Default: VOICE
        user_uid: User identifier

    Returns:
        JournalDTO ready for persistence

    Note:
        Default journal_type is VOICE since audio transcriptions are typically
        ephemeral voice journals (PJ1). Pass journal_type=JournalType.CURATED
        if the transcription should be permanently retained.
    """
    metadata = {
        "original_transcript": request.transcript_text if request.preserve_original else None,
        "audio_file": request.audio_file_path,
        "formatting_style": request.formatting_style,
        "analysis_depth": request.analysis_depth,
    }

    return JournalDTO(
        uid=str(uuid.uuid4()),
        user_uid=user_uid or request.user_uid or "unknown",  # REQUIRED field
        title=processed_title,
        content=processed_content,
        content_type=ContentType.AUDIO_TRANSCRIPT,
        journal_type=journal_type,
        category=detected_category,
        entry_date=date.today(),
        status=ContentStatus.TRANSCRIBED,
        visibility=ContentVisibility.PRIVATE,
        source_type="audio",
        source_file=request.audio_file_path,
        transcription_uid=request.transcription_uid,
        metadata=metadata,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        created_by=user_uid or request.user_uid,
    )
