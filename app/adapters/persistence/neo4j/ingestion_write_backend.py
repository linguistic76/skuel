"""
Ingestion Write Backend
=======================

Entity/edge write Cypher for the ingestion pipeline, below the hexagonal
boundary. Distinct from ``IngestionBackend`` (which tracks ingestion *runs* via
the Result-based executor): this backend performs the actual graph writes/reads
during ingestion and intentionally uses the raw ``AsyncDriver.execute_query``
tuple API with **exception-based** error flow, matching how the ingestion
service and batch helpers already handle failures (try/except NEO4J_EXCEPTIONS).

Relationship types interpolated into queries are typed ``RelationshipName`` —
the enum is the injection-safety guarantee (MyPy rejects raw strings at the call
site). Node labels are still validated against ``ENTITY_CONFIGS`` by the caller —
never user input (the driver requires a ``LiteralString``, hence the pyright ignores).

See: /docs/decisions/ADR-044-neo4j-committed-architectural-choice.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from core.models.enums.neo_labels import NeoLabel
    from core.models.relationship_names import RelationshipName


class IngestionWriteBackend:
    """Raw-driver Cypher for ingestion entity/edge writes and existence checks."""

    def __init__(self, driver: AsyncDriver) -> None:
        self._driver = driver

    async def ingest_edge(
        self, from_uid: str, to_uid: str, rel_type: RelationshipName, props: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """MERGE a ``rel_type`` edge between two existing nodes; return matched rows.

        Empty result means one or both endpoints were not found. ``rel_type`` is a
        ``RelationshipName`` — the enum type makes the interpolation injection-safe
        (MyPy rejects raw strings at the call site).
        """
        # NOT :Content — the chunk store's shadow node shares its entity's
        # uid; an unguarded MERGE would duplicate the edge onto the shadow
        # (G13). Exclusion, not :Entity binding: edge endpoints may be
        # non-Entity labels (e.g. Group).
        query = f"""
        MATCH (a {{uid: $from_uid}}) WHERE NOT a:Content
        MATCH (b {{uid: $to_uid}}) WHERE NOT b:Content
        MERGE (a)-[r:{rel_type}]->(b)
        SET r += $props
        RETURN a.uid AS from_uid, b.uid AS to_uid, type(r) AS rel_type,
               CASE WHEN r.created_at = $props.created_at THEN true ELSE false END AS created
        """
        records, _, _ = await self._driver.execute_query(  # pyright: ignore[reportArgumentType, reportCallIssue]
            query,
            from_uid=from_uid,
            to_uid=to_uid,
            props=props,
        )
        return list(records)

    async def entity_exists(self, uid: str) -> bool:
        """True if a node with ``uid`` exists (:Content shadows excluded, G13)."""
        records, _, _ = await self._driver.execute_query(
            "MATCH (n {uid: $uid}) WHERE NOT n:Content RETURN n.uid", uid=uid
        )
        return bool(records)

    async def create_group_ownership(self, owner_uid: str, group_uid: str) -> None:
        """MERGE the (User)-[:OWNS]->(Group) edge (ADR-053)."""
        await self._driver.execute_query(
            """
            MATCH (u:User {uid: $owner_uid})
            MATCH (g:Group {uid: $group_uid})
            MERGE (u)-[:OWNS]->(g)
            """,
            owner_uid=owner_uid,
            group_uid=group_uid,
        )

    async def check_existing_entities(self, uids: list[str]) -> dict[str, bool]:
        """Map each uid → whether a node with that uid already exists."""
        result = await self._driver.execute_query(
            """
            UNWIND $uids AS uid
            OPTIONAL MATCH (n {uid: uid})
            WHERE NOT n:Content
            RETURN uid, n IS NOT NULL AS exists
            """,
            {"uids": uids},
        )
        return {record["uid"]: record["exists"] for record in result.records}

    async def find_existing_uids_for_label(self, label: NeoLabel, uids: list[str]) -> list[str]:
        """Return the subset of ``uids`` that exist as ``:label`` nodes.

        ``label`` is derived from ENTITY_CONFIGS (trusted), not user input.
        """
        records, _, _ = await self._driver.execute_query(  # pyright: ignore[reportArgumentType, reportCallIssue]
            f"UNWIND $uids AS uid MATCH (n:{label} {{uid: uid}}) RETURN n.uid AS uid",
            uids=list(uids),
        )
        return [r["uid"] for r in records]

    async def resolve_path_suffixes(
        self, suffixes: list[str], root_prefix: str | None
    ) -> list[dict[str, Any]]:
        """Resolve vault note path suffixes to entity uids via IngestionMetadata.

        The tracker stores canonical absolute paths, so a link target like
        ``/0design/delmad.md`` resolves with ``ENDS WITH``. ``root_prefix``
        scopes matches to one vault (a personal MOC must not resolve into the
        content vault on a shared basename). Edge-file rows (``edge:``-prefixed
        uid slot) are excluded — they map to relationships, not nodes.

        May return multiple rows per suffix (same basename in two folders);
        the caller picks a deterministic winner.
        """
        records, _, _ = await self._driver.execute_query(
            """
            UNWIND $suffixes AS suffix
            MATCH (s:IngestionMetadata)
            WHERE s.file_path ENDS WITH suffix
              AND ($root_prefix IS NULL OR s.file_path STARTS WITH $root_prefix)
              AND NOT s.entity_uid STARTS WITH 'edge:'
            RETURN suffix, s.entity_uid AS entity_uid, s.file_path AS file_path
            """,
            suffixes=list(suffixes),
            root_prefix=root_prefix,
        )
        return [dict(r) for r in records]

    async def refresh_moc_organizes(self, source_uid: str, target_uids: list[str]) -> int:
        """Make ``target_uids`` (in order) the complete set of the source's
        outgoing ORGANIZES edges.

        The one write of the MOC edge pass: stale edges (targets no longer
        linked in the body) are deleted, surviving/new edges are MERGEd, and
        ``order`` is refreshed from list position (0-based — same contract as
        the rel-config ``order_property`` machinery). An empty ``target_uids``
        drops every outgoing ORGANIZES edge (an emptied MOC body). Targets
        that don't exist as :Entity nodes are silently skipped by the MATCH —
        the caller decides whether unresolved links warrant warnings.

        Returns the number of ORGANIZES edges now present.
        """
        records, _, _ = await self._driver.execute_query(
            """
            MATCH (n:Entity {uid: $source_uid})
            OPTIONAL MATCH (n)-[stale:ORGANIZES]->(t:Entity)
            WHERE NOT t.uid IN $target_uids
            DELETE stale
            WITH DISTINCT n
            UNWIND range(0, size($target_uids) - 1) AS idx
            MATCH (target:Entity {uid: $target_uids[idx]})
            MERGE (n)-[r:ORGANIZES]->(target)
            SET r.order = idx
            RETURN count(r) AS edges
            """,
            source_uid=source_uid,
            target_uids=list(target_uids),
        )
        return int(records[0]["edges"]) if records else 0
