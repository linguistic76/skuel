"""
Context Query Mixin
===================

Registry-driven context queries (April 2026) — build entity +
graph-neighborhood context using the relationship registry.

Provides:
    context_query_raw: Registry-driven context query
    basic_context_query_raw: Basic 3-relationship context for entities
        not in the registry

Requires on concrete class:
    driver, label
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.protocols import DomainModelProtocol
from core.utils.error_boundary import safe_backend_operation
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    import builtins

    from neo4j import AsyncDriver

    from core.models.enums.neo_labels import NeoLabel


class _ContextQueryMixin[T: DomainModelProtocol]:
    """
    Context query operations.

    Requires on concrete class:
        driver: AsyncDriver
        label: NeoLabel
    """

    if TYPE_CHECKING:
        driver: AsyncDriver
        label: NeoLabel

    @safe_backend_operation("context_query_raw")
    async def context_query_raw(
        self,
        uid: str,
        *,
        include_relationships: builtins.list[str] | None = None,
        exclude_relationships: builtins.list[str] | None = None,
        default_confidence: float = 0.7,
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Registry-driven context query for entity with graph neighborhood.

        Args:
            uid: Entity UID
            include_relationships: Only include these context field names
            exclude_relationships: Exclude these context field names
            default_confidence: Minimum confidence threshold

        Returns:
            Result[list[dict]]: Records with entity and relationship collections
        """
        from adapters.persistence.neo4j.query.cypher.context_query_generator import (
            generate_context_query,
        )

        cypher_query, params = generate_context_query(
            entity_label=self.label,
            include_relationships=include_relationships,
            exclude_relationships=exclude_relationships,
            default_confidence=default_confidence,
        )
        params["uid"] = uid

        async with self.driver.session() as session:
            result = await session.run(cypher_query, params)
            return Result.ok(await result.data())

    @safe_backend_operation("basic_context_query_raw")
    async def basic_context_query_raw(
        self,
        uid: str,
        prereq_rels: str,
        min_confidence: float = 0.7,
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Basic 3-relationship context query for entities not in the registry.

        Args:
            uid: Entity UID
            prereq_rels: Pipe-separated prerequisite relationship types
            min_confidence: Minimum confidence threshold

        Returns:
            Result[list[dict]]: Records with n, prerequisites, enables, related
        """
        label = self.label
        query = f"""
        MATCH (n:{label} {{uid: $uid}})

        // Prerequisites (outgoing REQUIRES relationships)
        OPTIONAL MATCH (n)-[r1:{prereq_rels}]->(prereq:{label})
        WHERE coalesce(r1.confidence, 1.0) >= $min_confidence
        WITH n, collect(DISTINCT {{
            uid: prereq.uid,
            title: prereq.title,
            confidence: coalesce(r1.confidence, 1.0)
        }}) as prerequisites

        // Entities this enables (incoming relationships)
        OPTIONAL MATCH (enabled:{label})-[r2:{prereq_rels}]->(n)
        WHERE coalesce(r2.confidence, 1.0) >= $min_confidence
        WITH n, prerequisites, collect(DISTINCT {{
            uid: enabled.uid,
            title: enabled.title,
            confidence: coalesce(r2.confidence, 1.0)
        }}) as enables

        // Related entities (lateral connections)
        OPTIONAL MATCH (n)-[r3:RELATED_TO|SIMILAR_TO]-(related:{label})
        WHERE coalesce(r3.confidence, 1.0) >= $min_confidence * 0.8
        WITH n, prerequisites, enables, collect(DISTINCT {{
            uid: related.uid,
            title: related.title,
            confidence: coalesce(r3.confidence, 1.0)
        }}) as related

        RETURN n, prerequisites, enables, related
        """

        async with self.driver.session() as session:
            result = await session.run(query, {"uid": uid, "min_confidence": min_confidence})
            return Result.ok(await result.data())
