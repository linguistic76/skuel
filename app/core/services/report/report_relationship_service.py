"""
Report Relationship Service
=============================

Graph queries against REPORT_FOR relationships — delegates Cypher to SubmissionsBackend.

Answers intelligence questions about the Report stage of the learning loop:
- Which of the user's submissions are still awaiting a report?
- How many submissions have reports vs. not?

No LLM dependencies — this is a Level 1 graph analytics service.
The higher-level ExerciseReportService (LLM report generation) is a separate concern.

Graph relationships queried:
- REPORT_FOR: (ExerciseReport)-[:REPORT_FOR]->(Submission)
- OWNS: (User)-[:OWNS]->(Submission)

See: /docs/architecture/REPORT_ARCHITECTURE.md
"""

from typing import TYPE_CHECKING

from core.models.enums.entity_enums import EntityType
from core.models.type_hints import UserUID
from core.ports.query_types import LearningLoopChain, ReportSummary, SubmissionChain
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from adapters.persistence.neo4j.domain_backends import SubmissionsBackend


class ReportRelationshipService:
    """
    Pure-Cypher relationship queries for the Report stage of the learning loop.

    Provides the intelligence layer with graph-level questions about REPORT_FOR
    relationships — no LLM, no AI. Just graph queries delegated to SubmissionsBackend.

    Used by UserContextIntelligence to answer:
    - "Does this user have submissions that haven't been reviewed yet?"
    - "What's the overall report completion rate for this user?"

    See: /docs/architecture/REPORT_ARCHITECTURE.md
    """

    _SUBMISSION_TYPES = [
        EntityType.EXERCISE_SUBMISSION.value,
        EntityType.JE_INPUT.value,
    ]

    def __init__(self, backend: "SubmissionsBackend") -> None:
        self.backend = backend
        self.logger = get_logger("skuel.services.report_relationship")

    # ========================================================================
    # INTELLIGENCE QUERIES
    # ========================================================================

    async def get_pending_submissions(self, user_uid: UserUID) -> Result[list[str]]:
        """
        Get UIDs of submissions that have not yet received a report.

        A "pending" submission is one owned by the user that has no
        REPORT_FOR relationship pointing to it.

        Graph: (User)-[:OWNS]->(submission:Entity) WHERE NOT ()-[:REPORT_FOR]->(submission)

        Args:
            user_uid: User identifier

        Returns:
            Result containing list of submission UIDs awaiting report (most recent first)
        """
        result = await self.backend.get_pending_submissions_raw(user_uid, self._SUBMISSION_TYPES)
        if result.is_error:
            return Result.fail(result)

        return Result.ok([str(r["uid"]) for r in (result.value or []) if r["uid"]])

    async def get_unsubmitted_exercises(
        self, user_uid: UserUID, limit: int = 5
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
        result = await self.backend.get_unsubmitted_exercises_raw(user_uid, limit)
        if result.is_error:
            return Result.fail(result)
        return Result.ok(
            [
                {
                    "uid": str(r["uid"]),
                    "title": str(r["title"]) if r["title"] else "Untitled Exercise",
                    "due_date": str(r["due_date"]) if r["due_date"] else None,
                }
                for r in (result.value or [])
                if r["uid"]
            ]
        )

    async def get_report_summary(self, user_uid: UserUID) -> Result[ReportSummary]:
        """
        Get report completion summary for a user.

        Returns counts of submissions with/without reports and total
        report items received.

        Args:
            user_uid: User identifier

        Returns:
            Result containing dict with keys:
                - total_submissions: Total submission + journal count
                - with_report: Count that have at least one REPORT_FOR
                - without_report: Count that have no REPORT_FOR
                - total_reports: Total count of report entities received
        """
        result = await self.backend.get_report_summary_raw(user_uid, self._SUBMISSION_TYPES)
        if result.is_error:
            return Result.fail(result)

        records = result.value or []
        if not records:
            return Result.ok(
                {
                    "total_submissions": 0,
                    "with_report": 0,
                    "without_report": 0,
                    "total_reports": 0,
                }
            )

        record = records[0]
        return Result.ok(
            {
                "total_submissions": int(record["total_submissions"] or 0),
                "with_report": int(record["with_report"] or 0),
                "without_report": int(record["without_report"] or 0),
                "total_reports": int(record["total_reports"] or 0),
            }
        )

    # ========================================================================
    # LEARNING LOOP CHAIN TRAVERSAL
    # ========================================================================

    async def get_learning_loop_chain(self, exercise_uid: str) -> Result[LearningLoopChain]:
        """
        Traverse the full learning loop chain from an exercise.

        Teacher/admin view: "show me everything related to this exercise."

        Graph pattern (mixed directions):
            (Submission)-[:FULFILLS_EXERCISE]->(Exercise)
            (ExerciseReport)-[:REPORT_FOR]->(Submission)
            (RevisedExercise)-[:RESPONDS_TO_REPORT]->(ExerciseReport)
            (RevisedExercise)-[:REVISES_EXERCISE]->(Exercise)

        Args:
            exercise_uid: UID of the exercise or revised exercise

        Returns:
            Result[dict] with keys: exercise, submissions, feedback, revised_exercises
        """
        result = await self.backend.get_learning_loop_chain_raw(exercise_uid)
        if result.is_error:
            return Result.fail(result)

        records = result.value or []
        if not records or records[0].get("exercise") is None:
            return Result.fail(Errors.not_found(resource="Exercise", identifier=exercise_uid))

        record = records[0]
        submissions = list(record.get("submissions") or [])  # type: ignore[arg-type]
        feedback = list(record.get("feedback") or [])  # type: ignore[arg-type]
        revised = list(record.get("revised_exercises") or [])  # type: ignore[arg-type]
        return Result.ok(
            {
                "exercise": dict(record["exercise"]) if record["exercise"] else {},  # type: ignore[arg-type]
                "submissions": [dict(s) for s in submissions if s.get("uid")],  # type: ignore[union-attr]
                "feedback": [dict(f) for f in feedback if f.get("uid")],  # type: ignore[union-attr]
                "revised_exercises": [dict(r) for r in revised if r.get("uid")],  # type: ignore[union-attr]
            }
        )

    async def get_submission_chain(self, submission_uid: str) -> Result[SubmissionChain]:
        """
        Traverse the learning loop chain from a specific submission.

        Student view: "what happened after I submitted?"

        Graph pattern:
            (Submission)-[:FULFILLS_EXERCISE]->(Exercise)
            (ExerciseReport)-[:REPORT_FOR]->(Submission)
            (RevisedExercise)-[:RESPONDS_TO_REPORT]->(ExerciseReport)

        Args:
            submission_uid: UID of the submission

        Returns:
            Result[dict] with keys: submission, exercise, feedback, revised_exercises
        """
        result = await self.backend.get_submission_chain_raw(submission_uid)
        if result.is_error:
            return Result.fail(result)

        records = result.value or []
        if not records or records[0].get("submission") is None:
            return Result.fail(Errors.not_found(resource="Submission", identifier=submission_uid))

        record = records[0]
        feedback = list(record.get("feedback") or [])  # type: ignore[arg-type]
        revised = list(record.get("revised_exercises") or [])  # type: ignore[arg-type]
        return Result.ok(
            {
                "submission": dict(record["submission"]) if record["submission"] else {},  # type: ignore[arg-type]
                "exercise": dict(record["exercise"]) if record.get("exercise") else None,  # type: ignore[arg-type]
                "feedback": [dict(f) for f in feedback if f.get("uid")],  # type: ignore[union-attr]
                "revised_exercises": [dict(r) for r in revised if r.get("uid")],  # type: ignore[union-attr]
            }
        )


__all__ = ["ReportRelationshipService"]
