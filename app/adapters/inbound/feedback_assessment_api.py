"""
Feedback Assessment API Routes
================================

REST API for teacher assessments of students.

Routes:
- POST /api/feedback/assessments — create assessment (requires TEACHER role)
- GET /api/feedback/assessments/given — teacher's authored assessments
- GET /api/feedback/assessments/received — student's received assessments
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.ports.feedback_protocols import FeedbackOperations

from starlette.requests import Request

from adapters.inbound.auth import require_authenticated_user, require_teacher
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.route_factories import parse_int_query_param
from core.models.entity_converters import ku_to_response
from core.models.feedback.feedback_requests import AssessmentCreateRequest
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger("skuel.routes.submissions.assessment")


def create_feedback_assessment_api_routes(
    _app: Any,
    rt: Any,
    feedback_service: "FeedbackOperations",
    user_service_getter: Any,
) -> list[Any]:
    """
    Create assessment API routes.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        feedback_service: FeedbackOperations service for assessment CRUD
        user_service_getter: Named function returning user_service (for role checks)
    """

    logger.info("Creating Reports Assessment API routes")

    # ========================================================================
    # ASSESSMENT CRUD
    # ========================================================================

    @rt("/api/feedback/assessments")
    @require_teacher(user_service_getter)
    @boundary_handler(success_status=201)
    async def create_assessment(request: Request, current_user: Any) -> Result[Any]:
        """Create a teacher assessment for a student."""
        teacher_uid = current_user.uid
        body = await request.json()
        req = AssessmentCreateRequest.model_validate(body)

        result = await feedback_service.create_assessment(
            teacher_uid=teacher_uid,
            subject_uid=req.subject_uid,
            title=req.title,
            content=req.content,
            metadata=req.metadata,
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok(
            {
                "report": ku_to_response(result.value),
                "message": "Assessment created successfully",
            }
        )

    @rt("/api/feedback/assessments/given")
    @boundary_handler()
    async def get_given_assessments(request: Request) -> Result[Any]:
        """Get assessments authored by the current teacher."""
        user_uid = require_authenticated_user(request)
        limit = parse_int_query_param(request.query_params, "limit", 50, minimum=1, maximum=500)

        result = await feedback_service.get_assessments_by_teacher(
            teacher_uid=user_uid,
            limit=limit,
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        reports = result.value or []
        return Result.ok(
            {
                "assessments": [ku_to_response(r) for r in reports],
                "count": len(reports),
            }
        )

    @rt("/api/feedback/assessments/received")
    @boundary_handler()
    async def get_received_assessments(request: Request) -> Result[Any]:
        """Get assessments received by the current student."""
        user_uid = require_authenticated_user(request)
        limit = parse_int_query_param(request.query_params, "limit", 50, minimum=1, maximum=500)

        result = await feedback_service.get_assessments_for_student(
            student_uid=user_uid,
            limit=limit,
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        reports = result.value or []
        return Result.ok(
            {
                "assessments": [ku_to_response(r) for r in reports],
                "count": len(reports),
            }
        )

    logger.info("Reports Assessment API routes created successfully")
    return [create_assessment, get_given_assessments, get_received_assessments]
