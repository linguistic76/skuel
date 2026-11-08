"""
Knowledge-Grounding Backend
===========================

Persistence side of Ku grounding, one set of statements for every source.

A source is an entity kind whose stored embedding ``KnowledgeGroundingService``
matches against the Ku vector index — a UserEntry (``EntryGroundingBackend``) or a
Task (``TaskGroundingBackend``). This base holds the four statements: which
entities still need a pass, the provenance-stamped ``APPLIES_KNOWLEDGE`` write, the
grounded stamp, and the ownership-scoped removal that records the owner's
rejection. A source names its label, its gate (the Cypher predicate over ``s``
that says which of its entities may ground) and the text the judge reads.

Freshness is HASH-based, not timestamp-based: an entity is pending when its
``grounded_text_hash`` differs from the ``embedding_text_hash`` the embedding
store wrote (ADR-074 §8). Comparing hashes sidesteps the temporal storage bug
class (isoformat-string vs Cypher-datetime comparisons across writers) and
mirrors the content-hash idempotency the embedding pipeline already uses.

Like PrereqCandidateBackend, this takes a Neo4jQueryExecutor directly — it reads
across a source and Kus rather than serving one entity type's CRUD, and its one
edge write is a dedicated provenance writer rather than a registry-validated
``create_relationship`` call.

Protocol: core/ports/grounding_protocols.py KnowledgeGroundingBackendOperations
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar
from uuid import uuid4

from adapters.persistence.neo4j.query.cypher.crud_queries import build_publication_clause
from core.ports.query_types import (
    GroundingRemovalRow,
    GroundingSourceRow,
    to_grounding_source_rows,
)
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
    from core.models.enums.neo_labels import NeoLabel
    from core.models.type_hints import Neo4jProperties, UserUID


class KnowledgeGroundingBackend(ABC):
    """Candidate reads + eager provenance-stamped edge writes for one grounding source.

    Subclasses set ``label`` and ``content_expression`` and implement ``gate``.
    """

    #: The source's node label.
    label: ClassVar[NeoLabel]
    #: The Cypher expression over ``s`` for the text the judge reads.
    content_expression: ClassVar[str]

    def __init__(self, executor: Neo4jQueryExecutor) -> None:
        self._executor = executor

    @abstractmethod
    def gate(self) -> tuple[str, Neo4jProperties]:
        """The predicate over ``s`` that admits an entity to grounding, and its parameters."""

    async def get_pending(
        self,
        user_uid: str | None = None,
        force: bool = False,
        source_uid: str | None = None,
    ) -> Result[list[GroundingSourceRow]]:
        """Embedded entities the gate admits whose grounding stamp is missing or stale.

        Pending = ``grounded_text_hash`` absent or differing from the stored
        ``embedding_text_hash`` (the embedding changed since the last pass); ``force``
        sweeps every embedded entity the gate admits regardless of stamp.
        Ownership rides the canonical ``(User)-[:OWNS]->`` edge — the row's
        ``user_uid`` comes from the owner, and it is what the substance event carries.
        """
        gate, gate_params = self.gate()
        result = await self._executor.execute_query(
            f"""
            MATCH (owner:User)-[:OWNS]->(s:{self.label.value})
            WHERE {gate}
              AND s.embedding IS NOT NULL
              AND ($user_uid IS NULL OR owner.uid = $user_uid)
              AND ($source_uid IS NULL OR s.uid = $source_uid)
              AND ($force
                   OR s.grounded_text_hash IS NULL
                   OR s.grounded_text_hash <> coalesce(s.embedding_text_hash, ''))
            OPTIONAL MATCH (s)-[:APPLIES_KNOWLEDGE]->(k:Ku)
            WITH owner, s, [uid IN collect(k.uid) WHERE uid IS NOT NULL] AS applied
            RETURN s.uid AS uid,
                   owner.uid AS user_uid,
                   s.title AS title,
                   {self.content_expression} AS content,
                   s.embedding AS embedding,
                   coalesce(s.embedding_text_hash, '') AS embedding_text_hash,
                   applied AS applied_ku_uids,
                   coalesce(s.grounding_rejected_ku_uids, []) AS rejected_ku_uids
            ORDER BY datetime(s.created_at)
            """,
            {"user_uid": user_uid, "force": force, "source_uid": source_uid, **gate_params},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(to_grounding_source_rows(result.value or []))

    async def write_applies_knowledge(
        self, source_uid: str, ku_uid: str, confidence: float
    ) -> Result[bool]:
        """MERGE ``(s)-[:APPLIES_KNOWLEDGE {inferred, confidence, grounded_at}]->(ku)``.

        Returns True iff a NEW edge was created — the caller publishes the
        substance event only then. Provenance lands ON CREATE only, so an
        existing link the owner made is never re-stamped as inferred.
        ``confidence`` is the vector similarity; the MEGA-QUERY's
        ``coalesce(confidence, 1.0) >= $min_confidence`` filter applies to it with
        zero query changes.

        The Ku must be published (``build_publication_clause``): a draft is
        unfinished curriculum no learner is shown, so it is no one's applied
        knowledge — it matches nothing and writes nothing, like a Ku that is gone.

        The entity's write-lock is taken first (the ``_sg_lock`` sentinel), so this
        writer and the owner's link writer of one pair serialize on the entity and
        exactly one of them creates the edge. A pair the owner removed
        (``grounding_rejected_ku_uids``) is refused under that lock, so a pass that
        read the entity before the removal cannot re-make it; so is an entity the
        gate does not admit at the write.
        """
        gate, gate_params = self.gate()
        published, published_params = build_publication_clause("k")
        result = await self._executor.execute_query(
            f"""
            MATCH (s:{self.label.value} {{uid: $source_uid}})
            SET s.`_sg_lock` = $lock_token
            REMOVE s.`_sg_lock`
            WITH s
            WHERE NOT $ku_uid IN coalesce(s.grounding_rejected_ku_uids, [])
              AND {gate}
            MATCH (k:Ku {{uid: $ku_uid}}) WHERE {published}
            MERGE (s)-[r:APPLIES_KNOWLEDGE]->(k)
            ON CREATE SET r.inferred = true,
                          r.confidence = $confidence,
                          r.grounded_at = datetime(),
                          r.grounding_created = true
            WITH r, coalesce(r.grounding_created, false) AS created
            REMOVE r.grounding_created
            RETURN created
            """,
            {
                "source_uid": source_uid,
                "ku_uid": ku_uid,
                "confidence": confidence,
                "lock_token": uuid4().hex,
                **gate_params,
                **published_params,
            },
        )
        if result.is_error:
            return Result.fail(result)
        rows = result.value or []
        if not rows:
            # The entity or the Ku is gone, the Ku is a draft, the owner removed
            # the pair, or the gate does not admit the entity at the write.
            return Result.ok(False)
        return Result.ok(bool(rows[0].get("created")))

    async def stamp_grounded(self, source_uid: str, text_hash: str, version: int) -> Result[None]:
        """Mark the entity's grounding pass complete for its current embedding text.

        ``grounded_at`` is provenance only — freshness comparisons use the hash pair
        (see module docstring). The stamp lands only on the entity the pass read:
        under its write-lock, the gate must still admit it and it must still store
        the embedding text ``text_hash`` names — an entity whose text changed
        meanwhile stays pending for its new text.
        """
        gate, gate_params = self.gate()
        result = await self._executor.execute_query(
            f"""
            MATCH (s:{self.label.value} {{uid: $source_uid}})
            SET s.`_sg_lock` = $lock_token
            REMOVE s.`_sg_lock`
            WITH s
            WHERE {gate}
              AND coalesce(s.embedding_text_hash, '') = $text_hash
            SET s.grounded_at = datetime(),
                s.grounded_text_hash = $text_hash,
                s.grounding_version = $version
            RETURN s.uid AS uid
            """,
            {
                "source_uid": source_uid,
                "text_hash": text_hash,
                "version": version,
                "lock_token": uuid4().hex,
                **gate_params,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(None)

    async def remove_grounded_edge(
        self, source_uid: str, ku_uid: str, user_uid: UserUID
    ) -> Result[GroundingRemovalRow | None]:
        """Ownership-scoped delete of an inferred edge + rejection record.

        The ``(User)-[:OWNS]->`` anchor makes the delete ownership-verified in one
        query. Only an edge the grounding pass inferred (``inferred``) is removed
        here: a link the owner made is removed where they made it. No match (not
        owned, edge absent, or the owner's) returns None so the route answers 404
        alike (never 403). The removed ku_uid is appended to
        ``grounding_rejected_ku_uids`` so a future grounding pass (including
        ``--force``) never re-infers the pair or double-counts its substance event;
        the returned confidence is calibration data.
        """
        result = await self._executor.execute_query(
            f"""
            MATCH (u:User {{uid: $user_uid}})-[:OWNS]->(s:{self.label.value} {{uid: $source_uid}})
                  -[r:APPLIES_KNOWLEDGE]->(k {{uid: $ku_uid}})
            WHERE coalesce(r.inferred, false)
            WITH s, k, r.confidence AS confidence, r
            DELETE r
            SET s.grounding_rejected_ku_uids =
                [x IN coalesce(s.grounding_rejected_ku_uids, []) WHERE x <> $ku_uid] + $ku_uid
            RETURN k.uid AS ku_uid, confidence
            """,
            {"user_uid": user_uid, "source_uid": source_uid, "ku_uid": ku_uid},
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
            )
        )
