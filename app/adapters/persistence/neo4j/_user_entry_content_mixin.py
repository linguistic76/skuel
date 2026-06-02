"""
UserEntry Content Enrichment Mixin
===================================

Journal processing context + exercise-instruction enrichment reads.
Covers journal temporal/thematic/goal linking, exercise-instruction
set CRUD, and path-step entry listings.

Consolidated from ``_SubmissionContentMixin`` + the ADR-054 Step 4 wrapper
into a single standalone mixin (commit 7).

Requires on concrete class:
    driver, label, logger, execute_query (from _SearchMixin)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adapters.persistence.neo4j.batch_cypher_builder import BatchCypherBuilder
from core.models.enums.entity_enums import EntityType
from core.models.relationship_names import RelationshipName
from core.models.type_hints import Neo4jProperties, UserUID
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

    async def create_goal_support_relationships(
        self, entry_uid: str, goal_uids: list[str]
    ) -> Result[int]:
        """Batch-create SUPPORTS_GOAL relationships from an entry to goals."""
        if not goal_uids:
            return Result.ok(0)
        relationships: list[tuple[str, str, str, dict[str, Any] | None]] = [
            (entry_uid, goal_uid, RelationshipName.SUPPORTS_GOAL.value, None)
            for goal_uid in goal_uids
        ]
        queries = BatchCypherBuilder.build_relationship_create_queries(relationships)
        total_created = 0
        for query, rels_data in queries:
            result = await self.execute_query(query, {"rels": rels_data})
            if result.is_error:
                continue
            records = result.value or []
            total_created += records[0]["created_count"] if records else 0
        return Result.ok(total_created)
