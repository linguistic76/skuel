"""
UserEntry CRUD / Content Mixin
==============================

CRUD/query operations for the ``UserEntry`` domain — content substring search,
feedback-count joins, exercise-linked entry lookups, teacher feedback-state EMA.

Consolidated from the legacy ``_SubmissionCrudMixin`` into a single
standalone mixin (ADR-054).

Requires on concrete class:
    driver, label, logger, execute_query (from _SearchMixin)
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from adapters.persistence.neo4j.neo4j_mapper import from_neo4j_node, to_neo4j_node
from core.models.enums.entity_enums import EntityType
from core.models.relationship_names import RelationshipName
from core.models.type_hints import Neo4jProperties, UserUID
from core.ports.query_types import ExtractionTwinRow
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    import logging

    from neo4j import AsyncDriver, Record

    from core.models.enums.neo_labels import NeoLabel
    from core.models.user_entry.user_entry import UserEntry

_USER_ENTRY = EntityType.USER_ENTRY.value


class _UserEntryCrudMixin:
    """CRUD / content-search operations for ``UserEntry``.

    See ``UserEntryBackend`` in ``backends/user_entry_backend.py`` for the
    composed class.
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
        logger: logging.Logger
        entity_class: type[UserEntry]
        _create_labels: str
        default_filters: Neo4jProperties

        async def execute_query(
            self, query: str, params: dict[str, Any] | None = None
        ) -> Result[list[dict[str, Any]]]: ...

    # ------------------------------------------------------------------
    # Deterministic upsert (MERGE-on-uid)
    # ------------------------------------------------------------------

    async def upsert(self, entry: UserEntry) -> Result[UserEntry]:
        """Create-or-update a ``UserEntry`` keyed on its (caller-supplied) uid.

        Mirrors the bulk-ingestion MERGE-on-uid pattern
        (``bulk_upsert_backend.py``): re-syncing a vault note with a
        deterministic uid (e.g. ``ue:daily:2026-06-16``) updates the existing
        node in place rather than minting a duplicate.

        **Ownership is enforced atomically inside the MERGE.** The ``ON MATCH``
        write is gated on ``n.user_uid = $owner``, so a caller cannot overwrite
        a UserEntry that already belongs to someone else (deterministic uids are
        predictable, e.g. ``ue:daily:2026-06-16``). A mismatch returns not-found
        — 404-not-403, so we never leak that the uid is taken. Doing this in one
        statement (rather than a separate read + write) closes the TOCTOU race a
        preflight check leaves open: the ``Entity.uid`` uniqueness constraint
        (``Neo4jSchemaManager.sync_domain_indexes``) serializes concurrent
        MERGEs on the same uid, so the loser observes the winner's node and the
        ownership gate rejects it (Codex P2 on #317).

        ``created_at`` is preserved across re-syncs (set only ``ON CREATE``);
        every other property — including ``updated_at`` and the note body in
        ``content`` — is refreshed from ``entry``. Like ``create()``, the
        ``(User)-[:OWNS]->(entry)`` edge is MERGEd in the SAME statement when
        ``entry`` carries a ``user_uid``, so the node and its owner edge are
        never separable: UserEntry is ``OWNER_ONLY``, and a property-only entry
        answers property-scoped reads while vanishing from every
        :OWNS-traversing one. An unknown owner fails the upsert rather than
        persisting that shape.

        Backend: MERGE on the generic ``UserEntryBackend``.
        """
        node_data = to_neo4j_node(entry)
        node_data.update(self.default_filters)
        user_uid = node_data.get("user_uid")

        # ON MATCH must not clobber the original created_at — drop it from the
        # match-side payload so re-sync keeps the first-seen timestamp.
        on_match_props = {k: v for k, v in node_data.items() if k != "created_at"}

        # The owner edge rides in THIS statement, not a follow-up query, so the
        # node and its :OWNS edge cannot come apart. Two guards matter here:
        #   1. The owner is MATCHed up front, so an unknown owner aborts the
        #      whole upsert rather than leaving a property-only entry.
        #   2. The MERGE is inside a CALL subquery filtered on
        #      ``n.user_uid = owner.uid`` — the SAME gate the ON MATCH write
        #      uses. Without it, losing the ownership race would still hand the
        #      caller an :OWNS edge onto someone else's entry, which the
        #      edge-anchored faceted path reads as ownership.
        owner_match = ""
        owns_clause = ""
        owns_params: Neo4jProperties = {}
        if user_uid:
            owner_match = "MATCH (owner:User {uid: $owner})"
            owns_clause = f"""
        WITH n, owner
        CALL {{
          WITH n, owner
          WITH n, owner WHERE n.user_uid = owner.uid
          MERGE (owner)-[owns:{RelationshipName.OWNS.value}]->(n)
          ON CREATE SET
              owns.created_at = $owns_timestamp,
              owns.last_accessed = $owns_timestamp,
              owns.access_count = 0,
              owns.is_active = true
        }}"""
            owns_params = {"owns_timestamp": datetime.now().isoformat()}

        # ON CREATE stamps the owner from $props; ON MATCH only writes when the
        # existing owner matches $owner, else it is a no-op and `owned` is false.
        query = f"""
        {owner_match}
        MERGE (n:{self._create_labels} {{uid: $uid}})
          ON CREATE SET n = $props
          ON MATCH SET n += (CASE WHEN n.user_uid = $owner THEN $on_match_props ELSE {{}} END)
        {owns_clause}
        RETURN n, coalesce(n.user_uid = $owner, false) AS owned
        """

        record = await self._run_single(
            query,
            {
                "uid": node_data["uid"],
                "props": node_data,
                "on_match_props": on_match_props,
                "owner": user_uid,
                **owns_params,
            },
        )
        if not record:
            return Result.fail(Errors.database("upsert", f"Failed to upsert {self.label}"))
        if not record["owned"]:
            # A different user already owns this uid — reject without writing
            # and without leaking that it exists (404-not-403).
            return Result.fail(
                Errors.not_found(resource=str(self.label), identifier=str(node_data["uid"]))
            )
        upserted = from_neo4j_node(dict(record["n"]), self.entity_class)
        return Result.ok(upserted)

    # ------------------------------------------------------------------
    # Content search
    # ------------------------------------------------------------------

    async def search_entry_content(
        self,
        user_uid: UserUID,
        query_text: str,
        limit: int = 50,
    ) -> Result[list[Neo4jProperties]]:
        """Case-insensitive substring search across ``processed_content``."""
        cypher = f"""
        MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(s:Entity)
        WHERE s.entity_type = $entry_type
          AND s.processed_content IS NOT NULL
          AND toLower(s.processed_content) CONTAINS toLower($query)
        RETURN s
        ORDER BY s.created_at DESC
        LIMIT $limit
        """
        result = await self.execute_query(
            cypher,
            {
                "user_uid": user_uid,
                "entry_type": _USER_ENTRY,
                "query": query_text,
                "limit": limit,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["s"] for record in result.value or []])

    # ------------------------------------------------------------------
    # Feedback counts
    # ------------------------------------------------------------------

    async def get_entries_with_feedback_count(
        self,
        user_uid: UserUID,
        limit: int = 50,
    ) -> Result[list[Neo4jProperties]]:
        """List user entries enriched with teacher feedback counts."""
        query = f"""
        MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(s:Entity)
        WHERE s.entity_type = $entry_type
        OPTIONAL MATCH (fb:Entity {{entity_type: $report_type}})-[:{RelationshipName.REPORT_FOR.value}]->(s)
        WITH s, count(fb) AS feedback_count
        RETURN s.uid AS uid,
               s.title AS title,
               s.original_filename AS original_filename,
               s.status AS status,
               s.entity_type AS entity_type,
               s.created_at AS created_at,
               feedback_count
        ORDER BY s.created_at DESC
        LIMIT $limit
        """
        result = await self.execute_query(
            query,
            {
                "user_uid": user_uid,
                "limit": limit,
                "entry_type": _USER_ENTRY,
                "report_type": EntityType.ENTRY_REPORT.value,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    # ------------------------------------------------------------------
    # Exercise-linked lookups
    # ------------------------------------------------------------------

    async def count_entries_for_exercise(self, user_uid: UserUID, exercise_uid: str) -> Result[int]:
        """Count entries a user has submitted against an exercise."""
        query = """
        MATCH (target:Entity {uid: $exercise_uid})
        OPTIONAL MATCH (target)-[:REVISES_EXERCISE]->(orig:Entity {entity_type: 'exercise'})
        WITH COALESCE(orig, target) AS exercise
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(s:Entity)-[:FULFILLS_EXERCISE]->(exercise)
        WHERE s.entity_type = $entry_type
        RETURN count(s) AS count
        """
        result = await self.execute_query(
            query,
            {
                "user_uid": user_uid,
                "exercise_uid": exercise_uid,
                "entry_type": _USER_ENTRY,
            },
        )
        if result.is_error:
            return Result.fail(result)
        record = result.value[0] if result.value else {}
        return Result.ok(record.get("count", 0))

    async def get_first_entry_for_exercise(
        self, user_uid: UserUID, exercise_uid: str
    ) -> Result[Neo4jProperties | None]:
        """Earliest entry's uid + created_at for a user+exercise pair."""
        query = """
        MATCH (target:Entity {uid: $exercise_uid})
        OPTIONAL MATCH (target)-[:REVISES_EXERCISE]->(orig:Entity {entity_type: 'exercise'})
        WITH COALESCE(orig, target) AS exercise
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(s:Entity)-[:FULFILLS_EXERCISE]->(exercise)
        WHERE s.entity_type = $entry_type
        RETURN s.uid AS uid, s.created_at AS created_at
        ORDER BY s.created_at ASC
        LIMIT 1
        """
        result = await self.execute_query(
            query,
            {
                "user_uid": user_uid,
                "exercise_uid": exercise_uid,
                "entry_type": _USER_ENTRY,
            },
        )
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok(None)
        return Result.ok(result.value[0])

    async def get_latest_entry_for_exercise(
        self, user_uid: UserUID, exercise_uid: str
    ) -> Result[Neo4jProperties | None]:
        """Newest turn-in's uid + content for a user+exercise pair.

        The vault submit-signal branch compares the living file's content
        against this row to decide whether a new frozen copy is due — the
        copies themselves ARE the last-submitted state, so no separate
        hash bookkeeping exists to drift. Ordered by the edge's revision
        (the copy sequence), newest first.

        Deliberately the same root-lineage lens as ``_next_revision`` /
        ``count_entries_for_exercise``: a RevisedExercise target collapses
        to its root, and revision-cycle copies are visible here because
        ``create_with_exercise_link`` always anchors ``FULFILLS_EXERCISE``
        on the root. Dedup and revision numbering therefore agree on what
        "the last copy" means across a whole exercise lineage.
        """
        query = """
        MATCH (target:Entity {uid: $exercise_uid})
        OPTIONAL MATCH (target)-[:REVISES_EXERCISE]->(orig:Entity {entity_type: 'exercise'})
        WITH COALESCE(orig, target) AS exercise
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(s:Entity)-[r:FULFILLS_EXERCISE]->(exercise)
        WHERE s.entity_type = $entry_type
        RETURN s.uid AS uid, s.content AS content, r.revision AS revision
        ORDER BY r.revision DESC, s.created_at DESC
        LIMIT 1
        """
        result = await self.execute_query(
            query,
            {
                "user_uid": user_uid,
                "exercise_uid": exercise_uid,
                "entry_type": _USER_ENTRY,
            },
        )
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok(None)
        return Result.ok(result.value[0])

    async def get_exercise_for_entry(self, entry_uid: str) -> Result[str | None]:
        """Exercise UID linked via ``FULFILLS_EXERCISE``, if any."""
        query = """
        MATCH (s:Entity {uid: $entry_uid})-[:FULFILLS_EXERCISE]->(e:Entity)
        RETURN e.uid AS exercise_uid
        LIMIT 1
        """
        result = await self.execute_query(query, {"entry_uid": entry_uid})
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok(None)
        return Result.ok(result.value[0]["exercise_uid"])

    # ------------------------------------------------------------------
    # Teacher feedback EMA state
    # ------------------------------------------------------------------

    async def get_teacher_feedback_state(self, teacher_uid: str) -> Result[Neo4jProperties]:
        """Read feedback EMA state from User node for turnaround calibration."""
        query = """
        MATCH (u:User {uid: $teacher_uid})
        RETURN u.feedback_ema_hours AS feedback_ema_hours,
               u.feedback_sample_count AS feedback_sample_count,
               u.feedback_updated_at AS feedback_updated_at
        """
        result = await self.execute_query(query, {"teacher_uid": teacher_uid})
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok({})
        return Result.ok(result.value[0])

    async def get_extracted_entities_for_entry(
        self, entry_uid: str
    ) -> Result[list[dict[str, Any]]]:
        """Return extracted entity UIDs + EXTRACTED_FROM edge properties for a UserEntry.

        Returns a list of dicts with keys: entity_uid, title, labels,
        source_line_hash, vault_id. Used by VaultReconciler for outbound ID
        injection / status round-trip (ADR-070) and by
        UserEntryProcessingService as the input to both extraction dedup
        guards (Guard 2 hashes + Guard 3 semantic keys, R3).

        Source is :Entity-bound: :Content chunk shadows share their entity's
        uid (G13) and must never match here.
        """
        query = """
        MATCH (e:Entity)-[r:EXTRACTED_FROM]->(entry:UserEntry {uid: $entry_uid})
        RETURN e.uid AS entity_uid,
               e.title AS title,
               labels(e) AS labels,
               r.source_line_hash AS source_line_hash,
               r.vault_id AS vault_id
        """
        result = await self.execute_query(query, {"entry_uid": entry_uid})
        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            [
                {
                    "entity_uid": rec.get("entity_uid", ""),
                    "title": rec.get("title") or "",
                    "labels": rec.get("labels") or [],
                    "source_line_hash": rec.get("source_line_hash") or "",
                    "vault_id": rec.get("vault_id"),
                }
                for rec in (result.value or [])
            ]
        )

    async def get_user_active_extraction_twins(
        self, user_uid: UserUID, labels: list[str]
    ) -> Result[list[ExtractionTwinRow]]:
        """Return the user's OWNED, non-terminal entities of the given domain labels.

        Input to extraction dedup Guard 4 (cross-entry, F4): a checkbox/DSL line
        whose (label, normalized title) matches an ACTIVE owned entity merges
        into it instead of re-creating a node the F4 cleanup just deleted.
        Terminal entities (completed/cancelled/...) are excluded — re-typing a
        finished task's title is a legitimate new task, not a duplicate.

        Ordered oldest-first so the map builder's ``setdefault`` keeps the same
        winner the F4 fixer keeps (oldest ``created_at``).

        Source is :Entity-bound and excludes :Content chunk shadows (G13).
        """
        from core.models.enums.entity_enums import EntityStatus

        terminal = [s.value for s in EntityStatus if s.is_terminal()]
        query = """
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(e:Entity)
        WHERE NOT e:Content
          AND any(lb IN labels(e) WHERE lb IN $labels)
          AND NOT coalesce(e.status, '') IN $terminal
        RETURN e.uid AS entity_uid,
               e.title AS title,
               labels(e) AS labels
        ORDER BY e.created_at ASC
        """
        result = await self.execute_query(
            query, {"user_uid": user_uid, "labels": labels, "terminal": terminal}
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            [
                {
                    "entity_uid": rec.get("entity_uid", ""),
                    "title": rec.get("title") or "",
                    "labels": rec.get("labels") or [],
                }
                for rec in (result.value or [])
            ]
        )

    async def update_teacher_feedback_state(
        self, teacher_uid: str, properties: Neo4jProperties
    ) -> Result[bool]:
        """Write feedback EMA state to User node."""
        query = """
        MATCH (u:User {uid: $teacher_uid})
        SET u += $properties
        RETURN u.uid
        """
        result = await self.execute_query(
            query, {"teacher_uid": teacher_uid, "properties": properties}
        )
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.fail(Errors.not_found(resource="User", identifier=teacher_uid))
        return Result.ok(True)
