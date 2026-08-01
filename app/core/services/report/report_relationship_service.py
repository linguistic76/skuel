"""
Report Relationship Service
=============================

Graph queries against REPORT_FOR relationships — delegates Cypher to UserEntryBackend.

Answers intelligence questions about the Report stage of the learning loop:
- Which of the user's submissions are still awaiting a report?
- How many submissions have reports vs. not?

No LLM dependencies — this is a Level 1 graph analytics service.
The higher-level EntryReportService (LLM report generation) is a separate concern.

Graph relationships queried:
- REPORT_FOR: (EntryReport)-[:REPORT_FOR]->(UserEntry)
- OWNS: (User)-[:OWNS]->(UserEntry)

See: /docs/architecture/REPORT_ARCHITECTURE.md
"""

from typing import TYPE_CHECKING, Any, cast

from core.models.type_hints import UserUID
from core.ports.query_types import (
    ExchangeThread,
    ExchangeThreadEntry,
    ExchangeThreadReport,
    ExchangeThreadRevision,
    LearningLoopChain,
    ReportSummary,
    SubmissionChain,
)
from core.utils.logging import get_logger
from core.utils.neo4j_props import coerce_int
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.enums.pipeline import Pipeline
    from core.ports.user_entry_protocols import UserEntryReportQueryOperations


