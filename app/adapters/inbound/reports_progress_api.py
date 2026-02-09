"""
Reports Progress & Schedule API Routes
========================================

REST API for progress report generation and scheduling.

Routes:
- POST /api/reports/progress/generate — on-demand generation
- GET /api/reports/progress — list user's progress reports
- POST /api/reports/schedule — create/update schedule
- GET /api/reports/schedule — get user's schedule
- PUT /api/reports/schedule/{uid} — update schedule
- DELETE /api/reports/schedule/{uid} — deactivate schedule
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.services.protocols.reports_protocols import (
        ProgressReportGeneratorOperations,
        ReportScheduleOperations,
        ReportSubmissionOperations,
    )

from starlette.requests import Request

from core.auth import require_authenticated_user
from core.models.report import report_to_response
from core.models.report.report_request import (
    ProgressReportGenerateRequest,
    ReportScheduleCreateRequest,
    ReportScheduleUpdateRequest,
)
from core.utils.error_boundary import boundary_handler
from core.utils.logging import get_logger
from core.utils.result_simplified import Errors, Result

logger = get_logger("skuel.routes.reports.progress")


def create_reports_progress_api_routes(
    _app: Any,
    rt: Any,
    progress_generator: "ProgressReportGeneratorOperations",
    report_service: "ReportSubmissionOperations",
    schedule_service: "ReportScheduleOperations | None" = None,
) -> list[Any]:
    """
    Create progress report and schedule API routes.

    Args:
        _app: FastHTML application instance
        rt: Router instance
        progress_generator: ProgressReportGenerator for on-demand generation
        report_service: ReportSubmissionService for listing reports
        schedule_service: ReportScheduleService for schedule CRUD
    """

    logger.info("Creating Reports Progress API routes")

    # ========================================================================
    # PROGRESS REPORT GENERATION
    # ========================================================================

    @rt("/api/reports/progress/generate")
    @boundary_handler(success_status=201)
    async def generate_progress_report(request: Request) -> Result[Any]:
        """Generate a progress report on demand."""
        user_uid = require_authenticated_user(request)

        body = await request.json()
        req = ProgressReportGenerateRequest.model_validate(body)

        result = await progress_generator.generate(
            user_uid=user_uid,
            time_period=req.time_period,
            domains=req.domains if req.domains else None,
            depth=req.depth,
            include_insights=req.include_insights,
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        return Result.ok(
            {
                "report": report_to_response(result.value),
                "message": "Progress report generated successfully",
            }
        )

    @rt("/api/reports/progress")
    @boundary_handler()
    async def list_progress_reports(request: Request) -> Result[Any]:
        """List user's progress reports."""
        user_uid = require_authenticated_user(request)
        limit = int(request.query_params.get("limit", "20"))

        result = await report_service.list_reports(
            user_uid=user_uid,
            report_type="progress",
            limit=limit,
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        reports = result.value or []
        return Result.ok(
            {
                "reports": [report_to_response(r) for r in reports],
                "count": len(reports),
            }
        )

    # ========================================================================
    # SCHEDULE CRUD
    # ========================================================================

    routes = [generate_progress_report, list_progress_reports]

    if schedule_service:

        @rt("/api/reports/schedule")
        @boundary_handler(success_status=201)
        async def create_schedule(request: Request) -> Result[Any]:
            """Create or update a report generation schedule."""
            user_uid = require_authenticated_user(request)
            body = await request.json()
            req = ReportScheduleCreateRequest.model_validate(body)

            result = await schedule_service.create_schedule(
                user_uid=user_uid,
                schedule_type=req.schedule_type,
                day_of_week=req.day_of_week,
                domains=req.domains,
                depth=req.depth,
            )

            if result.is_error:
                return Result.fail(result.expect_error())

            return Result.ok(
                {
                    "schedule": result.value,
                    "message": "Schedule created successfully",
                }
            )

        @rt("/api/reports/schedule/get")
        @boundary_handler()
        async def get_schedule(request: Request) -> Result[Any]:
            """Get user's report schedule."""
            user_uid = require_authenticated_user(request)

            result = await schedule_service.get_user_schedule(user_uid)
            if result.is_error:
                return Result.fail(result.expect_error())

            return Result.ok({"schedule": result.value})

        @rt("/api/reports/schedule/update")
        @boundary_handler()
        async def update_schedule(request: Request, uid: str) -> Result[Any]:
            """Update a report schedule."""
            _user_uid = require_authenticated_user(request)
            body = await request.json()
            req = ReportScheduleUpdateRequest.model_validate(body)

            updates = {k: v for k, v in req.model_dump().items() if v is not None}
            result = await schedule_service.update_schedule(uid, updates)

            if result.is_error:
                return Result.fail(result.expect_error())

            return Result.ok(
                {
                    "schedule": result.value,
                    "message": "Schedule updated",
                }
            )

        @rt("/api/reports/schedule/delete")
        @boundary_handler()
        async def deactivate_schedule(request: Request, uid: str) -> Result[Any]:
            """Deactivate a report schedule."""
            _user_uid = require_authenticated_user(request)

            result = await schedule_service.deactivate_schedule(uid)
            if result.is_error:
                return Result.fail(result.expect_error())

            return Result.ok({"message": "Schedule deactivated"})

        routes.extend([create_schedule, get_schedule, update_schedule, deactivate_schedule])
        logger.info("Report schedule routes registered")

    logger.info("Reports Progress API routes created successfully")
    return routes
