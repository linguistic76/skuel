"""
UserEntry Lifecycle Mixin
=========================

Exercise entry processing, FULFILLS_EXERCISE linking, temporal/thematic
relationship creation, and revision-chain queries.

Consolidated from ``_SubmissionLifecycleMixin`` + the ADR-054 Step 4 wrapper
into a single standalone mixin (commit 7).

Requires on concrete class:
    driver, label, logger, execute_query (from _SearchMixin)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.enums.entity_enums import EntityType
from core.models.relationship_names import RelationshipName
from core.models.type_hints import Neo4jProperties, UserUID
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from core.models.user_entry.user_entry import UserEntry

_USER_ENTRY = EntityType.USER_ENTRY.value


class _UserEntryLifecycleMixin:
    """Lifecycle operations for ``UserEntry``.

    See ``UserEntryBackend`` in ``backends/user_entry_backend.py`` for the
    composed class.
    """

    if TYPE_CHECKING:
        driver: AsyncDriver
        label: str

        async def execute_query(
            self, query: str, params: dict[str, Any] | None = None
        ) -> Result[list[dict[str, Any]]]: ...

        async def create(self, entity: Any) -> Result[Any]: ...

    # ========================================================================
    # EXERCISE CONTEXT
    # ========================================================================

    async def get_exercise_context(self, exercise_uid: str) -> Result[list[Neo4jProperties]]:
        """Get exercise scope, teacher, group info for submission processing."""
        query = """
        MATCH (exercise:Entity {uid: $exercise_uid})
        WHERE exercise.entity_type IN ['exercise', 'revised_exercise']
        OPTIONAL MATCH (teacher:User)-[:OWNS]->(exercise)
        OPTIONAL MATCH (exercise)-[:SHARED_WITH_GROUP]->(g:Group)
        OPTIONAL MATCH (exercise)-[:REVISES_EXERCISE]->(original:Entity {entity_type: 'exercise'})
        RETURN exercise.entity_type as exercise_entity_type,
               exercise.scope as scope,
               COALESCE(teacher.uid, exercise.user_uid) as teacher_uid,
               exercise.student_uid as student_uid,
               exercise.title as exercise_title,
               g.uid as group_uid,
               original.uid as original_exercise_uid
        """
        return await self.execute_query(query, {"exercise_uid": exercise_uid})

    # ========================================================================
    # OWNERSHIP & GROUP MEMBERSHIP
    # ========================================================================

    async def get_submission_owner(self, submission_uid: str) -> Result[list[Neo4jProperties]]:
        """Get student UID who owns an entry."""
        query = """
        MATCH (student:User)-[:OWNS]->(submission:Entity {uid: $submission_uid})
        RETURN student.uid as student_uid
        """
        return await self.execute_query(query, {"submission_uid": submission_uid})

    async def get_entry_owner(self, entry_uid: str) -> Result[list[Neo4jProperties]]:
        """Student UID who owns an entry."""
        return await self.get_submission_owner(submission_uid=entry_uid)

    async def verify_student_group_membership(
        self, submission_uid: str, group_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Check student owns entry AND is member of group."""
        query = """
        MATCH (student:User)-[:OWNS]->(submission:Entity {uid: $submission_uid})
        OPTIONAL MATCH (student)-[:MEMBER_OF]->(g:Group {uid: $group_uid})
        RETURN student.uid as student_uid, g.uid as member_of_group
        """
        return await self.execute_query(
            query, {"submission_uid": submission_uid, "group_uid": group_uid}
        )

    # ========================================================================
    # EXERCISE LINKING
    # ========================================================================

    async def link_to_exercise(
        self, submission_uid: str, exercise_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Create exercise relationships for an entry.

        Standard Exercise:
            (entry)-[:FULFILLS_EXERCISE]->(exercise)

        RevisedExercise:
            (entry)-[:FULFILLS_EXERCISE]->(original_exercise)
            (entry)-[:FULFILLS_REVISED_EXERCISE]->(revised_exercise)
        """
        query = f"""
        MATCH (submission:Entity {{uid: $submission_uid}})
        MATCH (exercise:Entity {{uid: $exercise_uid}})
        WHERE exercise.entity_type IN ['exercise', 'revised_exercise']
        OPTIONAL MATCH (exercise)-[:{RelationshipName.REVISES_EXERCISE}]->(original:Entity {{entity_type: 'exercise'}})
        WITH submission, exercise, original
        FOREACH (_ IN CASE WHEN original IS NOT NULL THEN [1] ELSE [] END |
          MERGE (submission)-[:{RelationshipName.FULFILLS_EXERCISE}]->(original)
          MERGE (submission)-[:{RelationshipName.FULFILLS_REVISED_EXERCISE}]->(exercise)
        )
        FOREACH (_ IN CASE WHEN original IS NULL THEN [1] ELSE [] END |
          MERGE (submission)-[:{RelationshipName.FULFILLS_EXERCISE}]->(exercise)
        )
        RETURN true as success
        """
        return await self.execute_query(
            query, {"submission_uid": submission_uid, "exercise_uid": exercise_uid}
        )

    async def create_with_exercise_link(
        self,
        entry: UserEntry,
        exercise_uid: str,
        revision: int,
    ) -> Result[UserEntry]:
        """Create a ``UserEntry`` and link it to an exercise atomically.

        Writes ``(:Entity:UserEntry)-[:FULFILLS_EXERCISE {revision}]->(:Exercise)``.
        For a ``RevisedExercise`` target, additionally writes
        ``FULFILLS_REVISED_EXERCISE`` to the revision node while anchoring
        ``FULFILLS_EXERCISE`` on the root ``Exercise``.
        """
        create_result = await self.create(entry)
        if create_result.is_error:
            return Result.fail(create_result)
        created: UserEntry = create_result.value  # type: ignore[assignment]

        link_query = f"""
        MATCH (entry:Entity {{uid: $entry_uid, entity_type: $entry_type}})
        MATCH (exercise:Entity {{uid: $exercise_uid}})
        WHERE exercise.entity_type IN ['exercise', 'revised_exercise']
        OPTIONAL MATCH (exercise)-[:{RelationshipName.REVISES_EXERCISE.value}]->(original:Entity {{entity_type: 'exercise'}})
        WITH entry, exercise, original
        FOREACH (_ IN CASE WHEN original IS NOT NULL THEN [1] ELSE [] END |
          MERGE (entry)-[r1:{RelationshipName.FULFILLS_EXERCISE.value}]->(original)
            ON CREATE SET r1.revision = $revision
            ON MATCH SET r1.revision = $revision
          MERGE (entry)-[r2:{RelationshipName.FULFILLS_REVISED_EXERCISE.value}]->(exercise)
            ON CREATE SET r2.revision = $revision
            ON MATCH SET r2.revision = $revision
        )
        FOREACH (_ IN CASE WHEN original IS NULL THEN [1] ELSE [] END |
          MERGE (entry)-[r3:{RelationshipName.FULFILLS_EXERCISE.value}]->(exercise)
            ON CREATE SET r3.revision = $revision
            ON MATCH SET r3.revision = $revision
        )
        RETURN true AS success
        """
        link_result = await self.execute_query(
            link_query,
            {
                "entry_uid": created.uid,
                "entry_type": _USER_ENTRY,
                "exercise_uid": exercise_uid,
                "revision": revision,
            },
        )
        if link_result.is_error:
            return Result.fail(link_result)
        if not link_result.value:
            return Result.fail(
                Errors.not_found(
                    resource="Exercise",
                    identifier=exercise_uid,
                )
            )
        return Result.ok(created)

    # ========================================================================
    # TEMPORAL & THEMATIC RELATIONSHIPS
    # ========================================================================

    async def create_temporal_relationship(
        self, ku_uid: str, user_uid: UserUID, entity_type: str
    ) -> Result[list[Neo4jProperties]]:
        """Create FOLLOWS relationship to most recent previous entry."""
        query = """
        MATCH (new:Entity {uid: $ku_uid})
        MATCH (prev:Entity {user_uid: $user_uid, entity_type: $entity_type})
        WHERE prev.uid <> $ku_uid
          AND prev.created_at <= new.created_at
        WITH new, prev
        ORDER BY prev.created_at DESC
        LIMIT 1
        MERGE (new)-[r:FOLLOWS]->(prev)
        RETURN count(r) as count
        """
        return await self.execute_query(
            query, {"ku_uid": ku_uid, "user_uid": user_uid, "entity_type": entity_type}
        )

    async def create_thematic_relationships(
        self, ku_uid: str, user_uid: UserUID, themes: list[str], shared_topics_str: str
    ) -> Result[list[Neo4jProperties]]:
        """Create RELATED_TO relationships for shared topics."""
        query = """
        MATCH (new:Entity {uid: $ku_uid})
        MATCH (other:Entity {user_uid: $user_uid})
        WHERE other.uid <> $ku_uid
          AND other.metadata IS NOT NULL
        WITH new, other, other.metadata.themes as other_themes
        WHERE other_themes IS NOT NULL
          AND any(topic IN $themes WHERE topic IN other_themes)
        WITH new, other
        LIMIT 5
        MERGE (new)-[r:RELATED_TO {shared_topics: $shared_topics_str}]->(other)
        RETURN count(r) as count
        """
        return await self.execute_query(
            query,
            {
                "ku_uid": ku_uid,
                "user_uid": user_uid,
                "themes": themes,
                "shared_topics_str": shared_topics_str,
            },
        )

    # ========================================================================
    # RELATIONSHIP QUERIES
    # ========================================================================

    async def get_related_entry_uids(self, entry_uid: str) -> Result[list[Neo4jProperties]]:
        """Get UIDs of entries related via RELATED_TO."""
        query = """
        MATCH (a:Entity {uid: $entry_uid})-[:RELATED_TO]->(related:Entity)
        RETURN related.uid as uid
        ORDER BY related.uid
        """
        return await self.execute_query(query, {"entry_uid": entry_uid})

    async def get_supported_goal_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get UIDs of goals supported by an entry via SUPPORTS_GOAL."""
        query = """
        MATCH (a:Entity {uid: $ku_uid})-[:SUPPORTS_GOAL]->(goal:Goal)
        RETURN goal.uid as uid
        ORDER BY goal.uid
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def get_submission_relationship_summary(
        self, ku_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Get relationship counts for an entry."""
        query = """
        MATCH (a:Entity {uid: $ku_uid})
        OPTIONAL MATCH (a)-[:RELATED_TO]->(related)
        OPTIONAL MATCH (a)-[:SUPPORTS_GOAL]->(goal)
        OPTIONAL MATCH (a)-[:FOLLOWS]->(prev)
        RETURN count(DISTINCT related) as related_count,
               count(DISTINCT goal) as goal_count,
               count(DISTINCT prev) as follows_count
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def get_entry_relationship_summary(self, entry_uid: str) -> Result[list[Neo4jProperties]]:
        """Per-entry relationship counts (related, goals, follows)."""
        return await self.get_submission_relationship_summary(ku_uid=entry_uid)
