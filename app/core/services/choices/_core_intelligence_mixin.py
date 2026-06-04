"""
Core Intelligence Mixin — ChoicesIntelligenceService
=====================================================

Graph-context methods: get_choice_with_context, get_decision_intelligence,
analyze_choice_impact.

Part of choices_intelligence_service.py decomposition (March 2026).
See: /docs/architecture/ENTITY_TYPE_ARCHITECTURE.md
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
    from core.models.choice.choice import Choice
    from core.models.graph_context import GraphContext
    from core.services.choices.choices_types import (
        ChoiceImpactAnalysis,
        DecisionIntelligence,
    )


def _path_rank(entity: dict[str, Any]) -> tuple[float, float]:
    """Sort key for picking the strongest path to a node: lowest distance wins, then
    highest path_strength. Missing/None metadata sorts worst (a real measured path always
    beats an unmeasured one)."""
    distance = entity.get("distance")
    strength = entity.get("path_strength")
    return (
        float(distance) if distance is not None else float("inf"),
        -(float(strength) if strength is not None else 0.0),
    )


def _union_buckets(context_dict: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    """Collect cross-domain-context bucket dicts across keys, one entry per uid (the
    strongest path).

    ``UnifiedRelationshipService.get_cross_domain_context()`` emits one bucket per
    CHOICES_CONFIG ``context_field_name``, each a list of
    ``{"uid", "title", "distance", "path_strength", "via_relationships"}`` dicts —
    exactly the shape ``PathAwareAnalyzer.parse_*`` consume.

    De-dup by uid serves two purposes:
    1. A single typed field may aggregate several buckets: a choice's informing
       principles span both INFORMED_BY_PRINCIPLE (outgoing, ``aligned_principles``) and
       GUIDES_CHOICE (incoming, ``guiding_principles``).
    2. Even within ONE bucket the same node can recur: the underlying Cypher does
       ``collect(DISTINCT {uid, distance, path_strength, ...})`` — DISTINCT over the whole
       path-metadata map, not the uid — so at ``depth>=2`` a node reachable via multiple
       distinct paths appears once per path. Without this de-dup, goal/knowledge counts,
       stake level, impact score and cascade impact would all inflate.

    When a uid recurs, the **strongest** path is kept (lowest distance, then highest
    path_strength via ``_path_rank``), NOT the first raw occurrence — the producer query
    has no ``ORDER BY``, so first-seen could be the weaker/indirect path and would then
    misreport ``distance``/``path_strength``, the direct-connection count, max path depth,
    and the direct-vs-indirect cascade split. Order-preserving by first-seen uid.
    """
    best: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for key in keys:
        for entity in context_dict.get(key) or []:
            if not isinstance(entity, dict):
                continue
            uid = entity.get("uid")
            if not uid:
                continue
            incumbent = best.get(uid)
            if incumbent is None:
                best[uid] = entity
                order.append(uid)
            elif _path_rank(entity) < _path_rank(incumbent):
                best[uid] = entity
    return [best[uid] for uid in order]


class _CoreIntelligenceMixin(_SharedCoreMixin):
    """
    Core + decision intelligence for ChoicesIntelligenceService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by ChoicesIntelligenceService.__init__
    backend: Any
    relationships: Any
    path_helper: Any

    @requires_graph_intelligence("get_choice_with_context")
    async def get_choice_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[Choice, GraphContext]]:
        """Domain-named alias for get_with_context(). See shared base."""
        return await self.get_with_context(uid, depth)

    @requires_graph_intelligence("get_decision_intelligence")
    async def get_decision_intelligence(
        self, choice_uid: str, min_confidence: float = ConfidenceLevel.MEDIUM, depth: int = 2
    ) -> Result[DecisionIntelligence]:
        """
        Get complete decision intelligence for informed choice

        Provides comprehensive decision support including:
        - Decision context (goals, principles, knowledge)
        - Impact analysis (tasks, habits affected)
        - Decision complexity assessment
        - Option rankings and recommendations

        Args:
            choice_uid: Choice UID

        Returns:
            Result containing decision intelligence:
            {
                "choice": Choice,
                "context": {
                    "goals": List[Goal],
                    "principles": List[Principle],
                    "knowledge": List[Ku]
                },
                "impact": {
                    "tasks": List[Task],
                    "goals": List[Goal],
                    "habits": List[Habit]
                },
                "decision_analysis": {
                    "complexity": float, # 0-10
                    "confidence_needed": str, # "low", "medium", "high"
                    "stake_level": str # "low", "medium", "high"
                },
                "recommendations": {
                    "gather_more_info": bool,
                    "consult_principles": List[str],
                    "consider_impact_on": List[str]
                },
                "graph_context": GraphContext
            }

        Example:
            ```python
            result = await choices_service.get_decision_intelligence("choice_1")
            intelligence = result.value

            context = intelligence["context"]
            print(f"Related goals: {len(context['goals'])}")
            print(f"Guiding principles: {len(context['principles'])}")
            print(f"Required knowledge: {len(context['knowledge'])}")

            impact = intelligence["impact"]
            print(f"Will affect {len(impact['tasks'])} tasks")
            print(f"Will affect {len(impact['habits'])} habits")

            analysis = intelligence["decision_analysis"]
            print(f"Decision complexity: {analysis['complexity']:.1f}/10")
            print(f"Stakes: {analysis['stake_level']}")
            ```
        """
        from core.models.choice.choice import Choice
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
        from core.utils.result_simplified import Errors, Result

        # Get choice
        choice_result = await self.backend.get(choice_uid)
        if choice_result.is_error:
            return Result.fail(choice_result)

        if not choice_result.value:
            return Result.fail(Errors.not_found(resource="Choice", identifier=choice_uid))

        choice = choice_result.value  # backend.get() already returns domain model
        assert isinstance(choice, Choice)

        # Get cross-domain context using relationship helper (Priority 2 refactoring)
        if self.relationships is None:
            return Result.fail(
                Errors.system(
                    message="ChoicesRelationshipOperations not available",
                    operation="get_choice_with_context",
                )
            )

        context_result = await self.relationships.get_cross_domain_context(
            choice_uid, depth=depth, min_confidence=min_confidence
        )
        if context_result.is_error:
            return Result.fail(context_result)

        context_dict = context_result.value

        # Parse path-aware context
        from core.models.graph.path_aware_types import ChoiceCrossContext

        # Extract path-aware entities from the real CHOICES_CONFIG buckets (the
        # config-driven get_cross_domain_context emits context_field_name buckets, NOT
        # generic domain names). Goals come from the single polarity-free AFFECTS_GOAL
        # edge (`affected_goals`); informing principles span both INFORMED_BY_PRINCIPLE
        # (outgoing, `aligned_principles`) and GUIDES_CHOICE (incoming,
        # `guiding_principles`); knowledge from INFORMED_BY_KNOWLEDGE.
        supporting_goals = [
            self.path_helper.parse_goal(g) for g in _union_buckets(context_dict, "affected_goals")
        ]
        # No conflicting-goal edge exists — AFFECTS_GOAL is polarity-free (#214). Stays
        # empty rather than reading a bucket nothing emits.
        conflicting_goals: list[Any] = []
        guiding_principles = [
            self.path_helper.parse_principle(p)
            for p in _union_buckets(context_dict, "aligned_principles", "guiding_principles")
        ]
        required_knowledge = [
            self.path_helper.parse_knowledge(k)
            for k in _union_buckets(context_dict, "informed_by_knowledge")
        ]

        # Create strongly-typed context
        path_context = ChoiceCrossContext(
            choice_uid=choice_uid,
            principles=guiding_principles,
            supporting_goals=supporting_goals,
            conflicting_goals=conflicting_goals,
            knowledge=required_knowledge,
        )

        # For backward compatibility, use lists
        related_goals = supporting_goals + conflicting_goals

        # Note: Tasks/habits impact analysis not in choice cross-domain context
        affected_tasks: list[Any] = []
        affected_goals = related_goals + conflicting_goals
        affected_habits: list[Any] = []

        # Calculate decision complexity using choice domain method
        complexity = choice.calculate_decision_complexity()

        # Determine confidence needed and stake level
        confidence_needed = "medium"
        if complexity > 7.0:
            confidence_needed = "high"
        elif complexity < 3.0:
            confidence_needed = "low"

        stake_level = "medium"
        total_impact = len(affected_tasks) + len(affected_goals) + len(affected_habits)
        if total_impact > 10:
            stake_level = "high"
        elif total_impact < 3:
            stake_level = "low"

        # Build recommendations with mutable accumulation
        consult_principles_list = (
            [p.title for p in guiding_principles] if guiding_principles else []
        )
        consider_impact_list: list[str] = []

        if affected_goals:
            consider_impact_list.append("goal progress")
        if affected_habits:
            consider_impact_list.append("habit consistency")
        if affected_tasks:
            consider_impact_list.append("task completion")

        # Generate path-aware improvement_opportunities
        improvement_opportunities_list = self.path_helper.generate_recommendations(
            goals=related_goals,
            knowledge=required_knowledge,
            principles=guiding_principles,
        )

        # Calculate cascade impact for graph context
        cascade_impact = self.path_helper.calculate_cascade_impact(
            goals=related_goals,
            knowledge=required_knowledge,
            principles=guiding_principles,
        )

        cascade_impact_obj = CascadeImpact(
            total_impact=cascade_impact.get("total_impact", 0.0),
            direct_impact=cascade_impact.get("direct_impact", 0.0),
            indirect_impact=cascade_impact.get("indirect_impact", 0.0),
            domain_impacts=cascade_impact.get("domain_impacts", {}),
        )

        path_aware_context_obj = PathAwareContext(
            total_strong_connections=path_context.strong_connections(),
            direct_connections_count=len(path_context.direct_goals)
            + len(path_context.direct_principles),
            max_path_depth=max((e.distance for e in path_context.all_goals), default=0),
            avg_path_strength=path_context.avg_strength(),
        )

        graph_context_obj = ChoiceGraphContext(
            cascade_impact=cascade_impact_obj,
            path_aware_context=path_aware_context_obj,
            raw_context=context_dict,
        )

        # Build immutable result using frozen dataclasses
        decision_context = DecisionContext(
            goals=related_goals, principles=guiding_principles, knowledge=required_knowledge
        )

        decision_impact = DecisionImpact(
            tasks=affected_tasks, goals=affected_goals, habits=affected_habits
        )

        decision_analysis = DecisionAnalysis(
            complexity=complexity, confidence_needed=confidence_needed, stake_level=stake_level
        )

        recommendations = DecisionRecommendations(
            gather_more_info=complexity > 6.0 and len(required_knowledge) > 0,
            consult_principles=consult_principles_list,
            consider_impact_on=consider_impact_list,
            improvement_opportunities=improvement_opportunities_list,
        )

        intelligence = DecisionIntelligence(
            choice=choice,
            context=decision_context,
            impact=decision_impact,
            decision_analysis=decision_analysis,
            recommendations=recommendations,
            graph_context=graph_context_obj,
        )

        return Result.ok(intelligence)

    @requires_graph_intelligence("analyze_choice_impact")
    async def analyze_choice_impact(
        self, choice_uid: str, depth: int = 2, min_confidence: float = ConfidenceLevel.MEDIUM
    ) -> Result[ChoiceImpactAnalysis]:
        """
        Analyze cross-domain impact of a choice

        Provides detailed impact analysis including:
        - Entities affected by this choice
        - Impact severity by domain
        - Risk assessment
        - Opportunity identification

        Args:
            choice_uid: Choice UID,
            depth: Graph traversal depth (default: 2)

        Returns:
            Result containing impact analysis:
            {
                "choice": Choice,
                "impact_summary": {
                    "total_entities_affected": int,
                    "domains_affected": List[str],
                    "impact_score": float # 0-10
                },
                "domain_impact": {
                    "goals": {
                        "affected": List[Goal],
                        "count": int,
                        "severity": str
                    },
                    "tasks": {...},
                    "habits": {...},
                    "principles": {...}
                },
                "risk_assessment": {
                    "risk_level": str, # "low", "medium", "high"
                    "risk_factors": List[str],
                    "mitigation_suggestions": List[str]
                },
                "opportunities": List[str],
                "graph_context": GraphContext
            }

        Example:
            ```python
            result = await choices_service.analyze_choice_impact("choice_1")
            impact = result.value

            summary = impact["impact_summary"]
            print(f"Affects {summary['total_entities_affected']} entities")
            print(f"Impact score: {summary['impact_score']:.1f}/10")

            risk = impact["risk_assessment"]
            print(f"Risk level: {risk['risk_level']}")
            for factor in risk["risk_factors"]:
                print(f" ⚠ {factor}")
            ```
        """
        from core.models.graph.path_aware_types import ChoiceCrossContext
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
        from core.utils.result_simplified import Errors, Result

        # Get choice
        choice_result = await self.backend.get(choice_uid)
        if choice_result.is_error:
            return Result.fail(choice_result)

        if not choice_result.value:
            return Result.fail(Errors.not_found(resource="Choice", identifier=choice_uid))

        choice = choice_result.value  # backend.get() already returns domain model

        # Get cross-domain context with configurable depth
        if self.relationships is None:
            return Result.fail(
                Errors.system(
                    message="ChoicesRelationshipOperations not available",
                    operation="analyze_cross_domain_impact",
                )
            )

        context_result = await self.relationships.get_cross_domain_context(
            choice_uid, depth=depth, min_confidence=min_confidence
        )
        if context_result.is_error:
            return Result.fail(context_result)

        context_dict = context_result.value

        # Read the real CHOICES_CONFIG buckets (see get_decision_intelligence): goals
        # from the polarity-free AFFECTS_GOAL edge, informing principles from
        # INFORMED_BY_PRINCIPLE union GUIDES_CHOICE, knowledge from INFORMED_BY_KNOWLEDGE.
        supporting_goals = [
            self.path_helper.parse_goal(g) for g in _union_buckets(context_dict, "affected_goals")
        ]
        # No conflicting-goal edge exists — AFFECTS_GOAL is polarity-free (#214).
        conflicting_goals: list[Any] = []
        affected_principles = [
            self.path_helper.parse_principle(p)
            for p in _union_buckets(context_dict, "aligned_principles", "guiding_principles")
        ]
        knowledge = [
            self.path_helper.parse_knowledge(k)
            for k in _union_buckets(context_dict, "informed_by_knowledge")
        ]

        # Create path-aware context for cascade analysis
        path_context = ChoiceCrossContext(
            choice_uid=choice_uid,
            principles=affected_principles,
            supporting_goals=supporting_goals,
            conflicting_goals=conflicting_goals,
            knowledge=knowledge,
        )

        # Calculate cascade impact using shared helper
        cascade_impact = self.path_helper.calculate_cascade_impact(
            goals=supporting_goals + conflicting_goals,
            knowledge=knowledge,
            principles=affected_principles,
        )

        # Extract affected entities (backward compatibility)
        affected_goals = supporting_goals + conflicting_goals
        affected_tasks: list[Any] = []  # Not in choice cross-domain context
        affected_habits: list[Any] = []  # Not in choice cross-domain context

        # Calculate impact summary with mutable accumulation
        total_affected = (
            len(affected_goals)
            + len(affected_tasks)
            + len(affected_habits)
            + len(affected_principles)
        )
        domains_affected_list: list[str] = []
        if affected_goals:
            domains_affected_list.append("goals")
        if affected_tasks:
            domains_affected_list.append("tasks")
        if affected_habits:
            domains_affected_list.append("habits")
        if affected_principles:
            domains_affected_list.append("principles")

        # Calculate impact score (0-10)
        impact_score = min(
            10.0,
            (
                len(affected_goals) * 2.5
                + len(affected_habits) * 2.0
                + len(affected_tasks) * 1.0
                + len(affected_principles) * 3.0
            ),
        )

        # Determine severity by domain
        def get_severity(count: int) -> str:
            if count > 5:
                return "high"
            elif count > 2:
                return "medium"
            elif count > 0:
                return "low"
            return "none"

        # Risk assessment with mutable accumulation
        risk_level = "low"
        risk_factors_list: list[str] = []

        if len(affected_principles) > 0:
            risk_level = "high"
            risk_factors_list.append(f"May affect {len(affected_principles)} core principles")

        if len(affected_goals) > 3:
            if risk_level != "high":
                risk_level = "medium"
            risk_factors_list.append(f"Impacts {len(affected_goals)} goals")

        if impact_score > 7.0:
            risk_level = "high"
            risk_factors_list.append("High overall impact score")

        # Mitigation suggestions
        mitigation_list: list[str] = []
        if risk_level == "high":
            mitigation_list.append("Carefully evaluate alignment with principles")
            mitigation_list.append("Consider phased implementation")
        if len(affected_goals) > 0:
            mitigation_list.append("Track impact on goal progress")
        if len(affected_habits) > 0:
            mitigation_list.append("Plan for habit adjustments")

        # Identify opportunities (including path-strength recommendations)
        opportunities_list: list[str] = []
        if len(affected_goals) > 2:
            opportunities_list.append("Opportunity to accelerate multiple goals simultaneously")
        if len(affected_habits) > 0:
            opportunities_list.append("Opportunity to strengthen habit consistency")
        if len(affected_principles) > 0:
            opportunities_list.append("Opportunity to live more aligned with principles")

        # Add path-strength-based recommendations
        path_recommendations = self.path_helper.generate_recommendations(
            goals=supporting_goals + conflicting_goals,
            knowledge=knowledge,
            principles=affected_principles,
        )
        opportunities_list.extend(path_recommendations)

        # Build immutable result using frozen dataclasses
        impact_summary = ImpactSummary(
            total_entities_affected=total_affected,
            domains_affected=domains_affected_list,
            impact_score=impact_score,
        )

        domain_impact = DomainImpactBreakdown(
            goals=DomainImpactDetail(
                affected=affected_goals,
                count=len(affected_goals),
                severity=get_severity(len(affected_goals)),
            ),
            tasks=DomainImpactDetail(
                affected=affected_tasks,
                count=len(affected_tasks),
                severity=get_severity(len(affected_tasks)),
            ),
            habits=DomainImpactDetail(
                affected=affected_habits,
                count=len(affected_habits),
                severity=get_severity(len(affected_habits)),
            ),
            principles=DomainImpactDetail(
                affected=affected_principles,
                count=len(affected_principles),
                severity=get_severity(len(affected_principles)),
            ),
        )

        risk_assessment = RiskAssessment(
            risk_level=risk_level,
            risk_factors=risk_factors_list,
            mitigation_suggestions=mitigation_list,
        )

        cascade_impact_obj = CascadeImpact(
            total_impact=cascade_impact.get("total_impact", 0.0),
            direct_impact=cascade_impact.get("direct_impact", 0.0),
            indirect_impact=cascade_impact.get("indirect_impact", 0.0),
            domain_impacts=cascade_impact.get("domain_impacts", {}),
        )

        path_aware_context_obj = PathAwareContext(
            total_strong_connections=path_context.strong_connections(),
            direct_connections_count=len(path_context.direct_goals)
            + len(path_context.direct_principles),
            max_path_depth=max((e.distance for e in path_context.all_goals), default=0),
            avg_path_strength=path_context.avg_strength(),
        )

        graph_context_obj = ChoiceGraphContext(
            cascade_impact=cascade_impact_obj,
            path_aware_context=path_aware_context_obj,
            raw_context=context_dict,
        )

        impact_analysis = ChoiceImpactAnalysis(
            choice=choice,
            impact_summary=impact_summary,
            domain_impact=domain_impact,
            risk_assessment=risk_assessment,
            opportunities=opportunities_list,
            graph_context=graph_context_obj,
        )

        return Result.ok(impact_analysis)
