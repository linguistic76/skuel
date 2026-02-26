"""
Tasks Service Sub-Services
===========================

This package contains focused sub-services that compose the unified TasksService facade.

Architecture: Facade Pattern (7 sub-services)
- Each sub-service handles ONE specific responsibility
- TasksService (facade) auto-delegates to appropriate sub-service via explicit delegation methods
- ~35 auto-generated delegation methods + explicit orchestration methods
- Zero breaking changes to external code

Sub-Services:
- TasksCoreService: CRUD operations, event publishing
- TasksSearchService: Search, discovery, filtering
- TasksProgressService: Progress tracking, completion with cascade
- TasksSchedulingService: Scheduling, capacity management
- TasksPlanningService: Context-aware planning and recommendations
- TasksIntelligenceService: Pure Cypher analytics (NO AI dependencies)
- TasksAIService: AI-powered features (LLM/embeddings) - OPTIONAL

Common Import Pattern (Production):
    from core.services.tasks_service import TasksService  # Facade
    result = await tasks_service.create_task(request, user_uid)

Direct Sub-Service Import (Testing/Composition):
    from core.services.tasks import TasksCoreService
    core = TasksCoreService(backend=mock_backend)

Documentation:
- Quick Start: /docs/guides/BASESERVICE_QUICK_START.md
- Sub-Service Catalog: /docs/reference/SUB_SERVICE_CATALOG.md
- Method Index: /docs/reference/BASESERVICE_METHOD_INDEX.md
- Service Topology: /docs/architecture/SERVICE_TOPOLOGY.md

Architecture Notes:
- TasksRelationshipService replaced by UnifiedRelationshipService (December 2025)
- TasksGraphNativeService removed, replaced by UnifiedRelationshipService (January 2026 - ADR-029)
- Intelligence/AI separation: IntelligenceService (analytics) vs AIService (LLM) - ADR-030
- TasksAnalyticsService removed: analytics now via direct AnalyticsEngine calls (January 2026)
"""

# Import implemented services
from core.services.tasks.tasks_ai_service import TasksAIService
from core.services.tasks.tasks_core_service import TasksCoreService
from core.services.tasks.tasks_intelligence_service import TasksIntelligenceService
from core.services.tasks.tasks_planning_service import TasksPlanningService
from core.services.tasks.tasks_progress_service import TasksProgressService
from core.services.tasks.tasks_scheduling_service import TasksSchedulingService
from core.services.tasks.tasks_search_service import TasksSearchService

__all__ = [
    "TasksAIService",
    "TasksCoreService",
    "TasksIntelligenceService",
    "TasksPlanningService",
    "TasksProgressService",
    "TasksSchedulingService",
    "TasksSearchService",
]
