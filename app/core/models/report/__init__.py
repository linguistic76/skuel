"""
Report Models Package
=====================

Clean public API for report domain models following three-tier architecture.
"""

from core.models.report.report import ReportDTO, ReportPure, dto_to_pure, pure_to_dto
from core.models.report.report_request import WeeklyPlanningRequest, WeeklyReviewRequest

__all__ = [
    # Domain models
    "ReportDTO",
    "ReportPure",
    # Request models (Pydantic)
    "WeeklyPlanningRequest",
    "WeeklyReviewRequest",
    "dto_to_pure",
    "pure_to_dto",
]
