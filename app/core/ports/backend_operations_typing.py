"""
BackendOperations Sub-Protocol Selection Guide
===============================================

Decision guide for choosing the right backend protocol when wiring a service.
New services should read this before choosing a constructor parameter type.

Quick Decision Tree
-------------------
Ask: what does my service actually call on the backend?

    Runs complex Cypher across multiple entity types?
        → QueryExecutor        (most common focused protocol)

    Standard CRUD on a single domain entity type?
        → CrudOperations[T]    (get, create, update, delete, list)

    Also needs search/filter on top of CRUD?
        → CrudOperations[T] + EntitySearchOperations[T]
          (or just BackendOperations[T] if multiple sub-protocols needed)

    Creates or removes graph edges?
        → RelationshipCrudOperations

    Reads edge counts or UID lists without loading entities?
        → RelationshipQueryOperations

    Reads or updates properties stored on a graph edge?
        → RelationshipMetadataOperations

    Cross-domain neighborhood traversal (intelligence services)?
        → GraphTraversalOperations

    Health monitoring or direct Cypher with health_check()?
        → LowLevelOperations

    Full domain service (facade + sub-services)?
        → BackendOperations[T]  (composed protocol, default for BaseService)


Sub-Protocol Reference
----------------------

Protocol                      Methods                         Typical consumers
----------------------------  ------------------------------  -----------------------------------
CrudOperations[T]             create, get, get_many, update,  CrudOperationsMixin, simple services
                              delete, list

EntitySearchOperations[T]     search, find_by, count,         SearchOperationsMixin
                              get_user_entities

RelationshipCrudOperations    add_relationship, has_          RelationshipOperationsMixin,
                              relationship, get_relationships, UnifiedRelationshipService
                              create/delete_relationships_batch

RelationshipMetadataOperations get_relationship_metadata,     Strength-tracking services,
                              update_relationship_properties,  alignment scoring
                              get_relationships_batch

RelationshipQueryOperations   count_related,                  Lightweight graph counting,
                              get_related_uids,               prerequisite checks
                              count_relationships_batch

GraphTraversalOperations      traverse,                       ContextOperationsMixin,
                              get_domain_context_raw          intelligence services

LowLevelOperations            execute_query, health_check     Infrastructure / health routes
  (inherits QueryExecutor)

QueryExecutor                 execute_query                   THE most-used focused protocol —
                                                              cross-domain queries, MEGA-QUERY,
                                                              lateral relationships, sharing

BackendOperations[T]          All of the above                BaseService, domain facades


Real Examples from SKUEL Services
----------------------------------

QueryExecutor — the most common focused protocol:

    # Used by: KuOrganizationService, CrossDomainQueries, LateralRelationshipService,
    #          UserContextQueryExecutor, UserStatsAggregator, ReportSharingService,
    #          TeacherReviewService, ProgressFeedbackGenerator, Neo4jVectorSearchService,
    #          Neo4jGenAIEmbeddingsService, UserProgressService

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from core.ports import QueryExecutor
        from core.utils.result_simplified import Result

    class LateralRelationshipService:
        def __init__(self, executor: "QueryExecutor") -> None:
            self.executor = executor

        async def get_blocking_chain(self, uid: str) -> "Result[list[dict]]":
            return await self.executor.execute_query(
                "MATCH (e {uid: $uid})-[:BLOCKS*1..5]->(b) RETURN b",
                {"uid": uid},
            )

    # In bootstrap.py, satisfied by any backend or a standalone executor:
    # lateral_service = LateralRelationshipService(executor=tasks_backend)
    # lateral_service = LateralRelationshipService(executor=neo4j_query_executor)


CrudOperations[T] — minimal CRUD dependency:

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from core.ports import CrudOperations
        from core.models.task.task import Task

    class TaskStatusUpdater:
        \"\"\"Only creates and reads tasks — no search, no graph ops.\"\"\"

        def __init__(self, backend: "CrudOperations[Task]") -> None:
            self.backend = backend

        async def mark_complete(self, uid: str) -> None:
            await self.backend.update(uid, {"status": "completed"})


RelationshipCrudOperations — creating graph edges:

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from core.ports import RelationshipCrudOperations
        from core.models.relationship_names import RelationshipName

    class GoalLinkService:
        def __init__(self, backend: "RelationshipCrudOperations") -> None:
            self.backend = backend

        async def link_task_to_goal(self, task_uid: str, goal_uid: str) -> None:
            await self.backend.add_relationship(
                task_uid, goal_uid, RelationshipName.FULFILLS_GOAL
            )


RelationshipQueryOperations — counting edges without loading entities:

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from core.ports import RelationshipQueryOperations
        from core.models.relationship_names import RelationshipName

    class PrerequisiteChecker:
        def __init__(self, backend: "RelationshipQueryOperations") -> None:
            self.backend = backend

        async def count_blocking(self, task_uid: str) -> int:
            result = await self.backend.count_related(
                task_uid, RelationshipName.BLOCKS, direction="incoming"
            )
            return result.value if result.is_ok else 0


GraphTraversalOperations — cross-domain intelligence:

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from core.ports import GraphTraversalOperations

    class TaskIntelligenceService:
        def __init__(self, backend: "GraphTraversalOperations") -> None:
            self.backend = backend

        async def get_cross_domain_context(self, task_uid: str) -> list[dict]:
            result = await self.backend.get_domain_context_raw(
                entity_uid=task_uid,
                entity_label="Task",
                relationship_types=["APPLIES_KNOWLEDGE", "FULFILLS_GOAL"],
                depth=2,
            )
            return result.value if result.is_ok else []


BackendOperations[T] — full protocol for domain services:

    # Use this when a service is a full domain facade with CRUD, search,
    # relationships, and intelligence all in one.

    from core.services.base_service import BaseService
    from core.ports import BackendOperations

    class TasksCoreService(BaseService[BackendOperations["Task"], Task]):
        pass  # inherits all 7 mixin groups


Passing to Route Factories
--------------------------
Route function signatures should declare the narrowest protocol that routes
actually call. CRUD-only routes don't need GraphTraversalOperations.

    # Too broad — gives routes access they don't use:
    def create_tasks_api_routes(tasks_service: BackendOperations[Task]) -> ...:

    # Correct — ISP-compliant route signature:
    def create_tasks_api_routes(tasks_service: TasksService) -> ...:
        # TasksService is the facade, type-checked via concrete class
        # (see CLAUDE.md: route-facing types use concrete facade class)


Why BackendOperations[T] Is the Default
-----------------------------------------
BaseService accepts BackendOperations[T] because its 7 mixins collectively
use all 7 sub-protocols. Breaking the backend dependency into 7 separate
constructor parameters would create noise without benefit. Use focused
sub-protocols only when a service genuinely uses fewer than ~3 of the groups.

Rule of thumb:
    - Uses 1-2 sub-protocol groups → depend on those sub-protocols
    - Uses 3+ sub-protocol groups → use BackendOperations[T]


See Also
--------
    core/ports/base_protocols.py  — Protocol definitions
    docs/patterns/BACKEND_OPERATIONS_ISP.md  — Architecture rationale
    adapters/persistence/neo4j/universal_backend.py  — Single implementation
"""

# Re-export the protocols named here so `from core.ports.backend_operations_typing
# import QueryExecutor` works as a documentation-friendly import path.
from core.ports.base_protocols import (
    BackendOperations,
    CrudOperations,
    EntitySearchOperations,
    GraphTraversalOperations,
    LowLevelOperations,
    QueryExecutor,
    RelationshipCrudOperations,
    RelationshipMetadataOperations,
    RelationshipQueryOperations,
)

__all__ = [
    "BackendOperations",
    "CrudOperations",
    "EntitySearchOperations",
    "GraphTraversalOperations",
    "LowLevelOperations",
    "QueryExecutor",
    "RelationshipCrudOperations",
    "RelationshipMetadataOperations",
    "RelationshipQueryOperations",
]
