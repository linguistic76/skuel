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

Usage:
    from core.models.enums import Priority, ActivityStatus, EntityType
    # or
    from core.models.shared_enums import Priority  # Legacy import still works
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

# Learning enums - education, knowledge, and mastery tracking
from .learning_enums import (
    DOMAIN_SEL_MAPPING,
    ContentType,
    EducationalLevel,
    KnowledgeStatus,
    KnowledgeType,
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
    "BridgeType",
    "CacheStrategy",
    "CompletionStatus",
    "ContentScope",
    "ContentType",
    "Context",
    "ContextHealthScore",
    "ConversationState",
    "Domain",
    "EducationalLevel",
    "EnergyLevel",
    # Entity enums
    "EntityType",
    "ErrorSeverity",
    "ExtractionMethod",
    "FacetType",
    "GoalStatus",
    "GuidanceMode",
    "HealthStatus",
    "Intent",
    "KnowledgeStatus",
    "KnowledgeType",
    # Learning enums
    "LearningLevel",
    "LearningModality",
    "MasteryStatus",
    "MessageRole",
    # Neo4j labels
    "NeoLabel",
    "Personality",
    "PracticeLevel",
    # Activity enums
    "Priority",
    # Scheduling enums
    "RecurrencePattern",
    "RelationshipType",
    "AnalyticsDomain",
    # Metadata enums
    "ResponseTone",
    "SELCategory",
    "SearchScope",
    "SeverityLevel",
    "SystemConstants",
    "TimeOfDay",
    "TrendDirection",
    # User enums
    "UserRole",
    "Visibility",
]
