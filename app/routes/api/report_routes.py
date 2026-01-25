"""
Report Generation API Routes (FastHTML-Aligned)
================================================

REST API endpoints for statistical domain reports following FastHTML best practices.

Following SKUEL's principles:
- User-requested (not pushed/recommended)
- Purely statistical (no AI prescriptions)
- Transparent metrics (no black boxes)

FastHTML Conventions Applied:
- Function names define routes
- Query parameters with type hints
- Automatic parameter extraction

Endpoints:
- GET /reports/generate - Generate report for any domain and period
- GET /reports/monthly - Convenience endpoint for monthly reports
- GET /reports/weekly - Convenience endpoint for weekly reports
- GET /reports/yearly - Convenience endpoint for yearly reports
- GET /reports/health-check - Service health check
"""

from datetime import datetime
from typing import Any

from core.models.shared_enums import ReportType
from core.utils.error_boundary import boundary_handler
from core.utils.logging import get_logger

logger = get_logger(__name__)


# ============================================================================
# ROUTE HANDLERS
# ============================================================================


def create_report_routes(app, services):
    """Create and register report routes (FastHTML-aligned)."""

    @app.get("/reports/generate")
    @boundary_handler()
    async def generate(request) -> Any:
        """
        Generate statistical report for any domain and period.

        Query params:
        - user_uid: User identifier (required)
        - report_type: Domain to report on - tasks, habits, goals, events, finance, choices (required)
        - period_start: Start date YYYY-MM-DD (required)
        - period_end: End date YYYY-MM-DD (required)

        Returns:
        - 200: Report with metrics and markdown
        - 400: Invalid parameters
        - 503: Report service not available
        """
        params = dict(request.query_params)
        user_uid = params.get("user_uid")
        report_type_str = params.get("report_type")
        period_start_str = params.get("period_start")
        period_end_str = params.get("period_end")

        # Validate required params
        if not user_uid:
            return {"error": "user_uid is required"}, 400
        if not report_type_str:
            return {
                "error": "report_type is required (tasks, habits, goals, events, finance, choices)"
            }, 400
        if not period_start_str or not period_end_str:
            return {"error": "period_start and period_end are required (YYYY-MM-DD format)"}, 400

        # Check service availability
        if not services.reports:
            return {"error": "Report service not available"}, 503

        # Parse report type
        try:
            report_type = ReportType(report_type_str.lower())
        except ValueError:
            return {
                "error": f"Invalid report_type. Must be one of: {', '.join(r.value for r in ReportType)}"
            }, 400

        # Parse dates
        try:
            period_start = datetime.strptime(period_start_str, "%Y-%m-%d").date()
            period_end = datetime.strptime(period_end_str, "%Y-%m-%d").date()
        except ValueError:
            return {"error": "Invalid date format. Use YYYY-MM-DD"}, 400

        # Generate report
        result = await services.reports.generate_report(
            user_uid=user_uid,
            report_type=report_type,
            period_start=period_start,
            period_end=period_end,
        )

        if result.is_error:
            logger.error(f"Failed to generate report: {result.error}")
            return {"error": "Report generation failed", "details": str(result.error)}, 500

        report = result.value

        # Return report data
        return {
            "uid": report.uid,
            "report_type": report.report_type.value,
            "user_uid": report.user_uid,
            "period_start": report.period_start.isoformat(),
            "period_end": report.period_end.isoformat(),
            "period_days": report.get_period_days(),
            "generated_at": report.generated_at.isoformat(),
            "title": report.title,
            "metrics": report.metrics,
            "markdown": report.markdown_content,
        }, 200

    @app.get("/reports/monthly")
    @boundary_handler()
    async def monthly(request) -> Any:
        """
        Generate monthly report for a domain.

        Query params:
        - user_uid: User identifier (required)
        - report_type: Domain to report on (required)
        - year: Year (required)
        - month: Month 1-12 (required)

        Returns:
        - 200: Monthly report
        - 400: Invalid parameters
        - 503: Report service not available
        """
        params = dict(request.query_params)
        user_uid = params.get("user_uid")
        report_type_str = params.get("report_type")
        year_str = params.get("year")
        month_str = params.get("month")

        # Validate
        if not user_uid:
            return {"error": "user_uid is required"}, 400
        if not report_type_str:
            return {"error": "report_type is required"}, 400
        if not year_str or not month_str:
            return {"error": "year and month are required"}, 400

        # Check service
        if not services.reports:
            return {"error": "Report service not available"}, 503

        # Parse
        try:
            report_type = ReportType(report_type_str.lower())
            year = int(year_str)
            month = int(month_str)
            if not (1 <= month <= 12):
                return {"error": "month must be between 1 and 12"}, 400
        except ValueError as e:
            return {"error": f"Invalid parameter: {e}"}, 400

        # Generate
        result = await services.reports.generate_monthly_report(
            user_uid=user_uid, report_type=report_type, year=year, month=month
        )

        if result.is_error:
            logger.error(f"Failed to generate monthly report: {result.error}")
            return {"error": "Report generation failed"}, 500

        report = result.value

        return {
            "uid": report.uid,
            "report_type": report.report_type.value,
            "user_uid": report.user_uid,
            "period_start": report.period_start.isoformat(),
            "period_end": report.period_end.isoformat(),
            "generated_at": report.generated_at.isoformat(),
            "title": report.title,
            "metrics": report.metrics,
            "markdown": report.markdown_content,
        }, 200

    @app.get("/reports/weekly")
    @boundary_handler()
    async def weekly(request) -> Any:
        """
        Generate weekly report for a domain.

        Query params:
        - user_uid: User identifier (required)
        - report_type: Domain to report on (required)
        - week_start: Week start date YYYY-MM-DD (optional, defaults to current week)

        Returns:
        - 200: Weekly report
        - 400: Invalid parameters
        - 503: Report service not available
        """
        params = dict(request.query_params)
        user_uid = params.get("user_uid")
        report_type_str = params.get("report_type")
        week_start_str = params.get("week_start")

        # Validate
        if not user_uid:
            return {"error": "user_uid is required"}, 400
        if not report_type_str:
            return {"error": "report_type is required"}, 400

        # Check service
        if not services.reports:
            return {"error": "Report service not available"}, 503

        # Parse report type
        try:
            report_type = ReportType(report_type_str.lower())
        except ValueError:
            return {"error": "Invalid report_type"}, 400

        # Parse week_start if provided
        week_start = None
        if week_start_str:
            try:
                week_start = datetime.strptime(week_start_str, "%Y-%m-%d").date()
            except ValueError:
                return {"error": "Invalid date format. Use YYYY-MM-DD"}, 400

        # Generate
        result = await services.reports.generate_weekly_report(
            user_uid=user_uid, report_type=report_type, week_start=week_start
        )

        if result.is_error:
            logger.error(f"Failed to generate weekly report: {result.error}")
            return {"error": "Report generation failed"}, 500

        report = result.value

        return {
            "uid": report.uid,
            "report_type": report.report_type.value,
            "user_uid": report.user_uid,
            "period_start": report.period_start.isoformat(),
            "period_end": report.period_end.isoformat(),
            "generated_at": report.generated_at.isoformat(),
            "title": report.title,
            "metrics": report.metrics,
            "markdown": report.markdown_content,
        }, 200

    @app.get("/reports/yearly")
    @boundary_handler()
    async def yearly(request) -> Any:
        """
        Generate yearly report for a domain.

        Query params:
        - user_uid: User identifier (required)
        - report_type: Domain to report on (required)
        - year: Year (required)

        Returns:
        - 200: Yearly report
        - 400: Invalid parameters
        - 503: Report service not available
        """
        params = dict(request.query_params)
        user_uid = params.get("user_uid")
        report_type_str = params.get("report_type")
        year_str = params.get("year")

        # Validate
        if not user_uid:
            return {"error": "user_uid is required"}, 400
        if not report_type_str:
            return {"error": "report_type is required"}, 400
        if not year_str:
            return {"error": "year is required"}, 400

        # Check service
        if not services.reports:
            return {"error": "Report service not available"}, 503

        # Parse
        try:
            report_type = ReportType(report_type_str.lower())
            year = int(year_str)
        except ValueError as e:
            return {"error": f"Invalid parameter: {e}"}, 400

        # Generate
        result = await services.reports.generate_yearly_report(
            user_uid=user_uid, report_type=report_type, year=year
        )

        if result.is_error:
            logger.error(f"Failed to generate yearly report: {result.error}")
            return {"error": "Report generation failed"}, 500

        report = result.value

        return {
            "uid": report.uid,
            "report_type": report.report_type.value,
            "user_uid": report.user_uid,
            "period_start": report.period_start.isoformat(),
            "period_end": report.period_end.isoformat(),
            "generated_at": report.generated_at.isoformat(),
            "title": report.title,
            "metrics": report.metrics,
            "markdown": report.markdown_content,
        }, 200

    @app.get("/reports/health-check")
    async def health_check() -> tuple[dict[str, Any], int]:
        """Check if report service is available."""
        return {
            "service": "reports",
            "available": services.reports is not None,
            "report_types": [r.value for r in ReportType],
            "timestamp": datetime.now().isoformat(),
        }, 200

    logger.info("✅ Report routes registered (FastHTML-aligned)")


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = ["create_report_routes"]
