"""
Semantic Mixin
==============

Semantic relationship and graph analysis operations for domain backends.

Provides semantic relationship CRUD (create, delete, query by type, discover
bridges, infer transitive) and graph analysis (hub scores, foundational
knowledge, prerequisite chains, next steps, time-aware paths).

Requires on concrete class:
    execute_query, logger  (provided by UniversalNeo4jBackend)

See: /docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from adapters.persistence.neo4j._backend_helpers import _validate_rel_name, direction_clause
from adapters.persistence.neo4j.query.cypher import build_publication_clause
from core.models.enums.neo_labels import NeoLabel
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    import builtins
    import logging

    from core.infrastructure.relationships.semantic_relationships import (
        SemanticRelationshipType,
        SemanticTriple,
    )
    from core.models.type_hints import Neo4jProperties


class _SemanticMixin:
    """Semantic relationship and graph analysis operations.

    Domain backends that manage semantic relationships should add
    ``_SemanticMixin`` to their class bases.

    Requires on concrete class:
        execute_query: async (query, params) -> Result[list[dict]]
        logger: logging.Logger
    """

    if TYPE_CHECKING:
        logger: logging.Logger

        async def execute_query(
            self, query: str, params: dict[str, Any] | None = None
        ) -> Result[builtins.list[dict[str, Any]]]: ...

    # ========================================================================
    # SEMANTIC RELATIONSHIP OPERATIONS
    # ========================================================================

    async def create_semantic_relationship(
        self, triple: SemanticTriple
    ) -> Result[list[Neo4jProperties]]:
        """Persist a single semantic triple as a MERGE'd relationship.

        The triple (a domain object) is handed down from the service; the
        Cypher is authored here, below the hexagonal boundary (ADR-044).
        """
        from adapters.persistence.neo4j.query import build_semantic_merge

        query, params = build_semantic_merge(triple)
        return await self.execute_query(query, params)

    async def query_semantic_neighborhood(
        self,
        uid: str,
        semantic_types: list[SemanticRelationshipType],
        depth: int,
        min_confidence: float,
    ) -> Result[list[Neo4jProperties]]:
        """Query semantic neighborhood using build_semantic_context helper."""
        from adapters.persistence.neo4j.query import build_semantic_context

        query, params = build_semantic_context(
            node_uid=uid,
            semantic_types=semantic_types,
            depth=depth,
            min_confidence=min_confidence,
        )
        return await self.execute_query(query, params)

    async def delete_semantic_relationship(
        self,
        rel_name: str,
        subject_uid: str,
        object_uid: str,
        semantic_type: str | None = None,
    ) -> Result[list[Neo4jProperties]]:
        """Delete a semantic relationship between two entities.

        ``rel_name`` is the coarse ``RelationshipName`` edge type; pass
        ``semantic_type`` (the precise namespaced predicate) to delete only the
        edge with that meaning. Without it a targeted delete would remove every
        edge that shares the collapsed edge type between the two nodes (roadmap
        Phase 1). See ``build_semantic_merge``.
        """
        _validate_rel_name(rel_name)
        query = f"""
        MATCH (s:Entity {{uid: $subject_uid}})
              -[r:{rel_name}]->
              (o:Entity {{uid: $object_uid}})
        WHERE $semantic_type IS NULL OR r.semantic_type = $semantic_type
        DELETE r
        RETURN count(r) as deleted
        """
        return await self.execute_query(
            query,
            {
                "subject_uid": subject_uid,
                "object_uid": object_uid,
                "semantic_type": semantic_type,
            },
        )

    async def query_relationships_by_type(
        self,
        uid: str,
        rel_name: str,
        direction: Literal["outgoing", "incoming", "both"] = "both",
        semantic_type: str | None = None,
    ) -> Result[list[Neo4jProperties]]:
        """Find relationships by type and direction for an entity.

        ``rel_name`` is the coarse ``RelationshipName`` edge type; pass
        ``semantic_type`` to narrow to a single precise predicate that collapsed
        onto it (roadmap Phase 1).
        """
        _validate_rel_name(rel_name)
        pattern = f"(source){direction_clause(direction, 'r', rel_name)}(target)"

        query = f"""
        MATCH {pattern}
        WHERE source.uid = $uid
          AND ($semantic_type IS NULL OR r.semantic_type = $semantic_type)
        RETURN target, r,
               startNode(r).uid as subject_uid,
               endNode(r).uid as object_uid
        """
        return await self.execute_query(query, {"uid": uid, "semantic_type": semantic_type})

    async def discover_semantic_bridges(
        self, uid: str, target_domain: str | None, limit: int
    ) -> Result[list[Neo4jProperties]]:
        """Discover cross-domain semantic bridges via shared concepts."""
        # Discovery: the whole point is to surface entities in OTHER domains
        # that the caller never referenced — draft curriculum must not be one
        # of them. NULL-tolerant (#1006).
        published, published_params = build_publication_clause("target")
        query = f"""
        MATCH (source:Entity {{uid: $uid}})
        MATCH (source)-[r1]->(shared)
        MATCH (target:Entity)-[r2]->(shared)
        WHERE source.domain <> target.domain
        AND ($target_domain IS NULL OR target.domain = $target_domain)
        AND type(r1) = type(r2)
        AND {published}
        RETURN DISTINCT target,
               type(r1) as bridge_type,
               shared.uid as shared_concept,
               r1.confidence + r2.confidence as combined_confidence
        ORDER BY combined_confidence DESC
        LIMIT $limit
        """
        return await self.execute_query(
            query,
            {"uid": uid, "target_domain": target_domain, "limit": limit, **published_params},
        )

    async def infer_transitive_relationships(
        self, uid: str, limit: int
    ) -> Result[list[Neo4jProperties]]:
        """Infer potential relationships via transitive closure A->B->C => A->C."""
        query = """
        MATCH (source:Entity {uid: $uid})-[r1]->(intermediate)
              -[r2]->(target:Entity)
        WHERE NOT (source)-[]->(target)
        AND type(r1) = type(r2)
        RETURN DISTINCT target,
               type(r1) as inferred_type,
               intermediate.uid as via_uid,
               (r1.confidence * r2.confidence) as confidence
        ORDER BY confidence DESC
        LIMIT $limit
        """
        return await self.execute_query(query, {"uid": uid, "limit": limit})

    # ========================================================================
    # GRAPH ANALYSIS OPERATIONS
    # ========================================================================

    async def compute_hub_scores(self) -> Result[list[Neo4jProperties]]:
        """Compute and cache degree centrality hub scores on all Entity nodes."""
        query = """
        MATCH (ku:Entity)-[r]-(neighbor)
        WITH ku, count(r) as degree_centrality
        SET ku.hub_score = degree_centrality
        RETURN count(ku) as updated_count
        """
        return await self.execute_query(query, {})

    async def query_foundational_knowledge(
        self, domain: str | None, min_hub_score: int, limit: int
    ) -> Result[list[Neo4jProperties]]:
        """Query high-hub-score KUs (foundational concepts)."""
        # Discovery: an unanchored ranking of "foundational concepts" — a browse
        # surface, so draft curriculum is withheld. NULL-tolerant (#1006).
        published, published_params = build_publication_clause("ku")
        where_clauses = ["ku.hub_score >= $min_hub_score", published]
        if domain:
            where_clauses.append("ku.domain = $domain")
        where_clause = " AND ".join(where_clauses)

        query = f"""
        MATCH (ku:Entity)
        WHERE {where_clause}
        RETURN ku
        ORDER BY ku.hub_score DESC
        LIMIT $limit
        """
        params: dict[str, Any] = {
            "limit": limit,
            "min_hub_score": min_hub_score,
            **published_params,
        }
        if domain:
            params["domain"] = domain
        return await self.execute_query(query, params)

    async def find_prerequisite_chain(
        self, uid: str, depth: int, min_confidence: float
    ) -> Result[list[Neo4jProperties]]:
        """Find prerequisite chain using CypherGenerator helper."""
        from adapters.persistence.neo4j.query import build_simple_prerequisite_chain
        from core.models.relationship_names import RelationshipName

        query, params = build_simple_prerequisite_chain(
            node_uid=uid,
            node_label=NeoLabel.ENTITY,
            relationship_type=RelationshipName.REQUIRES_KNOWLEDGE.value,
            depth=depth,
            order="DESC",
            include_leaf_only=True,
            min_confidence=min_confidence,
        )
        return await self.execute_query(query, params)

    async def find_next_steps(self, uid: str, limit: int) -> Result[list[Neo4jProperties]]:
        """Find KUs that have this one as a prerequisite (incoming REQUIRES_KNOWLEDGE)."""
        from adapters.persistence.neo4j.query import build_relationship_traversal_query
        from core.models.relationship_names import RelationshipName

        query, params = build_relationship_traversal_query(
            source_uid=uid,
            relationship_type=RelationshipName.REQUIRES_KNOWLEDGE.value,
            target_label=NeoLabel.ENTITY,
            direction="incoming",
            limit=limit,
        )
        return await self.execute_query(query, params)
