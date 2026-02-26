"""
Universal Neo4j Backend
=======================

SKUEL's 14-Domain Persistence Layer
------------------------------------

This module provides the universal backend for the 14 domains in SKUEL.
A single generic implementation replaces what would otherwise be 14+
separate domain-specific backend classes.

DOMAINS SERVED BY THIS BACKEND (12 of 14)
-----------------------------------------

**Activity Domains (7):**
    UniversalNeo4jBackend[Task] - tasks_backend
    UniversalNeo4jBackend[Goal] - goals_backend
    UniversalNeo4jBackend[Habit] - habits_backend
    UniversalNeo4jBackend[Event] - events_backend
    UniversalNeo4jBackend[Choice] - choices_backend
    UniversalNeo4jBackend[Principle] - principles_backend
    UniversalNeo4jBackend[ExpensePure] - finance_backend

**Curriculum Domains (3):**
    UniversalNeo4jBackend[KnowledgeUnit] - knowledge_backend (ku:)
    UniversalNeo4jBackend[LearningStep] - ls_backend (ls:)
    UniversalNeo4jBackend[LearningPath] - lp_backend (lp:)

**Content/Organization Domains (2 of 4):**
    UniversalNeo4jBackend[Report] - reports_backend (journals are Report with report_type=JOURNAL)
    UniversalNeo4jBackend[Moc] - moc_backend

DOMAINS NOT USING THIS BACKEND (2 of 14)
----------------------------------------

    13. LifePath - Uses cross-domain queries (AnalyticsLifePathService)
    14. Analytics - Read-only aggregation (no entity storage)

THE 4 CROSS-CUTTING SYSTEMS
---------------------------

    1. UserContext - UserBackend (dedicated, not UniversalNeo4jBackend)
    2. Search - SearchRouter → Domain SearchServices (One Path Forward, January 2026)
    3. Askesis - Cross-domain queries (no dedicated backend)
    4. Messaging - Conversation models (no dedicated backend)

100% DYNAMIC BACKEND PATTERN
----------------------------

Core Principle: "The plant grows on the lattice"

This backend enables SKUEL's dynamic architecture:
    - Add field to model → Instantly queryable via find_by()
    - Storage: Auto-serialization via introspection
    - Retrieval: Auto-deserialization via type hints
    - Queries: find_by(field__lt=5.0) auto-generated
    - All operators work: gte, lte, contains, in

Key Features:
    - Generic type support for any entity type
    - Convention-based label mapping
    - Automatic serialization/deserialization
    - Full CRUD operations with Result[T] pattern
    - Domain-specific queries through generic interface
    - Protocol compliance for all domain operations

See Also:
    /core/models/shared_enums.py - Domain enum definitions
    /core/ports/domain_protocols.py - Service interfaces
    /services_bootstrap.py - Service composition
"""

from __future__ import annotations

import time
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any

from adapters.persistence.neo4j.relationship_builders import RelationshipBuilder
from core.models.enums.neo_labels import NeoLabel
from core.models.protocols import DomainModelProtocol
from core.models.query import QueryIntent, UnifiedQueryBuilder
from core.models.relationship_names import RelationshipName
from core.utils.error_boundary import safe_backend_operation
from core.utils.logging import get_logger
from core.utils.neo4j_mapper import from_neo4j_node, to_neo4j_node
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    import builtins
    from collections.abc import Callable

    from neo4j import AsyncDriver

    from core.models.graph_context import GraphContext
    from core.models.semantic import EdgeMetadata
    from core.ports.base_protocols import (
        Direction,
        GraphContextNode,
        RelationshipMetadata,
    )

logger = get_logger(__name__)


