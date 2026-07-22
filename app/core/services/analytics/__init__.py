"""
Analytics Package - 4-Service Architecture
=========================================

Cross-domain and cross-layer analytics generation with specialized sub-services.

Architecture (October 24, 2025):
- AnalyticsMetricsService: Domain-specific statistical calculations
- AnalyticsAggregationService: Cross-domain synthesis and Life Analytics
- AnalyticsLifePathService: Life Path alignment tracking (NEW - Layer 3 critical!)
- AnalyticsService: Facade orchestrating all services (in parent directory)
- VisualizationAggregationService: Data fetching + aggregation for chart endpoints

This package enables:
1. Single-domain analytics (Tasks, Habits, Goals, Events, Finance, Choices, Principles)
2. Cross-domain Life Analytics (Weekly/Monthly/Quarterly/Yearly summaries)
3. Life Path alignment tracking (THE most important metric!)
4. Pattern detection across domains and layers
5. Chart/timeline/gantt data aggregation for visualization endpoints
"""

from core.services.analytics.analytics_aggregation_service import AnalyticsAggregationService
from core.services.analytics.analytics_life_path_service import AnalyticsLifePathService
from core.services.analytics.analytics_metrics_service import AnalyticsMetricsService
from core.services.analytics.knowledge_health_service import KnowledgeHealthService
from core.services.analytics.visualization_aggregation_service import (
    VisualizationAggregationService,
)

__all__ = [
    "AnalyticsAggregationService",
    "AnalyticsLifePathService",
    "AnalyticsMetricsService",
    "KnowledgeHealthService",
    "VisualizationAggregationService",
]
