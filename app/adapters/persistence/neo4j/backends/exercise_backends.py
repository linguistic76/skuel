"""Exercise-family backends: Exercise, RevisedExercise, EntryReport.

The three entities that drive the four-phase learning loop:
Exercise → UserEntry → EntryReport → RevisedExercise → …

PathStep is the curriculum anchor, linked via (PathStep)-[:HAS_EXERCISE]->(Exercise)
(denormalized as Exercise.path_step_uid for PERSONAL scope).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums.pipeline import Pipeline
from core.models.exercises.exercise import Exercise
from core.models.relationship_names import RelationshipName
from core.models.report.entry_report import EntryReport
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
    - get_user_exercises             — OWNS query for user's exercises
    - get_student_exercises          — MEMBER_OF + SHARED_WITH_GROUP traversal
    - get_student_exercises_with_status — Above + FULFILLS_EXERCISE submission check
                                          + living-intent in-progress check
    - get_exercises_for_curriculum   — Reverse REQUIRES_KNOWLEDGE lookup
    - link_to_curriculum             — MERGE REQUIRES_KNOWLEDGE relationship
    - unlink_from_curriculum         — DELETE REQUIRES_KNOWLEDGE relationship
    - get_required_knowledge         — Query all KUs required by an exercise
    - get_exercise_for_submission    — FULFILLS_EXERCISE reverse lookup
    - link_to_path_step              — MERGE HAS_EXERCISE (path_step -> exercise)
    """

    async def link_to_path_step(self, exercise_uid: str, path_step_uid: str) -> Result[bool]:
        """
        Create HAS_EXERCISE relationship from PathStep to Exercise.

        Dual-write partner for Exercise.path_step_uid — keeps the denormalized
        field and the graph edge in sync. Called during create_exercise() for
        PERSONAL-scope exercises.

        Args:
            exercise_uid: Exercise UID (entity_type='exercise')
            path_step_uid: PathStep UID (entity_type='path_step')

        Returns:
            Result[bool] - True if relationship created or already exists
        """
        result = await self.execute_query(
            f"""
            MATCH (ps:Entity {{uid: $path_step_uid, entity_type: 'path_step'}})
            MATCH (exercise:Entity {{uid: $exercise_uid, entity_type: 'exercise'}})
            MERGE (ps)-[r:{RelationshipName.HAS_EXERCISE}]->(exercise)
            ON CREATE SET r.created_at = datetime()
            RETURN true as success
            """,
            {"exercise_uid": exercise_uid, "path_step_uid": path_step_uid},
        )
        if result.is_error:
            return Result.fail(result)
        records = result.value or []
        if not records:
            return Result.fail(
                Errors.not_found(
                    resource="PathStep or Exercise",
                    identifier=f"{path_step_uid} -> {exercise_uid}",
                )
            )
        return Result.ok(True)

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
        items: list[RequiredKnowledgeResult] = [
            cast("RequiredKnowledgeResult", dict(record)) for record in (result.value or [])
        ]
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
        """Get assigned exercises for a student via MEMBER_OF -> Group <- SHARED_WITH_GROUP.

        Args:
            user_uid: Student UID

        Returns:
            Result containing exercise node records
        """
        return await self.execute_query(
            f"""
            MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.MEMBER_OF}]->(group:Group)
            MATCH (exercise:Entity {{entity_type: 'exercise'}})-[:{RelationshipName.SHARED_WITH_GROUP}]->(group)
            WHERE exercise.scope = 'assigned'
            RETURN exercise
            ORDER BY exercise.due_date ASC, exercise.created_at DESC
            """,
            {"user_uid": user_uid},
        )

    async def get_student_exercises_with_status(
        self, user_uid: UserUID, limit: int | None = None
    ) -> Result[list[Neo4jProperties]]:
        """Get assigned exercises with submission + report status for a student.

        Returns exercise properties enriched with:
        - has_submission: bool
        - submission_uid: str | None (most recent submission)
        - submission_status: str | None
        - has_report: bool
        - report_uid: str | None (most recent report)
        - report_outcome: str | None (assessment_outcome on the report)
        - has_in_progress: bool (vault living entry declares this exercise)
        - in_progress_uid: str | None (newest living entry)
        - group_name: str

        The living-entry match is the vault exercise channel's declared intent:
        an owned UserEntry whose ``fulfills_exercise_uid`` property names the
        exercise but which carries NO FULFILLS_EXERCISE edge — the edge is
        exclusive to frozen turn-in copies, so property-without-edge is exactly
        the work-in-progress file.

        Args:
            user_uid: Student UID
            limit: Cap the number of returned records; ``None`` returns all

        Returns:
            Result containing enriched exercise records
        """
        limit_clause = "LIMIT $limit" if limit is not None else ""
        return await self.execute_query(
            f"""
            MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.MEMBER_OF}]->(group:Group)
            MATCH (exercise:Entity {{entity_type: 'exercise'}})-[:{RelationshipName.SHARED_WITH_GROUP}]->(group)
            WHERE exercise.scope = 'assigned'
            OPTIONAL MATCH (user)-[:{RelationshipName.OWNS}]->(sub:Entity)-[:{RelationshipName.FULFILLS_EXERCISE}]->(exercise)
            OPTIONAL MATCH (report:Entity)-[:{RelationshipName.REPORT_FOR}]->(sub)
            WITH user, exercise, group, sub, report
            ORDER BY sub.created_at DESC
            WITH user, exercise, group,
                 collect(sub)[0] AS latest_sub,
                 collect(report)[0] AS latest_report
            OPTIONAL MATCH (user)-[:{RelationshipName.OWNS}]->(living:Entity {{entity_type: 'user_entry'}})
            WHERE living.fulfills_exercise_uid = exercise.uid
              AND NOT (living)-[:{RelationshipName.FULFILLS_EXERCISE}]->(:Entity)
            WITH exercise, group, latest_sub, latest_report, living
            ORDER BY living.updated_at DESC
            WITH exercise, group, latest_sub, latest_report,
                 collect(living)[0] AS latest_living
            RETURN exercise,
                   latest_sub.uid AS submission_uid,
                   latest_sub.status AS submission_status,
                   latest_sub IS NOT NULL AS has_submission,
                   latest_report.uid AS report_uid,
                   latest_report.assessment_outcome AS report_outcome,
                   latest_report IS NOT NULL AS has_report,
                   latest_living.uid AS in_progress_uid,
                   latest_living IS NOT NULL AS has_in_progress,
                   group.title AS group_name
            ORDER BY exercise.due_date ASC, exercise.created_at DESC
            {limit_clause}
            """,
            {"user_uid": user_uid, "limit": limit},
        )

    async def get_enrolled_ps_exercises_with_status(
        self, user_uid: UserUID, limit: int | None = None
    ) -> Result[list[Neo4jProperties]]:
        """Get personal + curriculum exercises linked to PathSteps the user is enrolled in.

        Returns the same shape as get_student_exercises_with_status() so results
        can be merged at the service layer. Exercises are discovered via:
            (user)-[:IN_PROGRESS]->(ps)-[:HAS_EXERCISE]->(exercise)
        covering the user's own PathStep-anchored templates (scope=personal) and
        vault-authored shared exercises (scope=curriculum).

        Args:
            user_uid: Student UID
            limit: Cap the number of returned records; ``None`` returns all

        Returns:
            Result containing enriched exercise records (group_name is empty string)
        """
        limit_clause = "LIMIT $limit" if limit is not None else ""
        return await self.execute_query(
            f"""
            MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.IN_PROGRESS}]->(ps:Entity)
            MATCH (ps)-[:{RelationshipName.HAS_EXERCISE}]->(exercise:Entity {{entity_type: 'exercise'}})
            WHERE exercise.scope IN ['personal', 'curriculum']
            WITH DISTINCT user, exercise
            OPTIONAL MATCH (user)-[:{RelationshipName.OWNS}]->(sub:Entity)-[:{RelationshipName.FULFILLS_EXERCISE}]->(exercise)
            OPTIONAL MATCH (report:Entity)-[:{RelationshipName.REPORT_FOR}]->(sub)
            WITH user, exercise, sub, report
            ORDER BY sub.created_at DESC
            WITH user, exercise,
                 collect(sub)[0] AS latest_sub,
                 collect(report)[0] AS latest_report
            OPTIONAL MATCH (user)-[:{RelationshipName.OWNS}]->(living:Entity {{entity_type: 'user_entry'}})
            WHERE living.fulfills_exercise_uid = exercise.uid
              AND NOT (living)-[:{RelationshipName.FULFILLS_EXERCISE}]->(:Entity)
            WITH exercise, latest_sub, latest_report, living
            ORDER BY living.updated_at DESC
            WITH exercise, latest_sub, latest_report,
                 collect(living)[0] AS latest_living
            RETURN exercise,
                   latest_sub.uid AS submission_uid,
                   latest_sub.status AS submission_status,
                   latest_sub IS NOT NULL AS has_submission,
                   latest_report.uid AS report_uid,
                   latest_report.assessment_outcome AS report_outcome,
                   latest_report IS NOT NULL AS has_report,
                   latest_living.uid AS in_progress_uid,
                   latest_living IS NOT NULL AS has_in_progress,
                   '' AS group_name
            ORDER BY exercise.created_at DESC
            {limit_clause}
            """,
            {"user_uid": user_uid, "limit": limit},
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
            MATCH (ps:Entity {{uid: $ps_uid}})-[:{RelationshipName.HAS_EXERCISE}]->(exercise:Entity {{entity_type: 'exercise'}})
            OPTIONAL MATCH (user:User {{uid: $user_uid}})-[:{RelationshipName.OWNS}]->(sub:Entity)-[:{RelationshipName.FULFILLS_EXERCISE}]->(exercise)
            OPTIONAL MATCH (report:Entity)-[:{RelationshipName.REPORT_FOR}]->(sub)
            WITH exercise, sub, report
            ORDER BY sub.created_at DESC
            WITH exercise,
                 collect(sub)[0] AS latest_sub,
                 collect(report)[0] AS latest_report
            OPTIONAL MATCH (u:User {{uid: $user_uid}})-[:{RelationshipName.OWNS}]->(living:Entity {{entity_type: 'user_entry'}})
            WHERE living.fulfills_exercise_uid = exercise.uid
              AND NOT (living)-[:{RelationshipName.FULFILLS_EXERCISE}]->(:Entity)
            WITH exercise, latest_sub, latest_report, living
            ORDER BY living.updated_at DESC
            WITH exercise, latest_sub, latest_report,
                 collect(living)[0] AS latest_living
            RETURN exercise,
                   latest_sub.uid AS submission_uid,
                   latest_sub.status AS submission_status,
                   latest_sub IS NOT NULL AS has_submission,
                   latest_report.uid AS report_uid,
                   latest_report.assessment_outcome AS report_outcome,
                   latest_report IS NOT NULL AS has_report,
                   latest_living.uid AS in_progress_uid,
                   latest_living IS NOT NULL AS has_in_progress,
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
            cast("CurriculumExerciseResult", dict(record)) for record in (result.value or [])
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
        OPTIONAL MATCH (s:Entity:UserEntry)-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(exercise)
          WHERE s.pipeline = $pipeline
            AND EXISTS {{ (s)-[:{RelationshipName.SHARED_WITH_GROUP.value}]->(:Group)<-[:{RelationshipName.OWNS.value}]-(user) }}
        WITH exercise, count(DISTINCT s) AS total_count,
             count(DISTINCT CASE WHEN s.status = 'completed' THEN s.uid END) AS reviewed_count
        RETURN exercise.uid AS uid, exercise.title AS title,
               exercise.scope AS scope, exercise.created_at AS created_at,
               total_count, reviewed_count,
               total_count - reviewed_count AS pending_count
        ORDER BY exercise.created_at DESC
        """
        return await self.execute_query(
            query, {"teacher_uid": teacher_uid, "pipeline": Pipeline.TEACHER_REVIEW.value}
        )


class RevisedExerciseBackend(UniversalNeo4jBackend["RevisedExercise"]):
    """
    Domain backend for RevisedExercise entities.

    Provides relationship-specific Cypher for the four-phase learning loop:
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
            WHERE fb.entity_type IN ['entry_report', 'activity_report']
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
        - (EntryReport)-[:REPORT_FOR]->(UserEntry) exists
        - (Student)-[:OWNS]->(UserEntry)
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
            MATCH (fb:Entity {uid: $report_uid})-[:REPORT_FOR]->(submission:Entity:UserEntry)
            MATCH (student:User {uid: $student_uid})-[:OWNS]->(submission)
            WHERE EXISTS { (submission)-[:FULFILLS_EXERCISE|FULFILLS_REVISED_EXERCISE]->() }
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
            cast("RevisionChainResult", dict(record)) for record in (result.value or [])
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


class EntryReportBackend(UniversalNeo4jBackend[EntryReport]):
    """
    Domain backend for EntryReport entities.

    Provides typed relationship-specific reads for the four-phase learning loop.
    All reads assert both labels (``:Entity:EntryReport``) and return
    ``list[EntryReport]`` via ``from_neo4j_node``.

    Report *creation* works through ``create_report_node`` and ``create_report_and_revised_exercise``
    to ensure the EntryReport domain backend completely owns its own lifecycle.
    """

    async def create_report_node(self, params: dict[str, Any]) -> Result[list[Neo4jProperties]]:
        """Create EntryReport node, link via REPORT_FOR, share with student, update submission.

        Canonical report-creation path for both teacher (HUMAN) and AI (LLM) reports.

        Params:
            report_uid: Submission UID to attach the report to
            report_entity_uid: UID for the new EntryReport node
            author_uid: UID of the human who authored the report — the teacher
                for HUMAN reports, ``None`` for LLM/AI reports (no human author,
                per the EntryReport contract).
            feedback, title, entity_type, completed_status, processor_type,
                assessment_outcome, now: standard report fields
            report_file_path: optional path to uploaded .md file (may be None)
            submission_status: new status to transition the submission to, or
                None to leave submission.status unchanged (AI reports pass None)
            allowed_from_statuses: list of current-status values permitted for
                the transition, or None to skip the guard (AI reports pass None)
            visibility: report node visibility — ``'shared'`` for teacher/AI
                reports (student gets a SHARES_WITH grant), ``'private'`` for
                self-owned journal responses (no separate grant; owner reads it).
            create_student_share: when True (teacher/AI), create the
                ``(student)-[:SHARES_WITH]->(report)`` grant; when False
                (journal responses), skip it — the owner already owns the node.

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
        // Multi-label: :Entity for cross-domain queries, :EntryReport for
        // typed reads via EntryReportBackend (CLAUDE.md: multi-label writes invariant).
        CREATE (fb:Entity:EntryReport {{
            uid: $report_entity_uid,
            title: $title,
            entity_type: $entity_type,
            user_uid: CASE WHEN student IS NOT NULL THEN student.uid ELSE $author_uid END,
            author_uid: $author_uid,
            status: $completed_status,
            visibility: $visibility,
            processor_type: $processor_type,
            assessment_outcome: $assessment_outcome,
            processed_content: $feedback,
            report_file_path: $report_file_path,
            created_by: $author_uid,
            created_at: datetime($now),
            updated_at: datetime($now)
        }})

        // Owner = the submission's student when present, else the author.
        // OPTIONAL author MATCH so LLM journal responses can pass author_uid=null
        // (no human author) without dropping the row — the entry owner still owns it.
        WITH submission, student, fb
        OPTIONAL MATCH (author:User {{uid: $author_uid}})
        WITH submission, student, fb, COALESCE(student, author) AS owner
        WHERE owner IS NOT NULL
        CREATE (owner)-[:{RelationshipName.OWNS.value}]->(fb)
        CREATE (fb)-[:{RelationshipName.REPORT_FOR.value}]->(submission)

        WITH submission, student, fb
        FOREACH (_ IN CASE WHEN student IS NOT NULL AND $create_student_share THEN [1] ELSE [] END |
            CREATE (student)-[:{RelationshipName.SHARES_WITH.value} {{shared_at: datetime($now), role: 'student'}}]->(fb)
        )

        RETURN submission.uid as uid,
               submission.status as status,
               student.uid as student_uid,
               fb.uid as report_entity_uid
        """
        return await self.execute_query(query, params)

    async def create_report_and_revised_exercise(
        self, params: dict[str, Any]
    ) -> Result[list[Neo4jProperties]]:
        """Atomically create EntryReport + RevisedExercise in one transaction.

        Combines the two-phase revision request (create_report_node + RevisedExercise
        create with relationships) into a single Cypher query. All-or-nothing: if any
        part fails, no partial state is left behind.

        Params required:
            Phase 1 (EntryReport): report_uid (submission UID), report_entity_uid,
                author_uid, feedback, report_file_path, title, entity_type,
                submission_status, completed_status, processor_type,
                assessment_outcome, allowed_from_statuses, now
            Phase 2 (RevisedExercise): re_props (from to_neo4j_node), re_uid,
                original_exercise_uid
        """
        query = f"""
        // Phase 1: Match submission with status guard, create EntryReport
        MATCH (submission:Entity {{uid: $report_uid}})
        WHERE submission.status IN $allowed_from_statuses
        OPTIONAL MATCH (student:User)-[:{RelationshipName.OWNS.value}]->(submission)

        SET submission.status = $submission_status,
            submission.updated_at = datetime($now)

        CREATE (fb:Entity:EntryReport {{
            uid: $report_entity_uid,
            title: $title,
            entity_type: $entity_type,
            user_uid: CASE WHEN student IS NOT NULL THEN student.uid ELSE $author_uid END,
            author_uid: $author_uid,
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
        WITH submission, student, fb, author,
             CASE WHEN student IS NOT NULL THEN student ELSE author END AS owner
        CREATE (owner)-[:{RelationshipName.OWNS.value}]->(fb)
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

        // Auto-share RevisedExercise with student.
        // re is freshly CREATEd in this tx, so no prior share can exist — CREATE
        // with inline props puts shared_at on the relationship (matching the report
        // share above); ON CREATE SET inside FOREACH can't bind the rel var.
        WITH submission, student, fb, re, revision_number
        FOREACH (_ IN CASE WHEN student IS NOT NULL THEN [1] ELSE [] END |
            CREATE (student)-[:{RelationshipName.SHARES_WITH.value} {{
                shared_at: datetime($now), role: 'student'
            }}]->(re)
        )

        RETURN submission.uid AS uid,
               submission.status AS status,
               CASE WHEN student IS NOT NULL THEN student.uid ELSE null END AS student_uid,
               fb.uid AS report_entity_uid,
               re.uid AS revised_exercise_uid,
               revision_number
        """
        return await self.execute_query(query, params)

    async def get(self, uid: str) -> Result[EntryReport | None]:
        """Typed single-fetch for EntryReport by UID.

        Overrides ``UniversalNeo4jBackend.get`` to project ``subject_uid``
        from the REPORT_FOR edge so the hydrated EntryReport carries the
        submission UID it reports on. Returns ``Result.ok(None)`` when no
        node matches (same not-found-is-not-error contract as the parent).
        """
        cypher = f"""
            MATCH (n:EntryReport {{uid: $uid}})
            OPTIONAL MATCH (n)-[:{RelationshipName.REPORT_FOR.value}]->(sub:Entity)
            RETURN n{{.*, subject_uid: sub.uid}} AS n
        """
        try:
            async with self.driver.session() as session:
                result = await session.run(cypher, {"uid": uid})
                records = await result.data()
            if not records:
                return Result.ok(None)
            entity = from_neo4j_node(records[0]["n"], self.entity_class)
            return Result.ok(entity)
        except Exception as e:  # safety-net: neo4j + mapping errors
            return Result.fail(Errors.database("get", f"Failed to fetch EntryReport: {e!s}"))

    async def list_for_submission(self, submission_uid: str) -> Result[list[EntryReport]]:
        """Return all reports attached to a submission, as typed EntryReport
        instances, ordered by created_at ASC (oldest → newest review round).

        Replaces the former dict-returning get_report_for_submission (this
        backend) and the dict-returning UserEntryBackend.get_report_history.
        Typed all the way to the route handler — no TypedDict projection.
        """
        cypher = f"""
            MATCH (n:EntryReport)-[:{RelationshipName.REPORT_FOR.value}]->(:Entity {{uid: $submission_uid}})
            RETURN n{{.*, subject_uid: $submission_uid}} AS n
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
    ) -> Result[list[EntryReport]]:
        """All EntryReports for a student's submissions on a given exercise.

        Traverses: (Student)-[:OWNS]->(UserEntry)-[:FULFILLS_EXERCISE]->(Exercise)
                   (EntryReport)-[:REPORT_FOR]->(UserEntry)

        Returns typed EntryReport instances ordered by created_at DESC
        (newest-first — natural reading order for "most recent feedback").
        """
        cypher = f"""
            MATCH (student:User {{uid: $student_uid}})-[:{RelationshipName.OWNS.value}]->(sub:Entity)
            MATCH (sub)-[:{RelationshipName.FULFILLS_EXERCISE.value}]->(ex:Entity {{uid: $exercise_uid, entity_type: 'exercise'}})
            MATCH (n:EntryReport)-[:{RelationshipName.REPORT_FOR.value}]->(sub)
            RETURN n{{.*, subject_uid: sub.uid}} AS n
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
    ) -> Result[list[EntryReport]]:
        """All EntryReports authored by a teacher, newest first.

        Filters on ``author_uid`` — the dedicated authorship field set at
        report creation time. ``user_uid`` on EntryReport always stores the
        student (access ownership); ``author_uid`` stores the teacher for
        HUMAN reports and is None for LLM/AI reports.

        Returns typed EntryReport instances.
        """
        cypher = f"""
            MATCH (n:EntryReport {{author_uid: $teacher_uid}})
            OPTIONAL MATCH (n)-[:{RelationshipName.REPORT_FOR.value}]->(sub:Entity)
            RETURN n{{.*, subject_uid: sub.uid}} AS n
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
