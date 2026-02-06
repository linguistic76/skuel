"""
Shared Enums - Re-export from Focused Modules
==============================================

This file re-exports all enums from their focused modules for backward compatibility.

Canonical Location: core/models/enums/
--------------------------------------
Enums are now organized in focused modules:
- activity_enums.py: Priority, ActivityStatus, ActivityType, CompletionStatus, GoalStatus
- entity_enums.py: EntityType, Domain, AnalyticsDomain, Context
- scheduling_enums.py: RecurrencePattern, TimeOfDay, EnergyLevel
- learning_enums.py: LearningLevel, EducationalLevel, MasteryStatus, ContentType, etc.
- metadata_enums.py: RelationshipType, Intent, Visibility, SystemConstants, etc.

Usage:
    # Preferred - import from focused modules
    from core.models.enums import Priority, ActivityStatus

    # Legacy - still works via this re-export
    from core.models.shared_enums import Priority, ActivityStatus
"""

# Re-export everything from the new modular structure
from core.models.enums import (
    DOMAIN_SEL_MAPPING,
    ActivityStatus,
    ActivityType,
    AnalyticsDomain,
    BridgeType,
    CacheStrategy,
    CompletionStatus,
    ContentScope,
    ContentType,
    Context,
    ConversationState,
    Domain,
    EducationalLevel,
    EnergyLevel,
    EntityType,
    ErrorSeverity,
    ExtractionMethod,
    FacetType,
    GoalStatus,
    GuidanceMode,
    HealthStatus,
    Intent,
    KnowledgeStatus,
    KnowledgeType,
    LearningLevel,
    LearningModality,
    MasteryStatus,
    MessageRole,
    Personality,
    PracticeLevel,
    Priority,
    RecurrencePattern,
    RelationshipType,
    ResponseTone,
    SearchScope,
    SELCategory,
    SeverityLevel,
    SystemConstants,
    TimeOfDay,
    TrendDirection,
    Visibility,
)

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
    "Visibility",
]
