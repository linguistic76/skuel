"""
SKUEL Protocol Interfaces - THE Single Source
==============================================

All protocols consolidated in one location per CLAUDE.md architecture.
ISP-compliant design (refactored November 2025).

Backend Protocol Hierarchy
--------------------------
BackendOperations[T] is THE full backend protocol, composed from 7 sub-protocols:

    BackendOperations[T]  ← UniversalNeo4jBackend implements this
        ├── CrudOperations[T]              (6 methods)
        ├── EntitySearchOperations[T]      (3 methods)
        ├── RelationshipCrudOperations     (6 methods)
        ├── RelationshipMetadataOperations (3 methods)
        ├── RelationshipQueryOperations    (3 methods)
        ├── GraphTraversalOperations       (2 methods)
        └── LowLevelOperations             (2 methods + driver)

Protocol Categories
-------------------
- Backend protocols: BackendOperations + 7 sub-protocols (ISP-compliant)
- Domain protocols: TasksOperations, GoalsOperations, etc. (inherit from BackendOperations)
- Curriculum protocols: CurriculumOperations + KuOperations, LsOperations, LpOperations (Nov 2025)
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
    # Composable Backend Protocols (7 - ISP-compliant)
    CrudOperations,
    # Type Aliases and TypedDicts (3)
    Direction,
    EntitySearchOperations,
    # Core Conversion Protocols (5)
    EnumLike,
    # Pydantic Field Constraint Protocols (7)
    GeConstraint,
    GraphContextNode,
    # Graph Relationship Operations Protocol (1)
    GraphRelationshipOperations,
    GraphTraversalOperations,
    GtConstraint,
    # Timestamp Protocols (3)
    HasCreatedAt,
    HasDict,
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
    HasToDict,
    HasToNumeric,
    # Entity Attribute Protocols - Core (6)
    HasUID,
    HasUpdated,
    HasUpdatedAt,
    HasUsage,
    HasValidate,
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
    PydanticFieldInfo,
    PydanticModel,
    # Standalone query execution port (February 2026)
    QueryExecutor,
    RelationshipCrudOperations,
    RelationshipMetadata,
    RelationshipMetadataOperations,
    RelationshipQueryOperations,
    Result,
    Serializable,
    StreaksLike,
    # Backend Capability Protocols (10)
    SupportsCount,
    SupportsHealthCheck,
    SupportsInsights,
    SupportsPathfinding,
    SupportsRelatedSearch,
    SupportsSearch,
    SupportsSearchWithFilters,
    # Helper Functions (2)
    get_enum_value,
    to_dict,
)

# Context awareness protocols - ISP slices of UserContext (~240 fields → focused protocols)
# These define the architecture for context-aware services. Services should depend on the
# smallest slice they need. See: /docs/architecture/UNIFIED_USER_ARCHITECTURE.md
from .context_awareness_protocols import (
    ChoiceAwareness,
    CoreIdentity,
    CrossDomainAwareness,
    EventAwareness,
    FullAwareness,
    GoalAwareness,
    HabitAwareness,
    KnowledgeAwareness,
    LearningPathAwareness,
    PrincipleAwareness,
    TaskAwareness,
)

# Curriculum operation protocols (November 2025 - consistent hierarchy)
# Three curriculum domains: KU (point), LS (edge), LP (path)
# NOTE: MOC is KU-based (January 2026) - no separate MocOperations protocol
from .curriculum_protocols import (
    CurriculumOperations,
    ExerciseOperations,
    KuOperations,
    LpOperations,
    LsOperations,
)

# Domain operation protocols
from .domain_protocols import (
    ChoicesOperations,
    EventsOperations,
    FinancesOperations,
    GoalsOperations,
    HabitsOperations,
    # NOTE: JournalsOperations REMOVED (February 2026) - Journal merged into Reports
    PrinciplesOperations,
    TasksOperations,
    UserContextOperations,
)

# Feedback protocols — Feedback stage of the educational loop
from .feedback_protocols import (
    ActivityReportOperations,
    FeedbackOperations,
    ProgressFeedbackOperations,
    ProgressScheduleOperations,
    ReviewQueueOperations,
    TeacherReviewOperations,
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
    UserOperations,
)

# Intelligence operation protocols
from .intelligence_protocols import IntelligenceOperations

# Query types - TypedDicts for type-safe queries and payloads (January 2026)
from .query_types import (
    # Filter Specifications
    ActivityFilterSpec,
    BaseFilterSpec,
    # Update Payloads
    BaseUpdatePayload,
    ChoiceUpdatePayload,
    CurriculumFilterSpec,
    # Cypher Parameters
    CypherParams,
    EventUpdatePayload,
    GoalUpdatePayload,
    # Response/Context Types
    GraphContextResult,
    HabitUpdatePayload,
    IntelligenceResult,
    KuUpdatePayload,
    LpUpdatePayload,
    LsUpdatePayload,
    # Query Building Types
    OrderBySpec,
    PaginationSpec,
    PrincipleUpdatePayload,
    ProgressResult,
    TaskUpdatePayload,
    WhereClauseSpec,
)

# Knowledge operation protocols
# NOTE: KuOperationsLegacy, KuQueryOperations DELETED January 2026
# Use KuOperations from curriculum_protocols.py
# NOTE: LearningPathsOperations DELETED January 2026 - use LpOperations from curriculum_protocols.py
# Search operation protocols
from .search_protocols import (
    # Domain-specific search protocols (November 2025)
    ChoicesSearchOperations,
    CypherOperations,
    DomainSearchOperations,  # Base: Per-domain search services
    EventsSearchOperations,
    GoalsSearchOperations,
    HabitsSearchOperations,
    PrinciplesSearchOperations,
    QueryBuilderOperations,
    SearchOperations,
    # Graph-aware search capability protocols (January 2026)
    SupportsGraphAwareSearch,
    SupportsGraphTraversalSearch,
    SupportsTagSearch,
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

# Submission protocols — Submission stage of the educational loop
from .submission_protocols import (
    SubmissionOperations,
    SubmissionProcessingOperations,
    SubmissionSearchOperations,
)

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
    # Update Payloads
    "BaseUpdatePayload",
    "ChoiceUpdatePayload",
    "EventUpdatePayload",
    "GoalUpdatePayload",
    "HabitUpdatePayload",
    "KuUpdatePayload",
    "LpUpdatePayload",
    "LsUpdatePayload",
    "PrincipleUpdatePayload",
    "TaskUpdatePayload",
    # Query Building Types
    "OrderBySpec",
    "PaginationSpec",
    "WhereClauseSpec",
    # Response/Context Types
    "GraphContextResult",
    "IntelligenceResult",
    "ProgressResult",
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
    # ========== CONTEXT AWARENESS PROTOCOLS (11 - ISP slices of UserContext) ==========
    "ChoiceAwareness",
    "CoreIdentity",
    "CrossDomainAwareness",
    "EventAwareness",
    "FullAwareness",
    "GoalAwareness",
    "HabitAwareness",
    "KnowledgeAwareness",
    "LearningPathAwareness",
    "PrincipleAwareness",
    "TaskAwareness",
    # ========== SEARCH OPERATION PROTOCOLS (10) ==========
    "ChoicesSearchOperations",
    # ========== DOMAIN OPERATION PROTOCOLS (8) ==========
    "ChoicesOperations",
    "Closeable",
    "CrossDomainAnalyticsOperations",
    # ========== BACKEND PROTOCOLS (ISP-compliant hierarchy) ==========
    # Sub-protocols (for focused dependencies)
    "CrudOperations",  # Basic CRUD (6 methods)
    # ========== CURRICULUM OPERATION PROTOCOLS (5 - Dec 2025) ==========
    "CurriculumOperations",  # Base protocol for KU, LS, LP, MOC
    "CypherOperations",
    # ========== TYPE ALIASES (3) ==========
    "Direction",
    "DomainSearchOperations",
    "EntitySearchOperations",  # Search/filter (3 methods)
    # ========== CORE CONVERSION PROTOCOLS (5) ==========
    "EnumLike",
    "EventBusOperations",
    "EventsSearchOperations",
    "EventsOperations",
    "FinancesOperations",
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
    "HabitsSearchOperations",
    "HabitsOperations",
    "HabitEventSchedulerOperations",
    # ========== TIMESTAMP PROTOCOLS (3) ==========
    "HasCreatedAt",
    "HasDict",
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
    "HasToDict",
    "HasToNumeric",
    # ========== ENTITY ATTRIBUTE PROTOCOLS (6) ==========
    "HasUID",
    "HasUpdated",
    "HasUpdatedAt",
    "HasUsage",
    "HasValidate",
    # ========== INTELLIGENCE PROTOCOLS (1) ==========
    "IntelligenceOperations",
    # ========== MOCK/STUB ENDPOINT PROTOCOLS (2) ==========
    "IsMockEndpoint",
    "IsStubEndpoint",
    # "JournalsOperations", - REMOVED February 2026 - Journal merged into Reports
    "KuOperations",  # Knowledge Unit operations (point)
    # KuOperationsLegacy, KuQueryOperations DELETED January 2026
    "LeConstraint",
    # "LearningOperations", - DELETED January 2026
    "LifePathAlignmentOperations",
    "LifePathOperations",
    # "LearningPathsOperations", - DELETED January 2026, use LpOperations
    "LowLevelOperations",  # Direct DB access (2 methods + driver)
    "QueryExecutor",  # Standalone Cypher query execution port
    "LpOperations",  # Learning Path operations (path)
    "LsOperations",  # Learning Step operations (edge)
    "LtConstraint",
    "MaxItemsConstraint",
    "MaxLenConstraint",
    "MetricsLike",
    "MinLenConstraint",
    # MocOperations removed January 2026 - MOC is KU-based
    "PrinciplesSearchOperations",
    "PrinciplesOperations",
    "PydanticFieldInfo",
    "PydanticModel",
    "QueryBuilderOperations",
    # ========== SUBMISSION PROTOCOLS (3) ==========
    "SubmissionOperations",
    "SubmissionProcessingOperations",
    "SubmissionSearchOperations",
    # ========== SHARING PROTOCOL ==========
    "SharingOperations",
    # ========== FEEDBACK PROTOCOLS (5) ==========
    "ActivityReportOperations",
    "FeedbackOperations",
    "ProgressFeedbackOperations",
    "ProgressScheduleOperations",
    "ReviewQueueOperations",
    # ========== EXERCISE PROTOCOL ==========
    "ExerciseOperations",
    "RelationshipCrudOperations",  # Edge CRUD (6 methods)
    "RelationshipMetadata",
    "RelationshipMetadataOperations",  # Edge properties (3 methods)
    "RelationshipQueryOperations",  # Relationship queries (3 methods)
    "Result",
    "SchemaOperations",
    "SearchOperations",
    "Serializable",
    "StreaksLike",
    # ========== BACKEND CAPABILITY PROTOCOLS (10) ==========
    "SupportsCount",
    # Graph-aware search capability protocols (January 2026)
    "SupportsGraphAwareSearch",
    "SupportsGraphTraversalSearch",
    "SupportsHealthCheck",
    "SupportsInsights",
    "SupportsPathfinding",
    "SupportsRelatedSearch",
    "SupportsSearch",
    "SupportsSearchWithFilters",
    "SupportsTagSearch",
    "SystemServiceOperations",
    "TasksSearchOperations",
    "TasksOperations",
    "TeacherReviewOperations",
    "UserContextOperations",
    "UserOperations",
    "VisualizationOperations",
    # ========== HELPER FUNCTIONS (2) ==========
    "get_enum_value",
    "to_dict",
    # ========== ZPD PROTOCOL (1 - March 2026) ==========
    "ZPDOperations",
]
