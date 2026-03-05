"""
Unified Relationship Service - Configuration-Driven Generic Relationship Service
==================================================================================

A single generic service that handles ALL domain relationship operations through
configuration, eliminating ~90% of duplicated code across 14 relationship services.

**The Problem:**
14 relationship service files with ~11,000 lines of largely duplicated patterns:
- TasksRelationshipService: 1168 lines
- GoalsRelationshipService: 1002 lines
- HabitsRelationshipService: 1523 lines
- EventsRelationshipService: 1319 lines
- ChoicesRelationshipService: 1192 lines
- PrinciplesRelationshipService: 1013 lines
- (+ 8 more services)

**The Solution:**
One UnifiedRelationshipService + 14 RelationshipConfig objects = ~1000 lines total.

**What This Service Provides:**
1. Graph-native relationship queries (get_entity_*, has_entity_*)
2. Existence checks (has_*, is_*)
3. Batch operations
4. Cross-domain context retrieval
5. Semantic relationship operations
6. Relationship creation (batch edge creation)
7. Intent-based graph intelligence queries

**Usage:**
```python
from core.models.relationship_registry import TASKS_CONFIG
from core.services.relationships import UnifiedRelationshipService

tasks_relationship_service = UnifiedRelationshipService(
    backend=tasks_backend,
    graph_intel=graph_intel,
    config=TASKS_CONFIG,
)

# All methods now available:
await tasks_relationship_service.get_related_uids("subtasks", task_uid)
await tasks_relationship_service.has_relationship("prerequisites", task_uid)
await tasks_relationship_service.get_cross_domain_context(task_uid)
await tasks_relationship_service.get_with_context(task_uid)
```

**File Structure (decomposed 2026-03-01):**
```
core/services/relationships/
├── unified_relationship_service.py   (shell: constructor + core CRUD)
├── planning_mixin.py                 (UserContext-aware planning methods)
├── _batch_operations_mixin.py        (N+1 elimination batch queries)
├── _ordered_relationships_mixin.py   (curriculum ordered/metadata queries)
├── _intelligence_mixin.py            (graph intelligence + semantic + cross-domain)
└── _life_path_mixin.py               (SERVES_LIFE_PATH relationship methods)
```
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from core.models.protocols import DomainModelProtocol
from core.models.relationship_names import RelationshipName
from core.models.relationship_registry import DomainRelationshipConfig
from core.ports.base_protocols import BackendOperations
from core.services.base_service import BaseService
from core.services.infrastructure import RelationshipCreationHelper, SemanticRelationshipHelper
from core.services.relationships._batch_operations_mixin import BatchOperationsMixin
from core.services.relationships._domain_planning_mixin import DomainPlanningMixin
from core.services.relationships._intelligence_mixin import IntelligenceMixin
from core.services.relationships._life_path_mixin import LifePathMixin
from core.services.relationships._ordered_relationships_mixin import OrderedRelationshipsMixin
from core.services.relationships.planning_mixin import PlanningMixin
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_result_score

if TYPE_CHECKING:
    from core.ports.context_awareness_protocols import (
        CoreIdentity,
        CrossDomainAwareness,
        GoalAwareness,
        TaskAwareness,
    )

# Type variables
T = TypeVar("T")  # Domain model type
D = TypeVar("D")  # DTO type


class UnifiedRelationshipService[Ops: BackendOperations, Model: DomainModelProtocol, DtoType](
    PlanningMixin,
    DomainPlanningMixin,
    LifePathMixin,
    IntelligenceMixin,
    OrderedRelationshipsMixin,
    BatchOperationsMixin,
    BaseService[Ops, Model],
):
    """
    Configuration-driven generic relationship service for all domains.

    Type Parameters:
        Ops: Backend operations protocol
        Model: Domain model type
        DtoType: DTO type

    This single service replaces 14 domain-specific relationship services by using
    RelationshipConfig to capture all domain-specific behavior.

    **Key Design Principles:**
    1. Configuration over code - domain nuances captured in RelationshipConfig
    2. Generic methods with config-driven behavior
    3. Composable helpers (semantic, creation) for specialized operations
    4. Backward-compatible method names via dynamic generation

    **Architecture:**
    ```
    UnifiedRelationshipService
    ├── DomainRelationshipConfig (from relationship registry — single source of truth)
    ├── RelationshipCreationHelper (cross-domain link creation)
    ├── SemanticRelationshipHelper (semantic relationship operations)
    └── GraphIntelligenceService (intent-based graph queries)
    ```
    """

    def __init__(
        self,
        backend: Ops,
        config: DomainRelationshipConfig,
        graph_intel: Any | None = None,
    ) -> None:
        """
        Initialize unified relationship service with configuration.

        Args:
            backend: Protocol-based backend for operations (REQUIRED)
            config: DomainRelationshipConfig from relationship registry (REQUIRED)
            graph_intel: GraphIntelligenceService for intent-based queries (optional)
        """
        if not backend:
            raise ValueError(f"{config.entity_label} backend is required")

        # Store configuration BEFORE calling super().__init__()
        # (needed by entity_label property during validation)
        self.config = config

        logger_name = f"{config.domain.value}.relationships"
        super().__init__(backend, logger_name)

        # Store graph_intel
        self.graph_intel = graph_intel

        # Store commonly accessed config values for convenience
        self._domain = config.domain
        self._dto_class = config.dto_class
        self._model_class = config.model_class
        self._backend_get_method = config.backend_get_method

        # Initialize RelationshipCreationHelper (always)
        self.relationship_helper = RelationshipCreationHelper[Model, DtoType](
            service=self,
            backend_get_method=config.backend_get_method,
            dto_class=config.dto_class,
            model_class=config.model_class,
            domain=config.domain,
        )

        # Initialize SemanticRelationshipHelper (optional)
        if config.use_semantic_helper:
            self.semantic_helper = SemanticRelationshipHelper[Model, DtoType](
                service=self,
                backend_get_method=config.backend_get_method,
                dto_class=config.dto_class,
                model_class=config.model_class,
                domain=config.domain,
                source_tag=f"{config.domain.value}_service_explicit",
            )
        else:
            self.semantic_helper = None

        self.logger.debug(
            f"Initialized UnifiedRelationshipService for {config.entity_label}: "
            f"domain={config.domain.value}, "
            f"semantic_helper={'enabled' if config.use_semantic_helper else 'disabled'}, "
            f"graph_intel={'enabled' if graph_intel else 'disabled'}"
        )

    @property
    def entity_label(self) -> str:
        """Return the graph label for this domain's entities."""
        return self.config.entity_label

    def _get_config_value(self, attr_name: str, default: Any = None) -> Any:
        """
        Get configuration value from DomainRelationshipConfig.

        Overrides BaseService._get_config_value() to use DomainRelationshipConfig
        instead of DomainConfig.

        Args:
            attr_name: Attribute name (e.g., "dto_class", "model_class")
            default: Default value if not found

        Returns:
            Configuration value from RelationshipConfig or default
        """
        # Check RelationshipConfig (instance config)
        if getattr(self, "config", None):
            value = getattr(self.config, attr_name, None)
            if value is not None:
                return value

        # Fallback to parent implementation (checks class-level _config)
        return super()._get_config_value(attr_name, default)

    # =========================================================================
    # ENTITY CONVERSION
    # =========================================================================

    def _context_to_domain_model(self, data: dict | DtoType | Model) -> Model:
        """Convert raw data to domain model for context queries."""
        # Guard: ensure classes are configured (always true for properly configured service)
        if self._model_class is None or self._dto_class is None:
            raise ValueError(f"{self.service_name} requires _model_class and _dto_class")

        if isinstance(data, self._model_class):
            return data
        if isinstance(data, self._dto_class):
            return self._model_class.from_dto(data)
        # dict case - convert via DTO
        dto = self._dto_class(**data) if isinstance(data, dict) else data
        return self._model_class.from_dto(dto)

    # =========================================================================
    # GENERIC RELATIONSHIP QUERIES
    # =========================================================================

    async def get_related_uids(
        self,
        relationship_key: str,
        entity_uid: str,
    ) -> Result[list[str]]:
        """
        Get UIDs of related entities by relationship key.

        This generic method replaces domain-specific methods like:
        - get_task_knowledge()
        - get_goal_principles()
        - get_habit_supporting_habits()

        Args:
            relationship_key: Key from config (e.g., "knowledge", "principles", "subtasks")
            entity_uid: Entity UID

        Returns:
            Result[list[str]] of related UIDs
        """
        spec = self.config.get_relationship_by_method(relationship_key)
        if not spec:
            return Result.fail(
                Errors.validation(
                    f"Unknown relationship key '{relationship_key}' for {self.config.entity_label}"
                )
            )

        return await self.backend.get_related_uids(
            uid=entity_uid,
            relationship_type=spec.relationship,
            direction=spec.direction,
        )

    async def has_relationship(
        self,
        relationship_key: str,
        entity_uid: str,
    ) -> Result[bool]:
        """
        Check if entity has any related entities for a relationship key.

        This generic method replaces domain-specific methods like:
        - has_subtasks()
        - is_learning_task()
        - has_prerequisites()

        Args:
            relationship_key: Key from config (e.g., "knowledge", "prerequisites")
            entity_uid: Entity UID

        Returns:
            Result[bool] indicating if any relationships exist
        """
        spec = self.config.get_relationship_by_method(relationship_key)
        if not spec:
            return Result.fail(
                Errors.validation(
                    f"Unknown relationship key '{relationship_key}' for {self.config.entity_label}"
                )
            )

        count_result = await self.backend.count_related(
            uid=entity_uid,
            relationship_type=spec.relationship,
            direction=spec.direction,
        )

        if count_result.is_error:
            return Result.fail(count_result.expect_error())

        return Result.ok(count_result.value > 0)

    async def count_related(
        self,
        relationship_key: str,
        entity_uid: str,
    ) -> Result[int]:
        """
        Count related entities for a relationship key.

        Args:
            relationship_key: Key from config
            entity_uid: Entity UID

        Returns:
            Result[int] with count of related entities
        """
        spec = self.config.get_relationship_by_method(relationship_key)
        if not spec:
            return Result.fail(
                Errors.validation(
                    f"Unknown relationship key '{relationship_key}' for {self.config.entity_label}"
                )
            )

        return await self.backend.count_related(
            uid=entity_uid,
            relationship_type=spec.relationship,
            direction=spec.direction,
        )

    # =========================================================================
    # RELATIONSHIP CREATION
    # =========================================================================

    async def create_user_relationship(
        self,
        user_uid: str,
        entity_uid: str,
        properties: dict[str, Any] | None = None,
    ) -> Result[bool]:
        """
        Create User→Entity relationship in graph.

        Args:
            user_uid: User UID
            entity_uid: Entity UID
            properties: Optional relationship properties

        Returns:
            Result[bool] indicating success
        """
        if not self.config.ownership_relationship:
            return Result.fail(
                Errors.validation(
                    f"No ownership relationship defined for {self.config.entity_label}"
                )
            )

        return await self.relationship_helper.create_user_relationship(
            user_uid=user_uid,
            entity_uid=entity_uid,
            relationship_label=self.config.ownership_relationship.value,
            properties=properties,
        )

    async def delete_user_relationship(
        self,
        user_uid: str,
        entity_uid: str,
    ) -> Result[bool]:
        """
        Delete User→Entity relationship in graph.

        Args:
            user_uid: User UID
            entity_uid: Entity UID

        Returns:
            Result[bool] indicating success
        """
        if not self.config.ownership_relationship:
            return Result.fail(
                Errors.validation(
                    f"No ownership relationship defined for {self.config.entity_label}"
                )
            )

        return await self.backend.delete_relationship(
            from_uid=user_uid,
            to_uid=entity_uid,
            relationship_type=self.config.ownership_relationship,
        )

    async def create_relationship(
        self,
        relationship_key: str,
        from_uid: str,
        to_uid: str,
        properties: dict[str, Any] | None = None,
    ) -> Result[bool]:
        """
        Create a relationship between entities.

        This generic method replaces domain-specific methods like:
        - link_task_to_knowledge()
        - link_goal_to_habit()
        - link_habit_to_principle()

        Args:
            relationship_key: Key from config
            from_uid: Source entity UID
            to_uid: Target entity UID
            properties: Optional relationship properties

        Returns:
            Result[bool] indicating success
        """
        spec = self.config.get_relationship_by_method(relationship_key)
        if not spec:
            return Result.fail(
                Errors.validation(
                    f"Unknown relationship key '{relationship_key}' for {self.config.entity_label}"
                )
            )

        return await self.relationship_helper.create_relationship(
            backend_method=f"link_{self.config.domain.value.rstrip('s')}_to_{relationship_key}",
            from_uid=from_uid,
            to_uid=to_uid,
            relationship_label=spec.relationship.value,
            properties=properties,
        )

    async def delete_relationship(
        self,
        relationship_key: str,
        from_uid: str,
        to_uid: str,
    ) -> Result[bool]:
        """
        Delete a relationship between entities.

        Args:
            relationship_key: Key from config
            from_uid: Source entity UID
            to_uid: Target entity UID

        Returns:
            Result[bool] indicating success
        """
        spec = self.config.get_relationship_by_method(relationship_key)
        if not spec:
            return Result.fail(
                Errors.validation(
                    f"Unknown relationship key '{relationship_key}' for {self.config.entity_label}"
                )
            )

        return await self.backend.delete_relationship(
            from_uid=from_uid,
            to_uid=to_uid,
            relationship_type=spec.relationship,
        )

    async def create_relationships_batch(
        self,
        entity_uid: str,
        relationships: dict[str, list[str]],
    ) -> Result[int]:
        """
        Create multiple relationships for an entity in a single batch.

        This replaces domain-specific batch creation methods like:
        - create_task_relationships()
        - create_goal_relationships()

        Args:
            entity_uid: Entity UID
            relationships: Dict mapping relationship_key → list of target UIDs
                Example: {"knowledge": ["ku:1", "ku:2"], "principles": ["principle:1"]}

        Returns:
            Result[int] with count of relationships created
        """
        total_created = 0

        for relationship_key, target_uids in relationships.items():
            if not target_uids:
                continue

            spec = self.config.get_relationship_by_method(relationship_key)
            if not spec:
                self.logger.warning(f"Unknown relationship key '{relationship_key}', skipping")
                continue

            # Use batch creation via backend - build relationships list
            relationships_batch = [
                (entity_uid, uid, spec.relationship.value, None) for uid in target_uids
            ]
            result = await self.backend.create_relationships_batch(relationships_batch)

            if result.is_ok:
                total_created += result.value

        return Result.ok(total_created)

    # =========================================================================
    # DOMAIN RELATIONSHIPS FETCHING
    # =========================================================================
    # These methods support the TaskRelationships/GoalRelationships pattern
    # by providing parallel fetching of all relationship UIDs.

    @with_error_handling("fetch_all_relationships", error_type="database", uid_param="entity_uid")
    async def fetch_all_relationships(
        self,
        entity_uid: str,
    ) -> Result[dict[str, list[str]]]:
        """
        Fetch all relationship UIDs for an entity in parallel.

        This method supports the domain relationships pattern (TaskRelationships,
        GoalRelationships, etc.) by fetching all configured relationships
        in a single parallel operation.

        Args:
            entity_uid: Entity UID

        Returns:
            Result containing dict of {relationship_key: [uids]}

        Example:
            rels = await service.fetch_all_relationships("task:123")
            # rels.value = {
            #     "knowledge": ["ku:1", "ku:2"],
            #     "principles": ["principle:1"],
            #     "subtasks": ["task:456", "task:789"],
            # }
        """
        import asyncio

        # Build list of relationship keys to fetch
        all_keys = self.config.get_all_relationship_methods()

        # Create coroutines for parallel execution
        coroutines = [self.get_related_uids(key, entity_uid) for key in all_keys]

        # Execute all in parallel
        results = await asyncio.gather(*coroutines)

        # Build result dict
        data: dict[str, list[str]] = {}
        for key, result in zip(all_keys, results, strict=False):
            data[key] = result.value if result.is_ok else []

        return Result.ok(data)

    # =========================================================================
    # USER CONTEXT PLANNING METHODS
    # =========================================================================
    # These methods leverage UserContext (~240 fields) for personalized queries.

    @with_error_handling("get_actionable_for_user", error_type="database")
    async def get_actionable_for_user(
        self,
        context: CrossDomainAwareness,
        limit: int = 10,
        include_learning: bool = True,
    ) -> Result[list[Model]]:
        """
        Get actionable entities for user based on their context.

        "Actionable" means:
        - No blocking prerequisites
        - User has required knowledge mastery
        - Not already completed
        - Relevant to active goals

        Context Fields Used:
        - knowledge_mastery: Filter by user's mastery levels
        - completed_*_uids: Exclude completed items
        - active_goal_uids: Prioritize goal-aligned items
        - overdue_*_uids: Boost urgency

        Args:
            context: User's complete context (~240 fields)
            limit: Maximum number of items to return
            include_learning: Include learning-related items

        Returns:
            Result containing list of actionable entities, ranked by relevance
        """
        domain_name = self.config.domain.value.rstrip("s")
        user_uid = context.user_uid

        # Get all user entities for this domain
        list_result = await self.backend.list(
            filters={"user_uid": user_uid},
            limit=limit * 3,  # Get extra for filtering
        )

        if list_result.is_error:
            return Result.fail(list_result.expect_error())

        # list() returns tuple[list[T], int]
        entities, _ = list_result.value

        # Filter and score each entity
        scored_entities = []
        for entity in entities:
            entity_model = self._context_to_domain_model(entity)

            # Skip completed entities
            if self._is_completed(entity_model, context):
                continue

            # Calculate readiness score
            readiness = await self._calculate_readiness_score(entity_model, context)
            if readiness < 0.5:  # Not ready
                continue

            # Calculate relevance score
            relevance = self._calculate_relevance_score(entity_model, context)

            # Combined score
            score = readiness * 0.4 + relevance * 0.6

            # Urgency boost
            if self._is_urgent(entity_model, context):
                score *= 1.3

            scored_entities.append((entity_model, score))

        # Sort by score descending
        scored_entities.sort(key=get_result_score, reverse=True)

        # Return top N
        result_entities = [e for e, _ in scored_entities[:limit]]

        self.logger.debug(
            f"Found {len(result_entities)} actionable {domain_name}s for user {user_uid}"
        )

        return Result.ok(result_entities)

    @with_error_handling("get_blocked_for_user", error_type="database")
    async def get_blocked_for_user(
        self,
        context: TaskAwareness,
        limit: int = 10,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get entities blocked by unmet prerequisites.

        Returns entities with their blocking reasons, helping users
        understand what they need to do to unblock progress.

        Args:
            context: User's complete context
            limit: Maximum number of items to return

        Returns:
            Result containing list of dicts with entity and blocking_reasons
        """
        domain_name = self.config.domain.value.rstrip("s")
        user_uid = context.user_uid

        list_result = await self.backend.list(filters={"user_uid": user_uid}, limit=limit * 2)

        if list_result.is_error:
            return Result.fail(list_result)

        # list() returns tuple[list, int]
        entities_list, _ = list_result.value
        entities = entities_list or []
        blocked = []

        for entity in entities:
            entity_model = self._context_to_domain_model(entity)

            if self._is_completed(entity_model, context):
                continue

            readiness = await self._calculate_readiness_score(entity_model, context)
            if readiness >= 0.5:  # Not blocked
                continue

            # Get blocking reasons
            reasons = await self._identify_blocking_reasons(entity_model, context)
            if reasons:
                blocked.append(
                    {
                        domain_name: entity_model,
                        "blocking_reasons": reasons,
                        "readiness_score": readiness,
                    }
                )

        return Result.ok(blocked[:limit])

    @with_error_handling("get_goal_aligned_for_user", error_type="database")
    async def get_goal_aligned_for_user(
        self,
        context: GoalAwareness,
        goal_uid: str | None = None,
        limit: int = 10,
    ) -> Result[list[Model]]:
        """
        Get entities aligned with user's goals.

        Args:
            context: User's complete context
            goal_uid: Optional specific goal to filter by
            limit: Maximum number of items

        Returns:
            Result containing goal-aligned entities
        """
        domain_name = self.config.domain.value.rstrip("s")
        user_uid = context.user_uid

        # Build query based on domain's goal relationships
        goal_rels = [
            RelationshipName.FULFILLS_GOAL.value,
            RelationshipName.SUPPORTS_GOAL.value,
            RelationshipName.CONTRIBUTES_TO_GOAL.value,
        ]
        rel_pattern = "|".join(goal_rels)

        entity_label = self.config.entity_label
        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[:HAS_{domain_name.upper()}]->(e:{entity_label})
        MATCH (e)-[:{rel_pattern}]->(g:Goal)
        {"WHERE g.uid = $goal_uid" if goal_uid else ""}
        RETURN DISTINCT e, collect(g.uid) as goal_uids
        ORDER BY size(collect(g.uid)) DESC
        LIMIT $limit
        """

        params: dict[str, Any] = {"user_uid": user_uid, "limit": limit}
        if goal_uid:
            params["goal_uid"] = goal_uid

        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return Result.fail(result)

        entities = [
            self._context_to_domain_model(record.get("e"))
            for record in result.value
            if record.get("e")
        ]

        return Result.ok(entities)

    # =========================================================================
    # SCORING HELPERS (for UserContext methods)
    # =========================================================================

    async def _calculate_readiness_score(
        self,
        entity: Model,
        context: TaskAwareness,
    ) -> float:
        """Calculate readiness score (0-1) based on prerequisites met."""
        try:
            entity_uid = getattr(entity, "uid", None)
            if not entity_uid:
                return 0.0

            # Get prerequisites via configured relationship keys
            prereq_tasks: list[str] = []
            prereq_knowledge: list[str] = []

            # Try to get prerequisite relationships
            for key in ["prerequisite_tasks", "prerequisites"]:
                if self.config.get_relationship_by_method(key):
                    result = await self.get_related_uids(key, entity_uid)
                    if result.is_ok:
                        prereq_tasks.extend(result.value)
                        break

            for key in ["prerequisite_knowledge", "required_knowledge"]:
                if self.config.get_relationship_by_method(key):
                    result = await self.get_related_uids(key, entity_uid)
                    if result.is_ok:
                        prereq_knowledge.extend(result.value)
                        break

            if not prereq_tasks and not prereq_knowledge:
                return 1.0  # No prerequisites = fully ready

            # Check task prerequisites
            completed_tasks = set(getattr(context, "completed_task_uids", []) or [])
            tasks_met = sum(1 for t in prereq_tasks if t in completed_tasks)
            task_score = tasks_met / len(prereq_tasks) if prereq_tasks else 1.0

            # Check knowledge prerequisites
            mastery = getattr(context, "knowledge_mastery", {}) or {}
            knowledge_met = sum(1 for k in prereq_knowledge if mastery.get(k, 0) >= 0.7)
            knowledge_score = knowledge_met / len(prereq_knowledge) if prereq_knowledge else 1.0

            # Weighted average
            return task_score * 0.5 + knowledge_score * 0.5

        except Exception:
            return 0.5  # Default to uncertain

    def _calculate_relevance_score(
        self,
        entity: Model,
        context: GoalAwareness,
    ) -> float:
        """Calculate relevance score (0-1) based on goal alignment."""
        try:
            score = 0.5  # Base score

            # Priority boost
            priority = getattr(entity, "priority", None)
            if priority:
                priority_scores = {"urgent": 0.3, "high": 0.2, "medium": 0.1, "low": 0.0}
                score += priority_scores.get(str(priority).lower(), 0.0)

            # Goal alignment boost
            goal_uid = getattr(entity, "fulfills_goal_uid", None) or getattr(
                entity, "supports_goal_uid", None
            )
            active_goals = set(getattr(context, "active_goal_uids", []) or [])
            if goal_uid and goal_uid in active_goals:
                score += 0.2

            return min(score, 1.0)

        except Exception:
            return 0.5

    def _is_completed(self, entity: Model, context: CoreIdentity) -> bool:
        """Check if entity is completed based on context."""
        entity_uid = getattr(entity, "uid", None)
        status = getattr(entity, "status", None)

        # Check status
        if status and str(status).lower() in ("completed", "done"):
            return True

        # Check context completed lists
        domain_name = self.config.domain.value.rstrip("s")
        completed_field = f"completed_{domain_name}_uids"
        completed_uids = set(getattr(context, completed_field, []) or [])

        return entity_uid in completed_uids

    def _is_urgent(self, entity: Model, context: TaskAwareness) -> bool:
        """Check if entity is urgent based on context."""
        entity_uid = getattr(entity, "uid", None)

        # Check overdue
        domain_name = self.config.domain.value.rstrip("s")
        overdue_field = f"overdue_{domain_name}_uids"
        overdue_uids = set(getattr(context, overdue_field, []) or [])

        if entity_uid in overdue_uids:
            return True

        # Check priority
        priority = getattr(entity, "priority", None)
        return bool(priority and str(priority).lower() == "urgent")

    async def _identify_blocking_reasons(
        self,
        entity: Model,
        context: TaskAwareness,
    ) -> list[str]:
        """Identify what's blocking this entity."""
        reasons = []
        entity_uid = getattr(entity, "uid", None)
        if not entity_uid:
            return reasons

        try:
            # Check prerequisite tasks
            for key in ["prerequisite_tasks", "prerequisites"]:
                if self.config.get_relationship_by_method(key):
                    result = await self.get_related_uids(key, entity_uid)
                    if result.is_ok:
                        completed_tasks = set(getattr(context, "completed_task_uids", []) or [])
                        for task_uid in result.value:
                            if task_uid not in completed_tasks:
                                reasons.append(f"Requires completion of task: {task_uid}")
                        break

            # Check knowledge prerequisites
            for key in ["prerequisite_knowledge", "required_knowledge"]:
                if self.config.get_relationship_by_method(key):
                    result = await self.get_related_uids(key, entity_uid)
                    if result.is_ok:
                        mastery = getattr(context, "knowledge_mastery", {}) or {}
                        for ku_uid in result.value:
                            current_mastery = mastery.get(ku_uid, 0)
                            if current_mastery < 0.7:
                                reasons.append(
                                    f"Requires knowledge mastery: {ku_uid} "
                                    f"(70% needed, you have {int(current_mastery * 100)}%)"
                                )
                        break

        except Exception as e:
            self.logger.warning(f"Error identifying blocking reasons: {e}")

        return reasons

    # =========================================================================
    # TYPED LINK METHODS
    # =========================================================================
    # Domain-specific link methods with typed parameters.

    async def link_to_knowledge(
        self,
        entity_uid: str,
        knowledge_uid: str,
        **properties: Any,
    ) -> Result[bool]:
        """
        Link entity to knowledge unit with domain-specific properties.

        This is a typed convenience method that wraps create_relationship()
        with the appropriate relationship key for knowledge links.

        Args:
            entity_uid: Source entity UID
            knowledge_uid: Target knowledge UID
            **properties: Domain-specific properties (varies by domain)
                - Tasks: knowledge_score_required, is_learning_opportunity
                - Goals: proficiency_required, priority
                - Habits: skill_level, proficiency_gain_rate

        Returns:
            Result[bool] indicating success
        """
        # Try different knowledge relationship keys
        for key in ["knowledge", "prerequisite_knowledge", "required_knowledge"]:
            if self.config.get_relationship_by_method(key):
                return await self.create_relationship(
                    relationship_key=key,
                    from_uid=entity_uid,
                    to_uid=knowledge_uid,
                    properties=properties if properties else None,
                )

        return Result.fail(
            Errors.validation(
                f"No knowledge relationship configured for {self.config.entity_label}"
            )
        )

    async def link_to_goal(
        self,
        entity_uid: str,
        goal_uid: str,
        **properties: Any,
    ) -> Result[bool]:
        """
        Link entity to goal with domain-specific properties.

        Args:
            entity_uid: Source entity UID
            goal_uid: Target goal UID
            **properties: Domain-specific properties
                - Tasks: contribution_percentage, milestone_uid
                - Habits: weight, contribution_type

        Returns:
            Result[bool] indicating success
        """
        for key in ["contributes_to_goal", "fulfills_goal", "supported_goals", "goals"]:
            if self.config.get_relationship_by_method(key):
                return await self.create_relationship(
                    relationship_key=key,
                    from_uid=entity_uid,
                    to_uid=goal_uid,
                    properties=properties if properties else None,
                )

        return Result.fail(
            Errors.validation(f"No goal relationship configured for {self.config.entity_label}")
        )

    async def link_to_principle(
        self,
        entity_uid: str,
        principle_uid: str,
        **properties: Any,
    ) -> Result[bool]:
        """
        Link entity to principle with domain-specific properties.

        Args:
            entity_uid: Source entity UID
            principle_uid: Target principle UID
            **properties: Domain-specific properties
                - Goals: alignment_strength
                - Habits: embodiment_strength

        Returns:
            Result[bool] indicating success
        """
        for key in ["principles", "aligned_principles", "embodying_principles"]:
            if self.config.get_relationship_by_method(key):
                return await self.create_relationship(
                    relationship_key=key,
                    from_uid=entity_uid,
                    to_uid=principle_uid,
                    properties=properties if properties else None,
                )

        return Result.fail(
            Errors.validation(
                f"No principle relationship configured for {self.config.entity_label}"
            )
        )
