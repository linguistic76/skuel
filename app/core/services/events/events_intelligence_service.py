"""
Events Intelligence Service
============================

Handles pure Cypher graph intelligence queries for events.

Responsibilities:
- Get event with full graph context (Phase 1-4)
- Analyze event performance and impact
- Get event's goal contribution analysis
- Get event's knowledge reinforcement tracking

Uses pure Cypher for 8-10x performance improvement over sequential queries.
"""

from typing import TYPE_CHECKING, Any

from core.constants import GraphDepth
from core.models.enums import Domain
from core.models.enums.activity_enums import EngagementLevel
from core.models.graph_context import GraphContext
from core.models.ku.ku_dto import KuDTO
from core.models.ku.ku_event import EventKu
from core.models.shared.dual_track import DualTrackResult
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.events.event_relationships import EventRelationships
from core.services.intelligence import (
    GraphContextOrchestrator,
    RecommendationEngine,
)
from core.utils.decorators import with_error_handling
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.services.protocols import BackendOperations
    from core.services.protocols.domain_protocols import EventsRelationshipOperations


class EventsIntelligenceService(BaseAnalyticsService["BackendOperations[EventKu]", EventKu]):
    """
    Graph intelligence service for events using pure Cypher graph intelligence.

    NOTE: This service extends BaseAnalyticsService (ADR-030) and has NO AI dependencies.
    It uses pure graph queries and Python calculations - no LLM or embeddings.

    Pure Cypher Pattern:
    - Single query retrieves event + full graph context
    - 8-10x faster than multiple sequential queries
    - Handles relationships, learning paths, goal support, habit reinforcement


    Source Tag: "events_intelligence_service_explicit"
    - Format: "events_intelligence_service_explicit" for user-created relationships
    - Format: "events_intelligence_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from events_intelligence metadata
    - 0.5-0.7: Suggested based on patterns
    - <0.5: Low confidence, needs verification

    SKUEL Architecture:
    - Uses CypherGenerator for ALL graph queries
    - No APOC calls (Phase 5 eliminated those)
    - Returns Result[T] for error handling
    - Logs operations with structured logging
    - NO embeddings_service or llm_service (ADR-030)

    """

    # Service name for hierarchical logging
    _service_name = "events.intelligence"

    def __init__(
        self,
        backend: "BackendOperations[EventKu]",
        graph_intelligence_service=None,
        relationship_service: "EventsRelationshipOperations | None" = None,
    ) -> None:
        """
        Initialize events intelligence service.

        Args:
            backend: Protocol-based backend for event operations,
            graph_intelligence_service: GraphIntelligenceService for pure Cypher analytics,
            relationship_service: EventsRelationshipOperations protocol for fetching graph relationships
        """
        super().__init__(
            backend=backend,
            graph_intelligence_service=graph_intelligence_service,
            relationship_service=relationship_service,
        )
        # Initialize GraphContextOrchestrator for get_with_context pattern
        if graph_intelligence_service:
            self.orchestrator = GraphContextOrchestrator[EventKu, KuDTO](
                service=self,
                backend_get_method="get",  # EventsService uses generic 'get'
                dto_class=KuDTO,
                model_class=EventKu,
                domain=Domain.EVENTS,
            )

    # ========================================================================
    # INTELLIGENCEOPERATIONS PROTOCOL METHODS (January 2026)
    # These methods implement the IntelligenceOperations protocol for use
    # with IntelligenceRouteFactory.
    # ========================================================================

    async def get_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[EventKu, GraphContext]]:
        """
        Get event with full graph context.

        Protocol method: Uses GraphContextOrchestrator for generic pattern.
        Used by IntelligenceRouteFactory for GET /api/events/context route.

        Args:
            uid: Event UID
            depth: Graph traversal depth (default: 2)

        Returns:
            Result containing (Event, GraphContext) tuple
        """
        if self.orchestrator is None:
            return Result.fail(
                Errors.system(
                    message="Graph intelligence service required for context queries",
                    operation="get_with_context",
                )
            )
        return await self.orchestrator.get_with_context(uid=uid, depth=depth)

    async def get_performance_analytics(
        self, user_uid: str, period_days: int = 30
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

        # Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(days=period_days)

        # Get events for user within period
        events_result = await self.backend.find_by(user_uid=user_uid)
        if events_result.is_error:
            return Result.fail(events_result.expect_error())

        all_events = events_result.value or []

        # Filter to events within the period
        events = [e for e in all_events if e.event_date and start_date <= e.event_date <= end_date]

        # Calculate analytics
        total_events = len(events)
        completed_events = [e for e in events if e.is_completed]
        upcoming_events = [e for e in events if not e.is_completed and not e.is_past()]

        # Calculate completion rate
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
        # analyze_event_performance doesn't take min_confidence, but we can use it for filtering
        return await self.analyze_event_performance(uid)

    # ========================================================================
    # PURE CYPHER GRAPH CONTEXT
    # ========================================================================

    @with_error_handling("get_event_with_context", error_type="system", uid_param="uid")
    async def get_event_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[EventKu, GraphContext]]:
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
            uid: UID of the event,
            depth: Graph traversal depth

        Returns:
            Result containing tuple of (Event, GraphContext)
        """
        # Fail-fast: GraphIntelligenceService is required for context retrieval
        if not self.graph_intel:
            return Result.fail(
                Errors.system(
                    message="GraphIntelligenceService is required for event context retrieval"
                )
            )

        # Use pure Cypher graph intelligence
        context_result = await self.graph_intel.get_entity_context(
            entity_uid=uid, entity_type="Ku", depth=depth
        )

        if context_result.is_error:
            return context_result

        context = context_result.value
        event = context.primary_entity

        self.logger.info(
            f"Retrieved event {uid} with context: "
            f"{len(context.relationships)} relationships, depth={depth}"
        )

        return Result.ok((event, context))

    async def analyze_event_performance(self, uid: str) -> Result[dict[str, Any]]:
        """
        Analyze event with goal support and habit reinforcement using Phase 1-4.

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
        # Get event with context
        context_result = await self.get_event_with_context(uid, GraphDepth.NEIGHBORHOOD)
        if context_result.is_error:
            return Result.fail(context_result.expect_error())  # P3: Type-safe error propagation

        event, context = context_result.value

        # Analyze goal support
        goal_support = await self._analyze_goal_support(event, context)

        # Analyze habit reinforcement
        habit_impact = await self._analyze_habit_impact(event, context)

        # Analyze knowledge reinforcement
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
            "graph_context_depth": len(context.all_relationships),  # P3: Fixed attribute name
        }

        return Result.ok(analysis)

    async def get_event_goal_support(self, uid: str, depth: int = 2) -> Result[dict[str, Any]]:
        """
        Get event's goal contribution analysis using Phase 1-4.

        Args:
            uid: UID of the event,
            depth: Graph traversal depth

        Returns:
            Result containing goal support analysis
        """
        context_result = await self.get_event_with_context(uid, depth)
        if context_result.is_error:
            return Result.fail(context_result.expect_error())  # P3: Type-safe error propagation

        event, context = context_result.value

        goal_support = await self._analyze_goal_support(event, context)

        # GRAPH-NATIVE: Fetch goal relationships from graph
        # Fail-fast: UnifiedRelationshipService is required
        if not self.relationships:
            return Result.fail(
                Errors.system(
                    message="UnifiedRelationshipService is required for goal support analysis"
                )
            )

        # Fetch all event relationships in parallel (includes goals via CONTRIBUTES_TO_GOAL)
        rels = await EventRelationships.fetch(uid, self.relationships)
        goal_uids = rels.supports_goal_uids

        return Result.ok(
            {
                "event_uid": uid,
                "supports_goal_uids": goal_uids,  # Can support multiple goals
                "goal_contribution_weight": 0.0 if not goal_uids else 1.0,
                "analysis": goal_support,
                "retrieved_via": "pure Cypher graph intelligence with EventRelationships",
            }
        )

    async def get_event_knowledge_reinforcement(
        self, uid: str, depth: int = 2
    ) -> Result[dict[str, Any]]:
        """
        Get event's knowledge practice tracking using Phase 1-4.

        Args:
            uid: UID of the event,
            depth: Graph traversal depth

        Returns:
            Result containing knowledge reinforcement analysis
        """
        context_result = await self.get_event_with_context(uid, depth)
        if context_result.is_error:
            return Result.fail(context_result.expect_error())  # P3: Type-safe error propagation

        event, context = context_result.value

        knowledge_impact = await self._analyze_knowledge_impact(event, context)

        # GRAPH-NATIVE: Fetch knowledge practice relationships from graph
        # Fail-fast: UnifiedRelationshipService is required
        if not self.relationships:
            return Result.fail(
                Errors.system(
                    message="UnifiedRelationshipService is required for knowledge reinforcement analysis"
                )
            )

        # Fetch all event relationships in parallel
        rels = await EventRelationships.fetch(uid, self.relationships)
        practices_knowledge_uids = rels.practices_knowledge_uids

        return Result.ok(
            {
                "event_uid": uid,
                "practices_knowledge_uids": practices_knowledge_uids,  # Proper naming
                "analysis": knowledge_impact,
                "retrieved_via": "pure Cypher graph intelligence with EventRelationships",
            }
        )

    # ========================================================================
    # BATCH INTELLIGENCE OPERATIONS
    # ========================================================================

    async def analyze_upcoming_events(
        self, user_uid: str, days_ahead: int = 7
    ) -> Result[dict[str, Any]]:
        """
        Analyze all upcoming events for impact and optimization opportunities.

        Args:
            user_uid: UID of the user,
            days_ahead: Number of days to analyze

        Returns:
            Result containing batch analysis
        """
        from datetime import date, timedelta

        end_date = date.today() + timedelta(days=days_ahead)

        # Get upcoming events
        filters = {
            "user_uid": user_uid,
            "event_date__gte": date.today(),
            "event_date__lte": end_date,
            "status": "scheduled",
        }

        result = await self.backend.list(filters=filters)
        if result.is_error:
            return Result.fail(result.expect_error())

        # Unpack tuple: backend.list() returns (events, total_count)
        events, _ = result.value

        # Analyze each event
        high_impact_events = []
        low_impact_events = []
        total_goal_support = 0
        total_habit_reinforcement = 0

        if self.relationships is None:
            return Result.fail(
                Errors.system(
                    message="EventsRelationshipOperations not available",
                    operation="analyze_event_impact",
                )
            )

        for event in events:
            # Calculate impact score using graph queries for graph relationships
            impact_score = 0

            # Check goal support via graph
            context_result = await self.relationships.get_cross_domain_context(event.uid)
            if context_result.is_ok:
                goals = context_result.value.get("goals", [])
                if goals:
                    impact_score += 1
                    total_goal_support += 1

            # Check habit reinforcement (field still exists in Event model)
            if event.reinforces_habit_uid:
                impact_score += 1
                total_habit_reinforcement += 1

            # Check knowledge practice via graph
            knowledge_result = await self.relationships.get_related_uids("knowledge", event.uid)
            if knowledge_result.is_ok and knowledge_result.value:
                impact_score += len(knowledge_result.value) * 0.5

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
            "total_upcoming_events": len(result.value),
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

    # ========================================================================
    # PRIVATE ANALYSIS HELPERS
    # ========================================================================

    async def _analyze_goal_support(self, event: EventKu, _context: GraphContext) -> dict[str, Any]:
        """
        Analyze how event supports goals.

        GRAPH-NATIVE: Queries graph relationships instead of denormalized fields.
        Graph pattern: (event)-[:SUPPORTS_GOAL {contribution_weight}]->(goal)
        """
        if self.relationships is None:
            return {"supports_goals": False, "goal_uid": None, "contribution_weight": 0.0}

        # Query graph for supported goals
        context_result = await self.relationships.get_cross_domain_context(event.uid)
        if context_result.is_error:
            return {"supports_goals": False, "goal_uid": None, "contribution_weight": 0.0}

        context = context_result.value
        goals = context.get("goals", [])

        if not goals:
            return {"supports_goals": False, "goal_uid": None, "contribution_weight": 0.0}

        # Get first goal and its contribution weight from relationship properties
        goal = goals[0]
        contribution_weight = goal.get("contribution_weight", 1.0)

        return {
            "supports_goals": True,
            "goal_uid": goal.get("uid"),
            "contribution_weight": contribution_weight,
            "status": event.status,
            "completed": event.status == "completed",
        }

    async def _analyze_habit_impact(self, event: EventKu, _context: GraphContext) -> dict[str, Any]:
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
            "completed": event.status == "completed",
        }

    async def _analyze_knowledge_impact(
        self, event: EventKu, _context: GraphContext
    ) -> dict[str, Any]:
        """
        Analyze knowledge reinforcement.

        GRAPH-NATIVE: Queries graph relationships instead of denormalized fields.
        Graph pattern: (event)-[:PRACTICES_KNOWLEDGE]->(ku)
        """
        if self.relationships is None:
            return {"reinforces_knowledge": False, "knowledge_units": [], "knowledge_count": 0}

        # Query graph for practiced knowledge units
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
            "study_time_minutes": getattr(event, "duration_minutes", None),  # Safe access
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

    # ========================================================================
    # DUAL-TRACK ASSESSMENT (ADR-030)
    # ========================================================================

    async def assess_engagement_dual_track(
        self,
        user_uid: str,
        user_engagement_level: EngagementLevel,
        user_evidence: str,
        user_reflection: str | None = None,
        period_days: int = 30,
    ) -> Result[DualTrackResult[EngagementLevel]]:
        """
        Dual-track engagement assessment for events.

        Compares user's self-assessed engagement level with system-measured
        metrics (attendance, completion, participation).

        Args:
            user_uid: User making the assessment
            user_engagement_level: User's self-reported engagement level
            user_evidence: User's evidence for their assessment
            user_reflection: Optional reflection on engagement
            period_days: Period to analyze (default 30 days)

        Returns:
            Result[DualTrackResult[EngagementLevel]] with gap analysis
        """
        return await self._dual_track_assessment(
            uid=user_uid,  # Using user_uid as entity for user-level assessment
            user_uid=user_uid,
            user_level=user_engagement_level,
            user_evidence=user_evidence,
            user_reflection=user_reflection,
            system_calculator=self._make_system_engagement_calculator(period_days),
            level_scorer=self._engagement_level_to_score,
            entity_type="user_events",
            insight_generator=self._generate_event_gap_insights,
            recommendation_generator=self._generate_event_gap_recommendations,
        )

    def _make_system_engagement_calculator(self, period_days: int) -> Any:
        """Create a system calculator for dual-track engagement assessment."""

        async def _calculate(_entity: Any, u_uid: str) -> tuple[EngagementLevel, float, list[str]]:
            return await self._calculate_system_engagement_for_dual_track(u_uid, period_days)

        return _calculate

    async def _calculate_system_engagement_for_dual_track(
        self, user_uid: str, period_days: int = 30
    ) -> tuple[EngagementLevel, float, list[str]]:
        """
        Calculate system-measured engagement level from event data.

        Metrics considered:
        - Attendance rate (completed vs scheduled)
        - Active participation (events with habit reinforcement)
        - Goal support (events linked to goals)
        - Recency (recent event activity)

        Returns:
            Tuple of (EngagementLevel, score 0.0-1.0, evidence list)
        """
        from datetime import date, timedelta

        evidence: list[str] = []

        # Get events for period
        start_date = date.today() - timedelta(days=period_days)
        events_result = await self.backend.find_by(user_uid=user_uid)

        if events_result.is_error or not events_result.value:
            evidence.append("No events found in analysis period")
            return EngagementLevel.ABSENT, 0.0, evidence

        all_events = events_result.value
        # Filter to period
        period_events = [e for e in all_events if e.event_date and e.event_date >= start_date]

        if not period_events:
            evidence.append(f"No events scheduled in last {period_days} days")
            return EngagementLevel.ABSENT, 0.1, evidence

        total_events = len(period_events)
        evidence.append(f"{total_events} events in period")

        # Calculate attendance rate
        completed = [e for e in period_events if e.is_completed]
        attendance_rate = len(completed) / total_events if total_events > 0 else 0.0
        evidence.append(f"Attendance rate: {attendance_rate:.0%}")

        # Calculate active participation (events with habit reinforcement)
        with_habit = [e for e in period_events if e.reinforces_habit_uid]
        habit_rate = len(with_habit) / total_events if total_events > 0 else 0.0
        if habit_rate > 0:
            evidence.append(f"{len(with_habit)} events reinforce habits")

        # Calculate goal support via relationships
        goal_support_count = 0
        if self.relationships:
            for event in period_events[:10]:  # Sample first 10 for efficiency
                context_result = await self.relationships.get_cross_domain_context(event.uid)
                if context_result.is_ok:
                    goals = context_result.value.get("goals", [])
                    if goals:
                        goal_support_count += 1

        goal_rate = goal_support_count / min(total_events, 10) if total_events > 0 else 0.0
        if goal_support_count > 0:
            evidence.append(f"{goal_support_count} events support goals")

        # Calculate recency (activity in last 7 days)
        recent_date = date.today() - timedelta(days=7)
        recent_events = [e for e in period_events if e.event_date and e.event_date >= recent_date]
        recency_score = min(1.0, len(recent_events) / 3.0)  # 3+ recent events = full score
        if recent_events:
            evidence.append(f"{len(recent_events)} events in last 7 days")

        # Weighted composite score
        # Attendance: 40%, Goal support: 25%, Habit reinforcement: 20%, Recency: 15%
        composite_score = (
            attendance_rate * 0.40 + goal_rate * 0.25 + habit_rate * 0.20 + recency_score * 0.15
        )

        # Map to EngagementLevel
        system_level = EngagementLevel.from_score(composite_score)

        return system_level, composite_score, evidence

    @staticmethod
    def _engagement_level_to_score(level: EngagementLevel) -> float:
        """Convert EngagementLevel to numeric score."""
        return level.to_score()

    @staticmethod
    def _generate_event_gap_insights(direction: str, gap: float, entity_name: str) -> list[str]:
        """Generate event-specific insights based on perception gap."""
        insights: list[str] = []

        if direction == "aligned":
            insights.append(
                "Your engagement self-perception matches your event participation patterns."
            )
            insights.append("This self-awareness helps maintain consistent engagement.")
        elif direction == "user_higher":
            insights.append(f"Self-assessment exceeds measured engagement (gap: {gap:.0%}).")
            insights.append("Consider tracking event outcomes more carefully.")
            if gap > 0.25:
                insights.append("Review which events you're actually attending vs planning.")
        else:  # system_higher
            insights.append(
                f"Your event engagement is stronger than you perceive (gap: {gap:.0%})."
            )
            insights.append("You may be undervaluing your participation and commitment.")
            if gap > 0.25:
                insights.append("Celebrate your consistent event attendance!")

        return insights

    @staticmethod
    def _generate_event_gap_recommendations(
        direction: str, _gap: float, _entity: Any, evidence: list[str]
    ) -> list[str]:
        """Generate event-specific recommendations to close the gap."""
        recommendations: list[str] = []

        if direction == "user_higher":
            recommendations.append("Link more events to goals for meaningful engagement.")
            recommendations.append("Add habit reinforcement to regular events.")
            recommendations.append("Review and complete scheduled events consistently.")
            if any("attendance" in e.lower() for e in evidence):
                recommendations.append("Focus on showing up for planned events.")
        elif direction == "system_higher":
            recommendations.append("Acknowledge your strong event participation.")
            recommendations.append("Build on this momentum by taking on more impactful events.")
        else:  # aligned
            recommendations.append("Maintain current engagement practices.")
            recommendations.append("Consider stretching into higher-impact events.")

        return recommendations
