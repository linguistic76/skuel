"""
SKUEL Enums - Centralized Enumeration Types
============================================

This module provides unified access to all SKUEL enumerations.

Module Organization:
- activity_enums: Priority, ActivityType, dual-track assessment levels
- entity_enums: NonKuDomain, DomainIdentifier, Domain, AnalyticsDomain, Context
- scheduling_enums: RecurrencePattern, TimeOfDay, EnergyLevel
- learning_enums: LearningLevel, EducationalLevel, MasteryStatus, KnowledgeStatus,
                  ContentType, PracticeLevel, KnowledgeType, SELCategory
- metadata_enums: RelationshipType, Intent, Visibility, SystemConstants, etc.
- ku_enums: EntityType, EntityStatus, CompletionStatus, ProcessorType, ProjectScope, etc.

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

# Entity enums - entity type identification and domain categorization
from .entity_enums import (
    AnalyticsDomain,
    ContentScope,
    Context,
    Domain,
    DomainIdentifier,
    NonKuDomain,
)

# Ku enums - unified knowledge unit identity, processing, and scheduling
from .ku_enums import (
    AnalysisDepth,
    CompletionStatus,
    ContentOrigin,
    ContextEnrichmentLevel,
    EntityStatus,
    EntityType,
    FormattingStyle,
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
    "ActivityType",
    "AnalyticsDomain",
    # Ku enums (LLM processing)
    "AnalysisDepth",
    "BridgeType",
    "CacheStrategy",
    "CompletionStatus",
    # Dual-track assessment levels
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
    "ErrorSeverity",
    "ExtractionMethod",
    "FacetType",
    "FormattingStyle",
    "GuidanceMode",
    "HealthStatus",
    "Intent",
    "KnowledgeStatus",
    "KnowledgeType",
    "KuComplexity",
    # Ku enums (core)
    "EntityStatus",
    "EntityType",
    "LearningLevel",
    "LearningModality",
    "MasteryStatus",
    "MessageRole",
    "NeoLabel",
    "NonKuDomain",
    "Personality",
    "PracticeLevel",
    "Priority",
    # Ku enums (processing + scheduling)
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
    "SystemConstants",
    "TimeOfDay",
    "TrendDirection",
    "UserRole",
    "Visibility",
]
