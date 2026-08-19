"""
Analytics Mixin — EventsIntelligenceService
============================================

Batch event analysis and scheduling recommendations.

Part of events_intelligence_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.services.events._habit_links import enrich_events_with_habit_links
from core.services.intelligence import RecommendationEngine
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.type_hints import FilterParams, UserUID
    from core.ports.domain_protocols import EventsOperations
    from core.services.cross_domain.cross_domain_query_service import CrossDomainQueryService


class _AnalyticsMixin:
    """
    Batch event analysis and scheduling recommendations for EventsIntelligenceService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by EventsIntelligenceService.__init__
    backend: "EventsOperations"
    relationships: Any
    cross_domain_query: CrossDomainQueryService | None
    logger: Any

    async def analyze_upcoming_events(
        self, user_uid: UserUID, days_ahead: int = 7
    ) -> Result[dict[str, Any]]:
        """
        Analyze all upcoming events for impact and optimization opportunities.

        Args:
            user_uid: UID of the user
            days_ahead: Number of days to analyze

        Returns:
            Result containing batch analysis
        """
        from datetime import date, timedelta

        from core.services.cross_domain.cross_domain_types import EventImpactRow

        end_date = date.today() + timedelta(days=days_ahead)

        filters: FilterParams = {
            "user_uid": user_uid,
            "event_date__gte": date.today().isoformat(),
            "event_date__lte": end_date.isoformat(),
            "status": "scheduled",
        }

        result = await self.backend.list(filters=filters)
        if result.is_error:
            return Result.fail(result)

        events, _ = result.value
        # Populate the derived reinforces_habit_uid from the REINFORCES_HABIT edge.
        events = await enrich_events_with_habit_links(self.backend, events)

        high_impact_events = []
        low_impact_events = []
        total_goal_support = 0
        total_habit_reinforcement = 0

        if self.cross_domain_query is None:
            return Result.fail(
                Errors.system(
                    message="CrossDomainQueryService not available",
                    operation="analyze_upcoming_events",
                )
            )

        batch_result = await self.cross_domain_query.get_event_impact_batch(
            user_uid=user_uid,
            start_date=date.today(),
            end_date=end_date,
        )
        if batch_result.is_error:
            return Result.fail(batch_result)

        impact_lookup: dict[str, EventImpactRow] = {
            row.event_uid: row for row in batch_result.value.rows
        }

        for event in events:
            impact_score: float = 0
            row = impact_lookup.get(event.uid)

            if row and row.goal_count > 0:
                impact_score += 1
                total_goal_support += 1

            if event.reinforces_habit_uid:
                impact_score += 1
                total_habit_reinforcement += 1

            if row and row.knowledge_count > 0:
                impact_score += row.knowledge_count * 0.5

            if impact_score >= 2.0:
                high_impact_events.append(
                    {
                        "uid": event.uid,
                        "title": event.title,
                        "event_date": event.event_date,
                        "impact_score": impact_score,
                    }
                )
            elif impact_score < 1.0:
                low_impact_events.append(
                    {
                        "uid": event.uid,
                        "title": event.title,
                        "event_date": event.event_date,
                        "impact_score": impact_score,
                    }
                )

        analysis = {
            "total_upcoming_events": len(events),
            "high_impact_events": high_impact_events,
            "low_impact_events": low_impact_events,
            "total_goal_supporting_events": total_goal_support,
            "total_habit_reinforcing_events": total_habit_reinforcement,
            "days_analyzed": days_ahead,
            "recommendations": self._generate_scheduling_recommendations(
                len(result.value), len(high_impact_events), len(low_impact_events)
            ),
        }

        return Result.ok(analysis)

    def _generate_scheduling_recommendations(
        self, total_events: int, high_impact_count: int, low_impact_count: int
    ) -> list[str]:
        """Generate scheduling recommendations based on analysis.

        Uses RecommendationEngine for structured threshold-based recommendations.
        """
        low_impact_ratio = low_impact_count / total_events if total_events > 0 else 0
        high_impact_ratio = high_impact_count / total_events if total_events > 0 else 0

        return (
            RecommendationEngine()
            .with_metrics(
                {
                    "total_events": total_events,
                    "low_impact_ratio": low_impact_ratio,
                    "high_impact_ratio": high_impact_ratio,
                }
            )
            .add_conditional(
                low_impact_ratio > 0.3,
                f"Consider linking {low_impact_count} low-impact events to goals or habits",
            )
            .add_conditional(
                high_impact_ratio < 0.2,
                "Increase high-impact events by scheduling more goal-supporting activities",
            )
            .add_threshold_check(
                "total_events",
                threshold=5,
                message="Schedule more events to maintain consistent progress",
                comparison="lt",
            )
            .add_threshold_check(
                "total_events",
                threshold=20,
                message="Consider consolidating events to avoid overcommitment",
                comparison="gt",
            )
            .build()
        )
