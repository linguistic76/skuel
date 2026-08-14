"""
Events Intelligence Service
============================

Handles pure Cypher graph intelligence queries for events.

Architecture: Shell delegates to 3 focused mixins in this directory:
  _core_intelligence_mixin.py        — analyze_event_performance,
                                       goal/habit/knowledge analysis helpers
  _analytics_mixin.py                — analyze_upcoming_events, scheduling recommendations
  _behavioral_signals_mixin.py       — assess_engagement_dual_track, dual-track helpers

Uses pure Cypher for 8-10x performance improvement over sequential queries.
"""

from typing import TYPE_CHECKING, Any

from core.constants import QueryLimit
from core.models.event.event import Event
from core.models.type_hints import UserUID
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.events._analytics_mixin import _AnalyticsMixin
from core.services.events._behavioral_signals_mixin import _BehavioralSignalsMixin
from core.services.events._core_intelligence_mixin import _CoreIntelligenceMixin
from core.services.events.event_relationships import EventRelationships
from core.services.knowledge.knowledge_pattern_analyzer import KnowledgePatternAnalyzer
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports.domain_protocols import EventsOperations
    from core.services.cross_domain.cross_domain_query_service import CrossDomainQueryService
    from core.services.relationships import UnifiedRelationshipService


class EventsIntelligenceService(
    _CoreIntelligenceMixin,
    _AnalyticsMixin,
    _BehavioralSignalsMixin,
    BaseAnalyticsService["EventsOperations", Event],
):
    """
    Graph intelligence service for events using pure Cypher graph intelligence.

    NOTE: This service extends BaseAnalyticsService (ADR-030) and has NO AI dependencies.
    It uses pure graph queries and Python calculations - no LLM or embeddings.

    Handles:
    - Pure Cypher context retrieval (_CoreIntelligenceMixin)
    - Batch event impact analysis, scheduling recommendations (_AnalyticsMixin)
    - Dual-track engagement assessment (_BehavioralSignalsMixin)
    """

    # Service name for hierarchical logging
    _service_name = "events.intelligence"

    def __init__(
        self,
        backend: "EventsOperations",
        graph_intel=None,
        relationship_service: "UnifiedRelationshipService[Any, Any, Any] | None" = None,
        cross_domain_query: "CrossDomainQueryService | None" = None,
        insight_store: Any | None = None,
    ) -> None:
        """
        Initialize events intelligence service.

        Args:
            backend: Protocol-based backend for event operations
            graph_intel: GraphIntelligenceService for pure Cypher analytics
            relationship_service: UnifiedRelationshipService for fetching graph relationships
            cross_domain_query: CrossDomainQueryService for batch cross-domain reads
                                (required for analyze_upcoming_events)
            insight_store: For persisting event-driven insights (optional)
        """
        super().__init__(
            backend=backend,
            graph_intel=graph_intel,
            relationship_service=relationship_service,
            insight_store=insight_store,
        )
        self.cross_domain_query = cross_domain_query
        self._knowledge_analyzer = KnowledgePatternAnalyzer(graph_intel=self.graph_intel)

    # ========================================================================
    # INTELLIGENCEOPERATIONS PROTOCOL METHODS (January 2026)
    # These methods implement the IntelligenceOperations protocol for use
    # with IntelligenceRouteFactory.
    # get_with_context() is inherited from _CoreIntelligenceMixin (_SharedCoreMixin).
    # ========================================================================

    async def get_performance_analytics(
        self, user_uid: UserUID, period_days: int = 30
    ) -> Result[dict[str, Any]]:
        """
        Get event performance analytics for a user.

        Protocol method: Aggregates event metrics over time period.
        Used by IntelligenceRouteFactory for GET /api/events/analytics route.

        Args:
            user_uid: User UID
            period_days: Number of days to analyze (default: 30)

        Returns:
            Result containing analytics data dict
        """
        from datetime import date, timedelta

        end_date = date.today()
        start_date = end_date - timedelta(days=period_days)

        events_result = await self.backend.find_by(user_uid=user_uid)
        if events_result.is_error:
            return Result.fail(events_result)

        all_events = events_result.value or []

        events = [e for e in all_events if e.event_date and start_date <= e.event_date <= end_date]

        total_events = len(events)
        completed_events = [e for e in events if e.is_completed]
        upcoming_events = [e for e in events if not e.is_completed and not e.is_past()]

        completion_rate = len(completed_events) / total_events if total_events > 0 else 0.0

        return Result.ok(
            {
                "user_uid": user_uid,
                "period_days": period_days,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "total_events": total_events,
                "completed_events": len(completed_events),
                "upcoming_events": len(upcoming_events),
                "completion_rate": round(completion_rate, 2),
                "analytics": {
                    "total": total_events,
                    "completed": len(completed_events),
                    "upcoming": len(upcoming_events),
                    "completion_rate_percentage": round(completion_rate * 100, 1),
                },
            }
        )

    async def get_domain_insights(
        self, uid: str, min_confidence: float = 0.7
    ) -> Result[dict[str, Any]]:
        """
        Get domain-specific insights for an event.

        Protocol method: Maps to analyze_event_performance.
        Used by IntelligenceRouteFactory for GET /api/events/insights route.

        Args:
            uid: Event UID
            min_confidence: Minimum confidence threshold (default: 0.7)

        Returns:
            Result containing insights data dict
        """
        return await self.analyze_event_performance(uid)

    async def analyze_learning_patterns(
        self, user_uid: UserUID, timeframe_days: int = 30
    ) -> Result[list[Any]]:
        """Detect knowledge-learning patterns across the user's event activities."""
        entities_result = await self.backend.find_by(user_uid=user_uid, limit=QueryLimit.MAXIMUM)
        if entities_result.is_error:
            return Result.fail(entities_result)

        service = self.relationships

        async def _fetch_event_rels(uid: str) -> EventRelationships:
            if service:
                return await EventRelationships.fetch(uid, service)
            return EventRelationships.empty()

        return await self._knowledge_analyzer.analyze_learning_patterns(
            entities_result.value, _fetch_event_rels, timeframe_days
        )
