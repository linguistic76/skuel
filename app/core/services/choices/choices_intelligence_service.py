"""
Choices Intelligence Service - Pure Cypher Graph Analytics
======================================================

Handles Pure Cypher graph intelligence queries for choices.

Architecture: Shell delegates to 3 focused mixins in the same directory:
  _core_intelligence_mixin.py  — get_decision_intelligence,
                                  analyze_choice_impact
  _analytics_mixin.py          — get_quick_decision_metrics, batch_analyze_decision_complexity,
                                  get_decision_patterns, get_choice_quality_correlations,
                                  get_domain_decision_patterns
  _behavioral_signals_mixin.py — dual-track, principle analysis (via CrossDomainQueryService),
                                  get_zpd_behavioral_signals()
                                  (event handlers migrated to ChoiceEventHandlerService, March 2026)

See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.constants import ConfidenceLevel, QueryLimit
from core.models.choice.choice import Choice
from core.models.type_hints import UserUID
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.choices._analytics_mixin import _AnalyticsMixin
from core.services.choices._behavioral_signals_mixin import _BehavioralSignalsMixin
from core.services.choices._core_intelligence_mixin import _CoreIntelligenceMixin
from core.services.knowledge.knowledge_pattern_analyzer import KnowledgePatternAnalyzer
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.ports.domain_protocols import ChoicesOperations
    from core.services.cross_domain import CrossDomainQueryService
    from core.services.insight.insight_store import InsightStore
    from core.services.relationships import UnifiedRelationshipService


class ChoicesIntelligenceService(
    _CoreIntelligenceMixin,
    _AnalyticsMixin,
    _BehavioralSignalsMixin,
    BaseAnalyticsService["ChoicesOperations", Choice],
):
    """
    Pure Cypher graph intelligence queries for choices.

    NOTE: This service extends BaseAnalyticsService (ADR-030) and has NO AI dependencies.
    It uses pure graph queries and Python calculations - no LLM or embeddings.

    Responsibilities:
    - Get choice with graph context
    - Analyze choice impact across domains
    - Provide decision intelligence
    - Track decision patterns over time
    """

    # Service name for hierarchical logging
    _service_name = "choices.intelligence"

    # Relationships are REQUIRED for this service — principle and goal alignment,
    # decision complexity and learning patterns are all graph reads, and without the
    # relationship service each returns an empty result indistinguishable from a real
    # zero. Failing at construction keeps that a wiring bug rather than a silent 0%
    # (or a 500 on the live /api/choices learning-patterns route). Matches habits and
    # goals intelligence, which already declare it.
    _require_relationships = True

    def __init__(
        self,
        backend: ChoicesOperations,
        cross_domain_query: CrossDomainQueryService,
        graph_intel=None,
        relationship_service: UnifiedRelationshipService[Any, Any, Any] | None = None,
        insight_store: InsightStore | None = None,
    ) -> None:
        """
        Initialize choices intelligence service.

        Args:
            backend: Protocol-based backend for choice operations (Choice model)
            cross_domain_query: CrossDomainQueryService for cross-domain reads (REQUIRED)
            graph_intel: GraphIntelligenceService for pure Cypher analytics,
            relationship_service: UnifiedRelationshipService for specialized relationship queries
            insight_store: InsightStore for persisting event-driven insights (optional)
        """
        super().__init__(
            backend=backend,
            graph_intel=graph_intel,
            relationship_service=relationship_service,
            insight_store=insight_store,
        )
        self.cross_domain_query = cross_domain_query
        self._knowledge_analyzer = KnowledgePatternAnalyzer()

    # ========================================================================
    # INTELLIGENCEOPERATIONS PROTOCOL METHODS (January 2026)
    # These methods implement the IntelligenceOperations protocol for use
    # with IntelligenceRouteFactory.
    #
    # get_with_context is provided by _CoreIntelligenceMixin (mechanism B,
    # registry-sourced via self.relationships) — NOT redefined here. A local
    # override that delegated back to get_choice_with_context recursed infinitely
    # (get_with_context → get_choice_with_context → get_with_context); the mixin
    # now owns the real implementation. (Convergence Phase 1, 2C.)
    # ========================================================================

    async def get_performance_analytics(
        self, user_uid: UserUID, _period_days: int = 30
    ) -> Result[dict[str, Any]]:
        """
        Get choice/decision analytics for a user.

        Protocol method: Aggregates decision metrics over time period.
        Used by IntelligenceRouteFactory for GET /api/choices/analytics route.

        Args:
            user_uid: User UID
            _period_days: Placeholder - not yet implemented. Will filter by period when added.

        Returns:
            Result containing analytics data dict

        Note: _period_days uses underscore prefix per CLAUDE.md convention to indicate
        "API contract defined, implementation deferred". Currently calculates analytics
        over ALL choices. Future enhancement: filter by created_at within period.
        """
        # Get all choices for user
        choices_result = await self.backend.find_by(user_uid=user_uid)
        if choices_result.is_error:
            return Result.fail(choices_result)

        all_items = choices_result.value or []
        choices = [c for c in all_items if isinstance(c, Choice)]

        # Calculate analytics
        total_choices = len(choices)
        decided_choices = [c for c in choices if c.selected_option_uid is not None]
        pending_choices = [c for c in choices if c.selected_option_uid is None]

        # Calculate decision rate
        decision_rate = len(decided_choices) / total_choices if total_choices > 0 else 0.0

        return Result.ok(
            {
                "user_uid": user_uid,
                "period_days": _period_days,
                "total_choices": total_choices,
                "decided_choices": len(decided_choices),
                "pending_choices": len(pending_choices),
                "decision_rate": round(decision_rate, 2),
                "analytics": {
                    "total": total_choices,
                    "decided": len(decided_choices),
                    "pending": len(pending_choices),
                    "decision_rate_percentage": round(decision_rate * 100, 1),
                },
            }
        )

    async def get_domain_insights(
        self, uid: str, min_confidence: float = ConfidenceLevel.MEDIUM
    ) -> Result[dict[str, Any]]:
        """
        Get domain-specific insights for a choice.

        Protocol method: Maps to analyze_choice_impact.
        Used by IntelligenceRouteFactory for GET /api/choices/insights route.

        Args:
            uid: Choice UID
            min_confidence: Minimum confidence threshold (default: ConfidenceLevel.MEDIUM)

        Returns:
            Result containing insights data dict (ChoiceImpactAnalysis)
        """
        result = await self.analyze_choice_impact(uid, depth=2, min_confidence=min_confidence)
        # analyze_choice_impact returns ChoiceImpactAnalysis, convert to dict
        if result.is_ok and result.value:
            return Result.ok(result.value.to_dict())
        return result

    async def analyze_learning_patterns(
        self, user_uid: UserUID, timeframe_days: int = 30
    ) -> Result[list[Any]]:
        """Detect knowledge-learning patterns across the user's choice activities."""
        entities_result = await self.backend.find_by(user_uid=user_uid, limit=QueryLimit.MAXIMUM)
        if entities_result.is_error:
            return Result.fail(entities_result)

        return await self._knowledge_analyzer.analyze_learning_patterns(
            entities_result.value, self._fetch_choice_relationships, timeframe_days
        )
