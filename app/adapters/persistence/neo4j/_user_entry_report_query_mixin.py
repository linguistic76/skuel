"""
UserEntry Report Query Mixin
=============================

Cross-joins to ExerciseReport and learning-loop chain queries.
Covers pending entries, unsubmitted exercises, report summaries,
and learning-loop chain reads.

Consolidated from the legacy ``_SubmissionReportQueryMixin`` into a single
standalone mixin (ADR-054).

Requires on concrete class:
    driver, label, logger, execute_query (from _SearchMixin)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.enums.entity_enums import EntityType
from core.models.relationship_names import RelationshipName
from core.models.type_hints import Neo4jProperties, UserUID
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from core.models.enums.neo_labels import NeoLabel

_USER_ENTRY = EntityType.USER_ENTRY.value


class _UserEntryReportQueryMixin:
    """Report-relationship cross-joins and learning-loop chain reads for ``UserEntry``.

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
    # REPORT RELATIONSHIP QUERIES
    # ========================================================================

    async def get_pending_submissions_raw(
        self, user_uid: UserUID, submission_types: list[str]
    ) -> Result[list[Neo4jProperties]]:
        """Get entries without a REPORT_FOR relationship."""
        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(submission:Entity)
        WHERE submission.entity_type IN $submission_types
          AND NOT ()-[:{RelationshipName.REPORT_FOR.value}]->(submission)
        RETURN submission.uid AS uid
        ORDER BY submission.created_at DESC
        LIMIT 20
        """
        return await self.execute_query(
            query, {"user_uid": user_uid, "submission_types": submission_types}
        )

    async def get_pending_entries_raw(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Entries without an incoming ``REPORT_FOR`` relationship."""
        return await self.get_pending_submissions_raw(
            user_uid=user_uid,
            submission_types=[_USER_ENTRY],
        )

    async def get_unsubmitted_exercises_raw(
        self, user_uid: UserUID, limit: int
    ) -> Result[list[Neo4jProperties]]:
        """Get exercises assigned via group with no entry yet."""
        query = f"""
        MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.MEMBER_OF.value}]->(group:Group)
        MATCH (exercise:Entity {{entity_type: 'exercise', scope: 'assigned'}})-[:{RelationshipName.SHARED_WITH_GROUP.value}]->(group)
        WHERE NOT (:Entity {{user_uid: $user_uid}})-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(exercise)
        RETURN exercise.uid AS uid,
               exercise.title AS title,
               exercise.due_date AS due_date
        ORDER BY exercise.due_date ASC
        LIMIT $limit
        """
        return await self.execute_query(query, {"user_uid": user_uid, "limit": limit})

    async def get_report_summary_raw(
        self, user_uid: UserUID, submission_types: list[str]
    ) -> Result[list[Neo4jProperties]]:
        """Get report completion counts for a user's entries."""
        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(submission:Entity)
        WHERE submission.entity_type IN $submission_types
        OPTIONAL MATCH (fb:Entity)-[:{RelationshipName.REPORT_FOR.value}]->(submission)
        WITH submission, count(fb) AS report_count
        RETURN
            count(submission) AS total_submissions,
            count(CASE WHEN report_count > 0 THEN 1 END) AS with_report,
            count(CASE WHEN report_count = 0 THEN 1 END) AS without_report,
            sum(report_count) AS total_reports
        """
        return await self.execute_query(
            query, {"user_uid": user_uid, "submission_types": submission_types}
        )

    async def get_entry_report_summary_raw(
        self, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Aggregate report completion counts across user's entries."""
        return await self.get_report_summary_raw(
            user_uid=user_uid,
            submission_types=[_USER_ENTRY],
        )

    async def get_learning_loop_chain_raw(self, exercise_uid: str) -> Result[list[Neo4jProperties]]:
        """Traverse full learning loop chain from an exercise."""
        query = f"""
        MATCH (ex:Entity {{uid: $exercise_uid}})
        WHERE ex.entity_type IN ['exercise', 'revised_exercise']
        OPTIONAL MATCH (sub:Entity:UserEntry)-[:{RelationshipName.FULFILLS_EXERCISE.value}|{RelationshipName.FULFILLS_REVISED_EXERCISE.value}]->(ex)
        OPTIONAL MATCH (fb:Entity)-[:{RelationshipName.REPORT_FOR.value}]->(sub)
          WHERE fb.entity_type = 'exercise_report'
        OPTIONAL MATCH (re:Entity)-[:{RelationshipName.RESPONDS_TO_REPORT.value}]->(fb)
          WHERE re.entity_type = 'revised_exercise'
        RETURN ex {{.uid, .title, .entity_type, .status, .created_at}} AS exercise,
               collect(DISTINCT sub {{.uid, .title, .status, .created_at, .user_uid}}) AS submissions,
               collect(DISTINCT fb {{.uid, .title, .processor_type, .created_at}}) AS feedback,
               collect(DISTINCT re {{.uid, .title, .revision_number, .created_at}}) AS revised_exercises
        """
        return await self.execute_query(query, {"exercise_uid": exercise_uid})

    async def get_submission_chain_raw(self, submission_uid: str) -> Result[list[Neo4jProperties]]:
        """Traverse learning loop chain from a specific entry."""
        query = f"""
        MATCH (sub:Entity:UserEntry {{uid: $submission_uid}})
        OPTIONAL MATCH (sub)-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(ex:Entity)
          WHERE ex.entity_type IN ['exercise', 'revised_exercise']
        OPTIONAL MATCH (fb:Entity)-[:{RelationshipName.REPORT_FOR.value}]->(sub)
          WHERE fb.entity_type = 'exercise_report'
        OPTIONAL MATCH (re:Entity)-[:{RelationshipName.RESPONDS_TO_REPORT.value}]->(fb)
          WHERE re.entity_type = 'revised_exercise'
        RETURN sub {{.uid, .title, .status, .created_at, .user_uid}} AS submission,
               ex {{.uid, .title, .entity_type, .status}} AS exercise,
               collect(DISTINCT fb {{.uid, .title, .processor_type, .created_at}}) AS feedback,
               collect(DISTINCT re {{.uid, .title, .revision_number, .student_uid, .created_at}}) AS revised_exercises
        """
        return await self.execute_query(query, {"submission_uid": submission_uid})

    async def get_entry_chain_raw(self, entry_uid: str) -> Result[list[Neo4jProperties]]:
        """Loop chain rooted at a specific entry."""
        return await self.get_submission_chain_raw(submission_uid=entry_uid)

    async def get_admin_uid(self) -> Result[list[Neo4jProperties]]:
        """Get the UID of the oldest admin user."""
        query = """
        MATCH (admin:User)
        WHERE admin.user_role = 'admin'
        RETURN admin.uid AS admin_uid
        ORDER BY admin.created_at ASC
        LIMIT 1
        """
        return await self.execute_query(query, {})
