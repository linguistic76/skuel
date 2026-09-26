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

from adapters.persistence.neo4j.neo4j_mapper import (
    from_neo4j_node,
    to_neo4j_node,
    without_embedding_props,
)
from core.models.enums.entity_enums import EntityType
from core.models.relationship_names import RelationshipName
from core.models.type_hints import Neo4jProperties, UserUID
from core.ports.query_types import ExtractionTwinRow, VaultIdTaskRow, VaultRetiredTaskRow
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
        ``content`` — is refreshed from ``entry``, EXCEPT the embedding triple:
        ``embedding`` / ``embedding_model`` / ``embedding_updated_at`` (and the
        version + text hash beside them) belong to the embeddings writer and are
        dropped from the payload, so a re-sync never blanks a note's vector —
        the worker re-embeds only when the content hash changes (ADR-074 §8).
        Like ``create()``, the
        ``(User)-[:OWNS]->(entry)`` edge is MERGEd in the SAME statement when
        ``entry`` carries a ``user_uid``, so the node and its owner edge are
        never separable: UserEntry is ``OWNER_ONLY``, and a property-only entry
        answers property-scoped reads while vanishing from every
        :OWNS-traversing one. An unknown owner fails the upsert rather than
        persisting that shape.

        Backend: MERGE on the generic ``UserEntryBackend``.
        """
        # The model carries the embedding triple as None and the mapper keeps it as
        # an explicit null; under ``+=`` that null would REMOVE the stored vector on
        # every re-sync. Those properties have one writer — drop them here.
        node_data = without_embedding_props(to_neo4j_node(entry))
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
        CALL (n, owner) {{
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

    async def get_latest_copy_of_note(
        self, user_uid: UserUID, note_uid: str
    ) -> Result[Neo4jProperties | None]:
        """The newest frozen copy filed from a vault note: its uid + fingerprint.

        The vault door files a new copy of a ``status: submitted`` note only
        when the note's fingerprint differs from this row's — keyed on the
        copy's provenance (``submitted_from_uid``), never on an exercise
        lineage or the copy's live links (Submit & Share arc R9). Scoped to
        the owner's own copies. ``None`` when the note was never submitted.
        """
        query = f"""
        MATCH (:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(copy:Entity)
        WHERE copy.entity_type = $entry_type AND copy.submitted_from_uid = $note_uid
        RETURN copy.uid AS uid, copy.submission_fingerprint AS submission_fingerprint
        ORDER BY copy.created_at DESC
        LIMIT 1
        """
        result = await self.execute_query(
            query,
            {"user_uid": user_uid, "note_uid": note_uid, "entry_type": _USER_ENTRY},
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
        source_line_hash, vault_id, source_line (the base — the line verbatim
        as SKUEL last saw it, ``None`` on an edge not yet seeded). Used by
        VaultReconciler for outbound ID injection / status round-trip
        (ADR-070) and by UserEntryProcessingService as the input to both
        extraction dedup guards (Guard 2 hashes + Guard 3 semantic keys, R3).

        Source is :Entity-bound: :Content chunk shadows share their entity's
        uid (G13) and must never match here.
        """
        query = """
        MATCH (e:Entity)-[r:EXTRACTED_FROM]->(entry:UserEntry {uid: $entry_uid})
        RETURN e.uid AS entity_uid,
               e.title AS title,
               labels(e) AS labels,
               r.source_line_hash AS source_line_hash,
               r.vault_id AS vault_id,
               r.source_line AS source_line
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
                    "source_line": rec.get("source_line"),
                }
                for rec in (result.value or [])
            ]
        )

    # =========================================================================
    # VAULT RETIREMENT — the R4 grace record (ADR-070)
    # =========================================================================

    async def find_task_by_vault_id(
        self, user_uid: UserUID, vault_id: str
    ) -> Result[list[VaultIdTaskRow]]:
        """Every owned Task a 🆔 names: live ``EXTRACTED_FROM`` edges plus stamped tasks.

        Live rows first (an edge is the stronger fact), then tasks stamped
        ``retired_vault_id = $vault_id`` that hold no live edge for it. Both
        shapes are owner-scoped through ``:OWNS`` (ADR-085); the live shape
        additionally requires the edge's entry to be the user's own.
        """
        # The empty OPTIONAL MATCH collects one all-null map; it is dropped
        # BEFORE the stamped branch's ``NOT … IN`` — a list holding a null
        # makes that predicate null, which would silently discard every
        # stamped row.
        query = """
        MATCH (u:User {uid: $user_uid})
        OPTIONAL MATCH (u)-[:OWNS]->(live:Task)
              -[r:EXTRACTED_FROM {vault_id: $vault_id}]->(entry:UserEntry {user_uid: $user_uid})
        WITH u, [row IN collect({
            entity_uid: live.uid,
            tracked_entry_uid: entry.uid,
            source_line_hash: r.source_line_hash,
            source_line: r.source_line
        }) WHERE row.entity_uid IS NOT NULL] AS live_rows
        OPTIONAL MATCH (u)-[:OWNS]->(stamped:Task {retired_vault_id: $vault_id})
        WHERE NOT stamped.uid IN [row IN live_rows | row.entity_uid]
        WITH live_rows, [row IN collect({
            entity_uid: stamped.uid,
            tracked_entry_uid: null,
            source_line_hash: null,
            source_line: stamped.retired_source_line
        }) WHERE row.entity_uid IS NOT NULL] AS stamped_rows
        UNWIND live_rows + stamped_rows AS row
        RETURN row.entity_uid AS entity_uid,
               row.tracked_entry_uid AS tracked_entry_uid,
               row.source_line_hash AS source_line_hash,
               row.source_line AS source_line
        """
        result = await self.execute_query(query, {"user_uid": user_uid, "vault_id": vault_id})
        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            [
                {
                    "entity_uid": rec["entity_uid"],
                    "tracked_entry_uid": rec.get("tracked_entry_uid"),
                    "source_line_hash": rec.get("source_line_hash"),
                    "source_line": rec.get("source_line"),
                }
                for rec in (result.value or [])
            ]
        )

    async def list_vault_retired_tasks(
        self, user_uid: UserUID, retired_before: datetime
    ) -> Result[list[VaultRetiredTaskRow]]:
        """Every owned Task whose retirement stamp predates ``retired_before``.

        ``still_tracked`` says whether the task holds a live 🆔-bearing
        ``EXTRACTED_FROM`` edge into one of the user's entries — a task can be
        tracked from two notes, and losing one line is not losing the task.
        The comparison is DateTime against DateTime: the stamp was written by
        ``datetime()`` and the cutoff read from the same clock.
        """
        query = """
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(t:Task)
        WHERE t.retired_vault_id IS NOT NULL
          AND t.vault_line_retired_at < $retired_before
        RETURN t.uid AS entity_uid,
               t.retired_vault_id AS retired_vault_id,
               t.status AS status,
               EXISTS {
                   MATCH (t)-[r:EXTRACTED_FROM]->(:UserEntry {user_uid: $user_uid})
                   WHERE r.vault_id IS NOT NULL
               } AS still_tracked
        ORDER BY t.uid
        """
        result = await self.execute_query(
            query, {"user_uid": user_uid, "retired_before": retired_before}
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            [
                {
                    "entity_uid": rec["entity_uid"],
                    "retired_vault_id": rec["retired_vault_id"],
                    "status": rec.get("status"),
                    "still_tracked": bool(rec.get("still_tracked")),
                }
                for rec in (result.value or [])
            ]
        )

    async def clear_vault_retirement_stamps(
        self, user_uid: UserUID, stamps: list[tuple[str, str]]
    ) -> Result[int]:
        """Remove the three retirement stamps from each ``(task_uid, retired_vault_id)``.

        Keyed on the 🆔 as read: a task the sweep listed and a concurrent
        retirement re-stamped since is left alone, so its newer record is
        judged by a later sweep rather than erased by this one.
        """
        if not stamps:
            return Result.ok(0)
        query = """
        MATCH (u:User {uid: $user_uid})
        UNWIND $stamps AS stamp
        MATCH (u)-[:OWNS]->(t:Task {uid: stamp.uid, retired_vault_id: stamp.vault_id})
        REMOVE t.retired_vault_id, t.retired_source_line, t.vault_line_retired_at
        RETURN count(t) AS cleared
        """
        result = await self.execute_query(
            query,
            {
                "user_uid": user_uid,
                "stamps": [{"uid": uid, "vault_id": vault_id} for uid, vault_id in stamps],
            },
        )
        if result.is_error:
            return Result.fail(result)
        rows = result.value or []
        return Result.ok(int(rows[0]["cleared"]) if rows else 0)

    async def read_graph_clock(self) -> Result[datetime]:
        """The database's own ``datetime()``, as a timezone-aware Python datetime.

        The retirement stamps are written by ``datetime()`` inside their own
        statements, so the sweep's cutoff is read from the same clock — an
        application-clock cutoff would let modest skew make a retirement look
        older than the sync it happened in, and the grace would vanish.
        """
        result = await self.execute_query("RETURN datetime() AS now")
        if result.is_error:
            return Result.fail(result)
        rows = result.value or []
        if not rows or rows[0].get("now") is None:
            return Result.fail(Errors.database("read_graph_clock", "datetime() returned no row"))
        now = rows[0]["now"]
        # The driver hands back its own DateTime; ``to_native`` keeps the offset.
        return Result.ok(now.to_native() if not isinstance(now, datetime) else now)

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
