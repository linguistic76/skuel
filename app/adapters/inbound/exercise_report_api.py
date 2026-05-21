"""
Exercise Report Assessment API Routes
======================================

REST API for teacher assessments of students.

Routes:
- POST /api/reports/assessments — create assessment (requires TEACHER role)
- GET /api/reports/assessments/given — teacher's authored assessments
- GET /api/reports/assessments/received — student's received assessments
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.ports.report_protocols import ExerciseReportOperations

from adapters.inbound.auth import require_authenticated_user, require_teacher
from adapters.inbound.boundary import boundary_handler
from adapters.inbound.csrf import csrf_protected
from adapters.inbound.fasthtml_types import Request
from adapters.inbound.route_factories import parse_int_query_param
from core.models.entity_converters import entity_to_response
from core.models.report.report_requests import AssessmentCreateRequest
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

# Route-local response shapes (used only in this file)
AssessmentResponse = dict[str, Any]  # {"report": dict, "message": str}
AssessmentListResponse = dict[str, Any]  # {"assessments": list[dict], "count": int}

logger = get_logger("skuel.routes.submissions.assessment")


def create_exercise_report_api_routes(
    _app: Any,
    rt: Any,
    report_service: "ExerciseReportOperations",
    user_service_getter: Any,
) -> list[Any]:
    """
    Create assessment API routes.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        report_service: ExerciseReportOperations service for assessment CRUD
        user_service_getter: Named function returning user_service (for role checks)
    """

    logger.info("Creating Reports Assessment API routes")

    # ========================================================================
    # ASSESSMENT CRUD
    # ========================================================================

    @rt("/api/reports/assessments")
    @csrf_protected
    @require_teacher(user_service_getter)
    @boundary_handler(success_status=201)
    async def create_assessment(request: Request, current_user: Any) -> Result[AssessmentResponse]:
        """Create a teacher assessment for a student."""
        teacher_uid = current_user.uid
        body = await request.json()
        req = AssessmentCreateRequest.model_validate(body)

        result = await report_service.create_assessment(
            teacher_uid=teacher_uid,
            subject_uid=req.subject_uid,
            title=req.title,
            content=req.content,
            metadata=req.metadata,
        )

        if result.is_error:
            return Result.fail(result)

        return Result.ok(
            {
                "report": entity_to_response(result.value),
                "message": "Assessment created successfully",
            }
        )

    @rt("/api/reports/assessments/given")
    @boundary_handler()
    async def get_given_assessments(request: Request) -> Result[AssessmentListResponse]:
        """Get assessments authored by the current teacher."""
        user_uid = require_authenticated_user(request)
        limit = parse_int_query_param(request.query_params, "limit", 50, minimum=1, maximum=500)

        result = await report_service.get_assessments_by_teacher(
            teacher_uid=user_uid,
            limit=limit,
        )

        if result.is_error:
            return Result.fail(result)

        reports = result.value or []
        return Result.ok(
            {
                "assessments": [entity_to_response(r) for r in reports],
                "count": len(reports),
            }
        )

    @rt("/api/reports/assessments/received")
    @boundary_handler()
    async def get_received_assessments(request: Request) -> Result[AssessmentListResponse]:
        """Get assessments received by the current student."""
        user_uid = require_authenticated_user(request)
        limit = parse_int_query_param(request.query_params, "limit", 50, minimum=1, maximum=500)

        result = await report_service.get_assessments_for_student(
            student_uid=user_uid,
            limit=limit,
        )

        if result.is_error:
            return Result.fail(result)

        reports = result.value or []
        return Result.ok(
            {
                "assessments": [entity_to_response(r) for r in reports],
                "count": len(reports),
            }
        )

    logger.info("Reports Assessment API routes created successfully")
    return [create_assessment, get_given_assessments, get_received_assessments]
