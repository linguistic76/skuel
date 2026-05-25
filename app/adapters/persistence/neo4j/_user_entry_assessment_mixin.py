"""
UserEntry Assessment + Teacher Review Mixin
============================================

Assessment scoring + teacher-review queue and reporting.
Covers teacher authority verification, assessment relationships,
review queue queries, report creation, and teacher dashboards.

Consolidated from ``_SubmissionAssessmentMixin`` + the ADR-054 Step 4 wrapper
into a single standalone mixin (commit 7).

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
        WHERE report.entity_type = 'exercise_report'
        RETURN report
        ORDER BY report.created_at DESC
        LIMIT $limit
        """
        return await self.execute_query(query, {"student_uid": student_uid, "limit": limit})

    # ========================================================================
    # TEACHER REVIEW OPERATIONS
    # ========================================================================

    async def get_review_queue(
        self,
        teacher_uid: str,
        status_filter: str | None = None,
        entity_type_filter: str | None = None,
    ) -> Result[list[Neo4jProperties]]:
        """Get teacher's pending review queue (all student entries via OWNS)."""
        where_clauses = ["student.uid <> $teacher_uid"]
        params: dict[str, Any] = {"teacher_uid": teacher_uid}

        if status_filter:
            where_clauses.append("sub.status = $status_filter")
            params["status_filter"] = status_filter
        else:
            where_clauses.append("sub.status IN ['submitted', 'active']")

        if entity_type_filter:
            where_clauses.append("sub.entity_type = $entity_type_filter")
            params["entity_type_filter"] = entity_type_filter

        where_clause = f"WHERE {' AND '.join(where_clauses)}"

        query = f"""
        MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(sub:Entity {{entity_type: 'exercise_submission'}})
        {where_clause}
        OPTIONAL MATCH (sub)-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(exercise:Entity:Exercise)
        OPTIONAL MATCH (report:Entity {{entity_type: 'exercise_report'}})-[:{RelationshipName.REPORT_FOR.value}]->(sub)
        WITH sub, student, exercise, count(report) as feedback_count
        RETURN sub.uid as submission_uid,
               sub.title as title,
               sub.status as status,
               sub.entity_type as entity_type,
               sub.original_filename as original_filename,
               sub.created_at as submitted_at,
               student.uid as student_uid,
               student.name as student_name,
               exercise.uid as exercise_uid,
               exercise.title as exercise_name,
               exercise.due_date as due_date,
               feedback_count
        ORDER BY sub.created_at DESC
        """
        return await self.execute_query(query, params)

    async def get_review_queue_by_groups(
        self,
        teacher_uid: str,
        status_filter: list[str] | None = None,
    ) -> Result[list[Neo4jProperties]]:
        """Teacher's pending review queue via ``SHARED_WITH_GROUP``."""
        statuses = status_filter or ["submitted", "active"]
        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})-[:{RelationshipName.OWNS.value}]->(g:Group)
        MATCH (entry:Entity:UserEntry)-[:{RelationshipName.SHARED_WITH_GROUP.value}]->(g)
        WHERE entry.pipeline = $pipeline
          AND entry.status IN $statuses
        OPTIONAL MATCH (entry)-[r:{RelationshipName.FULFILLS_EXERCISE.value}]->(ex:Entity:Exercise)
        OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(entry)
        RETURN entry.uid AS entry_uid,
               entry.title AS title,
               entry.status AS status,
               entry.original_filename AS original_filename,
               entry.created_at AS submitted_at,
               student.uid AS student_uid,
               student.name AS student_name,
               ex.uid AS exercise_uid,
               ex.title AS exercise_title,
               ex.due_date AS due_date,
               r.revision AS revision,
               g.uid AS group_uid
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

    async def get_report_file_path(self, report_uid: str) -> Result[str | None]:
        """Get the report_file_path for an ExerciseReport node by UID."""
        query = """
        MATCH (r:Entity {uid: $report_uid, entity_type: 'exercise_report'})
        RETURN r.report_file_path as file_path
        """
        result = await self.execute_query(query, {"report_uid": report_uid})
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

    async def get_submissions_for_exercise_review(
        self, exercise_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Get all entries against a specific exercise (teacher review view)."""
        query = f"""
        MATCH (s:Entity {{entity_type: 'exercise_submission'}})-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(e:Entity:Exercise {{uid: $exercise_uid}})
        OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(s)
        OPTIONAL MATCH (fb:Entity {{entity_type: 'exercise_report'}})-[:{RelationshipName.REPORT_FOR.value}]->(s)
        WITH s, student, count(fb) AS feedback_count
        RETURN s.uid AS uid, s.title AS title,
               s.original_filename AS original_filename, s.status AS status,
               s.created_at AS created_at, student.uid AS student_uid,
               student.name AS student_name, feedback_count
        ORDER BY s.created_at DESC
        """
        return await self.execute_query(query, {"exercise_uid": exercise_uid})

    async def get_entries_for_exercise_review(
        self, exercise_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """All entries against an exercise (teacher review view)."""
        return await self.get_submissions_for_exercise_review(exercise_uid=exercise_uid)

    async def get_students_summary(self, teacher_uid: str) -> Result[list[Neo4jProperties]]:
        """Get students who have submitted work, with entry counts."""
        query = f"""
        MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(ku:Entity {{entity_type: 'exercise_submission'}})
        WHERE student.uid <> $teacher_uid
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
        return await self.execute_query(query, {"teacher_uid": teacher_uid})

    async def get_student_submissions_for_teacher(
        self, _teacher_uid: str, student_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Get all entries owned by a student (admin oversight view)."""
        query = f"""
        MATCH (student:User {{uid: $student_uid}})-[:{RelationshipName.OWNS.value}]->(ku:Entity {{entity_type: 'exercise_submission'}})
        OPTIONAL MATCH (fb:Entity {{entity_type: 'exercise_report'}})-[:{RelationshipName.REPORT_FOR.value}]->(ku)
        OPTIONAL MATCH (ku)-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(ex:Entity:Exercise)
        WITH ku, count(fb) AS feedback_count, ex
        RETURN ku.uid AS uid, ku.title AS title,
               ku.original_filename AS original_filename, ku.status AS status,
               ku.created_at AS created_at,
               feedback_count, ex.uid AS exercise_uid, ex.title AS exercise_title
        ORDER BY ku.created_at DESC
        """
        return await self.execute_query(query, {"student_uid": student_uid})

    async def get_student_entries_for_teacher(
        self, teacher_uid: str, student_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """All entries owned by a student (admin oversight view)."""
        return await self.get_student_submissions_for_teacher(
            _teacher_uid=teacher_uid, student_uid=student_uid
        )

    async def update_submission_score(
        self, submission_uid: str, score: float
    ) -> Result[list[Neo4jProperties]]:
        """Update the score of an entry explicitly."""
        query = """
        MATCH (sub:Entity {uid: $submission_uid})
        WHERE sub.entity_type = 'exercise_submission'
        SET sub.score = $score
        RETURN sub.uid as uid, sub.score as score
        """
        return await self.execute_query(query, {"submission_uid": submission_uid, "score": score})

    async def update_entry_score(
        self, entry_uid: str, score: float
    ) -> Result[list[Neo4jProperties]]:
        """Update the score on an entry explicitly."""
        return await self.update_submission_score(submission_uid=entry_uid, score=score)

    async def get_submission_detail_for_teacher(
        self, submission_uid: str, teacher_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Get full entry detail for teacher review (admin oversight view)."""
        query = f"""
        MATCH (s:Entity {{entity_type: 'exercise_submission', uid: $submission_uid}})
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
            query, {"submission_uid": submission_uid, "teacher_uid": teacher_uid}
        )

    async def get_entry_detail_for_teacher(
        self, entry_uid: str, teacher_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Full entry detail for teacher review (admin oversight view)."""
        return await self.get_submission_detail_for_teacher(
            submission_uid=entry_uid, teacher_uid=teacher_uid
        )

    async def get_dashboard_stats(self, teacher_uid: str) -> Result[list[Neo4jProperties]]:
        """Get at-a-glance stats for the teacher dashboard."""
        query = f"""
        MATCH (teacher:User {{uid: $teacher_uid}})
        OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(ku:Entity {{entity_type: 'exercise_submission'}})
        WHERE student.uid <> $teacher_uid
        OPTIONAL MATCH (teacher)-[:{RelationshipName.OWNS.value}]->(ex:Entity:Exercise)
        OPTIONAL MATCH (teacher)-[:{RelationshipName.OWNS.value}]->(g:Group)
        RETURN
          count(CASE WHEN ku.status IN ['submitted', 'active'] THEN 1 END) AS pending_count,
          count(DISTINCT student) AS total_students,
          count(DISTINCT ex) AS total_exercises,
          count(DISTINCT g) AS total_groups
        """
        return await self.execute_query(query, {"teacher_uid": teacher_uid})

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
