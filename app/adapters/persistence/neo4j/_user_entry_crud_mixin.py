"""
UserEntry CRUD / Content Mixin — ADR-054 Step 4
================================================

Thin wrapper over ``_SubmissionCrudMixin`` that exposes the method names
declared by ``UserEntryCrudOperations`` (Step 3 protocol). The underlying
Cypher is parametric by ``entity_type`` already; this mixin just hard-wires
``EntityType.USER_ENTRY.value`` so the protocol surface matches the ADR
naming ("entry", not "submission").

Additive through Step 13 — the legacy ``_SubmissionCrudMixin`` stays in
place and the legacy ``SubmissionsBackend`` continues to compose it for
the old ``exercise_submission`` entity type.
"""

from __future__ import annotations

from adapters.persistence.neo4j._submission_crud_mixin import _SubmissionCrudMixin
from core.models.enums.entity_enums import EntityType
from core.models.type_hints import Neo4jProperties, UserUID
from core.utils.result_simplified import Result

_USER_ENTRY = EntityType.USER_ENTRY.value


class _UserEntryCrudMixin(_SubmissionCrudMixin):
    """CRUD / content-search wrappers for ``UserEntry``.

    See ``UserEntryBackend`` in ``backends/user_entry_backend.py`` for the
    composed class.
    """

    async def search_entry_content(
        self,
        user_uid: UserUID,
        query_text: str,
        limit: int = 50,
    ) -> Result[list[Neo4jProperties]]:
        """Case-insensitive substring search across ``processed_content``."""
        return await self.search_submission_content(
            user_uid=user_uid,
            submission_type=_USER_ENTRY,
            query_text=query_text,
            limit=limit,
        )

    async def get_entries_with_feedback_count(
        self,
        user_uid: UserUID,
        limit: int = 50,
    ) -> Result[list[Neo4jProperties]]:
        """List user entries enriched with teacher feedback counts."""
        return await self.get_submissions_with_feedback_count(
            user_uid=user_uid,
            submission_type=_USER_ENTRY,
            report_type=EntityType.EXERCISE_REPORT.value,
            limit=limit,
        )

    async def count_entries_for_exercise(self, user_uid: UserUID, exercise_uid: str) -> Result[int]:
        """Count entries a user has submitted against an exercise.

        Resolves ``RevisedExercise`` -> root ``Exercise`` first (same
        semantics as ``count_submissions_for_exercise``), then counts
        ``UserEntry`` nodes connected by ``FULFILLS_EXERCISE``.
        """
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

    async def get_exercise_for_entry(self, entry_uid: str) -> Result[str | None]:
        """Exercise UID linked via ``FULFILLS_EXERCISE``, if any."""
        return await self.get_exercise_for_submission(submission_uid=entry_uid)
