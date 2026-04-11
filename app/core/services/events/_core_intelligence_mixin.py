"""
Core Intelligence Mixin — EventsIntelligenceService
====================================================

Event context retrieval and performance analysis.

Part of events_intelligence_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.constants import GraphDepth
from core.models.enums import EntityStatus
from core.services.intelligence._core_intelligence_mixin import (
    _CoreIntelligenceMixin as _SharedCoreMixin,
)
from core.utils.decorators import requires_graph_intelligence, with_error_handling
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.event.event import Event
    from core.models.graph_context import GraphContext


class _CoreIntelligenceMixin(_SharedCoreMixin):
    """
    Event context retrieval and performance analysis for EventsIntelligenceService.

    Extends the shared _CoreIntelligenceMixin to add event-specific context
    retrieval (get_event_with_context) and performance analysis methods.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by EventsIntelligenceService.__init__
    orchestrator: Any
    graph_intel: Any
    relationships: Any
    logger: Any

    @requires_graph_intelligence("get_event_with_context")
    @with_error_handling("get_event_with_context", error_type="system", uid_param="uid")
    async def get_event_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[Event, GraphContext]]:
        """
        Get event with full graph context using pure Cypher graph intelligence.

        Single query retrieves:
        - Event entity
        - Supporting goals
        - Reinforcing habits
        - Related knowledge units
        - Learning path connections
        - Semantic relationships

        8-10x faster than sequential queries.

        Args:
            uid: UID of the event
            depth: Graph traversal depth

        Returns:
            Result containing tuple of (Event, GraphContext)
        """
        if not self.graph_intel:
            return Result.fail(
                Errors.system(
                    message="GraphIntelligenceService is required for event context retrieval"
                )
            )

        context_result = await self.graph_intel.get_entity_context(
            entity_uid=uid, entity_type="Entity", depth=depth
        )

        if context_result.is_error:
            return context_result  # type: ignore[return-value]

        context = context_result.value
        event = context.primary_entity

        self.logger.info(
            f"Retrieved event {uid} with context: "
            f"{len(context.relationships)} relationships, depth={depth}"
        )

        return Result.ok((event, context))

    async def analyze_event_performance(self, uid: str) -> Result[dict[str, Any]]:
        """
        Analyze event with goal support and habit reinforcement.

        Returns comprehensive analysis:
        - Goal contribution metrics
        - Habit reinforcement impact
        - Knowledge practice tracking
        - Learning path progression

        Args:
            uid: UID of the event

        Returns:
            Result containing performance analysis
        """
        context_result = await self.get_event_with_context(uid, GraphDepth.NEIGHBORHOOD)
        if context_result.is_error:
            return Result.fail(context_result)

        event, context = context_result.value

        goal_support = await self._analyze_goal_support(event, context)
        habit_impact = await self._analyze_habit_impact(event, context)
        knowledge_impact = await self._analyze_knowledge_impact(event, context)

        analysis = {
            "event_uid": uid,
            "event_title": event.title,
            "status": event.status,
            "goal_support": goal_support,
            "habit_reinforcement": habit_impact,
            "knowledge_reinforcement": knowledge_impact,
            "overall_impact_score": self._calculate_overall_impact(
                goal_support, habit_impact, knowledge_impact
            ),
            "graph_context_depth": len(context.all_relationships),
        }

        return Result.ok(analysis)

    async def _analyze_goal_support(self, event: Event, _context: GraphContext) -> dict[str, Any]:
        """
        Analyze how event supports goals.

        GRAPH-NATIVE: Queries graph relationships instead of denormalized fields.
        Graph pattern: (event)-[:SUPPORTS_GOAL {contribution_weight}]->(goal)
        """
        if self.relationships is None:
            return {"supports_goals": False, "goal_uid": None, "contribution_weight": 0.0}

        context_result = await self.relationships.get_cross_domain_context(event.uid)
        if context_result.is_error:
            return {"supports_goals": False, "goal_uid": None, "contribution_weight": 0.0}

        context = context_result.value
        goals = context.get("goals", [])

        if not goals:
            return {"supports_goals": False, "goal_uid": None, "contribution_weight": 0.0}

        goal = goals[0]
        contribution_weight = goal.get("contribution_weight", 1.0)

        return {
            "supports_goals": True,
            "goal_uid": goal.get("uid"),
            "contribution_weight": contribution_weight,
            "status": event.status,
            "completed": event.status == EntityStatus.COMPLETED,
        }

    async def _analyze_habit_impact(self, event: Event, _context: GraphContext) -> dict[str, Any]:
        """
        Analyze habit reinforcement impact.

        Note: reinforces_habit_uid field still exists in Event model (not yet migrated to graph-only).
        GRAPH-NATIVE: Uses habit_completion_quality instead of removed quality_score field.
        """
        if not event.reinforces_habit_uid:
            return {"reinforces_habit": False, "habit_uid": None, "quality_score": None}

        return {
            "reinforces_habit": True,
            "habit_uid": event.reinforces_habit_uid,
            "quality_score": event.habit_completion_quality,  # GRAPH-NATIVE: renamed from quality_score
            "status": event.status,
            "completed": event.status == EntityStatus.COMPLETED,
        }

    async def _analyze_knowledge_impact(
        self, event: Event, _context: GraphContext
    ) -> dict[str, Any]:
        """
        Analyze knowledge reinforcement.

        GRAPH-NATIVE: Queries graph relationships instead of denormalized fields.
        Graph pattern: (event)-[:PRACTICES_KNOWLEDGE]->(ku)
        """
        if self.relationships is None:
            return {"reinforces_knowledge": False, "knowledge_units": [], "knowledge_count": 0}

        knowledge_result = await self.relationships.get_related_uids("knowledge", event.uid)
        if knowledge_result.is_error:
            return {"reinforces_knowledge": False, "knowledge_units": [], "knowledge_count": 0}

        knowledge_uids = knowledge_result.value
        if not knowledge_uids:
            return {"reinforces_knowledge": False, "knowledge_units": [], "knowledge_count": 0}

        return {
            "reinforces_knowledge": True,
            "knowledge_units": knowledge_uids,
            "knowledge_count": len(knowledge_uids),
            "study_time_minutes": getattr(event, "duration_minutes", None),
            "status": event.status,
        }

    def _calculate_overall_impact(
        self,
        goal_support: dict[str, Any],
        habit_impact: dict[str, Any],
        knowledge_impact: dict[str, Any],
    ) -> float:
        """Calculate overall impact score."""
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
