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
- Result[T] pattern with @boundary_handler
- @rt() decorators for route registration

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
from core.utils.result_simplified import Errors, Result

logger = get_logger(__name__)


# ============================================================================
# ROUTE HANDLERS
# ============================================================================


def create_report_routes(app, rt, services):
    """Create and register report routes (FastHTML-aligned)."""

    @rt("/reports/generate")
    @boundary_handler()
    async def generate(
        user_uid: str, report_type: str, period_start: str, period_end: str
    ) -> Result[Any]:
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
        # Check service availability
        if not services.reports:
            return Result.fail(
                Errors.system("Report service not available", service="ReportsService")
            )

        # Parse report type
        try:
            parsed_report_type = ReportType(report_type.lower())
        except ValueError:
            return Result.fail(
                Errors.validation(
                    f"Invalid report_type. Must be one of: {', '.join(r.value for r in ReportType)}",
                    field="report_type",
                    value=report_type,
                )
            )

        # Parse dates
        try:
            parsed_period_start = datetime.strptime(period_start, "%Y-%m-%d").date()
            parsed_period_end = datetime.strptime(period_end, "%Y-%m-%d").date()
        except ValueError:
            return Result.fail(
                Errors.validation(
                    "Invalid date format. Use YYYY-MM-DD",
                    field="period_start/period_end",
                    value=f"{period_start}/{period_end}",
                )
            )

        # Generate report
        result = await services.reports.generate_report(
            user_uid=user_uid,
            report_type=parsed_report_type,
            period_start=parsed_period_start,
            period_end=parsed_period_end,
        )

        if result.is_error:
            logger.error(f"Failed to generate report: {result.error}")
            return result

        report = result.value

        # Return report data
        return Result.ok(
            {
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
            }
        )

    @rt("/reports/monthly")
    @boundary_handler()
    async def monthly(user_uid: str, report_type: str, year: str, month: str) -> Result[Any]:
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
        # Check service
        if not services.reports:
            return Result.fail(
                Errors.system("Report service not available", service="ReportsService")
            )

        # Parse
        try:
            parsed_report_type = ReportType(report_type.lower())
            parsed_year = int(year)
            parsed_month = int(month)
            if not (1 <= parsed_month <= 12):
                return Result.fail(
                    Errors.validation("month must be between 1 and 12", field="month", value=month)
                )
        except ValueError as e:
            return Result.fail(Errors.validation(f"Invalid parameter: {e}", field="year/month"))

        # Generate
        result = await services.reports.generate_monthly_report(
            user_uid=user_uid, report_type=parsed_report_type, year=parsed_year, month=parsed_month
        )

        if result.is_error:
            logger.error(f"Failed to generate monthly report: {result.error}")
            return result

        report = result.value

        return Result.ok(
            {
                "uid": report.uid,
                "report_type": report.report_type.value,
                "user_uid": report.user_uid,
                "period_start": report.period_start.isoformat(),
                "period_end": report.period_end.isoformat(),
                "generated_at": report.generated_at.isoformat(),
                "title": report.title,
                "metrics": report.metrics,
                "markdown": report.markdown_content,
            }
        )

    @rt("/reports/weekly")
    @boundary_handler()
    async def weekly(user_uid: str, report_type: str, week_start: str | None = None) -> Result[Any]:
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
        # Check service
        if not services.reports:
            return Result.fail(
                Errors.system("Report service not available", service="ReportsService")
            )

        # Parse report type
        try:
            parsed_report_type = ReportType(report_type.lower())
        except ValueError:
            return Result.fail(
                Errors.validation("Invalid report_type", field="report_type", value=report_type)
            )

        # Parse week_start if provided
        parsed_week_start = None
        if week_start:
            try:
                parsed_week_start = datetime.strptime(week_start, "%Y-%m-%d").date()
            except ValueError:
                return Result.fail(
                    Errors.validation(
                        "Invalid date format. Use YYYY-MM-DD", field="week_start", value=week_start
                    )
                )

        # Generate
        result = await services.reports.generate_weekly_report(
            user_uid=user_uid, report_type=parsed_report_type, week_start=parsed_week_start
        )

        if result.is_error:
            logger.error(f"Failed to generate weekly report: {result.error}")
            return result

        report = result.value

        return Result.ok(
            {
                "uid": report.uid,
                "report_type": report.report_type.value,
                "user_uid": report.user_uid,
                "period_start": report.period_start.isoformat(),
                "period_end": report.period_end.isoformat(),
                "generated_at": report.generated_at.isoformat(),
                "title": report.title,
                "metrics": report.metrics,
                "markdown": report.markdown_content,
            }
        )

    @rt("/reports/yearly")
    @boundary_handler()
    async def yearly(user_uid: str, report_type: str, year: str) -> Result[Any]:
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
        # Check service
        if not services.reports:
            return Result.fail(
                Errors.system("Report service not available", service="ReportsService")
            )

        # Parse
        try:
            parsed_report_type = ReportType(report_type.lower())
            parsed_year = int(year)
        except ValueError as e:
            return Result.fail(Errors.validation(f"Invalid parameter: {e}", field="year"))

        # Generate
        result = await services.reports.generate_yearly_report(
            user_uid=user_uid, report_type=parsed_report_type, year=parsed_year
        )

        if result.is_error:
            logger.error(f"Failed to generate yearly report: {result.error}")
            return result

        report = result.value

        return Result.ok(
            {
                "uid": report.uid,
                "report_type": report.report_type.value,
                "user_uid": report.user_uid,
                "period_start": report.period_start.isoformat(),
                "period_end": report.period_end.isoformat(),
                "generated_at": report.generated_at.isoformat(),
                "title": report.title,
                "metrics": report.metrics,
                "markdown": report.markdown_content,
            }
        )

    @rt("/reports/health-check")
    @boundary_handler()
    async def health_check() -> Result[Any]:
        """Check if report service is available."""
        return Result.ok(
            {
                "service": "reports",
                "available": services.reports is not None,
                "report_types": [r.value for r in ReportType],
                "timestamp": datetime.now().isoformat(),
            }
        )

    logger.info("✅ Report routes registered (FastHTML-aligned)")


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = ["create_report_routes"]
