"""
Analytics Models Package
========================

Clean public API for analytics domain models following three-tier architecture.
"""

from core.models.analytics.analytics import (
    AnalyticsSummary,
    AnalyticsSummaryDTO,
    dto_to_summary,
    summary_to_dto,
)
from core.models.analytics.analytics_report_request import (
    WeeklyPlanningRequest,
    WeeklyReviewRequest,
)

__all__ = [
    # Domain models
    "AnalyticsSummaryDTO",
    "AnalyticsSummary",
    # Request models (Pydantic)
    "WeeklyPlanningRequest",
    "WeeklyReviewRequest",
    # Conversion functions
    "dto_to_summary",
    "summary_to_dto",
]
