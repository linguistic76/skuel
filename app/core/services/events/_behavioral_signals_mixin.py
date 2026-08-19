"""
Behavioral Signals Mixin — EventsIntelligenceService
=====================================================

Dual-track engagement assessment and behavioral pattern analysis.

Part of events_intelligence_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.constants import QueryLimit
from core.models.enums.activity_enums import EngagementLevel
from core.models.shared.dual_track import DualTrackResult
from core.models.type_hints import UserUID
from core.services.events._habit_links import enrich_events_with_habit_links
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from core.ports.domain_protocols import EventsOperations


class _BehavioralSignalsMixin:
    """
    Dual-track engagement assessment for EventsIntelligenceService.

    Compares user self-assessment against system-measured behavioral signals
    (attendance rate, goal support, habit reinforcement, recency).

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by EventsIntelligenceService.__init__
    backend: "EventsOperations"
    relationships: Any
    logger: Any
    _dual_track_assessment: Any  # provided by BaseAnalyticsService

    async def assess_engagement_dual_track(
        self,
        user_uid: UserUID,
        user_engagement_level: EngagementLevel,
        user_evidence: str,
        user_reflection: str | None = None,
        period_days: int = 30,
        store_callback: Callable[[str, DualTrackResult[EngagementLevel]], Awaitable[None]]
        | None = None,
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
            store_callback: Optional persistence callback (uid, result) -> None. The
                user-level check-in lives on the :User node, so the caller binds
                ``UserService.append_dual_track_checkin`` with the dimension — the
                Events intelligence backend can't write the User node itself.

        Returns:
            Result[DualTrackResult[EngagementLevel]] with gap analysis
        """
        return await self._dual_track_assessment(
            uid=user_uid,
            user_uid=user_uid,
            user_level=user_engagement_level,
            user_evidence=user_evidence,
            user_reflection=user_reflection,
            system_calculator=self._make_system_engagement_calculator(period_days),
            level_scorer=self._engagement_level_to_score,
            entity_type="user_events",
            require_entity=False,  # user-level: uid=user_uid, no :Entity row to fetch
            insight_generator=self._generate_event_gap_insights,
            recommendation_generator=self._generate_event_gap_recommendations,
            store_callback=store_callback,
        )

    def _make_system_engagement_calculator(self, period_days: int) -> Any:
        """Create a system calculator for dual-track engagement assessment."""

        async def _calculate(_entity: Any, u_uid: str) -> tuple[EngagementLevel, float, list[str]]:
            return await self._calculate_system_engagement_for_dual_track(
                UserUID(u_uid), period_days
            )

        return _calculate

    async def _calculate_system_engagement_for_dual_track(
        self, user_uid: UserUID, period_days: int = 30
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

        start_date = date.today() - timedelta(days=period_days)
        # Fetch the full set — find_by defaults to limit=100, so the in-memory window
        # filter below would otherwise sample an arbitrary page for prolific users.
        events_result = await self.backend.find_by(user_uid=user_uid, limit=QueryLimit.MAXIMUM)

        if events_result.is_error or not events_result.value:
            evidence.append("No events found in analysis period")
            return EngagementLevel.ABSENT, 0.0, evidence

        all_events = events_result.value
        if len(all_events) >= QueryLimit.MAXIMUM:
            self.logger.warning(
                "Engagement assessment for %s capped at %d events — score may be truncated",
                user_uid,
                QueryLimit.MAXIMUM,
            )
        period_events = [e for e in all_events if e.event_date and e.event_date >= start_date]
        # Populate the derived reinforces_habit_uid from the REINFORCES_HABIT edge.
        period_events = await enrich_events_with_habit_links(self.backend, period_events)

        if not period_events:
            evidence.append(f"No events scheduled in last {period_days} days")
            return EngagementLevel.ABSENT, 0.1, evidence

        total_events = len(period_events)
        evidence.append(f"{total_events} events in period")

        completed = [e for e in period_events if e.is_completed]
        attendance_rate = len(completed) / total_events if total_events > 0 else 0.0
        evidence.append(f"Attendance rate: {attendance_rate:.0%}")

        with_habit = [e for e in period_events if e.reinforces_habit_uid]
        habit_rate = len(with_habit) / total_events if total_events > 0 else 0.0
        if habit_rate > 0:
            evidence.append(f"{len(with_habit)} events reinforce habits")

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

        recent_date = date.today() - timedelta(days=7)
        recent_events = [e for e in period_events if e.event_date and e.event_date >= recent_date]
        recency_score = min(1.0, len(recent_events) / 3.0)
        if recent_events:
            evidence.append(f"{len(recent_events)} events in last 7 days")

        # Weighted composite score
        # Attendance: 40%, Goal support: 25%, Habit reinforcement: 20%, Recency: 15%
        composite_score = (
            attendance_rate * 0.40 + goal_rate * 0.25 + habit_rate * 0.20 + recency_score * 0.15
        )

        system_level = EngagementLevel.from_score(composite_score)

        return system_level, composite_score, evidence

    @staticmethod
    def _engagement_level_to_score(level: EngagementLevel) -> float:
        """Convert EngagementLevel to numeric score."""
        return level.to_score()

    @staticmethod
    def _generate_event_gap_insights(direction: str, gap: float, _entity_name: str) -> list[str]:
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
