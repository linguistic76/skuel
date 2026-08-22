"""
Unified Relationship Service - Configuration-Driven Generic Relationship Service
==================================================================================

A single generic service that handles ALL domain relationship operations through
configuration. One UnifiedRelationshipService + RelationshipConfig objects per domain.

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
from core.models.type_hints import EntityUID
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
├── _batch_operations_mixin.py        (N+1 elimination batch queries)
├── _ordered_relationships_mixin.py   (curriculum ordered/metadata queries)
└── _intelligence_mixin.py            (graph intelligence + semantic + cross-domain)
```
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from core.models.protocols import DomainModelProtocol, DTOProtocol
from core.models.relationship_registry import (
    DomainRelationshipConfig,
    UnifiedRelationshipDefinition,
)
from core.models.type_hints import EntityUID, Neo4jProperties
from core.ports.base_protocols import BackendOperations
from core.services.base_service import BaseService
from core.services.infrastructure import SemanticRelationshipLinker
from core.services.relationships._batch_operations_mixin import BatchOperationsMixin
from core.services.relationships._intelligence_mixin import IntelligenceMixin
from core.services.relationships._ordered_relationships_mixin import OrderedRelationshipsMixin
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.user.unified_user_context import UserContext

# Type variables
T = TypeVar("T")  # Domain model type
D = TypeVar("D")  # DTO type


def _spec_edge_filter(spec: UnifiedRelationshipDefinition) -> Neo4jProperties | None:
    """Edge-property filter for a relationship spec, or ``None`` when unfiltered.

    A spec with ``filter_property`` (e.g. GOALS_CONFIG's ``essential_habits`` =
    SUPPORTS_GOAL incoming filtered by ``essentiality="essential"``) selects only edges
    carrying that property value. Without this, every essentiality tier resolved to the
    same unfiltered set — the read half of the goal-habit essentiality bug. The backend
    ``get_related_uids`` / ``count_related`` apply it as ``WHERE r.<prop> = $value``.
    """
    if spec.filter_property is None:
        return None
    return {spec.filter_property: spec.filter_value}


class UnifiedRelationshipService[
    Ops: BackendOperations,
    Model: DomainModelProtocol,
    DtoType: DTOProtocol,
](
    IntelligenceMixin[Ops],
    OrderedRelationshipsMixin[Ops],
    BatchOperationsMixin[Ops],
    BaseService[Ops, Model],
):
    """
    Configuration-driven generic relationship service for all domains.

    Type Parameters:
        Ops: Backend operations protocol
        Model: Domain model type
        DtoType: DTO type

    This single service replaces per-entity-type relationship services by using
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
    ├── SemanticRelationshipLinker (semantic relationship operations)
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

        # Initialize SemanticRelationshipLinker (optional)
        if config.use_semantic_helper:
            self.semantic_helper = SemanticRelationshipLinker[Model, DtoType](
                service=self,
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
        entity_uid: EntityUID,
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
            properties=_spec_edge_filter(spec),
        )

    async def has_relationship(
        self,
        relationship_key: str,
        entity_uid: EntityUID,
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
            properties=_spec_edge_filter(spec),
        )

        if count_result.is_error:
            return Result.fail(count_result)

        return Result.ok(count_result.value > 0)

    async def count_related(
        self,
        relationship_key: str,
        entity_uid: EntityUID,
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
            properties=_spec_edge_filter(spec),
        )

    # =========================================================================
    # RELATIONSHIP CREATION
    # =========================================================================
    # NOTE: there is deliberately NO user→entity ownership writer here. The
    # former create_user_relationship/delete_user_relationship pair wrote the
    # registry's paper per-domain ownership edges (HAS_TASK, …) and was deleted
    # with that family (ADR-086) — :OWNS enters the graph only through the four
    # write doors the ADR names.

    async def create_relationship(
        self,
        relationship_key: str,
        from_uid: str,
        to_uid: str,
        properties: dict[str, Any] | None = None,
    ) -> Result[bool]:
        """
        Create a single relationship edge between entities.

        Routes through the proven ``backend.create_relationships_batch`` path (the same
        one create-flows and ``create_relationships_batch`` use), with the edge type
        taken from the registry ``spec`` for ``relationship_key``. This replaced a
        dynamic ``link_{domain}_to_{key}`` backend-method dispatch that existed only for
        two habit cases and failed at runtime ("Backend method not found") for every
        other domain — see ``/docs/patterns/UNIFIED_RELATIONSHIP_SERVICE.md``.

        Args:
            relationship_key: Key from config
            from_uid: Source entity UID
            to_uid: Target entity UID
            properties: Optional edge properties (persisted on the relationship)

        Returns:
            Result[bool] — True when the edge was created.
        """
        spec = self.config.get_relationship_by_method(relationship_key)
        if not spec:
            return Result.fail(
                Errors.validation(
                    f"Unknown relationship key '{relationship_key}' for {self.config.entity_label}"
                )
            )

        result = await self.backend.create_relationships_batch(
            [self._orient_edge(spec, from_uid, to_uid, properties)]
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value > 0)

    @staticmethod
    def _orient(spec: UnifiedRelationshipDefinition, from_uid: str, to_uid: str) -> tuple[str, str]:
        """Orient ``(owner, related)`` → ``(edge_from, edge_to)`` per the registry direction.

        ``from_uid`` is the entity that owns this domain config, ``to_uid`` the related
        entity. The registry read paths are direction-aware, so an ``incoming`` spec
        (stored related→owner, e.g. goals ``supporting_habits`` =
        ``(Habit)-[:SUPPORTS_GOAL]->(Goal)``) must have its endpoints swapped — on write
        AND on delete — otherwise the edge is created/matched backwards and the
        direction-aware reader never sees it. Shared by create_relationship,
        create_relationships_batch, and delete_relationship so all three agree.
        """
        if spec.direction == "incoming":
            return (to_uid, from_uid)
        return (from_uid, to_uid)

    @classmethod
    def _orient_edge(
        cls,
        spec: UnifiedRelationshipDefinition,
        from_uid: str,
        to_uid: str,
        properties: dict[str, Any] | None,
    ) -> tuple[str, str, str, dict[str, Any] | None]:
        """``_orient`` plus the relationship type and (filter-stamped) properties.

        A *filtered* spec (e.g. ``essential_habits`` = SUPPORTS_GOAL with
        ``essentiality="essential"``) defines edges by an edge property. Writing through
        that key must stamp the property, or the read side — which now requires
        ``r.essentiality = "essential"`` — would never see the edge back (create succeeds,
        read returns empty). The stamp uses ``setdefault`` so an explicit caller value
        wins. Unfiltered specs (the ``supporting_habits`` catch-all, all other domains)
        are untouched.
        """
        edge_from, edge_to = cls._orient(spec, from_uid, to_uid)
        return (
            edge_from,
            edge_to,
            spec.relationship.value,
            cls._stamp_spec_filter(spec, properties),
        )

    @staticmethod
    def _stamp_spec_filter(
        spec: UnifiedRelationshipDefinition, properties: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Merge a filtered spec's ``filter_property=filter_value`` into write properties.

        Keeps create/read symmetric for property-filtered relationship keys (see
        _orient_edge). No-op for unfiltered specs; an explicit caller value is preserved.
        """
        if spec.filter_property is None:
            return properties
        stamped = dict(properties or {})
        stamped.setdefault(spec.filter_property, spec.filter_value)
        return stamped

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

        edge_from, edge_to = self._orient(spec, from_uid, to_uid)
        return await self.backend.delete_relationship(
            from_uid=edge_from,
            to_uid=edge_to,
            relationship_type=spec.relationship,
        )

    async def create_relationships_batch(
        self,
        entity_uid: EntityUID,
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

            # Use batch creation via backend — orient each edge per the registry
            # direction so incoming specs are not written backwards (see _orient_edge).
            relationships_batch = [
                self._orient_edge(spec, entity_uid, uid, None) for uid in target_uids
            ]
            result = await self.backend.create_relationships_batch(relationships_batch)

            if result.is_ok:
                total_created += result.value

        return Result.ok(total_created)

    # =========================================================================
    # USER CONTEXT PLANNING METHODS
    # =========================================================================
    # These methods leverage UserContext (~240 fields) for personalized queries.

    @with_error_handling("get_blocked_for_user", error_type="database")
    async def get_blocked_for_user(
        self,
        context: UserContext,
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

    # =========================================================================
    # SCORING HELPERS (for UserContext methods)
    # =========================================================================

    async def _calculate_readiness_score(
        self,
        entity: Model,
        context: UserContext,
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

        except (ValueError, TypeError, AttributeError, KeyError):  # fmt: skip
            return 0.5  # Default to uncertain
        except Exception:  # safety-net: catch unexpected errors
            return 0.5  # Default to uncertain

    def _calculate_relevance_score(
        self,
        entity: Model,
        context: UserContext,
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

        except (ValueError, TypeError, AttributeError, KeyError):  # fmt: skip
            return 0.5
        except Exception:  # safety-net: catch unexpected errors
            return 0.5

    def _is_completed(self, entity: Model, context: UserContext) -> bool:
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

    async def _identify_blocking_reasons(
        self,
        entity: Model,
        context: UserContext,
    ) -> list[str]:
        """Identify what's blocking this entity."""
        reasons: list[str] = []
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

        except (ValueError, TypeError, AttributeError, KeyError) as e:
            self.logger.warning(f"Error identifying blocking reasons: {e}")
        except Exception as e:  # safety-net: catch unexpected errors
            self.logger.warning(f"Error identifying blocking reasons: {e}")

        return reasons

    # =========================================================================
    # CROSS-DOMAIN LINKING
    # =========================================================================
    # Activity/Curriculum facades link into the semantic graph via
    # ``create_relationship("<explicit method_key>", ...)`` — the registry validates
    # the key (fails closed on a typo), orients direction via ``_orient_edge``, and
    # writes through the proven batch path. The facade is where domain intent lives
    # (``link_task_to_goal`` knows it means ``contributes_to_goal``), so the key is
    # named explicitly there rather than guessed from a candidate list here.
    # Coverage is guarded by tests/test_cross_domain_link_keys.py.
