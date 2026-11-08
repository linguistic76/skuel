"""ChoiceImpactAnalysis and DecisionIntelligence answer as JSON through the route boundary.

``ChoicesIntelligenceService.get_domain_insights`` (GET /api/choices/insights) answers with
``ChoiceImpactAnalysis.to_dict()``, and ``jsonable_content`` serializes it, as it does
every ``Result`` route's value. These tests build a fully populated result tree (a real
Choice carrying an embedding, path-aware entities with date fields) and read what the
route would send: JSON that encodes, ISO dates, and a choice without its embedding fields.
"""

from __future__ import annotations

import json
from datetime import date

from adapters.inbound.boundary import jsonable_content
from core.models.choice.choice import Choice
from core.models.graph.path_aware_types import (
    PathAwareGoal,
    PathAwareKnowledge,
    PathAwarePrinciple,
)
from core.services.choices.choices_types import (
    CascadeImpact,
    ChoiceGraphContext,
    ChoiceImpactAnalysis,
    DecisionAnalysis,
    DecisionContext,
    DecisionImpact,
    DecisionIntelligence,
    DecisionRecommendations,
    DomainImpactBreakdown,
    DomainImpactDetail,
    ImpactSummary,
    PathAwareContext,
    RiskAssessment,
)

_EMBEDDING_KEYS = frozenset({"embedding", "embedding_model", "embedding_updated_at"})


def _embedded_choice() -> Choice:
    return Choice(
        uid="c1",
        title="Decide",
        user_uid="u1",
        embedding=tuple([0.25] * 1024),
        embedding_model="text-embedding-3-small",
    )


def _graph_context() -> ChoiceGraphContext:
    return ChoiceGraphContext(
        cascade_impact=CascadeImpact(
            total_impact=5.0, direct_impact=4.0, indirect_impact=1.0, domain_impacts={"goals": 4.0}
        ),
        path_aware_context=PathAwareContext(
            total_strong_connections=2,
            direct_connections_count=2,
            max_path_depth=1,
            avg_path_strength=0.85,
        ),
    )


def _goal() -> PathAwareGoal:
    # target_date exercises the date -> isoformat path in the serializer.
    return PathAwareGoal(
        uid="g1",
        title="Goal",
        distance=1,
        path_strength=0.9,
        via_relationships=["AFFECTS_GOAL"],
        target_date=date(2026, 1, 1),
    )


def test_choice_impact_analysis_to_dict_is_json_serializable() -> None:
    analysis = ChoiceImpactAnalysis(
        choice=_embedded_choice(),
        impact_summary=ImpactSummary(
            total_entities_affected=3, domains_affected=["goals", "principles"], impact_score=8.0
        ),
        domain_impact=DomainImpactBreakdown(
            goals=DomainImpactDetail(affected=[_goal()], count=1, severity="low"),
            tasks=DomainImpactDetail(affected=[], count=0, severity="none"),
            habits=DomainImpactDetail(affected=[], count=0, severity="none"),
            principles=DomainImpactDetail(
                affected=[
                    PathAwarePrinciple(
                        uid="p1", title="P", distance=1, path_strength=0.9, via_relationships=[]
                    )
                ],
                count=1,
                severity="low",
            ),
        ),
        risk_assessment=RiskAssessment(
            risk_level="high",
            risk_factors=["May affect 1 core principles"],
            mitigation_suggestions=[],
        ),
        opportunities=["Opportunity to live more aligned with principles"],
        graph_context=_graph_context(),
    )

    payload = jsonable_content(analysis.to_dict())
    # Must round-trip through JSON (the actual /api/choices/insights contract).
    encoded = json.dumps(payload)
    assert isinstance(payload, dict)
    assert payload["choice"]["uid"] == "c1"
    assert _EMBEDDING_KEYS.isdisjoint(payload["choice"])
    assert payload["impact_summary"]["total_entities_affected"] == 3
    assert payload["domain_impact"]["principles"]["count"] == 1
    # nested date serialized to ISO string, not a raw date object
    assert payload["domain_impact"]["goals"]["affected"][0]["target_date"] == "2026-01-01"
    assert "2026-01-01" in encoded


def test_decision_intelligence_to_dict_is_json_serializable() -> None:
    intelligence = DecisionIntelligence(
        choice=_embedded_choice(),
        context=DecisionContext(
            goals=[_goal()],
            principles=[],
            knowledge=[
                PathAwareKnowledge(
                    uid="k1", title="K", distance=1, path_strength=0.7, via_relationships=[]
                )
            ],
        ),
        impact=DecisionImpact(tasks=[], goals=[_goal()], habits=[]),
        decision_analysis=DecisionAnalysis(
            complexity=0.65, confidence_needed="medium", stake_level="low"
        ),
        recommendations=DecisionRecommendations(
            gather_more_info=True,
            consult_principles=["P"],
            consider_impact_on=["goal progress"],
            improvement_opportunities=[],
        ),
        graph_context=_graph_context(),
    )

    payload = jsonable_content(intelligence.to_dict())
    json.dumps(payload)  # must not raise
    assert _EMBEDDING_KEYS.isdisjoint(payload["choice"])
    assert payload["decision_analysis"]["complexity"] == 0.65
    assert payload["context"]["knowledge"][0]["uid"] == "k1"
