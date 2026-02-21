"""
Reports Assessment API Routes
================================

REST API for teacher assessments of students.

Routes:
- POST /api/reports/assessments — create assessment (requires TEACHER role)
- GET /api/reports/assessments/given — teacher's authored assessments
- GET /api/reports/assessments/received — student's received assessments
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.services.protocols.reports_protocols import KuContentOperations

from starlette.requests import Request

from adapters.inbound.boundary import boundary_handler
from core.auth import require_authenticated_user, require_teacher
from core.models.ku import ku_to_response
from core.models.ku.ku_request import AssessmentCreateRequest
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

logger = get_logger("skuel.routes.reports.assessment")


def create_reports_assessment_api_routes(
    _app: Any,
    rt: Any,
    reports_core_service: "KuContentOperations",
    user_service_getter: Any,
) -> list[Any]:
    """
    Create assessment API routes.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        reports_core_service: ReportsCoreService for assessment CRUD
        user_service_getter: Named function returning user_service (for role checks)
    """

    logger.info("Creating Reports Assessment API routes")

    # ========================================================================
    # ASSESSMENT CRUD
    # ========================================================================

    @rt("/api/reports/assessments")
    @require_teacher(user_service_getter)
    @boundary_handler(success_status=201)
    async def create_assessment(request: Request, current_user: Any) -> Result[Any]:
        """Create a teacher assessment for a student."""
        teacher_uid = current_user.uid
        body = await request.json()
        req = AssessmentCreateRequest.model_validate(body)

        result = await reports_core_service.create_assessment(
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

    @rt("/api/reports/assessments/given")
    @boundary_handler()
    async def get_given_assessments(request: Request) -> Result[Any]:
        """Get assessments authored by the current teacher."""
        user_uid = require_authenticated_user(request)
        limit = int(request.query_params.get("limit", "50"))

        result = await reports_core_service.get_assessments_by_teacher(
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

    @rt("/api/reports/assessments/received")
    @boundary_handler()
    async def get_received_assessments(request: Request) -> Result[Any]:
        """Get assessments received by the current student."""
        user_uid = require_authenticated_user(request)
        limit = int(request.query_params.get("limit", "50"))

        result = await reports_core_service.get_assessments_for_student(
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
