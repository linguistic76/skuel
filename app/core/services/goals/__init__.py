"""
Goals Sub-Services
===================

This package contains focused sub-services and intelligence mixins that compose
the unified GoalsService facade.

Architecture: Facade Pattern (8 sub-services + intelligence mixins + 2 facade mixins)
- Each sub-service handles ONE specific responsibility
- GoalsService (facade) delegates to appropriate sub-service via explicit delegation methods
- GoalsService composes 2 facade mixins for relationship + orchestration methods (April 2026)
- GoalsIntelligenceService delegates to focused mixins (April 2026); graph context
  retrieval (get_with_context) comes from the shared
  core.services.intelligence._core_intelligence_mixin
- ~40+ delegation methods + explicit orchestration methods
- Zero breaking changes to external code

Facade Mixins (compose into GoalsService):
- _OrchestrationMixin: create_goal_with_context, generate_tasks_for_goal, assess_goal_feasibility
- _RelationshipMixin: link_goal_to_habit/knowledge/principle, semantic relationships

Intelligence Mixins (compose into GoalsIntelligenceService):
- _AnalyticsMixin: progress dashboard, completion forecast, learning requirements
- _PredictiveMixin: success prediction, habit impact, risk assessment, scenarios
- _DualTrackMixin: dual-track progress assessment (user vision vs system measurement)

Sub-Services (in this package):
- GoalsCoreService: CRUD operations, event publishing
- GoalsSearchService: Search, discovery, filtering
- GoalsProgressService: Progress tracking, milestones, completion
- GoalsLearningService: Learning path integration, knowledge connections
- GoalsPlanningService: Context-aware planning and recommendations
- GoalsSchedulingService: Capacity management, schedule optimization
- GoalEventHandlerService: Event-driven reactive handlers (achievements, abandonment, progress)
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
- Uses UnifiedRelationshipService for all relationship operations
- GoalsRecommendationService replaced by GoalEventHandlerService (March 2026)
"""

from core.services.goals._analytics_mixin import _AnalyticsMixin
from core.services.goals._dual_track_mixin import _DualTrackMixin
from core.services.goals._orchestration_mixin import _OrchestrationMixin
from core.services.goals._predictive_mixin import _PredictiveMixin
from core.services.goals._relationship_mixin import _RelationshipMixin
from core.services.goals.goal_event_handler_service import GoalEventHandlerService
from core.services.goals.goals_core_service import GoalsCoreService
from core.services.goals.goals_intelligence_service import (
    GoalPrediction,
    GoalsIntelligenceService,
    HabitImpactAnalysis,
)
from core.services.goals.goals_learning_service import GoalsLearningService
from core.services.goals.goals_planning_service import GoalsPlanningService
from core.services.goals.goals_progress_service import GoalsProgressService
from core.services.goals.goals_scheduling_service import (
    AchievabilityResult,
    GoalCapacityResult,
    GoalSequenceItem,
    GoalsSchedulingService,
    TimelineSuggestion,
)
from core.services.goals.goals_search_service import GoalsSearchService

__all__ = [
    "_AnalyticsMixin",
    "_DualTrackMixin",
    "_OrchestrationMixin",
    "_PredictiveMixin",
    "_RelationshipMixin",
    "AchievabilityResult",
    "GoalCapacityResult",
    "GoalEventHandlerService",
    "GoalPrediction",
    "GoalSequenceItem",
    "GoalsCoreService",
    "GoalsIntelligenceService",
    "GoalsLearningService",
    "GoalsPlanningService",
    "GoalsProgressService",
    "GoalsSchedulingService",
    "GoalsSearchService",
    "HabitImpactAnalysis",
    "TimelineSuggestion",
]
