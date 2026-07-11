"""
SKUEL Enums - Centralized Enumeration Types
============================================

This module provides unified access to all SKUEL enumerations.

Module Organization:
- entity_enums: EntityType, EntityStatus, ContentOrigin,
                Domain, NonKuDomain, DomainIdentifier, AnalyticsDomain, ContentScope, Context
- activity_enums: Priority, Confidence, ActivityType, dual-track assessment levels
- goal_enums: GoalType, GoalTimeframe, MeasurementType, HabitEssentiality
- habit_enums: HabitPolarity, HabitCategory, HabitDifficulty, CompletionStatus
- choice_enums: ChoiceType
- principle_enums: TriggerType, PrincipleCategory, PrincipleSource, PrincipleStrength, AlignmentLevel
- user_entry_enums: SubmissionModality, ExerciseScope, EnrichmentMode, FormattingStyle, AnalysisDepth,
                    ContextEnrichmentLevel, ScheduleType, ProgressDepth
- curriculum_enums: LpType, StepDifficulty
- lifepath_enums: ThemeCategory
- scheduling_enums: RecurrencePattern, TimeOfDay, EnergyLevel
- learning_enums: MasteryImpact, LearningLevel, EducationalLevel, MasteryStatus, KnowledgeStatus, etc.
- metadata_enums: RelationshipType, Intent, Visibility, SystemConstants, etc.
- askesis_enums: QueryComplexity, IntegrationSuccess
- transcription_enums: TranscriptionStatus

Usage:
    from core.models.enums import Priority, EntityStatus, EntityType
    from core.models.enums import EntityType, EntityStatus, ReportSource, ExerciseScope
"""

# Askesis enums - pedagogical companion interaction styles
# Activity enums - priority, confidence, calendar types, and assessment levels
from .activity_enums import (
    ActivityType,
    Confidence,
    ConsistencyLevel,
    DecisionQualityLevel,
    DualTrackDimension,
    EngagementLevel,
    EngagementState,
    MasteryLevel,
    Priority,
    ProductivityLevel,
    ProgressLevel,
)
from .askesis_enums import IntegrationSuccess, QueryComplexity

# Choice enums
from .choice_enums import ChoiceType

# Curriculum enums - learning path and step classification
from .curriculum_enums import LpType, StepDifficulty

# Entity enums - core identity, lifecycle, and domain classification
from .entity_enums import (
    AnalyticsDomain,
    ContentOrigin,
    ContentScope,
    Context,
    Domain,
    DomainIdentifier,
    EntityStatus,
    EntityType,
    NonKuDomain,
)

# Goal enums
from .goal_enums import GoalTimeframe, GoalType, HabitEssentiality, MeasurementType

# Habit enums
from .habit_enums import CompletionStatus, HabitCategory, HabitDifficulty, HabitPolarity

# Learning enums - education, knowledge, and mastery tracking
from .learning_enums import (
    DOMAIN_SEL_MAPPING,
    AssessmentOutcome,
    ContentType,
    EducationalLevel,
    FeedbackCategory,
    KnowledgeStatus,
    KnowledgeType,
    KuComplexity,
    LearningLevel,
    MasteryImpact,
    MasteryStatus,
    PracticeLevel,
    SELCategory,
)

# Life path enums
from .lifepath_enums import ThemeCategory

# Metadata enums - relationships, UI, search, and system configuration
from .metadata_enums import (
    BridgeType,
    CacheStrategy,
    ConversationState,
    ErrorSeverity,
    ExtractionMethod,
    FacetType,
    GuidanceMode,
    HealthStatus,
    Intent,
    LearningModality,
    MessageRole,
    Personality,
    RelationshipType,
    ResponseTone,
    SearchScope,
    SearchVisibility,
    SeverityLevel,
    SystemConstants,
    TrendDirection,
    Visibility,
)

# Neo4j labels - single source of truth for node labels
from .neo_labels import NeoLabel

# Pipeline + ReportSource (ADR-054) — replaces ProcessorType; JeUse scopes je_pro files
from .pipeline import JeUse, Pipeline, ReportSource

# Principle enums
from .principle_enums import (
    AlignmentLevel,
    PrincipleCategory,
    PrincipleSource,
    PrincipleStrength,
    TriggerType,
)

# Scheduling enums - time, recurrence, and energy management
from .scheduling_enums import (
    EnergyLevel,
    RecurrencePattern,
    TimeOfDay,
)

# Transcription enums
from .transcription_enums import TranscriptionStatus

# User entry enums - processing and scheduling (renamed from submissions_enums)
from .user_entry_enums import (
    AnalysisDepth,
    ContextEnrichmentLevel,
    EnrichmentMode,
    ExerciseScope,
    FormattingStyle,
    ProgressDepth,
    ScheduleType,
    SubmissionModality,
)

# User enums - roles, health scoring, and account management
from .user_enums import ContextHealthScore, JournalMode, JournalTier, UserRole, UserStatus

__all__ = [
    "DOMAIN_SEL_MAPPING",
    "ActivityType",
    "AlignmentLevel",
    "AssessmentOutcome",
    "AnalyticsDomain",
    "AnalysisDepth",
    "BridgeType",
    "CacheStrategy",
    "ChoiceType",
    "CompletionStatus",
    "Confidence",
    "ConsistencyLevel",
    "ContentOrigin",
    "ContentScope",
    "ContentType",
    "Context",
    "ContextEnrichmentLevel",
    "ContextHealthScore",
    "ConversationState",
    "DecisionQualityLevel",
    "DualTrackDimension",
    "Domain",
    "DomainIdentifier",
    "EducationalLevel",
    "FeedbackCategory",
    "EnrichmentMode",
    "EngagementLevel",
    "EngagementState",
    "EnergyLevel",
    "EntityStatus",
    "EntityType",
    "ErrorSeverity",
    "ExtractionMethod",
    "FacetType",
    "FormattingStyle",
    "GoalTimeframe",
    "GoalType",
    "GuidanceMode",
    "HabitCategory",
    "HabitDifficulty",
    "HabitEssentiality",
    "HabitPolarity",
    "HealthStatus",
    "IntegrationSuccess",
    "Intent",
    "JournalMode",
    "JournalTier",
    "KnowledgeStatus",
    "JeUse",
    "KnowledgeType",
    "KuComplexity",
    "LearningLevel",
    "LearningModality",
    "LpType",
    "MasteryImpact",
    "MasteryLevel",
    "MasteryStatus",
    "MeasurementType",
    "MessageRole",
    "NeoLabel",
    "NonKuDomain",
    "Personality",
    "Pipeline",
    "ReportSource",
    "PracticeLevel",
    "PrincipleCategory",
    "PrincipleSource",
    "PrincipleStrength",
    "Priority",
    "TriggerType",
    "ReportSource",
    "QueryComplexity",
    "ProductivityLevel",
    "ProgressDepth",
    "ProgressLevel",
    "ExerciseScope",
    "RecurrencePattern",
    "RelationshipType",
    "ResponseTone",
    "SELCategory",
    "ScheduleType",
    "SearchScope",
    "SearchVisibility",
    "SubmissionModality",
    "SeverityLevel",
    "StepDifficulty",
    "SystemConstants",
    "ThemeCategory",
    "TimeOfDay",
    "TranscriptionStatus",
    "TrendDirection",
    "UserRole",
    "UserStatus",
    "Visibility",
]
