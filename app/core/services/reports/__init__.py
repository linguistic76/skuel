"""
Reports Package - 4-Service Architecture
=========================================

Cross-domain and cross-layer report generation with specialized sub-services.

Architecture (October 24, 2025):
- ReportMetricsService: Domain-specific statistical calculations
- ReportAggregationService: Cross-domain synthesis and Life Reports
- ReportLifePathService: Life Path alignment tracking (NEW - Layer 3 critical!)
- ReportsService: Facade orchestrating all services (in parent directory)

This package enables:
1. Single-domain reports (Tasks, Habits, Goals, Events, Finance, Choices, Principles)
2. Cross-domain Life Reports (Weekly/Monthly/Quarterly/Yearly summaries)
3. Life Path alignment tracking (THE most important metric!)
4. Pattern detection across domains and layers
"""

from core.services.reports.report_aggregation_service import ReportAggregationService
from core.services.reports.report_life_path_service import ReportLifePathService
from core.services.reports.report_metrics_service import ReportMetricsService

__all__ = [
    "ReportAggregationService",
    "ReportLifePathService",
    "ReportMetricsService",
]