class ReportRelationshipService:
    """
    Pure-Cypher relationship queries for the Report stage of the learning loop.

    Provides the intelligence layer with graph-level questions about REPORT_FOR
    relationships — no LLM, no AI. Just graph queries delegated to the port
    (UserEntryReportQueryOperations).

    Used by UserContextIntelligence to answer:
    - "Does this user have submissions that haven't been reviewed yet?"
    - "What's the overall report completion rate for this user?"

    See: /docs/architecture/REPORT_ARCHITECTURE.md
    """

    def __init__(self, backend: "UserEntryReportQueryOperations") -> None:
        self.backend = backend
        self.logger = get_logger("skuel.services.report_relationship")

    # ========================================================================
    # INTELLIGENCE QUERIES
    # ========================================================================

    async def get_pending_submissions(
        self, user_uid: UserUID, pipelines: "list[Pipeline] | None" = None
    ) -> Result[list[str]]:
        """
        Get UIDs of submissions that have not yet received a report.

        A "pending" submission is one owned by the user that has no
        REPORT_FOR relationship pointing to it.

        Graph: (User)-[:OWNS]->(submission:Entity) WHERE NOT ()-[:REPORT_FOR]->(submission)

        Args:
            user_uid: User identifier
            pipelines: Optional pipeline filter — when given, only entries whose
                ``pipeline`` is in this set are returned (e.g. journal pipelines
                for the "entries awaiting a response" surface, ADR-069).

        Returns:
            Result containing list of submission UIDs awaiting report (most recent first)
        """
        result = await self.backend.get_pending_entries_raw(
            user_uid,
            pipelines=[p.value for p in pipelines] if pipelines else None,
        )
        if result.is_error:
            return Result.fail(result)

        return Result.ok([str(r["uid"]) for r in (result.value or []) if r["uid"]])

    async def get_unsubmitted_exercises(
        self, user_uid: UserUID, limit: int = 5
    ) -> Result[list[dict[str, str | None]]]:
        """
        Exercises assigned to this user (via group) with no submission yet.

        Graph traversal:
        (User)-[:MEMBER_OF]->(Group)<-[:SHARED_WITH_GROUP]-(Exercise)
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
        result = await self.backend.get_entry_report_summary_raw(user_uid)
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
                "total_submissions": coerce_int(record["total_submissions"]),
                "with_report": coerce_int(record["with_report"]),
                "without_report": coerce_int(record["without_report"]),
                "total_reports": coerce_int(record["total_reports"]),
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
            (UserEntry)-[:FULFILLS_EXERCISE]->(Exercise)
            (EntryReport)-[:REPORT_FOR]->(UserEntry)
            (RevisedExercise)-[:RESPONDS_TO_REPORT]->(EntryReport)
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

        record = cast("dict[str, Any]", records[0])
        submissions: list[dict[str, Any]] = list(record.get("submissions") or [])
        feedback: list[dict[str, Any]] = list(record.get("feedback") or [])
        revised: list[dict[str, Any]] = list(record.get("revised_exercises") or [])
        return Result.ok(
            {
                "exercise": dict(record["exercise"]) if record["exercise"] else {},
                "submissions": [dict(s) for s in submissions if s.get("uid")],
                "feedback": [dict(f) for f in feedback if f.get("uid")],
                "revised_exercises": [dict(r) for r in revised if r.get("uid")],
            }
        )

    async def get_exchange_thread(
        self, exercise_uid: str, student_uid: str, viewer_uid: str | None = None
    ) -> Result[ExchangeThread]:
        """
        One (student, root exercise) exchange — the thread view's single read.

        Returns every artifact of the exchange (the student's entries against
        the exercise, the reports on them, the revision requests responding to
        those reports) for the /exchange thread page (feedback-loop UX arc C5).

        Not-found covers BOTH a missing exercise and an exercise this student
        has never submitted against: an empty thread and a nonexistent one are
        deliberately indistinguishable, so the page cannot be used to probe
        which exercise UIDs exist. In teacher mode that includes an exchange
        whose entries the student directed only to another teacher's classroom
        — scoped out entirely, it reads as not-found too.

        Args:
            exercise_uid: UID of the root exercise.
            student_uid: The student whose exchange to read (already
                access-checked by the caller when it is not the viewer).
            viewer_uid: Teacher-mode scope (``None`` = self view) — only
                entries shared with an active group this viewer owns are in
                the chain (the Model B entry-level gate).

        Returns:
            Result[ExchangeThread] — exercise identity + entries/reports/
            revisions, each ``created_at`` an ISO-8601 string.
        """
        result = await self.backend.get_exchange_thread_raw(
            exercise_uid, student_uid, viewer_uid=viewer_uid
        )
        if result.is_error:
            return Result.fail(result)

        records = result.value or []
        record = cast("dict[str, Any]", records[0]) if records else {}
        exercise = record.get("exercise")
        entries = [dict(e) for e in (record.get("entries") or []) if e.get("uid")]
        if exercise is None or not entries:
            return Result.fail(Errors.not_found(resource="Exchange", identifier=exercise_uid))

        reports = [dict(r) for r in (record.get("reports") or []) if r.get("uid")]
        revisions = [dict(r) for r in (record.get("revisions") or []) if r.get("uid")]
        return Result.ok(
            ExchangeThread(
                exercise_uid=str(exercise.get("uid") or exercise_uid),
                exercise_title=str(exercise.get("title") or "") or exercise_uid,
                student_uid=student_uid,
                entries=cast("list[ExchangeThreadEntry]", entries),
                reports=cast("list[ExchangeThreadReport]", reports),
                revisions=cast("list[ExchangeThreadRevision]", revisions),
            )
        )

    async def get_submission_chain(self, submission_uid: str) -> Result[SubmissionChain]:
        """
        Traverse the learning loop chain from a specific submission.

        Student view: "what happened after I submitted?"

        Graph pattern:
            (UserEntry)-[:FULFILLS_EXERCISE]->(Exercise)
            (EntryReport)-[:REPORT_FOR]->(UserEntry)
            (RevisedExercise)-[:RESPONDS_TO_REPORT]->(EntryReport)

        Args:
            submission_uid: UID of the submission

        Returns:
            Result[dict] with keys: submission, exercise, feedback, revised_exercises
        """
        result = await self.backend.get_entry_chain_raw(submission_uid)
        if result.is_error:
            return Result.fail(result)

        records = result.value or []
        if not records or records[0].get("submission") is None:
            return Result.fail(Errors.not_found(resource="Submission", identifier=submission_uid))

        record = cast("dict[str, Any]", records[0])
        feedback: list[dict[str, Any]] = list(record.get("feedback") or [])
        revised: list[dict[str, Any]] = list(record.get("revised_exercises") or [])
        return Result.ok(
            {
                "submission": dict(record["submission"]) if record["submission"] else {},
                "exercise": dict(record["exercise"]) if record.get("exercise") else None,
                "feedback": [dict(f) for f in feedback if f.get("uid")],
                "revised_exercises": [dict(r) for r in revised if r.get("uid")],
            }
        )


__all__ = ["ReportRelationshipService"]
