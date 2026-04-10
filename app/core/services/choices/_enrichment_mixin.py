"""
Enrichment Mixin — ChoicesService
===================================

Analytics delegates and enriched data views for choice entities.

Part of choices_service.py decomposition (April 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.utils.result_simplified import Result
from core.utils.type_converters import get_enum_attr_str

if TYPE_CHECKING:
    from core.models.type_hints import UserUID
    from core.services.choices_service import ChoicesAnalyticsContext


class _EnrichmentMixin:
    """
    Analytics delegates and enriched data views for ChoicesService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by ChoicesService.__init__
    core: Any
    intelligence: Any

    # ========================================================================
    # ANALYTICS - Delegates to ChoicesIntelligenceService
    # ========================================================================

    async def analyze_decision_patterns(
        self, user_uid: UserUID, lookback_days: int = 90
    ) -> Result[dict[str, Any]]:
        """
        Analyze user's decision-making patterns across domains.

        Returns comprehensive analysis including:
        - Decision style distribution
        - Average time pressure and energy levels
        - Goal alignment metrics
        - Habit reinforcement patterns
        - Principle integrity metrics
        - Quality correlations (pressure vs satisfaction, energy vs confidence)
        - Auto-generated recommendations

        Args:
            user_uid: UID of the user
            lookback_days: Days to look back (default 90)

        Returns:
            Result containing decision pattern analysis
        """
        return await self.intelligence.get_decision_patterns(user_uid, days=lookback_days)

    # ========================================================================
    # ENRICHED DATA VIEWS
    # ========================================================================

    async def get_analytics_context(self, user_uid: UserUID) -> Result[ChoicesAnalyticsContext]:
        """Build pre-computed analytics context for the choices analytics view.

        Returns dict with: total_choices, total_decisions, satisfaction_rate,
        on_time_rate, outcomes.
        """
        all_result = await self.core.get_for_user_filtered(user_uid, "all")
        if all_result.is_error:
            return Result.fail(all_result)

        choices = all_result.value

        total = len(choices)
        decided_statuses = ["decided", "implemented", "evaluated"]
        decided = sum(1 for c in choices if get_enum_attr_str(c, "status") in decided_statuses)

        # Satisfaction rate from choices with satisfaction_score (1-5 scale)
        choices_with_satisfaction = [
            c for c in choices if getattr(c, "satisfaction_score", None) is not None
        ]
        if choices_with_satisfaction:
            satisfied_count = sum(
                1 for c in choices_with_satisfaction if getattr(c, "satisfaction_score", 0) >= 4
            )
            satisfaction_rate = satisfied_count / len(choices_with_satisfaction)
        else:
            satisfaction_rate = 0.0

        # On-time rate from choices with deadline and decided_at
        choices_with_deadline = [
            c
            for c in choices
            if getattr(c, "decision_deadline", None) is not None
            and getattr(c, "decided_at", None) is not None
        ]
        if choices_with_deadline:
            on_time_count = sum(
                1 for c in choices_with_deadline if c.decided_at <= c.decision_deadline
            )
            on_time_rate = on_time_count / len(choices_with_deadline)
        else:
            on_time_rate = 0.0

        # Outcomes from evaluated choices
        outcomes = [
            {
                "title": getattr(c, "title", "Choice"),
                "outcome": getattr(c, "actual_outcome", ""),
                "satisfaction": getattr(c, "satisfaction_score", None),
                "lessons": getattr(c, "lessons_learned", ()),
            }
            for c in choices
            if getattr(c, "actual_outcome", None) is not None
        ]

        return Result.ok(
            {
                "total_choices": total,
                "total_decisions": decided,
                "satisfaction_rate": satisfaction_rate,
                "on_time_rate": on_time_rate,
                "outcomes": outcomes,
            }
        )
