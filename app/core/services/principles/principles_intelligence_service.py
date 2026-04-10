"""
Principles Intelligence Service - Pure Cypher Graph Analytics
=========================================================

Handles Pure Cypher graph intelligence queries for principles.

Architecture: Shell delegates to 3 focused mixins in the same directory:
  _core_intelligence_mixin.py       — get_with_context, get_performance_analytics,
                                      get_domain_insights, get_principle_with_context
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

from core.models.enums import Domain
from core.models.principle.principle import Principle
from core.models.principle.principle_dto import PrincipleDTO
from core.ports.domain_protocols import PrinciplesOperations
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.intelligence import GraphContextOrchestrator
from core.services.principles._alignment_intelligence_mixin import _AlignmentIntelligenceMixin
from core.services.principles._core_intelligence_mixin import _CoreIntelligenceMixin
from core.services.principles._influence_mixin import _InfluenceMixin
from core.utils.logging import get_logger

if TYPE_CHECKING:
    from core.ports.domain_protocols import PrinciplesRelationshipOperations

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
    PrincipleEventHandlerService — see principles_event_handler_service.py.

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
        graph_intelligence_service=None,
        relationship_service: PrinciplesRelationshipOperations | None = None,
        insight_store: Any | None = None,
    ) -> None:
        """
        Initialize principles intelligence service.

        Args:
            backend: Backend for principle operations
            graph_intelligence_service: GraphIntelligenceService for pure Cypher analytics
            relationship_service: PrinciplesRelationshipOperations protocol for specialized relationship queries
            insight_store: For persisting event-driven insights (optional)
        """
        super().__init__(
            backend=backend,
            graph_intelligence_service=graph_intelligence_service,
            relationship_service=relationship_service,
            insight_store=insight_store,
        )

        # Initialize GraphContextOrchestrator for get_with_context pattern
        if graph_intelligence_service:
            self.orchestrator = GraphContextOrchestrator[Principle, PrincipleDTO](
                service=self,
                backend_get_method="get",  # PrinciplesService uses generic 'get'
                dto_class=PrincipleDTO,
                model_class=Principle,
                domain=Domain.PRINCIPLES,
            )

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Principle entities."""
        return "Principle"
