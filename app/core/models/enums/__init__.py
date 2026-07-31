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
- user_entry_enums: SubmissionModality, ExerciseScope, EnrichmentMode, ScheduleType, ProgressDepth
- pipeline: Pipeline, JeUse, ProcessingMode, ReportSource
- curriculum_enums: LpType, StepDifficulty
- lifepath_enums: ThemeCategory
- scheduling_enums: RecurrencePattern, TimeOfDay, EnergyLevel
- learning_enums: MasteryImpact, LearningLevel, EducationalLevel, MasteryStatus, KnowledgeStatus, etc.
- metadata_enums: RelationshipType, Intent, Visibility, SystemConstants, etc.
- askesis_enums: QueryComplexity, IntegrationSuccess
- transcription_enums: TranscriptionStatus
- interaction_enums: InteractionType, InteractionResult
- relationship_enums: ProficiencyLevel, KnowledgeRelevance

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

# Interaction enums - learning-loop event records
from .interaction_enums import InteractionResult, InteractionType

# Learning enums - education, knowledge, and mastery tracking
from .learning_enums import (
    AssessmentOutcome,
    ContentType,
    EducationalLevel,
    FeedbackCategory,
    KnowledgeStatus,
    KuComplexity,
    LearningLevel,
    MasteryImpact,
    MasteryStatus,
    SELCategory,
)

# Life path enums
from .lifepath_enums import ThemeCategory

# Metadata enums - relationships, UI, search, and system configuration
from .metadata_enums import (
    CacheStrategy,
    ConversationState,
    ErrorSeverity,
    GuidanceMode,
    HealthStatus,
    Intent,
    MessageRole,
    Personality,
    RelationshipType,
    ResponseTone,
    SearchVisibility,
    SeverityLevel,
    SystemConstants,
    TrendDirection,
    Visibility,
)

# Neo4j labels - single source of truth for node labels
from .neo_labels import NeoLabel

# Pipeline + ReportSource (ADR-054) — replaces ProcessorType; JeUse scopes je_pro files;
# ProcessingMode drives the journals upload doors (ADR-073)
from .pipeline import JeUse, Pipeline, ProcessingMode, ReportSource

# Principle enums
from .principle_enums import (
    AlignmentLevel,
    PrincipleCategory,
    PrincipleSource,
    PrincipleStrength,
    TriggerType,
)

# Relationship-property enums
from .relationship_enums import KnowledgeRelevance, ProficiencyLevel

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
    EnrichmentMode,
    ExerciseScope,
    ProgressDepth,
    ScheduleType,
    SubmissionModality,
)

# User enums - roles, health scoring, and account management
from .user_enums import (
    ContextHealthScore,
    GroupMemberRole,
    JournalMode,
    JournalTier,
    UserRole,
    UserStatus,
)

__all__ = [
    "ActivityType",
    "AlignmentLevel",
    "AssessmentOutcome",
    "AnalyticsDomain",
    "CacheStrategy",
    "ChoiceType",
    "CompletionStatus",
    "Confidence",
    "ConsistencyLevel",
    "ContentOrigin",
    "ContentScope",
    "ContentType",
    "Context",
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
    "InteractionResult",
    "InteractionType",
    "JournalMode",
    "JournalTier",
    "KnowledgeStatus",
    "JeUse",
    "KnowledgeRelevance",
    "KuComplexity",
    "LearningLevel",
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
    "ProcessingMode",
    "ReportSource",
    "PrincipleCategory",
    "PrincipleSource",
    "PrincipleStrength",
    "Priority",
    "ProficiencyLevel",
    "TriggerType",
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
    "SearchVisibility",
    "SubmissionModality",
    "SeverityLevel",
    "StepDifficulty",
    "SystemConstants",
    "ThemeCategory",
    "TimeOfDay",
    "TranscriptionStatus",
    "TrendDirection",
    "GroupMemberRole",
    "UserRole",
    "UserStatus",
    "Visibility",
]
