"""
Core Intelligence Mixin — EventsIntelligenceService
====================================================

Event context retrieval and performance analysis.

Part of events_intelligence_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.enums import EntityStatus
from core.services.intelligence import calculate_event_performance_metrics
from core.services.intelligence._core_intelligence_mixin import (
    _CoreIntelligenceMixin as _SharedCoreMixin,
)
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.models.event.event import Event
    from core.models.graph.path_aware_types import EventCrossContext


class _CoreIntelligenceMixin(_SharedCoreMixin):
    """
    Event context retrieval and performance analysis for EventsIntelligenceService.

    ``get_with_context`` (mechanism B) is inherited from the shared
    ``_CoreIntelligenceMixin``; this mixin adds event performance
    analysis methods.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by EventsIntelligenceService.__init__
    orchestrator: Any
    graph_intel: Any
    relationships: Any
    logger: Any
    # Provided by BaseAnalyticsService via multiple inheritance on the composed service.
    _analyze_entity_with_typed_context: Any

    async def analyze_event_performance(self, uid: str) -> Result[dict[str, Any]]:
        """
        Analyze event with goal support and habit reinforcement.

        Returns comprehensive analysis:
        - Goal contribution metrics
        - Habit reinforcement impact
        - Knowledge practice tracking
        - Overall impact score

        Args:
            uid: UID of the event

        Returns:
            Result containing performance analysis

        Refactoring:
        - Uses BaseAnalyticsService._analyze_entity_with_typed_context over the CANONICAL
          path-aware reader (get_cross_domain_context_typed), replacing the previous direct
          per-helper ``get_cross_domain_context`` / ``get_related_uids`` /
          ``get_habit_links_for_events`` construction. The ``/api/events/insights`` payload
          shape (nested goal_support / habit_reinforcement / knowledge_reinforcement +
          overall_impact_score) is preserved; cascade_impact / path_aware_context are
          additive. Event surfaces NO recommendations list, so no recommendations_fn.
        """
        analysis_result = await self._analyze_entity_with_typed_context(
            uid=uid,
            metrics_fn=calculate_event_performance_metrics,
        )
        if analysis_result.is_error:
            return analysis_result

        analysis = analysis_result.value
        event: Event = analysis["entity"]
        context: EventCrossContext = analysis["context"]
        metrics = analysis["metrics"]

        completed = event.status == EntityStatus.COMPLETED

        # Goal support — single-goal lens (mirrors the legacy ``goals[0]`` shape).
        # CONTRIBUTES_TO_GOAL exposes only uid/title (no contribution_weight), so the legacy
        # weight always defaulted to 1.0; preserved.
        if context.goals:
            goal_support = {
                "supports_goals": True,
                "goal_uid": context.goals[0].uid,
                "contribution_weight": 1.0,
                "status": event.status,
                "completed": completed,
            }
        else:
            goal_support = {
                "supports_goals": False,
                "goal_uid": None,
                "contribution_weight": 0.0,
            }

        # Habit reinforcement — single-habit lens (mirrors the legacy single habit_uid shape).
        if context.habits:
            habit_reinforcement: dict[str, Any] = {
                "reinforces_habit": True,
                "habit_uid": context.habits[0].uid,
                "quality_score": event.habit_completion_quality,
                "status": event.status,
                "completed": completed,
            }
        else:
            habit_reinforcement = {
                "reinforces_habit": False,
                "habit_uid": None,
                "quality_score": None,
            }

        # Knowledge reinforcement — full list lens.
        knowledge_uids = [k.uid for k in context.knowledge]
        if knowledge_uids:
            knowledge_reinforcement: dict[str, Any] = {
                "reinforces_knowledge": True,
                "knowledge_units": knowledge_uids,
                "knowledge_count": len(knowledge_uids),
                "study_time_minutes": event.duration_minutes,
                "status": event.status,
            }
        else:
            knowledge_reinforcement = {
                "reinforces_knowledge": False,
                "knowledge_units": [],
                "knowledge_count": 0,
            }

        return Result.ok(
            {
                "event_uid": uid,
                "event_title": event.title,
                "status": event.status,
                "goal_support": goal_support,
                "habit_reinforcement": habit_reinforcement,
                "knowledge_reinforcement": knowledge_reinforcement,
                "overall_impact_score": self._calculate_overall_impact(
                    goal_support, habit_reinforcement, knowledge_reinforcement
                ),
                # Connection breadth across cross-domain edges (typed-reader equivalent of
                # the former mechanism-B ``len(context.all_relationships)`` depth metric).
                "graph_context_depth": context.total_connections,
                # Rich path-aware additions (additive — existing keys unchanged).
                "cascade_impact": metrics["cascade_impact"],
                "path_aware_context": metrics["path_aware_context"],
            }
        )

    @staticmethod
    def _calculate_overall_impact(
        goal_support: dict[str, Any],
        habit_impact: dict[str, Any],
        knowledge_impact: dict[str, Any],
    ) -> float:
        """Calculate overall impact score.

        Preserved unchanged from the pre-convergence direct-construction method: goal term
        weighs the (always-1.0) contribution_weight, habit term adds 1.0 plus a
        quality_score/5.0 bonus, knowledge term adds 0.5 per practiced unit.
        """
        score = 0.0

        if goal_support.get("supports_goals"):
            score += goal_support.get("contribution_weight", 1.0)

        if habit_impact.get("reinforces_habit"):
            score += 1.0
            if habit_impact.get("quality_score"):
                score += habit_impact["quality_score"] / 5.0

        if knowledge_impact.get("reinforces_knowledge"):
            score += knowledge_impact["knowledge_count"] * 0.5

        return score
