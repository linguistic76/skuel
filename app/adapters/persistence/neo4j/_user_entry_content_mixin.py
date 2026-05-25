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

from core.infrastructure.batch.batch_cypher_builder import BatchCypherBuilder
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
        """Gather journal processing context in a single query."""
        cypher = """
        MATCH (u:User {uid: $user_uid})

        // Recent journal-type reports (last 7 days)
        OPTIONAL MATCH (u)-[:OWNS]->(recent:Entity)
        WHERE recent.entity_type = 'exercise_submission'
          AND recent.created_at >= datetime() - duration('P7D')
        WITH u, collect({
            uid: recent.uid,
            title: recent.title,
            content: recent.content,
            entry_date: toString(date(recent.entry_date)),
            mood: recent.mood,
            energy_level: recent.energy_level,
            key_topics: recent.key_topics
        }) as recent_journals

        // Active goals
        OPTIONAL MATCH (u)-[:OWNS]->(g:Goal)
        WHERE g.status = 'active'
        WITH u, recent_journals, collect({
            uid: g.uid,
            title: g.title,
            description: g.description
        }) as active_goals

        // Recent topics (from last 30 days) - journal-type reports
        OPTIONAL MATCH (u)-[:OWNS]->(j:Entity)
        WHERE j.entity_type = 'exercise_submission'
          AND j.created_at >= datetime() - duration('P30D')
          AND j.key_topics IS NOT NULL
        WITH u, recent_journals, active_goals,
             collect(j.key_topics) as all_topics_raw,
             collect(j.energy_level) as all_energy_levels

        RETURN {
            recent_entries: recent_journals,
            active_goals: active_goals,
            all_topics_json: all_topics_raw,
            recent_mood_avg:
                CASE
                    WHEN size([e IN all_energy_levels WHERE e IS NOT NULL]) > 0
                    THEN reduce(sum = 0.0, e IN [x IN all_energy_levels WHERE x IS NOT NULL] | sum + e) /
                         size([e IN all_energy_levels WHERE e IS NOT NULL])
                    ELSE 0.0
                END,
            data_points: size(all_energy_levels)
        } as context
        """
        return await self.execute_query(cypher, {"user_uid": user_uid})

    async def get_recent_journal_entries(
        self, user_uid: UserUID, cutoff_datetime: str
    ) -> Result[list[Neo4jProperties]]:
        """Get recent journal-type report entries."""
        cypher = """
        MATCH (j:Report {user_uid: $user_uid, report_type: 'journal'})
        WHERE j.created_at >= datetime($cutoff_datetime)
        RETURN j.uid as uid,
               j.title as title,
               j.content as content,
               date(j.entry_date) as entry_date,
               j.mood as mood,
               j.energy_level as energy_level,
               j.key_topics as key_topics
        ORDER BY j.created_at DESC
        LIMIT 10
        """
        return await self.execute_query(
            cypher, {"user_uid": user_uid, "cutoff_datetime": cutoff_datetime}
        )

    async def get_active_goals_for_user(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Get active goals for a user (for content enrichment context)."""
        cypher = """
        MATCH (g:Goal {user_uid: $user_uid})
        WHERE g.status = 'active'
        RETURN g.uid as uid, g.title as title, g.description as description
        ORDER BY g.created_at DESC
        LIMIT 10
        """
        return await self.execute_query(cypher, {"user_uid": user_uid})

    async def get_recent_journal_topics(
        self, user_uid: UserUID, cutoff_datetime: str
    ) -> Result[list[Neo4jProperties]]:
        """Get key_topics from recent journal entries for topic aggregation."""
        cypher = """
        MATCH (j:Report {user_uid: $user_uid, report_type: 'journal'})
        WHERE j.created_at >= datetime($cutoff_datetime)
        RETURN j.key_topics as key_topics
        """
        return await self.execute_query(
            cypher, {"user_uid": user_uid, "cutoff_datetime": cutoff_datetime}
        )

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
