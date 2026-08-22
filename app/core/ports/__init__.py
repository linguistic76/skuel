"""
SKUEL Protocol Interfaces - THE Single Source
==============================================

All protocols consolidated in one location per CLAUDE.md architecture.
ISP-compliant design (refactored November 2025).

Backend Protocol Hierarchy
--------------------------
BackendOperations[T] is THE full backend protocol, composed from 10 sub-protocols:

    BackendOperations[T]  ← UniversalNeo4jBackend implements this
        ├── CrudOperations[T]                  (7 methods)
        ├── EntitySearchOperations[T]          (3 methods)
        ├── RelationshipCrudOperations         (6 methods)
        ├── RelationshipMetadataOperations     (3 methods)
        ├── RelationshipQueryOperations        (3 methods)
        ├── OrderedRelationshipOperations      (7 methods)
        ├── BatchRelationshipOperations        (3 methods)
        ├── GraphTraversalOperations           (2 methods)
        └── LowLevelOperations                 (2 methods + driver)

Protocol Categories
-------------------
- Backend protocols: BackendOperations + 10 sub-protocols (ISP-compliant)
- Domain protocols: TasksOperations, GoalsOperations, etc. (inherit from BackendOperations)
- Curriculum protocols: CurriculumOperations + PsOperations, LpOperations, KuOperations (Nov 2025, Apr 2026)
- Search protocols: DomainSearchOperations, TasksSearchOperations, etc.
- Infrastructure protocols: EventBusOperations, SchemaOperations, etc.

Usage
-----
    # Full backend protocol
    from core.ports import BackendOperations

    class MyService:
        def __init__(self, backend: BackendOperations[Task]) -> None:
            self.backend = backend

    # Focused dependency (ISP)
    from core.ports import CrudOperations

    class SimpleReadService:
        def __init__(self, backend: CrudOperations[Task]) -> None:
            self.backend = backend  # Only needs CRUD
"""

# Base protocols - Core type contracts (ISP-compliant - streamlined Nov 2025)
# NOTE: Deepgram protocols moved to adapters/external/deepgram/
# Askesis cross-cutting intelligence protocols (January 2026)
from .askesis_protocols import (
    AskesisCoreOperations,
    AskesisDomainSynthesisOperations,
    AskesisOperations,
    AskesisQueryOperations,
    AskesisRecommendationOperations,
    AskesisStateAnalysisOperations,
)
from .base_protocols import (
    # Composed Backend Protocol (1 - backward compatible)
    BackendOperations,
    BatchRelationshipOperations,
    # Composable Backend Protocols (7 - ISP-compliant)
    CrudOperations,
    # Type Aliases and TypedDicts (3)
    Direction,
    EntitySearchOperations,
    # Pydantic Field Constraint Protocols (7)
    GeConstraint,
    GraphContextNode,
    # Graph Relationship Operations Protocol (1)
    GraphRelationshipOperations,
    GraphTraversalOperations,
    GtConstraint,
    # Timestamp Protocols (3)
    HasCreatedAt,
    HasLogger,
    HasMetadata,
    # Priority/Sorting Protocols (3)
    HasPriority,
    HasRelevanceScore,
    # Score/Metrics Protocols (6)
    HasScore,
    # Query/Optimizer Protocols (3)
    HasSeverity,
    HasStrategy,
    HasSummary,
    HasToNumeric,
    # Entity Attribute Protocols - Core (6)
    HasUID,
    HasUpdated,
    HasUpdatedAt,
    HasUsage,
    # Hierarchy Backend Protocol (BackendOperations + HierarchyOperations)
    HierarchicalBackendOperations,
    # Mock/Stub Endpoint Protocols (2)
    IsMockEndpoint,
    IsStubEndpoint,
    LeConstraint,
    LowLevelOperations,
    LtConstraint,
    MaxItemsConstraint,
    MaxLenConstraint,
    MetricsLike,
    MinLenConstraint,
    OrderedRelationshipOperations,
    PydanticFieldInfo,
    # Standalone query execution port (February 2026)
    QueryExecutor,
    RelationshipCrudOperations,
    RelationshipMetadata,
    RelationshipMetadataOperations,
    RelationshipQueryOperations,
    Result,
    StreaksLike,
    # Backend Capability Protocols (10)
)

