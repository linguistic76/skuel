"""
SKUEL Enums - Centralized Enumeration Types
============================================

This module provides unified access to all SKUEL enumerations.

Module Organization:
- entity_enums: EntityType, EntityStatus, ContentOrigin, ProcessorType,
                Domain, NonKuDomain, DomainIdentifier, AnalyticsDomain, ContentScope, Context
- activity_enums: Priority, ActivityType, dual-track assessment levels
- goal_enums: GoalType, GoalTimeframe, MeasurementType, HabitEssentiality
- habit_enums: HabitPolarity, HabitCategory, HabitDifficulty, CompletionStatus
- choice_enums: ChoiceType
- principle_enums: PrincipleCategory, PrincipleSource, PrincipleStrength, AlignmentLevel
- reports_enums: ProjectScope, FormattingStyle, AnalysisDepth, ContextEnrichmentLevel,
                 ScheduleType, ProgressDepth
- curriculum_enums: LpType, StepDifficulty
- lifepath_enums: ThemeCategory
- scheduling_enums: RecurrencePattern, TimeOfDay, EnergyLevel
- learning_enums: LearningLevel, EducationalLevel, MasteryStatus, KnowledgeStatus, etc.
- metadata_enums: RelationshipType, Intent, Visibility, SystemConstants, etc.

Usage:
    from core.models.enums import Priority, EntityStatus, EntityType
    from core.models.enums import EntityType, EntityStatus, ProcessorType, ProjectScope
"""

# Activity enums - priority, calendar types, and assessment levels
from .activity_enums import (
    ActivityType,
    ConsistencyLevel,
    DecisionQualityLevel,
    EngagementLevel,
    Priority,
    ProductivityLevel,
    ProgressLevel,
)

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
    ProcessorType,
)

# Goal enums
from .goal_enums import GoalTimeframe, GoalType, HabitEssentiality, MeasurementType

# Habit enums
from .habit_enums import CompletionStatus, HabitCategory, HabitDifficulty, HabitPolarity

# Learning enums - education, knowledge, and mastery tracking
from .learning_enums import (
    DOMAIN_SEL_MAPPING,
    ContentType,
    EducationalLevel,
    KnowledgeStatus,
    KnowledgeType,
    KuComplexity,
    LearningLevel,
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
    SeverityLevel,
    SystemConstants,
    TrendDirection,
    Visibility,
)

# Neo4j labels - single source of truth for node labels
from .neo_labels import NeoLabel

# Principle enums
from .principle_enums import AlignmentLevel, PrincipleCategory, PrincipleSource, PrincipleStrength

# Reports enums - processing, scheduling, and assignment
from .reports_enums import (
    AnalysisDepth,
    ContextEnrichmentLevel,
    FormattingStyle,
    ProgressDepth,
    ProjectScope,
    ScheduleType,
)

# Scheduling enums - time, recurrence, and energy management
from .scheduling_enums import (
    EnergyLevel,
    RecurrencePattern,
    TimeOfDay,
)

# User enums - roles, health scoring, and account management
from .user_enums import ContextHealthScore, UserRole

__all__ = [
    "DOMAIN_SEL_MAPPING",
    "ActivityType",
    "AlignmentLevel",
    "AnalyticsDomain",
    "AnalysisDepth",
    "BridgeType",
    "CacheStrategy",
    "ChoiceType",
    "CompletionStatus",
    "ConsistencyLevel",
    "ContentOrigin",
    "ContentScope",
    "ContentType",
    "Context",
    "ContextEnrichmentLevel",
    "ContextHealthScore",
    "ConversationState",
    "DecisionQualityLevel",
    "Domain",
    "DomainIdentifier",
    "EducationalLevel",
    "EngagementLevel",
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
    "Intent",
    "KnowledgeStatus",
    "KnowledgeType",
    "KuComplexity",
    "LearningLevel",
    "LearningModality",
    "LpType",
    "MasteryStatus",
    "MeasurementType",
    "MessageRole",
    "NeoLabel",
    "NonKuDomain",
    "Personality",
    "PracticeLevel",
    "PrincipleCategory",
    "PrincipleSource",
    "PrincipleStrength",
    "Priority",
    "ProcessorType",
    "ProductivityLevel",
    "ProgressDepth",
    "ProgressLevel",
    "ProjectScope",
    "RecurrencePattern",
    "RelationshipType",
    "ResponseTone",
    "SELCategory",
    "ScheduleType",
    "SearchScope",
    "SeverityLevel",
    "StepDifficulty",
    "SystemConstants",
    "ThemeCategory",
    "TimeOfDay",
    "TrendDirection",
    "UserRole",
    "Visibility",
]
