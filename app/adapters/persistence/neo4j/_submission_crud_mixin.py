"""
Submission CRUD / Content Mixin
===============================

Submission-specific get/find/count/search overrides — content substring
search, feedback-count joins, exercise-linked submission lookups, teacher
feedback-state EMA read/write.

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
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from neo4j import AsyncDriver


class _SubmissionCrudMixin:
    """Submission-specific CRUD/query overrides.

    See ``SubmissionsBackend`` in ``backends/submissions_backend.py`` for the composed class.
    """

    if TYPE_CHECKING:
        driver: AsyncDriver
        label: str

        async def execute_query(
            self, query: str, params: dict[str, Any] | None = None
        ) -> Result[list[dict[str, Any]]]: ...

    async def search_submission_content(
        self,
        user_uid: UserUID,
        submission_type: str,
        query_text: str,
        limit: int = 50,
    ) -> Result[list[Neo4jProperties]]:
        """Case-insensitive substring search across processed_content.

        Args:
            user_uid: Owner of the submissions.
            submission_type: Entity type string (e.g. 'exercise_submission').
            query_text: Substring to match (case-insensitive).
            limit: Maximum results.

        Returns:
            Result containing list of submission node properties.
        """
        cypher = f"""
        MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(s:Entity)
        WHERE s.entity_type = $submission_type
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
                "submission_type": submission_type,
                "query": query_text,
                "limit": limit,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok([record["s"] for record in result.value or []])

    async def get_submissions_with_feedback_count(
        self,
        user_uid: UserUID,
        submission_type: str,
        report_type: str,
        limit: int = 50,
    ) -> Result[list[Neo4jProperties]]:
        """Get submissions enriched with teacher feedback count.

        Args:
            user_uid: Student user UID.
            submission_type: Entity type for submissions.
            report_type: Entity type for reports.
            limit: Maximum results.

        Returns:
            Result containing list of dicts with submission fields + feedback_count.
        """
        query = f"""
        MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(s:Entity)
        WHERE s.entity_type = $submission_type
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
                "submission_type": submission_type,
                "report_type": report_type,
            },
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value or [])

    async def count_submissions_for_exercise(
        self, user_uid: UserUID, exercise_uid: str
    ) -> Result[int]:
        """Count all submissions by a user for an exercise across the full learning loop.

        Resolves to the root Exercise first: if exercise_uid is a RevisedExercise,
        traverses REVISES_EXERCISE to find the original. Counts all submissions
        against the root Exercise via FULFILLS_EXERCISE, covering both initial
        submissions (revision_number=1) and all revision-cycle submissions.

        Callers may pass either an original Exercise UID or a RevisedExercise UID;
        both return the same total across all loop iterations.
        """
        query = """
        MATCH (target:Entity {uid: $exercise_uid})
        OPTIONAL MATCH (target)-[:REVISES_EXERCISE]->(orig:Entity {entity_type: 'exercise'})
        WITH COALESCE(orig, target) AS exercise
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(s:Entity)-[:FULFILLS_EXERCISE]->(exercise)
        WHERE s.entity_type IN ['exercise_submission', 'submission']
        RETURN count(s) AS count
        """
        result = await self.execute_query(
            query, {"user_uid": user_uid, "exercise_uid": exercise_uid}
        )
        if result.is_error:
            return Result.fail(result)
        record = result.value[0] if result.value else {}
        return Result.ok(record.get("count", 0))

    async def get_first_submission_for_exercise(
        self, user_uid: UserUID, exercise_uid: str
    ) -> Result[Neo4jProperties | None]:
        """Get earliest submission's uid + created_at for a user+exercise pair.

        Resolves to the root Exercise first (same logic as count_submissions_for_exercise)
        so mastery velocity calculations see the full loop from the original first attempt.
        """
        query = """
        MATCH (target:Entity {uid: $exercise_uid})
        OPTIONAL MATCH (target)-[:REVISES_EXERCISE]->(orig:Entity {entity_type: 'exercise'})
        WITH COALESCE(orig, target) AS exercise
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(s:Entity)-[:FULFILLS_EXERCISE]->(exercise)
        WHERE s.entity_type IN ['exercise_submission', 'submission']
        RETURN s.uid AS uid, s.created_at AS created_at
        ORDER BY s.created_at ASC
        LIMIT 1
        """
        result = await self.execute_query(
            query, {"user_uid": user_uid, "exercise_uid": exercise_uid}
        )
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok(None)
        return Result.ok(result.value[0])

    async def get_exercise_for_submission(self, submission_uid: str) -> Result[str | None]:
        """Get exercise UID linked to a submission via FULFILLS_EXERCISE."""
        query = """
        MATCH (s:Entity {uid: $submission_uid})-[:FULFILLS_EXERCISE]->(e:Entity)
        RETURN e.uid AS exercise_uid
        LIMIT 1
        """
        result = await self.execute_query(query, {"submission_uid": submission_uid})
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok(None)
        return Result.ok(result.value[0]["exercise_uid"])

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
