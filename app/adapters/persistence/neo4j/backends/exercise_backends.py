"""Exercise-family backends: Exercise, RevisedExercise, ExerciseReport.

The three entities that drive the five-phase learning loop:
Exercise → ExerciseSubmission → ExerciseReport → RevisedExercise → …
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.exercises.exercise import Exercise
from core.models.relationship_names import RelationshipName
from core.models.report.exercise_report import ExerciseReport
from core.models.type_hints import Neo4jProperties, UserUID
from core.ports.query_types import (
    CurriculumExerciseResult,
    RequiredKnowledgeResult,
    RevisionChainResult,
)
from core.utils.neo4j_mapper import from_neo4j_node
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.exercises.revised_exercise import RevisedExercise  # noqa: F401


class ExerciseBackend(UniversalNeo4jBackend[Exercise]):
    """
    Domain backend for Exercise entities.

    Extends UniversalNeo4jBackend[Exercise] with exercise-specific Cypher
    that was previously inline in ExerciseService.

    Methods:
    - create_owns_relationship      — MERGE OWNS (user -> exercise)
    - create_for_group_relationship — MERGE FOR_GROUP (exercise -> group)
    - get_user_exercises             — OWNS query for user's exercises
    - get_student_exercises          — MEMBER_OF + FOR_GROUP traversal
    - get_student_exercises_with_status — Above + FULFILLS_EXERCISE submission check
    - get_exercises_for_curriculum   — Reverse REQUIRES_KNOWLEDGE lookup
    - link_to_curriculum             — MERGE REQUIRES_KNOWLEDGE relationship
    - unlink_from_curriculum         — DELETE REQUIRES_KNOWLEDGE relationship
    - get_required_knowledge         — Query all KUs required by an exercise
    - get_exercise_for_submission    — FULFILLS_EXERCISE reverse lookup
    """

    async def link_to_curriculum(self, exercise_uid: str, curriculum_uid: str) -> Result[bool]:
        """
        Create REQUIRES_KNOWLEDGE relationship from exercise to curriculum KU.

        Args:
            exercise_uid: Exercise UID (entity_type='exercise')
            curriculum_uid: Curriculum KU UID (entity_type='ku' or 'resource')

        Returns:
            Result[bool] - True if relationship created
        """
        result = await self.execute_query(
            f"""
            MATCH (exercise:Entity {{uid: $exercise_uid, entity_type: 'exercise'}})
            MATCH (curriculum:Entity {{uid: $curriculum_uid}})
            WHERE curriculum.entity_type IN ['ku', 'resource']
            MERGE (exercise)-[r:{RelationshipName.REQUIRES_KNOWLEDGE}]->(curriculum)
            ON CREATE SET r.created_at = datetime()
            RETURN true as success
            """,
            {"exercise_uid": exercise_uid, "curriculum_uid": curriculum_uid},
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.fail(
                Errors.not_found(
                    resource="Exercise or Curriculum KU",
                    identifier=f"{exercise_uid} -> {curriculum_uid}",
                )
            )
        return Result.ok(True)

    async def unlink_from_curriculum(self, exercise_uid: str, curriculum_uid: str) -> Result[bool]:
        """
        Remove REQUIRES_KNOWLEDGE relationship between exercise and curriculum KU.

        Args:
            exercise_uid: Exercise UID
            curriculum_uid: Curriculum KU UID

        Returns:
            Result[bool] - True if relationship removed
        """
        result = await self.execute_query(
            f"""
            MATCH (exercise:Entity {{uid: $exercise_uid, entity_type: 'exercise'}})
                  -[r:{RelationshipName.REQUIRES_KNOWLEDGE}]->
                  (curriculum:Entity {{uid: $curriculum_uid}})
            DELETE r
            RETURN true as success
            """,
            {"exercise_uid": exercise_uid, "curriculum_uid": curriculum_uid},
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.fail(
                Errors.not_found(
                    resource="REQUIRES_KNOWLEDGE relationship",
                    identifier=f"{exercise_uid} -> {curriculum_uid}",
                )
            )
        return Result.ok(True)

    async def get_required_knowledge(
        self, exercise_uid: str
    ) -> Result[list[RequiredKnowledgeResult]]:
        """
        Get all curriculum KUs required by an exercise.

        Args:
            exercise_uid: Exercise UID

        Returns:
            Result containing list of curriculum KU summaries
        """
        result = await self.execute_query(
            f"""
            MATCH (exercise:Entity {{uid: $exercise_uid, entity_type: 'exercise'}})
                  -[:{RelationshipName.REQUIRES_KNOWLEDGE}]->
                  (curriculum:Entity)
            RETURN curriculum.uid as uid,
                   curriculum.title as title,
                   curriculum.entity_type as entity_type,
                   curriculum.complexity as complexity,
                   curriculum.learning_level as learning_level
            ORDER BY curriculum.title
            """,
            {"exercise_uid": exercise_uid},
        )
        if result.is_error:
            return Result.fail(result)
        items: list[RequiredKnowledgeResult] = [dict(record) for record in (result.value or [])]  # type: ignore[misc]
        return Result.ok(items)

    async def create_owns_relationship(
        self, user_uid: UserUID, exercise_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Create OWNS relationship from user to exercise.

        Args:
            user_uid: User who owns this exercise
            exercise_uid: Exercise UID

        Returns:
            Result containing query records
        """
        return await self.execute_query(
            f"""
            MATCH (u:User {{uid: $user_uid}})
            MATCH (e:Entity {{uid: $exercise_uid}})
            MERGE (u)-[:{RelationshipName.OWNS.value}]->(e)
            RETURN true as success
            """,
            {"user_uid": user_uid, "exercise_uid": exercise_uid},
        )

    async def create_for_group_relationship(
        self, exercise_uid: str, group_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Create FOR_GROUP relationship from exercise to group.

        Args:
            exercise_uid: Exercise UID
            group_uid: Target group UID

        Returns:
            Result containing query records
        """
        return await self.execute_query(
            f"""
            MATCH (exercise:Entity {{uid: $exercise_uid, entity_type: 'exercise'}})
            MATCH (group:Group {{uid: $group_uid}})
            MERGE (exercise)-[:{RelationshipName.FOR_GROUP}]->(group)
            RETURN true as success
            """,
            {"exercise_uid": exercise_uid, "group_uid": group_uid},
        )

    async def get_user_exercises(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Get all exercises owned by a user via OWNS relationship.

        Args:
            user_uid: User UID

        Returns:
            Result containing exercise node records
        """
        return await self.execute_query(
            f"""
            MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS.value}]->(e:Exercise)
            RETURN e
            ORDER BY e.created_at DESC
            """,
            {"user_uid": user_uid},
        )

    async def get_student_exercises(self, user_uid: UserUID) -> Result[list[Neo4jProperties]]:
        """Get assigned exercises for a student via MEMBER_OF -> Group <- FOR_GROUP.

        Args:
            user_uid: Student UID

        Returns:
            Result containing exercise node records
        """
        return await self.execute_query(
            f"""
            MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.MEMBER_OF}]->(group:Group)
            MATCH (exercise:Entity {{entity_type: 'exercise'}})-[:{RelationshipName.FOR_GROUP}]->(group)
            WHERE exercise.scope = 'assigned'
            RETURN exercise
            ORDER BY exercise.due_date ASC, exercise.created_at DESC
            """,
            {"user_uid": user_uid},
        )

    async def get_student_exercises_with_status(
        self, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Get assigned exercises with submission + report status for a student.

        Returns exercise properties enriched with:
        - has_submission: bool
        - submission_uid: str | None (most recent submission)
        - submission_status: str | None
        - has_report: bool
        - report_uid: str | None (most recent report)
        - report_outcome: str | None (assessment_outcome on the report)
        - group_name: str

        Args:
            user_uid: Student UID

        Returns:
            Result containing enriched exercise records
        """
        return await self.execute_query(
            f"""
            MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.MEMBER_OF}]->(group:Group)
            MATCH (exercise:Entity {{entity_type: 'exercise'}})-[:{RelationshipName.FOR_GROUP}]->(group)
            WHERE exercise.scope = 'assigned'
            OPTIONAL MATCH (user)-[:{RelationshipName.OWNS}]->(sub:Entity)-[:{RelationshipName.FULFILLS_EXERCISE}]->(exercise)
            OPTIONAL MATCH (report:Entity)-[:{RelationshipName.REPORT_FOR}]->(sub)
            WITH exercise, group, sub, report
            ORDER BY sub.created_at DESC
            WITH exercise, group,
                 collect(sub)[0] AS latest_sub,
                 collect(report)[0] AS latest_report
            RETURN exercise,
                   latest_sub.uid AS submission_uid,
                   latest_sub.status AS submission_status,
                   latest_sub IS NOT NULL AS has_submission,
                   latest_report.uid AS report_uid,
                   latest_report.assessment_outcome AS report_outcome,
                   latest_report IS NOT NULL AS has_report,
                   group.title AS group_name
            ORDER BY exercise.due_date ASC, exercise.created_at DESC
            """,
            {"user_uid": user_uid},
        )

    async def get_enrolled_ps_exercises_with_status(
        self, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Get personal exercises linked to PathSteps the user is enrolled in.

        Returns the same shape as get_student_exercises_with_status() so results
        can be merged at the service layer. Exercises are discovered via:
            (user)-[:IN_PROGRESS]->(ps)-[:RELATED_TO]->(exercise {scope: 'personal'})

        Args:
            user_uid: Student UID

        Returns:
            Result containing enriched exercise records (group_name is empty string)
        """
        return await self.execute_query(
            f"""
            MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.IN_PROGRESS}]->(ps:Entity)
            MATCH (ps)-[:{RelationshipName.RELATED_TO}]->(exercise:Entity {{entity_type: 'exercise'}})
            WHERE exercise.scope = 'personal'
            WITH DISTINCT user, exercise
            OPTIONAL MATCH (user)-[:{RelationshipName.OWNS}]->(sub:Entity)-[:{RelationshipName.FULFILLS_EXERCISE}]->(exercise)
            OPTIONAL MATCH (report:Entity)-[:{RelationshipName.REPORT_FOR}]->(sub)
            WITH exercise, sub, report
            ORDER BY sub.created_at DESC
            WITH exercise,
                 collect(sub)[0] AS latest_sub,
                 collect(report)[0] AS latest_report
            RETURN exercise,
                   latest_sub.uid AS submission_uid,
                   latest_sub.status AS submission_status,
                   latest_sub IS NOT NULL AS has_submission,
                   latest_report.uid AS report_uid,
                   latest_report.assessment_outcome AS report_outcome,
                   latest_report IS NOT NULL AS has_report,
                   '' AS group_name
            ORDER BY exercise.created_at DESC
            """,
            {"user_uid": user_uid},
        )

    async def get_ps_exercises_with_status(
        self, ps_uid: str, user_uid: UserUID
    ) -> Result[list[Neo4jProperties]]:
        """Get exercises linked to a specific PathStep with submission/feedback status.

        Scoped version of get_enrolled_ps_exercises_with_status() — returns the same
        shape (compatible with ExerciseStatusRow) but for a single PathStep.
        """
        return await self.execute_query(
            f"""
            MATCH (ps:Entity {{uid: $ps_uid}})-[:{RelationshipName.RELATED_TO}]->(exercise:Entity {{entity_type: 'exercise'}})
            OPTIONAL MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.OWNS}]->(sub:Entity)-[:{RelationshipName.FULFILLS_EXERCISE}]->(exercise)
            OPTIONAL MATCH (report:Entity)-[:{RelationshipName.REPORT_FOR}]->(sub)
            WITH exercise, sub, report
            ORDER BY sub.created_at DESC
            WITH exercise,
                 collect(sub)[0] AS latest_sub,
                 collect(report)[0] AS latest_report
            RETURN exercise,
                   latest_sub.uid AS submission_uid,
                   latest_sub.status AS submission_status,
                   latest_sub IS NOT NULL AS has_submission,
                   latest_report.uid AS report_uid,
                   latest_report.assessment_outcome AS report_outcome,
                   latest_report IS NOT NULL AS has_report,
                   '' AS group_name
            ORDER BY exercise.title
            """,
            {"ps_uid": ps_uid, "user_uid": user_uid},
        )

    async def get_exercises_for_curriculum(
        self, curriculum_uid: str
    ) -> Result[list[CurriculumExerciseResult]]:
        """Get all exercises that require a specific curriculum KU.

        Args:
            curriculum_uid: Curriculum KU UID

        Returns:
            Result containing exercise summary records
        """
        result = await self.execute_query(
            f"""
            MATCH (exercise:Entity {{entity_type: 'exercise'}})
                  -[:{RelationshipName.REQUIRES_KNOWLEDGE}]->
                  (curriculum:Entity {{uid: $curriculum_uid}})
            RETURN exercise.uid as uid,
                   exercise.title as title,
                   exercise.scope as scope,
                   exercise.due_date as due_date,
                   exercise.status as status,
                   exercise.form_schema as form_schema
            ORDER BY exercise.created_at DESC
            """,
            {"curriculum_uid": curriculum_uid},
        )
        if result.is_error:
            return Result.fail(result)
        items: list[CurriculumExerciseResult] = [
            dict(record)
            for record in (result.value or [])  # type: ignore[misc]
        ]
        return Result.ok(items)

    async def get_exercise_for_submission(
        self, submission_uid: str
    ) -> Result[Neo4jProperties | None]:
        """Get the exercise that a submission fulfills via FULFILLS_EXERCISE relationship.

        Args:
            submission_uid: Submission UID

        Returns:
            Result containing exercise summary dict or None if not linked
        """
        result = await self.execute_query(
            f"""
            MATCH (s:Entity {{uid: $uid}})-[:{RelationshipName.FULFILLS_EXERCISE}]->(ex:Entity:Exercise)
            RETURN ex.uid AS exercise_uid, ex.title AS exercise_title
            LIMIT 1
            """,
            {"uid": submission_uid},
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.ok(None)
        return Result.ok(dict(records[0]))

    async def get_exercises_for_path_steps(
        self, ps_uids: list[str]
    ) -> Result[list[Neo4jProperties]]:
        """Get exercises associated with a list of PathStep UIDs.

        Traverses PathStep -[:USES_KU|CONTAINS_KNOWLEDGE]-> Ku <-[:REQUIRES_KNOWLEDGE]- Exercise
        to find exercises that practice knowledge from those PathSteps.

        Args:
            ps_uids: List of PathStep UIDs

        Returns:
            Result containing distinct exercise property dicts
        """
        if not ps_uids:
            return Result.ok([])

        result = await self.execute_query(
            f"""
            MATCH (ps:Entity:PathStep)-[:USES_KU|CONTAINS_KNOWLEDGE]->(ku:Entity)
                  <-[:{RelationshipName.REQUIRES_KNOWLEDGE}]-(ex:Entity {{entity_type: 'exercise'}})
            WHERE ps.uid IN $ps_uids
            RETURN DISTINCT ex.uid AS uid,
                   ex.title AS title,
                   ex.scope AS scope,
                   ex.description AS description,
                   ex.status AS status
            ORDER BY ex.title
            """,
            {"ps_uids": ps_uids},
        )
        if result.is_error:
            return Result.fail(result)
        items = [dict(record) for record in (result.value or [])]
        return Result.ok(items)

    # ========================================================================
    # TEACHER REVIEW OPERATIONS (migrated from TeacherReviewService)
    # ========================================================================

    async def get_exercises_with_submission_counts(
        self, teacher_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Get teacher's exercises with submission and reviewed counts."""
        query = f"""
        MATCH (user:User {{uid: $teacher_uid}})-[:{RelationshipName.OWNS.value}]->(exercise:Entity:Exercise)
        OPTIONAL MATCH (s:Entity {{entity_type: 'exercise_submission'}})-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(exercise)
        WITH exercise, count(s) AS total_count,
             count(CASE WHEN s.status = 'completed' THEN 1 END) AS reviewed_count
        RETURN exercise.uid AS uid, exercise.title AS title,
               exercise.scope AS scope, exercise.created_at AS created_at,
               total_count, reviewed_count,
               total_count - reviewed_count AS pending_count
        ORDER BY exercise.created_at DESC
        """
        return await self.execute_query(query, {"teacher_uid": teacher_uid})


class RevisedExerciseBackend(UniversalNeo4jBackend["RevisedExercise"]):
    """
    Domain backend for RevisedExercise entities.

    Provides relationship-specific Cypher for the five-phase learning loop:
    - verify_teacher_authority    — Check teacher review authority graph path
    - create_owns_relationship   — MERGE OWNS (teacher -> revised exercise)
    - auto_share_with_student    — MERGE SHARES_WITH (student -> revised exercise)
    - list_for_student           — Query revisions targeting a student
    - link_to_report             — MERGE RESPONDS_TO_REPORT relationship
    - link_to_exercise           — MERGE REVISES_EXERCISE relationship
    - get_revision_chain         — Query all revisions of an original exercise
    """

    async def link_to_report(self, re_uid: str, report_uid: str) -> Result[bool]:
        """Create RESPONDS_TO_REPORT relationship from revised exercise to report."""
        result = await self.execute_query(
            f"""
            MATCH (re:Entity {{uid: $re_uid, entity_type: 'revised_exercise'}})
            MATCH (fb:Entity {{uid: $report_uid}})
            WHERE fb.entity_type IN ['exercise_report', 'activity_report']
            MERGE (re)-[r:{RelationshipName.RESPONDS_TO_REPORT}]->(fb)
            ON CREATE SET r.created_at = datetime()
            RETURN true as success
            """,
            {"re_uid": re_uid, "report_uid": report_uid},
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.fail(
                Errors.not_found(
                    resource="RESPONDS_TO_REPORT relationship",
                    identifier=f"{re_uid} -> {report_uid}",
                )
            )
        return Result.ok(True)

    async def link_to_exercise(self, re_uid: str, exercise_uid: str) -> Result[bool]:
        """Create REVISES_EXERCISE relationship from revised exercise to original exercise."""
        result = await self.execute_query(
            f"""
            MATCH (re:Entity {{uid: $re_uid, entity_type: 'revised_exercise'}})
            MATCH (ex:Entity {{uid: $exercise_uid, entity_type: 'exercise'}})
            MERGE (re)-[r:{RelationshipName.REVISES_EXERCISE}]->(ex)
            ON CREATE SET r.created_at = datetime()
            RETURN true as success
            """,
            {"re_uid": re_uid, "exercise_uid": exercise_uid},
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.fail(
                Errors.not_found(
                    resource="REVISES_EXERCISE relationship",
                    identifier=f"{re_uid} -> {exercise_uid}",
                )
            )
        return Result.ok(True)

    async def verify_teacher_authority(
        self, teacher_uid: str, report_uid: str, student_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Verify teacher has review authority over a report.

        Checks the graph path (OWNS-based, per ADR-040):
        - (ExerciseReport)-[:REPORT_FOR]->(Submission) exists
        - (Student)-[:OWNS]->(Submission)
        - Teacher identity is role-gated at the route level (@require_role)

        teacher_uid is retained for audit logging and future per-teacher scoping.

        Args:
            teacher_uid: Teacher user UID (for audit; access is role-gated at route)
            report_uid: Report UID
            student_uid: Student user UID

        Returns:
            Result containing matching submission records (empty if no authority)
        """
        return await self.execute_query(
            """
            MATCH (fb:Entity {uid: $report_uid})-[:REPORT_FOR]->(submission:Entity)
            MATCH (student:User {uid: $student_uid})-[:OWNS]->(submission)
            WHERE submission.entity_type = 'exercise_submission'
            RETURN submission.uid AS submission_uid
            """,
            {
                "report_uid": report_uid,
                "teacher_uid": teacher_uid,
                "student_uid": student_uid,
            },
        )

    async def create_owns_relationship(
        self, teacher_uid: str, re_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Create OWNS relationship from teacher to revised exercise.

        Args:
            teacher_uid: Teacher user UID
            re_uid: Revised exercise UID

        Returns:
            Result containing query records
        """
        return await self.execute_query(
            f"""
            MATCH (u:User {{uid: $teacher_uid}})
            MATCH (re:Entity {{uid: $re_uid}})
            MERGE (u)-[:{RelationshipName.OWNS.value}]->(re)
            RETURN true as success
            """,
            {"teacher_uid": teacher_uid, "re_uid": re_uid},
        )

    async def auto_share_with_student(
        self, student_uid: str, re_uid: str, shared_at: str
    ) -> Result[list[Neo4jProperties]]:
        """Auto-share revised exercise with student via SHARES_WITH.

        Same pattern as assignment auto-sharing (ADR-040).

        Args:
            student_uid: Student user UID
            re_uid: Revised exercise UID
            shared_at: ISO timestamp for the share

        Returns:
            Result containing query records
        """
        return await self.execute_query(
            f"""
            MATCH (student:User {{uid: $student_uid}})
            MATCH (re:Entity {{uid: $re_uid}})
            MERGE (student)-[r:{RelationshipName.SHARES_WITH.value}]->(re)
            ON CREATE SET r.shared_at = $shared_at, r.role = 'student'
            SET re.visibility = 'shared'
            RETURN true as success
            """,
            {
                "student_uid": student_uid,
                "re_uid": re_uid,
                "shared_at": shared_at,
            },
        )

    async def list_for_student(
        self, student_uid: str, teacher_uid: str | None = None
    ) -> Result[list[Neo4jProperties]]:
        """List revised exercises targeting a specific student.

        Args:
            student_uid: The student whose revisions to list
            teacher_uid: If provided, only return revisions owned by this teacher

        Returns:
            Result containing revised exercise node records
        """
        if teacher_uid:
            query = f"""
            MATCH (u:User {{uid: $teacher_uid}})-[:{RelationshipName.OWNS.value}]->(re:RevisedExercise {{student_uid: $student_uid}})
            RETURN re
            ORDER BY re.created_at DESC
            """
            params: dict[str, str] = {"student_uid": student_uid, "teacher_uid": teacher_uid}
        else:
            query = """
            MATCH (re:RevisedExercise {student_uid: $student_uid})
            RETURN re
            ORDER BY re.created_at DESC
            """
            params = {"student_uid": student_uid}

        return await self.execute_query(query, params)

    async def get_by_report_uid(self, report_uid: str) -> Result[list[Neo4jProperties]]:
        """Look up a RevisedExercise by the report it responds to."""
        query = """
        MATCH (re:RevisedExercise {report_uid: $report_uid})
        RETURN re
        LIMIT 1
        """
        return await self.execute_query(query, {"report_uid": report_uid})

    async def get_revision_chain(self, exercise_uid: str) -> Result[list[RevisionChainResult]]:
        """
        Get all revised exercises in the revision chain for an original exercise.

        Returns revisions ordered by revision_number ascending.
        """
        result = await self.execute_query(
            f"""
            MATCH (re:Entity {{entity_type: 'revised_exercise'}})
                  -[:{RelationshipName.REVISES_EXERCISE}]->
                  (ex:Entity {{uid: $exercise_uid, entity_type: 'exercise'}})
            RETURN re.uid as uid,
                   re.title as title,
                   re.revision_number as revision_number,
                   re.student_uid as student_uid,
                   re.report_uid as report_uid,
                   re.status as status,
                   re.created_at as created_at
            ORDER BY re.revision_number ASC
            """,
            {"exercise_uid": exercise_uid},
        )
        if result.is_error:
            return Result.fail(result)
        items: list[RevisionChainResult] = [
            dict(record)
            for record in (result.value or [])  # type: ignore[misc]
        ]
        return Result.ok(items)

    async def get_for_teacher(
        self, teacher_uid: str, limit: int = 50
    ) -> Result[list[Neo4jProperties]]:
        """
        List all RevisedExercises created by a teacher, ordered by most recent.

        Traverses OWNS relationship from teacher to revised exercises for
        authoritative ownership lookup. Includes student and exercise context
        for teacher dashboard display.

        Args:
            teacher_uid: The teacher's user UID
            limit: Maximum records to return (default 50)

        Returns:
            Result containing revised exercise records with student/exercise context
        """
        return await self.execute_query(
            f"""
            MATCH (teacher:User {{uid: $teacher_uid}})-[:{RelationshipName.OWNS.value}]->(re:RevisedExercise)
            OPTIONAL MATCH (re)-[:{RelationshipName.REVISES_EXERCISE.value}]->(ex:Entity {{entity_type: 'exercise'}})
            RETURN re.uid AS uid,
                   re.title AS title,
                   re.revision_number AS revision_number,
                   re.student_uid AS student_uid,
                   re.report_uid AS report_uid,
                   re.status AS status,
                   re.created_at AS created_at,
                   ex.uid AS exercise_uid,
                   ex.title AS exercise_title
            ORDER BY re.created_at DESC
            LIMIT $limit
            """,
            {"teacher_uid": teacher_uid, "limit": limit},
        )


class ExerciseReportBackend(UniversalNeo4jBackend[ExerciseReport]):
    """
    Domain backend for ExerciseReport entities.

    Provides typed relationship-specific reads for the five-phase learning loop.
    All reads assert both labels (``:Entity:ExerciseReport``) and return
    ``list[ExerciseReport]`` via ``from_neo4j_node``.

    Report *creation* is delegated to ``SubmissionsBackend.create_report_node``
    — the canonical cross-domain path shared by teacher and AI reports.
    """

    async def list_for_submission(self, submission_uid: str) -> Result[list[ExerciseReport]]:
        """Return all reports attached to a submission, as typed ExerciseReport
        instances, ordered by created_at ASC (oldest → newest review round).

        Replaces the former dict-returning get_report_for_submission (this
        backend) and the dict-returning SubmissionsBackend.get_report_history.
        Typed all the way to the route handler — no TypedDict projection.
        """
        cypher = f"""
            MATCH (n:ExerciseReport)-[:{RelationshipName.REPORT_FOR.value}]->(:Entity {{uid: $submission_uid}})
            RETURN n
            ORDER BY n.created_at ASC
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(cypher, {"submission_uid": submission_uid})
                records = await result.data()
            entities = [from_neo4j_node(record["n"], self.entity_class) for record in records]
            return Result.ok(entities)
        except Exception as e:  # safety-net: neo4j + mapping errors
            return Result.fail(
                Errors.database("list_for_submission", f"Failed to list reports: {e!s}")
            )

    async def get_reports_for_student_exercise(
        self, student_uid: str, exercise_uid: str
    ) -> Result[list[ExerciseReport]]:
        """All ExerciseReports for a student's submissions on a given exercise.

        Traverses: (Student)-[:OWNS]->(Submission)-[:FULFILLS_EXERCISE]->(Exercise)
                   (Report)-[:REPORT_FOR]->(Submission)

        Returns typed ExerciseReport instances ordered by created_at DESC
        (newest-first — natural reading order for "most recent feedback").
        """
        cypher = f"""
            MATCH (student:User {{uid: $student_uid}})-[:{RelationshipName.OWNS.value}]->(sub:Entity)
            MATCH (sub)-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(ex:Entity {{uid: $exercise_uid, entity_type: 'exercise'}})
            MATCH (n:ExerciseReport)-[:{RelationshipName.REPORT_FOR.value}]->(sub)
            RETURN n
            ORDER BY n.created_at DESC
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(
                    cypher, {"student_uid": student_uid, "exercise_uid": exercise_uid}
                )
                records = await result.data()
            entities = [from_neo4j_node(record["n"], self.entity_class) for record in records]
            return Result.ok(entities)
        except Exception as e:  # safety-net: neo4j + mapping errors
            return Result.fail(
                Errors.database(
                    "get_reports_for_student_exercise",
                    f"Failed to list reports: {e!s}",
                )
            )

    async def get_reports_by_teacher(
        self, teacher_uid: str, limit: int = 50
    ) -> Result[list[ExerciseReport]]:
        """All ExerciseReports authored by a teacher, newest first.

        Uses user_uid field (denormalized on creation) for O(1) lookup.
        Returns typed ExerciseReport instances.
        """
        cypher = """
            MATCH (n:ExerciseReport {user_uid: $teacher_uid})
            RETURN n
            ORDER BY n.created_at DESC
            LIMIT $limit
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(cypher, {"teacher_uid": teacher_uid, "limit": limit})
                records = await result.data()
            entities = [from_neo4j_node(record["n"], self.entity_class) for record in records]
            return Result.ok(entities)
        except Exception as e:  # safety-net: neo4j + mapping errors
            return Result.fail(
                Errors.database("get_reports_by_teacher", f"Failed to list reports: {e!s}")
            )

    async def get_linked_ku_and_student(self, submission_uid: str) -> Result[list[Neo4jProperties]]:
        """
        Get Ku UIDs and student UID linked to a submission via APPLIES_KNOWLEDGE.

        Used by mastery propagation after AI report generation.

        Returns:
            Records with ku_uid and student_uid fields
        """
        return await self.execute_query(
            f"""
            MATCH (submission:Entity {{uid: $submission_uid}})-[:{RelationshipName.APPLIES_KNOWLEDGE.value}]->(ku:Entity {{entity_type: 'ku'}})
            OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(submission)
            RETURN ku.uid AS ku_uid, student.uid AS student_uid
            """,
            {"submission_uid": submission_uid},
        )
