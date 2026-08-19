"""
Core Intelligence Mixin — ChoicesIntelligenceService
=====================================================

Graph-context methods: get_with_context, get_decision_intelligence,
analyze_choice_impact.

Graph context retrieval (mechanism B, registry-sourced) is inherited from the
shared ``_CoreIntelligenceMixin``: ``self.relationships.get_with_context`` sources
its edge vocabulary from ``CHOICES_CONFIG.cross_domain_relationship_types`` (the
registry single source of truth). This mixin adds decision intelligence.

``get_decision_intelligence`` and ``analyze_choice_impact`` are thin lenses over
the CANONICAL typed reader: ``BaseAnalyticsService._analyze_entity_with_typed_context``
fetches the entity + ``get_cross_domain_context_typed`` (the path-aware
``ChoiceCrossContext``), runs a domain ``metrics_fn``/``recommendations_fn`` from
``metrics_calculators``, and returns the ``{entity, metrics, recommendations,
context}`` envelope; each lens transcribes that envelope into its frozen result
type. The select/rename/union/dedup of buckets lives in
``ChoiceCrossContext.from_categorized`` (the per-domain factory seam).

Part of choices_intelligence_service.py decomposition (March 2026).
Converged onto mechanism B in Convergence Phase 1 (2C); the per-domain override
was collapsed into the shared base in the curriculum-convergence teardown.
Folded onto the typed reader in the get_cross_domain_context_typed first-mover slice.
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md,
     /docs/roadmap/intent-traversal-registry-convergence.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.constants import ConfidenceLevel
from core.services.intelligence._core_intelligence_mixin import (
    _CoreIntelligenceMixin as _SharedCoreMixin,
)
from core.utils.decorators import requires_graph_intelligence
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from core.services.choices.choices_types import (
        ChoiceImpactAnalysis,
        DecisionIntelligence,
    )
    from core.services.relationships import UnifiedRelationshipService


class _CoreIntelligenceMixin(_SharedCoreMixin):
    """
    Core + decision intelligence for ChoicesIntelligenceService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by ChoicesIntelligenceService.__init__ (stores relationship_service).
    # Stays optional to match BaseAnalyticsService's own `relationship_service: Any | None`
    # parameter; the runtime guarantee is _require_relationships = True on the service,
    # which refuses the construction. Sites that need the narrowing assert on it.
    relationships: UnifiedRelationshipService[Any, Any, Any] | None
    # Provided by BaseAnalyticsService via multiple inheritance on the composed service.
    _analyze_entity_with_typed_context: Any

    @requires_graph_intelligence("get_decision_intelligence")
    async def get_decision_intelligence(
        self, choice_uid: str, min_confidence: float = ConfidenceLevel.MEDIUM, depth: int = 2
    ) -> Result[DecisionIntelligence]:
        """Decision-readiness lens: is this choice ready to decide, and how complex?

        Surfaces decision context (goals/principles/knowledge), cross-domain impact,
        a complexity/stakes assessment, and what to consult. A thin lens over the
        typed reader — the heavy lifting is ``calculate_decision_metrics`` +
        ``decision_improvement_opportunities`` (see ``metrics_calculators``).

        Returns:
            Result[DecisionIntelligence]
        """
        from core.services.choices.choices_types import (
            CascadeImpact,
            ChoiceGraphContext,
            DecisionAnalysis,
            DecisionContext,
            DecisionImpact,
            DecisionIntelligence,
            DecisionRecommendations,
            PathAwareContext,
        )
        from core.services.intelligence.metrics_calculators import (
            calculate_decision_metrics,
            decision_improvement_opportunities,
        )

        result = await self._analyze_entity_with_typed_context(
            choice_uid,
            metrics_fn=calculate_decision_metrics,
            recommendations_fn=decision_improvement_opportunities,
            depth=depth,
            min_confidence=min_confidence,
        )
        if result.is_error:
            return Result.fail(result)

        envelope = result.value
        choice = envelope["entity"]
        metrics = envelope["metrics"]
        improvement_opportunities = envelope["recommendations"]
        cascade = metrics["cascade_impact"]
        pac = metrics["path_aware_context"]

        intelligence = DecisionIntelligence(
            choice=choice,
            context=DecisionContext(
                goals=metrics["context"]["goals"],
                principles=metrics["context"]["principles"],
                knowledge=metrics["context"]["knowledge"],
            ),
            impact=DecisionImpact(
                tasks=metrics["impact"]["tasks"],
                goals=metrics["impact"]["goals"],
                habits=metrics["impact"]["habits"],
            ),
            decision_analysis=DecisionAnalysis(
                complexity=metrics["decision_analysis"]["complexity"],
                confidence_needed=metrics["decision_analysis"]["confidence_needed"],
                stake_level=metrics["decision_analysis"]["stake_level"],
            ),
            recommendations=DecisionRecommendations(
                gather_more_info=metrics["gather_more_info"],
                consult_principles=metrics["consult_principles"],
                consider_impact_on=metrics["consider_impact_on"],
                improvement_opportunities=improvement_opportunities,
            ),
            graph_context=ChoiceGraphContext(
                cascade_impact=CascadeImpact(
                    total_impact=cascade.get("total_impact", 0.0),
                    direct_impact=cascade.get("direct_impact", 0.0),
                    indirect_impact=cascade.get("indirect_impact", 0.0),
                    domain_impacts=cascade.get("domain_impacts", {}),
                ),
                path_aware_context=PathAwareContext(
                    total_strong_connections=pac["total_strong_connections"],
                    direct_connections_count=pac["direct_connections_count"],
                    max_path_depth=pac["max_path_depth"],
                    avg_path_strength=pac["avg_path_strength"],
                ),
            ),
        )
        return Result.ok(intelligence)

    @requires_graph_intelligence("analyze_choice_impact")
    async def analyze_choice_impact(
        self, choice_uid: str, depth: int = 2, min_confidence: float = ConfidenceLevel.MEDIUM
    ) -> Result[ChoiceImpactAnalysis]:
        """Impact-risk lens: what does this choice affect, how severe, how risky?

        Surfaces the cross-domain blast radius, per-domain severity, a risk
        assessment, and opportunities. A thin lens over the typed reader — the
        heavy lifting is ``calculate_choice_impact_metrics`` +
        ``choice_impact_recommendations`` (see ``metrics_calculators``).

        Returns:
            Result[ChoiceImpactAnalysis]
        """
        from core.services.choices.choices_types import (
            CascadeImpact,
            ChoiceGraphContext,
            ChoiceImpactAnalysis,
            DomainImpactBreakdown,
            DomainImpactDetail,
            ImpactSummary,
            PathAwareContext,
            RiskAssessment,
        )
        from core.services.intelligence.metrics_calculators import (
            calculate_choice_impact_metrics,
            choice_impact_recommendations,
        )

        result = await self._analyze_entity_with_typed_context(
            choice_uid,
            metrics_fn=calculate_choice_impact_metrics,
            recommendations_fn=choice_impact_recommendations,
            depth=depth,
            min_confidence=min_confidence,
        )
        if result.is_error:
            return Result.fail(result)

        envelope = result.value
        choice = envelope["entity"]
        metrics = envelope["metrics"]
        opportunities = envelope["recommendations"]
        di = metrics["domain_impact"]
        cascade = metrics["cascade_impact"]
        pac = metrics["path_aware_context"]

        def _detail(d: dict[str, Any]) -> DomainImpactDetail:
            return DomainImpactDetail(
                affected=d["affected"], count=d["count"], severity=d["severity"]
            )

        impact_analysis = ChoiceImpactAnalysis(
            choice=choice,
            impact_summary=ImpactSummary(
                total_entities_affected=metrics["impact_summary"]["total_entities_affected"],
                domains_affected=metrics["impact_summary"]["domains_affected"],
                impact_score=metrics["impact_summary"]["impact_score"],
            ),
            domain_impact=DomainImpactBreakdown(
                goals=_detail(di["goals"]),
                tasks=_detail(di["tasks"]),
                habits=_detail(di["habits"]),
                principles=_detail(di["principles"]),
            ),
            risk_assessment=RiskAssessment(
                risk_level=metrics["risk_assessment"]["risk_level"],
                risk_factors=metrics["risk_assessment"]["risk_factors"],
                mitigation_suggestions=metrics["risk_assessment"]["mitigation_suggestions"],
            ),
            opportunities=opportunities,
            graph_context=ChoiceGraphContext(
                cascade_impact=CascadeImpact(
                    total_impact=cascade.get("total_impact", 0.0),
                    direct_impact=cascade.get("direct_impact", 0.0),
                    indirect_impact=cascade.get("indirect_impact", 0.0),
                    domain_impacts=cascade.get("domain_impacts", {}),
                ),
                path_aware_context=PathAwareContext(
                    total_strong_connections=pac["total_strong_connections"],
                    direct_connections_count=pac["direct_connections_count"],
                    max_path_depth=pac["max_path_depth"],
                    avg_path_strength=pac["avg_path_strength"],
                ),
            ),
        )
        return Result.ok(impact_analysis)
