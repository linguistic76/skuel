"""
Principles Intelligence Service - Pure Cypher Graph Analytics
=========================================================

Handles Pure Cypher graph intelligence queries for principles.

Architecture: Shell delegates to 3 focused mixins in the same directory:
  _core_intelligence_mixin.py       — get_with_context, get_performance_analytics,
                                      get_domain_insights
  _alignment_intelligence_mixin.py  — assess_principle_alignment, assess_alignment_dual_track,
                                      get_principle_adherence_trends, helpers
  _influence_mixin.py               — get_principle_conflict_analysis, get_quick_principle_impact,
                                      batch_analyze_principle_adoption,
                                      get_choice_guidance_effectiveness

Part of the PrinciplesService decomposition.
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.constants import QueryLimit
from core.models.principle.principle import Principle
from core.models.type_hints import UserUID
from core.ports.domain_protocols import PrinciplesOperations
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.knowledge.knowledge_pattern_analyzer import KnowledgePatternAnalyzer
from core.services.principles._alignment_intelligence_mixin import _AlignmentIntelligenceMixin
from core.services.principles._core_intelligence_mixin import _CoreIntelligenceMixin
from core.services.principles._influence_mixin import _InfluenceMixin
from core.services.principles.principle_relationships import PrincipleRelationships
from core.utils.logging import get_logger
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.services.relationships import UnifiedRelationshipService

logger = get_logger(__name__)


class PrinciplesIntelligenceService(
    _CoreIntelligenceMixin,
    _AlignmentIntelligenceMixin,
    _InfluenceMixin,
    BaseAnalyticsService[PrinciplesOperations, Principle],
):
    """
    Pure Cypher graph intelligence for principles.

    NOTE: This service extends BaseAnalyticsService (ADR-030) and has NO AI dependencies.
    It uses pure graph queries and Python calculations - no LLM or embeddings.

    Event-driven handlers (strength changes, reflections, conflicts) are in
    PrincipleEventHandlerService — see principle_event_handler_service.py.

    Responsibilities:
    - Get principle with graph context
    - Assess principle alignment (single + dual-track)
    - Analyze adherence trends
    - Detect principle conflicts
    - Quick impact metrics and batch adoption analysis
    - Choice guidance effectiveness
    """

    # Service name for hierarchical logging
    _service_name = "principles.intelligence"

    def __init__(
        self,
        backend: PrinciplesOperations,
        graph_intel=None,
        relationship_service: UnifiedRelationshipService[Any, Any, Any] | None = None,
        insight_store: Any | None = None,
    ) -> None:
        """
        Initialize principles intelligence service.

        Args:
            backend: Backend for principle operations
            graph_intel: GraphIntelligenceService for pure Cypher analytics
            relationship_service: UnifiedRelationshipService for specialized relationship queries
            insight_store: For persisting event-driven insights (optional)
        """
        super().__init__(
            backend=backend,
            graph_intel=graph_intel,
            relationship_service=relationship_service,
            insight_store=insight_store,
        )
        self._knowledge_analyzer = KnowledgePatternAnalyzer(graph_intel=self.graph_intel)

    async def analyze_learning_patterns(
        self, user_uid: UserUID, timeframe_days: int = 30
    ) -> Result[list[Any]]:
        """Detect knowledge-learning patterns across the user's principle activities."""
        entities_result = await self.backend.find_by(user_uid=user_uid, limit=QueryLimit.MAXIMUM)
        if entities_result.is_error:
            return Result.fail(entities_result)

        service = self.relationships

        async def _fetch_principle_rels(uid: str) -> PrincipleRelationships:
            if service:
                return await PrincipleRelationships.fetch(uid, service)
            return PrincipleRelationships.empty()

        return await self._knowledge_analyzer.analyze_learning_patterns(
            entities_result.value, _fetch_principle_rels, timeframe_days
        )
