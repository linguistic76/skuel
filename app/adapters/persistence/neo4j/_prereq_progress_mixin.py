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
from core.ports.query_types import PrerequisiteChainRow
from core.utils.error_boundary import safe_backend_operation
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    import builtins

    from neo4j import AsyncDriver, Record

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

        # Session-run chokepoint (Neo4jSessionRunner)
        async def _run_single(
            self, query: str, params: dict[str, Any] | None = None
        ) -> Record | None: ...

        async def _run_records(
            self, query: str, params: dict[str, Any] | None = None
        ) -> list[dict[str, Any]]: ...

        label: NeoLabel
        base_label: NeoLabel | None
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

        records = await self._run_records(cypher_query, params)
        return Result.ok([from_neo4j_node(record["n"], self.entity_class) for record in records])

    @safe_backend_operation("prerequisite_chain_with_distance")
    async def prerequisite_chain_with_distance(
        self,
        uid: str,
        relationship_types: builtins.list[str],
        depth: int = 3,
    ) -> Result[builtins.list[PrerequisiteChainRow]]:
        """
        Traverse the prerequisite chain and return each node with its hop distance.

        The distance-carrying sibling of :meth:`prerequisite_traversal`: uses a
        min-distance-deduped query so a node reachable by multiple paths appears
        once, at its nearest distance.

        Prerequisites are matched on the **base** label (``:Entity``) rather than
        the domain label, so a REQUIRES_KNOWLEDGE edge terminating at a Ku is
        included — not just PathStep→PathStep hops. Because the result is
        heterogeneous (Ku *and* PathStep), it is returned as a projected
        :class:`PrerequisiteChainRow` (uid/title/domain/entity_type/distance)
        rather than a single-type domain model — the chain read needs identity +
        distance, not full models, and mapping a Ku into a PathStep would fail
        the entity_type guard.

        Args:
            uid: Entity UID to start from
            relationship_types: Prerequisite relationship type strings (any may
                connect a hop — e.g. REQUIRES_STEP and REQUIRES_KNOWLEDGE)
            depth: Maximum traversal depth (1-10)

        Returns:
            Result[list[PrerequisiteChainRow]]: projected prerequisite rows,
            nearest-first.
        """
        from adapters.persistence.neo4j.query.cypher import build_prerequisite_chain_query

        cypher_query, params = build_prerequisite_chain_query(
            label=self.base_label or self.label,
            uid=uid,
            relationship_types=relationship_types,
            depth=depth,
        )

        records = await self._run_records(cypher_query, params)
        return Result.ok(
            [
                PrerequisiteChainRow(
                    uid=record["uid"],
                    title=record["title"] or "",
                    domain=record["domain"] or "",
                    entity_type=record["entity_type"] or "",
                    distance=int(record["distance"]),
                )
                for record in records
            ]
        )

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
