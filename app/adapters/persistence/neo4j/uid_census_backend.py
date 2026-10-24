"""
UID Census Backend — every node's uid, read for the uid grammar census
======================================================================

Read-only. Returns each node's labels and uid so ``scripts/uid_census.py``
(``./dev uid-census``) can read every uid in the graph against
``core/utils/uid_grammar.py``, and counts the nodes that carry no uid. For the
graph-health poller, ``read_breaches`` reads only the census's breaches — the
server filters by ``UID_PATTERN``, so a graph that fits sends back two zeros.
Nothing is written.

Like the telemetry-retention backend, it spans every label, so it takes a
``Neo4jQueryExecutor`` directly rather than extending ``UniversalNeo4jBackend``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.infrastructure.monitoring.uid_grammar_check import UidBreaches
from core.models.enums.neo_labels import NeoLabel
from core.utils.result_simplified import Result
from core.utils.uid_grammar import UID_PATTERN

if TYPE_CHECKING:
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor

# A uid that is not a string matches no pattern: `=~` gives null, read as outside.
_BREACHES = """
CALL () {
    MATCH (n) WHERE n.uid IS NOT NULL AND NOT coalesce(n.uid =~ $pattern, false)
    RETURN count(n) AS outside, collect({labels: labels(n), uid: n.uid})[..$sample] AS outside_sample
}
CALL () {
    MATCH (n) WHERE n.uid IS NOT NULL
    WITH n.uid AS uid, count(*) AS holders
    WHERE holders > 1
    RETURN count(uid) AS shared, collect(uid)[..$sample] AS shared_sample
}
RETURN outside, outside_sample, shared, shared_sample
"""


def _labelled(labels: list[str], uid: object) -> str:
    named = sorted(label for label in labels if label != NeoLabel.ENTITY.value)
    return f"{':'.join(named) or NeoLabel.ENTITY.value} {uid}"


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

    async def read_breaches(self, sample: int) -> Result[UidBreaches]:
        """How many uids are outside the grammar and how many two nodes hold, ``sample`` of each."""
        result = await self._executor.execute_query(
            _BREACHES, {"pattern": UID_PATTERN, "sample": sample}
        )
        if result.is_error:
            return Result.fail(result)
        row = result.value[0]
        return Result.ok(
            UidBreaches(
                outside=int(row["outside"]),
                shared=int(row["shared"]),
                outside_sample=tuple(
                    _labelled(entry["labels"], entry["uid"]) for entry in row["outside_sample"]
                ),
                shared_sample=tuple(str(uid) for uid in row["shared_sample"]),
            )
        )
