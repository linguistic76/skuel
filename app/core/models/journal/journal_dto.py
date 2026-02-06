"""
Journal DTO Models
==================

Data Transfer Objects for Journal domain (Tier 2 of three-tier architecture).
Mutable dataclasses for transferring data between layers.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any

# Journal enums consolidated in /core/models/enums/report_enums.py (February 2026)
from core.models.enums.metadata_enums import Visibility as ContentVisibility
from core.models.enums.report_enums import (
    ContentStatus,
    ContentType,
    JournalCategory,
    JournalType,
)


class FormattingStyle(Enum):
    """Style for formatting transcripts"""

    STRUCTURED = "structured"
    NARRATIVE = "narrative"
    BULLET_POINTS = "bullet_points"
    CONVERSATIONAL = "conversational"
    EXECUTIVE_SUMMARY = "executive_summary"


class AnalysisDepth(Enum):
    """Depth of analysis for transcript processing"""

    BASIC = "basic"
    DETAILED = "detailed"
    COMPREHENSIVE = "comprehensive"


class ContextEnrichmentLevel(Enum):
    """Level of SKUEL enterprise context integration"""

    NONE = "none"
    BASIC = "basic"
    STANDARD = "standard"
    DEEP = "deep"


# ============================================================================
# JOURNAL DTOs
# ============================================================================


@dataclass
class JournalDTO:
    """
    Mutable DTO for journal data transfer between layers.

    Used to move data between:
    - API layer (Pydantic) and Service layer
    - Service layer and Repository/Backend layer
    - Service layer and Domain model (Pure)
    """

    # Identity
    uid: str
    user_uid: str  # REQUIRED - journal entry ownership

    # Core content
    title: str
    content: str

    # Classification
    content_type: ContentType
    journal_type: JournalType = JournalType.CURATED
    category: JournalCategory = JournalCategory.DAILY

    # Metadata
    entry_date: date = field(default_factory=date.today)
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
    key_topics: list[str] = field(default_factory=list)
    mentioned_people: list[str] = field(default_factory=list)
    mentioned_places: list[str] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)

    # Relations - GRAPH-NATIVE: Query via JournalRelationshipService
    # Graph relationship: (journal)-[:RELATED_TO]->(journal)
    related_journal_uids: list[str] = field(default_factory=list)  # Populated from service layer
    project_uid: str | None = None  # Single project reference (not a relationship)
    # Graph relationship: (journal)-[:SUPPORTS_GOAL]->(goal)
    goal_uids: list[str] = field(default_factory=list)  # Populated from service layer

    # AI Feedback (optional - only if entry was submitted to a project)
    feedback: str | None = None
    feedback_generated_at: datetime | None = None

    # Metadata
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Audit
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    created_by: str | None = None

    def __post_init__(self) -> None:
        """Calculate word count and reading time if not set"""
        if self.word_count == 0 and self.content:
            self.word_count = len(self.content.split())
        if self.reading_time_minutes == 0 and self.word_count > 0:
            # Average reading speed: 200-250 words per minute
            self.reading_time_minutes = self.word_count / 225

    def to_dict(self) -> dict[str, Any]:
        """Convert DTO to dictionary for serialization"""
        from dataclasses import asdict

        from core.models.dto_helpers import (
            convert_dates_to_iso,
            convert_datetimes_to_iso,
            convert_enums_to_values,
        )

        data = asdict(self)

        # Convert enums to values
        convert_enums_to_values(
            data, ["content_type", "journal_type", "category", "status", "visibility"]
        )

        # Convert dates to ISO format
        convert_dates_to_iso(data, ["entry_date"])

        # Convert datetimes to ISO format
        convert_datetimes_to_iso(data, ["created_at", "updated_at", "feedback_generated_at"])

        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JournalDTO":
        """Create DTO from dictionary"""
        from core.models.dto_helpers import (
            parse_date_fields,
            parse_datetime_fields,
            parse_enum_field,
        )

        # Parse dates
        parse_date_fields(data, ["entry_date"])

        # Parse datetimes
        parse_datetime_fields(data, ["created_at", "updated_at", "feedback_generated_at"])

        # Parse enums
        parse_enum_field(data, "content_type", ContentType)
        parse_enum_field(data, "journal_type", JournalType)
        parse_enum_field(data, "category", JournalCategory)
        parse_enum_field(data, "status", ContentStatus)
        parse_enum_field(data, "visibility", ContentVisibility)

        return cls(**data)


# ============================================================================
# TRANSCRIPT PROCESSING DTOs
# ============================================================================


@dataclass
class TranscriptProcessingInstructionsDTO:
    """DTO for transcript processing instructions"""

    # Core processing options
    formatting_style: FormattingStyle = FormattingStyle.STRUCTURED
    analysis_depth: AnalysisDepth = AnalysisDepth.DETAILED

    # SKUEL enterprise integration
    enterprise_integration: bool = True
    context_enrichment: ContextEnrichmentLevel = ContextEnrichmentLevel.STANDARD

    # Content extraction flags
    auto_categorization: bool = True
    extract_action_items: bool = True
    identify_entities: bool = True
    suggest_connections: bool = True

    # Output preferences
    include_summary: bool = True
    preserve_original: bool = True
    generate_title: bool = True

    # User-specific customizations
    custom_formatting_rules: dict[str, Any] | None = None


@dataclass
class ProcessedTranscriptResultDTO:
    """DTO for processed transcript results"""

    # Core journal content
    journal: JournalDTO

    # Processing insights
    detected_entities: dict[str, list[str]] = field(default_factory=dict)
    suggested_connections: list[str] = field(default_factory=list)
    confidence_score: float = 0.0

    # Enhancement suggestions
    recommended_tags: list[str] = field(default_factory=list)
    suggested_category: JournalCategory | None = None
    follow_up_actions: list[str] | None = None

    # Processing metadata
    processing_instructions_used: TranscriptProcessingInstructionsDTO | None = None
    processing_timestamp: datetime | None = None


@dataclass
class SKUELEnterpriseContext:
    """Enterprise context for SKUEL transcript processing"""

    user_id: str | None = None
    user_preferences: dict[str, Any] | None = None
    current_projects: list[str] | None = None
    active_knowledge_domains: list[str] | None = None
    recent_journal_themes: list[str] | None = None
    known_people: list[str] | None = None
    known_places: list[str] | None = None
    enterprise_concepts: dict[str, Any] | None = None
    preferred_categories: list[JournalCategory] | None = None
    formatting_templates: dict[str, str] | None = None


# ============================================================================
# ANALYTICS DTOs
# ============================================================================


@dataclass
class JournalAnalyticsDTO:
    """DTO for journal analytics data"""

    # Time period
    period_start: date
    period_end: date

    # Entry metrics
    total_entries: int = 0
    total_words: int = 0
    average_words_per_entry: float = 0.0
    longest_entry_words: int = 0

    # Category breakdown
    category_counts: dict[str, int] = field(default_factory=dict)
    category_word_counts: dict[str, int] = field(default_factory=dict)

    # Status breakdown
    status_counts: dict[str, int] = field(default_factory=dict)

    # Writing patterns
    entries_by_day: dict[str, int] = field(default_factory=dict)
    entries_by_month: dict[str, int] = field(default_factory=dict)

    # Mood and energy trends
    mood_frequency: dict[str, int] = field(default_factory=dict)
    average_energy_level: float | None = None
    energy_trend: list[float] = field(default_factory=list)

    # Content insights
    top_topics: list[str] = field(default_factory=list)
    total_action_items: int = 0
    completed_action_items: int = 0

    # Writing consistency
    streak_days: int = 0
    longest_streak: int = 0
    entries_per_week: float = 0.0

    # Metadata
    generated_at: datetime = field(default_factory=datetime.now)


@dataclass
class JournalExportDTO:
    """DTO for journal export data"""

    format: str
    journals: list[JournalDTO]
    include_metadata: bool = True
    include_insights: bool = True
    export_timestamp: datetime = field(default_factory=datetime.now)
    total_count: int = 0
    total_words: int = 0

    def __post_init__(self) -> None:
        """Calculate totals"""
        if self.journals:
            self.total_count = len(self.journals)
            self.total_words = sum(j.word_count for j in self.journals)
