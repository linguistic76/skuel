"""Submissions UI Orchestrator
=============================

Application orchestrator for the Submissions Hub. Consolidates multi-service
dependencies into a single unified facade for UI components.

All service dependencies are required — bootstrap raises if any are missing
(Fail-Fast Dependency Philosophy). ``context_builder`` on UserService is the
one legitimate optional: it is ``None`` when no database context is available.
"""

from typing import TYPE_CHECKING, Any

from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.exercises.exercise_service import ExerciseService
    from core.services.report.activity_report_service import ActivityReportService
    from core.services.report.teacher_review_service import TeacherReviewService
    from core.services.revised_exercises import RevisedExerciseService
    from core.services.submissions import (
        SubmissionsCoreService,
        SubmissionsSearchService,
        SubmissionsService,
    )
    from core.services.user_service import UserService


class SubmissionsOrchestrator:
    """Facade for the submissions UI layer.

    Abstracts cross-domain reads so the UI routing layer depends only on this
    orchestrator. All service dependencies are required — bootstrap raises if
    any are missing (Fail-Fast Dependency Philosophy).

    ``user_service.context_builder`` is the one legitimate optional: it is
    ``None`` when no database context is available, and ``build_user_context``
    degrades gracefully in that case.
    """

    def __init__(  # noqa: ANN204
        self,
        submissions_service: "SubmissionsService",
        exercises_service: "ExerciseService",
        submissions_search_service: "SubmissionsSearchService",
        submissions_core_service: "SubmissionsCoreService",
        teacher_review_service: "TeacherReviewService",
        user_service: "UserService",
        activity_report_service: "ActivityReportService",
        revised_exercise_service: "RevisedExerciseService",
    ):
        self._submissions_service = submissions_service
        self._exercises_service = exercises_service
        self._submissions_search_service = submissions_search_service
        self._submissions_core_service = submissions_core_service
        self._teacher_review_service = teacher_review_service
        self._user_service = user_service
        self._activity_report_service = activity_report_service
        self._revised_exercise_service = revised_exercise_service

    # --- Submissions & Processing ---

    async def get_submission(self, uid: str) -> Result[Any]:
        """Fetch a submission document by ID."""
        return await self._submissions_service.get_submission(uid)

    async def list_submissions(self, user_uid: str, **kwargs: Any) -> Result[list[Any]]:
        """List user submissions based on filters."""
        return await self._submissions_service.list_submissions(user_uid, **kwargs)

    async def process_submission(self, **kwargs: Any) -> Result[Any]:
        """Submit and process a file."""
        return await self._submissions_service.submit_file(**kwargs)

    async def delete_submission_with_file(self, uid: str) -> Result[bool]:
        """Delete a submission and its associated file."""
        return await self._submissions_service.delete_submission_with_file(uid)

    async def get_submissions_with_feedback_status(self, user_uid: str) -> Result[list[Any]]:
        """Get submissions with teacher review status for the history view."""
        return await self._submissions_search_service.get_submissions_with_feedback_status(
            user_uid
        )

    # --- Exercises ---

    async def get_student_exercises(self, user_uid: str) -> Result[list[Any]]:
        """Get assigned exercises for dropdowns."""
        return await self._exercises_service.get_student_exercises(user_uid)

    async def get_exercise_for_submission(self, submission_uid: str) -> Result[Any]:
        """Get the specific exercise connected to a submission."""
        return await self._exercises_service.get_exercise_for_submission(submission_uid)

    # --- Reviews and Assessments ---

    async def get_assessment(self, uid: str) -> Result[Any]:
        """Fetch a teacher assessment (exercise report) by ID."""
        return await self._submissions_core_service.get_submission(uid)

    async def get_assessments_for_student(
        self, user_uid: str, **kwargs: Any
    ) -> Result[list[Any]]:
        """Get all received assessments for a student."""
        return await self._submissions_core_service.get_assessments_for_student(
            user_uid, **kwargs
        )

    async def get_report_history(self, submission_uid: str) -> Result[Any]:
        """Get the teacher review thread history for a submission."""
        return await self._teacher_review_service.get_report_history(submission_uid)

    # --- Activity Reports ---

    async def get_activity_report_history(
        self, user_uid: str, limit: int = 50
    ) -> Result[list[Any]]:
        """Fetch history of activity-based feedback."""
        return await self._activity_report_service.get_history(
            subject_uid=user_uid, limit=limit
        )

    # --- Revised Exercises ---

    async def get_revised_exercise(self, uid: str) -> Result[Any]:
        """Fetch a specific student-requested revision."""
        return await self._revised_exercise_service.get(uid)

    async def get_revision_by_report(self, report_uid: str) -> Result[Any]:
        """Find a revision generated starting from a given report."""
        return await self._revised_exercise_service.get_by_report_uid(report_uid)

    async def list_revised_exercises(self, user_uid: str) -> Result[list[Any]]:
        """List all revisions created by the student."""
        return await self._revised_exercise_service.list_for_student(user_uid)

    # --- Context / User Info ---

    async def build_user_context(self, user_uid: str) -> Result[Any]:
        """Build the structured learning context needed for deep processing."""
        if not self._user_service.context_builder:
            return Result.fail(Errors.system("User Context Builder not running"))
        return await self._user_service.context_builder.build(user_uid)
