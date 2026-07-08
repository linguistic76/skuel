"""
Batch Chunking Backend
======================

Read Cypher for :Content chunk-regeneration candidate discovery, below the
hexagonal boundary. Builds the candidate query (with optional version-staleness
and uid filters) and runs it via the raw driver session.

Implements no port directly — ``BatchChunkingService`` holds one and delegates;
the dynamic query assembly is a persistence concern (ADR-044).

See: /docs/decisions/ADR-044-neo4j-committed-architectural-choice.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from core.ports.chunk_protocols import BatchChunkingCandidate

if TYPE_CHECKING:
    from neo4j import AsyncDriver


class BatchChunkingBackend:
    """Cypher backend for chunk-regeneration candidate reads."""

    def __init__(self, driver: AsyncDriver) -> None:
        self._driver = driver

    async def fetch_regeneration_candidates(
        self,
        parent_uids: list[str] | None,
        force: bool,
        current_version: str,
    ) -> list[BatchChunkingCandidate]:
        """Return :Content rows needing chunk regeneration.

        When ``force`` is False, a candidate is one with no chunks or at least
        one chunk whose ``chunking_version`` differs from ``current_version``.
        Row shape is fixed by the ``RETURN`` projection and matches
        ``BatchChunkingCandidate``.
        """
        if force:
            where_clause = ""
        else:
            where_clause = """
            AND (
                NOT EXISTS {(c)-[:HAS_CHUNK]->(:ContentChunk)}
                OR EXISTS {
                    MATCH (c)-[:HAS_CHUNK]->(stale:ContentChunk)
                    WHERE coalesce(stale.chunking_version, '') <> $current_version
                }
            )
            """

        uid_filter = "AND c.uid IN $parent_uids" if parent_uids is not None else ""

        query = f"""
        MATCH (c:Content)
        WHERE c.body IS NOT NULL AND c.body <> ''
        {uid_filter}
        {where_clause}
        OPTIONAL MATCH (parent:Entity)-[:HAS_CONTENT]->(c)
        RETURN c.uid AS uid, c.body AS body, c.format AS format,
               [l IN labels(parent) WHERE l <> 'Entity'][0] AS entity_label
        """

        params: dict[str, Any] = {"current_version": current_version}
        if parent_uids is not None:
            params["parent_uids"] = parent_uids

        async with self._driver.session() as session:
            result = await session.run(query, params)
            # boundary: Neo4j Record rows match BatchChunkingCandidate by the
            # RETURN projection above; cast narrows for typed consumers.
            return [cast("BatchChunkingCandidate", dict(record)) async for record in result]
