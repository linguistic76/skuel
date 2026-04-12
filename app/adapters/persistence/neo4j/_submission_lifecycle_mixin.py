"""
Submission Lifecycle Mixin
==========================

Exercise submission processing + submission relationship wiring.
Covers FULFILLS_EXERCISE linking, temporal/thematic relationship creation,
and revision-chain queries.

Extracted from ``SubmissionsBackend`` as part of the
April 2026 persistence-layer decomposition. All behavior is unchanged —
this file only moves methods to a smaller, more focused mixin.

Requires on concrete class:
    driver, label, logger, execute_query (from _SearchMixin)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.relationship_names import RelationshipName
from core.models.type_hints import Neo4jProperties, UserUID
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from neo4j import AsyncDriver


class _SubmissionLifecycleMixin:
    """Exercise submission processing + FULFILLS_EXERCISE/temporal/thematic relationships.

    See ``SubmissionsBackend`` in ``backends/submissions_backend.py`` for the composed class.
    """

    if TYPE_CHECKING:
        driver: AsyncDriver
        label: str

        async def execute_query(
            self, query: str, params: dict[str, Any] | None = None
        ) -> Result[list[dict[str, Any]]]: ...

    # ========================================================================
    # EXERCISE SUBMISSION PROCESSING
    # ========================================================================

    async def get_exercise_context(self, exercise_uid: str) -> Result[list[Neo4jProperties]]:
        """Get exercise scope, teacher, group info for submission processing.

        Teacher is identified via the OWNS relationship — Exercise extends
        Curriculum(Entity), not UserOwnedEntity, so exercise.user_uid is always
        None in Neo4j. COALESCE falls back to the stored property for
        RevisedExercise (UserOwnedEntity) and any future user-owned exercise types.

        For RevisedExercise nodes, also traverses REVISES_EXERCISE to return the
        root Exercise UID. process_exercise_submission() uses this to anchor
        FULFILLS_EXERCISE on the original exercise, not the revision node.
        """
        query = """
        MATCH (exercise:Entity {uid: $exercise_uid})
        WHERE exercise.entity_type IN ['exercise', 'revised_exercise']
        OPTIONAL MATCH (teacher:User)-[:OWNS]->(exercise)
        OPTIONAL MATCH (exercise)-[:FOR_GROUP]->(g:Group)
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

    async def get_submission_owner(self, submission_uid: str) -> Result[list[Neo4jProperties]]:
        """Get student UID who owns a submission."""
        query = """
        MATCH (student:User)-[:OWNS]->(submission:Entity {uid: $submission_uid})
        RETURN student.uid as student_uid
        """
        return await self.execute_query(query, {"submission_uid": submission_uid})

    async def verify_student_group_membership(
        self, submission_uid: str, group_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Check student owns submission AND is member of group."""
        query = """
        MATCH (student:User)-[:OWNS]->(submission:Entity {uid: $submission_uid})
        OPTIONAL MATCH (student)-[:MEMBER_OF]->(g:Group {uid: $group_uid})
        RETURN student.uid as student_uid, g.uid as member_of_group
        """
        return await self.execute_query(
            query, {"submission_uid": submission_uid, "group_uid": group_uid}
        )

    async def link_to_exercise(
        self, submission_uid: str, exercise_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Create exercise relationships for a submission.

        Two-path logic based on whether exercise_uid is an Exercise or RevisedExercise:

        Standard Exercise:
            (submission)-[:FULFILLS_EXERCISE]->(exercise)

        RevisedExercise:
            (submission)-[:FULFILLS_EXERCISE]->(original_exercise)   ← root anchor
            (submission)-[:FULFILLS_REVISED_EXERCISE]->(revised_exercise)

        FULFILLS_EXERCISE always points to the root Exercise node. This invariant
        means every analytics or review query against an original Exercise UID finds
        all submissions across all revision cycles without multi-hop traversal.
        FULFILLS_REVISED_EXERCISE records which specific revision instructions were
        addressed, preserving the iteration chain for chain-traversal queries.
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

    # ========================================================================
    # SUBMISSION RELATIONSHIPS
    # ========================================================================

    async def create_temporal_relationship(
        self, ku_uid: str, user_uid: UserUID, entity_type: str
    ) -> Result[list[Neo4jProperties]]:
        """Create FOLLOWS relationship to most recent previous submission."""
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

    async def get_related_submission_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get UIDs of submissions related via RELATED_TO."""
        query = """
        MATCH (a:Entity {uid: $ku_uid})-[:RELATED_TO]->(related:Entity)
        RETURN related.uid as uid
        ORDER BY related.uid
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def get_supported_goal_uids(self, ku_uid: str) -> Result[list[Neo4jProperties]]:
        """Get UIDs of goals supported by a submission via SUPPORTS_GOAL."""
        query = """
        MATCH (a:Entity {uid: $ku_uid})-[:SUPPORTS_GOAL]->(goal:Goal)
        RETURN goal.uid as uid
        ORDER BY goal.uid
        """
        return await self.execute_query(query, {"ku_uid": ku_uid})

    async def get_submission_relationship_summary(
        self, ku_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Get relationship counts for a submission."""
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
