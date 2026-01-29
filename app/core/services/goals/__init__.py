"""
Goals Service Sub-Services
===========================

This package contains focused sub-services that compose the unified GoalsService facade.

Architecture: Facade Pattern (9 sub-services)
- Each sub-service handles ONE specific responsibility
- GoalsService (facade) auto-delegates to appropriate sub-service via FacadeDelegationMixin
- ~40+ auto-generated delegation methods + explicit orchestration methods
- Zero breaking changes to external code

Sub-Services:
- GoalsCoreService: CRUD operations, event publishing
- GoalsSearchService: Search, discovery, filtering
- GoalsProgressService: Progress tracking, milestones, completion
- GoalsLearningService: Learning path integration, knowledge connections
- GoalsPlanningService: Context-aware planning and recommendations
- GoalsSchedulingService: Capacity management, schedule optimization
- GoalsRecommendationService: Goal recommendations and suggestions
- GoalsIntelligenceService: Pure Cypher analytics and predictive analytics (NO AI dependencies)

Common Import Pattern (Production):
    from core.services.goals_service import GoalsService  # Facade
    result = await goals_service.create_goal(request, user_uid)

Direct Sub-Service Import (Testing/Composition):
    from core.services.goals import GoalsCoreService
    core = GoalsCoreService(backend=mock_backend)

Documentation:
- Quick Start: /docs/guides/BASESERVICE_QUICK_START.md
- Sub-Service Catalog: /docs/reference/SUB_SERVICE_CATALOG.md
- Method Index: /docs/reference/BASESERVICE_METHOD_INDEX.md
- Service Topology: /docs/architecture/SERVICE_TOPOLOGY.md

Architecture Notes:
- GoalsRelationshipService replaced by UnifiedRelationshipService (December 2025)
- GoalsGraphNativeService removed, replaced by UnifiedRelationshipService (January 2026 - ADR-029)

Version: 6.1.0
Date: 2026-01-29
"""

from core.services.goals.goals_core_service import GoalsCoreService
from core.services.goals.goals_intelligence_service import (
    GoalPrediction,
    GoalsIntelligenceService,
    HabitImpactAnalysis,
)
from core.services.goals.goals_learning_service import GoalsLearningService
from core.services.goals.goals_planning_service import GoalsPlanningService
from core.services.goals.goals_progress_service import GoalsProgressService
from core.services.goals.goals_recommendation_service import GoalsRecommendationService
from core.services.goals.goals_scheduling_service import (
    AchievabilityResult,
    GoalCapacityResult,
    GoalSequenceItem,
    GoalsSchedulingService,
    TimelineSuggestion,
)
from core.services.goals.goals_search_service import GoalsSearchService

__all__ = [
    "AchievabilityResult",
    "GoalCapacityResult",
    "GoalPrediction",
    "GoalSequenceItem",
    "GoalsCoreService",
    "GoalsIntelligenceService",
    "GoalsLearningService",
    "GoalsPlanningService",
    "GoalsProgressService",
    "GoalsRecommendationService",
    "GoalsSchedulingService",
    "GoalsSearchService",
    "HabitImpactAnalysis",
    "TimelineSuggestion",
]
