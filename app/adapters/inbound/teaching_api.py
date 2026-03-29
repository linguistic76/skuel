"""
Teaching API Routes
====================

API endpoints for teacher review workflow.

Provides:
- Review queue (pending student submissions)
- Feedback submission
- Revision requests
- Report approval

TEACHER role required for all endpoints.

See: /docs/decisions/ADR-040-teacher-assignment-workflow.md
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import Request

from adapters.inbound.auth.roles import UserRole, make_service_getter, require_role
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.form_helpers import parse_form_body, parse_json_body
from core.models.teaching.teaching_request import (
    CreateTeachingExerciseRequest,
    RequestRevisionRequest,
    SubmitReportRequest,
    UpdateTeachingExerciseRequest,
)

# NOTE: FastHTML evaluates string annotations at runtime via signature_ex(),
# so types used in @rt() handler return annotations must be real imports.
from core.ports.query_types import (
    ExerciseWithSubmissionCounts,
    GroupMemberProgress,
    ReportApprovalResult,
    ReportSubmitResult,
    ReviewQueueItem,
    RevisionRequestResult,
    StudentSubmissionItem,
    StudentSummaryItem,
    SubmissionDetailResult,
    SubmissionForExercise,
    TeacherDashboardStats,
    TeacherGroupStats,
)
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.ports import TeacherReviewOperations

logger = get_logger(__name__)


def create_teaching_api_routes(
    app: Any,
    rt: Any,
    teacher_review_service: "TeacherReviewOperations",
    user_service: Any,
    exercises_service: Any,
) -> list[Any]:
    """
    Create teaching API routes.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        teacher_review_service: TeacherReviewService instance
        user_service: UserService for role checks
    """

    get_user_service = make_service_getter(user_service)

    @rt("/api/teaching/review-queue", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def review_queue(request: Request, current_user: Any) -> "Result[list[ReviewQueueItem]]":
        """Get teacher's pending review queue."""
        status_filter = request.query_params.get("status", None)
        return await teacher_review_service.get_review_queue(
            teacher_uid=current_user.uid,
            status_filter=status_filter,
        )

    @rt("/api/teaching/review/{uid}/report", methods=["POST"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def submit_feedback(
        request: Request, uid: str, current_user: Any
    ) -> Result[ReportSubmitResult]:
        """Submit feedback for a student report."""
        result = await parse_json_body(request, SubmitReportRequest)
        if result.is_error:
            return Result.fail(result)

        return await teacher_review_service.submit_report(
            report_uid=uid,
            teacher_uid=current_user.uid,
            feedback=result.value.feedback,
        )

    @rt("/api/teaching/review/{uid}/revision", methods=["POST"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def request_revision(
        request: Request, uid: str, current_user: Any
    ) -> Result[RevisionRequestResult]:
        """Request revision for a student report."""
        result = await parse_json_body(request, RequestRevisionRequest)
        if result.is_error:
            return Result.fail(result)

        return await teacher_review_service.request_revision(
            report_uid=uid,
            teacher_uid=current_user.uid,
            notes=result.value.notes,
        )

    @rt("/api/teaching/review/{uid}/approve", methods=["POST"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def approve_report(
        request: Request, uid: str, current_user: Any
    ) -> Result[ReportApprovalResult]:
        """Approve a student report."""
        return await teacher_review_service.approve_report(
            report_uid=uid,
            teacher_uid=current_user.uid,
        )

    @rt("/api/teaching/review/{uid}", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_submission_detail(
        request: Request, uid: str, current_user: Any
    ) -> "Result[SubmissionDetailResult]":
        """Get full submission detail for teacher review.

        Returns submission content, student info, and linked exercise.
        Access-controlled: only succeeds if teacher has SHARES_WITH {role: 'teacher'} access.
        """
        return await teacher_review_service.get_submission_detail(
            submission_uid=uid,
            teacher_uid=current_user.uid,
        )

    @rt("/api/teaching/exercises", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_exercises(
        request: Request, current_user: Any
    ) -> Result[list[ExerciseWithSubmissionCounts]]:
        """Get teacher's exercises with submission counts."""
        return await teacher_review_service.get_exercises_with_submission_counts(
            teacher_uid=current_user.uid,
        )

    @rt("/api/teaching/exercises/{uid}/submissions", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_exercise_submissions(
        request: Request, uid: str, current_user: Any
    ) -> Result[list[SubmissionForExercise]]:
        """Get all submissions against an exercise."""
        return await teacher_review_service.get_submissions_for_exercise(exercise_uid=uid)

    @rt("/api/teaching/students", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_students(request: Request, current_user: Any) -> Result[list[StudentSummaryItem]]:
        """Get students who shared work with the teacher."""
        return await teacher_review_service.get_students_summary(
            teacher_uid=current_user.uid,
        )

    @rt("/api/teaching/students/{uid}/submissions", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_student_submissions(
        request: Request, uid: str, current_user: Any
    ) -> Result[list[StudentSubmissionItem]]:
        """Get all submissions from a specific student."""
        return await teacher_review_service.get_student_submissions(
            teacher_uid=current_user.uid,
            student_uid=uid,
        )

    @rt("/api/teaching/dashboard", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_dashboard_stats(
        request: Request, current_user: Any
    ) -> "Result[TeacherDashboardStats]":
        """Get at-a-glance stats for the teacher dashboard."""
        return await teacher_review_service.get_dashboard_stats(
            teacher_uid=current_user.uid,
        )

    @rt("/api/teaching/classes", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_classes(request: Request, current_user: Any) -> Result[list[TeacherGroupStats]]:
        """Get teacher's groups with member, exercise, and pending submission counts."""
        return await teacher_review_service.get_teacher_groups_with_stats(
            teacher_uid=current_user.uid,
        )

    @rt("/api/teaching/classes/{uid}", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_class_detail(
        request: Request, uid: str, current_user: Any
    ) -> Result[list[GroupMemberProgress]]:
        """Get members of a specific class with their submission progress."""
        return await teacher_review_service.get_group_detail(
            group_uid=uid,
            teacher_uid=current_user.uid,
        )

    @rt("/api/teaching/exercises", methods=["POST"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler(success_status=201)
    async def create_teaching_exercise(
        request: Request, current_user: Any = None
    ) -> Result[dict[str, Any]]:
        """Create a new exercise owned by the authenticated teacher."""
        if not exercises_service:
            return Result.fail(
                Errors.system(
                    "exercises_service not available", operation="create_teaching_exercise"
                )
            )

        parsed = await parse_form_body(request, CreateTeachingExerciseRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value

        result = await exercises_service.create_exercise(
            user_uid=current_user.uid,
            name=req.name,
            instructions=req.instructions,
            model=req.model,
            scope=req.scope,
            group_uid=req.group_uid,
            due_date=req.due_date,
            processor_type=req.processor_type,
            context_notes=req.parsed_context_notes,
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value.to_dto().to_dict())

    @rt("/api/teaching/exercises/{uid}", methods=["POST"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def update_teaching_exercise(
        request: Request, uid: str, current_user: Any = None
    ) -> Result[dict[str, Any]]:
        """Update an existing exercise."""
        if not exercises_service:
            return Result.fail(
                Errors.system(
                    "exercises_service not available", operation="update_teaching_exercise"
                )
            )

        parsed = await parse_form_body(request, UpdateTeachingExerciseRequest)
        if parsed.is_error:
            return Result.fail(parsed)
        req = parsed.value

        result = await exercises_service.update_exercise(
            uid=uid,
            name=req.name,
            instructions=req.instructions,
            model=req.model,
            context_notes=req.parsed_context_notes,
        )
        if result.is_error:
            return Result.fail(result)
        return Result.ok(result.value.to_dto().to_dict())

    logger.info("✅ Teaching API routes registered")
    return []
