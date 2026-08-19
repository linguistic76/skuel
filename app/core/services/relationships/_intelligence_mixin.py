"""
Intelligence Mixin
==================

Graph intelligence, semantic relationship, and cross-domain context methods.

Provides:
    get_cross_domain_context: Complete cross-domain context with path-aware intelligence
    get_with_context: Entity with full graph context via intent-based traversal
    create_semantic_relationship: Create semantic relationship between entities
    find_by_semantic_filter: Find entities by semantic relationship filter
    get_cross_domain_context_typed: Typed cross-domain context with path-aware entities

Requires on concrete class:
    config, backend, logger, graph_intel, semantic_helper,
    _domain, _context_to_domain_model
    (set by UnifiedRelationshipService.__init__)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from core.models.type_hints import EntityUID, Neo4jProperties
from core.ports.base_protocols import BackendOperations
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


def _incident_matches(
    mapping_direction: str,
    mapping_rel: str,
    incident_rel_type: str | None,
    incident_into_related: bool | None,
) -> bool:
    """Does the edge INCIDENT to a related node match a mapping's relationship + direction?

    Each related node is attributed by the LAST hop of its path — the edge incident to
    it — not by any edge in the path. ``incident_rel_type`` is that edge's type and
    ``incident_into_related`` is its orientation: ``True`` when it points INTO the node
    (the node is the relationship's object), ``False`` when it points OUT (the node is
    the subject). This holds at ANY distance, so ``depth`` genuinely controls how far
    transitive context reaches without mis-attributing nodes:

        outgoing mapping (source REL related; related is the object)  ⟺ into_related True
        incoming mapping (related REL source; related is the subject) ⟺ into_related False
        both                                                          ⟺ either orientation

    Using the incident edge (vs. matching any path edge against center-relative markers)
    is what kills the depth>=2 over-inclusion: a 2-hop node is bucketed by the edge
    actually touching it, never by the first hop that merely left the source.
    """
    if incident_rel_type != mapping_rel:
        return False
    if mapping_direction == "outgoing":
        return incident_into_related is True
    if mapping_direction == "incoming":
        return incident_into_related is False
    return True  # "both": orientation-agnostic


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


def _mapping_sort_key(rel: UnifiedRelationshipDefinition) -> tuple[bool, bool]:
    """Categorization order: property-FILTERED mappings first, then generic-label-last.

    Several mappings can share a relationship + direction and differ only by an edge
    property: GOALS' incoming SUPPORTS_GOAL splits into ``essential_habits`` /
    ``critical_habits`` / ``optional_habits`` (each ``filter_property="essentiality"``)
    plus the unfiltered ``contributing_habits`` catch-all. The first-match ``break`` means
    the catch-all would swallow every habit before a tier is reached, so filtered mappings
    (``filter_property is None`` → ``False``) must sort BEFORE the catch-all (``True``); an
    essential habit then lands in ``essential_habits`` and only un-tiered habits fall
    through to ``contributing_habits``. The second key preserves the existing
    generic-``Entity``-last routing (see _generic_label_last). Stable sort keeps config
    order within each group, and configs with no filtered mappings are unaffected (the
    first key is constant, so ordering collapses to _generic_label_last).
    """
    return (rel.filter_property is None, _generic_label_last(rel))


def _filter_matches(
    rel: UnifiedRelationshipDefinition,
    incident_rel_properties: Neo4jProperties | None,
) -> bool:
    """Does the incident edge satisfy a mapping's optional edge-property filter?

    Unfiltered mappings (``filter_property is None``) always match. A filtered mapping
    matches only when the incident edge carries the configured property value — e.g.
    ``essential_habits`` accepts a SUPPORTS_GOAL edge only when its
    ``essentiality`` property equals ``"essential"``. Paired with _mapping_sort_key
    (filtered-first), this partitions a shared relationship into its tier buckets.
    """
    if rel.filter_property is None:
        return True
    return (incident_rel_properties or {}).get(rel.filter_property) == rel.filter_value


class IntelligenceMixin[Ops: BackendOperations]:
    """
    Mixin providing graph intelligence, semantic, and cross-domain context methods.

    Requires on concrete class:
        config: DomainRelationshipConfig
        backend: Protocol-based backend
        logger: Logger instance
        graph_intel: GraphIntelligenceService (optional)
        semantic_helper: SemanticRelationshipLinker (optional)
        _domain: Domain value
        _context_to_domain_model: Conversion method
    """

    # Provided by UnifiedRelationshipService.__init__ — declared for mypy
    config: DomainRelationshipConfig
    backend: Ops
    logger: Any
    graph_intel: Any | None
    semantic_helper: Any | None
    _domain: Any

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

        ``depth`` is a genuine traversal knob: each related entity is bucketed by the
        edge INCIDENT to it (its last hop), so a node 2 hops out is attributed to the
        right relationship just like a direct neighbour — never to the first hop that
        merely left the source. Every bucket entry carries its ``distance``, so callers
        wanting direct-only context can filter on ``distance == 1``.

        Args:
            entity_uid: Entity UID
            depth: Graph traversal depth — how many hops of transitive context to
                include (default 2; depth=1 is direct connections only)
            min_confidence: Minimum path confidence filter (default 0.7)

        Returns:
            Result containing rich context dictionary with path-aware entities
        """
        # Step 1: Get raw graph context from backend.
        #
        # Always traverse BOTH directions: categorization below matches each mapping's
        # `direction` against the orientation of the edge incident to the related node,
        # so the single query-wide `bidirectional` flag no longer decides which mappings
        # can populate. Fetching only outgoing edges (the former
        # `len(bidirectional_relationships) > 0` rule) structurally starved every
        # INCOMING mapping for outgoing-only configs — e.g. HABITS_CONFIG's
        # inspiring_principles / reinforcing_* buckets were always empty.
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

        # Step 2: Categorize raw context by the edge INCIDENT to each related node.
        #
        # A node lands in a mapping's bucket iff its incident edge (the last hop) is the
        # mapping's relationship in the mapping's orientation — `incident_into_related`
        # True for OUTGOING mappings (the node is the object), False for INCOMING (the
        # node is the subject), either for "both" (see _incident_matches). This is what
        # makes `depth` correct: a 2-hop node is attributed by the edge actually touching
        # it, so transitive context is included WITHOUT the depth>=2 over-inclusion the
        # old center-relative-marker matching produced (a 2-hop neighbour — or the source
        # itself on a cycle, e.g. the canonical INSPIRES_HABIT <-> EMBODIES_PRINCIPLE
        # pair — used to leak into a sibling bucket). The Cypher excludes related == center.
        #
        # A node must ALSO satisfy a mapping's optional edge-property filter
        # (`filter_property`/`filter_value`, e.g. SUPPORTS_GOAL {essentiality} habit
        # tiers) — see _filter_matches. Mappings sort property-FILTERED first, then
        # specific target labels before the catch-all "Entity" bucket, so the first-match
        # `break` routes each node to its most precise mapping (see _mapping_sort_key).
        # Stable sort preserves config order within each group.
        cross_domain_rels = sorted(
            (r for r in self.config.relationships if r.is_cross_domain_mapping),
            key=_mapping_sort_key,
        )
        categorized: dict[str, list[dict]] = {
            rel.context_field_name: [] for rel in cross_domain_rels
        }

        for entity in raw_context:
            labels = entity.get("labels", [])
            incident_rel_type = entity.get("incident_rel_type")
            incident_into_related = entity.get("incident_into_related")
            incident_rel_properties = entity.get("incident_rel_properties")

            for rel in cross_domain_rels:
                if (
                    rel.target_label in labels
                    and _incident_matches(
                        rel.direction,
                        rel.relationship.value,
                        incident_rel_type,
                        incident_into_related,
                    )
                    and _filter_matches(rel, incident_rel_properties)
                ):
                    categorized[rel.context_field_name].append(
                        {
                            "uid": entity.get("uid"),
                            "title": entity.get("title"),
                            "distance": entity.get("distance"),
                            "path_strength": entity.get("path_strength"),
                            "via_relationships": entity.get("via_relationships", []),
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
        entity_result = await self.backend.get(uid)
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

        # Registry-source the edge vocabulary ONLY for the default-context traversal
        # (Convergence Phase 1, One Path Forward). With no explicit intent, the traversal
        # filters on this domain's `cross_domain_relationship_types` — the registry single
        # source of truth — instead of `query_with_intent`'s hard-coded `default` clause
        # that drifts (this is the route / `get_<domain>_with_context` path 2A converges).
        #
        # An EXPLICIT intent (e.g. "dependencies"/"practice") still selects its specific
        # hard-coded edge slice: collapsing those onto the full registry vocabulary would
        # surface unrelated nodes. Intent-as-shape over the registry set is a later phase.
        # See: /docs/roadmap/intent-traversal-registry-convergence.md
        relationship_types = self.config.cross_domain_relationship_types if intent is None else None

        # Execute through graph intelligence service.
        graph_context_result = await self.graph_intel.query_with_intent(
            domain=self._domain,
            node_uid=uid,
            intent=query_intent,
            depth=depth,
            relationship_types=relationship_types,
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

    # =========================================================================
    # SEMANTIC RELATIONSHIP METHODS
    # =========================================================================

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
