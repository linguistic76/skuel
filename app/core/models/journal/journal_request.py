"""
Journal Request Models (Pydantic)
==================================

Pydantic models for Journal API boundaries (Tier 1 of three-tier architecture).
Handles validation and serialization at the API layer.

Based on journal_schemas.py but aligned with three-tier pattern.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Type literals for strict validation
ContentTypeLiteral = Literal["journal", "audio_transcript", "note", "article", "reflection"]
ContentStatusLiteral = Literal["draft", "transcribed", "processed", "published", "archived"]
ContentVisibilityLiteral = Literal["private", "shared", "public"]
JournalCategoryLiteral = Literal[
    "daily",
    "weekly",
    "monthly",
    "reflection",
    "gratitude",
    "goals",
    "ideas",
    "dreams",
    "health",
    "work",
    "personal",
    "learning",
    "project",
    "other",
]
FormattingStyleLiteral = Literal[
    "structured", "narrative", "bullet_points", "conversational", "executive_summary"
]
AnalysisDepthLiteral = Literal["basic", "detailed", "comprehensive"]
ContextEnrichmentLiteral = Literal["none", "basic", "standard", "deep"]


# ============================================================================
# JOURNAL REQUEST MODELS
# ============================================================================


class JournalCreateRequest(BaseModel):
    """Request model for creating a journal entry"""

    # Core fields
    title: str = Field(min_length=1, max_length=200, description="Journal entry title")
    content: str = Field(min_length=1, description="Journal entry content")

    # Classification
    content_type: ContentTypeLiteral = Field(default="journal", description="Content type")
    category: JournalCategoryLiteral = Field(default="daily", description="Journal category")

    # Timing
    entry_date: date = Field(default_factory=date.today, description="Date this entry is about")

    # Status
    status: ContentStatusLiteral = Field(default="draft", description="Content status")
    visibility: ContentVisibilityLiteral = Field(default="private", description="Visibility level")

    # Relations
    project_uid: str | None = Field(default=None, description="Associated project UID")
    goal_uids: list[str] = Field(default_factory=list, description="Associated goal UIDs")
    related_journal_uids: list[str] = Field(
        default_factory=list, description="Related journal UIDs"
    )

    # Insights (optional at creation)
    mood: str | None = Field(default=None, max_length=50, description="Mood description")
    energy_level: int | None = Field(default=None, ge=1, le=10, description="Energy level 1-10")
    key_topics: list[str] = Field(default_factory=list, description="Key topics mentioned")
    mentioned_people: list[str] = Field(default_factory=list, description="People mentioned")
    mentioned_places: list[str] = Field(default_factory=list, description="Places mentioned")
    action_items: list[str] = Field(default_factory=list, description="Action items identified")

    # Metadata
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")

    # Source information (for transcribed content)
    source_type: str | None = Field(default=None, description="Source type (audio, text, import)")
    source_file: str | None = Field(default=None, description="Source file path")
    transcription_uid: str | None = Field(default=None, description="Linked transcription UID")

    @field_validator("content")
    @classmethod
    def validate_content_length(cls, v: str) -> str:
        """Validate content is not too long"""
        if len(v) > 100000:  # 100k character limit
            raise ValueError("Content exceeds maximum length of 100,000 characters")
        return v

    @field_validator("energy_level")
    @classmethod
    def validate_energy_level(cls, v: int | None) -> int | None:
        """Ensure energy level is in valid range"""
        if v is not None and (v < 1 or v > 10):
            raise ValueError("Energy level must be between 1 and 10")
        return v


class JournalUpdateRequest(BaseModel):
    """Request model for updating a journal entry"""

    # Core fields (all optional for updates)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1)

    # Classification
    category: JournalCategoryLiteral | None = Field(default=None)
    entry_date: date | None = Field(default=None)

    # Status
    status: ContentStatusLiteral | None = Field(default=None)
    visibility: ContentVisibilityLiteral | None = Field(default=None)

    # Relations
    project_uid: str | None = Field(default=None)
    goal_uids: list[str] | None = Field(default=None)
    related_journal_uids: list[str] | None = Field(default=None)

    # Insights
    mood: str | None = Field(default=None, max_length=50)
    energy_level: int | None = Field(default=None, ge=1, le=10)
    key_topics: list[str] | None = Field(default=None)
    mentioned_people: list[str] | None = Field(default=None)
    mentioned_places: list[str] | None = Field(default=None)
    action_items: list[str] | None = Field(default=None)

    # Metadata
    tags: list[str] | None = Field(default=None)

    @field_validator("content")
    @classmethod
    def validate_content_length(cls, v: str | None) -> str | None:
        """Validate content is not too long"""
        if v is not None and len(v) > 100000:
            raise ValueError("Content exceeds maximum length of 100,000 characters")
        return v


# ============================================================================
# FILTER REQUEST MODELS
# ============================================================================


class JournalFilterRequest(BaseModel):
    """Request model for filtering and searching journals"""

    # Date filters
    start_date: date | None = Field(default=None, description="Filter from date")
    end_date: date | None = Field(default=None, description="Filter to date")

    # Content filters
    categories: list[JournalCategoryLiteral] | None = Field(default=None)
    statuses: list[ContentStatusLiteral] | None = Field(default=None)
    content_types: list[ContentTypeLiteral] | None = Field(default=None)

    # Length filters
    min_word_count: int | None = Field(default=None, ge=0)
    max_word_count: int | None = Field(default=None, gt=0)

    # Insight filters
    has_mood: bool | None = Field(default=None)
    has_energy_level: bool | None = Field(default=None)
    has_action_items: bool | None = Field(default=None)
    mood: str | None = Field(default=None)
    min_energy_level: int | None = Field(default=None, ge=1, le=10)
    max_energy_level: int | None = Field(default=None, ge=1, le=10)

    # Text search
    search_query: str | None = Field(
        default=None, max_length=100, description="Search in title and content"
    )

    # Associations
    project_uid: str | None = Field(default=None)
    has_project: bool | None = Field(default=None)

    # Tags and topics
    tags: list[str] | None = Field(default=None)
    topics: list[str] | None = Field(default=None)

    # Source filters
    source_type: str | None = Field(default=None)
    has_transcription: bool | None = Field(default=None)

    @field_validator("end_date")
    @classmethod
    def validate_date_range(cls, v: date | None, info) -> date | None:
        """Ensure end_date is after start_date"""
        if v is None:
            return v
        start_date = info.data.get("start_date")
        if start_date and v <= start_date:
            raise ValueError("end_date must be after start_date")
        return v

    @field_validator("max_energy_level")
    @classmethod
    def validate_energy_range(cls, v: int | None, info) -> int | None:
        """Ensure max_energy_level is greater than min_energy_level"""
        if v is None:
            return v
        min_level = info.data.get("min_energy_level")
        if min_level is not None and v <= min_level:
            raise ValueError("max_energy_level must be greater than min_energy_level")
        return v


# ============================================================================
# TRANSCRIPT PROCESSING REQUEST MODELS
# ============================================================================


class TranscriptProcessingRequest(BaseModel):
    """Request model for processing raw transcripts into formatted journals"""

    # Source transcript
    transcript_text: str = Field(description="Raw transcript text to process")
    transcription_uid: str | None = Field(default=None, description="UID of source transcription")
    audio_file_path: str | None = Field(default=None, description="Path to source audio file")

    # Processing options
    formatting_style: FormattingStyleLiteral = Field(
        default="structured", description="Style for formatting the transcript"
    )
    analysis_depth: AnalysisDepthLiteral = Field(
        default="detailed", description="Depth of analysis for processing"
    )

    # SKUEL enterprise integration
    enterprise_integration: bool = Field(
        default=True, description="Enable enterprise context integration"
    )
    context_enrichment: ContextEnrichmentLiteral = Field(
        default="standard", description="Level of context enrichment"
    )

    # Content extraction flags
    auto_categorization: bool = Field(default=True, description="Auto-categorize the journal")
    extract_action_items: bool = Field(default=True, description="Extract action items")
    identify_entities: bool = Field(default=True, description="Identify people, places, concepts")
    suggest_connections: bool = Field(default=True, description="Suggest related knowledge")

    # Output preferences
    include_summary: bool = Field(default=True, description="Generate a summary")
    preserve_original: bool = Field(default=True, description="Keep raw transcript as metadata")
    generate_title: bool = Field(default=True, description="Auto-generate a title")

    # User context (optional)
    user_uid: str | None = Field(default=None, description="User UID for personalization")
    current_projects: list[str] | None = Field(default=None, description="Current project UIDs")
    preferred_categories: list[JournalCategoryLiteral] | None = Field(default=None)


# ============================================================================
# INSIGHT EXTRACTION REQUEST MODELS
# ============================================================================


class JournalInsightExtractionRequest(BaseModel):
    """Request model for extracting insights from journal content"""

    journal_uid: str = Field(description="UID of journal to analyze")

    # Extraction options
    extract_mood: bool = Field(default=True, description="Extract mood")
    extract_energy: bool = Field(default=True, description="Extract energy level")
    extract_topics: bool = Field(default=True, description="Extract key topics")
    extract_people: bool = Field(default=True, description="Extract mentioned people")
    extract_places: bool = Field(default=True, description="Extract mentioned places")
    extract_actions: bool = Field(default=True, description="Extract action items")

    # Analysis depth
    use_ai_analysis: bool = Field(default=True, description="Use AI for deeper analysis")
    connect_to_knowledge: bool = Field(default=True, description="Connect to knowledge graph")


# ============================================================================
# BULK OPERATION REQUEST MODELS
# ============================================================================


class JournalBulkUpdateRequest(BaseModel):
    """Request model for bulk updating multiple journals"""

    journal_uids: list[str] = Field(min_length=1, description="Journal UIDs to update")
    updates: JournalUpdateRequest = Field(description="Updates to apply")


class JournalExportRequest(BaseModel):
    """Request model for exporting journals"""

    format: Literal["markdown", "json", "pdf", "html"] = Field(default="markdown")
    filters: JournalFilterRequest | None = Field(default=None)
    include_metadata: bool = Field(default=True)
    include_insights: bool = Field(default=True)
    combine_into_single_file: bool = Field(default=False)


# ============================================================================
# ANALYTICS REQUEST MODELS
# ============================================================================


class JournalAnalyticsRequest(BaseModel):
    """Request model for journal analytics"""

    # Time period
    start_date: date = Field(description="Analytics start date")
    end_date: date = Field(description="Analytics end date")

    # Analysis options
    include_mood_trends: bool = Field(default=True)
    include_energy_trends: bool = Field(default=True)
    include_topic_analysis: bool = Field(default=True)
    include_writing_patterns: bool = Field(default=True)
    include_action_item_stats: bool = Field(default=True)

    # Grouping
    group_by: Literal["day", "week", "month", "category"] | None = Field(default="week")

    # Filters
    categories: list[JournalCategoryLiteral] | None = Field(default=None)
    min_word_count: int | None = Field(default=None, ge=0)

    @field_validator("end_date")
    @classmethod
    def validate_date_range(cls, v: date, info) -> date:
        """Ensure end_date is after start_date"""
        start_date = info.data.get("start_date")
        if start_date and v <= start_date:
            raise ValueError("end_date must be after start_date")
        return v
