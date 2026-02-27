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

from adapters.inbound.auth.roles import UserRole, require_role
from adapters.inbound.boundary import boundary_handler
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
) -> list[Any]:
    """
    Create teaching API routes.

    Args:
        app: FastHTML application instance
        rt: Route decorator
        teacher_review_service: TeacherReviewService instance
        user_service: UserService for role checks
    """

    def get_user_service() -> Any:
        return user_service

    @rt("/api/teaching/review-queue", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def review_queue(request: Request, current_user: Any) -> Result[Any]:
        """Get teacher's pending review queue."""
        status_filter = request.query_params.get("status", None)
        return await teacher_review_service.get_review_queue(
            teacher_uid=current_user.uid,
            status_filter=status_filter,
        )

    @rt("/api/teaching/review/{uid}/feedback", methods=["POST"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def submit_feedback(request: Request, uid: str, current_user: Any) -> Result[Any]:
        """Submit feedback for a student report."""
        body = await request.json()
        feedback = body.get("feedback", "")
        if not feedback:
            return Result.fail(Errors.validation("Feedback text is required", field="feedback"))

        return await teacher_review_service.submit_feedback(
            report_uid=uid,
            teacher_uid=current_user.uid,
            feedback=feedback,
        )

    @rt("/api/teaching/review/{uid}/revision", methods=["POST"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def request_revision(request: Request, uid: str, current_user: Any) -> Result[Any]:
        """Request revision for a student report."""
        body = await request.json()
        notes = body.get("notes", "")
        if not notes:
            return Result.fail(Errors.validation("Revision notes are required", field="notes"))

        return await teacher_review_service.request_revision(
            report_uid=uid,
            teacher_uid=current_user.uid,
            notes=notes,
        )

    @rt("/api/teaching/review/{uid}/approve", methods=["POST"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def approve_report(request: Request, uid: str, current_user: Any) -> Result[Any]:
        """Approve a student report."""
        return await teacher_review_service.approve_report(
            report_uid=uid,
            teacher_uid=current_user.uid,
        )

    @rt("/api/teaching/exercises", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_exercises(request: Request, current_user: Any) -> Result[Any]:
        """Get teacher's exercises with submission counts."""
        return await teacher_review_service.get_exercises_with_submission_counts(
            teacher_uid=current_user.uid,
        )

    @rt("/api/teaching/exercises/{uid}/submissions", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_exercise_submissions(
        request: Request, uid: str, current_user: Any
    ) -> Result[Any]:
        """Get all submissions against an exercise."""
        return await teacher_review_service.get_submissions_for_exercise(exercise_uid=uid)

    @rt("/api/teaching/students", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_students(request: Request, current_user: Any) -> Result[Any]:
        """Get students who shared work with the teacher."""
        return await teacher_review_service.get_students_summary(
            teacher_uid=current_user.uid,
        )

    @rt("/api/teaching/students/{uid}/submissions", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_student_submissions(
        request: Request, uid: str, current_user: Any
    ) -> Result[Any]:
        """Get all submissions from a specific student."""
        return await teacher_review_service.get_student_submissions(
            teacher_uid=current_user.uid,
            student_uid=uid,
        )

    @rt("/api/teaching/dashboard", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_dashboard_stats(request: Request, current_user: Any) -> Result[Any]:
        """Get at-a-glance stats for the teacher dashboard."""
        return await teacher_review_service.get_dashboard_stats(
            teacher_uid=current_user.uid,
        )

    @rt("/api/teaching/classes", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_classes(request: Request, current_user: Any) -> Result[Any]:
        """Get teacher's groups with member, exercise, and pending submission counts."""
        return await teacher_review_service.get_teacher_groups_with_stats(
            teacher_uid=current_user.uid,
        )

    @rt("/api/teaching/classes/{uid}", methods=["GET"])
    @require_role(UserRole.TEACHER, get_user_service)
    @boundary_handler()
    async def get_class_detail(request: Request, uid: str, current_user: Any) -> Result[Any]:
        """Get members of a specific class with their submission progress."""
        return await teacher_review_service.get_group_detail(
            group_uid=uid,
            teacher_uid=current_user.uid,
        )

    logger.info("✅ Teaching API routes registered")
    return []
