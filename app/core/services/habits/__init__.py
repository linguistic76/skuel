"""
Habits Sub-Services
===================

This package contains focused sub-services and facade mixins that compose the unified
HabitsService facade.

Architecture: Facade Pattern (12 sub-services + 3 facade mixins)
- Each sub-service handles ONE specific responsibility
- HabitsService (facade) delegates to appropriate sub-service via explicit delegation methods
- Facade mixins host methods with custom logic (extracted April 2026)
- Most complex Activity Domain (streaks, consistency, event integration)
- Zero breaking changes to external code

Facade Mixins (in this package):
- _CompletionMixin: completion tracking, status lifecycle, reminder config
- _EnrichmentMixin: analytics delegates, enriched data views
- _OrchestrationMixin: graph relationship creation, cross-domain orchestration

Sub-Services (in this package):
- HabitsCoreService: CRUD operations, event publishing
- HabitsSearchService: Search, discovery, filtering
- HabitsProgressService: Streaks, consistency tracking, keystone habits
- HabitsLearningService: Learning path integration, knowledge reinforcement
- HabitsPlanningService: Context-aware habit recommendations
- HabitsSchedulingService: Smart scheduling, capacity management
- HabitsIntelligenceService: Pure Cypher analytics + event scheduling intelligence (NO AI dependencies)
- HabitEventHandlerService: Event-driven reactive logic (fire-and-forget handlers)
- HabitsPatternService: Atomic Habits pattern recognition with confidence scoring
- HabitsGoalAnalyticsService: SHELVED (2026-03-28)
- HabitsAIService: SHELVED (2026-03-28)

Common Import Pattern (Production):
    from core.services.habits_service import HabitsService  # Facade
    result = await habits_service.create_habit(request, user_uid)

Direct Sub-Service Import (Testing/Composition):
    from core.services.habits import HabitsCoreService
    core = HabitsCoreService(backend=mock_backend)

Documentation:
- Quick Start: /docs/guides/BASESERVICE_QUICK_START.md
- Sub-Service Catalog: /docs/reference/SUB_SERVICE_CATALOG.md
- Method Index: /docs/reference/BASESERVICE_METHOD_INDEX.md
- Service Topology: /docs/architecture/SERVICE_TOPOLOGY.md

Architecture Notes:
- Uses UnifiedRelationshipService for all relationship operations
- HabitAchievementService absorbed into HabitEventHandlerService (March 2026)
"""

from core.services.habits._completion_mixin import _CompletionMixin
from core.services.habits._enrichment_mixin import _EnrichmentMixin
from core.services.habits._orchestration_mixin import _OrchestrationMixin
from core.services.habits.habit_event_handler_service import HabitEventHandlerService
from core.services.habits.habits_core_service import HabitsCoreService
from core.services.habits.habits_intelligence_service import HabitsIntelligenceService
from core.services.habits.habits_learning_service import HabitsLearningService
from core.services.habits.habits_pattern_service import HabitsPatternService
from core.services.habits.habits_planning_service import HabitsPlanningService
from core.services.habits.habits_progress_service import HabitsProgressService
from core.services.habits.habits_scheduling_service import HabitsSchedulingService
from core.services.habits.habits_search_service import HabitsSearchService

# Shelved (2026-03-28): HabitsGoalAnalyticsService, HabitsAIService

__all__ = [
    "_CompletionMixin",
    "_EnrichmentMixin",
    "_OrchestrationMixin",
    "HabitEventHandlerService",
    "HabitsSearchService",
    "HabitsCoreService",
    "HabitsIntelligenceService",
    "HabitsLearningService",
    "HabitsPatternService",
    "HabitsPlanningService",
    "HabitsProgressService",
    "HabitsSchedulingService",
]
