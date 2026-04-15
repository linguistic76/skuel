"""UserEntry UI Orchestrator (ADR-054 — Commit 4)
=================================================

Unified orchestrator for the UserEntry hub — the successor to
``SubmissionsOrchestrator`` + ``JournalOrchestrator``. Journal is a
``pipeline=TRANSCRIBE_AND_STRUCTURE`` flow on ``UserEntry``, not a
separate domain, so the previously-split orchestrators collapse into one.

Legacy orchestrators remain alive through commit 5 while the legacy
submissions_* / journals_* route files still bind against them. Any
new UI code should depend on this orchestrator instead.

All dependencies are required — bootstrap raises if any are missing
(Fail-Fast Dependency Philosophy).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict

from core.models.enums.entity_enums import EntityStatus
from core.models.enums.pipeline import Pipeline
from core.models.type_hints import UserUID
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.exercises.exercise import Exercise
    from core.models.exercises.revised_exercise import RevisedExercise
    from core.models.report.activity_report import ActivityReport
    from core.models.report.exercise_report import ExerciseReport
    from core.models.user_entry.user_entry import UserEntry
    from core.services.exercises.exercise_service import ExerciseService
    from core.services.report.activity_report_service import ActivityReportService
    from core.services.report.exercise_report_service import ExerciseReportService
    from core.services.report.teacher_review_service import TeacherReviewService
    from core.services.revised_exercises import RevisedExerciseService
    from core.services.sharing import UnifiedSharingService
    from core.services.user_entry.user_entry_service import UserEntryService
    from core.services.user_service import UserService


class ExerciseReportView(TypedDict):
    """Bundled view for the exercise-report detail page.

    Returned by :meth:`UserEntryOrchestrator.get_exercise_report_view` — combines
    the report itself with the optional ``RevisedExercise`` that targets it, so
    the UI can render both in a single round trip.
    """

    report: ExerciseReport
    revised_exercise: RevisedExercise | None


class UserEntryOrchestrator:
    """Facade for the UserEntry UI layer.

    Collapses the former SubmissionsOrchestrator + JournalOrchestrator
    surfaces onto ``UserEntryService``, the single domain facade for all
    user-authored content.
    """

    def __init__(
        self,
        user_entry_service: UserEntryService,
        exercises_service: ExerciseService,
        teacher_review_service: TeacherReviewService,
        user_service: UserService,
        activity_report_service: ActivityReportService,
        revised_exercise_service: RevisedExerciseService,
        exercise_report_service: ExerciseReportService,
        sharing_service: UnifiedSharingService,
    ) -> None:
        self._entries = user_entry_service
        self._exercises = exercises_service
        self._teacher_review = teacher_review_service
        self._user_service = user_service
        self._activity_report = activity_report_service
        self._revised_exercise = revised_exercise_service
        self._exercise_report = exercise_report_service
        self._sharing = sharing_service

    @property
    def user_service(self) -> UserService:
        """Expose user service for admin role checks in UI routes."""
        return self._user_service

    # ------------------------------------------------------------------
    # UserEntry reads
    # ------------------------------------------------------------------

    async def get_entry(self, uid: str, user_uid: UserUID) -> Result[UserEntry | None]:
        """Ownership-verified fetch of a single UserEntry."""
        return await self._entries.get_entry(uid, user_uid)

    async def list_for_user(
        self,
        user_uid: UserUID,
        pipeline: Pipeline | None = None,
        status: EntityStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Result[list[UserEntry]]:
        """List a user's entries, optionally filtered by pipeline/status."""
        return await self._entries.list_for_user(
            user_uid=user_uid,
            pipeline=pipeline,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def list_journal_entries(
        self, user_uid: UserUID, limit: int = 50
    ) -> Result[list[UserEntry]]:
        """Return journal-pipeline entries (TRANSCRIBE_AND_STRUCTURE)."""
        return await self._entries.list_for_user(
            user_uid=user_uid,
            pipeline=Pipeline.TRANSCRIBE_AND_STRUCTURE,
            limit=limit,
        )

    async def list_exercise_entries(
        self, user_uid: UserUID, limit: int = 50
    ) -> Result[list[UserEntry]]:
        """Return teacher-review-pipeline entries (exercise submissions)."""
        return await self._entries.list_for_user(
            user_uid=user_uid,
            pipeline=Pipeline.TEACHER_REVIEW,
            limit=limit,
        )

    async def delete_entry(self, uid: str, user_uid: UserUID) -> Result[bool]:
        """Ownership-verified cascade delete."""
        return await self._entries.delete_entry(uid, user_uid)

    # ------------------------------------------------------------------
    # Exercises (dropdowns, assignment reads)
    # ------------------------------------------------------------------

    async def get_student_exercises(self, user_uid: str) -> Result[list[Exercise]]:
        """Get assigned exercises for dropdowns in the submit form."""
        return await self._exercises.get_student_exercises(user_uid)

    async def list_user_exercises(self, user_uid: str) -> Result[list[Exercise]]:
        """List saved instruction-template exercises owned by the user."""
        return await self._exercises.list_user_exercises(user_uid)

    async def create_exercise(
        self, user_uid: str, name: str, instructions: str
    ) -> Result[Exercise]:
        """Save a new instruction file as an Exercise entity."""
        return await self._exercises.create_exercise(
            user_uid=user_uid,
            name=name,
            instructions=instructions,
        )

    # ------------------------------------------------------------------
    # Reports & Reviews
    # ------------------------------------------------------------------

    async def get_exercise_report(self, uid: str) -> Result[ExerciseReport]:
        """Fetch an ExerciseReport by UID."""
        return await self._exercise_report.get_by_uid(uid)

    async def check_report_access(self, report_uid: str, user_uid: str) -> Result[bool]:
        """Canonical access check for a report — owner, PUBLIC, or shared."""
        return await self._sharing.check_access(report_uid, user_uid)

    async def get_exercise_report_view(
        self, report_uid: str, user_uid: str
    ) -> Result[ExerciseReportView]:
        """Fetch a report with access check + optional linked revision.

        Access denial surfaces as a not-found error so the route can render
        the standard "Report not found" banner without leaking existence.
        """
        report_result = await self._exercise_report.get_by_uid(report_uid)
        if report_result.is_error:
            return Result.fail(report_result)
        report = report_result.value

        access_result = await self._sharing.check_access(report.uid, user_uid)
        if access_result.is_error or not access_result.value:
            return Result.fail(Errors.not_found("ExerciseReport", report_uid))

        revision: RevisedExercise | None = None
        revision_result = await self._revised_exercise.get_by_report_uid(report.uid)
        if revision_result.is_ok:
            revision = revision_result.value

        return Result.ok({"report": report, "revised_exercise": revision})

    # ------------------------------------------------------------------
    # Activity Reports
    # ------------------------------------------------------------------

    async def get_activity_report(self, uid: str, user_uid: str) -> Result[ActivityReport]:
        """Fetch a single ActivityReport by UID, scoped to the owning user."""
        return await self._activity_report.get_by_uid(uid, user_uid)

    async def get_activity_report_history(
        self, user_uid: str, limit: int = 50
    ) -> Result[list[ActivityReport]]:
        """Fetch history of activity-based feedback."""
        return await self._activity_report.get_history(subject_uid=user_uid, limit=limit)

    # ------------------------------------------------------------------
    # Revised Exercises
    # ------------------------------------------------------------------

    async def get_revised_exercise(self, uid: str) -> Result[RevisedExercise]:
        """Fetch a specific student-requested revision."""
        return await self._revised_exercise.get(uid)

    async def get_revision_by_report(self, report_uid: str) -> Result[RevisedExercise | None]:
        """Find a revision generated starting from a given report."""
        return await self._revised_exercise.get_by_report_uid(report_uid)

    async def list_revised_exercises(self, user_uid: str) -> Result[list[RevisedExercise]]:
        """List all revisions created by the student."""
        return await self._revised_exercise.list_for_student(user_uid)

    # ------------------------------------------------------------------
    # Teacher queue
    # ------------------------------------------------------------------

    async def get_review_queue(
        self, teacher_uid: str, status_filter: list[str] | None = None
    ) -> Result[list[dict[str, Any]]]:
        """Teacher review queue — entries shared to the teacher's groups."""
        return await self._entries.get_review_queue(teacher_uid, status_filter=status_filter)
