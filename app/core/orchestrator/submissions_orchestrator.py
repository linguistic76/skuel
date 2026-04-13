"""Submissions UI Orchestrator
=============================

Application orchestrator for the Submissions Hub. Consolidates multi-service
dependencies into a single unified facade for UI components — and owns the
cross-service compositions (report → access → revision, file submit with
learning context) that used to live inline in route handlers.

All service dependencies are required — bootstrap raises if any are missing
(Fail-Fast Dependency Philosophy).
"""

from typing import TYPE_CHECKING, Any, TypedDict

from core.models.entity import Entity
from core.models.entity_types import SubmissionEntity
from core.models.enums.entity_enums import EntityStatus, EntityType, ProcessorType
from core.models.exercises.exercise import Exercise
from core.models.exercises.revised_exercise import RevisedExercise
from core.models.report.activity_report import ActivityReport
from core.models.report.exercise_report import ExerciseReport
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.exercises.exercise_service import ExerciseService
    from core.services.report.activity_report_service import ActivityReportService
    from core.services.report.exercise_report_service import ExerciseReportService
    from core.services.report.teacher_review_service import TeacherReviewService
    from core.services.revised_exercises import RevisedExerciseService
    from core.services.sharing import UnifiedSharingService
    from core.services.submissions import (
        SubmissionsCoreService,
        SubmissionsSearchService,
        SubmissionsService,
    )
    from core.services.user_service import UserService


class ExerciseReportView(TypedDict):
    """Bundled view for the exercise-report detail page.

    Returned by ``get_exercise_report_view`` — combines the report itself with
    the optional ``RevisedExercise`` that targets it, so the UI can render both
    in a single round trip.
    """

    report: ExerciseReport
    revised_exercise: RevisedExercise | None


