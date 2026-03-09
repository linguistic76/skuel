"""
Report Relationship Service
=============================

Pure-Cypher Level 1 queries against FEEDBACK_FOR relationships.

Answers intelligence questions about the Report stage of the learning loop:
- Which of the user's submissions are still awaiting a report?
- How many submissions have reports vs. not?

No LLM dependencies — this is a Level 1 graph analytics service.
The higher-level SubmissionReportService (LLM report generation) is a separate concern.

Graph relationships queried:
- FEEDBACK_FOR: (SubmissionReport)-[:FEEDBACK_FOR]->(Submission)
- OWNS: (User)-[:OWNS]->(Submission)

See: /docs/architecture/FEEDBACK_ARCHITECTURE.md
"""

from typing import TYPE_CHECKING, Any

from core.models.enums.entity_enums import EntityType
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import BackendOperations


class ReportRelationshipService:
    """
    Pure-Cypher relationship queries for the Report stage of the learning loop.

    Provides the intelligence layer with graph-level questions about FEEDBACK_FOR
    relationships — no LLM, no AI. Just graph queries.

    Used by UserContextIntelligence to answer:
    - "Does this user have submissions that haven't been reviewed yet?"
    - "What's the overall report completion rate for this user?"

    See: /docs/architecture/FEEDBACK_ARCHITECTURE.md
    """

    def __init__(self, backend: "BackendOperations[Any]") -> None:
        self.backend = backend
        self.logger = get_logger("skuel.services.report_relationship")

    # ========================================================================
    # INTELLIGENCE QUERIES
    # ========================================================================

    async def get_pending_submissions(self, user_uid: str) -> Result[list[str]]:
        """
        Get UIDs of submissions that have not yet received feedback.

        A "pending" submission is one owned by the user that has no
        FEEDBACK_FOR relationship pointing to it.

        Graph: (User)-[:OWNS]->(submission:Entity) WHERE NOT ()-[:FEEDBACK_FOR]->(submission)

        Args:
            user_uid: User identifier

        Returns:
            Result containing list of submission UIDs awaiting feedback (most recent first)
        """
        cypher = """
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(submission:Entity)
        WHERE submission.entity_type IN $submission_types
          AND NOT ()-[:FEEDBACK_FOR]->(submission)
        RETURN submission.uid AS uid
        ORDER BY submission.created_at DESC
        LIMIT 20
        """

        result = await self.backend.execute_query(
            cypher,
            {
                "user_uid": user_uid,
                "submission_types": [
                    EntityType.SUBMISSION.value,
                    EntityType.JOURNAL.value,
                ],
            },
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok([r["uid"] for r in (result.value or []) if r["uid"]])

    async def get_unsubmitted_exercises(
        self, user_uid: str, limit: int = 5
    ) -> Result[list[dict[str, str | None]]]:
        """
        Exercises assigned to this user (via group) with no submission yet.

        Graph traversal:
        (User)-[:MEMBER_OF]->(Group)<-[:FOR_GROUP]-(Exercise)
        WHERE NOT (User)-[:OWNS]->(:Submission)-[:FULFILLS_EXERCISE]->(Exercise)

        Args:
            user_uid: User identifier
            limit: Maximum exercises to return (default 5, ordered by due_date ASC)

        Returns:
            Result containing list of dicts with: uid, title, due_date (ISO string or None)
        """
        cypher = """
        MATCH (user:User {uid: $user_uid})-[:MEMBER_OF]->(group:Group)
        MATCH (exercise:Entity {entity_type: 'exercise', scope: 'assigned'})-[:FOR_GROUP]->(group)
        WHERE NOT (:Entity {user_uid: $user_uid})-[:FULFILLS_EXERCISE]->(exercise)
        RETURN exercise.uid AS uid,
               exercise.title AS title,
               exercise.due_date AS due_date
        ORDER BY exercise.due_date ASC
        LIMIT $limit
        """
        result = await self.backend.execute_query(
            cypher,
            {"user_uid": user_uid, "limit": limit},
        )
        if result.is_error:
            return Result.fail(result.expect_error())
        return Result.ok(
            [
                {
                    "uid": r["uid"],
                    "title": r["title"] or "Untitled Exercise",
                    "due_date": str(r["due_date"]) if r["due_date"] else None,
                }
                for r in (result.value or [])
                if r["uid"]
            ]
        )

    async def get_report_summary(self, user_uid: str) -> Result[dict[str, int]]:
        """
        Get report completion summary for a user.

        Returns counts of submissions with/without reports and total
        report items received.

        Args:
            user_uid: User identifier

        Returns:
            Result containing dict with keys:
                - total_submissions: Total submission + journal count
                - with_feedback: Count that have at least one FEEDBACK_FOR
                - without_feedback: Count that have no FEEDBACK_FOR
                - total_feedback: Total count of feedback entities received
        """
        cypher = """
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(submission:Entity)
        WHERE submission.entity_type IN $submission_types
        OPTIONAL MATCH (fb:Entity)-[:FEEDBACK_FOR]->(submission)
        WITH submission, count(fb) AS feedback_count
        RETURN
            count(submission) AS total_submissions,
            count(CASE WHEN feedback_count > 0 THEN 1 END) AS with_feedback,
            count(CASE WHEN feedback_count = 0 THEN 1 END) AS without_feedback,
            sum(feedback_count) AS total_feedback
        """

        result = await self.backend.execute_query(
            cypher,
            {
                "user_uid": user_uid,
                "submission_types": [
                    EntityType.SUBMISSION.value,
                    EntityType.JOURNAL.value,
                ],
            },
        )
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []
        if not records:
            return Result.ok(
                {
                    "total_submissions": 0,
                    "with_feedback": 0,
                    "without_feedback": 0,
                    "total_feedback": 0,
                }
            )

        record = records[0]
        return Result.ok(
            {
                "total_submissions": record["total_submissions"],
                "with_feedback": record["with_feedback"],
                "without_feedback": record["without_feedback"],
                "total_feedback": record["total_feedback"],
            }
        )

    # ========================================================================
    # LEARNING LOOP CHAIN TRAVERSAL
    # ========================================================================

    async def get_learning_loop_chain(self, exercise_uid: str) -> Result[dict[str, Any]]:
        """
        Traverse the full learning loop chain from an exercise.

        Teacher/admin view: "show me everything related to this exercise."

        Graph pattern (mixed directions):
            (Submission)-[:FULFILLS_EXERCISE]->(Exercise)
            (SubmissionReport)-[:FEEDBACK_FOR]->(Submission)
            (RevisedExercise)-[:RESPONDS_TO_FEEDBACK]->(SubmissionReport)
            (RevisedExercise)-[:REVISES_EXERCISE]->(Exercise)

        Args:
            exercise_uid: UID of the exercise or revised exercise

        Returns:
            Result[dict] with keys: exercise, submissions, feedback, revised_exercises
        """
        cypher = """
        MATCH (ex:Entity {uid: $exercise_uid})
        WHERE ex.entity_type IN ['exercise', 'revised_exercise']
        OPTIONAL MATCH (sub:Entity)-[:FULFILLS_EXERCISE]->(ex)
          WHERE sub.entity_type = 'submission'
        OPTIONAL MATCH (fb:Entity)-[:FEEDBACK_FOR]->(sub)
          WHERE fb.entity_type = 'submission_feedback'
        OPTIONAL MATCH (re:Entity)-[:RESPONDS_TO_FEEDBACK]->(fb)
          WHERE re.entity_type = 'revised_exercise'
        RETURN ex {.uid, .title, .entity_type, .status, .created_at} AS exercise,
               collect(DISTINCT sub {.uid, .title, .status, .created_at, .user_uid}) AS submissions,
               collect(DISTINCT fb {.uid, .title, .processor_type, .created_at}) AS feedback,
               collect(DISTINCT re {.uid, .title, .revision_number, .created_at}) AS revised_exercises
        """
        result = await self.backend.execute_query(cypher, {"exercise_uid": exercise_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []
        if not records or records[0].get("exercise") is None:
            return Result.fail(Errors.not_found(resource="Exercise", identifier=exercise_uid))

        record = records[0]
        return Result.ok(
            {
                "exercise": dict(record["exercise"]) if record["exercise"] else {},
                "submissions": [dict(s) for s in record.get("submissions", []) if s.get("uid")],
                "feedback": [dict(f) for f in record.get("feedback", []) if f.get("uid")],
                "revised_exercises": [
                    dict(r) for r in record.get("revised_exercises", []) if r.get("uid")
                ],
            }
        )

    async def get_submission_chain(self, submission_uid: str) -> Result[dict[str, Any]]:
        """
        Traverse the learning loop chain from a specific submission.

        Student view: "what happened after I submitted?"

        Graph pattern:
            (Submission)-[:FULFILLS_EXERCISE]->(Exercise)
            (SubmissionReport)-[:FEEDBACK_FOR]->(Submission)
            (RevisedExercise)-[:RESPONDS_TO_FEEDBACK]->(SubmissionReport)

        Args:
            submission_uid: UID of the submission

        Returns:
            Result[dict] with keys: submission, exercise, feedback, revised_exercises
        """
        cypher = """
        MATCH (sub:Entity {uid: $submission_uid, entity_type: 'submission'})
        OPTIONAL MATCH (sub)-[:FULFILLS_EXERCISE]->(ex:Entity)
          WHERE ex.entity_type IN ['exercise', 'revised_exercise']
        OPTIONAL MATCH (fb:Entity)-[:FEEDBACK_FOR]->(sub)
          WHERE fb.entity_type = 'submission_feedback'
        OPTIONAL MATCH (re:Entity)-[:RESPONDS_TO_FEEDBACK]->(fb)
          WHERE re.entity_type = 'revised_exercise'
        RETURN sub {.uid, .title, .status, .created_at, .user_uid} AS submission,
               ex {.uid, .title, .entity_type, .status} AS exercise,
               collect(DISTINCT fb {.uid, .title, .processor_type, .created_at}) AS feedback,
               collect(DISTINCT re {.uid, .title, .revision_number, .student_uid, .created_at}) AS revised_exercises
        """
        result = await self.backend.execute_query(cypher, {"submission_uid": submission_uid})
        if result.is_error:
            return Result.fail(result.expect_error())

        records = result.value or []
        if not records or records[0].get("submission") is None:
            return Result.fail(Errors.not_found(resource="Submission", identifier=submission_uid))

        record = records[0]
        return Result.ok(
            {
                "submission": dict(record["submission"]) if record["submission"] else {},
                "exercise": dict(record["exercise"]) if record.get("exercise") else None,
                "feedback": [dict(f) for f in record.get("feedback", []) if f.get("uid")],
                "revised_exercises": [
                    dict(r) for r in record.get("revised_exercises", []) if r.get("uid")
                ],
            }
        )


__all__ = ["ReportRelationshipService"]
