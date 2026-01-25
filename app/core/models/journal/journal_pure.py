"""
Journal Pure Domain Models
===========================

Pure, immutable domain models for Journal (Tier 3 of three-tier architecture).
Frozen dataclasses with business logic, no framework dependencies.

Migrated from schemas_legacy/journal_pure.py to proper location.

Phase 1-4 Integration Status (October 3, 2025):
-----------------------------------------------
⚠️ NOT UPDATED - Excluded from Phase 1-4 integration per user request.

This domain does NOT have Phase 1-4 query building methods.
For future integration, see: /docs/REMAINING_DOMAINS_PHASE_1-4_EVOLUTION_PLAN.md
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

# Journal enums consolidated in /core/models/enums/journal_enums.py (January 2026)
from core.models.enums.journal_enums import (
    ContentStatus,
    ContentType,
    ContentVisibility,
    JournalCategory,
    JournalType,
)

if TYPE_CHECKING:
    from .journal_dto import JournalDTO


# ============================================================================
# JOURNAL PURE MODEL
# ============================================================================


@dataclass(frozen=True)
class JournalPure:
    """
    Pure immutable journal entry domain model.

    Represents a written journal entry or transcribed audio journal.
    All fields are immutable - use factory methods to create modified copies.
    """

    # Identity
    uid: str
    user_uid: str  # REQUIRED - journal entry ownership

    # Core content
    title: str
    content: str

    # Classification
    content_type: ContentType
    journal_type: JournalType = JournalType.CURATED  # Default to permanent tier
    category: JournalCategory = JournalCategory.DAILY

    # Metadata
    entry_date: date = None  # type: ignore[assignment]
    word_count: int = 0
    reading_time_minutes: float = 0.0

    # Status
    status: ContentStatus = ContentStatus.DRAFT
    visibility: ContentVisibility = ContentVisibility.PRIVATE

    # Source information (for transcribed content)
    source_type: str | None = None
    source_file: str | None = None
    transcription_uid: str | None = None

    # Extracted insights
    mood: str | None = None
    energy_level: int | None = None
    key_topics: list[str] = None  # type: ignore[assignment]
    mentioned_people: list[str] = None  # type: ignore[assignment]
    mentioned_places: list[str] = None  # type: ignore[assignment]
    action_items: list[str] = None  # type: ignore[assignment]

    # Relations
    # GRAPH-NATIVE: Relationships stored as Neo4j edges
    # Graph relationship: (journal)-[:RELATED_TO]->(journal)
    # Graph relationship: (journal)-[:SUPPORTS_GOAL]->(goal)
    project_uid: str | None = None  # Single project reference (not a relationship)

    # AI Feedback (optional - only if entry was submitted to a project)
    feedback: str | None = None
    feedback_generated_at: datetime | None = None  # type: ignore[assignment]

    # Metadata
    tags: list[str] = None  # type: ignore[assignment]
    metadata: dict[str, Any] = None  # type: ignore[assignment]

    # Audit
    created_at: datetime = None  # type: ignore[assignment]
    updated_at: datetime = None  # type: ignore[assignment]
    created_by: str | None = None

    def __post_init__(self) -> None:
        """
        Initialize default values for mutable fields.

        GRAPH-NATIVE: related_journal_uids and goal_uids removed - stored as graph edges.
        Use JournalRelationshipService to query relationships.
        """
        if self.entry_date is None:
            object.__setattr__(self, "entry_date", date.today())
        if self.key_topics is None:
            object.__setattr__(self, "key_topics", [])
        if self.mentioned_people is None:
            object.__setattr__(self, "mentioned_people", [])
        if self.mentioned_places is None:
            object.__setattr__(self, "mentioned_places", [])
        if self.action_items is None:
            object.__setattr__(self, "action_items", [])
        if self.tags is None:
            object.__setattr__(self, "tags", [])
        if self.metadata is None:
            object.__setattr__(self, "metadata", {})
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now())
        if self.updated_at is None:
            object.__setattr__(self, "updated_at", datetime.now())

        # Calculate word count and reading time if not set
        if self.word_count == 0 and self.content:
            object.__setattr__(self, "word_count", len(self.content.split()))
        if self.reading_time_minutes == 0 and self.word_count > 0:
            # Average reading speed: 200-250 words per minute
            object.__setattr__(self, "reading_time_minutes", self.word_count / 225)

    # ========================================================================
    # DTO CONVERSION - THREE-TIER ARCHITECTURE
    # ========================================================================

    @classmethod
    def from_dto(cls, dto: JournalDTO) -> JournalPure:
        """
        Create immutable JournalPure from mutable JournalDTO.

        This method maintains consistency with the three-tier architecture
        pattern used across all SKUEL domains.

        Args:
            dto: JournalDTO instance (mutable, from database/API layer)

        Returns:
            Immutable JournalPure domain model

        Note:
            Internally delegates to journal_dto_to_pure converter function.
            This class method exists to satisfy DomainModelProtocol for
            type-safe generic operations (UniversalNeo4jBackend, BaseService).

        Example:
            dto = JournalDTO.from_dict(data)
            journal = JournalPure.from_dto(dto)
        """
        from .journal_converters import journal_dto_to_pure

        return journal_dto_to_pure(dto)

    def to_dto(self) -> JournalDTO:
        """
        Convert immutable JournalPure to mutable JournalDTO.

        Used for database operations and API serialization.

        Returns:
            Mutable JournalDTO instance

        Note:
            Internally delegates to journal_pure_to_dto converter function.
            This instance method exists to satisfy DomainModelProtocol for
            type-safe generic operations.

            Graph-native fields (related_journal_uids, goal_uids) are NOT
            included in the DTO - they must be populated by service layer
            via graph queries.

        Example:
            journal = JournalPure(...)
            dto = journal.to_dto()  # Can modify DTO fields
        """
        from .journal_converters import journal_pure_to_dto

        return journal_pure_to_dto(self)

    # ========================================================================
    # DOMAIN METHODS
    # ========================================================================

    def with_status(self, status: ContentStatus) -> JournalPure:
        """Create new journal with updated status"""
        from .journal_converters import journal_dto_to_pure, journal_pure_to_dto

        dto = journal_pure_to_dto(self)
        dto.status = status
        dto.updated_at = datetime.now()
        return journal_dto_to_pure(dto)

    def publish(self) -> JournalPure:
        """Publish the journal entry"""
        return self.with_status(ContentStatus.PUBLISHED)

    def archive(self) -> JournalPure:
        """Archive the journal entry"""
        return self.with_status(ContentStatus.ARCHIVED)

    def with_insights(
        self,
        mood: str | None = None,
        energy_level: int | None = None,
        key_topics: list[str] | None = None,
        action_items: list[str] | None = None,
    ) -> JournalPure:
        """Update journal with extracted insights"""
        from .journal_converters import journal_dto_to_pure, journal_pure_to_dto

        dto = journal_pure_to_dto(self)
        if mood is not None:
            dto.mood = mood
        if energy_level is not None:
            dto.energy_level = energy_level
        if key_topics is not None:
            dto.key_topics = key_topics
        if action_items is not None:
            dto.action_items = action_items
        dto.updated_at = datetime.now()
        return journal_dto_to_pure(dto)

    # ========================================================================
    # DOMAIN LOGIC
    # ========================================================================

    def is_recent(self, days: int = 7) -> bool:
        """Check if journal entry is recent"""
        delta = date.today() - self.entry_date
        return delta.days <= days

    def is_long_form(self) -> bool:
        """Check if this is a long-form entry (>500 words)"""
        return self.word_count > 500

    def has_insights(self) -> bool:
        """Check if insights have been extracted"""
        return bool(self.mood or self.energy_level or self.key_topics or self.action_items)

    def get_summary(self, max_length: int = 200) -> str:
        """Get a summary of the journal entry"""
        if len(self.content) <= max_length:
            return self.content
        return self.content[: max_length - 3] + "..."

    def to_markdown(self) -> str:
        """Convert journal to markdown format"""
        md = f"# {self.title}\n\n"
        md += f"*{self.entry_date.strftime('%B %d, %Y')}*\n\n"

        if self.mood or self.energy_level:
            md += "## Mood & Energy\n"
            if self.mood:
                md += f"- Mood: {self.mood}\n"
            if self.energy_level:
                md += f"- Energy: {self.energy_level}/10\n"
            md += "\n"

        md += f"{self.content}\n\n"

        if self.action_items:
            md += "## Action Items\n"
            for item in self.action_items:
                md += f"- [ ] {item}\n"
            md += "\n"

        if self.tags:
            md += f"\n---\nTags: {', '.join(self.tags)}"

        return md


# ============================================================================
# FACTORY FUNCTIONS
# ============================================================================


def create_journal(
    uid: str,
    user_uid: str,
    title: str,
    content: str,
    journal_type: JournalType = JournalType.CURATED,
    category: JournalCategory = JournalCategory.DAILY,
    entry_date: date | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> JournalPure:
    """Factory function to create a new journal entry.

    Args:
        uid: Unique identifier
        user_uid: User ownership identifier
        title: Journal title
        content: Journal content
        journal_type: VOICE (ephemeral) or CURATED (permanent). Default: CURATED
        category: Journal category for organization
        entry_date: Date of the journal entry
        tags: Optional tags for categorization
        metadata: Optional additional metadata

    Returns:
        New JournalPure instance
    """
    if not user_uid:
        raise ValueError("user_uid is REQUIRED for journal creation (fail-fast)")

    return JournalPure(
        uid=uid,
        user_uid=user_uid,
        title=title,
        content=content,
        content_type=ContentType.JOURNAL,
        journal_type=journal_type,
        category=category,
        entry_date=entry_date or date.today(),
        tags=tags or [],
        metadata=metadata or {},
        status=ContentStatus.DRAFT,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


def create_journal_from_transcription(
    uid: str,
    user_uid: str,
    title: str,
    transcript_text: str,
    transcription_uid: str,
    audio_file_path: str,
    original_filename: str | None = None,
    transcript_confidence: float | None = None,
    audio_duration: float | None = None,
    journal_type: JournalType = JournalType.VOICE,
    category: JournalCategory = JournalCategory.DAILY,
) -> JournalPure:
    """Factory function to create journal from audio transcription.

    Args:
        uid: Unique identifier
        user_uid: User ownership identifier
        title: Journal title
        transcript_text: Transcribed text content
        transcription_uid: UID of the transcription record
        audio_file_path: Path to the source audio file
        original_filename: Original filename before upload
        transcript_confidence: Transcription confidence score
        audio_duration: Duration of the audio in seconds
        journal_type: VOICE (default) for audio, or CURATED for curated transcripts
        category: Journal category for organization

    Returns:
        New JournalPure instance

    Note:
        Default journal_type is VOICE since audio transcriptions are typically
        ephemeral voice journals (PJ1). Pass journal_type=JournalType.CURATED
        if the transcription should be permanently retained.
    """
    if not user_uid:
        raise ValueError("user_uid is REQUIRED for journal creation (fail-fast)")

    return JournalPure(
        uid=uid,
        user_uid=user_uid,
        title=title,
        content=transcript_text,
        content_type=ContentType.AUDIO_TRANSCRIPT,
        journal_type=journal_type,
        category=category,
        entry_date=date.today(),
        source_type="audio",
        source_file=audio_file_path,
        transcription_uid=transcription_uid,
        status=ContentStatus.TRANSCRIBED,
        metadata={
            "audio_duration": audio_duration,
            "original_filename": original_filename,
            "transcription_confidence": transcript_confidence,
        },
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
