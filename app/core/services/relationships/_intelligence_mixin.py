"""
Intelligence Mixin
==================

Graph intelligence, semantic relationship, and cross-domain context methods.

Provides:
    get_cross_domain_context: Complete cross-domain context with path-aware intelligence
    get_with_context: Entity with full graph context via intent-based traversal
    get_completion_impact: Impact analysis of completing an entity
    get_with_semantic_context: Entity with semantic knowledge relationships
    create_semantic_relationship: Create semantic relationship between entities
    find_by_semantic_filter: Find entities by semantic relationship filter
    get_cross_domain_context_typed: Typed cross-domain context with path-aware entities

Requires on concrete class:
    config, backend, logger, graph_intel, semantic_helper,
    _domain, _backend_get_method, _context_to_domain_model
    (set by UnifiedRelationshipService.__init__)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from core.constants import GraphDepth
from core.models.type_hints import EntityUID
from core.utils.decorators import requires_graph_intelligence, with_error_handling
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.infrastructure.relationships.semantic_relationships import SemanticRelationshipType
    from core.models.graph_context import GraphContext
    from core.models.protocols import DomainModelProtocol
    from core.models.relationship_registry import (
        DomainRelationshipConfig,
        UnifiedRelationshipDefinition,
    )
    from core.services.relationships.path_aware_factory import CrossContext

Model = TypeVar("Model", bound="DomainModelProtocol")


def _direction_matches(direction: str, rel_value: str, via_relationships: list[str]) -> bool:
    """Does a related node's incident edge match a mapping's relationship + direction?

    ``via_relationships`` carries center-relative markers (``->REL`` when the edge
    leaves the source, ``<-REL`` when it enters the source). At distance 1 the single
    edge is the one incident to the related node, so the marker encodes its direction
    exactly:

        outgoing mapping (source -> related)  ⟺ ``->REL``
        incoming mapping (related -> source)  ⟺ ``<-REL``
        both                                  ⟺ either

    Matching the wrong direction (the pre-fix behaviour accepted bare/``->``/``<-``
    indiscriminately) put incoming edges into outgoing buckets and vice versa.
    """
    outgoing = f"->{rel_value}"
    incoming = f"<-{rel_value}"
    if direction == "outgoing":
        return outgoing in via_relationships
    if direction == "incoming":
        return incoming in via_relationships
    # "both": either orientation of a direct edge qualifies.
    return outgoing in via_relationships or incoming in via_relationships


def _generic_label_last(rel: UnifiedRelationshipDefinition) -> bool:
    """Sort key putting catch-all ``Entity`` mappings AFTER label-specific ones.

    The categorization loop takes the FIRST matching mapping per entity (``break``).
    When several mappings share a relationship + direction but differ by target label
    — e.g. HABITS' incoming REINFORCES_HABIT splits into ``reinforcing_tasks`` (Task),
    ``reinforcing_events`` (Event), ``reinforcing_habits`` (Entity) — the generic
    ``Entity`` bucket matches every node (all nodes are ``:Entity``) and would swallow
    a Task/Event before its specific bucket is reached. Trying specific labels first
    (this key is ``False`` for them, ``True`` for ``Entity``; stable sort preserves
    config order within each group) routes each node to its most precise bucket.
    """
    return rel.target_label == "Entity"


class IntelligenceMixin:
    """
    Mixin providing graph intelligence, semantic, and cross-domain context methods.

    Requires on concrete class:
        config: DomainRelationshipConfig
        backend: Protocol-based backend
        logger: Logger instance
        graph_intel: GraphIntelligenceService (optional)
        semantic_helper: SemanticRelationshipLinker (optional)
        _domain: Domain value
        _backend_get_method: Backend get method name
        _context_to_domain_model: Conversion method
    """

    # Provided by UnifiedRelationshipService.__init__ — declared for mypy
    config: DomainRelationshipConfig
    backend: Any
    logger: Any
    graph_intel: Any | None
    semantic_helper: Any | None
    _domain: Any
    _backend_get_method: str

    def _context_to_domain_model(self, data: Any) -> Any:
        """Provided by shell — converts raw data to domain model."""
        ...

    # =========================================================================
    # CROSS-DOMAIN CONTEXT
    # =========================================================================

    @with_error_handling("get_cross_domain_context", error_type="database", uid_param="entity_uid")
    async def get_cross_domain_context(
        self,
        entity_uid: EntityUID,
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
        # Step 1: Get raw graph context from backend.
        #
        # Always traverse BOTH directions: categorization below is direction-aware
        # per cross-domain mapping (each mapping's `direction` is matched against the
        # edge actually incident to the related node), so the single query-wide
        # `bidirectional` flag no longer decides which mappings can populate. Fetching
        # only outgoing edges (the former `len(bidirectional_relationships) > 0` rule)
        # structurally starved every INCOMING mapping for outgoing-only configs — e.g.
        # HABITS_CONFIG's inspiring_principles / reinforcing_* buckets were always empty.
        raw_result = await self.backend.get_domain_context_raw(
            entity_uid=entity_uid,
            entity_label=self.config.entity_label,
            relationship_types=self.config.cross_domain_relationship_types,
            depth=depth,
            min_confidence=min_confidence,
            bidirectional=True,
        )

        if raw_result.is_error:
            return Result.fail(raw_result)

        raw_context = raw_result.value

        # Step 2: Categorize raw context using relationship definitions.
        #
        # An entity is bucketed into a mapping only when the edge INCIDENT to it (its
        # direct, distance-1 cross-domain edge) matches that mapping's relationship AND
        # direction. This is what makes the buckets mean what their consumers assume —
        # direct cross-domain relationships. Two failure modes this guards against,
        # both verified against the live graph (depth-2 over-inclusion was a real bug):
        #   * Direction: an OUTGOING mapping matches only `->REL`, an INCOMING mapping
        #     only `<-REL` (the marker is center-relative, so at distance 1 it encodes
        #     the edge direction exactly). The old code matched any of bare/`->`/`<-`,
        #     conflating "center has this edge" with "the related node has it".
        #   * Distance: only distance-1 nodes are categorized. At depth >= 2 the old
        #     guard matched on a HOP-1 edge marker (incident to center, not to the
        #     related node), so a 2-hop neighbour — or the source itself on a cycle
        #     (e.g. the canonical INSPIRES_HABIT <-> EMBODIES_PRINCIPLE pair) — leaked
        #     into a sibling bucket. The Cypher also excludes related == center.
        # Specific target labels before the catch-all "Entity" bucket, so the
        # first-match `break` routes each node to its most precise mapping (see
        # _generic_label_last). Stable sort preserves config order within each group.
        cross_domain_rels = sorted(
            (r for r in self.config.relationships if r.is_cross_domain_mapping),
            key=_generic_label_last,
        )
        categorized: dict[str, list[dict]] = {
            rel.context_field_name: [] for rel in cross_domain_rels
        }

        for entity in raw_context:
            # Direct cross-domain edges only; never the source entity itself.
            if entity.get("distance") != 1 or entity.get("uid") == entity_uid:
                continue

            labels = entity.get("labels", [])
            via_rels = entity.get("via_relationships", [])

            for rel in cross_domain_rels:
                if rel.target_label in labels and _direction_matches(
                    rel.direction, rel.relationship.value, via_rels
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
        response: dict[str, Any] = {f"{self.config.domain.value.rstrip('s')}_uid": entity_uid}
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
    ) -> Result[tuple[Any, GraphContext]]:
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
            return Result.fail(entity_result)

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
            return Result.fail(graph_context_result)

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
            return Result.fail(entity_result)

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
    ) -> Result[list[Any]]:
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
    # PATH-AWARE CONTEXT
    # =========================================================================

    @with_error_handling(
        "get_cross_domain_context_typed", error_type="database", uid_param="entity_uid"
    )
    async def get_cross_domain_context_typed(
        self,
        entity_uid: EntityUID,
        depth: int = 2,
        min_confidence: float = 0.7,
    ) -> Result[CrossContext]:
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
            return Result.fail(raw_result)

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