# Curriculum operation protocols (November 2025 - consistent hierarchy)
# Three curriculum domains: KU (point), PS (edge), LP (path)
# All three have dedicated operations protocols: KuOperations, PsOperations, LpOperations (April 2026)
# NOTE: MOC is KU-based (January 2026) - no separate MocOperations protocol
from .connection_fetch_protocols import ConnectionFetchOperations

# Conversation protocols (ADR-078 - persisted discussion sessions)
from .conversation_protocols import (
    ConversationBackendOperations,
    ConversationOperations,
)
from .cross_domain_protocols import CrossDomainBackendOperations
from .curriculum_protocols import (
    CurriculumOperations,
    ExerciseOperations,
    KuOperations,
    LpOperations,
    LpProgressBackendOperations,
    PsIntelligenceBackendOperations,
    PsOperations,
    PsOrganizesBackendOperations,
    PsProgressBackendOperations,
    RevisedExerciseOperations,
)

# Domain operation protocols
from .domain_protocols import (
    ChoicesOperations,
    EventsOperations,
    GoalsOperations,
    HabitsOperations,
    # NOTE: JournalsOperations REMOVED (February 2026) - Journal merged into Reports
    PrinciplesOperations,
    TasksOperations,
    UserContextOperations,
)

# Form protocols
from .form_protocols import (
    FormSubmissionOperations,
    FormTemplateOperations,
)

# Graph protocols - entity relationships (consolidated)
from .graph_protocols import GraphEntity, GraphEntityBase

# Group protocols (ADR-040 - February 2026)
from .group_protocols import GroupOperations

# Infrastructure operation protocols
from .infrastructure_protocols import (
    AsyncCloseable,
    Closeable,
    EventBusOperations,
    IngestionOperations,
    SchemaOperations,
    SchemaQueryExecutor,
    UserActivityOperations,
    UserCrudOperations,
    UserLearningStateOperations,
    UserOperations,
)

# Intelligence operation protocols
from .intelligence_protocols import (
    DomainIntelligenceOperations,
    IntelligenceOperations,
    KnowledgeIntelligenceOperations,
)
from .ps_engagement_protocols import PsEngagementOperations

# Query types - TypedDicts for type-safe queries and payloads (January 2026)
from .query_types import (
    # Filter Specifications
    ActivityFilterSpec,
    BaseFilterSpec,
    # Update Payloads (curriculum only — Activity Domains use frozen *UpdateIntent, ADR-066)
    BaseUpdatePayload,
    CurriculumFilterSpec,
    # Cypher Parameters
    CypherParams,
    # Response/Context Types
    GraphContextResult,
    IntelligenceResult,
    KuUpdatePayload,
    LpUpdatePayload,
    # Query Building Types
    OrderBySpec,
    PaginationSpec,
    ProgressResult,
    PsUpdatePayload,
    WhereClauseSpec,
)
from .relationship_backend_protocols import UserRelationshipOperations

# Report protocols — Report stage of the educational loop
from .report_protocols import (
    ActivityReportOperations,
    AssessmentOperations,
    EntryReportOperations,
    ProgressReportOperations,
    ProgressScheduleOperations,
    ReviewQueueOperations,
    TeacherReviewOperations,
)

# Knowledge operation protocols
# NOTE: KuOperationsLegacy, KuQueryOperations DELETED January 2026
# Use PsOperations from curriculum_protocols.py
# NOTE: LearningPathsOperations DELETED January 2026 - use LpOperations from curriculum_protocols.py
# Search operation protocols
from .search_protocols import (
    # Domain-specific search protocols (November 2025)
    ChoicesSearchOperations,
    DomainSearchOperations,  # Base: Per-domain search services
    EventsSearchOperations,
    GoalsSearchOperations,
    HabitsSearchOperations,
    PrinciplesSearchOperations,
    ScopedChunkRetrievalOperations,
    # Graph-aware search capability protocols (January 2026)
    SupportsGraphAwareSearch,
    SupportsGraphTraversalSearch,
    SupportsTagSearch,
    SupportsTextSearch,
    TasksSearchOperations,
)

# Service protocols - cross-cutting services (February 2026)
from .service_protocols import (
    CalendarServiceOperations,
    CrossDomainAnalyticsOperations,
    GoalTaskGeneratorOperations,
    GraphAuthOperations,
    HabitEventSchedulerOperations,
    LifePathAlignmentOperations,
    LifePathOperations,
    SystemServiceOperations,
    VisualizationOperations,
)

