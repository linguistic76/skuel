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
"""

from __future__ import annotations

from datetime import UTC
from typing import TYPE_CHECKING, Any, TypeVar

from core.constants import GraphDepth
from core.models.protocols import DomainModelProtocol
from core.models.relationship_names import RelationshipName
from core.models.relationship_registry import DomainRelationshipConfig
from core.services.base_service import BaseService
from core.services.infrastructure import RelationshipCreationHelper, SemanticRelationshipHelper
from core.ports.base_protocols import BackendOperations
from core.services.relationships.planning_mixin import PlanningMixin
from core.utils.decorators import requires_graph_intelligence, with_error_handling
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_result_score

if TYPE_CHECKING:
    from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
    from core.models.graph_context import GraphContext
    from core.services.user.unified_user_context import UserContext

# Type variables
T = TypeVar("T")  # Domain model type
D = TypeVar("D")  # DTO type


class UnifiedRelationshipService[Ops: BackendOperations, Model: DomainModelProtocol, DtoType](
    PlanningMixin, BaseService[Ops, Model]
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
    # BATCH OPERATIONS
    # =========================================================================

    @with_error_handling("batch_has_relationship", error_type="database")
    async def batch_has_relationship(
        self,
        relationship_key: str,
        entity_uids: list[str],
    ) -> Result[dict[str, bool]]:
        """
        Check if multiple entities have relationships of a given type.

        This eliminates N+1 queries by using UNWIND in a single query.

        Args:
            relationship_key: Key from config
            entity_uids: List of entity UIDs

        Returns:
            Result[dict[str, bool]] mapping uid → has_relationship
        """
        spec = self.config.get_relationship_by_method(relationship_key)
        if not spec:
            return Result.fail(
                Errors.validation(
                    f"Unknown relationship key '{relationship_key}' for {self.config.entity_label}"
                )
            )

        if not entity_uids:
            return Result.ok({})

        # Build batch query
        direction_clause = (
            "-[r]->"
            if spec.direction == "outgoing"
            else "<-[r]-"
            if spec.direction == "incoming"
            else "-[r]-"
        )

        query = f"""
        UNWIND $entity_uids AS entity_uid
        MATCH (e:{self.config.entity_label} {{uid: entity_uid}})
        OPTIONAL MATCH (e){direction_clause}(related)
        WHERE type(r) = $relationship_type
        RETURN entity_uid, count(related) > 0 AS has_relationship
        """

        params = {
            "entity_uids": entity_uids,
            "relationship_type": spec.relationship.value,
        }

        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return Result.fail(result.expect_error())

        # Transform to dict
        return Result.ok(
            {
                str(record["entity_uid"]): record.get("has_relationship", False)
                for record in result.value
            }
        )

    @with_error_handling("batch_count_related", error_type="database")
    async def batch_count_related(
        self,
        relationship_key: str,
        entity_uids: list[str],
    ) -> Result[dict[str, int]]:
        """
        Count related entities for multiple entities.

        Args:
            relationship_key: Key from config
            entity_uids: List of entity UIDs

        Returns:
            Result[dict[str, int]] mapping uid → count
        """
        spec = self.config.get_relationship_by_method(relationship_key)
        if not spec:
            return Result.fail(
                Errors.validation(
                    f"Unknown relationship key '{relationship_key}' for {self.config.entity_label}"
                )
            )

        if not entity_uids:
            return Result.ok({})

        direction_clause = (
            "-[r]->"
            if spec.direction == "outgoing"
            else "<-[r]-"
            if spec.direction == "incoming"
            else "-[r]-"
        )

        query = f"""
        UNWIND $entity_uids AS entity_uid
        MATCH (e:{self.config.entity_label} {{uid: entity_uid}})
        OPTIONAL MATCH (e){direction_clause}(related)
        WHERE type(r) = $relationship_type
        RETURN entity_uid, count(related) AS count
        """

        params = {
            "entity_uids": entity_uids,
            "relationship_type": spec.relationship.value,
        }

        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok(
            {str(record["entity_uid"]): record.get("count", 0) for record in result.value}
        )

    @with_error_handling("batch_get_related_uids", error_type="database")
    async def batch_get_related_uids(
        self,
        relationship_key: str,
        entity_uids: list[str],
    ) -> Result[dict[str, list[str]]]:
        """
        Get related entity UIDs for multiple entities in a single query.

        Eliminates N+1 query pattern when fetching relationships for multiple entities.

        Args:
            relationship_key: Key from config (e.g., "knowledge", "principles")
            entity_uids: List of entity UIDs to query

        Returns:
            Result[dict[str, list[str]]] mapping entity_uid → list of related UIDs

        Example:
            # Instead of N+1:
            # for habit in habits:
            #     uids = await service.get_related_uids("knowledge", habit.uid)
            #
            # Use batch:
            result = await service.batch_get_related_uids("knowledge", [h.uid for h in habits])
            # Returns: {"habit:1": ["ku:a", "ku:b"], "habit:2": ["ku:c"], ...}
        """
        spec = self.config.get_relationship_by_method(relationship_key)
        if not spec:
            return Result.fail(
                Errors.validation(
                    f"Unknown relationship key '{relationship_key}' for {self.config.entity_label}"
                )
            )

        if not entity_uids:
            return Result.ok({})

        direction_clause = (
            "-[r]->"
            if spec.direction == "outgoing"
            else "<-[r]-"
            if spec.direction == "incoming"
            else "-[r]-"
        )

        query = f"""
        UNWIND $entity_uids AS entity_uid
        MATCH (e:{self.config.entity_label} {{uid: entity_uid}})
        OPTIONAL MATCH (e){direction_clause}(related)
        WHERE type(r) = $relationship_type
        RETURN entity_uid, collect(related.uid) AS related_uids
        """

        params = {
            "entity_uids": entity_uids,
            "relationship_type": spec.relationship.value,
        }

        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return Result.fail(result.expect_error())

        # Build mapping, filtering out None values from collect()
        return Result.ok(
            {
                str(record["entity_uid"]): [
                    uid for uid in (record.get("related_uids") or []) if uid is not None
                ]
                for record in result.value
            }
        )

    # =========================================================================
    # ORDERED RELATIONSHIPS & EDGE METADATA (January 2026 - Curriculum Domains)
    # =========================================================================
    # These methods support curriculum domain patterns:
    # - Ordered relationships (HAS_STEP with sequence property)
    # - Edge metadata retrieval (return entity + edge properties)
    # - Hierarchical traversal (LP → LS → KU)

    @with_error_handling("get_ordered_related_uids", error_type="database", uid_param="entity_uid")
    async def get_ordered_related_uids(
        self,
        relationship_key: str,
        entity_uid: str,
    ) -> Result[list[str]]:
        """
        Get related entity UIDs in order defined by edge property.

        Uses order_by_property from RelationshipSpec if configured.
        Falls back to unordered query if no ordering configured.

        Args:
            relationship_key: Key from config (e.g., "steps")
            entity_uid: Entity UID

        Returns:
            Result[list[str]] of related UIDs in order

        Example:
            # Get LP steps in sequence order
            result = await lp_rel.get_ordered_related_uids("steps", "lp:python-basics")
            # Returns: ["ls:intro", "ls:syntax", "ls:functions", ...]
        """
        spec = self.config.get_relationship_by_method(relationship_key)
        if not spec:
            return Result.fail(
                Errors.validation(
                    f"Unknown relationship key '{relationship_key}' for {self.config.entity_label}"
                )
            )

        direction_clause = (
            "-[r]->"
            if spec.direction == "outgoing"
            else "<-[r]-"
            if spec.direction == "incoming"
            else "-[r]-"
        )

        # Build ORDER BY clause if configured
        order_clause = ""
        if spec.order_by_property:
            order_clause = f"ORDER BY r.{spec.order_by_property} {spec.order_direction}"

        query = f"""
        MATCH (e:{self.config.entity_label} {{uid: $entity_uid}}){direction_clause}(related)
        WHERE type(r) = $relationship_type
        RETURN related.uid AS uid
        {order_clause}
        """

        params = {
            "entity_uid": entity_uid,
            "relationship_type": spec.relationship.value,
        }

        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok([str(record["uid"]) for record in result.value if record.get("uid")])

    @with_error_handling("get_related_with_metadata", error_type="database", uid_param="entity_uid")
    async def get_related_with_metadata(
        self,
        relationship_key: str,
        entity_uid: str,
        edge_properties: list[str] | None = None,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get related entities WITH edge property metadata.

        Returns list of dicts containing entity data and edge properties.
        Uses include_edge_properties from RelationshipSpec if edge_properties not provided.
        Uses order_by_property from RelationshipSpec if configured.

        Args:
            relationship_key: Key from config (e.g., "steps")
            entity_uid: Entity UID
            edge_properties: Optional override of edge properties to return

        Returns:
            Result[list[dict]] with structure:
            [{"uid": "ls:1", "title": "...", "edge": {"sequence": 0, ...}}, ...]

        Example:
            # Get LP steps with sequence numbers
            result = await lp_rel.get_related_with_metadata("steps", "lp:python-basics")
            # Returns: [
            #     {"uid": "ls:intro", "title": "Introduction", "edge": {"sequence": 0}},
            #     {"uid": "ls:syntax", "title": "Basic Syntax", "edge": {"sequence": 1}},
            # ]
        """
        spec = self.config.get_relationship_by_method(relationship_key)
        if not spec:
            return Result.fail(
                Errors.validation(
                    f"Unknown relationship key '{relationship_key}' for {self.config.entity_label}"
                )
            )

        direction_clause = (
            "-[r]->"
            if spec.direction == "outgoing"
            else "<-[r]-"
            if spec.direction == "incoming"
            else "-[r]-"
        )

        # Determine which edge properties to return
        props_to_return = edge_properties or list(spec.include_edge_properties)

        # Build edge properties return clause
        if props_to_return:
            edge_props_clause = ", ".join(f"{p}: r.{p}" for p in props_to_return)
            edge_return = f"{{{edge_props_clause}}}"
        else:
            edge_return = "properties(r)"

        # Build ORDER BY clause if configured
        order_clause = ""
        if spec.order_by_property:
            order_clause = f"ORDER BY r.{spec.order_by_property} {spec.order_direction}"

        query = f"""
        MATCH (e:{self.config.entity_label} {{uid: $entity_uid}}){direction_clause}(related)
        WHERE type(r) = $relationship_type
        RETURN related.uid AS uid,
               related.title AS title,
               {edge_return} AS edge
        {order_clause}
        """

        params = {
            "entity_uid": entity_uid,
            "relationship_type": spec.relationship.value,
        }

        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok(
            [
                {
                    "uid": str(record["uid"]),
                    "title": record.get("title"),
                    "edge": dict(record.get("edge", {})) if record.get("edge") else {},
                }
                for record in result.value
                if record.get("uid")
            ]
        )

    @with_error_handling("reorder_relationships", error_type="database", uid_param="entity_uid")
    async def reorder_relationships(
        self,
        relationship_key: str,
        entity_uid: str,
        target_uid_sequence: list[str],
        sequence_property: str = "sequence",
    ) -> Result[int]:
        """
        Reorder relationships by updating edge sequence properties.

        Updates the sequence property on each relationship edge to match
        the order of target_uid_sequence (0-indexed).

        Args:
            relationship_key: Key from config (e.g., "steps")
            entity_uid: Source entity UID
            target_uid_sequence: List of target UIDs in desired order
            sequence_property: Edge property name for sequence (default: "sequence")

        Returns:
            Result[int] with count of relationships updated

        Example:
            # Reorder LP steps
            await lp_rel.reorder_relationships(
                "steps",
                "lp:python-basics",
                ["ls:syntax", "ls:intro", "ls:functions"],  # New order
            )
        """
        spec = self.config.get_relationship_by_method(relationship_key)
        if not spec:
            return Result.fail(
                Errors.validation(
                    f"Unknown relationship key '{relationship_key}' for {self.config.entity_label}"
                )
            )

        if not target_uid_sequence:
            return Result.ok(0)

        direction_clause = (
            "-[r]->"
            if spec.direction == "outgoing"
            else "<-[r]-"
            if spec.direction == "incoming"
            else "-[r]-"
        )

        # Build ordering data: [(uid, sequence), ...]
        ordering_data = [{"uid": uid, "seq": idx} for idx, uid in enumerate(target_uid_sequence)]

        query = f"""
        UNWIND $ordering AS item
        MATCH (e:{self.config.entity_label} {{uid: $entity_uid}}){direction_clause}(target {{uid: item.uid}})
        WHERE type(r) = $relationship_type
        SET r.{sequence_property} = item.seq
        RETURN count(*) AS updated_count
        """

        params = {
            "entity_uid": entity_uid,
            "ordering": ordering_data,
            "relationship_type": spec.relationship.value,
        }

        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return Result.fail(result.expect_error())

        updated = sum(record.get("updated_count", 0) for record in result.value)

        self.logger.info(f"Reordered {updated} {relationship_key} relationships for {entity_uid}")

        return Result.ok(updated)

    @with_error_handling(
        "create_relationship_with_properties", error_type="database", uid_param="from_uid"
    )
    async def create_relationship_with_properties(
        self,
        relationship_key: str,
        from_uid: str,
        to_uid: str,
        edge_properties: dict[str, Any],
    ) -> Result[bool]:
        """
        Create a relationship with specific edge properties.

        Useful for curriculum relationships that need metadata like sequence numbers.

        Args:
            relationship_key: Key from config (e.g., "steps")
            from_uid: Source entity UID
            to_uid: Target entity UID
            edge_properties: Properties to set on the relationship edge

        Returns:
            Result[bool] indicating success

        Example:
            # Attach step to path with sequence
            await lp_rel.create_relationship_with_properties(
                "steps",
                "lp:python-basics",
                "ls:new-step",
                {"sequence": 5, "completed": False},
            )
        """
        spec = self.config.get_relationship_by_method(relationship_key)
        if not spec:
            return Result.fail(
                Errors.validation(
                    f"Unknown relationship key '{relationship_key}' for {self.config.entity_label}"
                )
            )

        direction_clause = (
            "-[r]->"
            if spec.direction == "outgoing"
            else "<-[r]-"
            if spec.direction == "incoming"
            else "-[r]-"
        )

        query = f"""
        MATCH (from {{uid: $from_uid}})
        MATCH (to {{uid: $to_uid}})
        MERGE (from){direction_clause.replace("[r]", f"[r:{spec.relationship.value}]")}(to)
        SET r += $properties
        RETURN r IS NOT NULL AS success
        """

        params = {
            "from_uid": from_uid,
            "to_uid": to_uid,
            "properties": edge_properties,
        }

        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []
        success = records[0].get("success", False) if records else False

        if success:
            self.logger.info(
                f"Created {spec.relationship.value} relationship: {from_uid} → {to_uid} "
                f"with properties: {edge_properties}"
            )

        return Result.ok(success)

    @with_error_handling("get_hierarchical_children", error_type="database", uid_param="entity_uid")
    async def get_hierarchical_children(
        self,
        entity_uid: str,
        relationship_chain: list[tuple[str, str]],
        max_depth: int = 3,
    ) -> Result[list[dict[str, Any]]]:
        """
        Multi-hop hierarchical traversal for curriculum patterns.

        Traverses relationship chain and returns nested structure with edge metadata.
        Supports patterns like LP → LS → KU.

        Args:
            entity_uid: Root entity UID
            relationship_chain: List of (relationship_key, target_label) tuples
                Example: [("steps", "Ls"), ("knowledge", "Ku")]
            max_depth: Maximum traversal depth (default: 3)

        Returns:
            Result[list[dict]] with hierarchical structure including edge metadata

        Example:
            # Get LP with steps and their knowledge units
            result = await lp_rel.get_hierarchical_children(
                "lp:python-basics",
                [("steps", "Ls"), ("knowledge", "Ku")],
            )
            # Returns: [
            #     {
            #         "uid": "ls:intro",
            #         "title": "Introduction",
            #         "edge": {"sequence": 0},
            #         "children": [
            #             {"uid": "ku:python-overview", "title": "Python Overview"},
            #         ]
            #     },
            # ]
        """
        if not relationship_chain:
            return Result.ok([])

        if len(relationship_chain) > max_depth:
            return Result.fail(
                Errors.validation(f"Relationship chain exceeds max_depth of {max_depth}")
            )

        # Build the MATCH pattern dynamically
        match_parts = [f"(root:{self.config.entity_label} {{uid: $entity_uid}})"]
        return_parts = []
        order_expressions = []  # Store ordering for each level

        for idx, (rel_key, target_label) in enumerate(relationship_chain):
            spec = self.config.get_relationship_by_method(rel_key)
            if not spec:
                return Result.fail(Errors.validation(f"Unknown relationship key '{rel_key}'"))

            direction = "-[r{idx}]->" if spec.direction == "outgoing" else "<-[r{idx}]-"
            direction = direction.format(idx=idx)
            node_alias = f"n{idx}"

            match_parts.append(f"{direction}({node_alias}:{target_label})")

            # Add ordering expression for this level
            order_expr = (
                f"r{idx}.{spec.order_by_property}"
                if spec.order_by_property
                else f"{node_alias}.uid"
            )
            order_expressions.append(order_expr)

            return_parts.append(f"{node_alias}.uid AS uid{idx}")
            return_parts.append(f"{node_alias}.title AS title{idx}")

            if spec.include_edge_properties:
                edge_props = ", ".join(f"{p}: r{idx}.{p}" for p in spec.include_edge_properties)
                return_parts.append(f"{{{edge_props}}} AS edge{idx}")
            else:
                return_parts.append(f"properties(r{idx}) AS edge{idx}")

        # For simplicity, handle 1-2 levels explicitly
        # More complex hierarchies would need recursive CTEs
        if len(relationship_chain) == 1:
            rel_key, target_label = relationship_chain[0]
            spec = self.config.get_relationship_by_method(rel_key)
            if not spec:
                return Result.fail(Errors.validation(f"Unknown relationship key '{rel_key}'"))

            direction_clause = (
                "-[r]->"
                if spec.direction == "outgoing"
                else "<-[r]-"
                if spec.direction == "incoming"
                else "-[r]-"
            )

            order_clause = ""
            if spec.order_by_property:
                order_clause = f"ORDER BY r.{spec.order_by_property} {spec.order_direction}"

            query = f"""
            MATCH (root:{self.config.entity_label} {{uid: $entity_uid}}){direction_clause}(child:{target_label})
            WHERE type(r) = $rel_type
            RETURN child.uid AS uid,
                   child.title AS title,
                   properties(r) AS edge
            {order_clause}
            """

            params = {"entity_uid": entity_uid, "rel_type": spec.relationship.value}
            result = await self.backend.execute_query(query, params)

            if result.is_error:
                return Result.fail(result.expect_error())

            return Result.ok(
                [
                    {
                        "uid": str(record["uid"]),
                        "title": record.get("title"),
                        "edge": dict(record.get("edge", {})) if record.get("edge") else {},
                        "children": [],
                    }
                    for record in result.value
                    if record.get("uid")
                ]
            )

        elif len(relationship_chain) == 2:
            # Two-level hierarchy: LP → LS → KU
            rel_key1, target_label1 = relationship_chain[0]
            rel_key2, target_label2 = relationship_chain[1]

            spec1 = self.config.get_relationship_by_method(rel_key1)
            spec2 = self.config.get_relationship_by_method(rel_key2)

            if not spec1 or not spec2:
                return Result.fail(Errors.validation("Unknown relationship key in chain"))

            dir1 = "-[r1]->" if spec1.direction == "outgoing" else "<-[r1]-"
            dir2 = "-[r2]->" if spec2.direction == "outgoing" else "<-[r2]-"

            order1 = f"r1.{spec1.order_by_property}" if spec1.order_by_property else "n1.uid"

            query = f"""
            MATCH (root:{self.config.entity_label} {{uid: $entity_uid}}){dir1}(n1:{target_label1})
            WHERE type(r1) = $rel_type1
            OPTIONAL MATCH (n1){dir2}(n2:{target_label2})
            WHERE type(r2) = $rel_type2
            WITH n1, r1, collect({{uid: n2.uid, title: n2.title, edge: properties(r2)}}) AS children
            RETURN n1.uid AS uid,
                   n1.title AS title,
                   properties(r1) AS edge,
                   children
            ORDER BY {order1} {spec1.order_direction}
            """

            params = {
                "entity_uid": entity_uid,
                "rel_type1": spec1.relationship.value,
                "rel_type2": spec2.relationship.value,
            }

            result = await self.backend.execute_query(query, params)

            if result.is_error:
                return Result.fail(result.expect_error())

            return Result.ok(
                [
                    {
                        "uid": str(record["uid"]),
                        "title": record.get("title"),
                        "edge": dict(record.get("edge", {})) if record.get("edge") else {},
                        "children": [
                            {
                                "uid": str(c["uid"]) if c.get("uid") else None,
                                "title": c.get("title"),
                                "edge": dict(c.get("edge", {})) if c.get("edge") else {},
                            }
                            for c in (record.get("children") or [])
                            if c.get("uid")
                        ],
                    }
                    for record in result.value
                    if record.get("uid")
                ]
            )

        else:
            # For 3+ levels, use the dynamically built query parts
            # Build the full MATCH pattern
            full_match = "".join(match_parts)

            # Build relationship type parameters
            rel_types_params: dict[str, str] = {}
            for idx, (rel_key, _) in enumerate(relationship_chain):
                spec = self.config.get_relationship_by_method(rel_key)
                if spec is not None:
                    rel_types_params[f"rel_type{idx}"] = spec.relationship.value

            # Use the first order expression for top-level ordering
            order_clause = f"ORDER BY {order_expressions[0]}" if order_expressions else ""

            query = f"""
            MATCH {full_match}
            WHERE {" AND ".join(f"type(r{idx}) = $rel_type{idx}" for idx in range(len(relationship_chain)))}
            WITH *, {return_parts[0]} AS uid0
            RETURN {", ".join(return_parts)}
            {order_clause}
            """

            params = {"entity_uid": entity_uid, **rel_types_params}
            result = await self.backend.execute_query(query, params)

            if result.is_error:
                return Result.fail(result.expect_error())

            # For 3+ levels, return flat results (nested structure requires more complex handling)
            return Result.ok(
                [
                    {
                        "uid": str(record.get("uid0", "")),
                        "title": record.get("title0"),
                        "edge": dict(record.get("edge0", {})) if record.get("edge0") else {},
                        "children": [],  # Flat structure for 3+ levels
                    }
                    for record in result.value
                    if record.get("uid0")
                ]
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
            relationships = [
                (entity_uid, uid, spec.relationship.value, None) for uid in target_uids
            ]
            result = await self.backend.create_relationships_batch(relationships)

            if result.is_ok:
                total_created += result.value

        return Result.ok(total_created)

    # =========================================================================
    # CROSS-DOMAIN CONTEXT
    # =========================================================================

    @with_error_handling("get_cross_domain_context", error_type="database", uid_param="entity_uid")
    async def get_cross_domain_context(
        self,
        entity_uid: str,
        depth: int = 2,
        min_confidence: float = 0.7,
    ) -> Result[dict[str, Any]]:
        """
        Get complete cross-domain context for an entity with path-aware intelligence.

        This generic method replaces domain-specific context methods like:
        - get_task_cross_domain_context()
        - get_goal_cross_domain_context()

        Uses config.cross_domain_relationship_types and config.relationships
        to determine which relationships to query and how to categorize results.

        Args:
            entity_uid: Entity UID
            depth: Graph traversal depth (default 2)
            min_confidence: Minimum path confidence filter (default 0.7)

        Returns:
            Result containing rich context dictionary with path-aware entities
        """
        # Step 1: Get raw graph context from backend
        raw_result = await self.backend.get_domain_context_raw(
            entity_uid=entity_uid,
            entity_label=self.config.entity_label,
            relationship_types=self.config.cross_domain_relationship_types,
            depth=depth,
            min_confidence=min_confidence,
            bidirectional=len(self.config.bidirectional_relationships) > 0,
        )

        if raw_result.is_error:
            return Result.fail(raw_result.expect_error())

        raw_context = raw_result.value

        # Step 2: Categorize raw context using relationship definitions
        cross_domain_rels = [r for r in self.config.relationships if r.is_cross_domain_mapping]
        categorized: dict[str, list[dict]] = {
            rel.context_field_name: [] for rel in cross_domain_rels
        }

        for entity in raw_context:
            labels = entity.get("labels", [])
            via_rels = entity.get("via_relationships", [])

            for rel in cross_domain_rels:
                if rel.target_label in labels:
                    # Check if entity came via expected relationship
                    rel_value = rel.relationship.value
                    if (
                        rel_value in via_rels
                        or f"->{rel_value}" in via_rels
                        or f"<-{rel_value}" in via_rels
                    ):
                        categorized[rel.context_field_name].append(
                            {
                                "uid": entity.get("uid"),
                                "title": entity.get("title"),
                                "distance": entity.get("distance"),
                                "path_strength": entity.get("path_strength"),
                                "via_relationships": via_rels,
                            }
                        )
                        break  # Only add to one category

        # Step 3: Build response
        response = {f"{self.config.domain.value.rstrip('s')}_uid": entity_uid}
        response.update(categorized)

        return Result.ok(response)

    # =========================================================================
    # GRAPH INTELLIGENCE QUERIES
    # =========================================================================

    @requires_graph_intelligence("get_with_context")
    @with_error_handling("get_with_context", error_type="database", uid_param="uid")
    async def get_with_context(
        self,
        uid: str,
        depth: int = 2,
        intent: str | None = None,
    ) -> Result[tuple[Model, GraphContext]]:
        """
        Get entity with full graph context using intent-based traversal.

        Args:
            uid: Entity UID
            depth: Maximum graph traversal depth
            intent: Optional specific intent (uses config default if not provided)

        Returns:
            Result containing tuple of (Entity, GraphContext)
        """
        # Type narrowing: decorator @requires_graph_intelligence ensures this
        assert self.graph_intel is not None

        # Get entity
        get_method = getattr(self.backend, self._backend_get_method, None)
        if not get_method:
            return Result.fail(
                Errors.system(
                    message=f"Backend method '{self._backend_get_method}' not found",
                    operation="get_with_context",
                )
            )

        entity_result = await get_method(uid)
        if entity_result.is_error:
            return Result.fail(entity_result.expect_error())

        if not entity_result.value:
            return Result.fail(Errors.not_found(f"{self.config.entity_label} {uid} not found"))

        entity = self._context_to_domain_model(entity_result.value)

        # Get QueryIntent from config or parameter
        query_intent = (
            self.config.intent_mappings.get(intent, self.config.default_context_intent)
            if intent
            else self.config.default_context_intent
        )

        # Execute through graph intelligence service
        graph_context_result = await self.graph_intel.query_with_intent(
            domain=self._domain,
            node_uid=uid,
            intent=query_intent,
            depth=depth,
        )

        if graph_context_result.is_error:
            return Result.fail(graph_context_result.expect_error())

        self.logger.info(
            f"Retrieved {self.config.entity_label} {uid} with graph context: "
            f"{graph_context_result.value.total_nodes} nodes, "
            f"{graph_context_result.value.total_relationships} relationships "
            f"(intent={query_intent.value})"
        )

        return Result.ok((entity, graph_context_result.value))

    @requires_graph_intelligence("get_completion_impact")
    @with_error_handling("get_completion_impact", error_type="database", uid_param="uid")
    async def get_completion_impact(
        self,
        uid: str,
    ) -> Result[dict[str, Any]]:
        """
        Analyze impact of completing this entity using graph intelligence.

        Args:
            uid: Entity UID

        Returns:
            Result containing completion impact analysis
        """
        # Type narrowing: decorator @requires_graph_intelligence ensures this
        assert self.graph_intel is not None

        # Get entity
        get_method = getattr(self.backend, self._backend_get_method, None)
        if get_method is None:
            return Result.fail(
                Errors.system(f"Backend method {self._backend_get_method} not found")
            )
        entity_result = await get_method(uid)
        if entity_result.is_error:
            return Result.fail(entity_result.expect_error())

        if not entity_result.value:
            return Result.fail(Errors.not_found(f"{self.config.entity_label} {uid} not found"))

        entity = self._context_to_domain_model(entity_result.value)

        # Execute through graph intelligence with HIERARCHICAL intent
        graph_context_result = await self.graph_intel.query_with_intent(
            domain=self._domain,
            node_uid=uid,
            intent=self.config.get_intent_for_operation("impact"),
            depth=GraphDepth.NEIGHBORHOOD,
        )

        if graph_context_result.is_error:
            return graph_context_result

        context = graph_context_result.value

        # Analyze impact across domains using scoring weights
        from core.models.enums import Domain

        impacted_goals = context.get_nodes_by_domain(Domain.GOALS)
        impacted_habits = context.get_nodes_by_domain(Domain.HABITS)
        unlocked_knowledge = context.get_nodes_by_domain(Domain.KNOWLEDGE)
        triggered_tasks = context.get_nodes_by_domain(Domain.TASKS)

        weights = self.config.scoring_weights
        impact_score = (
            len(impacted_goals) * weights.get("goals", 0.4)
            + len(impacted_habits) * weights.get("habits", 0.3)
            + len(unlocked_knowledge) * weights.get("knowledge", 0.2)
            + len(triggered_tasks) * weights.get("tasks", 0.1)
        )

        return Result.ok(
            {
                self.config.domain.value.rstrip("s"): entity,
                "completion_impact": {
                    "impact_score": impact_score,
                    "impacted_goals": impacted_goals,
                    "impacted_habits": impacted_habits,
                    "unlocked_knowledge": unlocked_knowledge,
                    "triggered_tasks": triggered_tasks,
                },
                "graph_context": context,
                "performance_metrics": {
                    "query_time_ms": context.neo4j_query_time_ms,
                    "total_impacted_entities": context.total_nodes,
                },
            }
        )

    # =========================================================================
    # SEMANTIC RELATIONSHIP METHODS
    # =========================================================================

    async def get_with_semantic_context(
        self,
        uid: str,
        min_confidence: float = 0.8,
        semantic_types: list[SemanticRelationshipType] | None = None,
    ) -> Result[dict[str, Any]]:
        """
        Get entity with semantic knowledge relationships.

        Args:
            uid: Entity UID
            min_confidence: Minimum confidence threshold
            semantic_types: Optional override of semantic types (uses config default)

        Returns:
            Result containing entity with semantic context
        """
        if not self.semantic_helper:
            return Result.fail(
                Errors.validation(f"Semantic helper not enabled for {self.config.entity_label}")
            )

        types_to_use = semantic_types or self.config.semantic_types

        result = await self.semantic_helper.get_with_semantic_context(
            uid=uid,
            semantic_types=types_to_use,
            min_confidence=min_confidence,
        )

        if result.is_error:
            return result

        # Rename 'entity' key to domain-specific name for backward compatibility
        data = result.value
        entity_key = self.config.domain.value.rstrip("s")
        data[entity_key] = data.pop("entity", None)

        return Result.ok(data)

    async def create_semantic_relationship(
        self,
        from_uid: str,
        to_uid: str,
        semantic_type: SemanticRelationshipType,
        confidence: float = 0.9,
        notes: str | None = None,
    ) -> Result[dict[str, Any]]:
        """
        Create a semantic relationship between entity and knowledge.

        Args:
            from_uid: Source entity UID
            to_uid: Target knowledge UID
            semantic_type: Type of semantic relationship
            confidence: Confidence score (0-1)
            notes: Optional notes

        Returns:
            Result containing the created semantic triple
        """
        if not self.semantic_helper:
            return Result.fail(
                Errors.validation(f"Semantic helper not enabled for {self.config.entity_label}")
            )

        result = await self.semantic_helper.create_semantic_relationship(
            from_uid=from_uid,
            to_uid=to_uid,
            semantic_type=semantic_type,
            confidence=confidence,
            notes=notes,
        )

        if result.is_error:
            return result

        # Rename keys for backward compatibility
        data = result.value
        entity_key = f"{self.config.domain.value.rstrip('s')}_uid"
        return Result.ok(
            {
                entity_key: data["from_uid"],
                "knowledge_uid": data["to_uid"],
                "semantic_type": data["semantic_type"],
                "confidence": data["confidence"],
                "triple": data,
            }
        )

    async def find_by_semantic_filter(
        self,
        target_uid: str,
        min_confidence: float = 0.8,
        semantic_types: list[SemanticRelationshipType] | None = None,
        direction: str = "incoming",
    ) -> Result[list[Model]]:
        """
        Find entities by semantic relationship filter.

        Args:
            target_uid: Target knowledge UID to filter by
            min_confidence: Minimum confidence threshold
            semantic_types: Semantic types to filter by (uses config default)
            direction: Relationship direction ("incoming" or "outgoing")

        Returns:
            Result containing list of matching entities
        """
        if not self.semantic_helper:
            return Result.fail(
                Errors.validation(f"Semantic helper not enabled for {self.config.entity_label}")
            )

        types_to_use = semantic_types or self.config.semantic_types

        return await self.semantic_helper.find_by_semantic_filter(
            target_uid=target_uid,
            semantic_types=types_to_use,
            min_confidence=min_confidence,
            direction=direction,
        )

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
    # PATH-AWARE CONTEXT
    # =========================================================================
    # These methods provide typed path-aware context using the factory.

    @with_error_handling(
        "get_cross_domain_context_typed", error_type="database", uid_param="entity_uid"
    )
    async def get_cross_domain_context_typed(
        self,
        entity_uid: str,
        depth: int = 2,
        min_confidence: float = 0.7,
    ) -> Result[Any]:
        """
        Get cross-domain context with path-aware typed entities.

        Returns domain-specific context types (TaskCrossContext, GoalCrossContext, etc.)
        with path-aware entities (PathAwareTask, PathAwareGoal, etc.).

        Args:
            entity_uid: Entity UID
            depth: Graph traversal depth
            min_confidence: Minimum path confidence

        Returns:
            Result containing typed cross-context object
        """
        from core.services.relationships.path_aware_factory import (
            create_cross_context,
            get_domain_from_label,
        )

        # Get raw cross-domain context
        raw_result = await self.get_cross_domain_context(entity_uid, depth, min_confidence)
        if raw_result.is_error:
            return raw_result

        raw_context = raw_result.value

        # Build category → domain mapping from config
        category_domain_map: dict[str, Any] = {}
        cross_domain_rels = [r for r in self.config.relationships if r.is_cross_domain_mapping]
        for rel in cross_domain_rels:
            target_domain = get_domain_from_label(rel.target_label)
            if target_domain:
                category_domain_map[rel.context_field_name] = target_domain

        # Extract categorized data (exclude uid field)
        uid_field = f"{self.config.domain.value.rstrip('s')}_uid"
        categorized_data = {
            k: v for k, v in raw_context.items() if k != uid_field and isinstance(v, list)
        }

        # Create typed context
        typed_context = create_cross_context(
            source_domain=self._domain,
            source_uid=entity_uid,
            categorized_data=categorized_data,
            category_domain_map=category_domain_map,
        )

        return Result.ok(typed_context)

    # =========================================================================
    # USER CONTEXT PLANNING METHODS
    # =========================================================================
    # These methods leverage UserContext (~240 fields) for personalized queries.

    @with_error_handling("get_actionable_for_user", error_type="database")
    async def get_actionable_for_user(
        self,
        context: UserContext,
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

    @with_error_handling("get_goal_aligned_for_user", error_type="database")
    async def get_goal_aligned_for_user(
        self,
        context: UserContext,
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

        except Exception:
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

        except Exception:
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

    def _is_urgent(self, entity: Model, context: UserContext) -> bool:
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
        context: UserContext,
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

    # =========================================================================
    # LIFE PATH RELATIONSHIP METHODS
    # "Everything flows toward the life path"
    # =========================================================================

    @with_error_handling("link_to_life_path", error_type="database")
    async def link_to_life_path(
        self,
        entity_uid: str,
        life_path_uid: str,
        contribution_type: str | None = None,
        contribution_score: float = 0.0,
        notes: str | None = None,
    ) -> Result[bool]:
        """
        Link entity to a user's designated life path via SERVES_LIFE_PATH.

        This creates the fundamental connection that answers: "How does this
        entity contribute to my life path?"

        Args:
            entity_uid: The entity UID (task, goal, habit, etc.)
            life_path_uid: The LP UID that is the user's life path
            contribution_type: How it contributes (direct, supporting, foundational)
            contribution_score: Initial contribution score (0.0-1.0)
            notes: Optional notes about the contribution

        Returns:
            Result[bool] indicating success

        Example:
            # Link a goal to user's life path
            await relationship_service.link_to_life_path(
                entity_uid="goal:learn-python",
                life_path_uid="lp:software-engineering",
                contribution_type="direct",
                contribution_score=0.8,
            )
        """
        from datetime import datetime

        properties: dict[str, Any] = {
            "linked_at": datetime.now(UTC).isoformat(),
            "contribution_score": contribution_score,
        }
        if contribution_type:
            properties["contribution_type"] = contribution_type
        if notes:
            properties["notes"] = notes

        # Create SERVES_LIFE_PATH relationship
        query = """
        MATCH (entity {uid: $entity_uid})
        MATCH (lp:Lp {uid: $life_path_uid})
        MERGE (entity)-[r:SERVES_LIFE_PATH]->(lp)
        SET r += $properties
        RETURN r IS NOT NULL AS success
        """

        params = {
            "entity_uid": entity_uid,
            "life_path_uid": life_path_uid,
            "properties": properties,
        }

        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []
        success = records[0].get("success", False) if records else False

        if success:
            self.logger.info(
                f"Linked {entity_uid} to life path {life_path_uid} "
                f"(contribution_type={contribution_type}, score={contribution_score})"
            )

        return Result.ok(success)

    @with_error_handling("get_life_path_contributors", error_type="database")
    async def get_life_path_contributors(
        self,
        life_path_uid: str,
        entity_types: list[str] | None = None,
        min_contribution_score: float = 0.0,
        limit: int = 50,
    ) -> Result[list[dict[str, Any]]]:
        """
        Get all entities serving a user's life path.

        Returns entities with their contribution metadata, sorted by
        contribution score descending.

        Args:
            life_path_uid: The LP UID that is the user's life path
            entity_types: Optional filter by entity types (e.g., ["Goal", "Habit"])
            min_contribution_score: Minimum contribution score filter
            limit: Maximum number of results

        Returns:
            Result with list of contributor dictionaries containing:
            - uid: Entity UID
            - labels: Entity labels (e.g., ["Goal"])
            - title: Entity title
            - contribution_type: How it contributes
            - contribution_score: Score (0.0-1.0)
            - linked_at: When link was created

        Example:
            contributors = await service.get_life_path_contributors(
                life_path_uid="lp:software-engineering",
                entity_types=["Goal", "Habit"],
                min_contribution_score=0.5,
            )
        """
        # Build entity type filter
        type_filter = ""
        if entity_types:
            labels = ":".join(entity_types)
            type_filter = f"AND (entity:{labels})"

        query = f"""
        MATCH (entity)-[r:SERVES_LIFE_PATH]->(lp:Lp {{uid: $life_path_uid}})
        WHERE r.contribution_score >= $min_score
        {type_filter}
        RETURN entity.uid AS uid,
               labels(entity) AS labels,
               entity.title AS title,
               entity.description AS description,
               r.contribution_type AS contribution_type,
               r.contribution_score AS contribution_score,
               r.linked_at AS linked_at,
               r.notes AS notes
        ORDER BY r.contribution_score DESC
        LIMIT $limit
        """

        params = {
            "life_path_uid": life_path_uid,
            "min_score": min_contribution_score,
            "limit": limit,
        }

        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return Result.fail(result.expect_error())

        contributors = [
            {
                "uid": record.get("uid"),
                "labels": record.get("labels", []),
                "title": record.get("title"),
                "description": record.get("description"),
                "contribution_type": record.get("contribution_type"),
                "contribution_score": record.get("contribution_score", 0.0),
                "linked_at": record.get("linked_at"),
                "notes": record.get("notes"),
            }
            for record in (result.value or [])
        ]

        self.logger.debug(f"Found {len(contributors)} contributors to life path {life_path_uid}")

        return Result.ok(contributors)

    @with_error_handling("calculate_contribution_score", error_type="database")
    async def calculate_contribution_score(
        self,
        entity_uid: str,
        life_path_uid: str,
    ) -> Result[dict[str, Any]]:
        """
        Calculate how much an entity contributes to a life path.

        Uses graph traversal to measure:
        1. Direct connection strength
        2. Indirect contributions via goals/habits
        3. Knowledge alignment with LP content
        4. Activity alignment (events, tasks practicing LP skills)

        Args:
            entity_uid: The entity UID
            life_path_uid: The LP UID

        Returns:
            Result with contribution analysis:
            - total_score: Overall contribution score (0.0-1.0)
            - direct_score: Direct SERVES_LIFE_PATH strength
            - indirect_score: Via related entities
            - knowledge_score: Knowledge alignment
            - activity_score: Activity alignment
            - breakdown: Detailed component breakdown

        Example:
            analysis = await service.calculate_contribution_score(
                entity_uid="goal:learn-python",
                life_path_uid="lp:software-engineering",
            )
            # Returns: {"total_score": 0.75, "direct_score": 0.8, ...}
        """
        # Query for direct connection
        direct_query = """
        MATCH (entity {uid: $entity_uid})-[r:SERVES_LIFE_PATH]->(lp:Lp {uid: $life_path_uid})
        RETURN r.contribution_score AS direct_score, r.contribution_type AS type
        """

        # Query for indirect connections via goals that serve LP
        indirect_query = """
        MATCH (entity {uid: $entity_uid})
        OPTIONAL MATCH (entity)-[:FULFILLS_GOAL|SUPPORTS_GOAL|CONTRIBUTES_TO_GOAL]->(g:Goal)
                       -[r:SERVES_LIFE_PATH]->(lp:Lp {uid: $life_path_uid})
        RETURN count(g) AS goal_count, avg(r.contribution_score) AS avg_goal_score
        """

        # Query for knowledge alignment with LP KUs
        knowledge_query = """
        MATCH (entity {uid: $entity_uid})
        OPTIONAL MATCH (entity)-[:REQUIRES_KNOWLEDGE|APPLIES_KNOWLEDGE|REINFORCES_KNOWLEDGE]->(ku:Ku)
                       <-[:HAS_STEP*1..3]-(lp:Lp {uid: $life_path_uid})
        RETURN count(DISTINCT ku) AS aligned_ku_count
        """

        params = {"entity_uid": entity_uid, "life_path_uid": life_path_uid}

        # Execute queries in parallel
        import asyncio

        direct_result, indirect_result, knowledge_result = await asyncio.gather(
            self.backend.execute_query(direct_query, params),
            self.backend.execute_query(indirect_query, params),
            self.backend.execute_query(knowledge_query, params),
        )

        # Parse results
        direct_score = 0.0
        contribution_type = None
        if direct_result.is_ok and direct_result.value:
            record = direct_result.value[0]
            direct_score = record.get("direct_score") or 0.0
            contribution_type = record.get("type")

        indirect_score = 0.0
        goal_count = 0
        if indirect_result.is_ok and indirect_result.value:
            record = indirect_result.value[0]
            goal_count = record.get("goal_count") or 0
            avg_score = record.get("avg_goal_score") or 0.0
            # Indirect contribution capped at 0.5, scaled by number of goals
            indirect_score = min(0.5, avg_score * min(goal_count, 3) / 3)

        knowledge_score = 0.0
        aligned_ku_count = 0
        if knowledge_result.is_ok and knowledge_result.value:
            record = knowledge_result.value[0]
            aligned_ku_count = record.get("aligned_ku_count") or 0
            # Knowledge alignment: each KU adds ~0.1, capped at 0.3
            knowledge_score = min(0.3, aligned_ku_count * 0.1)

        # Calculate total (weighted average)
        # Direct: 50%, Indirect: 30%, Knowledge: 20%
        total_score = direct_score * 0.5 + indirect_score * 0.3 + knowledge_score * 0.2

        return Result.ok(
            {
                "entity_uid": entity_uid,
                "life_path_uid": life_path_uid,
                "total_score": round(total_score, 3),
                "direct_score": round(direct_score, 3),
                "indirect_score": round(indirect_score, 3),
                "knowledge_score": round(knowledge_score, 3),
                "contribution_type": contribution_type,
                "breakdown": {
                    "direct_connection": direct_score > 0,
                    "contributing_goals": goal_count,
                    "aligned_knowledge_units": aligned_ku_count,
                },
            }
        )

    @with_error_handling("update_contribution_score", error_type="database")
    async def update_contribution_score(
        self,
        entity_uid: str,
        life_path_uid: str,
        new_score: float,
        contribution_type: str | None = None,
    ) -> Result[bool]:
        """
        Update the contribution score for an entity's life path relationship.

        Args:
            entity_uid: The entity UID
            life_path_uid: The LP UID
            new_score: New contribution score (0.0-1.0)
            contribution_type: Optional new contribution type

        Returns:
            Result[bool] indicating success
        """
        from datetime import datetime

        set_clauses = ["r.contribution_score = $new_score", "r.updated_at = $updated_at"]
        params: dict[str, Any] = {
            "entity_uid": entity_uid,
            "life_path_uid": life_path_uid,
            "new_score": max(0.0, min(1.0, new_score)),
            "updated_at": datetime.now(UTC).isoformat(),
        }

        if contribution_type:
            set_clauses.append("r.contribution_type = $contribution_type")
            params["contribution_type"] = contribution_type

        query = f"""
        MATCH (entity {{uid: $entity_uid}})-[r:SERVES_LIFE_PATH]->(lp:Lp {{uid: $life_path_uid}})
        SET {", ".join(set_clauses)}
        RETURN r IS NOT NULL AS success
        """

        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []
        success = records[0].get("success", False) if records else False

        if success:
            self.logger.info(
                f"Updated contribution score for {entity_uid} → {life_path_uid}: {new_score}"
            )

        return Result.ok(success)

    @with_error_handling("remove_life_path_link", error_type="database")
    async def remove_life_path_link(
        self,
        entity_uid: str,
        life_path_uid: str,
    ) -> Result[bool]:
        """
        Remove an entity's connection to a life path.

        Args:
            entity_uid: The entity UID
            life_path_uid: The LP UID

        Returns:
            Result[bool] indicating success
        """
        query = """
        MATCH (entity {uid: $entity_uid})-[r:SERVES_LIFE_PATH]->(lp:Lp {uid: $life_path_uid})
        DELETE r
        RETURN count(r) > 0 AS deleted
        """

        params = {"entity_uid": entity_uid, "life_path_uid": life_path_uid}

        result = await self.backend.execute_query(query, params)

        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []
        deleted = records[0].get("deleted", False) if records else False

        if deleted:
            self.logger.info(f"Removed life path link: {entity_uid} → {life_path_uid}")

        return Result.ok(deleted)
