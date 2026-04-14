"""
UserEntry Assessment + Teacher Review Mixin — ADR-054 Step 4
=============================================================

Wrapper over ``_SubmissionAssessmentMixin`` exposing the method names
declared by ``UserEntryAssessmentOperations``. Adds
``get_review_queue_by_groups`` — the new SHARED_WITH_GROUP pattern for the
teacher review queue, symmetric with ADR-053 teacher→student sharing.

The old OWNS-based ``get_review_queue`` stays inherited and usable by the
legacy backend; the new method is what post-migration callers use.
"""

from __future__ import annotations

from adapters.persistence.neo4j._submission_assessment_mixin import (
    _SubmissionAssessmentMixin,
)
from core.models.enums.pipeline import Pipeline
from core.models.relationship_names import RelationshipName
from core.models.type_hints import Neo4jProperties
from core.utils.result_simplified import Result


class _UserEntryAssessmentMixin(_SubmissionAssessmentMixin):
    """Assessment + teacher-review wrappers for ``UserEntry``.

    Inherited unchanged from ``_SubmissionAssessmentMixin``:
        verify_teacher_authority, create_assessment_relationship,
        auto_share_assessment_with_student, get_assessments_for_student_raw,
        get_report_file_path, approve_and_get_linked_kus, verify_teacher_access

    See ``UserEntryBackend`` in ``backends/user_entry_backend.py`` for the
    composed class.
    """

    # ------------------------------------------------------------------
    # NEW — graph-pattern review queue via SHARED_WITH_GROUP
    # ------------------------------------------------------------------

    async def get_review_queue_by_groups(
        self,
        teacher_uid: str,
        status_filter: list[str] | None = None,
    ) -> Result[list[Neo4jProperties]]:
        """Teacher's pending review queue via ``SHARED_WITH_GROUP``.

        Graph pattern — no role gate at the Cypher level. Route-level role
        checks remain authoritative for access.

        Symmetric with ADR-053 teacher→student assignment sharing: an entry
        lands in a teacher's queue because the student (or auto-share
        default) explicitly shared it to a group the teacher owns.
        """
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

    # ------------------------------------------------------------------
    # Wrapper renames (submission -> entry terminology)
    # ------------------------------------------------------------------

    async def get_entries_for_exercise_review(
        self, exercise_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """All entries against an exercise (teacher review view)."""
        return await self.get_submissions_for_exercise_review(exercise_uid=exercise_uid)

    async def get_student_entries_for_teacher(
        self, teacher_uid: str, student_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """All entries owned by a student (admin oversight view)."""
        return await self.get_student_submissions_for_teacher(
            _teacher_uid=teacher_uid, student_uid=student_uid
        )

    async def update_entry_score(
        self, entry_uid: str, score: float
    ) -> Result[list[Neo4jProperties]]:
        """Update the score on an entry explicitly."""
        return await self.update_submission_score(submission_uid=entry_uid, score=score)

    async def get_entry_detail_for_teacher(
        self, entry_uid: str, teacher_uid: str
    ) -> Result[list[Neo4jProperties]]:
        """Full entry detail for teacher review (admin oversight view)."""
        return await self.get_submission_detail_for_teacher(
            submission_uid=entry_uid, teacher_uid=teacher_uid
        )
