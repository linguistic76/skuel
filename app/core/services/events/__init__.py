"""
Events Sub-Services
===================

This package contains focused sub-services that compose the unified EventsService facade.

Architecture: Facade Pattern (7 sub-services)
- Each sub-service handles ONE specific responsibility
- EventsService (facade) auto-delegates to appropriate sub-service via FacadeDelegationMixin
- Calendar and scheduling domain with habit integration
- Zero breaking changes to external code

Sub-Services:
- EventsCoreService: CRUD operations, event publishing
- EventsSearchService: Search, discovery, filtering
- EventsProgressService: Event attendance and completion tracking
- EventsSchedulingService: Scheduling, recurrence, capacity management
- EventsLearningService: Learning and knowledge integration
- EventsHabitIntegrationService: Cross-domain habits integration
- EventsIntelligenceService: Pure Cypher analytics (NO AI dependencies)

Common Import Pattern (Production):
    from core.services.events_service import EventsService  # Facade
    result = await events_service.create_event(request, user_uid)

Direct Sub-Service Import (Testing/Composition):
    from core.services.events import EventsCoreService
    core = EventsCoreService(backend=mock_backend)

Documentation:
- Quick Start: /docs/guides/BASESERVICE_QUICK_START.md
- Sub-Service Catalog: /docs/reference/SUB_SERVICE_CATALOG.md
- Method Index: /docs/reference/BASESERVICE_METHOD_INDEX.md
- Service Topology: /docs/architecture/SERVICE_TOPOLOGY.md

Architecture Notes:
- EventsRelationshipService replaced by UnifiedRelationshipService (December 2025)

Version: 2.1.0
Date: 2026-01-29
"""

from core.services.events.events_core_service import EventsCoreService
from core.services.events.events_habit_integration_service import EventsHabitIntegrationService
from core.services.events.events_intelligence_service import EventsIntelligenceService
from core.services.events.events_learning_service import EventsLearningService
from core.services.events.events_progress_service import EventsProgressService
from core.services.events.events_scheduling_service import EventsSchedulingService
from core.services.events.events_search_service import EventsSearchService

__all__ = [
    "EventsCoreService",
    "EventsHabitIntegrationService",
    "EventsIntelligenceService",
    "EventsLearningService",
    "EventsProgressService",
    "EventsSchedulingService",
    "EventsSearchService",
]
