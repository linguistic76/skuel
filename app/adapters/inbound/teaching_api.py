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

from core.auth.roles import UserRole, require_role
from core.utils.error_boundary import boundary_handler
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.protocols import TeacherReviewOperations

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

    logger.info("✅ Teaching API routes registered")
    return []
