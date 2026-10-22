"""
UID Census Backend — every node's uid, read for the uid grammar census
======================================================================

Read-only. Returns each node's labels and uid so ``scripts/uid_census.py``
(``./dev uid-census``) can read every uid in the graph against
``core/utils/uid_grammar.py``, and counts the nodes that carry no uid. Nothing is
written.

Like the telemetry-retention backend, it spans every label, so it takes a
``Neo4jQueryExecutor`` directly rather than extending ``UniversalNeo4jBackend``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor


class UidCensusBackend:
    """Read every node's uid and labels, and count the nodes without one."""

    def __init__(self, executor: Neo4jQueryExecutor) -> None:
        self._executor = executor

    async def read_uids(self) -> Result[list[tuple[tuple[str, ...], str]]]:
        """``(labels, uid)`` for every node that has a uid, labels sorted."""
        result = await self._executor.execute_query(
            "MATCH (n) WHERE n.uid IS NOT NULL RETURN labels(n) AS labels, n.uid AS uid"
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok([(tuple(sorted(row["labels"])), str(row["uid"])) for row in result.value])

    async def count_uidless(self) -> Result[dict[tuple[str, ...], int]]:
        """How many nodes carry no uid, by their sorted labels."""
        result = await self._executor.execute_query(
            "MATCH (n) WHERE n.uid IS NULL RETURN labels(n) AS labels, count(n) AS n"
        )
        if result.is_error:
            return Result.fail(result)
        counts: dict[tuple[str, ...], int] = {}
        for row in result.value:
            key = tuple(sorted(row["labels"]))
            counts[key] = counts.get(key, 0) + int(row["n"])
        return Result.ok(counts)
