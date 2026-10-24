"""
UserEntry Content Enrichment Mixin
===================================

Journal processing context + enrichment reads.
Covers journal temporal/thematic/goal linking, path-step entry listings,
and the knowledge-notes grounding list (entries + their APPLIES_KNOWLEDGE
chips).

Consolidated from the legacy ``_SubmissionContentMixin`` into a single
standalone mixin (ADR-054).

Requires on concrete class:
    driver, label, logger, execute_query (from _SearchMixin)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.persistence.neo4j.query.cypher.crud_queries import build_publication_clause
from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.relationship_names import RelationshipName
from core.models.type_hints import Neo4jProperties, UserUID
from core.ports.query_types import (
    KnowledgeChip,
    KnowledgeEntryGroundingRow,
    to_knowledge_chips,
    to_knowledge_entry_grounding_rows,
)
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from neo4j import AsyncDriver

_USER_ENTRY = EntityType.USER_ENTRY.value


def _knowledge_chips_clause() -> tuple[str, dict[str, str]]:
    """The tail that collects entry ``e``'s knowledge links as ``chips``.

    One chip per ``APPLIES_KNOWLEDGE`` edge to a published Ku or PathStep (a
    draft is unfinished curriculum no learner is shown), ordered by edge
    confidence; a link the owner named has no ``confidence`` and sorts first
    (coalesced to 1.0). Leaves ``e`` and ``chips`` in scope. Shared by every
    reader that shows an entry's knowledge links, so they show the same set.
    """
    published, params = build_publication_clause("k")
    return (
        f"""
        OPTIONAL MATCH (e)-[r:{RelationshipName.APPLIES_KNOWLEDGE.value}]->(k:Entity)
        WHERE (k:{NeoLabel.KU.value} OR k:{NeoLabel.PATH_STEP.value}) AND {published}
        WITH e, r, k
        ORDER BY coalesce(r.confidence, 1.0) DESC, k.title
        WITH e, [c IN collect({{
            uid: k.uid,
            title: k.title,
            entity_type: k.entity_type,
            confidence: r.confidence,
            inferred: r.inferred
        }}) WHERE c.uid IS NOT NULL] AS chips
        """,
        params,
    )


class _UserEntryContentMixin:
    """Content enrichment operations for ``UserEntry``.

    See ``UserEntryBackend`` in ``backends/user_entry_backend.py`` for the
    composed class.
    """

    if TYPE_CHECKING:
        driver: AsyncDriver
        label: NeoLabel

        async def execute_query(
            self, query: str, params: dict[str, Any] | None = None
        ) -> Result[list[dict[str, Any]]]: ...

    # ========================================================================
    # CONTENT ENRICHMENT BACKEND METHODS
    # ========================================================================

    async def get_journal_processing_context(
        self, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Gather active-goal context for the enrichment pipeline.

        ADR-054 dismantled the rich-journal model, so the former recent-journal,
        topic, and mood-trend bundles read gone properties and were removed.
        Active goals remain the only live enrichment signal.
        """
        cypher = """
        MATCH (u:User {uid: $user_uid})
        OPTIONAL MATCH (u)-[:OWNS]->(g:Goal)
        WHERE g.status = 'active'
        RETURN {
            active_goals: collect({
                uid: g.uid,
                title: g.title,
                description: g.description
            })
        } as context
        """
        return await self.execute_query(cypher, {"user_uid": user_uid})

    async def get_vault_notes_for_context(
        self,
        user_uid: UserUID,
        limit: int = 8,
    ) -> Result[list[Neo4jProperties]]:
        """Vault-synced personal notes for the journal context digest.

        Returns the N most-recently-updated UserEntry nodes that carry a
        ``vault_file_path`` in their metadata — the marker stamped by the
        ingestion pipeline for entries that came in via vault sync.

        Only ``pipeline = 'knowledge'`` notes are returned — the developed files
        the user shares to teach SKUEL (the ``knowledge/`` doorway, plus
        frontmatter-consented ``je_pro/`` entries per the ADR-073 amendment).
        Notes marked ``private: true`` are excluded —
        this read feeds journal prompts, so it carries the companion-retrieval
        gate (canon P3); the owner's own surfaces still show private notes.
        Content is truncated to 300 chars so the digest stays compact.
        """
        cypher = """
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(e:Entity {entity_type: 'user_entry'})
        WHERE e.pipeline = 'knowledge'
          AND coalesce(e.private, false) = false
          AND e.metadata IS NOT NULL
          AND e.metadata CONTAINS '"vault_file_path"'
        RETURN e.title AS title, left(coalesce(e.content, ''), 300) AS snippet
        ORDER BY datetime(coalesce(e.updated_at, e.created_at)) DESC
        LIMIT $limit
        """
        return await self.execute_query(cypher, {"user_uid": user_uid, "limit": limit})

    async def get_exercise_entries_for_user(
        self,
        user_uid: UserUID,
        limit: int,
    ) -> Result[list[Neo4jProperties]]:
        """A user's exercise submissions — every turn-in, its exercise live or not.

        A turn-in is an entry carrying the turn-in snapshot
        (``turn_in_exercise_uid``) or a ``FULFILLS_EXERCISE`` edge; the
        snapshot keeps a turn-in in its author's history after the exercise
        is deleted (Submit & Share arc R12). Pipeline-agnostic: an
        AI-destined turn-in is as much an exercise submission as a
        teacher-review one. TEACHER_REVIEW entries with neither are kept for
        pre-edge legacy rows.
        """
        query = f"""
        MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(e:Entity {{entity_type: $entry_type}})
        WHERE e.turn_in_exercise_uid IS NOT NULL
           OR EXISTS((e)-[:{RelationshipName.FULFILLS_EXERCISE.value}]->())
           OR e.pipeline = 'teacher_review'
        RETURN e
        ORDER BY datetime(e.created_at) DESC
        LIMIT $limit
        """
        result = await self.execute_query(
            query,
            {"user_uid": user_uid, "entry_type": _USER_ENTRY, "limit": limit},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok([dict(record["e"]) for record in result.value])

    async def get_knowledge_entries_with_grounding(
        self,
        user_uid: UserUID,
        limit: int,
    ) -> Result[list[KnowledgeEntryGroundingRow]]:
        """Knowledge-pipeline entries with their knowledge-link chips.

        One row per ``pipeline: knowledge`` entry the user OWNS, newest first,
        each carrying its ``chips`` (``_knowledge_chips_clause``).
        """
        chips, chip_params = _knowledge_chips_clause()
        query = f"""
        MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(e:Entity {{entity_type: $entry_type}})
        WHERE e.pipeline = 'knowledge'
        {chips}
        RETURN e.uid AS uid, e.title AS title, e.created_at AS created_at, chips
        ORDER BY datetime(e.created_at) DESC
        LIMIT $limit
        """
        result = await self.execute_query(
            query,
            {"user_uid": user_uid, "entry_type": _USER_ENTRY, "limit": limit, **chip_params},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(to_knowledge_entry_grounding_rows(result.value))

    async def get_entry_knowledge_chips(
        self, entry_uid: str, user_uid: UserUID
    ) -> Result[list[KnowledgeChip]]:
        """One owned entry's knowledge-link chips (``_knowledge_chips_clause``).

        Anchored on the owner's ``OWNS`` edge: an entry the user does not own,
        or one that does not exist, has no chips (an empty list).
        """
        chips, chip_params = _knowledge_chips_clause()
        query = f"""
        MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(e:Entity {{uid: $entry_uid, entity_type: $entry_type}})
        {chips}
        RETURN chips
        """
        result = await self.execute_query(
            query,
            {
                "user_uid": user_uid,
                "entry_uid": entry_uid,
                "entry_type": _USER_ENTRY,
                **chip_params,
            },
        )
        if result.is_error:
            return Result.fail(result)
        rows = result.value or []
        return Result.ok(to_knowledge_chips(rows[0]["chips"]) if rows else [])

    async def get_entries_for_path_step(
        self,
        user_uid: UserUID,
        ps_uid: str,
        limit: int,
    ) -> Result[list[Neo4jProperties]]:
        """Entries for a path step via ``Interaction`` edges.

        ``exercise_uid`` / ``exercise_title`` come from the turn-in snapshot
        (the exchange key, so the "Exchange" link works after the exercise
        is deleted), the title preferring the live exercise's.
        """
        query = f"""
        MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(sub:Entity {{entity_type: $entry_type}})
        MATCH (i:Entity:Interaction)-[:{RelationshipName.RECORDS.value}]->(sub)
        MATCH (i)-[:{RelationshipName.INTERACTION_DURING.value}]->(ps:Entity {{uid: $ps_uid}})
        OPTIONAL MATCH (ex:Entity:Exercise {{uid: sub.turn_in_exercise_uid}})
        OPTIONAL MATCH (report:Entity)-[:{RelationshipName.REPORT_FOR.value}]->(sub)
        RETURN sub.uid AS uid, sub.title AS title, sub.status AS status,
               sub.created_at AS created_at, sub.turn_in_revision AS revision,
               coalesce(ex.uid, sub.turn_in_exercise_uid) AS exercise_uid,
               coalesce(ex.title, sub.turn_in_exercise_title) AS exercise_title,
               report.uid AS report_uid,
               report.assessment_outcome AS report_outcome
        ORDER BY datetime(sub.created_at) DESC
        LIMIT $limit
        """
        result = await self.execute_query(
            query,
            {
                "user_uid": user_uid,
                "ps_uid": ps_uid,
                "entry_type": _USER_ENTRY,
                "limit": limit,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok([dict(record) for record in result.value])
