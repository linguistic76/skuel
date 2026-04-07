"""Submissions UI Orchestrator
=============================

Application orchestrator for the Submissions Hub. Consolidates multi-service
dependencies into a single unified facade for UI components.
"""

from typing import Any

from core.utils.errors import Errors
from core.utils.result import Result


class SubmissionsOrchestrator:
    """Facade for the submissions UI layer, routing to appropriate domains."""

    def __init__(
        self,
        submissions_service: Any,
        processing_service: Any | None = None,
        exercises_service: Any | None = None,
        submissions_search_service: Any | None = None,
        submissions_core_service: Any | None = None,
        teacher_review_service: Any | None = None,
        user_service: Any | None = None,
        activity_report_service: Any | None = None,
        revised_exercise_service: Any | None = None,
    ):
        self._submissions_service = submissions_service
        self._processing_service = processing_service
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

    async def list_submissions(self, **kwargs) -> Result[list[Any]]:
        """List user submissions based on filters."""
        return await self._submissions_service.list_submissions(**kwargs)
        
    async def process_submission(self, **kwargs) -> Result[Any]:
        """Submit and process a file."""
        return await self._submissions_service.submit_file(**kwargs)

    # --- Exercises ---
    
    async def get_student_exercises(self, user_uid: str) -> Result[list[Any]]:
        """Get assigned exercises for dropdowns."""
        if not self._exercises_service:
            return Result.fail(Errors.system("Exercises service not initialized"))
        return await self._exercises_service.get_student_exercises(user_uid)
        
    async def get_exercise_for_submission(self, submission_uid: str) -> Result[Any]:
        """Get the specific exercise connected to a submission."""
        if not self._exercises_service:
            return Result.fail(Errors.system("Exercises service not initialized"))
        return await self._exercises_service.get_exercise_for_submission(submission_uid)

    # --- Reviews and Assessments ---
    
    async def get_assessment(self, uid: str) -> Result[Any]:
        """Fetch a teacher assessment (exercise report) by ID."""
        if not self._submissions_core_service:
            return Result.fail(Errors.system("Assessments service not initialized"))
        return await self._submissions_core_service.get_submission(uid)

    async def get_assessments_for_student(self, user_uid: str, **kwargs) -> Result[list[Any]]:
        """Get all received assessments for a student."""
        if not self._submissions_core_service:
            return Result.fail(Errors.system("Assessments service not initialized"))
        return await self._submissions_core_service.get_assessments_for_student(user_uid, **kwargs)

    async def get_report_history(self, submission_uid: str) -> Result[Any]:
        """Get the teacher review thread history for a submission."""
        if not self._teacher_review_service:
            return Result.fail(Errors.system("Teacher review service not initialized"))
        return await self._teacher_review_service.get_report_history(submission_uid)
        
    # --- Activity Reports ---
    
    async def get_activity_report_history(self, user_uid: str, limit: int = 50) -> Result[list[Any]]:
        """Fetch history of activity-based feedback."""
        if not self._activity_report_service:
            return Result.fail(Errors.system("Activity report service not initialized"))
        return await self._activity_report_service.get_history(subject_uid=user_uid, limit=limit)

    # --- Revised Exercises ---
    
    async def get_revised_exercise(self, uid: str) -> Result[Any]:
        """Fetch a specific student-requested revision."""
        if not self._revised_exercise_service:
            return Result.fail(Errors.system("Revision service not initialized"))
        return await self._revised_exercise_service.get(uid)

    async def get_revision_by_report(self, report_uid: str) -> Result[Any]:
        """Find a revision generated starting from a given report."""
        if not self._revised_exercise_service:
            return Result.fail(Errors.system("Revision service not initialized"))
        return await self._revised_exercise_service.get_by_report_uid(report_uid)

    async def list_revised_exercises(self, user_uid: str) -> Result[list[Any]]:
        """List all revisions created by the student."""
        if not self._revised_exercise_service:
            return Result.fail(Errors.system("Revision service not initialized"))
        return await self._revised_exercise_service.list_for_student(user_uid)

    # --- Context / User Info ---
    
    async def build_user_context(self, user_uid: str) -> Result[Any]:
        """Build the structured learning context needed for deep processing."""
        if not self._user_service or not getattr(self._user_service, "context_builder", None):
            return Result.fail(Errors.system("User Context Builder not running"))
        return await self._user_service.context_builder.build(user_uid)