class UniversalNeo4jBackend[T: DomainModelProtocol]:
    """
    Universal backend for ANY entity type implementing DomainModelProtocol.

    Replaces 12+ domain-specific backend files with a single, generic implementation
    that works for all entity types. This is SKUEL's foundation for the "100% Dynamic
    Backend" pattern.

    Key Features:
        - **Universal CRUD**: create, get, update, DETACH DELETE, list work for any entity
        - **Dynamic Querying**: find_by() auto-generates queries from model fields
        - **Graph-Native Relationships**: Pure Neo4j edges, not serialized UID lists
        - **Path-Aware Intelligence**: Cross-domain context with relationship traversal
        - **Protocol Compliance**: Automatically satisfies all domain-specific protocols
        - **Type Safety**: Generic type parameter ensures type-safe operations

    Architecture:
        - Type Parameter: T must implement DomainModelProtocol (uid, created_at, to_dto, from_dto)
        - Query Building: Uses UnifiedQueryBuilder for all Cypher generation
        - Relationship API: Fluent RelationshipBuilder for graph operations
        - Error Handling: All methods return Result[T] (never raise exceptions)

    Supported Domains:
        - Activity: Tasks, Events, Habits, Goals, Choices, Principles
        - Knowledge: KnowledgeUnit, LearningPath, LearningStep
        - Finance: Expenses, Budgets
        - Content: Journals, Transcriptions, Assignments
        - Identity: Users (with UserBackend extensions)

    Performance:
        - Batch Operations: get_many() for N+1 query prevention
        - Efficient Queries: UnifiedQueryBuilder optimizes filters and indexes
        - Relationship Counting: count_related() without loading entities
        - Graph Intelligence: Optional -4 integration for smart traversal

    Usage:
        ```python
        from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
        from core.models.enums import NeoLabel
        from core.models.entity_types import Ku

        # All domain entities use NeoLabel.ENTITY (universal label)
        tasks_backend = UniversalNeo4jBackend[Ku](
            driver=neo4j_driver, label=NeoLabel.ENTITY, entity_class=Ku,
            default_filters={"ku_type": "task"},
        )

        # CRUD operations
        result = await tasks_backend.create(task)
        result = await tasks_backend.get("task:123")
        result = await tasks_backend.update("task:123", {"status": "completed"})
        result = await tasks_backend.DETACH DELETE("task:123", cascade=True)

        # Dynamic querying (any field!)
        result = await tasks_backend.find_by(priority="high", status="active")
        result = await tasks_backend.find_by(due_date__gte=date.today())

        # Graph relationships
        await tasks_backend.create_relationship(
            from_uid="task:123",
            to_uid="ku:python-basics",
            relationship_type="APPLIES_KNOWLEDGE",
        )
        ```

    Extension Points:
        - graph_intelligence_service: Enable -4 smart graph traversal
        - RelationshipRegistry: Validate relationship types per domain
        - Custom protocols: Add domain-specific methods (auto-delegated)

    MyPy Limitations (Documented Technical Debt):
        This file contains ~46 MyPy errors that are INTENTIONAL and DOCUMENTED.
        These arise from MyPy's limitations with advanced generic programming patterns.

        **Impact**: None - All 151/151 integration tests pass, runtime behavior is correct.

        **Error Categories**:
        1. Optional type inference: `list?[...]` not recognized as always initialized
        2. Generic constraints: MyPy can't verify protocol satisfaction statically
        3. Returning Any: Dynamic type resolution inherently untyped
        4. Indexable assertions: MyPy doesn't trust initialization guarantees

        **Rationale**: The "100% Dynamic Backend" pattern trades static type verification
        for zero code duplication. We verify correctness through comprehensive tests
        rather than satisfying MyPy's generic inference limitations.

        **Documentation**: See `/docs/technical_debt/MYPY_BACKEND_LIMITATIONS.md`

    See Also:
        - DomainModelProtocol: Required interface for all domain models
        - UnifiedQueryBuilder: Query construction and optimization
        - RelationshipRegistry: Valid relationship types per domain
        - RelationshipBuilder: Fluent API for graph operations
    """

    def __init__(
        self,
        driver: AsyncDriver,
        label: str | NeoLabel,
        entity_class: type[T],
        graph_intelligence_service: Any | None = None,
        *,
        validate_label: bool = True,
        prometheus_metrics: Any | None = None,
        default_filters: dict[str, Any] | None = None,
        base_label: str | NeoLabel | None = None,
    ) -> None:
        """
        Initialize universal backend for any entity type.

        Args:
            driver: Neo4j async driver
            label: Node label - can be NeoLabel enum or string (e.g., NeoLabel.TASK, "Task")
            entity_class: Entity class for serialization (e.g., Task, Goal)
            graph_intelligence_service: Optional GraphIntelligenceService for -4 queries
            validate_label: If True, validates label against NeoLabel enum (default: True)
            prometheus_metrics: PrometheusMetrics instance for database instrumentation
            default_filters: Properties automatically applied to all queries and new nodes.
                Legacy mechanism for Ku-type discrimination. Superseded by domain-specific
                labels (e.g., NeoLabel.TASK instead of NeoLabel.ENTITY + default_filters).
            base_label: Universal base label for multi-label CREATE operations.
                When set, CREATE produces ``(n:Entity:Task)`` — :Entity universal
                label and domain-specific label. Used for domain entities;
                non-Entity backends (Finance, Group) don't set this.

        Raises:
            ValueError: If validate_label=True and label is not a valid NeoLabel

        Example:
            # Domain-specific label with multi-label CREATE
            tasks_backend = UniversalNeo4jBackend[Task](
                driver, NeoLabel.TASK, Task, base_label=NeoLabel.ENTITY
            )

            # Non-Entity backends — single label, no base_label
            finance_backend = UniversalNeo4jBackend[ExpensePure](
                driver, NeoLabel.EXPENSE, ExpensePure
            )

            # Skip validation for edge cases (e.g., tests with dynamic labels)
            backend = UniversalNeo4jBackend[Task](driver, "TestLabel", Task, validate_label=False)
        """
        self.driver = driver

        # Extract string value from NeoLabel if provided
        label_str = label.value if isinstance(label, NeoLabel) else label

        # Validate label against known labels (codebase self-awareness)
        if validate_label and not NeoLabel.is_valid(label_str):
            valid_labels = ", ".join(sorted(NeoLabel.all_labels()))
            raise ValueError(
                f"Unknown Neo4j label '{label_str}'. "
                f"Valid labels: {valid_labels}. "
                f"Use validate_label=False to skip validation for testing."
            )

        self.label = label_str
        self.entity_class = entity_class
        self.graph_intel = graph_intelligence_service
        self.prometheus_metrics = prometheus_metrics
        self.default_filters = default_filters or {}
        self.logger = get_logger(f"skuel.universal.{label_str.lower()}")

        # Multi-label support: base_label enables CREATE (n:Entity:Task)
        base_label_str = base_label.value if isinstance(base_label, NeoLabel) else base_label
        self.base_label = base_label_str

        # Build the CREATE label string
        if self.base_label:
            # Multi-label: Entity base + domain-specific
            self._create_labels = f"{self.base_label}:{self.label}"
        else:
            # Single-label: non-Entity backends (Finance, Group, etc.)
            self._create_labels = self.label

        # UnifiedQueryBuilder for all query building
        self.query_builder = UnifiedQueryBuilder(executor=self)

        intel_status = "with Phase 1-4" if graph_intelligence_service else "basic"
        metrics_status = "metrics-enabled" if prometheus_metrics else "no-metrics"
        labels_status = f"labels={self._create_labels}" if self.base_label else "single-label"
        self.logger.info(
            f"{label_str} universal backend initialized ({intel_status}, {metrics_status}, {labels_status}) [UnifiedQueryBuilder]"
        )

    def _track_db_metrics(self, operation: str, duration: float, is_error: bool = False) -> None:
        """
        Track database operation metrics.

        Args:
            operation: Operation type (create/read/update/delete)
            duration: Operation duration in seconds
            is_error: Whether the operation resulted in an error
        """
        if not self.prometheus_metrics:
            return

        # Track query count
        self.prometheus_metrics.db.queries_total.labels(operation=operation, label=self.label).inc()

        # Track latency
        self.prometheus_metrics.db.query_duration.labels(
            operation=operation, label=self.label
        ).observe(duration)

        # Track errors
        if is_error:
            self.prometheus_metrics.db.query_errors.labels(operation=operation).inc()

    # ============================================================================
    # DEFAULT FILTER HELPERS (Unified Ku Model - )
    # ============================================================================

    def _default_filter_clause(self, node_var: str = "n") -> str:
        """Generate AND-joined conditions from default_filters.

        Returns empty string if no default_filters. Uses ``_df_`` prefixed
        parameter names to avoid collisions with caller parameters.

        Args:
            node_var: Cypher variable name for the node (default "n").

        Returns:
            Condition string like ``n.ku_type = $_df_ku_type`` or empty string.
        """
        if not self.default_filters:
            return ""
        return " AND ".join(f"{node_var}.{k} = $_df_{k}" for k in self.default_filters)

    def _default_filter_params(self) -> dict[str, Any]:
        """Return default_filters as query params with ``_df_`` prefix."""
        return {f"_df_{k}": v for k, v in self.default_filters.items()}

    def _inject_default_filters(
        self,
        where_clauses: builtins.list[str],
        params: dict[str, Any],
        node_var: str = "n",
    ) -> None:
        """Append default_filter conditions to existing WHERE clause lists.

        Mutates ``where_clauses`` and ``params`` in place. Safe to call when
        ``default_filters`` is empty (no-op).
        """
        for k, v in self.default_filters.items():
            where_clauses.append(f"{node_var}.{k} = $_df_{k}")
            params[f"_df_{k}"] = v

    # ============================================================================
    # UNIVERSAL CRUD - WORKS FOR ANY ENTITY TYPE
    # ============================================================================

    @safe_backend_operation("create")
    async def create(self, entity: T) -> Result[T]:
        """
        Create any entity type.

        AUTO-CREATES USER RELATIONSHIP: If entity has user_uid field,
        automatically creates (User)-[:OWNS]->(Entity) relationship.

        Multi-label CREATE: When base_label is set, creates nodes with
        dual labels: ``(n:Entity:Task)``.
        """
        start_time = time.time()
        node_data = to_neo4j_node(entity)

        # Ensure default_filter properties are set on new nodes (e.g., ku_type)
        node_data.update(self.default_filters)

        # Extract user_uid if present (for auto-relationship creation)
        user_uid = node_data.get("user_uid")

        query = f"""
        CREATE (n:{self._create_labels})
        SET n = $props
        RETURN n
        """

        async with self.driver.session() as session:
            result = await session.run(query, {"props": node_data})
            record = await result.single()

            if not record:
                # Track error metrics
                self._track_db_metrics("create", time.time() - start_time, is_error=True)
                return Result.fail(Errors.database("create", f"Failed to create {self.label}"))

            created = from_neo4j_node(dict(record["n"]), self.entity_class)

            # Auto-create user relationship if user_uid exists
            if user_uid:
                rel_result = await self.create_user_relationship(
                    user_uid=user_uid, entity_uid=created.uid, relationship_type="OWNS"
                )

                if rel_result.is_error:
                    self.logger.warning(
                        f"Created {self.label} {created.uid} but failed to create user relationship: {rel_result.error}"
                    )
                    # Don't fail the entire create operation - entity was created successfully
                else:
                    self.logger.debug(
                        f"Auto-created OWNS relationship for {self.label} {created.uid}"
                    )

            # Track metrics
            self._track_db_metrics("create", time.time() - start_time, is_error=False)

            return Result.ok(created)

    @safe_backend_operation("get")
    async def get(self, uid: str) -> Result[T | None]:
        """
        Get any entity by UID.

        Retrieves a single entity from the Neo4j database by its unique identifier.
        Returns None if the entity does not exist.

        Args:
            uid: Unique identifier of the entity (e.g., "task:123", "event:456")

        Returns:
            Result[T | None]: Success with entity if found, Success with None if not found,
                             or Failure if database error occurs

        Example:
            ```python
            backend = UniversalNeo4jBackend[Task](driver, "Task", Task)
            result = await backend.get("task:123")

            if result.is_ok:
                task = result.value
                if task:
                    print(f"Found task: {task.title}")
                else:
                    print("Task not found")
            else:
                print(f"Error: {result.error}")
            ```

        Note:
            - This method does NOT raise exceptions - all errors are wrapped in Result
            - Not found is NOT an error - returns Result.ok(None)
            - For batch retrieval, use get_many() to avoid N+1 queries
        """
        df_clause = self._default_filter_clause()
        where_line = f"WHERE {df_clause}" if df_clause else ""

        query = f"""
        MATCH (n:{self.label} {{uid: $uid}})
        {where_line}
        RETURN n
        """

        params: dict[str, Any] = {"uid": uid}
        params.update(self._default_filter_params())

        async with self.driver.session() as session:
            result = await session.run(query, params)
            record = await result.single()

            if not record:
                return Result.ok(None)

            entity = from_neo4j_node(dict(record["n"]), self.entity_class)
            return Result.ok(entity)

    @safe_backend_operation("get_many")
    async def get_many(self, uids: builtins.list[str]) -> Result[builtins.list[T]]:
        """
        Get multiple entities by UIDs in a single batched query.

        This method prevents N+1 query problems by fetching all requested
        entities in ONE database roundtrip using Neo4j's WHERE IN clause.

        **Critical for GraphQL DataLoader batching!**

        Args:
            uids: List of entity UIDs to fetch

        Returns:
            Result[List[T]] with entities in the SAME ORDER as input UIDs.
            Missing entities are represented as None in the list to maintain
            position correspondence with the input UIDs (DataLoader requirement).

        Example:
            # Fetch 10 knowledge units in one query instead of 10 separate queries
            result = await backend.get_many([
                "ku.python.basics",
                "ku.python.functions",
                "ku.python.classes"
            ])
            # Returns list with 3 KnowledgeUnit objects in same order

        Performance:
            - 10 entities: 10 queries → 1 query (~10x faster)
            - 100 entities: 100 queries → 1 query (~100x faster)
        """
        if not uids:
            return Result.ok([])

        # Guard: Skip operation if driver is closed (test teardown)
        if self._is_driver_closed():
            return Result.ok([])

        df_clause = self._default_filter_clause()
        extra_where = f" AND {df_clause}" if df_clause else ""

        query = f"""
        MATCH (n:{self.label})
        WHERE n.uid IN $uids{extra_where}
        RETURN n
        """

        params: dict[str, Any] = {"uids": uids}
        params.update(self._default_filter_params())

        async with self.driver.session() as session:
            result = await session.run(query, params)
            records = await result.data()

            # Create uid-to-entity map for fast lookup
            entity_map = {}
            for record in records:
                entity = from_neo4j_node(record["n"], self.entity_class)
                entity_map[entity.uid] = entity

            # Return entities in same order as input UIDs (DataLoader requirement)
            # Missing entities are None to maintain correspondence
            entities = [entity_map.get(uid) for uid in uids]

            self.logger.debug(
                f"Batched get_many: fetched {len(records)} of {len(uids)} {self.label} entities"
            )
            return Result.ok(entities)

    @safe_backend_operation("update")
    async def update(self, uid: str, updates: dict[str, Any]) -> Result[T]:
        """
        Update any entity by UID.

        Performs a partial update of an entity, modifying only the fields specified
        in the updates dictionary. Automatically sets updated_at timestamp.

        Args:
            uid: Unique identifier of the entity to update
            updates: Dictionary of field names to new values (partial update)

        Returns:
            Result[T]: Success with updated entity, or Failure if entity not found
                      or database error occurs

        Example:
            ```python
            backend = UniversalNeo4jBackend[Task](driver, "Task", Task)

            # Update specific fields
            result = await backend.update(
                "task:123",
                {
                    "status": "completed",
                    "priority": "high",
                    "completion_notes": "Finished ahead of schedule",
                },
            )

            if result.is_ok:
                task = result.value
                print(f"Updated task: {task.title}")
            ```

        Note:
            - Uses Neo4j's += operator for partial updates (preserves other fields)
            - Automatically adds updated_at timestamp
            - Returns error if entity doesn't exist (use get() first to check)
            - Empty updates dictionary returns validation error
        """
        start_time = time.time()

        if not updates:
            self._track_db_metrics("update", time.time() - start_time, is_error=True)
            return Result.fail(Errors.validation("No updates provided", field="updates"))

        # Add updated_at timestamp
        updates["updated_at"] = datetime.now().isoformat()

        # Prevent overwriting default_filter properties (e.g., ku_type)
        for k in self.default_filters:
            updates.pop(k, None)

        df_clause = self._default_filter_clause()
        where_line = f"WHERE {df_clause}" if df_clause else ""

        query = f"""
        MATCH (n:{self.label} {{uid: $uid}})
        {where_line}
        SET n += $updates
        RETURN n
        """

        params: dict[str, Any] = {"uid": uid, "updates": updates}
        params.update(self._default_filter_params())

        async with self.driver.session() as session:
            result = await session.run(query, params)
            record = await result.single()

            if not record:
                self._track_db_metrics("update", time.time() - start_time, is_error=True)
                return Result.fail(Errors.not_found("resource", f"{self.label} {uid} not found"))

            updated = from_neo4j_node(dict(record["n"]), self.entity_class)

            # Track metrics
            self._track_db_metrics("update", time.time() - start_time, is_error=False)

            return Result.ok(updated)

    @safe_backend_operation("delete")
    async def delete(self, uid: str, cascade: bool = False) -> Result[bool]:
        """
        DETACH DELETE any entity by UID.

        Removes an entity from the Neo4j database. Optionally deletes all relationships
        (cascade=True) or requires manual relationship cleanup (cascade=False).

        Args:
            uid: Unique identifier of the entity to DETACH DELETE
            cascade: If True, deletes entity and all its relationships (DETACH DELETE).
                    If False, fails if entity has relationships (requires manual cleanup).

        Returns:
            Result[bool]: Success with True if deleted, False if not found,
                         or Failure if database error occurs (e.g., relationships exist)

        Example:
            ```python
            backend = UniversalNeo4jBackend[Task](driver, "Task", Task)

            # DETACH DELETE with relationships (cascade)
            result = await backend.DETACH DELETE("task:123", cascade=True)

            if result.is_ok and result.value:
                print("Task and all relationships deleted")

            # DETACH DELETE without relationships (fails if relationships exist)
            result = await backend.DETACH DELETE("task:456", cascade=False)
            ```

        Warning:
            - cascade=True deletes ALL relationships (incoming and outgoing)
            - cascade=False will fail if entity has any relationships
            - Deletion is permanent - no soft DETACH DELETE or recovery
            - Consider backing up data before cascade DETACH DELETE operations

        Note:
            - Returns True even if entity didn't exist (idempotent)
            - Use cascade=True for most deletions to avoid orphaned relationships
        """
        start_time = time.time()

        df_clause = self._default_filter_clause()
        where_line = f"WHERE {df_clause}" if df_clause else ""

        if cascade:
            # DETACH DELETE removes entity AND all relationships
            query = f"""
            MATCH (n:{self.label} {{uid: $uid}})
            {where_line}
            DETACH DELETE n
            RETURN count(n) as deleted
            """
        else:
            # DELETE only - intentionally fails if relationships exist (safety check).
            # Use cascade=True to remove relationships too.
            query = f"""
            MATCH (n:{self.label} {{uid: $uid}})
            {where_line}
            DELETE n // noqa: CYP002 - intentional: non-DETACH DELETE is the safety check
            RETURN count(n) as deleted
            """

        params: dict[str, Any] = {"uid": uid}
        params.update(self._default_filter_params())

        async with self.driver.session() as session:
            try:
                result = await session.run(query, params)
                summary = await result.consume()

                deleted = summary.counters.nodes_deleted > 0

                # Track metrics
                self._track_db_metrics("delete", time.time() - start_time, is_error=False)

                return Result.ok(deleted)
            except Exception as e:
                error_msg = str(e)
                # Neo4j constraint error when trying to delete node with relationships
                if "Cannot delete" in error_msg and "relationship" in error_msg.lower():
                    self._track_db_metrics("delete", time.time() - start_time, is_error=True)
                    return Result.fail(
                        Errors.business(
                            rule="delete_with_relationships",
                            message=f"Cannot delete {self.label} '{uid}' - has existing relationships. "
                            "Use cascade=True to delete with relationships.",
                        )
                    )
                # Track error for other exceptions
                self._track_db_metrics("delete", time.time() - start_time, is_error=True)
                raise

    @safe_backend_operation("list")
    async def list(
        self,
        limit: int = 100,
        offset: int = 0,
        filters: dict[str, Any] | None = None,
        sort_by: str | None = None,
        sort_order: str = "asc",
    ) -> Result[builtins.list[T]]:
        """
        List any entity type with dynamic filters.

        Now uses UnifiedQueryBuilder with fluent API.
        Add a field to your model → it's automatically filterable!
        """
        # Build query using UnifiedQueryBuilder fluent API
        # Pass label explicitly to ensure correct Neo4j label is used
        builder = (
            self.query_builder.for_model(self.entity_class, label=self.label)
            .limit(limit)
            .offset(offset)
        )

        # Inject default_filters for Ku-type discrimination
        if self.default_filters:
            builder = builder.filter(**self.default_filters)

        if filters:
            builder = builder.filter(**filters)

        if sort_by:
            builder = builder.order_by(sort_by, desc=(sort_order == "desc"))

        query, params = builder.build()

        async with self.driver.session() as session:
            result = await session.run(query, params)
            records = await result.data()

            entities = [from_neo4j_node(r["n"], self.entity_class) for r in records]
            return Result.ok(entities)

    # ============================================================================
    # -4 GRAPH INTELLIGENCE INTEGRATION
    # ============================================================================

    @safe_backend_operation("get_with_graph_context")
    async def get_with_graph_context(
        self, uid: str, intent: QueryIntent | None = None, depth: int = 2
    ) -> Result[tuple[T | None, GraphContext | None]]:
        """
        Get entity with graph context in single call using -4.

        This method combines entity retrieval with graph intelligence,
        leveraging the entity's own query building methods if available.

        Args:
            uid: Entity UID,
            intent: Query intent (uses entity's suggested intent if not provided),
            depth: Graph traversal depth (default 2)

        Returns:
            Tuple of (entity, graph_context) or (None, None) if not found

        Example:
            ```python
            # Get task with graph context
            result = await backend.get_with_graph_context(
                "task_123", intent=QueryIntent.PREREQUISITE, GraphDepth.DEFAULT
            )

            if result.is_ok:
                task, context = result.value
                print(f"Task: {task.title}")
                print(f"Connected domains: {context.domains_involved}")
                print(f"Total relationships: {context.total_relationships}")
            ```
        """
        if not self.graph_intel:
            return Result.fail(
                Errors.system(
                    "Graph intelligence service is required for context queries",
                    service="UniversalBackend",
                    user_message="Please configure GraphIntelligenceService to use graph context features",
                )
            )

        # Get entity first
        entity_result = await self.get(uid)
        if entity_result.is_error:
            return Result.fail(entity_result.expect_error())

        entity = entity_result.value
        if not entity:
            return Result.ok((None, None))

        # Determine query intent
        query_intent = intent

        # Use entity's domain logic to suggest intent if not provided
        if not query_intent:
            suggest_fn: Callable[[], QueryIntent] | None = getattr(
                entity, "get_suggested_query_intent", None
            )
            if suggest_fn is not None:
                try:
                    query_intent = suggest_fn()
                except Exception as e:
                    self.logger.warning(f"Failed to get suggested intent: {e}")

        if not query_intent:
            query_intent = QueryIntent.SPECIFIC

        # Build query via infrastructure (not entity — entities express intent, not Cypher)
        from core.models.query.graph_traversal import build_graph_context_query

        cypher_query = build_graph_context_query(node_uid=uid, intent=query_intent, depth=depth)

        # Execute query through GraphIntelligenceService
        try:
            context_result = await self.graph_intel.execute_query(
                cypher_query, {"uid": uid, "depth": depth}, query_intent=query_intent
            )

            if context_result.is_error:
                self.logger.error(f"Graph context query failed: {context_result.error}")
                return Result.fail(
                    Errors.database(
                        operation="get_graph_context",
                        message=f"Failed to retrieve graph context for {self.label} {uid}: {context_result.error}",
                        entity=self.label,
                    )
                )

            graph_context = context_result.value

            self.logger.info(
                f"Retrieved {self.label} {uid} with graph context: "
                f"{graph_context.total_nodes} nodes, {graph_context.total_relationships} relationships"
            )

            return Result.ok((entity, graph_context))

        except Exception as e:
            self.logger.error(f"Failed to get graph context: {e}")
            return Result.fail(
                Errors.database(
                    operation="get_graph_context",
                    message=f"Exception while retrieving graph context for {self.label} {uid}: {e!s}",
                    entity=self.label,
                )
            )

    def _is_driver_closed(self) -> bool:
        """
        Check if the Neo4j driver has been closed.

        Used during test teardown to prevent "driver already closed" warnings.
        The _closed attribute is an internal Neo4j driver state indicator.

        Returns:
            True if driver is closed, False if still open

        Note:
            The _closed attribute is private to the Neo4j driver but is the
            recommended way to check driver state for graceful degradation.
            See: https://github.com/neo4j/neo4j-python-driver/issues/949
        """
        return getattr(self.driver, "_closed", False)

    # ============================================================================
    # UNIVERSAL DOMAIN-SPECIFIC OPERATIONS
    # ============================================================================

    @safe_backend_operation("find_by_date_range")
    async def find_by_date_range(
        self,
        start_date: date | str | None,
        end_date: date | str | None,
        date_field: str = "occurred_at",
        additional_filters: dict[str, Any] | None = None,
        limit: int = 100,
    ) -> Result[builtins.list[T]]:
        """Find any entity within a date range."""
        params: dict[str, Any] = {"limit": limit}
        where_clauses: builtins.list[str] = []

        # Inject default_filters for Ku-type discrimination
        self._inject_default_filters(where_clauses, params)

        # Build date range conditions
        if start_date:
            where_clauses.append(f"date(n.{date_field}) >= date($start_date)")
            if isinstance(start_date, date | datetime):
                params["start_date"] = start_date.isoformat()
            else:
                params["start_date"] = start_date

        if end_date:
            where_clauses.append(f"date(n.{date_field}) <= date($end_date)")
            if isinstance(end_date, date | datetime):
                params["end_date"] = end_date.isoformat()
            else:
                params["end_date"] = end_date

        # Add additional filters
        if additional_filters:
            for key, value in additional_filters.items():
                if value is not None:
                    where_clauses.append(f"n.{key} = ${key}")
                    params[key] = value

        where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        query = f"""
        MATCH (n:{self.label})
        {where_clause}
        RETURN n
        ORDER BY n.{date_field} DESC
        LIMIT $limit
        """

        async with self.driver.session() as session:
            result = await session.run(query, params)
            records = await result.data()

            entities = [from_neo4j_node(record["n"], self.entity_class) for record in records]
            return Result.ok(entities)

    @safe_backend_operation("search")
    async def search(self, query: str, limit: int = 10) -> Result[builtins.list[T]]:
        """
        Search any entity type by text.

        Performs case-sensitive substring search across common text fields:
        title, name, description, and content. Returns entities where query
        appears anywhere in these fields.

        Args:
            query: Search string (case-sensitive substring match)
            limit: Maximum number of results to return (default 10)

        Returns:
            Result[List[T]]: Success with matching entities (may be empty),
                            or Failure if database error

        Example:
            ```python
            backend = UniversalNeo4jBackend[Task](driver, "Task", Task)

            # Search for tasks containing "urgent"
            result = await backend.search("urgent", QueryLimit.MEDIUM)

            if result.is_ok:
                tasks = result.value
                print(f"Found {len(tasks)} urgent tasks")
                for task in tasks:
                    print(f"- {task.title}")
            ```

        Search Fields:
            - title: Primary entity title
            - name: Alternative name field
            - description: Entity description
            - content: Full entity content

        Limitations:
            - Case-sensitive matching (use LOWER() for case-insensitive)
            - Substring match only (not full-text search)
            - No relevance ranking
            - Searches across multiple fields (can't limit to specific field)

        Performance:
            - Sequential scan (no full-text index)
            - Use for simple queries only
            - For advanced search, use dedicated search service

        Note:
            - Returns empty list if no matches (not an error)
            - Field must exist and be non-null to match
            - For semantic search, use SearchIntelligenceService
            - For faceted search, use find_by() with filters

        See Also:
            - find_by(): Exact field matching with operators
            - SearchIntelligenceService: Semantic/embedding-based search
            - list(): Get all entities with filters
        """
        df_clause = self._default_filter_clause()
        extra_and = f"\n               AND {df_clause}" if df_clause else ""

        cypher = f"""
            MATCH (n:{self.label})
            WHERE (n.title CONTAINS $query
               OR n.name CONTAINS $query
               OR n.description CONTAINS $query
               OR n.content CONTAINS $query){extra_and}
            RETURN n
            LIMIT $limit
        """

        params: dict[str, Any] = {"query": query, "limit": limit}
        params.update(self._default_filter_params())

        async with self.driver.session() as session:
            result = await session.run(cypher, params)
            records = await result.data()

            entities = [from_neo4j_node(record["n"], self.entity_class) for record in records]
            return Result.ok(entities)

    @safe_backend_operation("find_by")
    async def find_by(self, limit: int = 100, **filters: Any) -> Result[builtins.list[T]]:
        """
        Dynamic find by any model field with operator support.

        This is the new 100% dynamic way to query - automatically supports
        ANY field you add to your model!

        Usage:
            # Simple equality
            tasks = await backend.find_by(priority='high', status='in_progress')

            # Comparison operators
            tasks = await backend.find_by(due_date__gte=date.today())
            tasks = await backend.find_by(estimated_hours__lt=5.0)

            # String matching
            tasks = await backend.find_by(title__contains='urgent')

            # List membership
            tasks = await backend.find_by(priority__in=['high', 'urgent'])

            # Pagination and sorting
            tasks = await backend.find_by(status='active', limit=QueryLimit.SMALL, offset=20)
            tasks = await backend.find_by(priority='high', sort_by='due_date', sort_order='asc')

        Supported operators:
            - eq (default): Exact match
            - gt, lt, gte, lte: Comparisons
            - contains: String matching
            - in: List membership

        Special parameters:
            - limit: Max results (default 100)
            - offset: Pagination offset
            - sort_by: Field name to sort by
            - sort_order: 'asc' or 'desc' (default 'asc')
        """
        start_time = time.time()

        # Extract pagination and sorting parameters
        offset_val = filters.pop("offset", 0)
        sort_by = filters.pop("sort_by", None)
        sort_order = filters.pop("sort_order", "asc")

        if not filters and not self.default_filters:
            return await self.list(limit=limit)  # type: ignore[no-any-return]

        # Merge default_filters (non-overridable) with caller filters
        all_filters = {**filters, **self.default_filters}

        # Use UnifiedQueryBuilder fluent API with explicit label
        query_builder = (
            self.query_builder.for_model(self.entity_class, label=self.label)
            .filter(**all_filters)
            .limit(limit)
        )

        # Apply pagination
        if offset_val > 0:
            query_builder = query_builder.offset(offset_val)

        # Apply sorting
        if sort_by:
            query_builder = query_builder.order_by(sort_by, desc=(sort_order == "desc"))

        query, params = query_builder.build()

        async with self.driver.session() as session:
            result = await session.run(query, params)
            records = await result.data()

            entities = [from_neo4j_node(r["n"], self.entity_class) for r in records]

            # Track metrics
            self._track_db_metrics("read", time.time() - start_time, is_error=False)

            return Result.ok(entities)

    @safe_backend_operation("count")
    async def count(self, **filters: Any) -> Result[int]:
        """
        Count any entity type with dynamic filters.

        Now uses UnifiedQueryBuilder - supports the same filter syntax as find_by().
        """
        # Merge default_filters with caller filters
        all_filters = {**filters, **self.default_filters}

        # Use UnifiedQueryBuilder fluent API for counting
        count = await (
            self.query_builder.for_model(self.entity_class, label=self.label).filter(**all_filters)
            if all_filters
            else self.query_builder.for_model(self.entity_class, label=self.label)
        ).count()

        return Result.ok(count)

    @safe_backend_operation("health_check")
    async def health_check(self) -> Result[bool]:
        """Check database health for any entity type."""
        cypher = "RETURN 1 as alive"

        async with self.driver.session() as session:
            result = await session.run(cypher, {})
            record = await result.single()

            return Result.ok(record and record["alive"] == 1)

    # ============================================================================
    # B: RAW GRAPH CONTEXT (DOMAIN-AGNOSTIC)
    # ============================================================================

    async def get_domain_context_raw(
        self,
        entity_uid: str,
        entity_label: str,
        relationship_types: builtins.list[str],
        depth: int = 2,
        min_confidence: float = 0.7,
        bidirectional: bool = False,
    ) -> Result[builtins.list[GraphContextNode]]:
        """
        Get raw graph context without domain-specific categorization.

        This is a PURE PRIMITIVE that returns typed graph traversal results.
        Domain-specific categorization happens in relationship/intelligence services.

        Args:
            entity_uid: Entity UID to query from
            entity_label: Neo4j label (e.g., "Task", "Goal", "Event")
            relationship_types: List of relationship types to traverse
            depth: Graph traversal depth (default 2)
            min_confidence: Minimum path confidence (default 0.7)
            bidirectional: Include incoming and outgoing (default False)

        Returns:
            Result[list[GraphContextNode]] with typed graph traversal results:
                - uid: Entity UID (str)
                - title: Entity title (str)
                - labels: Neo4j labels (list[str])
                - distance: Hops from source (int)
                - path_strength: Confidence cascade (float)
                - via_relationships: Relationship sequence with direction markers (list[str])

        Example:
            ```python
            # Get raw context for a task
            result = await backend.get_domain_context_raw(
                entity_uid="task:123",
                entity_label="Task",
                relationship_types=["DEPENDS_ON", "REQUIRES_KNOWLEDGE"],
                GraphDepth.NEIGHBORHOOD,
                bidirectional=True,
            )

            # Returns typed list - categorization done by caller
            for node in result.value:
                uid = node["uid"] # Type-safe: str
                labels = node["labels"] # Type-safe: list[str]
            ```

        Note:
            - This is domain-agnostic - works for ANY entity type
            - Categorization logic belongs in relationship/intelligence services

        See Also:
            - GraphContextNode for field type documentation
            - TasksRelationshipService.get_task_cross_domain_context() for usage
            - CypherGenerator.build_domain_context_with_paths()
        """
        from core.models.query import build_domain_context_with_paths

        try:
            # Build pure Cypher query
            query, params = build_domain_context_with_paths(
                node_uid=entity_uid,
                node_label=entity_label,
                relationship_types=relationship_types,
                depth=depth,
                min_confidence=min_confidence,
                bidirectional=bidirectional,
            )

            # Execute query
            async with self.driver.session() as session:
                result = await session.run(query, params)
                record = await result.single()

                if not record:
                    return Result.ok([])  # No context found (not an error)

                # Return raw domain_context list
                domain_context = record.get("domain_context", [])
                return Result.ok(domain_context)

        except Exception as e:
            self.logger.error(f"Failed to get raw domain context: {e}")
            return Result.fail(Errors.database(operation="get_domain_context_raw", message=str(e)))

    @safe_backend_operation("execute_query")
    async def execute_query(
        self, query: str, params: dict[str, Any] | None = None
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Execute a low-level Cypher query and return raw results.

        This method is used by batch query methods in relationship services
        to execute CypherGenerator queries efficiently.

        Args:
            query: Cypher query string
            params: Optional query parameters

        Returns:
            Result[list[dict]] with raw Neo4j records as dictionaries

        Example:
            ```python
            from core.models.query import build_batch_relationship_exists

            query, params = build_batch_relationship_exists(
                node_label="Task",
                relationship_types=["REQUIRES_KNOWLEDGE"],
                direction="outgoing",
            )
            params["uids"] = ["task:1", "task:2"]

            result = await backend.execute_query(query, params)
            # Returns: [{"uid": "task:1", "has_relationships": True}, ...]
            ```

        Note:
            - Returns raw dictionaries (not domain models)
            - Used primarily by batch query optimization methods
            - For domain model queries, use find_by() or search()
        """
        # Guard: Skip operation if driver is closed (test teardown)
        if self._is_driver_closed():
            return Result.ok([])

        if params is None:
            params = {}

        async with self.driver.session() as session:
            result = await session.run(query, params)
            records = await result.data()  # Get all records as dictionaries
            return Result.ok(records)

    # ============================================================================
    # DYNAMIC PROTOCOL COMPLIANCE - A
    # ============================================================================

    def __getattr__(self, name: str) -> Any:
        """
        Dynamic protocol compliance via attribute lookup.

        Automatically handles domain-specific protocol methods by delegating to
        universal methods. This eliminates ~1000 lines of boilerplate code.

        Supported Patterns:
            - create_{domain}(entity) → create(entity)
            - get_{domain}_by_uid(uid) → get(uid)
            - update_{domain}(uid, updates) → update(uid, updates)
            - delete_{domain}(uid) → DETACH DELETE(uid)
            - list_{domain}s(limit, **filters) → list(limit, filters=filters)

        Example:
            ```python
            # These calls are equivalent:
            await backend.create_task(task) # Via __getattr__
            await backend.create(task) # Direct call

            await backend.get_task_by_uid(uid) # Via __getattr__
            await backend.get(uid) # Direct call
            ```

        Note:
            - Only handles simple CRUD delegation
            - Domain-specific methods (link_X_to_Y, get_X_cross_domain_context)
              are NOT handled here - they have explicit implementations
            - Raises AttributeError if method doesn't match any pattern

        See Also:
            - Protocol definitions in core/ports/domain_protocols.py
            - A documentation in /docs/improvements/
        """
        # Pattern 1: create_{domain}(entity) → create(entity)
        if name.startswith("create_") and not name.endswith("_relationship"):
            return self.create

        # Pattern 2: get_{domain}_by_uid(uid) → get(uid)
        if name.startswith("get_") and name.endswith("_by_uid"):
            return self.get

        # Pattern 3: update_{domain}(uid, updates) → update(uid, updates)
        if name.startswith("update_") and not name.startswith("update_user"):
            return self.update

        # Pattern 4: delete_{domain}(uid) → delete(uid)
        if name.startswith("delete_") and not name.startswith("delete_user"):
            return self.delete

        # Pattern 5: list_{domain}s(limit, **filters) → list(limit, filters=filters)
        if name.startswith("list_") and name.endswith("s"):
            # For list_tasks, list_events, etc., we need a wrapper to handle **filters
            async def list_wrapper(limit: int = 100, **filters: Any) -> Result[builtins.list[T]]:
                return await self.list(limit=limit, filters=filters)  # type: ignore[no-any-return]

            return list_wrapper

        # No pattern matched - attribute doesn't exist
        raise AttributeError(
            f"'{type(self).__name__}' has no attribute '{name}'. "
            f"This may be a domain-specific method that should have an explicit implementation."
        )

    # ============================================================================
    # GRAPH-NATIVE RELATIONSHIP QUERIES
    # ============================================================================
    # Added: October 6, 2025
    # See: /docs/migrations/GRAPH_NATIVE_MIGRATION_PLAN.md
    #
    # These methods query relationships from graph edges, not node properties.
    # This enables removing relationship fields from domain models.

    async def get_related_entities(
        self, uid: str, relationship_type: str, direction: str = "outgoing", limit: int = 100
    ) -> Result[builtins.list[T]]:
        """
        Get related entities via graph edges.

        Args:
            uid: Source entity UID,
            relationship_type: Neo4j relationship type (e.g., "PREREQUISITE", "ENABLES"),
            direction: Traversal direction - "outgoing", "incoming", or "both",
            limit: Max results to return

        Returns:
            Result[List[T]] of related entities

        Example:
            # Get all prerequisites for a knowledge unit
            result = await backend.get_related_entities(
                uid="ku:python-basics",
                relationship_type="PREREQUISITE",
                direction="incoming"
            )
        """
        try:
            # Build Cypher pattern using helper
            pattern_result = self._build_direction_pattern(
                relationship_type=relationship_type,
                direction=direction,
                target_label=self.label,
            )
            if pattern_result.is_error:
                return Result.fail(pattern_result.expect_error())
            pattern = pattern_result.value

            df_clause = self._default_filter_clause()
            where_line = f"WHERE {df_clause}" if df_clause else ""

            query = f"""
            MATCH (n:{self.label} {{uid: $uid}})
            {where_line}
            MATCH {pattern}
            RETURN related
            LIMIT $limit
            """

            params: dict[str, Any] = {"uid": uid, "limit": limit}
            params.update(self._default_filter_params())

            async with self.driver.session() as session:
                result = await session.run(query, params)
                records = [record async for record in result]

                entities = []
                for record in records:
                    node = record["related"]
                    entity = from_neo4j_node(node, self.entity_class)
                    entities.append(entity)

                self.logger.debug(f"Found {len(entities)} related entities via {relationship_type}")
                return Result.ok(entities)

        except Exception as e:
            self.logger.error(f"Failed to get related entities: {e}")
            return Result.fail(
                Errors.database(operation="get_related_entities", message=str(e), entity=self.label)
            )

    async def get_related_uids(
        self,
        uid: str,
        relationship_type: RelationshipName,
        direction: Direction = "outgoing",
        limit: int = 100,
        properties: dict[str, Any] | None = None,
    ) -> Result[builtins.list[str]]:
        """
        Get UIDs of related entities via graph edge traversal.

        GRAPH-NATIVE QUERY: Traverses Neo4j edges, NOT node properties.
        This method queries actual graph relationships, enabling:
        - Multi-hop traversal (can be extended with depth parameter)
        - Relationship metadata access (if edges have properties)
        - Bidirectional queries (direction="both")
        - True graph analytics (compatible with APOC algorithms)

        Faster than get_related_entities() when you only need UIDs (no node property loading).

        Args:
            uid: Source entity UID,
            relationship_type: Neo4j relationship type (e.g., "PREREQUISITE", "ENABLES"),
            direction: Traversal direction
                - "outgoing": (n)-[:TYPE]->(related) - What this enables/points to
                - "incoming": (n)<-[:TYPE]-(related) - What requires/points to this
                - "both": (n)-[:TYPE]-(related) - All connections regardless of direction,
            limit: Max results to return (default 100)
            properties: Optional dict of relationship properties to filter by

        Returns:
            Result[List[str]] of related entity UIDs from graph traversal

        Graph Traversal Examples:
            # Get UIDs of knowledge units this enables (outgoing ENABLES edges)
            result = await backend.get_related_uids(
                uid="ku:python-basics",
                relationship_type="ENABLES",
                direction="outgoing"
            )
            # Cypher: MATCH (n {uid: $uid})-[:ENABLES]->(related) RETURN related.uid

            # Get UIDs of prerequisites (incoming PREREQUISITE edges)
            result = await backend.get_related_uids(
                uid="ku:advanced-oop",
                relationship_type="PREREQUISITE",
                direction="incoming"
            )
            # Cypher: MATCH (n {uid: $uid})<-[:PREREQUISITE]-(related) RETURN related.uid

            # Get all related topics (bidirectional RELATED_TO edges)
            result = await backend.get_related_uids(
                uid="ku:lists",
                relationship_type="RELATED_TO",
                direction="both"
            )
            # Cypher: MATCH (n {uid: $uid})-[:RELATED_TO]-(related) RETURN related.uid

            # Get habits with property filtering (e.g., essentiality="essential")
            result = await backend.get_related_uids(
                uid="goal:fitness",
                relationship_type="REQUIRES_HABIT",
                direction="outgoing",
                properties={"essentiality": "essential"}
            )
            # Cypher: MATCH (n {uid: $uid})-[r:REQUIRES_HABIT]->(related)
            # WHERE r.essentiality = $prop_essentiality
            # RETURN related.uid

        Edge Direction Semantics:
            - PREREQUISITE: Use "incoming" for requirements
              (n)<-[:PREREQUISITE]-(prereq) means "prereq is required by n"
            - ENABLES: Use "outgoing" for what this unlocks
              (n)-[:ENABLES]->(next) means "n enables/unlocks next"
            - RELATED_TO: Use "both" for bidirectional relationships
              (n)-[:RELATED_TO]-(other) means "n and other are related"

        Performance Notes:
            - Uses index on uid for O(1) node lookup
            - Returns UIDs only (no property loading) - fast for large graphs
            - For full entities with properties, use get_related_entities()
            - Compatible with APOC path expansion for multi-hop queries

        See: /docs/architecture/GRAPH_NATIVE_ANALYSIS.md for architecture details
        """
        try:
            # Extract string value for Cypher query
            rel_type = relationship_type.value

            # Build Cypher pattern using helper (with named relationship variable for property access)
            pattern_result = self._build_direction_pattern(
                relationship_type=rel_type,
                direction=direction,
                rel_var="r",
            )
            if pattern_result.is_error:
                return Result.fail(pattern_result.expect_error())
            pattern = pattern_result.value

            # Build WHERE clause for property filtering
            where_clauses = []
            params = {"uid": uid, "limit": limit}

            if properties:
                for key, value in properties.items():
                    param_name = f"prop_{key}"
                    where_clauses.append(f"r.{key} = ${param_name}")
                    params[param_name] = value

            where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

            query = f"""
            MATCH (n {{uid: $uid}})
            MATCH {pattern}
            {where_clause}
            RETURN related.uid as uid
            LIMIT $limit
            """

            async with self.driver.session() as session:
                result = await session.run(query, params)
                records = [record async for record in result]
                uids = [record["uid"] for record in records if record["uid"]]

                self.logger.debug(f"Found {len(uids)} related UIDs via {relationship_type}")
                return Result.ok(uids)

        except Exception as e:
            self.logger.error(f"Failed to get related UIDs: {e}")
            return Result.fail(Errors.database(operation="get_related_uids", message=str(e)))

    async def get_relationship_metadata(
        self, from_uid: str, to_uid: str, relationship_type: RelationshipName
    ) -> Result[RelationshipMetadata | None]:
        """
        Get relationship edge properties as typed metadata.

        Returns properties like strength, confidence, semantic_distance.
        Uses RelationshipMetadata TypedDict for ~80% type coverage of common fields.

        Args:
            from_uid: Source entity UID,
            to_uid: Target entity UID,
            relationship_type: Neo4j relationship type

        Returns:
            Result[Optional[Dict]] with relationship properties, or None if not found

        Example:
            # Get metadata for a prerequisite relationship
            result = await backend.get_relationship_metadata(
                from_uid="ku:programming-101",
                to_uid="ku:python-basics",
                relationship_type=RelationshipName.REQUIRES_KNOWLEDGE
            )
        """
        try:
            rel_type = relationship_type.value
            query = f"""
            MATCH (a {{uid: $from_uid}})-[r:{rel_type}]->(b {{uid: $to_uid}})
            RETURN properties(r) as props
            """

            async with self.driver.session() as session:
                result = await session.run(query, {"from_uid": from_uid, "to_uid": to_uid})
                record = await result.single()

                if not record:
                    return Result.ok(None)

                # Cast to RelationshipMetadata for type safety
                # TypedDict is structural - Neo4j properties map naturally
                props: RelationshipMetadata = dict(record["props"])  # type: ignore[assignment]
                return Result.ok(props)

        except Exception as e:
            self.logger.error(f"Failed to get relationship metadata: {e}")
            return Result.fail(
                Errors.database(operation="get_relationship_metadata", message=str(e))
            )

    async def update_relationship_properties(
        self,
        from_uid: str,
        to_uid: str,
        relationship_type: RelationshipName,
        properties: dict[str, Any],
    ) -> Result[bool]:
        """
        Update specific properties on a relationship edge.

        Updates only the specified properties using SET +=, leaving others unchanged.
        More flexible than update_edge_metadata() which replaces all properties.

        Args:
            from_uid: Source entity UID
            to_uid: Target entity UID
            relationship_type: Neo4j relationship type
            properties: Dict of properties to update

        Returns:
            Result[bool] indicating success

        Example:
            # Update confidence and last_verified
            await backend.update_relationship_properties(
                from_uid="ku:python",
                to_uid="ku:advanced-python",
                relationship_type=RelationshipName.ENABLES_KNOWLEDGE,
                properties={"confidence": 0.95, "last_verified": datetime.now().isoformat()}
            )
        """
        try:
            if not properties:
                return Result.ok(True)  # Nothing to update

            rel_type = relationship_type.value
            query = f"""
            MATCH (a {{uid: $from_uid}})-[r:{rel_type}]->(b {{uid: $to_uid}})
            SET r += $properties
            RETURN r
            """

            async with self.driver.session() as session:
                result = await session.run(
                    query, {"from_uid": from_uid, "to_uid": to_uid, "properties": properties}
                )
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.not_found(
                            resource="Relationship",
                            identifier=f"{from_uid} --[{rel_type}]-> {to_uid}",
                        )
                    )

                self.logger.debug(
                    f"Updated {len(properties)} properties on {from_uid} --[{rel_type}]-> {to_uid}"
                )
                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to update relationship properties: {e}")
            return Result.fail(
                Errors.database(operation="update_relationship_properties", message=str(e))
            )

    async def get_relationships_batch(
        self, relationships: builtins.list[tuple[str, str, str]]
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Get metadata for multiple relationships in a single query.

        More efficient than N individual get_relationship_metadata() calls.
        Returns metadata in same order as input (empty dict if edge doesn't exist).

        Args:
            relationships: List of (from_uid, to_uid, rel_type) tuples

        Returns:
            Result[List[Dict]] with metadata for each relationship

        Example:
            relationships = [
                ("task:123", "ku:python", "APPLIES_KNOWLEDGE"),
                ("task:123", "ku:algorithms", "REQUIRES_KNOWLEDGE"),
            ]
            result = await backend.get_relationships_batch(relationships)
        """
        from core.infrastructure.batch import BatchOperationHelper

        try:
            if not relationships:
                return Result.ok([])

            # Use BatchOperationHelper for query generation
            query_result = BatchOperationHelper.build_relationship_properties_query(relationships)

            async with self.driver.session() as session:
                result = await session.run(query_result.query, query_result.params)
                records = [record async for record in result]

                # Convert to list of dicts (empty dict if None)
                metadata_list = [
                    dict(record["props"]) if record["props"] else {} for record in records
                ]

                self.logger.debug(
                    f"Fetched metadata for {len(metadata_list)} relationships ({len(relationships)} requested)"
                )
                return Result.ok(metadata_list)

        except Exception as e:
            self.logger.error(f"Failed to get relationships batch: {e}")
            return Result.fail(Errors.database(operation="get_relationships_batch", message=str(e)))

    async def count_relationships_batch(
        self, requests: builtins.list[tuple[str, str, str | None]]
    ) -> Result[dict[tuple[str, str, str], int]]:
        """
        Count multiple relationship patterns in a single query.

        More efficient than N individual count_related() calls.

        Args:
            requests: List of (uid, relationship_type, direction) tuples
                     direction: "outgoing", "incoming", or "both"

        Returns:
            Result[Dict] mapping (uid, rel_type, direction) -> count

        Example:
            requests = [
                ("task:123", "APPLIES_KNOWLEDGE", "outgoing"),
                ("task:456", "REQUIRES_KNOWLEDGE", "outgoing"),
            ]
            result = await backend.count_relationships_batch(requests)
        """
        from core.infrastructure.batch import BatchOperationHelper

        try:
            if not requests:
                return Result.ok({})

            counts: dict[tuple[str, str, str], int] = {}

            # Use BatchOperationHelper to generate optimized queries by direction
            query_results = BatchOperationHelper.build_multi_direction_count_queries(requests)

            async with self.driver.session() as session:
                # Execute each direction's query
                for direction, query_result in query_results.items():
                    result = await session.run(query_result.query, query_result.params)
                    async for record in result:
                        counts[(record["uid"], record["rel_type"], direction)] = record["count"]

                # Fill in zeros for requests that had no results
                for uid, rel_type, direction in requests:
                    key = (uid, rel_type, direction or "outgoing")
                    if key not in counts:
                        counts[key] = 0

                self.logger.debug(f"Batch counted {len(counts)} relationship patterns")
                return Result.ok(counts)

        except Exception as e:
            self.logger.error(f"Failed to count relationships batch: {e}")
            return Result.fail(
                Errors.database(operation="count_relationships_batch", message=str(e))
            )

    # ============================================================================
    # RICH EDGE PROPERTIES
    # ============================================================================
    # Added: October 6, 2025
    # See: /docs/migrations/GRAPH_NATIVE_MIGRATION_PLAN.md
    #
    # These methods provide typed access to rich edge metadata.

    async def get_edge_metadata(
        self, from_uid: str, to_uid: str, relationship_type: RelationshipName
    ) -> Result[EdgeMetadata | None]:
        """
        Get typed EdgeMetadata for a relationship.

        Returns EdgeMetadata with confidence, strength, semantic_distance,
        learning properties, temporal tracking, etc.

        Args:
            from_uid: Source entity UID,
            to_uid: Target entity UID,
            relationship_type: Neo4j relationship type

        Returns:
            Result[Optional[EdgeMetadata]] or None if relationship doesn't exist

        Example:
            result = await backend.get_edge_metadata(
                from_uid="ku:programming-101",
                to_uid="ku:python-basics",
                relationship_type=RelationshipName.REQUIRES_KNOWLEDGE
            )
            if result.is_ok and result.value:
                metadata = result.value
                print(f"Confidence: {metadata.confidence}")
                print(f"Strength: {metadata.strength}")
                print(f"Traversed {metadata.traversal_count} times")
        """
        from core.models.semantic import EdgeMetadata

        try:
            props_result = await self.get_relationship_metadata(from_uid, to_uid, relationship_type)

            if not props_result.is_ok:
                return Result.fail(props_result.expect_error())

            if props_result.value is None:
                return Result.ok(None)

            # Convert dict to EdgeMetadata
            metadata = EdgeMetadata.from_neo4j_properties(props_result.value)
            return Result.ok(metadata)

        except Exception as e:
            self.logger.error(f"Failed to get edge metadata: {e}")
            return Result.fail(Errors.database(operation="get_edge_metadata", message=str(e)))

    async def update_edge_metadata(
        self, from_uid: str, to_uid: str, relationship_type: str, edge_metadata: EdgeMetadata
    ) -> Result[bool]:
        """
        Update edge metadata properties.

        Replaces all edge properties with new EdgeMetadata.

        Args:
            from_uid: Source entity UID,
            to_uid: Target entity UID,
            relationship_type: Neo4j relationship type,
            edge_metadata: New metadata to set

        Returns:
            Result[bool] indicating success

        Example:
            # Increment traversal count
            metadata_result = await backend.get_edge_metadata(from_uid, to_uid, "PREREQUISITE")
            if metadata_result.is_ok and metadata_result.value:
                updated = metadata_result.value.increment_traversal()
                await backend.update_edge_metadata(from_uid, to_uid, "PREREQUISITE", updated)
        """

        try:
            query = f"""
            MATCH (a {{uid: $from_uid}})-[r:{relationship_type}]->(b {{uid: $to_uid}})
            SET r = $metadata
            RETURN r
            """

            metadata_props = edge_metadata.to_neo4j_properties()

            async with self.driver.session() as session:
                result = await session.run(
                    query, {"from_uid": from_uid, "to_uid": to_uid, "metadata": metadata_props}
                )
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.not_found(
                            f"Relationship not found: {from_uid} --[{relationship_type}]-> {to_uid}"
                        )
                    )

                self.logger.debug(f"Updated edge metadata for {from_uid} -> {to_uid}")
                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to update edge metadata: {e}")
            return Result.fail(Errors.database(operation="update_edge_metadata", message=str(e)))

    async def increment_traversal_count(
        self, from_uid: str, to_uid: str, relationship_type: str
    ) -> Result[bool]:
        """
        Increment traversal count for a relationship.

        Updates traversal_count and last_traversed timestamp.
        More efficient than fetching + updating full metadata.

        Args:
            from_uid: Source entity UID,
            to_uid: Target entity UID,
            relationship_type: Neo4j relationship type

        Returns:
            Result[bool] indicating success

        Example:
            # Track relationship usage
            await backend.increment_traversal_count(
                from_uid="ku:programming-101",
                to_uid="ku:python-basics",
                relationship_type="PREREQUISITE"
            )
        """
        try:
            query = f"""
            MATCH (a {{uid: $from_uid}})-[r:{relationship_type}]->(b {{uid: $to_uid}})
            SET r.traversal_count = coalesce(r.traversal_count, 0) + 1,
                r.last_traversed = datetime()
            RETURN r.traversal_count as count
            """

            async with self.driver.session() as session:
                result = await session.run(query, {"from_uid": from_uid, "to_uid": to_uid})
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.not_found(
                            f"Relationship not found: {from_uid} --[{relationship_type}]-> {to_uid}"
                        )
                    )

                new_count = record["count"]
                self.logger.debug(
                    f"Incremented traversal count to {new_count} for {from_uid} -> {to_uid}"
                )
                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to increment traversal count: {e}")
            return Result.fail(
                Errors.database(operation="increment_traversal_count", message=str(e))
            )

    # ============================================================================
    # GRAPH-NATIVE RELATIONSHIP API (October 26, 2025)
    # ============================================================================
    # Generic relationship methods for pure graph operations.
    # These eliminate the need for denormalized UID lists in domain models.

    def _extract_label_from_uid(self, uid: str) -> str | None:
        """
        Extract label from UID pattern (e.g., 'task:123' → 'Task').

        SKUEL uses consistent UID patterns: {domain}:{id}
        Fast pattern matching, no DB query needed.

        Args:
            uid: Entity UID (e.g., "task:123", "ku.python-basics")

        Returns:
            Label string if pattern matches, None otherwise (requires DB fallback)

        Examples:
            >>> backend._extract_label_from_uid("task:123")
            "Task"
            >>> backend._extract_label_from_uid("ku.python-basics")
            "Entity"
            >>> backend._extract_label_from_uid("unknown:xyz")
            None
        """
        # Common UID patterns in SKUEL
        patterns = {
            "task:": "Task",
            "event:": "Event",
            "habit:": "Habit",
            "goal:": "Goal",
            "principle:": "Principle",
            "choice:": "Choice",
            "ku.": "Entity",  # Knowledge uses dots
            "user.": "User",
            "expense:": "Expense",
        }

        for prefix, label in patterns.items():
            if uid.startswith(prefix):
                return label

        return None  # Fallback to DB query

    def _build_direction_pattern(
        self,
        relationship_type: str,
        direction: Direction,
        source_var: str = "n",
        target_var: str = "related",
        rel_var: str | None = None,
        target_label: str | None = None,
    ) -> Result[str]:
        """
        Build Cypher pattern for directional relationship traversal.

        Consolidates repeated pattern building across:
        - get_related_entities() (with target label)
        - get_related_uids() (with relationship variable)
        - count_related() (with relationship variable)

        Args:
            relationship_type: The relationship type (e.g., "PREREQUISITE", "OWNS")
            direction: Traversal direction ("outgoing", "incoming", or "both")
            source_var: Variable name for source node (default: "n")
            target_var: Variable name for target node (default: "related")
            rel_var: Optional relationship variable name (e.g., "r" for property access)
            target_label: Optional label constraint on target node

        Returns:
            Result[str] containing the Cypher pattern or validation error

        Examples:
            >>> backend._build_direction_pattern("OWNS", "outgoing")
            Result.ok("(n)-[:OWNS]->(related)")

            >>> backend._build_direction_pattern("PREREQUISITE", "incoming", rel_var="r")
            Result.ok("(n)<-[r:PREREQUISITE]-(related)")

            >>> backend._build_direction_pattern("OWNS", "outgoing", target_label="Task")
            Result.ok("(n)-[:OWNS]->(related:Task)")
        """
        # Build relationship part: [r:TYPE] or [:TYPE]
        rel_part = f"[{rel_var}:{relationship_type}]" if rel_var else f"[:{relationship_type}]"

        # Build target part: (related) or (related:Label)
        target_part = f"({target_var}:{target_label})" if target_label else f"({target_var})"

        # Build pattern based on direction
        match direction:
            case "outgoing":
                return Result.ok(f"({source_var})-{rel_part}->{target_part}")
            case "incoming":
                return Result.ok(f"({source_var})<-{rel_part}-{target_part}")
            case "both":
                return Result.ok(f"({source_var})-{rel_part}-{target_part}")
            case _:
                return Result.fail(
                    Errors.validation(
                        message=f"Invalid direction: {direction}. Valid options: outgoing, incoming, both",
                        field="direction",
                        value=direction,
                    )
                )

    async def _get_node_labels(
        self, from_uid: str, to_uid: str
    ) -> Result[tuple[builtins.list[str], builtins.list[str]]]:
        """
        Query database for node labels (single efficient query).

        Gets labels for both source and target nodes in ONE transaction.
        Used for validation when UID pattern matching fails.

        Args:
            from_uid: Source node UID
            to_uid: Target node UID

        Returns:
            Result containing tuple of (source_labels, target_labels)
            Returns error if either node doesn't exist

        Example:
            >>> result = await backend._get_node_labels("task:123", "ku.python")
            >>> source_labels, target_labels = result.value
            >>> print(source_labels) # ["Task"]
            >>> print(target_labels) # ["Entity", "Entity"]
        """
        try:
            query = """
            MATCH (a {uid: $from_uid})
            MATCH (b {uid: $to_uid})
            RETURN labels(a) as source_labels, labels(b) as target_labels
            """

            async with self.driver.session() as session:
                result = await session.run(query, {"from_uid": from_uid, "to_uid": to_uid})
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.not_found(
                            resource="Node",
                            identifier=f"{from_uid} or {to_uid}",
                        )
                    )

                source_labels = record.get("source_labels", [])
                target_labels = record.get("target_labels", [])

                return Result.ok((source_labels, target_labels))

        except Exception as e:
            self.logger.error(f"Failed to get node labels: {e}")
            return Result.fail(
                Errors.database(
                    operation="get_node_labels",
                    message=str(e),
                    details={"from_uid": from_uid, "to_uid": to_uid},
                )
            )

    async def create_relationship(
        self,
        from_uid: str,
        to_uid: str,
        relationship_type: str,
        properties: dict[str, Any] | None = None,
    ) -> Result[bool]:
        """
        Create or update a graph relationship between two entities.


        - Validates relationship type for source domain (hard failure)
        - Validates target node label matches registry spec (hard failure)
        - Uses UID parsing + DB fallback for label extraction
        - Ensures semantic correctness of graph relationships

        GRAPH-NATIVE: Creates pure Neo4j relationship edges, not node properties.
        This is the foundation for eliminating UID list fields from domain models.

        Uses MERGE to be idempotent - if relationship exists, updates properties.
        This prevents duplicate relationships and allows safe retry logic.

        Args:
            from_uid: Source entity UID (must exist in database)
            to_uid: Target entity UID (must exist in database)
            relationship_type: Neo4j relationship type (e.g., "APPLIES_KNOWLEDGE", "DEPENDS_ON")
                              MUST match RelationshipRegistry for source domain
            properties: Optional relationship properties (metadata). Common properties:
                       - confidence: float (0.0-1.0) - relationship confidence score
                       - strength: float - relationship strength
                       - created_at: datetime - when relationship was created
                       - Any domain-specific metadata

        Returns:
            Result[bool]: Success with True if created/updated
            Result[Error]: Validation failure or database error

        Validation Errors:
            - Invalid relationship type for source domain
            - Invalid target node label (doesn't match registry spec)
            - Source or target node doesn't exist

        Examples:
            ```python
            backend = UniversalNeo4jBackend[Task](driver, "Task", Task)

            # Valid relationship - passes validation
            result = await backend.create_relationship(
                from_uid="task:123",
                to_uid="ku.python-basics",
                relationship_type="APPLIES_KNOWLEDGE",
            )
            # ✅ Task -> Knowledge is valid per registry

            # Invalid relationship - fails validation
            result = await backend.create_relationship(
                from_uid="task:123",
                to_uid="habit:exercise",
                relationship_type="APPLIES_KNOWLEDGE",
            )
            # ❌ Error: APPLIES_KNOWLEDGE expects Knowledge target, not Habit
            ```

        Note:
            - Both entities must exist before creating relationship
            - MERGE makes this idempotent (safe to call multiple times)
            - RelationshipRegistry validation is AUTOMATIC (no manual checks needed)
            - For batch operations, use create_relationships_batch() for better performance
            - Relationship properties are optional but recommended for graph analytics

        See Also:
            - delete_relationship(): Remove relationships
            - has_relationship(): Check if relationship exists
            - get_relationship_metadata(): Retrieve relationship properties
            - RelationshipRegistry: Valid relationship types per domain
        """
        from core.models.relationship_registry import (
            get_relationship_metadata,
            get_valid_relationships,
            validate_relationship,
        )

        # ========================================================================
        # C: VALIDATION (Hard Failures)
        # ========================================================================

        # Step 1: Extract source label (fast UID parsing first)
        source_label = self._extract_label_from_uid(from_uid)

        # Step 2: Get node labels from database (needed for target validation)
        labels_result = await self._get_node_labels(from_uid, to_uid)
        if labels_result.is_error:
            return Result.fail(labels_result.expect_error())  # Nodes don't exist

        source_labels: builtins.list[str]
        target_labels: builtins.list[str]
        source_labels, target_labels = labels_result.value

        # Use DB label if UID parsing failed
        if not source_label and source_labels:
            source_label = source_labels[0]

        if not source_label:
            return Result.fail(
                Errors.validation(
                    message=f"Unable to determine source label for UID: {from_uid}",
                    field="from_uid",
                    value=from_uid,
                )
            )

        # Step 3: Validate relationship type for source domain
        if not validate_relationship(source_label, relationship_type):
            valid_rels = get_valid_relationships(source_label)
            from core.utils.result_simplified import ErrorCategory, ErrorContext, ErrorSeverity

            return Result.fail(
                ErrorContext(
                    category=ErrorCategory.VALIDATION,
                    code="VALIDATION_FIELD_RELATIONSHIP_TYPE",
                    message=(
                        f"Invalid relationship type '{relationship_type}' for {source_label}. "
                        f"Valid types: {list(valid_rels.keys())}"
                    ),
                    severity=ErrorSeverity.LOW,
                    details={
                        "field": "relationship_type",
                        "value": relationship_type,
                        "source_label": source_label,
                        "source_uid": from_uid,
                        "valid_relationship_types": list(valid_rels.keys()),
                    },
                    user_message=f"Invalid relationship type '{relationship_type}'",
                    source_location=ErrorContext.capture_current_location(),
                )
            )

        # Step 4: Validate target node label
        spec = get_relationship_metadata(source_label, relationship_type)
        if spec and spec.target_labels:
            primary_target_label = target_labels[0] if target_labels else "Unknown"

            # Check if any of the node's labels match the spec
            valid_target = any(label in spec.target_labels for label in target_labels)

            if not valid_target:
                from core.utils.result_simplified import ErrorCategory, ErrorContext, ErrorSeverity

                return Result.fail(
                    ErrorContext(
                        category=ErrorCategory.VALIDATION,
                        code="VALIDATION_FIELD_TARGET_LABEL",
                        message=(
                            f"Invalid target label for relationship: "
                            f"{source_label} --[{relationship_type}]-> {primary_target_label}. "
                            f"Expected target labels: {spec.target_labels}"
                        ),
                        severity=ErrorSeverity.LOW,
                        details={
                            "field": "target_label",
                            "value": primary_target_label,
                            "source_label": source_label,
                            "target_labels": target_labels,
                            "expected_target_labels": spec.target_labels,
                            "relationship_type": relationship_type,
                        },
                        user_message=f"Invalid target type for {relationship_type} relationship",
                        source_location=ErrorContext.capture_current_location(),
                    )
                )

        # Note: Property validation and cardinality constraints were removed in January 2026
        # during the RelationshipRegistry migration. The new registry focuses on
        # essential validation (relationship type + target labels). Add cardinality
        # constraints to UnifiedRelationshipDefinition if needed in the future.

        # ========================================================================
        # RELATIONSHIP CREATION (All Validation Passed)
        # ========================================================================

        try:
            props = properties or {}

            query = f"""
            MATCH (a {{uid: $from_uid}})
            MATCH (b {{uid: $to_uid}})
            MERGE (a)-[r:{relationship_type}]->(b)
            SET r += $properties
            RETURN r
            """

            async with self.driver.session() as session:
                result = await session.run(
                    query, {"from_uid": from_uid, "to_uid": to_uid, "properties": props}
                )
                await result.single()

            self.logger.debug(
                f"Created relationship: {from_uid} --[{relationship_type}]-> {to_uid}"
            )
            return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to create relationship: {e}")
            return Result.fail(
                Errors.database(
                    operation="create_relationship",
                    message=str(e),
                    details={
                        "from_uid": from_uid,
                        "to_uid": to_uid,
                        "relationship_type": relationship_type,
                    },
                )
            )

    async def delete_relationship(
        self, from_uid: str, to_uid: str, relationship_type: RelationshipName
    ) -> Result[bool]:
        """
        DETACH DELETE a graph relationship between two entities.

        Args:
            from_uid: Source entity UID
            to_uid: Target entity UID
            relationship_type: Neo4j relationship type

        Returns:
            Result[bool] indicating success (True even if relationship didn't exist)

        Example:
            await backend.delete_relationship(
                from_uid="task:123",
                to_uid="ku:python-basics",
                relationship_type=RelationshipName.APPLIES_KNOWLEDGE
            )
        """
        try:
            rel_type = relationship_type.value
            query = f"""
            MATCH (a {{uid: $from_uid}})-[r:{rel_type}]->(b {{uid: $to_uid}})
            DETACH DELETE r
            RETURN count(r) as deleted_count
            """

            async with self.driver.session() as session:
                result = await session.run(query, {"from_uid": from_uid, "to_uid": to_uid})
                record = await result.single()
                deleted_count = record["deleted_count"] if record else 0

            self.logger.debug(
                f"Deleted {deleted_count} relationship(s): {from_uid} --[{rel_type}]-> {to_uid}"
            )
            return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to delete relationship: {e}")
            return Result.fail(Errors.database(operation="delete_relationship", message=str(e)))

    async def delete_relationships_batch(
        self, relationships: builtins.list[tuple[str, str, str]]
    ) -> Result[int]:
        """
        Delete multiple relationships in a single transaction.

        Symmetric with create_relationships_batch() for efficient bulk deletion.
        Idempotent - no error if relationships don't exist.

        Args:
            relationships: List of (from_uid, to_uid, rel_type) tuples

        Returns:
            Result[int] with count of relationships deleted

        Example:
            relationships = [
                ("task:123", "ku:python", "APPLIES_KNOWLEDGE"),
                ("task:123", "ku:algorithms", "REQUIRES_KNOWLEDGE"),
            ]
            result = await backend.delete_relationships_batch(relationships)
            print(f"Deleted {result.value} relationships")
        """
        from core.infrastructure.batch import BatchOperationHelper

        try:
            if not relationships:
                return Result.ok(0)

            # Use BatchOperationHelper for query generation
            query_result = BatchOperationHelper.build_relationship_delete_query(relationships)

            async with self.driver.session() as session:
                result = await session.run(query_result.query, query_result.params)
                record = await result.single()
                deleted_count = record["deleted_count"] if record else 0

            self.logger.debug(
                f"Batch deleted {deleted_count} relationships ({len(relationships)} requested)"
            )
            return Result.ok(deleted_count)

        except Exception as e:
            self.logger.error(f"Failed to batch delete relationships: {e}")
            return Result.fail(
                Errors.database(operation="delete_relationships_batch", message=str(e))
            )

    async def has_relationship(
        self, from_uid: str, to_uid: str, relationship_type: RelationshipName
    ) -> Result[bool]:
        """
        Check if a graph relationship exists between two entities.

        Efficient existence check - returns True/False without loading properties or entities.
        Much faster than get_relationship_metadata() when you only need to check existence.

        Args:
            from_uid: Source entity UID (must exist)
            to_uid: Target entity UID (must exist)
            relationship_type: Neo4j relationship type (exact match, case-sensitive)

        Returns:
            Result[bool]: Success with True if relationship exists, False if not,
                         or Failure if database error

        Example:
            ```python
            backend = UniversalNeo4jBackend[Task](driver, "Task", Task)

            # Check before creating to avoid duplicates
            exists = await backend.has_relationship(
                from_uid="task:123",
                to_uid="ku:python-basics",
                relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
            )

            if not exists.value:
                await backend.create_relationship(
                    from_uid="task:123",
                    to_uid="ku:python-basics",
                    relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
                )
            ```

        Performance:
            - O(1) lookup using relationship index
            - No property loading (very fast)
            - Use for existence checks before mutations

        Note:
            - Checks exact relationship type (case-sensitive)
            - Direction matters: (from)-[:TYPE]->(to) is different from (to)-[:TYPE]->(from)
            - For bidirectional check, call twice with swapped UIDs
            - Returns False if either entity doesn't exist

        See Also:
            - create_relationship(): Create new relationships
            - get_relationship_metadata(): Get relationship properties
            - count_related(): Count all relationships of a type
        """
        try:
            rel_type = relationship_type.value
            query = f"""
            MATCH (a {{uid: $from_uid}})-[r:{rel_type}]->(b {{uid: $to_uid}})
            RETURN count(r) > 0 as exists
            """

            async with self.driver.session() as session:
                result = await session.run(query, {"from_uid": from_uid, "to_uid": to_uid})
                record = await result.single()
                exists = record["exists"] if record else False

            return Result.ok(exists)

        except Exception as e:
            self.logger.error(f"Failed to check relationship existence: {e}")
            return Result.fail(Errors.database(operation="has_relationship", message=str(e)))

    async def count_related(
        self,
        uid: str,
        relationship_type: RelationshipName,
        direction: Direction = "outgoing",
        properties: dict[str, Any] | None = None,
    ) -> Result[int]:
        """
        Count related entities without loading them.

        Efficient for checking relationship counts (e.g., "How many prerequisites?").
        Use this instead of `len(await get_related_uids())` for better performance.

        Args:
            uid: Entity UID
            relationship_type: Neo4j relationship type
            direction: "outgoing", "incoming", or "both"
            properties: Optional dict of relationship properties to filter by

        Returns:
            Result[int] with relationship count

        Examples:
            # Count how many knowledge units this task applies
            count_result = await backend.count_related(
                uid="task:123",
                relationship_type=RelationshipName.APPLIES_KNOWLEDGE,
                direction="outgoing"
            )
            print(f"Task applies {count_result.value} knowledge units")

            # Count prerequisites
            prereq_count = await backend.count_related(
                uid="ku:advanced-python",
                relationship_type=RelationshipName.REQUIRES_KNOWLEDGE,
                direction="outgoing"
            )

            # Count essential habits (with property filtering)
            essential_count = await backend.count_related(
                uid="goal:fitness",
                relationship_type=RelationshipName.REQUIRES_HABIT,
                direction="outgoing",
                properties={"essentiality": "essential"}
            )
            print(f"Goal has {essential_count.value} essential habits")
        """
        try:
            # Extract string value for Cypher query
            rel_type = relationship_type.value

            # Build Cypher pattern using helper (with named relationship variable for property access)
            pattern_result = self._build_direction_pattern(
                relationship_type=rel_type,
                direction=direction,
                rel_var="r",
            )
            if pattern_result.is_error:
                return Result.fail(pattern_result.expect_error())
            pattern = pattern_result.value

            # Build WHERE clause for property filtering
            where_clauses = []
            params = {"uid": uid}

            if properties:
                for key, value in properties.items():
                    param_name = f"prop_{key}"
                    where_clauses.append(f"r.{key} = ${param_name}")
                    params[param_name] = value

            where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

            query = f"""
            MATCH (n {{uid: $uid}})
            MATCH {pattern}
            {where_clause}
            RETURN count(related) as count
            """

            async with self.driver.session() as session:
                result = await session.run(query, params)
                record = await result.single()
                count = record["count"] if record else 0

            return Result.ok(count)

        except Exception as e:
            self.logger.error(f"Failed to count related entities: {e}")
            return Result.fail(Errors.database(operation="count_related", message=str(e)))

    async def create_relationships_batch(
        self, relationships: builtins.list[tuple[str, str, str, dict[str, Any] | None]]
    ) -> Result[int]:
        """
        Create multiple relationships in a single transaction.


        - Validates ALL relationships BEFORE creating ANY (transaction integrity)
        - Returns detailed errors for invalid relationships
        - Uses efficient batch validation with single DB query

        Efficient batch operation for creating many relationships at once.
        Uses UNWIND for optimal performance.

        Args:
            relationships: List of (from_uid, to_uid, rel_type, properties) tuples

        Returns:
            Result[int] with count of relationships created
            Result[Error] if ANY relationship fails validation (creates NONE)

        Validation:
            - All relationship types must be valid for their source domains
            - All target labels must match registry specs
            - Validates ALL before creating ANY (transaction integrity)

        Example:
            # Create multiple task -> knowledge relationships
            rels = [
                ("task:123", "ku.python-basics", "APPLIES_KNOWLEDGE", {"confidence": 0.9}),
                ("task:123", "ku.functions", "APPLIES_KNOWLEDGE", {"confidence": 0.8}),
                ("task:123", "ku.loops", "APPLIES_KNOWLEDGE", {"confidence": 0.7})
            ]
            result = await backend.create_relationships_batch(rels)
            print(f"Created {result.value} relationships") # All or nothing
        """
        from core.models.relationship_registry import (
            get_relationship_metadata,
            get_valid_relationships,
            validate_relationship,
        )

        if not relationships:
            return Result.ok(0)

        # ========================================================================
        # C: BATCH VALIDATION (Validate ALL before creating ANY)
        # ========================================================================

        validation_errors = []

        for idx, (from_uid, to_uid, rel_type, _props) in enumerate(relationships):
            # Step 1: Extract source label (fast UID parsing)
            # Note: _props intentionally unused - property validation not yet implemented
            source_label = self._extract_label_from_uid(from_uid)

            # Step 2: Get node labels from database
            labels_result = await self._get_node_labels(from_uid, to_uid)
            if labels_result.is_error:
                validation_errors.append(
                    {
                        "index": idx,
                        "from_uid": from_uid,
                        "to_uid": to_uid,
                        "relationship_type": rel_type,
                        "error": "Nodes not found",
                        "details": labels_result.expect_error().message,
                    }
                )
                continue

            source_labels: builtins.list[str]
            target_labels: builtins.list[str]
            source_labels, target_labels = labels_result.value

            # Use DB label if UID parsing failed
            if not source_label and source_labels:
                source_label = source_labels[0]

            if not source_label:
                validation_errors.append(
                    {
                        "index": idx,
                        "from_uid": from_uid,
                        "error": "Unable to determine source label",
                    }
                )
                continue

            # Step 3: Validate relationship type for source domain
            if not validate_relationship(source_label, rel_type):
                valid_rels = get_valid_relationships(source_label)
                validation_errors.append(
                    {
                        "index": idx,
                        "from_uid": from_uid,
                        "to_uid": to_uid,
                        "relationship_type": rel_type,
                        "error": f"Invalid relationship type '{rel_type}' for {source_label}",
                        "valid_types": list(valid_rels.keys()),
                    }
                )
                continue

            # Step 4: Validate target node label
            spec = get_relationship_metadata(source_label, rel_type)
            if spec and spec.target_labels:
                # Check if any of the node's labels match the spec
                valid_target = any(label in spec.target_labels for label in target_labels)

                if not valid_target:
                    primary_target_label = target_labels[0] if target_labels else "Unknown"
                    validation_errors.append(
                        {
                            "index": idx,
                            "from_uid": from_uid,
                            "to_uid": to_uid,
                            "relationship_type": rel_type,
                            "error": (
                                f"Invalid target: {source_label} --[{rel_type}]-> {primary_target_label}"
                            ),
                            "expected_targets": spec.target_labels,
                            "actual_target": primary_target_label,
                        }
                    )
                    continue

        # If ANY validation failed, return errors without creating relationships
        if validation_errors:
            from core.utils.result_simplified import ErrorCategory, ErrorContext, ErrorSeverity

            return Result.fail(
                ErrorContext(
                    category=ErrorCategory.VALIDATION,
                    code="VALIDATION_FIELD_RELATIONSHIPS",
                    message=f"Batch validation failed: {len(validation_errors)} invalid relationships",
                    severity=ErrorSeverity.LOW,
                    details={
                        "field": "relationships",
                        "total_relationships": len(relationships),
                        "validation_errors": validation_errors,
                        "error_count": len(validation_errors),
                    },
                    user_message="Invalid relationships in batch",
                    source_location=ErrorContext.capture_current_location(),
                )
            )

        # ========================================================================
        # BATCH CREATION (All validations passed)
        # ========================================================================
        # Uses BatchOperationHelper for pure Cypher query generation
        from core.infrastructure.batch import BatchOperationHelper

        try:
            # Generate queries grouped by relationship type
            queries = BatchOperationHelper.build_relationship_create_queries(relationships)

            total_created = 0
            async with self.driver.session() as session:
                for query, rels_data in queries:
                    result = await session.run(query, {"rels": rels_data})
                    record = await result.single()
                    total_created += record["created_count"] if record else 0

            self.logger.info(f"Created {total_created} relationships in batch")
            return Result.ok(total_created)

        except Exception as e:
            self.logger.error(f"Failed to create relationships batch: {e}")
            return Result.fail(
                Errors.database(operation="create_relationships_batch", message=str(e))
            )

    # ============================================================================
    # RELATIONSHIP-FIRST API - FLUENT INTERFACE
    # ============================================================================

    def relate(self) -> RelationshipBuilder:
        """
        Create a fluent relationship builder for creating Neo4j relationships.

        This is the relationship-first API - relationships are the primary interface.

        Example:
            await backend.relate() \\
                .from_node(task_uid) \\
                .via("APPLIES_KNOWLEDGE") \\
                .to_node(ku_uid) \\
                .with_metadata(ConfidenceLevel.GOOD, evidence="Applied in task") \\
                .create()

        Returns:
            RelationshipBuilder instance for method chaining
        """
        return RelationshipBuilder(self.driver)

    # Convenience methods for common relationship patterns

    async def get_prerequisites(self, uid: str) -> Result[builtins.list[T]]:
        """
        Get all prerequisites for an entity.

        Convenience method for get_related_entities(relationship_type="PREREQUISITE", direction="incoming")
        """
        return await self.get_related_entities(uid, "PREREQUISITE", direction="incoming")

    async def get_enables(self, uid: str) -> Result[builtins.list[T]]:
        """
        Get all entities this enables.

        Convenience method for get_related_entities(relationship_type="ENABLES", direction="outgoing")
        """
        return await self.get_related_entities(uid, "ENABLES", direction="outgoing")

    async def get_related(self, uid: str) -> Result[builtins.list[T]]:
        """
        Get all related entities (bidirectional).

        Convenience method for get_related_entities(relationship_type="RELATED_TO", direction="both")
        """
        return await self.get_related_entities(uid, "RELATED_TO", direction="both")

    async def get_children(self, uid: str) -> Result[builtins.list[T]]:
        """
        Get all child entities.

        Convenience method for get_related_entities(relationship_type="CHILD_OF", direction="incoming")
        """
        return await self.get_related_entities(uid, "CHILD_OF", direction="incoming")

    async def get_parent(self, uid: str) -> Result[T | None]:
        """
        Get parent entity.

        Convenience method for get_related_entities(relationship_type="CHILD_OF", direction="outgoing", limit=1)
        """
        result = await self.get_related_entities(uid, "CHILD_OF", direction="outgoing", limit=1)
        if result.is_error:
            return Result.fail(result.expect_error())

        entities = result.value
        return Result.ok(entities[0] if entities else None)

    async def get_depends_on(self, uid: str) -> Result[builtins.list[T]]:
        """
        Get all entities this depends on.

        Convenience method for tasks/events/habits.
        """
        return await self.get_related_entities(uid, "DEPENDS_ON", direction="outgoing")

    async def get_blocks(self, uid: str) -> Result[builtins.list[T]]:
        """
        Get all entities this blocks.

        Convenience method for tasks/events/habits.
        """
        return await self.get_related_entities(uid, "BLOCKS", direction="outgoing")

    # ============================================================================
    # USER-ENTITY RELATIONSHIP TRACKING (October 16, 2025)
    # ============================================================================
    # Complete User Tracking Across All Domains
    #
    # These methods enable tracking of user-entity relationships for ALL domains:
    # tasks, events, habits, goals, choices, principles, journals, finance, etc.
    #
    # Auto-creates (User)-[:HAS_X]->(Entity) when entities are created with user_uid.
    # Provides query methods for user-specific entity filtering and statistics.

    @safe_backend_operation("create_user_relationship")
    async def create_user_relationship(
        self,
        user_uid: str,
        entity_uid: str,
        relationship_type: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Result[bool]:
        """
        Create user-entity relationship.

        This method is called automatically when entities are created with user_uid.
        Can also be called manually to create additional relationship types.

        Args:
            user_uid: User UID,
            entity_uid: Entity UID,
            relationship_type: Neo4j relationship type. Defaults to "OWNS".
            metadata: Optional edge properties (created_at, last_accessed, priority, etc.)

        Returns:
            Result[bool] indicating success

        Example:
            # Automatically called by create() when entity has user_uid
            await backend.create_user_relationship(
                user_uid="user_123",
                entity_uid="task_456",
                relationship_type="OWNS",
                metadata={"priority": "high", "created_at": datetime.now().isoformat()}
            )
        """
        try:
            # Default relationship type: OWNS (domain-first architecture)
            if not relationship_type:
                relationship_type = "OWNS"

            # Default metadata
            default_metadata = {
                "created_at": datetime.now().isoformat(),
                "last_accessed": datetime.now().isoformat(),
                "access_count": 0,
                "is_active": True,
            }

            # Merge with provided metadata
            props = {**default_metadata, **(metadata or {})}

            query = f"""
            MATCH (u:User {{uid: $user_uid}})
            MATCH (e:{self.label} {{uid: $entity_uid}})
            MERGE (u)-[r:{relationship_type}]->(e)
            SET r = $props
            RETURN r
            """

            async with self.driver.session() as session:
                result = await session.run(
                    query, {"user_uid": user_uid, "entity_uid": entity_uid, "props": props}
                )
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.database(
                            "create_user_relationship",
                            f"Failed to create relationship: User {user_uid} or {self.label} {entity_uid} not found",
                        )
                    )

                self.logger.info(
                    f"Created user relationship: {user_uid} --[{relationship_type}]-> {entity_uid}"
                )
                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to create user relationship: {e}")
            return Result.fail(Errors.database("create_user_relationship", str(e)))

    @safe_backend_operation("get_user_entities")
    async def get_user_entities(
        self,
        user_uid: str,
        relationship_type: str | None = None,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
        offset: int = 0,
        sort_by: str | None = None,
        sort_order: str = "desc",
    ) -> Result[tuple[builtins.list[T], int]]:
        """
        Get all entities for a user via relationship traversal.

        This is the PRIMARY method for user-specific entity queries.
        Replaces property-based filtering with graph relationship traversal.

        Args:
            user_uid: User UID,
            relationship_type: Optional relationship type filter (e.g., "HAS_TASK")
                              If None, uses default "HAS_{LABEL}" pattern
            filters: Optional filters on entity properties (status, priority, etc.),
            limit: Max results,
            offset: Pagination offset,
            sort_by: Field to sort by (default: created_at),
            sort_order: "asc" or "desc" (default: desc)

        Returns:
            Result[tuple[list[T], int]]: Tuple of (entities, total_count) for pagination

        Example:
            # Get all user's tasks
            result = await tasks_backend.get_user_entities("user_123")

            # Get only active tasks, sorted by due date
            result = await tasks_backend.get_user_entities(
                "user_123",
                filters={"status": "active"},
                sort_by="due_date",
                sort_order="asc"
            )

            # Get user's high-priority goals
            result = await goals_backend.get_user_entities(
                "user_123",
                filters={"priority": "high"}, limit=QueryLimit.PREVIEW
            )
        """
        try:
            # Default relationship type: OWNS (domain-first architecture)
            if not relationship_type:
                relationship_type = "OWNS"

            # Build filter clause
            filter_clauses: builtins.list[str] = []
            params: dict[str, Any] = {"user_uid": user_uid, "limit": limit, "offset": offset}

            # Inject default_filters for Ku-type discrimination
            self._inject_default_filters(filter_clauses, params, node_var="e")

            if filters:
                for key, value in filters.items():
                    filter_clauses.append(f"e.{key} = ${key}")
                    params[key] = value

            where_clause = f"WHERE {' AND '.join(filter_clauses)}" if filter_clauses else ""

            # Default sort field
            if not sort_by:
                sort_by = "created_at"

            # Sort direction
            order_direction = "DESC" if sort_order.lower() == "desc" else "ASC"

            query = f"""
            MATCH (u:User {{uid: $user_uid}})-[:{relationship_type}]->(e:{self.label})
            {where_clause}
            RETURN e
            ORDER BY e.{sort_by} {order_direction}
            SKIP $offset
            LIMIT $limit
            """

            async with self.driver.session() as session:
                result = await session.run(query, params)
                records = [record async for record in result]

                entities = []
                for record in records:
                    entity = from_neo4j_node(record["e"], self.entity_class)
                    entities.append(entity)

                # Get total count for pagination
                count_result = await self.count_user_entities(user_uid, relationship_type, filters)
                if count_result.is_error:
                    return Result.fail(count_result.expect_error())

                total_count = count_result.value

                self.logger.debug(
                    f"Found {len(entities)} entities for user {user_uid} (total: {total_count})"
                )
                return Result.ok((entities, total_count))

        except Exception as e:
            self.logger.error(f"Failed to get user entities: {e}")
            return Result.fail(Errors.database("get_user_entities", str(e)))

    @safe_backend_operation("count_user_entities")
    async def count_user_entities(
        self,
        user_uid: str,
        relationship_type: str | None = None,
        filters: dict[str, Any] | None = None,
    ) -> Result[int]:
        """
        Count entities for a user.

        Args:
            user_uid: User UID,
            relationship_type: Optional relationship type filter,
            filters: Optional filters on entity properties

        Returns:
            Result[int] count of entities

        Example:
            # Count all user's tasks
            count_result = await tasks_backend.count_user_entities("user_123")

            # Count completed tasks
            count_result = await tasks_backend.count_user_entities(
                "user_123",
                filters={"status": "completed"}
            )
        """
        try:
            # Default relationship type: OWNS (domain-first architecture)
            if not relationship_type:
                relationship_type = "OWNS"

            # Build filter clause
            filter_clauses: builtins.list[str] = []
            params: dict[str, Any] = {"user_uid": user_uid}

            # Inject default_filters for Ku-type discrimination
            self._inject_default_filters(filter_clauses, params, node_var="e")

            if filters:
                for key, value in filters.items():
                    filter_clauses.append(f"e.{key} = ${key}")
                    params[key] = value

            where_clause = f"WHERE {' AND '.join(filter_clauses)}" if filter_clauses else ""

            query = f"""
            MATCH (u:User {{uid: $user_uid}})-[:{relationship_type}]->(e:{self.label})
            {where_clause}
            RETURN count(e) as count
            """

            async with self.driver.session() as session:
                result = await session.run(query, params)
                record = await result.single()

                count = record["count"] if record else 0
                return Result.ok(count)

        except Exception as e:
            self.logger.error(f"Failed to count user entities: {e}")
            return Result.fail(Errors.database("count_user_entities", str(e)))

    @safe_backend_operation("update_relationship_access")
    async def update_relationship_access(
        self, user_uid: str, entity_uid: str, relationship_type: str | None = None
    ) -> Result[bool]:
        """
        Update relationship metadata when user accesses an entity.

        Increments access_count and updates last_accessed timestamp.
        Use this to track user engagement with entities.

        Args:
            user_uid: User UID,
            entity_uid: Entity UID,
            relationship_type: Optional relationship type

        Returns:
            Result[bool] indicating success

        Example:
            # Track when user views a task
            await backend.update_relationship_access(
                user_uid="user_123",
                entity_uid="task_456"
            )
        """
        try:
            if not relationship_type:
                relationship_type = "OWNS"

            query = f"""
            MATCH (u:User {{uid: $user_uid}})-[r:{relationship_type}]->(e:{self.label} {{uid: $entity_uid}})
            SET r.access_count = coalesce(r.access_count, 0) + 1,
                r.last_accessed = $now
            RETURN r.access_count as count
            """

            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "user_uid": user_uid,
                        "entity_uid": entity_uid,
                        "now": datetime.now().isoformat(),
                    },
                )
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.not_found(
                            "relationship",
                            f"User {user_uid} --[{relationship_type}]-> {self.label} {entity_uid}",
                        )
                    )

                self.logger.debug(
                    f"Updated access for {user_uid} -> {entity_uid} (count: {record['count']})"
                )
                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to update relationship access: {e}")
            return Result.fail(Errors.database("update_relationship_access", str(e)))

    @safe_backend_operation("delete_user_relationship")
    async def delete_user_relationship(
        self, user_uid: str, entity_uid: str, relationship_type: str | None = None
    ) -> Result[bool]:
        """
        DETACH DELETE user-entity relationship.

        Use this when transferring entity ownership or removing user access.

        Args:
            user_uid: User UID,
            entity_uid: Entity UID,
            relationship_type: Optional relationship type

        Returns:
            Result[bool] indicating success

        Example:
            # Remove user's access to a shared goal
            await backend.delete_user_relationship(
                user_uid="user_123",
                entity_uid="goal_456"
            )
        """
        try:
            if not relationship_type:
                relationship_type = "OWNS"

            query = f"""
            MATCH (u:User {{uid: $user_uid}})-[r:{relationship_type}]->(e:{self.label} {{uid: $entity_uid}})
            DETACH DELETE r
            RETURN count(r) as deleted
            """

            async with self.driver.session() as session:
                result = await session.run(query, {"user_uid": user_uid, "entity_uid": entity_uid})
                record = await result.single()

                deleted = (record and record["deleted"] > 0) if record else False

                if deleted:
                    (
                        self.logger.info(
                            f"Deleted user relationship: {user_uid} --[{relationship_type}]-> {entity_uid}"
                        ),
                    )
                else:
                    self.logger.warning(
                        f"No relationship found to delete: {user_uid} -> {entity_uid}"
                    )

                return Result.ok(deleted)

        except Exception as e:
            self.logger.error(f"Failed to delete user relationship: {e}")
            return Result.fail(Errors.database("delete_user_relationship", str(e)))

    # ============================================================================
    # USER PROTOCOL COMPLIANCE
    # ============================================================================

    @safe_backend_operation("get_user_by_username")
    async def get_user_by_username(self, username: str) -> Result[T | None]:
        """Get user by username - required by UserOperations protocol."""
        query = f"""
        MATCH (n:{self.label} {{username: $username}})
        RETURN n
        """

        async with self.driver.session() as session:
            result = await session.run(query, {"username": username})
            record = await result.single()

            if not record:
                return Result.ok(None)

            entity = from_neo4j_node(dict(record["n"]), self.entity_class)
            return Result.ok(entity)

    async def create_user(self, user: T) -> Result[T]:
        """Create user - required by UserOperations protocol."""
        return await self.create(user)  # type: ignore[no-any-return]

    async def get_user_by_uid(self, user_uid: str) -> Result[T | None]:
        """Get user by UID - required by UserOperations protocol."""
        return await self.get(user_uid)  # type: ignore[no-any-return]

    async def update_user(self, user: T) -> Result[T]:
        """Update user - required by UserOperations protocol."""
        # Convert user to dict for updates
        user_dict = to_neo4j_node(user)
        # Extract UID for update
        uid = user_dict.get("uid")
        if not uid:
            return Result.fail(Errors.validation("User must have uid field", field="uid"))
        # Remove uid from updates (it's used as the match key)
        updates = {k: v for k, v in user_dict.items() if k != "uid"}
        return await self.update(uid, updates)  # type: ignore[no-any-return]

    async def delete_user(self, user_uid: str) -> Result[bool]:
        """Delete user - required by UserOperations protocol."""
        return await self.delete(user_uid, cascade=True)  # type: ignore[no-any-return]

    async def update_user_progress(
        self, user_uid: str, progress_updates: dict[str, Any]
    ) -> Result[bool]:
        """Update user's learning progress - required by UserOperations protocol."""
        # Update the user's progress fields
        update_result = await self.update(user_uid, progress_updates)
        if update_result.is_error:
            return Result.fail(update_result.error)
        return Result.ok(True)

    async def record_knowledge_mastery(
        self,
        user_uid: str,
        knowledge_uid: str,
        mastery_score: float,
        practice_count: int = 1,
        confidence_level: float = 0.8,
    ) -> Result[bool]:
        """Record user's mastery level for a knowledge unit - required by UserOperations protocol."""
        try:
            query = """
            MATCH (u:User {uid: $user_uid})
            MATCH (k:Entity {uid: $knowledge_uid})
            MERGE (u)-[r:MASTERED]->(k)
            SET r.mastery_score = $mastery_score,
                r.practice_count = $practice_count,
                r.confidence_level = $confidence_level,
                r.mastered_at = datetime(),
                r.last_practiced = datetime()
            RETURN r
            """

            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "user_uid": user_uid,
                        "knowledge_uid": knowledge_uid,
                        "mastery_score": mastery_score,
                        "practice_count": practice_count,
                        "confidence_level": confidence_level,
                    },
                )
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.database(
                            "record_knowledge_mastery",
                            f"Failed to record mastery: User {user_uid} or Knowledge {knowledge_uid} not found",
                        )
                    )

                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to record knowledge mastery: {e}")
            return Result.fail(Errors.database("record_knowledge_mastery", str(e)))

    async def record_knowledge_progress(
        self,
        user_uid: str,
        knowledge_uid: str,
        progress: float,
        time_invested_minutes: int = 0,
        difficulty_rating: float | None = None,
    ) -> Result[bool]:
        """Record user's progress on a knowledge unit - required by UserOperations protocol."""
        try:
            query = """
            MATCH (u:User {uid: $user_uid})
            MATCH (k:Entity {uid: $knowledge_uid})
            MERGE (u)-[r:IN_PROGRESS]->(k)
            SET r.progress = $progress,
                r.time_invested_minutes = coalesce(r.time_invested_minutes, 0) + $time_invested_minutes,
                r.difficulty_rating = $difficulty_rating,
                r.last_updated = datetime()
            RETURN r
            """

            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "user_uid": user_uid,
                        "knowledge_uid": knowledge_uid,
                        "progress": progress,
                        "time_invested_minutes": time_invested_minutes,
                        "difficulty_rating": difficulty_rating,
                    },
                )
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.database(
                            "record_knowledge_progress",
                            f"Failed to record progress: User {user_uid} or Knowledge {knowledge_uid} not found",
                        )
                    )

                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to record knowledge progress: {e}")
            return Result.fail(Errors.database("record_knowledge_progress", str(e)))

    async def enroll_in_learning_path(
        self,
        user_uid: str,
        learning_path_uid: str,
        target_completion: str | None = None,
        weekly_time_commitment: int = 300,
        motivation_note: str = "",
    ) -> Result[bool]:
        """Enroll user in a learning path - required by UserOperations protocol."""
        try:
            query = """
            MATCH (u:User {uid: $user_uid})
            MATCH (lp:Lp {uid: $learning_path_uid})
            MERGE (u)-[r:ENROLLED]->(lp)
            SET r.enrolled_at = datetime(),
                r.target_completion = $target_completion,
                r.weekly_time_commitment = $weekly_time_commitment,
                r.motivation_note = $motivation_note,
                r.progress = 0.0
            RETURN r
            """

            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "user_uid": user_uid,
                        "learning_path_uid": learning_path_uid,
                        "target_completion": target_completion,
                        "weekly_time_commitment": weekly_time_commitment,
                        "motivation_note": motivation_note,
                    },
                )
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.database(
                            "enroll_in_learning_path",
                            f"Failed to enroll: User {user_uid} or LearningPath {learning_path_uid} not found",
                        )
                    )

                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to enroll in learning path: {e}")
            return Result.fail(Errors.database("enroll_in_learning_path", str(e)))

    async def complete_learning_path_graph(
        self,
        user_uid: str,
        learning_path_uid: str,
        completion_score: float = 1.0,
        feedback_rating: int | None = None,
    ) -> Result[bool]:
        """Mark a learning path as completed in the graph - required by UserOperations protocol."""
        try:
            query = """
            MATCH (u:User {uid: $user_uid})-[e:ENROLLED]->(lp:Lp {uid: $learning_path_uid})
            DETACH DELETE e
            WITH u, lp
            CREATE (u)-[c:COMPLETED]->(lp)
            SET c.completed_at = datetime(),
                c.completion_score = $completion_score,
                c.feedback_rating = $feedback_rating
            RETURN c
            """

            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "user_uid": user_uid,
                        "learning_path_uid": learning_path_uid,
                        "completion_score": completion_score,
                        "feedback_rating": feedback_rating,
                    },
                )
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.database(
                            "complete_learning_path_graph",
                            f"Failed to complete: User {user_uid} or LearningPath {learning_path_uid} not found or not enrolled",
                        )
                    )

                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to complete learning path: {e}")
            return Result.fail(Errors.database("complete_learning_path_graph", str(e)))

    async def express_interest_in_knowledge(
        self,
        user_uid: str,
        knowledge_uid: str,
        interest_score: float = 0.8,
        interest_source: str = "discovery",
        priority: str = "medium",
        notes: str = "",
    ) -> Result[bool]:
        """Record user's interest in a knowledge unit - required by UserOperations protocol."""
        try:
            query = """
            MATCH (u:User {uid: $user_uid})
            MATCH (k:Entity {uid: $knowledge_uid})
            MERGE (u)-[r:INTERESTED_IN]->(k)
            SET r.interest_score = $interest_score,
                r.interest_source = $interest_source,
                r.priority = $priority,
                r.notes = $notes,
                r.created_at = datetime()
            RETURN r
            """

            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "user_uid": user_uid,
                        "knowledge_uid": knowledge_uid,
                        "interest_score": interest_score,
                        "interest_source": interest_source,
                        "priority": priority,
                        "notes": notes,
                    },
                )
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.database(
                            "express_interest_in_knowledge",
                            f"Failed to record interest: User {user_uid} or Knowledge {knowledge_uid} not found",
                        )
                    )

                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to express interest in knowledge: {e}")
            return Result.fail(Errors.database("express_interest_in_knowledge", str(e)))

    async def bookmark_knowledge(
        self,
        user_uid: str,
        knowledge_uid: str,
        bookmark_reason: str = "reference",
        tags: builtins.list | None = None,
        reminder_date: str | None = None,
    ) -> Result[bool]:
        """Bookmark a knowledge unit for later review - required by UserOperations protocol."""
        try:
            query = """
            MATCH (u:User {uid: $user_uid})
            MATCH (k:Entity {uid: $knowledge_uid})
            MERGE (u)-[r:BOOKMARKED]->(k)
            SET r.bookmark_reason = $bookmark_reason,
                r.tags = $tags,
                r.reminder_date = $reminder_date,
                r.created_at = datetime()
            RETURN r
            """

            async with self.driver.session() as session:
                result = await session.run(
                    query,
                    {
                        "user_uid": user_uid,
                        "knowledge_uid": knowledge_uid,
                        "bookmark_reason": bookmark_reason,
                        "tags": tags,
                        "reminder_date": reminder_date,
                    },
                )
                record = await result.single()

                if not record:
                    return Result.fail(
                        Errors.database(
                            "bookmark_knowledge",
                            f"Failed to bookmark: User {user_uid} or Knowledge {knowledge_uid} not found",
                        )
                    )

                return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to bookmark knowledge: {e}")
            return Result.fail(Errors.database("bookmark_knowledge", str(e)))

    async def update_user_activity(
        self, user_uid: str, activity_data: dict[str, Any]
    ) -> Result[bool]:
        """Update user's activity tracking data - required by UserOperations protocol."""
        # Update user node with activity data
        update_result = await self.update(user_uid, activity_data)
        if update_result.is_error:
            return Result.fail(update_result.error)
        return Result.ok(True)

    async def add_conversation_message(
        self, user_uid: str, role: str, _content: str, _metadata: dict[str, Any] | None = None
    ) -> Result[bool]:
        """Add a conversation message to user's history - required by UserOperations protocol."""
        # For now, this is a simplified implementation
        # In the future, this could create ConversationMessage nodes
        self.logger.info(f"Adding conversation message for user {user_uid} (role: {role})")
        return Result.ok(True)

    async def get_active_learners(
        self, since_hours: int = 24, limit: int = 100
    ) -> Result[builtins.list[T]]:
        """Get list of active learners - required by UserOperations protocol."""
        try:
            from datetime import datetime, timedelta

            cutoff_time = (datetime.now(UTC) - timedelta(hours=since_hours)).isoformat()

            query = f"""
            MATCH (n:{self.label})
            WHERE n.last_active >= $cutoff_time
            RETURN n
            ORDER BY n.last_active DESC
            LIMIT $limit
            """

            async with self.driver.session() as session:
                result = await session.run(query, {"cutoff_time": cutoff_time, "limit": limit})
                records = await result.data()

                entities = [from_neo4j_node(r["n"], self.entity_class) for r in records]
                return Result.ok(entities)

        except Exception as e:
            self.logger.error(f"Failed to get active learners: {e}")
            return Result.fail(Errors.database("get_active_learners", str(e)))

    # ============================================================================
    # PROTOCOL COMPLIANCE - AUTOMATIC VIA __GETATTR__
    # ============================================================================
    # Simple CRUD methods (create_task, get_task_by_uid, update_task, delete_task, list_tasks)
    # are now handled automatically by __getattr__ above.
    #
    # Only domain-specific methods remain below (link_X_to_Y, get_X_cross_domain_context, etc.)

    # ========================================================================
    # TASKS RELATIONSHIP METHODS
    # ========================================================================

    async def link_task_to_knowledge(
        self,
        task_uid: str,
        knowledge_uid: str,
        knowledge_score_required: float = 0.8,
        is_learning_opportunity: bool = False,
    ) -> Result[bool]:
        """
        Link task to required knowledge unit.
        Creates: (Task)-[:REQUIRES_KNOWLEDGE]->(Knowledge)
        """
        try:
            query = """
            MATCH (t:Task {uid: $task_uid})
            MATCH (k:Entity {uid: $knowledge_uid})
            MERGE (t)-[r:REQUIRES_KNOWLEDGE]->(k)
            SET r.knowledge_score_required = $knowledge_score_required,
                r.is_learning_opportunity = $is_learning_opportunity
            RETURN r
            """
            params = {
                "task_uid": task_uid,
                "knowledge_uid": knowledge_uid,
                "knowledge_score_required": knowledge_score_required,
                "is_learning_opportunity": is_learning_opportunity,
            }

            async with self.driver.session() as session:
                result = await session.run(query, params)
                await result.single()

            self.logger.info(f"Linked Task:{task_uid} to Knowledge:{knowledge_uid}")
            return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to link task to knowledge: {e}")
            return Result.fail(Errors.database(operation="link_task_to_knowledge", message=str(e)))

    async def link_task_to_goal(
        self,
        task_uid: str,
        goal_uid: str,
        contribution_percentage: float = 0.1,
        milestone_uid: str | None = None,
    ) -> Result[bool]:
        """
        Link task to goal it contributes to.
        Creates: (Task)-[:CONTRIBUTES_TO_GOAL]->(Goal)
        """
        try:
            query = """
            MATCH (t:Task {uid: $task_uid})
            MATCH (g:Goal {uid: $goal_uid})
            MERGE (t)-[r:CONTRIBUTES_TO_GOAL]->(g)
            SET r.contribution_percentage = $contribution_percentage,
                r.milestone_uid = $milestone_uid
            RETURN r
            """
            params = {
                "task_uid": task_uid,
                "goal_uid": goal_uid,
                "contribution_percentage": contribution_percentage,
                "milestone_uid": milestone_uid,
            }

            async with self.driver.session() as session:
                result = await session.run(query, params)
                await result.single()

            self.logger.info(f"Linked Task:{task_uid} to Goal:{goal_uid}")
            return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to link task to goal: {e}")
            return Result.fail(Errors.database(operation="link_task_to_goal", message=str(e)))

    # Events Protocol compliance
    async def link_event_to_goal(
        self, event_uid: str, goal_uid: str, contribution_weight: float = 1.0
    ) -> Result[bool]:
        """
        Link event to goal it supports.
        Creates: (Event)-[:SUPPORTS_GOAL {contribution_weight}]->(Goal)
        """
        try:
            query = """
            MATCH (e:Event {uid: $event_uid})
            MATCH (g:Goal {uid: $goal_uid})
            MERGE (e)-[r:SUPPORTS_GOAL]->(g)
            SET r.contribution_weight = $contribution_weight
            RETURN r
            """
            params = {
                "event_uid": event_uid,
                "goal_uid": goal_uid,
                "contribution_weight": contribution_weight,
            }

            async with self.driver.session() as session:
                result = await session.run(query, params)
                await result.single()

            self.logger.info(f"Linked Event:{event_uid} to Goal:{goal_uid}")
            return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to link event to goal: {e}")
            return Result.fail(Errors.database(operation="link_event_to_goal", message=str(e)))

    async def link_event_to_habit(self, event_uid: str, habit_uid: str) -> Result[bool]:
        """
        Link event to habit it reinforces.
        Creates: (Event)-[:REINFORCES_HABIT]->(Habit)
        """
        try:
            query = """
            MATCH (e:Event {uid: $event_uid})
            MATCH (h:Habit {uid: $habit_uid})
            MERGE (e)-[r:REINFORCES_HABIT]->(h)
            RETURN r
            """
            params = {"event_uid": event_uid, "habit_uid": habit_uid}

            async with self.driver.session() as session:
                result = await session.run(query, params)
                await result.single()

            self.logger.info(f"Linked Event:{event_uid} to Habit:{habit_uid}")
            return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to link event to habit: {e}")
            return Result.fail(Errors.database(operation="link_event_to_habit", message=str(e)))

    async def link_event_to_knowledge(
        self, event_uid: str, knowledge_uids: builtins.list[str]
    ) -> Result[bool]:
        """
        Link event to knowledge units it reinforces.
        Creates: (Event)-[:REINFORCES_KNOWLEDGE]->(Knowledge) for each UID
        """
        try:
            query = """
            MATCH (e:Event {uid: $event_uid})
            UNWIND $knowledge_uids AS ku_uid
            MATCH (k:Entity {uid: ku_uid})
            MERGE (e)-[r:REINFORCES_KNOWLEDGE]->(k)
            RETURN count(r) as relationship_count
            """
            params = {"event_uid": event_uid, "knowledge_uids": knowledge_uids}

            async with self.driver.session() as session:
                result = await session.run(query, params)
                await result.single()

            self.logger.info(f"Linked Event:{event_uid} to {len(knowledge_uids)} knowledge units")
            return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to link event to knowledge: {e}")
            return Result.fail(Errors.database(operation="link_event_to_knowledge", message=str(e)))

    # REMOVED: get_event_cross_domain_context()
    # Use EventsRelationshipService.get_event_cross_domain_context() instead.
    # Backend now provides get_domain_context_raw() primitive, services handle categorization.

    # Finance Protocol compliance - Relationship methods
    async def link_expense_to_goal(
        self, expense_uid: str, goal_uid: str, contribution_type: str = "investment"
    ) -> Result[bool]:
        """
        Link expense to goal it supports.
        Creates: (Expense)-[:SUPPORTS_GOAL {contribution_type}]->(Goal)
        """
        try:
            query = """
            MATCH (e:Expense {uid: $expense_uid})
            MATCH (g:Goal {uid: $goal_uid})
            MERGE (e)-[r:SUPPORTS_GOAL]->(g)
            SET r.contribution_type = $contribution_type
            RETURN r
            """
            params = {
                "expense_uid": expense_uid,
                "goal_uid": goal_uid,
                "contribution_type": contribution_type,
            }

            async with self.driver.session() as session:
                result = await session.run(query, params)
                await result.single()

            self.logger.info(f"Linked Expense:{expense_uid} to Goal:{goal_uid}")
            return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to link expense to goal: {e}")
            return Result.fail(Errors.database(operation="link_expense_to_goal", message=str(e)))

    async def link_expense_to_knowledge(
        self, expense_uid: str, knowledge_uid: str, learning_investment: bool = True
    ) -> Result[bool]:
        """
        Link expense to knowledge unit it invests in.
        Creates: (Expense)-[:INVESTS_IN_KNOWLEDGE {learning_investment}]->(Knowledge)
        """
        try:
            query = """
            MATCH (e:Expense {uid: $expense_uid})
            MATCH (k:Entity {uid: $knowledge_uid})
            MERGE (e)-[r:INVESTS_IN_KNOWLEDGE]->(k)
            SET r.learning_investment = $learning_investment
            RETURN r
            """
            params = {
                "expense_uid": expense_uid,
                "knowledge_uid": knowledge_uid,
                "learning_investment": learning_investment,
            }

            async with self.driver.session() as session:
                result = await session.run(query, params)
                await result.single()

            self.logger.info(f"Linked Expense:{expense_uid} to Knowledge:{knowledge_uid}")
            return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to link expense to knowledge: {e}")
            return Result.fail(
                Errors.database(operation="link_expense_to_knowledge", message=str(e))
            )

    async def link_expense_to_project(
        self, expense_uid: str, project_uid: str, allocation_percentage: float = 100.0
    ) -> Result[bool]:
        """
        Link expense to project/task it funds.
        Creates: (Expense)-[:FUNDS_PROJECT {allocation_percentage}]->(Task)
        """
        try:
            query = """
            MATCH (e:Expense {uid: $expense_uid})
            MATCH (t:Task {uid: $project_uid})
            MERGE (e)-[r:FUNDS_PROJECT]->(t)
            SET r.allocation_percentage = $allocation_percentage
            RETURN r
            """
            params = {
                "expense_uid": expense_uid,
                "project_uid": project_uid,
                "allocation_percentage": allocation_percentage,
            }

            async with self.driver.session() as session:
                result = await session.run(query, params)
                await result.single()

            self.logger.info(f"Linked Expense:{expense_uid} to Project:{project_uid}")
            return Result.ok(True)

        except Exception as e:
            self.logger.error(f"Failed to link expense to project: {e}")
            return Result.fail(Errors.database(operation="link_expense_to_project", message=str(e)))

    async def get_expense_cross_domain_context(
        self, expense_uid: str, depth: int = 2
    ) -> Result[dict[str, Any]]:
        """
        Get complete cross-domain context for an expense.

        Args:
            expense_uid: Expense UID
            depth: Graph traversal depth (1=direct relationships, 2+=multi-hop)

        Returns relationships to:
        - Goals (SUPPORTS_GOAL)
        - Knowledge units (INVESTS_IN_KNOWLEDGE)
        - Projects/Tasks (FUNDS_PROJECT)
        """
        try:
            # Use variable-length patterns to support depth parameter
            max_depth = max(1, depth)  # Ensure at least 1-hop
            query = f"""
            MATCH (e:Expense {{uid: $expense_uid}})
            OPTIONAL MATCH (e)-[sg:SUPPORTS_GOAL*1..{max_depth}]->(g:Goal)
            OPTIONAL MATCH (e)-[ik:INVESTS_IN_KNOWLEDGE*1..{max_depth}]->(k:Entity)
            OPTIONAL MATCH (e)-[fp:FUNDS_PROJECT*1..{max_depth}]->(t:Task)
            RETURN
                e,
                collect(DISTINCT {{goal: g, contribution_type: COALESCE(sg[0].contribution_type, 'general')}}) as goals,
                collect(DISTINCT {{knowledge: k, learning_investment: COALESCE(ik[0].learning_investment, true)}}) as knowledge,
                collect(DISTINCT {{project: t, allocation_percentage: COALESCE(fp[0].allocation_percentage, 100.0)}}) as projects
            """
            params = {"expense_uid": expense_uid}

            async with self.driver.session() as session:
                result = await session.run(query, params)
                record = await result.single()

                if not record:
                    return Result.fail(Errors.not_found(resource="Expense", identifier=expense_uid))

                context = {
                    "expense_uid": expense_uid,
                    "goals": [
                        {
                            "uid": g["goal"]["uid"],
                            "title": g["goal"].get("title"),
                            "contribution_type": g.get("contribution_type", "investment"),
                        }
                        for g in record["goals"]
                        if g["goal"] is not None
                    ],
                    "knowledge": [
                        {
                            "uid": k["knowledge"]["uid"],
                            "title": k["knowledge"].get("title"),
                            "learning_investment": k.get("learning_investment", True),
                        }
                        for k in record["knowledge"]
                        if k["knowledge"] is not None
                    ],
                    "projects": [
                        {
                            "uid": p["project"]["uid"],
                            "title": p["project"].get("title"),
                            "allocation_percentage": p.get("allocation_percentage", 100.0),
                        }
                        for p in record["projects"]
                        if p["project"] is not None
                    ],
                }

            return Result.ok(context)

        except Exception as e:
            self.logger.error(f"Failed to get expense cross-domain context: {e}")
            return Result.fail(
                Errors.database(operation="get_expense_cross_domain_context", message=str(e))
            )

    # REMOVED: get_habit_cross_domain_context()
    # Use HabitsRelationshipService.get_habit_cross_domain_context() instead.
    # Backend now provides get_domain_context_raw() primitive, services handle categorization.

    # REMOVED: get_goal_cross_domain_context()
    # Use GoalsRelationshipService.get_goal_cross_domain_context() instead.
    # Backend now provides get_domain_context_raw() primitive, services handle categorization.

    # REMOVED: get_principle_cross_domain_context()
    # Use PrinciplesRelationshipService.get_principle_cross_domain_context() instead.
    # Backend now provides get_domain_context_raw() primitive, services handle categorization.

    # REMOVED: get_choice_cross_domain_context()
    # Use ChoicesRelationshipService.get_choice_cross_domain_context() instead.
    # Backend now provides get_domain_context_raw() primitive, services handle categorization.

    # ============================================================================
    # PROTOCOL COMPLIANCE METHODS (November 28, 2025)
    # ============================================================================
    # These methods implement the Supports* protocols required by BaseService.
    # They provide protocol-compliant signatures that delegate to existing methods.

    async def add_relationship(
        self,
        from_uid: str,
        to_uid: str,
        relationship_type: RelationshipName,
        properties: dict[str, Any] | None = None,
    ) -> Result[bool]:
        """
        Add a relationship between entities.

        Protocol: RelationshipCrudOperations, SupportsRelationships

        Delegates to create_relationship() with protocol-compliant signature.

        Args:
            from_uid: Source entity UID
            to_uid: Target entity UID
            relationship_type: Relationship type (e.g., RelationshipName.APPLIES_KNOWLEDGE)
            properties: Optional relationship properties

        Returns:
            Result[bool]: True if relationship created/updated
        """
        return await self.create_relationship(
            from_uid=from_uid,
            to_uid=to_uid,
            relationship_type=relationship_type.value,
            properties=properties,
        )

    async def get_relationships(
        self, uid: str, direction: Direction = "both"
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Get relationships for an entity.

        Protocol: SupportsRelationships

        Args:
            uid: Entity UID to get relationships for
            direction: "outgoing", "incoming", or "both" (default)

        Returns:
            Result[list[dict]]: List of relationship data with:
                - type: Relationship type
                - target_uid: Connected entity UID
                - direction: "outgoing" or "incoming"
                - properties: Relationship properties
        """
        try:
            # Build direction-specific query
            if direction == "outgoing":
                cypher = """
                MATCH (n {uid: $uid})-[r]->(target)
                RETURN type(r) as type, target.uid as target_uid,
                       'outgoing' as direction, properties(r) as properties
                """
            elif direction == "incoming":
                cypher = """
                MATCH (n {uid: $uid})<-[r]-(source)
                RETURN type(r) as type, source.uid as target_uid,
                       'incoming' as direction, properties(r) as properties
                """
            else:  # both
                cypher = """
                MATCH (n {uid: $uid})-[r]-(other)
                WITH r, other,
                     CASE WHEN startNode(r).uid = $uid THEN 'outgoing' ELSE 'incoming' END as dir
                RETURN type(r) as type, other.uid as target_uid,
                       dir as direction, properties(r) as properties
                """

            async with self.driver.session() as session:
                result = await session.run(cypher, {"uid": uid})
                records = await result.data()

            return Result.ok(records)

        except Exception as e:
            self.logger.error(f"Failed to get relationships for {uid}: {e}")
            return Result.fail(Errors.database(operation="get_relationships", message=str(e)))

    async def traverse(
        self,
        start_uid: str,
        rel_pattern: str,
        max_depth: int = 3,
        include_properties: bool = False,
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Traverse the graph from a starting point.

        Protocol: SupportsTraversal

        Args:
            start_uid: Starting entity UID
            rel_pattern: Relationship pattern (e.g., "REQUIRES", "REQUIRES|ENABLES")
            max_depth: Maximum traversal depth (default: 3)
            include_properties: Whether to include node properties in results

        Returns:
            Result[list[dict]]: List of traversed nodes with:
                - uid: Node UID
                - labels: Node labels
                - depth: Distance from start node
                - properties: Node properties (if include_properties=True)
        """
        try:
            # Build relationship filter
            rel_filter = f":{rel_pattern}" if rel_pattern else ""

            if include_properties:
                cypher = f"""
                MATCH path = (start {{uid: $start_uid}})-[{rel_filter}*1..{max_depth}]-(node)
                UNWIND range(1, length(path)) as depth
                WITH node, depth, labels(node) as node_labels, properties(node) as props
                RETURN DISTINCT node.uid as uid, node_labels as labels,
                       min(depth) as depth, props as properties
                ORDER BY depth
                """
            else:
                cypher = f"""
                MATCH path = (start {{uid: $start_uid}})-[{rel_filter}*1..{max_depth}]-(node)
                UNWIND range(1, length(path)) as depth
                WITH node, depth, labels(node) as node_labels
                RETURN DISTINCT node.uid as uid, node_labels as labels, min(depth) as depth
                ORDER BY depth
                """

            async with self.driver.session() as session:
                result = await session.run(cypher, {"start_uid": start_uid})
                records = await result.data()

            return Result.ok(records)

        except Exception as e:
            self.logger.error(f"Failed to traverse from {start_uid}: {e}")
            return Result.fail(Errors.database(operation="traverse", message=str(e)))

    async def find_path(
        self,
        from_uid: str,
        to_uid: str,
        rel_types: builtins.list[str],
        max_depth: int = 5,
    ) -> Result[builtins.list[dict[str, Any]] | None]:
        """
        Find a path between two entities.

        Protocol: SupportsPathfinding

        Args:
            from_uid: Source entity UID
            to_uid: Target entity UID
            rel_types: Allowed relationship types for path
            max_depth: Maximum path length (default: 5)

        Returns:
            Result[list[dict] | None]: Path as list of nodes, or None if no path exists.
                Each node dict contains:
                - uid: Node UID
                - labels: Node labels
        """
        try:
            # Build relationship filter
            rel_filter = "|".join(rel_types) if rel_types else ""
            rel_clause = f":{rel_filter}" if rel_filter else ""

            cypher = f"""
            MATCH path = shortestPath(
                (start {{uid: $from_uid}})-[{rel_clause}*..{max_depth}]-(end {{uid: $to_uid}})
            )
            UNWIND nodes(path) as node
            RETURN node.uid as uid, labels(node) as labels
            """

            async with self.driver.session() as session:
                result = await session.run(cypher, {"from_uid": from_uid, "to_uid": to_uid})
                records = await result.data()

            if not records:
                return Result.ok(None)

            return Result.ok(records)

        except Exception as e:
            # Neo4j returns error if no path exists in some versions
            if "no path" in str(e).lower():
                return Result.ok(None)

            self.logger.error(f"Failed to find path from {from_uid} to {to_uid}: {e}")
            return Result.fail(Errors.database(operation="find_path", message=str(e)))


# ============================================================================
# CONVENIENCE FACTORY FUNCTIONS
# ============================================================================


def create_tasks_backend(driver: AsyncDriver) -> UniversalNeo4jBackend:
    """Create universal backend for tasks."""
    from core.models.task.task import Task as TaskPure

    return UniversalNeo4jBackend[TaskPure](driver, "Task", TaskPure)


def create_events_backend(driver: AsyncDriver) -> UniversalNeo4jBackend:
    """Create universal backend for events."""
    from core.models.event.event import Event as EventPure

    return UniversalNeo4jBackend[EventPure](driver, "Event", EventPure)


def create_finance_backend(driver: AsyncDriver) -> UniversalNeo4jBackend:
    """Create universal backend for finance."""
    from core.models.finance.finance_pure import ExpensePure

    return UniversalNeo4jBackend[ExpensePure](driver, "Expense", ExpensePure)


def create_habits_backend(driver: AsyncDriver) -> UniversalNeo4jBackend:
    """Create universal backend for habits."""
    from core.models.habit.habit import Habit as HabitPure

    return UniversalNeo4jBackend[HabitPure](driver, "Habit", HabitPure)


# Pattern continues for all domains...
# 12+ domain-specific files replaced by 12 simple factory functions
