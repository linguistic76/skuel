"""
Universal Neo4j Backend
=======================

SKUEL's 14-Domain Persistence Layer
------------------------------------

This module provides the universal backend for the 14 domains in SKUEL.
A single generic implementation replaces what would otherwise be 14+
separate domain-specific backend classes.

BACKENDS IN USE (services_bootstrap.py)
----------------------------------------

**Activity Domains (6):**
    HabitsBackend[Habit] - habits_backend
    GoalsBackend[Goal] - goals_backend
    TasksBackend[Task] - tasks_backend
    EventsBackend[Event] - events_backend
    ChoicesBackend[Choice] - choices_backend
    PrinciplesBackend[Principle] - principles_backend

**Curriculum Domains (4):**
    ArticleBackend[Article] - knowledge_backend (article:)
    UniversalNeo4jBackend[LearningStep] - ls_backend (ls:)
    LpBackend[LearningPath] - lp_backend (lp:)
    ExerciseBackend[Exercise] - exercise_backend

**Finance Domains (2):**
    UniversalNeo4jBackend[ExpensePure] - finance_backend
    UniversalNeo4jBackend[InvoicePure] - invoice_backend

**Content/Submissions (2):**
    SubmissionsBackend[Submission] - submissions_backend
    UniversalNeo4jBackend[ActivityReport] - ai_feedback_backend

**Supporting (5):**
    UniversalNeo4jBackend[HabitCompletion] - habit_completions_backend
    UniversalNeo4jBackend[Transcription] - transcription_backend
    UniversalNeo4jBackend[PrincipleReflection] - reflection_backend
    UniversalNeo4jBackend[UserProgress] - progress_backend
    UniversalNeo4jBackend[Askesis] - askesis_backend

NOT USING THIS BACKEND
----------------------

    UserContext - UserBackend (dedicated, with graph traversal extensions)
    LifePath - Cross-domain queries (AnalyticsLifePathService)
    Analytics - Read-only aggregation (no entity storage)

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

ARCHITECTURAL BOUNDARY
----------------------

This class is SKUEL's hexagonal boundary for Neo4j.

Everything above this boundary (service mixins, domain services, routes)
is written in domain concepts. Everything below it (Cypher strings, the
AsyncDriver, label conventions, relationship syntax) is Neo4j-specific.

Service mixins (ContextOperationsMixin, RelationshipOperationsMixin) use
graph vocabulary — depth, traverse, graph_enrichment_patterns — because
SKUEL's domain model is inherently a graph. This is intentional coupling,
not an incomplete refactor. The relationships between entities are domain
primitives, not storage implementation details.

Neo4j is a committed architectural choice, not a swappable adapter.
Replacing it would require rewriting this module and reconsidering the
graph-aware service mixins. The domain models and protocols above this
boundary would survive intact.

See: /docs/decisions/ADR-044-neo4j-committed-architectural-choice.md

See Also:
    /core/models/enums/entity_enums.py - EntityType, EntityStatus
    /core/ports/domain_protocols.py - Service interfaces
    /services_bootstrap.py - Service composition
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.enums.neo_labels import NeoLabel
from core.models.protocols import DomainModelProtocol
from core.models.query import QueryIntent, UnifiedQueryBuilder
from core.utils.error_boundary import safe_backend_operation
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    import builtins
    from collections.abc import Callable

    from neo4j import AsyncDriver

    from core.models.graph_context import GraphContext

from adapters.persistence.neo4j._crud_mixin import _CrudMixin
from adapters.persistence.neo4j._relationship_crud_mixin import _RelationshipCrudMixin
from adapters.persistence.neo4j._relationship_query_mixin import _RelationshipQueryMixin
from adapters.persistence.neo4j._search_mixin import _SearchMixin
from adapters.persistence.neo4j._traversal_mixin import _TraversalMixin
from adapters.persistence.neo4j._user_entity_mixin import _UserEntityMixin

logger = get_logger(__name__)


class UniversalNeo4jBackend[T: DomainModelProtocol](
    _CrudMixin[T],
    _SearchMixin[T],
    _RelationshipQueryMixin[T],
    _RelationshipCrudMixin[T],
    _UserEntityMixin[T],
    _TraversalMixin,
):
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
        from core.models.entity import Entity
        from core.models.enums import NeoLabel

        # All domain entities use NeoLabel.ENTITY (universal label)
        tasks_backend = UniversalNeo4jBackend[Entity](
            driver=neo4j_driver, label=NeoLabel.ENTITY, entity_class=Entity,
            default_filters={"entity_type": "task"},
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
    # DEFAULT FILTER HELPERS
    # ============================================================================

    def _default_filter_clause(self, node_var: str = "n") -> str:
        """Generate AND-joined conditions from default_filters.

        Returns empty string if no default_filters. Uses ``_df_`` prefixed
        parameter names to avoid collisions with caller parameters.

        Args:
            node_var: Cypher variable name for the node (default "n").

        Returns:
            Condition string like ``n.entity_type = $_df_entity_type`` or empty string.
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
    # DYNAMIC PROTOCOL COMPLIANCE - A
    # ============================================================================

    def __getattr__(self, name: str) -> Any:
        """
        Dynamic protocol compliance for simple CRUD method name aliases.

        Delegates domain-named methods to their universal equivalents:
            - create_{domain}(entity)       → create(entity)
            - get_{domain}_by_uid(uid)      → get(uid)
            - update_{domain}(uid, updates) → update(uid, updates)
            - delete_{domain}(uid)          → delete(uid)

        Domain-specific methods (link_X_to_Y, get_user_X, archive_X, etc.)
        have explicit implementations on domain backend subclasses.
        """
        if name.startswith("create_") and not name.endswith("_relationship"):
            return self.create

        if name.startswith("get_") and name.endswith("_by_uid"):
            return self.get

        if name.startswith("update_") and not name.startswith("update_user"):
            return self.update

        if name.startswith("delete_") and not name.startswith("delete_user"):
            return self.delete

        raise AttributeError(
            f"'{type(self).__name__}' has no attribute '{name}'. "
            f"Domain-specific methods require explicit implementation on the backend subclass."
        )
