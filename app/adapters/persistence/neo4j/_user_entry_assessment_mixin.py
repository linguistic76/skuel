"""
UserEntry Assessment + Teacher Review Mixin
============================================

Assessment scoring + teacher-review queue and reporting.
Covers teacher authority verification, assessment relationships,
review queue queries, report creation, and teacher dashboards.

Consolidated from the legacy ``_SubmissionAssessmentMixin`` into a single
standalone mixin (ADR-054).

Requires on concrete class:
    driver, label, logger, execute_query (from _SearchMixin)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.enums.pipeline import Pipeline
from core.models.relationship_names import RelationshipName
from core.models.type_hints import Neo4jProperties
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from neo4j import AsyncDriver

    from core.models.enums.neo_labels import NeoLabel


class _UserEntryAssessmentMixin:
    """Assessment scoring + teacher-review workflow operations for ``UserEntry``.

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
    # ASSESSMENT OPERATIONS
    # ========================================================================

    async def verify_teacher_authority(
        self, teacher_uid: str, subject_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Verify teacher-student share an active group."""
        query = """
        MATCH (teacher:User {uid: $teacher_uid})-[:OWNS]->(g:Group)
              <-[:MEMBER_OF]-(student:User {uid: $subject_uid})
        WHERE g.is_active = true
        RETURN g.uid AS group_uid LIMIT 1
        """
        return await self.execute_query(
            query, {"teacher_uid": teacher_uid, "subject_uid": subject_uid}
        )

    async def create_assessment_relationship(
        self, assessment_uid: str, subject_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Create ASSESSMENT_OF relationship from assessment to user."""
        query = """
        MATCH (assessment:Entity {uid: $assessment_uid})
        MATCH (u:User {uid: $subject_uid})
        MERGE (assessment)-[:ASSESSMENT_OF]->(u)
        RETURN true AS success
        """
        return await self.execute_query(
            query, {"assessment_uid": assessment_uid, "subject_uid": subject_uid}
        )

    async def auto_share_assessment_with_student(
        self, subject_uid: str, assessment_uid: str, now: str
    ) -> Result[list[Neo4jProperties]]:
        """Auto-share assessment with student via SHARES_WITH."""
        query = """
        MATCH (student:User {uid: $subject_uid})
        MATCH (assessment:Entity {uid: $assessment_uid})
        MERGE (student)-[rel:SHARES_WITH]->(assessment)
        SET rel.shared_at = datetime($now),
            rel.role = 'student'
        RETURN true AS success
        """
        return await self.execute_query(
            query,
            {"subject_uid": subject_uid, "assessment_uid": assessment_uid, "now": now},
        )

    async def get_assessments_for_student_raw(
        self, student_uid: str, limit: int
    ) -> Result[list[Neo4jProperties]]:
        """Get assessment nodes for a student via ASSESSMENT_OF."""
        query = """
        MATCH (report:Entity)-[:ASSESSMENT_OF]->(u:User {uid: $student_uid})
        WHERE report.entity_type = 'entry_report'
        RETURN report
        ORDER BY report.created_at DESC
        LIMIT $limit
        """
        return await self.execute_query(query, {"student_uid": student_uid, "limit": limit})

    # ========================================================================
    # TEACHER REVIEW OPERATIONS
    # ========================================================================

    async def get_review_queue_by_groups(
        self,
        teacher_uid: str,
        status_filter: list[str] | None = None,
    ) -> Result[list[Neo4jProperties]]:
        """Teacher's pending review queue via ``SHARED_WITH_GROUP``.

        Returns entries shared with the teacher's groups whose pipeline is
        ``teacher_review``. Empty when the teacher owns no groups, or when no
        ``UserEntry`` has been ``SHARED_WITH_GROUP`` an owned group — so we do
        not leak the existence of unrelated students' submissions.

        Copy revisions collapse to the lineage's newest: the vault exercise
        channel freezes a copy per turn-in, and a pending copy with a newer
        sibling in its (student, root exercise) lineage — newer by the
        ``FULFILLS_EXERCISE`` edge revision, the same root-lineage lens as
        ``get_latest_entry_for_exercise`` / ``_next_revision`` — is superseded
        work and never queues, regardless of the newer copy's status (a
        reviewed rev 2 retires a still-pending rev 1). Entries with no
        exercise anchor have no lineage and always pass through.
        """
        statuses = status_filter or ["submitted", "active"]
        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})-[:{RelationshipName.OWNS.value}]->(g:Group)
        MATCH (entry:Entity:UserEntry)-[:{RelationshipName.SHARED_WITH_GROUP.value}]->(g)
        WHERE entry.pipeline = $pipeline
          AND entry.status IN $statuses
        OPTIONAL MATCH (entry)-[r:{RelationshipName.FULFILLS_EXERCISE.value}]->(ex:Entity:Exercise)
        OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(entry)
        WITH entry, r, ex, student, g
        WHERE ex IS NULL OR NOT EXISTS {{
            MATCH (student)-[:{RelationshipName.OWNS.value}]->(newer:Entity:UserEntry)
                  -[nr:{RelationshipName.FULFILLS_EXERCISE.value}]->(ex)
            WHERE coalesce(nr.revision, 0) > coalesce(r.revision, 0)
               OR (coalesce(nr.revision, 0) = coalesce(r.revision, 0)
                   AND newer.created_at > entry.created_at)
        }}
        OPTIONAL MATCH (report:Entity {{entity_type: 'entry_report'}})-[:{RelationshipName.REPORT_FOR.value}]->(entry)
        WITH entry, r, ex, student, g, count(DISTINCT report) AS feedback_count
        RETURN entry.uid AS entry_uid,
               entry.title AS title,
               entry.status AS status,
               entry.entity_type AS entity_type,
               entry.original_filename AS original_filename,
               entry.created_at AS submitted_at,
               student.uid AS student_uid,
               student.name AS student_name,
               ex.uid AS exercise_uid,
               ex.title AS exercise_title,
               ex.due_date AS due_date,
               r.revision AS revision,
               g.uid AS group_uid,
               feedback_count
        ORDER BY entry.created_at DESC
        """
        return await self.execute_query(
            query,
            {
                "teacher_uid": teacher_uid,
                "pipeline": Pipeline.TEACHER_REVIEW.value,
                "statuses": statuses,
            },
        )

    async def get_report_file_path(self, report_uid: str, teacher_uid: str) -> Result[str | None]:
        """Get the report_file_path for an EntryReport, gated by teacher group access.

        Anchors on the report, walks ``REPORT_FOR`` to the reviewed submission
        and its owning student, and requires the teacher to share an active
        group with that student — the same predicate that gates writing the
        feedback (``verify_teacher_has_group_access``). Returns ``None`` both
        when no such report exists and when the teacher is outside the student's
        classroom, so a denied download is indistinguishable from a missing one
        and cannot enumerate other classrooms' reports.
        """
        query = f"""
        MATCH (r:Entity {{uid: $report_uid, entity_type: 'entry_report'}})
              -[:{RelationshipName.REPORT_FOR.value}]->(sub:Entity)
        MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(sub)
        MATCH (teacher:User {{uid: $teacher_uid}})-[:{RelationshipName.OWNS.value}]->(g:Group)
              <-[:{RelationshipName.MEMBER_OF.value}]-(student)
        WHERE g.is_active = true
          AND student.uid <> $teacher_uid
        RETURN r.report_file_path as file_path
        LIMIT 1
        """
        result = await self.execute_query(
            query, {"report_uid": report_uid, "teacher_uid": teacher_uid}
        )
        if result.is_error:
            return Result.fail(result)
        if not result.value:
            return Result.ok(None)
        return Result.ok(result.value[0].get("file_path"))

    async def approve_and_get_linked_kus(
        self,
        report_uid: str,
        now: str,
        status: str,
        allowed_from_statuses: list[str],
    ) -> Result[list[Neo4jProperties]]:
        """Approve entry: set status and return linked KU UIDs for mastery."""
        query = f"""
        MATCH (ku:Entity {{uid: $report_uid}})
        WHERE ku.status IN $allowed_from_statuses
        SET ku.status = $status,
            ku.updated_at = datetime($now)
        WITH ku
        OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(ku)
        OPTIONAL MATCH (ku)-[:{RelationshipName.APPLIES_KNOWLEDGE.value}]->(curriculum:Entity:Ku)
        OPTIONAL MATCH (ku)-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(exercise:Entity)
        RETURN ku.uid as uid,
               ku.status as status,
               student.uid as student_uid,
               collect(curriculum.uid) as linked_ku_uids,
               exercise.mastery_impact as mastery_impact
        """
        return await self.execute_query(
            query,
            {
                "report_uid": report_uid,
                "now": now,
                "status": status,
                "allowed_from_statuses": allowed_from_statuses,
            },
        )

    async def get_entries_for_exercise_review(
        self, exercise_uid: str, teacher_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Entries against an exercise that are shared with the requesting teacher's groups.

        Scoped to teacher-review turn-ins ``SHARED_WITH_GROUP`` an active or
        inactive group the teacher owns — a teacher supplying another teacher's
        exercise UID gets an empty result rather than that classroom's work.
        """
        query = f"""
        MATCH (s:Entity:UserEntry)-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(e:Entity:Exercise {{uid: $exercise_uid}})
        WHERE s.pipeline = $pipeline
          AND EXISTS {{ (s)-[:{RelationshipName.SHARED_WITH_GROUP.value}]->(:Group)<-[:{RelationshipName.OWNS.value}]-(:User {{uid: $teacher_uid}}) }}
        OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(s)
        OPTIONAL MATCH (fb:Entity {{entity_type: 'entry_report'}})-[:{RelationshipName.REPORT_FOR.value}]->(s)
        WITH s, student, count(fb) AS feedback_count
        RETURN s.uid AS uid, s.title AS title,
               s.original_filename AS original_filename, s.status AS status,
               s.created_at AS created_at, student.uid AS student_uid,
               student.name AS student_name, feedback_count
        ORDER BY s.created_at DESC
        """
        return await self.execute_query(
            query,
            {
                "exercise_uid": exercise_uid,
                "teacher_uid": teacher_uid,
                "pipeline": Pipeline.TEACHER_REVIEW.value,
            },
        )

    async def get_students_summary(self, teacher_uid: str) -> Result[list[Neo4jProperties]]:
        """Get students who have submitted work, with entry counts."""
        query = f"""
        MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(ku:Entity:UserEntry)
        WHERE student.uid <> $teacher_uid
          AND ku.pipeline = $pipeline
          AND EXISTS {{ (ku)-[:{RelationshipName.SHARED_WITH_GROUP.value}]->(:Group)<-[:{RelationshipName.OWNS.value}]-(:User {{uid: $teacher_uid}}) }}
        WITH student,
             count(DISTINCT ku) AS submission_count,
             count(DISTINCT CASE WHEN ku.status = 'completed' THEN ku.uid END) AS reviewed_count
        RETURN student.uid AS student_uid,
               student.name AS student_name,
               submission_count,
               reviewed_count,
               submission_count - reviewed_count AS pending_count
        ORDER BY pending_count DESC, submission_count DESC
        """
        return await self.execute_query(
            query, {"teacher_uid": teacher_uid, "pipeline": Pipeline.TEACHER_REVIEW.value}
        )

    async def get_student_entries_for_teacher(
        self, teacher_uid: str, student_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """A student's teacher-review entries that are shared with the teacher's groups.

        Gate: each entry must itself be ``SHARED_WITH_GROUP`` an active group the
        requesting teacher owns — not merely prove that teacher and student share
        *some* group. This stops a teacher who shares one group with a multi-class
        student from reading entries the student only shared with another teacher's
        group. Empty result when nothing the student owns is shared with this
        teacher's groups — indistinguishable from a genuinely empty history, so the
        existence of other classrooms' submissions is not leaked. (Mirrors the
        entry-level gate used by ``get_entry_detail_for_teacher``; ``EXISTS`` avoids
        inflating ``feedback_count`` when an entry is shared with several of the
        teacher's groups.)
        """
        query = f"""
        MATCH (student:User {{uid: $student_uid}})-[:{RelationshipName.OWNS.value}]->(ku:Entity:UserEntry)
        WHERE ku.pipeline = $pipeline
          AND EXISTS {{
            (ku)-[:{RelationshipName.SHARED_WITH_GROUP.value}]->(g:Group {{is_active: true}})
                <-[:{RelationshipName.OWNS.value}]-(:User {{uid: $teacher_uid}})
          }}
        OPTIONAL MATCH (fb:Entity {{entity_type: 'entry_report'}})-[:{RelationshipName.REPORT_FOR.value}]->(ku)
        OPTIONAL MATCH (ku)-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(ex:Entity:Exercise)
        WITH ku, count(fb) AS feedback_count, ex
        RETURN ku.uid AS uid, ku.title AS title,
               ku.original_filename AS original_filename, ku.status AS status,
               ku.created_at AS created_at,
               feedback_count, ex.uid AS exercise_uid, ex.title AS exercise_title
        ORDER BY ku.created_at DESC
        """
        return await self.execute_query(
            query,
            {
                "teacher_uid": teacher_uid,
                "student_uid": student_uid,
                "pipeline": Pipeline.TEACHER_REVIEW.value,
            },
        )

    async def update_entry_score(
        self, entry_uid: str, score: float
    ) -> Result[list[Neo4jProperties]]:
        """Update the score on an entry explicitly."""
        query = """
        MATCH (sub:Entity:UserEntry {uid: $entry_uid})
        SET sub.score = $score
        RETURN sub.uid as uid, sub.score as score
        """
        return await self.execute_query(query, {"entry_uid": entry_uid, "score": score})

    async def get_entry_detail_for_teacher(
        self, entry_uid: str, teacher_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Full entry detail for teacher review, gated by SHARED_WITH_GROUP.

        Model B gate: the entry must be ``SHARED_WITH_GROUP`` an active group
        the teacher owns. Empty result when the teacher has no shared group
        with the entry — service-layer callers (``get_submission_detail``)
        map empty to ``Errors.not_found`` (404) so a teacher outside the
        student's group cannot distinguish "entry does not exist" from
        "entry exists but belongs to another teacher's student".
        """
        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})-[:{RelationshipName.OWNS.value}]->(g:Group)
        WHERE g.is_active = true
        MATCH (s:Entity:UserEntry {{uid: $entry_uid}})
              -[:{RelationshipName.SHARED_WITH_GROUP.value}]->(g)
        WHERE s.pipeline = $pipeline
        OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(s)
        OPTIONAL MATCH (s)-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(ex:Entity:Exercise)
        RETURN s.uid AS uid,
               s.title AS title,
               s.content AS content,
               s.processed_content AS processed_content,
               s.file_path AS file_path,
               s.original_filename AS original_filename,
               s.entity_type AS entity_type,
               s.status AS status,
               s.created_at AS created_at,
               student.uid AS student_uid,
               student.name AS student_name,
               ex.uid AS exercise_uid,
               ex.title AS exercise_title,
               ex.instructions AS exercise_instructions
        """
        return await self.execute_query(
            query,
            {
                "entry_uid": entry_uid,
                "teacher_uid": teacher_uid,
                "pipeline": Pipeline.TEACHER_REVIEW.value,
            },
        )

    async def get_dashboard_stats(self, teacher_uid: str) -> Result[list[Neo4jProperties]]:
        """At-a-glance stats for the teacher dashboard, scoped to the teacher's classroom.

        ``pending_count`` + ``total_students`` are Model-B-scoped: counted only
        across entries ``SHARED_WITH_GROUP`` an active group the teacher owns.
        ``total_exercises`` + ``total_groups`` are scoped via direct ``OWNS``
        from the teacher (already correct pre-fix).

        ``pending_count`` is the review queue's badge twin and applies the
        queue's copy-revision collapse (see ``get_review_queue_by_groups``):
        a pending copy superseded by a newer sibling in its (student, root
        exercise) lineage is not pending work, so the badge and the queue
        length agree.
        """
        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})
        OPTIONAL MATCH (teacher)-[:{RelationshipName.OWNS.value}]->(g:Group)
        OPTIONAL MATCH (sub:Entity:UserEntry)
                      -[:{RelationshipName.SHARED_WITH_GROUP.value}]->(g)
          WHERE sub.pipeline = $pipeline
        OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(sub)
        WHERE student.uid <> $teacher_uid
        OPTIONAL MATCH (teacher)-[:{RelationshipName.OWNS.value}]->(ex:Entity:Exercise)
        RETURN
          count(DISTINCT CASE
              WHEN sub.status IN ['submitted', 'active'] AND NOT EXISTS {{
                  MATCH (sub)-[sr:{RelationshipName.FULFILLS_EXERCISE.value}]->(:Entity:Exercise)
                        <-[nr:{RelationshipName.FULFILLS_EXERCISE.value}]-(newer:Entity:UserEntry)
                  WHERE (student)-[:{RelationshipName.OWNS.value}]->(newer)
                    AND (coalesce(nr.revision, 0) > coalesce(sr.revision, 0)
                         OR (coalesce(nr.revision, 0) = coalesce(sr.revision, 0)
                             AND newer.created_at > sub.created_at))
              }}
              THEN sub.uid END) AS pending_count,
          count(DISTINCT student) AS total_students,
          count(DISTINCT ex) AS total_exercises,
          count(DISTINCT g) AS total_groups
        """
        return await self.execute_query(
            query, {"teacher_uid": teacher_uid, "pipeline": Pipeline.TEACHER_REVIEW.value}
        )

    async def verify_teacher_has_group_access(
        self, submission_uid: str, teacher_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Verify teacher and the entry's owner share an active group.

        Anchors on the submission to resolve the student, then requires
        ``(teacher)-[:OWNS]->(g:Group {is_active:true})<-[:MEMBER_OF]-(student)``.
        Returns empty when the teacher has no shared active group with the
        submission's owner — callers map empty to 404 (not found) so we do
        not leak the existence of unrelated students' submissions.
        """
        query = f"""
        MATCH (submission:Entity {{uid: $submission_uid}})
        MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(submission)
        MATCH (teacher:User {{uid: $teacher_uid}})-[:{RelationshipName.OWNS.value}]->(g:Group)
              <-[:{RelationshipName.MEMBER_OF.value}]-(student)
        WHERE g.is_active = true
          AND student.uid <> $teacher_uid
        RETURN true AS has_access LIMIT 1
        """
        return await self.execute_query(
            query, {"submission_uid": submission_uid, "teacher_uid": teacher_uid}
        )
