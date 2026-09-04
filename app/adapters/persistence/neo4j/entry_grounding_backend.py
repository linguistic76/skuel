"""
Entry-Grounding Backend
=======================

Persistence side of entry→Ku grounding (Entry-Enrichment PR 3).

Serves ``EntryGroundingService``: which knowledge-pipeline UserEntries still
need a grounding pass, the provenance-stamped ``APPLIES_KNOWLEDGE`` write,
the per-entry grounded stamp, and the ownership-scoped removal that records
the user's rejection (threshold calibration data).

Freshness is HASH-based, not timestamp-based: an entry is pending when its
``grounded_text_hash`` differs from the ``embedding_text_hash`` the embedding
store wrote (ADR-074 §8). Comparing hashes sidesteps the temporal storage bug
class (isoformat-string vs Cypher-datetime comparisons across writers) and
mirrors the content-hash idempotency the embedding pipeline already uses.

Like PrereqCandidateBackend, this takes a Neo4jQueryExecutor directly — it
reads across UserEntries/Kus rather than serving one entity type's CRUD, and
its one edge write is a dedicated provenance writer (the
``create_extracted_from_links`` precedent) rather than a registry-validated
``create_relationship`` call.

Protocol: core/ports/user_entry_protocols.py EntryGroundingBackendOperations
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.ports.query_types import (
    GroundingEntryRow,
    GroundingRemovalRow,
    to_grounding_entry_rows,
)
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
    from core.models.type_hints import UserUID


class EntryGroundingBackend:
    """Candidate reads + eager provenance-stamped edge writes for grounding."""

    def __init__(self, executor: Neo4jQueryExecutor) -> None:
        self._executor = executor

    async def get_pending_entries(
        self, user_uid: str | None = None, force: bool = False
    ) -> Result[list[GroundingEntryRow]]:
        """Knowledge entries with an embedding whose grounding stamp is missing or stale.

        Pending = ``grounded_text_hash`` absent or differing from the stored
        ``embedding_text_hash`` (the embedding changed since the last pass);
        ``force`` sweeps every embedded knowledge entry regardless of stamp.
        Ownership rides the canonical ``(User)-[:OWNS]->`` edge — the entry's
        ``user_uid`` in the row comes from the owner, and it is what the
        substance event carries.
        """
        result = await self._executor.execute_query(
            """
            MATCH (owner:User)-[:OWNS]->(e:UserEntry {pipeline: 'knowledge'})
            WHERE NOT e:Content
              AND e.embedding IS NOT NULL
              AND ($user_uid IS NULL OR owner.uid = $user_uid)
              AND ($force
                   OR e.grounded_text_hash IS NULL
                   OR e.grounded_text_hash <> coalesce(e.embedding_text_hash, ''))
            OPTIONAL MATCH (e)-[:APPLIES_KNOWLEDGE]->(k:Ku)
            WITH owner, e, [uid IN collect(k.uid) WHERE uid IS NOT NULL] AS applied
            RETURN e.uid AS uid,
                   owner.uid AS user_uid,
                   e.title AS title,
                   coalesce(e.content, e.processed_content, '') AS content,
                   e.embedding AS embedding,
                   coalesce(e.embedding_text_hash, '') AS embedding_text_hash,
                   applied AS applied_ku_uids,
                   coalesce(e.grounding_rejected_ku_uids, []) AS rejected_ku_uids
            ORDER BY e.created_at
            """,
            {"user_uid": user_uid, "force": force},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(to_grounding_entry_rows(result.value or []))

    async def write_applies_knowledge(
        self, entry_uid: str, ku_uid: str, confidence: float
    ) -> Result[bool]:
        """MERGE ``(entry)-[:APPLIES_KNOWLEDGE {inferred, confidence, grounded_at}]->(ku)``.

        Returns True iff a NEW edge was created — the caller publishes the
        substance event only then. Provenance lands ON CREATE only, so an
        existing explicit edge (EXTRACT_ACTIVITIES ``@ku()`` reference) is
        never re-stamped as inferred. ``confidence`` is the vector similarity;
        the MEGA-QUERY's ``coalesce(entry_app_rel.confidence, 1.0) >=
        $min_confidence`` filter applies to it with zero query changes.
        """
        result = await self._executor.execute_query(
            """
            MATCH (e:UserEntry {uid: $entry_uid}) WHERE NOT e:Content
            MATCH (k:Ku {uid: $ku_uid}) WHERE NOT k:Content
            MERGE (e)-[r:APPLIES_KNOWLEDGE]->(k)
            ON CREATE SET r.inferred = true,
                          r.confidence = $confidence,
                          r.grounded_at = datetime(),
                          r.grounding_created = true
            WITH r, coalesce(r.grounding_created, false) AS created
            REMOVE r.grounding_created
            RETURN created
            """,
            {"entry_uid": entry_uid, "ku_uid": ku_uid, "confidence": confidence},
        )
        if result.is_error:
            return Result.fail(result)
        rows = result.value or []
        if not rows:
            # Entry or Ku vanished between the candidate read and the write.
            return Result.ok(False)
        return Result.ok(bool(rows[0].get("created")))

    async def stamp_grounded(self, entry_uid: str, text_hash: str, version: int) -> Result[None]:
        """Mark the entry's grounding pass complete for its current embedding text.

        ``grounded_at`` is provenance only — freshness comparisons use the
        hash pair (see module docstring).
        """
        result = await self._executor.execute_query(
            """
            MATCH (e:UserEntry {uid: $entry_uid}) WHERE NOT e:Content
            SET e.grounded_at = datetime(),
                e.grounded_text_hash = $text_hash,
                e.grounding_version = $version
            RETURN e.uid AS uid
            """,
            {"entry_uid": entry_uid, "text_hash": text_hash, "version": version},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(None)

    async def remove_grounded_edge(
        self, entry_uid: str, ku_uid: str, user_uid: UserUID
    ) -> Result[GroundingRemovalRow | None]:
        """Ownership-scoped edge delete + rejection record.

        The ``(User)-[:OWNS]->`` anchor makes the delete ownership-verified in
        one query — no match (not owned, or edge absent) returns None so the
        route can 404 (never 403). The removed ku_uid is appended to
        ``grounding_rejected_ku_uids`` so a future grounding pass (including
        ``--force``) never re-infers the pair or double-counts its substance
        event; the returned confidence/inferred pair is calibration data.
        """
        result = await self._executor.execute_query(
            """
            MATCH (u:User {uid: $user_uid})-[:OWNS]->(e:UserEntry {uid: $entry_uid})
                  -[r:APPLIES_KNOWLEDGE]->(k {uid: $ku_uid})
            WHERE NOT e:Content AND NOT k:Content
            WITH e, k, r.confidence AS confidence, coalesce(r.inferred, false) AS inferred, r
            DELETE r
            SET e.grounding_rejected_ku_uids =
                [x IN coalesce(e.grounding_rejected_ku_uids, []) WHERE x <> $ku_uid] + $ku_uid
            RETURN k.uid AS ku_uid, confidence, inferred
            """,
            {"user_uid": user_uid, "entry_uid": entry_uid, "ku_uid": ku_uid},
        )
        if result.is_error:
            return Result.fail(result)
        rows = result.value or []
        if not rows:
            return Result.ok(None)
        row = rows[0]
        raw_confidence = row.get("confidence")
        return Result.ok(
            GroundingRemovalRow(
                ku_uid=str(row.get("ku_uid") or ku_uid),
                confidence=float(raw_confidence) if raw_confidence is not None else None,
                inferred=bool(row.get("inferred")),
            )
        )
