"""
SKUEL Enums - Centralized Enumeration Types
============================================

This module provides unified access to all SKUEL enumerations.

Module Organization:
- activity_enums: Priority, ActivityStatus, ActivityType, CompletionStatus, GoalStatus
- entity_enums: EntityType, Domain, AnalyticsDomain, Context
- scheduling_enums: RecurrencePattern, TimeOfDay, EnergyLevel
- learning_enums: LearningLevel, EducationalLevel, MasteryStatus, KnowledgeStatus,
                  ContentType, PracticeLevel, KnowledgeType, SELCategory
- metadata_enums: RelationshipType, Intent, Visibility, SystemConstants, etc.
- ku_enums: KuType, KuStatus, ProcessorType, ProjectScope, JournalType, etc.

Usage:
    from core.models.enums import Priority, ActivityStatus, EntityType
    from core.models.enums import KuType, KuStatus, ProcessorType, ProjectScope
"""

# Activity enums - status and priority for trackable activities
from .activity_enums import (
    ActivityStatus,
    ActivityType,
    CompletionStatus,
    GoalStatus,
    Priority,
)

# Entity enums - entity type identification and domain categorization
from .entity_enums import (
    AnalyticsDomain,
    ContentScope,
    Context,
    Domain,
    EntityType,
)

# Ku enums - unified knowledge unit identity, processing, and scheduling
from .ku_enums import (
    AnalysisDepth,
    ContextEnrichmentLevel,
    FormattingStyle,
    JournalCategory,
    JournalMode,
    JournalType,
    KuStatus,
    KuType,
    ProcessorType,
    ProgressDepth,
    ProjectScope,
    ScheduleType,
)

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
    "ActivityStatus",
    "ActivityType",
    "AnalyticsDomain",
    # Ku enums (LLM processing)
    "AnalysisDepth",
    "BridgeType",
    "CacheStrategy",
    "CompletionStatus",
    "ContentScope",
    "ContentType",
    "Context",
    "ContextEnrichmentLevel",
    "ContextHealthScore",
    "ConversationState",
    "Domain",
    "EducationalLevel",
    "EnergyLevel",
    "EntityType",
    "ErrorSeverity",
    "ExtractionMethod",
    "FacetType",
    "FormattingStyle",
    "GoalStatus",
    "GuidanceMode",
    "HealthStatus",
    "Intent",
    # Ku enums (journal processing)
    "JournalCategory",
    "JournalMode",
    "JournalType",
    "KnowledgeStatus",
    "KnowledgeType",
    "KuComplexity",
    # Ku enums (core)
    "KuStatus",
    "KuType",
    "LearningLevel",
    "LearningModality",
    "MasteryStatus",
    "MessageRole",
    "NeoLabel",
    "Personality",
    "PracticeLevel",
    "Priority",
    # Ku enums (processing + scheduling)
    "ProcessorType",
    "ProgressDepth",
    "ProjectScope",
    "RecurrencePattern",
    "RelationshipType",
    "ResponseTone",
    "SELCategory",
    "ScheduleType",
    "SearchScope",
    "SeverityLevel",
    "SystemConstants",
    "TimeOfDay",
    "TrendDirection",
    "UserRole",
    "Visibility",
]