# Sharing protocol — cross-cutting, any entity type can be shared
from .sharing_protocols import SharingOperations

# Activity Template protocol — PS-owned templates (May 2026)
from .template_protocols import ActivityTemplateOperations, TemplateAttachmentOperations

# ZPD protocol — Zone of Proximal Development (March 2026)
from .zpd_protocols import ZPDOperations

# ============================================================================
# EXPLICIT EXPORTS - Protocol Catalog (ISP-compliant Nov 2025)
# NOTE: Deepgram protocols moved to adapters/external/deepgram/
# ============================================================================

__all__ = [
    # ========== QUERY TYPES - TypedDicts (January 2026) ==========
    # Cypher Parameters
    "CypherParams",
    # Filter Specifications
    "ActivityFilterSpec",
    "BaseFilterSpec",
    "CurriculumFilterSpec",
    # Update Payloads (curriculum only — Activity Domains use frozen *UpdateIntent, ADR-066)
    "BaseUpdatePayload",
    "KuUpdatePayload",
    "LpUpdatePayload",
    "PsUpdatePayload",
    # Query Building Types
    "OrderBySpec",
    "PaginationSpec",
    "WhereClauseSpec",
    # Response/Context Types
    "GraphContextResult",
    "IntelligenceResult",
    "ProgressResult",
    # ========== ACTIVITY TEMPLATE PROTOCOL (1 - May 2026) ==========
    "ActivityTemplateOperations",
    "TemplateAttachmentOperations",
    # ========== ASKESIS PROTOCOLS (6 - February 2026) ==========
    "AskesisCoreOperations",  # CRUD + context building (6 methods)
    "AskesisDomainSynthesisOperations",
    "AskesisOperations",  # Complete Askesis interface (16 methods)
    "AskesisQueryOperations",
    "AskesisRecommendationOperations",
    "AskesisStateAnalysisOperations",
    # ========== INFRASTRUCTURE PROTOCOLS (7) ==========
    "AsyncCloseable",
    # Full protocol (composes all 7 sub-protocols)
    "BackendOperations",  # THE protocol for UniversalNeo4jBackend
    # ========== CALENDAR/SYSTEM/SERVICE PROTOCOLS (7 - February 2026) ==========
    "CalendarServiceOperations",
    # ========== SEARCH OPERATION PROTOCOLS (10) ==========
    "ChoicesSearchOperations",
    # ========== DOMAIN OPERATION PROTOCOLS (8) ==========
    "ChoicesOperations",
    "Closeable",
    "ConnectionFetchOperations",
    "ConversationBackendOperations",
    "ConversationOperations",
    "CrossDomainAnalyticsOperations",
    "CrossDomainBackendOperations",
    "PsEngagementOperations",
    "UserRelationshipOperations",
    # ========== BACKEND PROTOCOLS (ISP-compliant hierarchy) ==========
    # Sub-protocols (for focused dependencies)
    "CrudOperations",  # Basic CRUD (6 methods)
    # ========== CURRICULUM OPERATION PROTOCOLS (5 - Dec 2025) ==========
    "CurriculumOperations",  # Base protocol for KU, PS, LP, MOC
    # ========== TYPE ALIASES (3) ==========
    "Direction",
    "DomainSearchOperations",
    "EntitySearchOperations",  # Search/filter (3 methods)
    "EventBusOperations",
    "EventsSearchOperations",
    "EventsOperations",
    "IngestionOperations",
    # ========== PYDANTIC CONSTRAINT PROTOCOLS (7) ==========
    "GeConstraint",
    "GoalsSearchOperations",
    "GoalsOperations",
    "GoalTaskGeneratorOperations",
    "GraphContextNode",
    # ========== GRAPH PROTOCOLS (2) ==========
    "GraphAuthOperations",
    "GraphEntity",
    "GraphEntityBase",
    # ========== GROUP & TEACHING PROTOCOLS (2 - February 2026) ==========
    "GroupOperations",
    # Domain relationship queries
    "GraphRelationshipOperations",
    "GraphTraversalOperations",  # Graph traversal (2 methods)
    "GtConstraint",
    "HierarchicalBackendOperations",  # BackendOperations + HierarchyOperations
    "HabitsSearchOperations",
    "HabitsOperations",
    "HabitEventSchedulerOperations",
    # ========== TIMESTAMP PROTOCOLS (3) ==========
    "HasCreatedAt",
    "HasLogger",
    "HasMetadata",
    # ========== PRIORITY/SORTING PROTOCOLS (3) ==========
    "HasPriority",
    "HasRelevanceScore",
    # ========== SCORE/METRICS PROTOCOLS (6) ==========
    "HasScore",
    # ========== QUERY/OPTIMIZER PROTOCOLS (3) ==========
    "HasSeverity",
    "HasStrategy",
    "HasSummary",
    "HasToNumeric",
    # ========== ENTITY ATTRIBUTE PROTOCOLS (6) ==========
    "HasUID",
    "HasUpdated",
    "HasUpdatedAt",
    "HasUsage",
    # ========== INTELLIGENCE PROTOCOLS (3) ==========
    "DomainIntelligenceOperations",
    "IntelligenceOperations",
    "KnowledgeIntelligenceOperations",
    # ========== MOCK/STUB ENDPOINT PROTOCOLS (2) ==========
    "IsMockEndpoint",
    "IsStubEndpoint",
    # "JournalsOperations", - REMOVED February 2026 - Journal merged into Reports
    # KuOperationsLegacy, KuQueryOperations DELETED January 2026
    "LeConstraint",
    # "LearningOperations", - DELETED January 2026
    "LifePathAlignmentOperations",
    "LifePathOperations",
    # "LearningPathsOperations", - DELETED January 2026, use LpOperations
    "LowLevelOperations",  # Direct DB access (2 methods + driver)
    "QueryExecutor",  # Standalone Cypher query execution port
    "KuOperations",  # Knowledge Unit operations (atom)
    "LpOperations",  # Learning Path operations (path)
    "LpProgressBackendOperations",  # KU/PS → LP progress backend slice
    "PsIntelligenceBackendOperations",  # PathStep readiness/practice/guidance reads
    "PsOperations",  # Learning Step operations (edge)
    "PsOrganizesBackendOperations",  # ORGANIZES backend slice (MOC hierarchy)
    "PsProgressBackendOperations",  # KU → PathStep progress backend slice
    "LtConstraint",
    "MaxItemsConstraint",
    "MaxLenConstraint",
    "MetricsLike",
    "MinLenConstraint",
    # MocOperations removed January 2026 - MOC is KU-based
    "PrinciplesSearchOperations",
    "PrinciplesOperations",
    "PydanticFieldInfo",
    # ========== SHARING PROTOCOL ==========
    "SharingOperations",
    # ========== REPORT PROTOCOLS (6) ==========
    "ActivityReportOperations",
    "AssessmentOperations",
    "EntryReportOperations",
    "ProgressReportOperations",
    "ProgressScheduleOperations",
    "ReviewQueueOperations",
    # ========== EXERCISE PROTOCOLS ==========
    "ExerciseOperations",
    "RevisedExerciseOperations",
    # ========== FORM PROTOCOLS ==========
    "FormTemplateOperations",
    "FormSubmissionOperations",
    "BatchRelationshipOperations",  # Batch relationship queries (3 methods)
    "OrderedRelationshipOperations",  # Ordered/hierarchical traversal (7 methods)
    "RelationshipCrudOperations",  # Edge CRUD (6 methods)
    "RelationshipMetadata",
    "RelationshipMetadataOperations",  # Edge properties (3 methods)
    "RelationshipQueryOperations",  # Relationship queries (3 methods)
    "Result",
    "SchemaOperations",
    "SchemaQueryExecutor",
    "ScopedChunkRetrievalOperations",
    "StreaksLike",
    # ========== BACKEND CAPABILITY PROTOCOLS (10) ==========
    # Graph-aware search capability protocols (January 2026)
    "SupportsGraphAwareSearch",
    "SupportsGraphTraversalSearch",
    "SupportsTagSearch",
    "SupportsTextSearch",
    "SystemServiceOperations",
    "TasksSearchOperations",
    "TasksOperations",
    "TeacherReviewOperations",
    "UserActivityOperations",
    "UserContextOperations",
    "UserCrudOperations",
    "UserOperations",
    "UserLearningStateOperations",
    "VisualizationOperations",
    # ========== ZPD PROTOCOL (1 - March 2026) ==========
    "ZPDOperations",
]
