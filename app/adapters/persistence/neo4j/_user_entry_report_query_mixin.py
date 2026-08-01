"""
UserEntry Report Query Mixin
=============================

Cross-joins to EntryReport and learning-loop chain queries.
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
from core.models.enums.metadata_enums import Visibility
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
        self,
        user_uid: UserUID,
        submission_types: list[str],
        pipelines: list[str] | None = None,
    ) -> Result[list[Neo4jProperties]]:
        """Get entries without a REPORT_FOR relationship.

        When ``pipelines`` is non-empty, narrows further to entries whose
        ``pipeline`` property is in the given values (``$pipelines IS NULL``
        is the no-filter case, evaluated server-side).
        """
        query = f"""
        MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(submission:Entity)
        WHERE submission.entity_type IN $submission_types
          AND ($pipelines IS NULL OR submission.pipeline IN $pipelines)
          AND NOT ()-[:{RelationshipName.REPORT_FOR.value}]->(submission)
        RETURN submission.uid AS uid
        ORDER BY submission.created_at DESC
        LIMIT 20
        """
        return await self.execute_query(
            query,
            {
                "user_uid": user_uid,
                "submission_types": submission_types,
                "pipelines": pipelines if pipelines else None,
            },
        )

    async def get_pending_entries_raw(
        self, user_uid: UserUID, pipelines: list[str] | None = None
    ) -> Result[list[Neo4jProperties]]:
        """Entries without an incoming ``REPORT_FOR`` relationship."""
        return await self.get_pending_submissions_raw(
            user_uid=user_uid,
            submission_types=[_USER_ENTRY],
            pipelines=pipelines,
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
          WHERE fb.entity_type = 'entry_report'
        OPTIONAL MATCH (re:Entity)-[:{RelationshipName.RESPONDS_TO_REPORT.value}]->(fb)
          WHERE re.entity_type = 'revised_exercise'
        RETURN ex {{.uid, .title, .entity_type, .status, .created_at}} AS exercise,
               collect(DISTINCT sub {{.uid, .title, .status, .created_at, .user_uid}}) AS submissions,
               collect(DISTINCT fb {{.uid, .title, .processor_type, .created_at}}) AS feedback,
               collect(DISTINCT re {{.uid, .title, .revision_number, .created_at}}) AS revised_exercises
        """
        return await self.execute_query(query, {"exercise_uid": exercise_uid})

    async def get_exchange_thread_raw(
        self, exercise_uid: str, student_uid: str, viewer_uid: str | None = None
    ) -> Result[list[Neo4jProperties]]:
        """One (student, root exercise) exchange — the whole chain in one read.

        Collects every artifact of the exchange thread (feedback-loop UX arc
        C5): the student's entries against the root exercise (both the direct
        ``FULFILLS_EXERCISE`` turn-ins, carrying the edge's ``revision``, and
        entries fulfilling a revision of it via ``FULFILLS_REVISED_EXERCISE``),
        the reports written on those entries, and the revision requests that
        respond to those reports. Revisions are scoped through the chain's own
        reports, so another student's revision of the same exercise never
        appears.

        ``viewer_uid`` is the teacher-mode scope (NULL = the student reading
        their own exchange): each entry must itself be ``SHARED_WITH_GROUP``
        an active group the viewer owns — the Model B entry-level gate
        (``get_entry_detail_for_teacher``). Merely sharing *some* group with
        a multi-class student must not expose work the student directed only
        to another teacher's classroom; reports and revisions hang off the
        entries, so gating the entries gates the whole chain.

        PRIVATE reports are excluded — a self-owned journal reflection is the
        student's own artifact, not part of the teacher↔student exchange
        (same class rule as ``get_assessments_for_student_raw``).

        Every ``created_at`` is emitted through ``toString()`` so the caller
        always receives ISO-8601 strings — entry timestamps are stored as ISO
        strings by the mapper while report timestamps are native datetimes,
        and a mixed-type emission would push the sort problem to every reader.

        Returns a single row: ``exercise`` (NULL when the UID matches no
        exercise), ``entries``, ``reports``, ``revisions``.
        """
        viewer_gate = f"""($viewer_uid IS NULL OR EXISTS {{
            MATCH (%s)-[:{RelationshipName.SHARED_WITH_GROUP.value}]->(:Group {{is_active: true}})
                  <-[:{RelationshipName.OWNS.value}]-(:User {{uid: $viewer_uid}})
        }})"""
        query = f"""
        OPTIONAL MATCH (ex:Entity:Exercise {{uid: $exercise_uid}})
        OPTIONAL MATCH (student:User {{uid: $student_uid}})-[:{RelationshipName.OWNS.value}]->(direct:Entity:UserEntry)
                       -[f:{RelationshipName.FULFILLS_EXERCISE.value}]->(ex)
        WHERE {viewer_gate % "direct"}
        WITH ex,
             collect(DISTINCT direct {{.uid, .title, .status, created_at: toString(direct.created_at),
                                       revision: f.revision, via_revised_uid: NULL}}) AS direct_rows,
             collect(DISTINCT direct) AS direct_nodes
        OPTIONAL MATCH (:User {{uid: $student_uid}})-[:{RelationshipName.OWNS.value}]->(rentry:Entity:UserEntry)
                       -[:{RelationshipName.FULFILLS_REVISED_EXERCISE.value}]->(rex:Entity:RevisedExercise)
                       -[:{RelationshipName.REVISES_EXERCISE.value}]->(ex)
        WHERE {viewer_gate % "rentry"}
        WITH ex, direct_rows, direct_nodes,
             collect(DISTINCT rentry {{.uid, .title, .status, created_at: toString(rentry.created_at),
                                       revision: NULL, via_revised_uid: rex.uid}}) AS revised_rows,
             collect(DISTINCT rentry) AS revised_nodes
        WITH ex, direct_rows + revised_rows AS entry_rows, direct_nodes + revised_nodes AS entry_nodes
        OPTIONAL MATCH (report:Entity {{entity_type: 'entry_report'}})-[:{RelationshipName.REPORT_FOR.value}]->(entry)
        WHERE entry IN entry_nodes
          AND coalesce(report.visibility, 'shared') <> $private_visibility
        WITH ex, entry_rows,
             collect(DISTINCT report {{.uid, .title, .content, .processed_content, .processor_type,
                                       .report_file_path, created_at: toString(report.created_at),
                                       entry_uid: entry.uid}}) AS report_rows,
             collect(DISTINCT report) AS report_nodes
        OPTIONAL MATCH (rev:Entity:RevisedExercise)-[:{RelationshipName.RESPONDS_TO_REPORT.value}]->(rep)
        WHERE rep IN report_nodes
        RETURN ex {{.uid, .title, .status, .entity_type}} AS exercise,
               entry_rows AS entries,
               report_rows AS reports,
               collect(DISTINCT rev {{.uid, .title, .instructions, .revision_number,
                                      created_at: toString(rev.created_at),
                                      report_uid: rep.uid}}) AS revisions
        """
        return await self.execute_query(
            query,
            {
                "exercise_uid": exercise_uid,
                "student_uid": student_uid,
                "viewer_uid": viewer_uid,
                "private_visibility": Visibility.PRIVATE.value,
            },
        )

    async def get_submission_chain_raw(self, submission_uid: str) -> Result[list[Neo4jProperties]]:
        """Traverse learning loop chain from a specific entry."""
        query = f"""
        MATCH (sub:Entity:UserEntry {{uid: $submission_uid}})
        OPTIONAL MATCH (sub)-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(ex:Entity)
          WHERE ex.entity_type IN ['exercise', 'revised_exercise']
        OPTIONAL MATCH (fb:Entity)-[:{RelationshipName.REPORT_FOR.value}]->(sub)
          WHERE fb.entity_type = 'entry_report'
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
        """Get the UID of the oldest human admin user.

        The role lives in the `role` property (the User dataclass field name);
        `user_role` was a legacy property no current write path produces.

        Service accounts (`@skuel.local` emails: user_system, the legacy
        vault-watcher) carry role=admin but must never win this pick — the
        caller treats the result as the default TEACHER for curriculum
        content, and a default group owned by user_system is a review queue
        nobody can ever log into.
        """
        query = """
        MATCH (admin:User)
        WHERE admin.role = 'admin'
          AND NOT coalesce(admin.email, '') ENDS WITH '@skuel.local'
        RETURN admin.uid AS admin_uid
        ORDER BY admin.created_at ASC
        LIMIT 1
        """
        return await self.execute_query(query, {})
