"""
UserEntry Content Enrichment Mixin
===================================

Journal processing context + exercise-instruction enrichment reads.
Covers journal temporal/thematic/goal linking, exercise-instruction
set CRUD, path-step entry listings, and the knowledge-notes grounding
list (entries + their APPLIES_KNOWLEDGE chips).

Consolidated from the legacy ``_SubmissionContentMixin`` into a single
standalone mixin (ADR-054).

Requires on concrete class:
    driver, label, logger, execute_query (from _SearchMixin)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.enums.entity_enums import EntityType
from core.models.relationship_names import RelationshipName
from core.models.type_hints import Neo4jProperties, UserUID
from core.ports.query_types import KnowledgeEntryGroundingRow, to_knowledge_entry_grounding_rows
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from core.models.enums.neo_labels import NeoLabel

_USER_ENTRY = EntityType.USER_ENTRY.value


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

    async def load_exercise_instructions(self, uid: str) -> Result[list[Neo4jProperties]]:
        """Load formatting instructions from an Exercise entity node."""
        query = """
        MATCH (i:Entity {uid: $uid, entity_type: 'exercise'})
        RETURN i.instructions as instructions, i.name as name
        """
        return await self.execute_query(query, {"uid": uid})

    async def create_exercise_instruction_set(
        self, uid: str, name: str, instructions: str
    ) -> Result[list[Neo4jProperties]]:
        """Create a new Exercise instruction set node."""
        query = """
        CREATE (i:Entity:Exercise {
            uid: $uid,
            name: $name,
            entity_type: 'exercise',
            instructions: $instructions,
            created_at: datetime(),
            char_count: size($instructions)
        })
        RETURN i
        """
        return await self.execute_query(
            query, {"uid": uid, "name": name, "instructions": instructions}
        )

    async def list_exercise_instruction_sets(self) -> Result[list[Neo4jProperties]]:
        """List all available exercise instruction sets."""
        query = """
        MATCH (i:Entity {entity_type: 'exercise'})
        RETURN i.uid as uid, i.name as name, i.char_count as char_count
        ORDER BY i.name
        """
        return await self.execute_query(query)

    async def get_vault_notes_for_context(
        self,
        user_uid: UserUID,
        limit: int = 8,
    ) -> Result[list[Neo4jProperties]]:
        """Vault-synced personal notes for the journal context digest.

        Returns the N most-recently-updated UserEntry nodes that carry a
        ``vault_file_path`` in their metadata — the marker stamped by the
        ingestion pipeline for entries that came in via vault sync.

        ``pipeline = 'journal'`` (root vault notes) and ``pipeline = 'knowledge'``
        (developed files the user shares to teach SKUEL — the ``knowledge/``
        doorway, plus frontmatter-consented ``je_pro/`` entries per the ADR-073
        amendment) are returned. Notes marked ``private: true`` are excluded —
        this read feeds journal prompts, so it carries the companion-retrieval
        gate (canon P3); the owner's own surfaces still show private notes.
        Content is truncated to 300 chars so the digest stays compact.
        """
        cypher = """
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(e:Entity {entity_type: 'user_entry'})
        WHERE e.pipeline IN ['journal', 'knowledge']
          AND coalesce(e.private, false) = false
          AND e.metadata IS NOT NULL
          AND e.metadata CONTAINS '"vault_file_path"'
        RETURN e.title AS title, left(coalesce(e.content, ''), 300) AS snippet
        ORDER BY coalesce(e.updated_at, e.created_at) DESC
        LIMIT $limit
        """
        return await self.execute_query(cypher, {"user_uid": user_uid, "limit": limit})

    async def get_exercise_entries_for_user(
        self,
        user_uid: UserUID,
        limit: int,
    ) -> Result[list[Neo4jProperties]]:
        """A user's exercise submissions — defined by the FULFILLS_EXERCISE edge.

        Pipeline-agnostic: an AI-destined turn-in is as much an exercise
        submission as a teacher-review one (systems review, 2026-07-03; the
        old pipeline=TEACHER_REVIEW filter hid solo-learner submissions from
        their own history). TEACHER_REVIEW entries without an edge are kept
        for pre-edge legacy rows.
        """
        query = f"""
        MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(e:Entity {{entity_type: $entry_type}})
        WHERE EXISTS((e)-[:{RelationshipName.FULFILLS_EXERCISE.value}]->()) OR e.pipeline = 'teacher_review'
        RETURN e
        ORDER BY e.created_at DESC
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
        """Knowledge-pipeline entries with their grounded-Ku chips.

        One row per ``pipeline: knowledge`` entry the user OWNS, newest first,
        each carrying a ``grounded_kus`` list built from its outgoing
        ``APPLIES_KNOWLEDGE`` edges (both writers: EXTRACT_ACTIVITIES explicit
        refs and vector grounding). Chips are ordered by edge confidence;
        explicit edges have no ``confidence`` property and sort first
        (coalesced to 1.0 — an explicit reference outranks any inference).
        """
        query = f"""
        MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(e:Entity {{entity_type: $entry_type}})
        WHERE e.pipeline = 'knowledge'
        OPTIONAL MATCH (e)-[r:{RelationshipName.APPLIES_KNOWLEDGE.value}]->(ku:Entity:Ku)
        WITH e, r, ku
        ORDER BY coalesce(r.confidence, 1.0) DESC, ku.title
        WITH e, [g IN collect({{
            ku_uid: ku.uid,
            ku_title: ku.title,
            confidence: r.confidence,
            inferred: r.inferred
        }}) WHERE g.ku_uid IS NOT NULL] AS grounded_kus
        RETURN e.uid AS uid, e.title AS title, e.created_at AS created_at,
               grounded_kus
        ORDER BY e.created_at DESC
        LIMIT $limit
        """
        result = await self.execute_query(
            query,
            {"user_uid": user_uid, "entry_type": _USER_ENTRY, "limit": limit},
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(to_knowledge_entry_grounding_rows(result.value))

    async def get_entries_for_path_step(
        self,
        user_uid: UserUID,
        ps_uid: str,
        limit: int,
    ) -> Result[list[Neo4jProperties]]:
        """Entries for a path step via ``Interaction`` edges."""
        query = f"""
        MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(sub:Entity {{entity_type: $entry_type}})
        MATCH (i:Entity:Interaction)-[:{RelationshipName.RECORDS.value}]->(sub)
        MATCH (i)-[:{RelationshipName.INTERACTION_DURING.value}]->(ps:Entity {{uid: $ps_uid}})
        OPTIONAL MATCH (sub)-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(ex:Entity)
        OPTIONAL MATCH (report:Entity)-[:{RelationshipName.REPORT_FOR.value}]->(sub)
        RETURN sub.uid AS uid, sub.title AS title, sub.status AS status,
               sub.created_at AS created_at,
               ex.uid AS exercise_uid, ex.title AS exercise_title,
               report.uid AS report_uid,
               report.assessment_outcome AS report_outcome
        ORDER BY sub.created_at DESC
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
