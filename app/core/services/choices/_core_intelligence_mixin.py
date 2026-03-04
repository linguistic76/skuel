"""
Core Intelligence Mixin — ChoicesIntelligenceService
=====================================================

Graph-context methods: get_choice_with_context, get_decision_intelligence,
analyze_choice_impact.

Part of choices_intelligence_service.py decomposition (March 2026).
See: /docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.constants import ConfidenceLevel
from core.utils.decorators import requires_graph_intelligence
from core.utils.result_simplified import Errors, Result

if TYPE_CHECKING:
    from core.models.choice.choice import Choice
    from core.models.graph_context import GraphContext
    from core.services.choices.choices_types import (
        ChoiceImpactAnalysis,
        DecisionIntelligence,
    )


class _CoreIntelligenceMixin:
    """
    Graph context methods for ChoicesIntelligenceService.

    Declares class-level attributes used by these methods so mypy
    resolves them without runtime cost.
    """

    # Populated by ChoicesIntelligenceService.__init__
    backend: Any
    orchestrator: Any
    relationships: Any
    path_helper: Any

    @requires_graph_intelligence("get_choice_with_context")
    async def get_choice_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[Choice, GraphContext]]:
        """
        Get choice with full graph context using pure Cypher graph intelligence.

        Automatically selects optimal query type based on choice's suggested intent:
        - RELATIONSHIP → Related goals, principles, knowledge
        - HIERARCHICAL → Decision hierarchy and dependencies
        - AGGREGATION → Impact analysis across domains
        - Default → Comprehensive decision ecosystem

        This replaces multiple sequential queries with a single Pure Cypher query,
        achieving 8-10x performance improvement.

        Args:
            uid: Choice UID,
            depth: Graph traversal depth (default: 2)

        Returns:
            Result containing (choice, GraphContext) tuple with:
            - choice: The Choice domain model
            - GraphContext: Rich graph context with cross-domain insights including:
                * Related goals
                * Guiding principles
                * Required knowledge
                * Impacted tasks and habits
                * Performance metrics (query time, node counts)

        Performance:
            - Old approach: ~220ms (3-4 separate queries)
            - New approach: ~28ms (single APOC query)
            - 8x faster with single database round trip

        Example:
            ```python
            result = await choices_service.get_choice_with_context(
                "choice_1", GraphDepth.NEIGHBORHOOD
            )
            choice, context = result.value

            # Extract cross-domain insights
            goals = context.get_nodes_by_domain(Domain.GOALS)
            principles = context.get_nodes_by_domain(Domain.PRINCIPLES)
            knowledge = context.get_nodes_by_domain(Domain.KNOWLEDGE)

            print(f"This choice relates to {len(goals)} goals")
            print(f"Guided by {len(principles)} principles")
            ```
        """
        # Use GraphContextOrchestrator pattern (consolidation)
        # Orchestrator is guaranteed to exist when @requires_graph_intelligence passes
        if not self.orchestrator:
            return Result.fail(
                Errors.system(
                    message="GraphContextOrchestrator not initialized",
                    operation="get_choice_with_context",
                )
            )
        return await self.orchestrator.get_with_context(uid=uid, depth=depth)

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
            return Result.fail(choice_result.expect_error())

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
            return Result.fail(context_result.expect_error())

        context_dict = context_result.value

        # Parse path-aware context
        from core.models.graph.path_aware_types import ChoiceCrossContext

        # Extract path-aware entities from dict (using shared helper)
        supporting_goals = [
            self.path_helper.parse_goal(g) for g in context_dict.get("supporting_goals", [])
        ]
        conflicting_goals = [
            self.path_helper.parse_goal(g) for g in context_dict.get("conflicting_goals", [])
        ]
        guiding_principles = [
            self.path_helper.parse_principle(p) for p in context_dict.get("principles", [])
        ]
        required_knowledge = [
            self.path_helper.parse_knowledge(k) for k in context_dict.get("knowledge", [])
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
        affected_tasks = []
        affected_goals = related_goals + conflicting_goals
        affected_habits = []

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
            return Result.fail(choice_result.expect_error())

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
            return Result.fail(context_result.expect_error())

        context_dict = context_result.value

        supporting_goals = [
            self.path_helper.parse_goal(g) for g in context_dict.get("supporting_goals", [])
        ]
        conflicting_goals = [
            self.path_helper.parse_goal(g) for g in context_dict.get("conflicting_goals", [])
        ]
        affected_principles = [
            self.path_helper.parse_principle(p) for p in context_dict.get("principles", [])
        ]
        knowledge = [self.path_helper.parse_knowledge(k) for k in context_dict.get("knowledge", [])]

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
        affected_tasks = []  # Not in choice cross-domain context
        affected_habits = []  # Not in choice cross-domain context

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
