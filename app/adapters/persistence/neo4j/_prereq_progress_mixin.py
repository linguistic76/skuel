"""
Prerequisite & Hierarchy Mixin
==============================

Prerequisite / hierarchy query operations (April 2026).

Provides:
    prerequisite_traversal: Traverse prerequisite relationships (typed models)
    hierarchy_query_raw: Get parents + children

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
    from core.ports.base_protocols import Direction


class _PrereqProgressMixin[T: DomainModelProtocol]:
    """
    Prerequisite/hierarchy query operations.

    Requires on concrete class:
        driver: AsyncDriver
        label: NeoLabel
    """

    if TYPE_CHECKING:
        driver: AsyncDriver
        label: NeoLabel
        entity_class: type[T]

    @safe_backend_operation("prerequisite_traversal")
    async def prerequisite_traversal(
        self,
        uid: str,
        relationship_types: builtins.list[str],
        depth: int = 3,
        direction: Direction = "outgoing",
    ) -> Result[builtins.list[T]]:
        """
        Traverse prerequisite relationships and return typed domain models.

        Record→model conversion happens here, below the hexagonal boundary —
        services receive ``entity_class`` instances, never raw records.

        Args:
            uid: Entity UID to start from
            relationship_types: Prerequisite relationship type strings
            depth: Maximum traversal depth
            direction: "outgoing" for prerequisites, "incoming" for enables

        Returns:
            Result[list[T]]: Traversed entities as domain models
        """
        from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node
        from adapters.persistence.neo4j.query.cypher import build_prerequisite_traversal_query

        cypher_query, params = build_prerequisite_traversal_query(
            label=self.label,
            uid=uid,
            relationship_types=relationship_types,
            depth=depth,
            direction=direction,
        )

        async with self.driver.session() as session:
            result = await session.run(cypher_query, params)
            records = await result.data()
        return Result.ok([from_neo4j_node(record["n"], self.entity_class) for record in records])

    @safe_backend_operation("hierarchy_query_raw")
    async def hierarchy_query_raw(
        self,
        uid: str,
    ) -> Result[builtins.list[dict[str, Any]]]:
        """
        Get hierarchical structure (parents + children) for an entity.

        Args:
            uid: Entity UID

        Returns:
            Result[list[dict]]: Records with "parents" and "children" keys
        """
        from adapters.persistence.neo4j.query.cypher import build_hierarchy_query

        cypher_query, params = build_hierarchy_query(
            label=self.label,
            uid=uid,
        )

        async with self.driver.session() as session:
            result = await session.run(cypher_query, params)
            return Result.ok(await result.data())