class SubmissionsOrchestrator:
    """Facade for the submissions UI layer.

    Wraps 10 services so UI route files depend on one object. Owns the
    multi-service compositions the routes used to run by hand — see
    ``get_exercise_report_view`` and ``submit_file_with_learning_context``.
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
        exercise_report_service: "ExerciseReportService",
        sharing_service: "UnifiedSharingService",
    ):
        self._submissions_service = submissions_service
        self._exercises_service = exercises_service
        self._submissions_search_service = submissions_search_service
        self._submissions_core_service = submissions_core_service
        self._teacher_review_service = teacher_review_service
        self._user_service = user_service
        self._activity_report_service = activity_report_service
        self._revised_exercise_service = revised_exercise_service
        self._exercise_report_service = exercise_report_service
        self._sharing_service = sharing_service

    # --- Submissions & Processing ---

    async def get_submission(self, uid: str) -> Result[Entity | None]:
        """Fetch a submission document by UID."""
        return await self._submissions_service.get_submission(uid)

    async def list_submissions(
        self,
        user_uid: str,
        entity_type: EntityType | None = None,
        status: EntityStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Result[list[Entity]]:
        """List user submissions with optional filters."""
        return await self._submissions_service.list_submissions(
            user_uid,
            entity_type=entity_type,
            status=status,
            limit=limit,
            offset=offset,
        )

    async def process_submission(
        self,
        file_content: bytes,
        original_filename: str,
        user_uid: str,
        entity_type: EntityType = EntityType.EXERCISE_SUBMISSION,
        processor_type: ProcessorType = ProcessorType.AUTOMATIC,
        file_type: str | None = None,
        title: str | None = None,
        parent_entity_uid: str | None = None,
        metadata: dict[str, Any] | None = None,
        applies_knowledge_uids: list[str] | None = None,
        fulfills_exercise_uid: str | None = None,
        context_path_step_uid: str | None = None,
        context_learning_path_uid: str | None = None,
    ) -> Result[Entity]:
        """Submit and process a file. Prefer ``submit_file_with_learning_context``
        for exercise submissions — it enriches the PS/LP audit context automatically.
        """
        return await self._submissions_service.submit_file(
            file_content=file_content,
            original_filename=original_filename,
            user_uid=user_uid,
            entity_type=entity_type,
            processor_type=processor_type,
            file_type=file_type,
            title=title,
            parent_entity_uid=parent_entity_uid,
            metadata=metadata,
            applies_knowledge_uids=applies_knowledge_uids,
            fulfills_exercise_uid=fulfills_exercise_uid,
            context_path_step_uid=context_path_step_uid,
            context_learning_path_uid=context_learning_path_uid,
        )

    async def submit_file_with_learning_context(
        self,
        file_content: bytes,
        original_filename: str,
        user_uid: str,
        fulfills_exercise_uid: str | None,
        metadata: dict[str, Any] | None,
        from_ps: str | None,
        entity_type: EntityType = EntityType.EXERCISE_SUBMISSION,
        processor_type: ProcessorType = ProcessorType.HUMAN,
    ) -> Result[Entity]:
        """Submit a file with learning-loop audit context auto-enriched.

        Resolves ``context_path_step_uid`` and ``context_learning_path_uid``
        from the user's live ``UserContext`` so Interaction audit records carry
        the PathStep/LearningPath the student was studying at submission time.

        Precedence for ``context_path_step_uid``:
        1. Explicit ``from_ps`` (navigation context from the request).
        2. ``UserContext.current_ps_uids`` first entry.

        Best-effort: when ``user_service.context_builder`` is ``None`` or the
        build fails, the submission still proceeds without enriched context.
        """
        context_path_step_uid: str | None = from_ps or None
        context_learning_path_uid: str | None = None

        context_builder = self._user_service.context_builder
        if context_builder is not None:
            ctx_result = await context_builder.build(user_uid)
            if ctx_result.is_ok:
                ctx = ctx_result.value
                if not context_path_step_uid:
                    context_path_step_uid = next(iter(ctx.current_ps_uids), None)
                context_learning_path_uid = ctx.current_learning_path_uid

        return await self._submissions_service.submit_file(
            file_content=file_content,
            original_filename=original_filename,
            user_uid=user_uid,
            entity_type=entity_type,
            processor_type=processor_type,
            metadata=metadata,
            fulfills_exercise_uid=fulfills_exercise_uid,
            context_path_step_uid=context_path_step_uid,
            context_learning_path_uid=context_learning_path_uid,
        )

    async def delete_submission_with_file(self, uid: str) -> Result[bool]:
        """Delete a submission and its associated file."""
        return await self._submissions_service.delete_submission_with_file(uid)

    async def get_submissions_with_feedback_status(
        self, user_uid: str
    ) -> Result[list[dict[str, Any]]]:
        """Get submissions with teacher review status for the history view."""
        return await self._submissions_search_service.get_submissions_with_feedback_status(user_uid)

    # --- Exercises ---

    async def get_student_exercises(self, user_uid: str) -> Result[list[Exercise]]:
        """Get assigned exercises for dropdowns."""
        return await self._exercises_service.get_student_exercises(user_uid)

    async def get_exercise_for_submission(
        self, submission_uid: str
    ) -> Result[dict[str, Any] | None]:
        """Get the specific exercise connected to a submission."""
        return await self._exercises_service.get_exercise_for_submission(submission_uid)

    # --- Reviews and Assessments ---

    async def get_exercise_report(self, uid: str) -> Result[ExerciseReport]:
        """Fetch an ExerciseReport by UID via the typed read path."""
        return await self._exercise_report_service.get_by_uid(uid)

    async def check_report_access(self, report_uid: str, user_uid: str) -> Result[bool]:
        """Canonical access check for an ExerciseReport — owner, PUBLIC, or
        SHARES_WITH/group-share via ``UnifiedSharingService``.
        """
        return await self._sharing_service.check_access(report_uid, user_uid)

    async def get_exercise_report_view(
        self, report_uid: str, user_uid: str
    ) -> Result[ExerciseReportView]:
        """Fetch a report with access check + optional linked revision.

        Collapses the detail-page dance (fetch → guard → revision lookup) into
        one call. Access denial is surfaced as a not-found error so the route
        can render the standard "Report not found" banner without leaking
        existence.
        """
        report_result = await self._exercise_report_service.get_by_uid(report_uid)
        if report_result.is_error:
            return Result.fail(report_result)
        report = report_result.value

        access_result = await self._sharing_service.check_access(report.uid, user_uid)
        if access_result.is_error or not access_result.value:
            return Result.fail(Errors.not_found("ExerciseReport", report_uid))

        revision: RevisedExercise | None = None
        revision_result = await self._revised_exercise_service.get_by_report_uid(report.uid)
        if revision_result.is_ok:
            revision = revision_result.value

        view: ExerciseReportView = {"report": report, "revised_exercise": revision}
        return Result.ok(view)

    async def get_assessments_for_student(
        self, user_uid: str, limit: int = 50
    ) -> Result[list[SubmissionEntity]]:
        """Get all received assessments for a student."""
        return await self._submissions_core_service.get_assessments_for_student(
            user_uid, limit=limit
        )

    # --- Activity Reports ---

    async def get_activity_report(self, uid: str, user_uid: str) -> Result[ActivityReport]:
        """Fetch a single ActivityReport by UID, scoped to the owning user."""
        return await self._activity_report_service.get_by_uid(uid, user_uid)

    async def get_activity_report_history(
        self, user_uid: str, limit: int = 50
    ) -> Result[list[ActivityReport]]:
        """Fetch history of activity-based feedback."""
        return await self._activity_report_service.get_history(subject_uid=user_uid, limit=limit)

    # --- Revised Exercises ---

    async def get_revised_exercise(self, uid: str) -> Result[RevisedExercise]:
        """Fetch a specific student-requested revision."""
        return await self._revised_exercise_service.get(uid)

    async def get_revision_by_report(self, report_uid: str) -> Result[RevisedExercise | None]:
        """Find a revision generated starting from a given report."""
        return await self._revised_exercise_service.get_by_report_uid(report_uid)

    async def list_revised_exercises(self, user_uid: str) -> Result[list[RevisedExercise]]:
        """List all revisions created by the student."""
        return await self._revised_exercise_service.list_for_student(user_uid)
