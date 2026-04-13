"""
Submission Assessment + Teacher Review Mixin
============================================

Assessment scoring + teacher-review queue and reporting.
Covers teacher authority verification, assessment relationships,
review queue queries, report creation, and teacher dashboards.

Extracted from ``SubmissionsBackend`` as part of the
April 2026 persistence-layer decomposition. All behavior is unchanged —
this file only moves methods to a smaller, more focused mixin.

Requires on concrete class:
    driver, label, logger, execute_query (from _SearchMixin)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.relationship_names import RelationshipName
from core.models.type_hints import Neo4jProperties
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from neo4j import AsyncDriver


class _SubmissionAssessmentMixin:
    """Assessment scoring + teacher-review workflow operations.

    See ``SubmissionsBackend`` in ``backends/submissions_backend.py`` for the composed class.
    """

    if TYPE_CHECKING:
        driver: AsyncDriver
        label: str

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
    # TEACHER REVIEW OPERATIONS (migrated from TeacherReviewService)
    # ========================================================================

    async def get_review_queue(
        self,
        teacher_uid: str,
        status_filter: str | None = None,
        entity_type_filter: str | None = None,
    ) -> Result[list[Neo4jProperties]]:
        """Get teacher's pending review queue (all student submissions via OWNS)."""
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

    async def create_report_node(self, params: dict[str, Any]) -> Result[list[Neo4jProperties]]:
        """Create ExerciseReport node, link via REPORT_FOR, share with student, update submission.

        Canonical report-creation path for both teacher (HUMAN) and AI (LLM) reports.

        Params:
            report_uid: Submission UID to attach the report to
            report_entity_uid: UID for the new ExerciseReport node
            author_uid: UID of the user who authored the report. For teacher
                reports this is the teacher; for AI reports the caller is the
                student themselves (the "author of record").
            feedback, title, entity_type, completed_status, processor_type,
                assessment_outcome, now: standard report fields
            report_file_path: optional path to uploaded .md file (may be None)
            submission_status: new status to transition the submission to, or
                None to leave submission.status unchanged (AI reports pass None)
            allowed_from_statuses: list of current-status values permitted for
                the transition, or None to skip the guard (AI reports pass None)

        Returns empty results when the guard is present and rejects the
        transition (caller already verified existence).
        """
        query = f"""
        MATCH (submission:Entity {{uid: $report_uid}})
        WHERE $allowed_from_statuses IS NULL
           OR submission.status IN $allowed_from_statuses
        OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(submission)

        SET submission.updated_at = datetime($now)

        // Optional status transition (skip when $submission_status is null)
        FOREACH (_ IN CASE WHEN $submission_status IS NOT NULL THEN [1] ELSE [] END |
            SET submission.status = $submission_status
        )

        // Canonical feedback lives on the report node
        // Multi-label: :Entity for cross-domain queries, :ExerciseReport for
        // typed reads via ExerciseReportBackend (CLAUDE.md: multi-label writes invariant).
        CREATE (fb:Entity:ExerciseReport {{
            uid: $report_entity_uid,
            title: $title,
            entity_type: $entity_type,
            user_uid: $author_uid,
            status: $completed_status,
            visibility: 'shared',
            processor_type: $processor_type,
            assessment_outcome: $assessment_outcome,
            processed_content: $feedback,
            report_file_path: $report_file_path,
            created_by: $author_uid,
            created_at: datetime($now),
            updated_at: datetime($now)
        }})

        WITH submission, student, fb
        MATCH (author:User {{uid: $author_uid}})
        CREATE (author)-[:{RelationshipName.OWNS.value}]->(fb)
        CREATE (fb)-[:{RelationshipName.REPORT_FOR.value}]->(submission)

        WITH submission, student, fb
        WHERE student IS NOT NULL
        CREATE (student)-[:{RelationshipName.SHARES_WITH.value} {{shared_at: datetime($now), role: 'student'}}]->(fb)

        RETURN submission.uid as uid,
               submission.status as status,
               student.uid as student_uid,
               fb.uid as report_entity_uid
        """
        return await self.execute_query(query, params)

    async def create_report_and_revised_exercise(
        self, params: dict[str, Any]
    ) -> Result[list[Neo4jProperties]]:
        """Atomically create ExerciseReport + RevisedExercise in one transaction.

        Combines the two-phase revision request (create_report_node + RevisedExercise
        create with relationships) into a single Cypher query. All-or-nothing: if any
        part fails, no partial state is left behind.

        Params required:
            Phase 1 (ExerciseReport): report_uid (submission UID), report_entity_uid,
                author_uid, feedback, report_file_path, title, entity_type,
                submission_status, completed_status, processor_type,
                assessment_outcome, allowed_from_statuses, now
            Phase 2 (RevisedExercise): re_props (from to_neo4j_node), re_uid,
                original_exercise_uid
        """
        query = f"""
        // Phase 1: Match submission with status guard, create ExerciseReport
        MATCH (submission:Entity {{uid: $report_uid}})
        WHERE submission.status IN $allowed_from_statuses
        OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(submission)

        SET submission.status = $submission_status,
            submission.updated_at = datetime($now)

        CREATE (fb:Entity:ExerciseReport {{
            uid: $report_entity_uid,
            title: $title,
            entity_type: $entity_type,
            user_uid: $author_uid,
            status: $completed_status,
            visibility: 'shared',
            processor_type: $processor_type,
            assessment_outcome: $assessment_outcome,
            processed_content: $feedback,
            report_file_path: $report_file_path,
            created_by: $author_uid,
            created_at: datetime($now),
            updated_at: datetime($now)
        }})

        WITH submission, student, fb
        MATCH (author:User {{uid: $author_uid}})
        CREATE (author)-[:{RelationshipName.OWNS.value}]->(fb)
        CREATE (fb)-[:{RelationshipName.REPORT_FOR.value}]->(submission)

        // Share report with student
        WITH submission, student, fb, author
        FOREACH (_ IN CASE WHEN student IS NOT NULL THEN [1] ELSE [] END |
            CREATE (student)-[:{RelationshipName.SHARES_WITH.value} {{
                shared_at: datetime($now), role: 'student'
            }}]->(fb)
        )

        // Phase 2: Count existing revisions for revision_number
        WITH submission, student, fb, author
        OPTIONAL MATCH (existing_re:Entity {{entity_type: 'revised_exercise'}})
                       -[:{RelationshipName.REVISES_EXERCISE.value}]->
                       (orig_ex:Entity {{uid: $original_exercise_uid, entity_type: 'exercise'}})
        WITH submission, student, fb, author,
             count(existing_re) + 1 AS revision_number

        // Resolve expected_modality from original exercise
        OPTIONAL MATCH (orig_exercise:Entity {{uid: $original_exercise_uid, entity_type: 'exercise'}})

        // Create RevisedExercise node
        WITH submission, student, fb, author, revision_number, orig_exercise
        CREATE (re:Entity:RevisedExercise $re_props)
        SET re.uid = $re_uid,
            re.revision_number = revision_number,
            re.submission_uid = submission.uid,
            re.student_uid = CASE WHEN student IS NOT NULL THEN student.uid ELSE null END,
            re.title = 'Revision ' + toString(revision_number),
            re.expected_modality = orig_exercise.expected_modality,
            re.created_at = datetime($now),
            re.updated_at = datetime($now)

        // RevisedExercise relationships
        MERGE (author)-[:{RelationshipName.OWNS.value}]->(re)
        MERGE (re)-[:{RelationshipName.RESPONDS_TO_REPORT.value}]->(fb)

        WITH submission, student, fb, re, revision_number, orig_exercise
        FOREACH (_ IN CASE WHEN orig_exercise IS NOT NULL THEN [1] ELSE [] END |
            MERGE (re)-[:{RelationshipName.REVISES_EXERCISE.value}]->(orig_exercise)
        )

        // Auto-share RevisedExercise with student
        WITH submission, student, fb, re, revision_number
        FOREACH (_ IN CASE WHEN student IS NOT NULL THEN [1] ELSE [] END |
            MERGE (student)-[:{RelationshipName.SHARES_WITH.value} {{
                role: 'student'
            }}]->(re)
            ON CREATE SET student.shared_at = datetime($now)
        )

        RETURN submission.uid AS uid,
               submission.status AS status,
               CASE WHEN student IS NOT NULL THEN student.uid ELSE null END AS student_uid,
               fb.uid AS report_entity_uid,
               re.uid AS revised_exercise_uid,
               revision_number
        """
        return await self.execute_query(query, params)

    async def approve_and_get_linked_kus(
        self,
        report_uid: str,
        now: str,
        status: str,
        allowed_from_statuses: list[str],
    ) -> Result[list[Neo4jProperties]]:
        """Approve submission: set status and return linked KU UIDs for mastery.

        Cypher-level guard ensures the submission's current status is in
        ``allowed_from_statuses`` before mutating.  Returns empty results
        when the guard rejects the transition.

        Also traverses FULFILLS_EXERCISE to return the exercise's mastery_impact
        so TeacherReviewService can use MasteryImpact.get_teacher_score().
        """
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
        """Get all submissions against a specific exercise (teacher review view)."""
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

    async def get_students_summary(self, teacher_uid: str) -> Result[list[Neo4jProperties]]:
        """Get students who have submitted work, with submission counts.

        Anchors on OWNS exercise_submission — any student who has ever submitted
        appears here, regardless of PathStep enrollment. Access control is at the
        route level (TEACHER role required); teacher_uid only excludes self.
        """
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
        """Get all submissions owned by a student (admin oversight view).

        Returns every submission regardless of exercise scope or sharing status.
        Access control is handled at the route level (TEACHER role required).
        teacher_uid is retained in the signature for future per-teacher scoping.
        """
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

    async def update_submission_score(
        self, submission_uid: str, score: float
    ) -> Result[list[Neo4jProperties]]:
        """Update the score of a submission explicitly."""
        query = """
        MATCH (sub:Entity {uid: $submission_uid})
        WHERE sub.entity_type = 'exercise_submission'
        SET sub.score = $score
        RETURN sub.uid as uid, sub.score as score
        """
        return await self.execute_query(query, {"submission_uid": submission_uid, "score": score})

    async def get_submission_detail_for_teacher(
        self, submission_uid: str, teacher_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Get full submission detail for teacher review (admin oversight view).

        Looks up by submission uid directly — no SHARES_WITH gate. Standalone
        submissions (no fulfills_exercise_uid) never create a SHARES_WITH teacher
        relationship, so a sharing check would silently return empty. Access
        control is at the route level (TEACHER role required).
        teacher_uid is retained in the signature for future per-teacher scoping.
        """
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

    async def verify_teacher_access(
        self, submission_uid: str, teacher_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Verify a student (not the teacher) owns the submission."""
        query = f"""
        MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(submission:Entity {{uid: $submission_uid}})
        WHERE student.uid <> $teacher_uid
        RETURN true as has_access
        """
        return await self.execute_query(
            query, {"submission_uid": submission_uid, "teacher_uid": teacher_uid}
        )
