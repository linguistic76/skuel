"""
Choices Intelligence Service - Pure Cypher Graph Analytics
======================================================

Handles Pure Cypher graph intelligence queries for choices.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from core.constants import ConfidenceLevel
from core.events.choice_events import ChoiceMade, ChoiceOutcomeRecorded
from core.models.enums import Domain
from core.models.enums.activity_enums import DecisionQualityLevel
from core.models.insight.persisted_insight import InsightImpact, InsightType, PersistedInsight
from core.models.ku.ku import Ku
from core.models.ku.ku_base import KuBase
from core.models.ku.ku_dto import KuDTO
from core.models.relationship_names import RelationshipName
from core.models.shared.dual_track import DualTrackResult
from core.services.base_analytics_service import BaseAnalyticsService
from core.services.choices.choices_types import (
    ChoiceImpactAnalysis,
    DecisionAnalysis,
    DecisionContext,
    DecisionImpact,
    DecisionIntelligence,
    DecisionRecommendations,
    DomainImpactBreakdown,
    DomainImpactDetail,
    ImpactSummary,
    RiskAssessment,
)
from core.services.intelligence import (
    GraphContextOrchestrator,
)
from core.services.intelligence.path_aware_intelligence_helper import (
    PathAwareIntelligenceHelper,
)
from core.utils.decorators import requires_graph_intelligence
from core.utils.result_simplified import Errors, Result
from core.utils.sort_functions import get_aligned_count, get_domain_choice_count

if TYPE_CHECKING:
    from core.models.graph_context import GraphContext
    from core.services.insight.insight_store import InsightStore
    from core.services.protocols import BackendOperations
    from core.services.protocols.domain_protocols import ChoicesRelationshipOperations


class ChoicesIntelligenceService(BaseAnalyticsService["BackendOperations[Ku]", Ku]):
    """
    Pure Cypher graph intelligence queries for choices.

    NOTE: This service extends BaseAnalyticsService (ADR-030) and has NO AI dependencies.
    It uses pure graph queries and Python calculations - no LLM or embeddings.

    Responsibilities:
    - Get choice with graph context (Phase 1-4)
    - Analyze choice impact across domains
    - Provide decision intelligence
    - Track decision patterns over time


    Source Tag: "choices_intelligence_service_explicit"
    - Format: "choices_intelligence_service_explicit" for user-created relationships
    - Format: "choices_intelligence_service_inferred" for system-generated relationships

    Confidence Scoring:
    - 0.9+: User explicitly defined relationship
    - 0.7-0.9: Inferred from choices_intelligence metadata
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
    _service_name = "choices.intelligence"

    def __init__(
        self,
        backend: BackendOperations[Ku],
        graph_intelligence_service=None,
        relationship_service: ChoicesRelationshipOperations | None = None,
        insight_store: InsightStore | None = None,
    ) -> None:
        """
        Initialize choices intelligence service.

        Args:
            backend: Protocol-based backend for choice operations (Ku model)
            graph_intelligence_service: GraphIntelligenceService for pure Cypher analytics,
            relationship_service: ChoicesRelationshipOperations protocol for specialized relationship queries
            insight_store: InsightStore for persisting event-driven insights (optional)
        """
        super().__init__(
            backend=backend,
            graph_intelligence_service=graph_intelligence_service,
            relationship_service=relationship_service,
        )
        self.insight_store = insight_store

        # Initialize GraphContextOrchestrator for get_with_context pattern (Phase 2)
        if graph_intelligence_service:
            self.orchestrator = GraphContextOrchestrator[KuBase, KuDTO](
                service=self,
                backend_get_method="get",  # ChoicesService uses generic 'get'
                dto_class=KuDTO,
                model_class=KuBase,
                domain=Domain.CHOICES,
            )

        # Initialize path-aware intelligence helper (Phase 4)
        self.path_helper = PathAwareIntelligenceHelper()

    # ========================================================================
    # DOMAIN-SPECIFIC CONTRACT
    # ========================================================================

    @property
    def entity_label(self) -> str:
        """Return the graph label for Choice entities (now Ku with ku_type filter)."""
        return "Ku"

    # ========================================================================
    # INTELLIGENCEOPERATIONS PROTOCOL METHODS (January 2026)
    # These methods implement the IntelligenceOperations protocol for use
    # with IntelligenceRouteFactory.
    # ========================================================================

    async def get_with_context(self, uid: str, depth: int = 2) -> Result[tuple[Ku, GraphContext]]:
        """
        Get choice with full graph context.

        Protocol method: Maps to get_choice_with_context.
        Used by IntelligenceRouteFactory for GET /api/choices/context route.

        Args:
            uid: Choice UID
            depth: Graph traversal depth (default: 2)

        Returns:
            Result containing (Choice, GraphContext) tuple
        """
        return await self.get_choice_with_context(uid, depth)

    async def get_performance_analytics(
        self, user_uid: str, _period_days: int = 30
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
            return Result.fail(choices_result.expect_error())

        choices = choices_result.value or []

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

    # ================================================================================
    # GRAPH INTELLIGENCE METHODS
    # ================================================================================

    @requires_graph_intelligence("get_choice_with_context")
    async def get_choice_with_context(
        self, uid: str, depth: int = 2
    ) -> Result[tuple[Ku, GraphContext]]:
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
        # Use GraphContextOrchestrator pattern (Phase 2 consolidation)
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
        Get complete decision intelligence for informed choice using Phase 1-4.

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
                    "complexity": float,  # 0-10
                    "confidence_needed": str,  # "low", "medium", "high"
                    "stake_level": str  # "low", "medium", "high"
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
        # Get choice
        choice_result = await self.backend.get(choice_uid)
        if choice_result.is_error:
            return Result.fail(choice_result.expect_error())

        if not choice_result.value:
            return Result.fail(Errors.not_found(resource="Choice", identifier=choice_uid))

        choice = choice_result.value  # backend.get() already returns Ku domain model

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

        # Parse path-aware context (Phase 4: Path Intelligence)
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

        # Generate path-aware improvement_opportunities (Phase 5: Path-Aware Intelligence)
        improvement_opportunities_list = self.path_helper.generate_recommendations(
            goals=related_goals,
            knowledge=required_knowledge,
            principles=guiding_principles,
        )

        # Calculate cascade impact for graph context (Phase 5)
        cascade_impact = self.path_helper.calculate_cascade_impact(
            goals=related_goals,
            knowledge=required_knowledge,
            principles=guiding_principles,
        )

        # Build structured graph context (Phase 5)
        from core.services.choices.choices_types import (
            CascadeImpact,
            ChoiceGraphContext,
            PathAwareContext,
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
        Analyze cross-domain impact of a choice using Phase 1-4.

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
                    "impact_score": float  # 0-10
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
                    "risk_level": str,  # "low", "medium", "high"
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
                print(f"  ⚠ {factor}")
            ```
        """
        # Get choice
        choice_result = await self.backend.get(choice_uid)
        if choice_result.is_error:
            return Result.fail(choice_result.expect_error())

        if not choice_result.value:
            return Result.fail(Errors.not_found(resource="Choice", identifier=choice_uid))

        choice = choice_result.value  # backend.get() already returns Ku domain model

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

        # Parse path-aware context (Phase 4: Path Intelligence)
        from core.models.graph.path_aware_types import ChoiceCrossContext

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

        # Add path-strength-based recommendations (Phase 4 - using shared helper)
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

        # Build structured graph context with cascade impact (Phase 5: Path-Aware Intelligence)
        from core.services.choices.choices_types import (
            CascadeImpact,
            ChoiceGraphContext,
            PathAwareContext,
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

    # ========================================================================
    # DOMAIN-SPECIFIC INTELLIGENCE (Phase 4)
    # ========================================================================
    # Note: Generic path-aware helpers moved to PathAwareIntelligenceHelper
    # This section reserved for Choice-specific intelligence methods

    # ========================================================================
    # RELATIONSHIP HELPER INTEGRATION (November 2025)
    # ========================================================================
    # Two-phase optimization methods using fetch() for quick metrics

    async def get_quick_decision_metrics(self, choice_uid: str) -> Result[dict[str, Any]]:
        """
        Get quick decision metrics using parallel relationship fetch.

        OPTIMIZATION: This method uses fetch() for ~60% faster simple metrics
        without path metadata. Use this for:
        - Dashboard quick views
        - Decision complexity screening
        - Batch analysis of multiple choices

        For full intelligence with path metadata, use get_decision_intelligence().

        Args:
            choice_uid: Choice UID

        Returns:
            Result containing:
            {
                "choice_uid": str,
                "relationship_counts": {
                    "knowledge": int,
                    "principles": int,
                    "learning_paths": int,
                    "required_knowledge": int
                },
                "quick_complexity": float (0-10),
                "stake_level": str ("low" | "medium" | "high"),
                "needs_full_analysis": bool,
                "is_informed": bool,
                "is_principle_aligned": bool
            }

        Example:
            ```python
            # Quick check first (fast - ~160ms)
            metrics_result = await service.get_quick_decision_metrics(choice_uid)
            metrics = metrics_result.value

            if metrics["needs_full_analysis"]:
                # Only call expensive method when needed (slow - ~250ms)
                intel_result = await service.get_decision_intelligence(choice_uid)
            else:
                # Use quick metrics for simple decisions
                print(f"Simple decision: {metrics['stake_level']} complexity")
            ```
        """
        from core.services.choices.choice_relationships import ChoiceRelationships

        # ✅ Use fetch() for fast parallel UID fetching (~160ms vs ~250ms)
        rels = await ChoiceRelationships.fetch(choice_uid, self.relationships)

        # Quick complexity calculation based on relationship counts
        knowledge_count = len(rels.informed_by_knowledge_uids)
        principle_count = len(rels.aligned_principle_uids)
        path_count = len(rels.opens_learning_path_uids)
        required_count = len(rels.required_knowledge_uids)

        total_relationships = knowledge_count + principle_count + path_count

        # Simple complexity score (0-10)
        quick_complexity = min(
            10.0, (knowledge_count * 1.5) + (principle_count * 2.0) + (required_count * 1.0)
        )

        # Stake level based on total relationships
        stake_level = "low"
        if total_relationships > 10:
            stake_level = "high"
        elif total_relationships > 5:
            stake_level = "medium"

        # Recommend full analysis for complex decisions
        needs_full_analysis = quick_complexity > 6.0 or principle_count > 2

        return Result.ok(
            {
                "choice_uid": choice_uid,
                "relationship_counts": {
                    "knowledge": knowledge_count,
                    "principles": principle_count,
                    "learning_paths": path_count,
                    "required_knowledge": required_count,
                },
                "quick_complexity": quick_complexity,
                "stake_level": stake_level,
                "needs_full_analysis": needs_full_analysis,
                "is_informed": rels.is_informed_decision(),
                "is_principle_aligned": rels.is_principle_aligned(),
            }
        )

    async def batch_analyze_decision_complexity(
        self, choice_uids: list[str]
    ) -> Result[dict[str, dict[str, Any]]]:
        """
        Analyze decision complexity for multiple choices in parallel.

        OPTIMIZATION: Uses fetch() for ~50% faster batch processing.
        Perfect for:
        - User dashboards showing all choices
        - Decision pattern analysis
        - Filtering choices by complexity before detailed analysis

        For individual full intelligence, use get_decision_intelligence().

        Args:
            choice_uids: List of choice UIDs

        Returns:
            Result containing mapping of choice_uid -> quick_metrics

        Example:
            ```python
            # Analyze 100 user choices in ~4s instead of ~8s
            all_choices = ["choice:1", "choice:2", ..., "choice:100"]
            batch_result = await service.batch_analyze_decision_complexity(all_choices)

            # Filter complex decisions for full analysis
            complex_choices = [
                uid
                for uid, metrics in batch_result.value.items()
                if metrics["complexity"] > 6.0
            ]

            # Only run expensive analysis on subset
            for uid in complex_choices:
                await service.get_decision_intelligence(uid)
            ```
        """
        import asyncio

        from core.services.choices.choice_relationships import ChoiceRelationships

        # ✅ Fetch all relationships in parallel (~4s for 100 choices vs ~8s sequential)
        all_rels = await asyncio.gather(
            *[ChoiceRelationships.fetch(uid, self.relationships) for uid in choice_uids]
        )

        # Calculate quick complexity for each
        results = {}
        for choice_uid, rels in zip(choice_uids, all_rels, strict=False):
            knowledge_count = len(rels.informed_by_knowledge_uids)
            principle_count = len(rels.aligned_principle_uids)
            total = rels.total_knowledge_count()

            quick_complexity = min(10.0, (knowledge_count * 1.5) + (principle_count * 2.0))

            results[choice_uid] = {
                "complexity": quick_complexity,
                "total_relationships": total,
                "is_informed": rels.is_informed_decision(),
                "is_principle_aligned": rels.is_principle_aligned(),
            }

        return Result.ok(results)

    # ========================================================================
    # DECISION PATTERN ANALYTICS (Consolidated from ChoicesAnalyticsService - January 2026)
    # ========================================================================

    async def get_decision_patterns(self, user_uid: str, days: int = 90) -> Result[dict[str, Any]]:
        """
        Analyze user's decision-making patterns.

        Provides pattern analysis including:
        - Decision frequency and distribution
        - Principle alignment trends
        - Goal-oriented vs exploratory choices
        - Decision quality metrics

        Args:
            user_uid: User UID
            days: Number of days to analyze (default: 90)

        Returns:
            Result containing decision pattern analysis:
            {
                "user_uid": str,
                "period": {
                    "start_date": date,
                    "end_date": date,
                    "days": int
                },
                "decision_metrics": {
                    "total_choices": int,
                    "choices_per_week": float,
                    "principle_aligned_percentage": float,
                    "goal_oriented_percentage": float
                },
                "decision_quality": {
                    "average_confidence": float,
                    "average_satisfaction": float,
                    "principle_alignment_score": float
                },
                "patterns": {
                    "most_common_principle": str,
                    "decision_making_trend": str,  # "improving", "stable", "declining"
                    "strategic_vs_tactical": str  # "strategic", "balanced", "tactical"
                },
                "recommendations": List[str]
            }

        Example:
            ```python
            result = await choices_service.get_decision_patterns(user_uid, days=90)
            patterns = result.value

            metrics = patterns["decision_metrics"]
            print(f"Made {metrics['total_choices']} choices")
            print(f"Avg {metrics['choices_per_week']:.1f} per week")
            print(f"Principle-aligned: {metrics['principle_aligned_percentage']:.0%}")

            quality = patterns["decision_quality"]
            print(f"Avg confidence: {quality['average_confidence']:.0%}")
            print(f"Avg satisfaction: {quality['average_satisfaction']:.0%}")
            ```
        """
        # Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        # Get user's choices in period
        choices_result = await self.backend.find_by(
            user_uid=user_uid, date__gte=start_date, date__lte=end_date
        )

        if choices_result.is_error:
            return Result.fail(choices_result.expect_error())

        choices = choices_result.value

        if not choices:
            return Result.ok(
                {
                    "user_uid": user_uid,
                    "period": {"start_date": start_date, "end_date": end_date, "days": days},
                    "decision_metrics": {
                        "total_choices": 0,
                        "choices_per_week": 0.0,
                        "principle_aligned_percentage": 0.0,
                        "goal_oriented_percentage": 0.0,
                    },
                    "decision_quality": {
                        "average_confidence": 0.0,
                        "average_satisfaction": 0.0,
                        "principle_alignment_score": 0.0,
                    },
                    "patterns": {
                        "most_common_principle": None,
                        "decision_making_trend": "no_data",
                        "strategic_vs_tactical": "no_data",
                    },
                    "recommendations": ["No choices found in this period"],
                }
            )

        # Calculate metrics
        total_choices = len(choices)
        weeks = days / 7.0
        choices_per_week = total_choices / weeks

        # Analyze alignment (simplified - would need actual principle/goal links)
        principle_aligned_count = sum(1 for c in choices if getattr(c, "aligned_principles", None))
        goal_oriented_count = sum(1 for c in choices if getattr(c, "related_goals", None))

        principle_aligned_percentage = (
            (principle_aligned_count / total_choices) if total_choices > 0 else 0
        )
        goal_oriented_percentage = (goal_oriented_count / total_choices) if total_choices > 0 else 0

        # Decision quality (simplified)
        avg_confidence = 0.7  # Placeholder
        avg_satisfaction = 0.75  # Placeholder
        principle_alignment_score = principle_aligned_percentage

        # Identify patterns
        decision_making_trend = "stable"
        if choices_per_week > 3:
            decision_making_trend = "improving"
        elif choices_per_week < 1:
            decision_making_trend = "declining"

        strategic_vs_tactical = "balanced"
        if goal_oriented_percentage > 0.6:
            strategic_vs_tactical = "strategic"
        elif goal_oriented_percentage < 0.3:
            strategic_vs_tactical = "tactical"

        # Recommendations
        recommendations = []
        if principle_aligned_percentage < 0.5:
            recommendations.append("Consider linking more choices to your core principles")
        if goal_oriented_percentage < 0.4:
            recommendations.append("Align more decisions with your goals")
        if choices_per_week < 1:
            recommendations.append("Track more decisions to build better patterns")
        if principle_aligned_percentage > 0.7:
            recommendations.append("Excellent principle alignment - keep it up!")

        return Result.ok(
            {
                "user_uid": user_uid,
                "period": {"start_date": start_date, "end_date": end_date, "days": days},
                "decision_metrics": {
                    "total_choices": total_choices,
                    "choices_per_week": choices_per_week,
                    "principle_aligned_percentage": principle_aligned_percentage,
                    "goal_oriented_percentage": goal_oriented_percentage,
                },
                "decision_quality": {
                    "average_confidence": avg_confidence,
                    "average_satisfaction": avg_satisfaction,
                    "principle_alignment_score": principle_alignment_score,
                },
                "patterns": {
                    "most_common_principle": None,  # Would need aggregation
                    "decision_making_trend": decision_making_trend,
                    "strategic_vs_tactical": strategic_vs_tactical,
                },
                "recommendations": recommendations,
            }
        )

    async def get_choice_quality_correlations(
        self, user_uid: str, days: int = 90
    ) -> Result[dict[str, Any]]:
        """
        Analyze correlations between decision quality metrics.

        Returns:
            Result containing correlations between:
            - Time pressure vs satisfaction
            - Energy level vs confidence
            - Principle alignment vs long-term satisfaction
            - Decision complexity vs quality
        """
        # Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        # Get user's choices in period
        choices_result = await self.backend.find_by(
            user_uid=user_uid, date__gte=start_date, date__lte=end_date
        )

        if choices_result.is_error:
            return Result.fail(choices_result.expect_error())

        choices = choices_result.value

        if not choices:
            return Result.ok(
                {
                    "user_uid": user_uid,
                    "period": {"start_date": start_date, "end_date": end_date, "days": days},
                    "correlations": {},
                    "insights": ["Insufficient data for correlation analysis"],
                }
            )

        # Placeholder correlation analysis
        # In real implementation, would calculate actual correlations from choice data
        correlations = {
            "time_pressure_vs_satisfaction": -0.3,  # Negative correlation
            "energy_vs_confidence": 0.7,  # Strong positive correlation
            "principle_alignment_vs_satisfaction": 0.8,  # Strong positive correlation
            "complexity_vs_quality": -0.2,  # Slight negative correlation
        }

        insights = []
        if correlations["time_pressure_vs_satisfaction"] < -0.2:
            insights.append("Decisions made under time pressure tend to have lower satisfaction")
        if correlations["energy_vs_confidence"] > 0.5:
            insights.append("Higher energy levels strongly correlate with decision confidence")
        if correlations["principle_alignment_vs_satisfaction"] > 0.7:
            insights.append("Principle-aligned decisions show significantly higher satisfaction")

        return Result.ok(
            {
                "user_uid": user_uid,
                "period": {"start_date": start_date, "end_date": end_date, "days": days},
                "total_choices_analyzed": len(choices),
                "correlations": correlations,
                "insights": insights,
                "recommendations": [
                    "Allow more time for important decisions",
                    "Make critical decisions when energy is high",
                    "Prioritize principle alignment for long-term satisfaction",
                ],
            }
        )

    async def get_domain_decision_patterns(
        self, user_uid: str, days: int = 90
    ) -> Result[dict[str, Any]]:
        """
        Analyze decision patterns by domain.

        Returns:
            Result containing per-domain analysis:
            - Choice frequency by domain
            - Average quality scores by domain
            - Domain-specific strengths and weaknesses
        """
        # Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        # Get user's choices in period
        choices_result = await self.backend.find_by(
            user_uid=user_uid, date__gte=start_date, date__lte=end_date
        )

        if choices_result.is_error:
            return Result.fail(choices_result.expect_error())

        choices = choices_result.value

        if not choices:
            return Result.ok(
                {
                    "user_uid": user_uid,
                    "period": {"start_date": start_date, "end_date": end_date, "days": days},
                    "domain_patterns": {},
                    "insights": ["No choices found in this period"],
                }
            )

        # Group choices by domain
        domain_choices: dict[str, list[Ku]] = defaultdict(list)
        for choice in choices:
            domain = getattr(choice, "domain", None)
            if domain:
                domain_choices[str(domain.value)].append(choice)

        # Analyze each domain
        domain_patterns = {}
        for domain, domain_choice_list in domain_choices.items():
            count = len(domain_choice_list)
            domain_patterns[domain] = {
                "choice_count": count,
                "percentage": (count / len(choices)) * 100,
                "avg_quality_score": 0.7,  # Placeholder
                "common_themes": [],
            }

        # Generate insights
        insights = []
        if domain_patterns:
            most_common_domain = max(domain_patterns.items(), key=get_domain_choice_count)
            insights.append(f"Most decisions made in {most_common_domain[0]} domain")

        return Result.ok(
            {
                "user_uid": user_uid,
                "period": {"start_date": start_date, "end_date": end_date, "days": days},
                "total_choices": len(choices),
                "domain_patterns": domain_patterns,
                "insights": insights,
            }
        )

    # ========================================================================
    # EVENT HANDLERS
    # ========================================================================

    async def handle_choice_outcome_recorded(self, event: ChoiceOutcomeRecorded) -> None:
        """Track decision quality when outcome is recorded.

        Event-driven handler that analyzes choice outcomes to learn from
        decisions. Enables cross-domain intelligence by connecting
        outcomes to principle alignment and decision patterns.

        The handler:
        1. Gets choice details (description, domain, selected option)
        2. Checks principle alignment of the choice
        3. Tracks outcome quality vs. alignment correlation
        4. Logs structured insights for pattern analysis

        Args:
            event: ChoiceOutcomeRecorded event with outcome context

        Note:
            This is a fire-and-forget handler - it logs but doesn't
            fail the original operation. Errors are caught and logged.
        """
        try:
            # 1. Get choice details
            choice_result = await self.backend.get(event.choice_uid)
            if choice_result.is_error:
                self.logger.warning(
                    f"Failed to get choice for outcome analysis: {event.choice_uid}"
                )
                return

            choice = choice_result.value
            if not choice:
                self.logger.warning(f"Choice not found for outcome analysis: {event.choice_uid}")
                return

            # 2. Query principle alignment relationships
            aligned_principles: list[str] = []
            if self.relationships:
                rel_result = await self.relationships.get_related_uids(
                    event.choice_uid,
                    RelationshipName.ALIGNED_WITH_PRINCIPLE.value,
                    "outgoing",
                )
                if rel_result.is_ok:
                    aligned_principles = rel_result.value

            # 3. Determine outcome quality category
            outcome_quality = event.outcome_quality
            quality_category = self._categorize_outcome_quality(outcome_quality)

            # 4. Analyze principle alignment correlation
            was_principle_aligned = len(aligned_principles) > 0
            alignment_outcome_match = (was_principle_aligned and outcome_quality >= 0.6) or (
                not was_principle_aligned and outcome_quality < 0.6
            )

            # 5. Log structured insights for decision learning
            self.logger.info(
                f"Choice outcome recorded: {(choice.description or '')[:50]}...",
                extra={
                    "choice_uid": event.choice_uid,
                    "user_uid": event.user_uid,
                    "outcome_quality": round(outcome_quality, 2),
                    "quality_category": quality_category,
                    "principles_aligned": len(aligned_principles),
                    "was_principle_aligned": was_principle_aligned,
                    "alignment_outcome_match": alignment_outcome_match,
                    "lessons_learned": (
                        event.lessons_learned[:100] if event.lessons_learned else None
                    ),
                    "event_type": "choice.outcome.analyzed",
                },
            )

            # Log insight about principle correlation
            if was_principle_aligned:
                if outcome_quality >= 0.7:
                    self.logger.info(
                        f"Principle-aligned choice had positive outcome ({quality_category})",
                        extra={
                            "choice_uid": event.choice_uid,
                            "principle_count": len(aligned_principles),
                            "event_type": "choice.principle_correlation.positive",
                        },
                    )
                elif outcome_quality < 0.4:
                    self.logger.info(
                        "Principle-aligned choice had negative outcome - worth reviewing",
                        extra={
                            "choice_uid": event.choice_uid,
                            "principle_uids": aligned_principles[:3],
                            "event_type": "choice.principle_correlation.review_needed",
                        },
                    )

        except Exception as e:
            self.logger.error(
                f"Error analyzing choice outcome: {e}",
                extra={"choice_uid": event.choice_uid, "error": str(e)},
            )

    def _categorize_outcome_quality(self, quality: float) -> str:
        """Categorize outcome quality score into named buckets.

        Args:
            quality: Outcome quality score (0.0 - 1.0)

        Returns:
            Category name: "excellent", "good", "neutral", "poor", "bad"
        """
        if quality >= 0.8:
            return "excellent"
        elif quality >= 0.6:
            return "good"
        elif quality >= 0.4:
            return "neutral"
        elif quality >= 0.2:
            return "poor"
        else:
            return "bad"

    async def handle_choice_made(self, event: ChoiceMade) -> None:
        """Track decision patterns when a choice is finalized.

        Event-driven handler that analyzes decision-making patterns when
        choices are made. Enables cross-domain intelligence by connecting
        decisions to principle alignment and confidence patterns.

        The handler:
        1. Gets choice details (description, domain, urgency)
        2. Checks principle alignment of the decision
        3. Analyzes confidence level vs. complexity correlation
        4. Logs structured insights for decision pattern analysis

        Args:
            event: ChoiceMade event with decision context

        Note:
            This is a fire-and-forget handler - it logs but doesn't
            fail the original operation. Errors are caught and logged.
        """
        try:
            # 1. Get choice details
            choice_result = await self.backend.get(event.choice_uid)
            if choice_result.is_error:
                self.logger.warning(
                    f"Failed to get choice for decision analysis: {event.choice_uid}"
                )
                return

            choice = choice_result.value
            if not choice:
                self.logger.warning(f"Choice not found for decision analysis: {event.choice_uid}")
                return

            # 2. Query principle alignment relationships
            aligned_principles: list[str] = []
            if self.relationships:
                rel_result = await self.relationships.get_related_uids(
                    event.choice_uid,
                    RelationshipName.ALIGNED_WITH_PRINCIPLE.value,
                    "outgoing",
                )
                if rel_result.is_ok:
                    aligned_principles = rel_result.value

            # 3. Analyze decision confidence
            confidence = event.confidence
            confidence_category = self._categorize_confidence(confidence)
            was_principle_aligned = len(aligned_principles) > 0

            # 4. Calculate decision complexity from choice model
            complexity = choice.calculate_decision_complexity()

            # 5. Analyze confidence vs complexity correlation
            # High confidence on complex decisions = experienced decision-maker
            # Low confidence on simple decisions = may need support
            confidence_complexity_ratio = confidence / max(complexity / 10.0, 0.1)

            # 6. Log structured insights
            self.logger.info(
                f"Choice made: {(choice.description or '')[:50]}...",
                extra={
                    "choice_uid": event.choice_uid,
                    "user_uid": event.user_uid,
                    "selected_option": event.selected_option,
                    "confidence": round(confidence, 2),
                    "confidence_category": confidence_category,
                    "complexity": round(complexity, 2),
                    "principles_aligned": len(aligned_principles),
                    "was_principle_aligned": was_principle_aligned,
                    "confidence_complexity_ratio": round(confidence_complexity_ratio, 2),
                    "event_type": "choice.made.analyzed",
                },
            )

            # Log insight about principle-aligned decisions
            if was_principle_aligned and confidence >= 0.7:
                self.logger.info(
                    "High-confidence principle-aligned decision made",
                    extra={
                        "choice_uid": event.choice_uid,
                        "principle_count": len(aligned_principles),
                        "confidence": round(confidence, 2),
                        "event_type": "choice.principle_confidence.high",
                    },
                )

                # Persist insight for positive pattern (Phase 1: Quick Wins)
                if self.insight_store:
                    insight = PersistedInsight(
                        uid=PersistedInsight.generate_uid(
                            InsightType.DECISION_PATTERN, event.choice_uid
                        ),
                        user_uid=event.user_uid,
                        insight_type=InsightType.DECISION_PATTERN,
                        domain="choices",
                        title="Strong Principle-Aligned Decision",
                        description=f"You made a high-confidence decision aligned with {len(aligned_principles)} principle(s).",
                        confidence=0.9,
                        impact=InsightImpact.LOW,  # Positive pattern, not urgent
                        entity_uid=event.choice_uid,
                        recommended_actions=[],
                        supporting_data={
                            "confidence": round(confidence, 2),
                            "principle_count": len(aligned_principles),
                            "aligned_principles": aligned_principles[:3],
                            "complexity": round(complexity, 2),
                        },
                    )
                    create_result = await self.insight_store.create_insight(insight)
                    if create_result.is_error:
                        self.logger.warning(
                            f"Failed to persist decision pattern insight: {create_result.error}"
                        )

            elif not was_principle_aligned and complexity > 5.0:
                self.logger.info(
                    "Complex decision made without principle alignment",
                    extra={
                        "choice_uid": event.choice_uid,
                        "complexity": round(complexity, 2),
                        "event_type": "choice.principle_alignment.missing",
                    },
                )

                # Persist insight for missing alignment (Phase 1: Quick Wins)
                if self.insight_store:
                    insight = PersistedInsight(
                        uid=PersistedInsight.generate_uid(
                            InsightType.PRINCIPLE_ALIGNMENT, event.choice_uid
                        ),
                        user_uid=event.user_uid,
                        insight_type=InsightType.PRINCIPLE_ALIGNMENT,
                        domain="choices",
                        title="Complex Decision Without Principle Guidance",
                        description=f"This complex decision (complexity: {round(complexity, 1)}) wasn't aligned with any principles.",
                        confidence=0.8,
                        impact=InsightImpact.MEDIUM,
                        entity_uid=event.choice_uid,
                        recommended_actions=[
                            {
                                "action": "Link principles to guide future decisions",
                                "rationale": "Principles provide clarity for complex choices",
                            }
                        ],
                        supporting_data={
                            "complexity": round(complexity, 2),
                            "confidence": round(confidence, 2),
                        },
                    )
                    create_result = await self.insight_store.create_insight(insight)
                    if create_result.is_error:
                        self.logger.warning(
                            f"Failed to persist alignment insight: {create_result.error}"
                        )

        except Exception as e:
            self.logger.error(
                f"Error analyzing choice made: {e}",
                extra={"choice_uid": event.choice_uid, "error": str(e)},
            )

    def _categorize_confidence(self, confidence: float) -> str:
        """Categorize decision confidence into named buckets.

        Args:
            confidence: Confidence score (0.0 - 1.0)

        Returns:
            Category name: "very_high", "high", "moderate", "low", "very_low"
        """
        if confidence >= 0.9:
            return "very_high"
        elif confidence >= 0.7:
            return "high"
        elif confidence >= 0.5:
            return "moderate"
        elif confidence >= 0.3:
            return "low"
        else:
            return "very_low"

    # ========================================================================
    # DUAL-TRACK ASSESSMENT (ADR-030)
    # ========================================================================

    async def assess_decision_quality_dual_track(
        self,
        user_uid: str,
        user_decision_quality_level: DecisionQualityLevel,
        user_evidence: str,
        user_reflection: str | None = None,
        period_days: int = 30,
    ) -> Result[DualTrackResult[DecisionQualityLevel]]:
        """
        Dual-track decision quality assessment for choices.

        Compares user's self-assessed decision-making quality with system-measured
        metrics (outcome quality, principle alignment, decision speed).

        Args:
            user_uid: User making the assessment
            user_decision_quality_level: User's self-reported decision quality level
            user_evidence: User's evidence for their assessment
            user_reflection: Optional reflection on decision-making
            period_days: Period to analyze (default 30 days)

        Returns:
            Result[DualTrackResult[DecisionQualityLevel]] with gap analysis
        """
        return await self._dual_track_assessment(
            uid=user_uid,  # Using user_uid as entity for user-level assessment
            user_uid=user_uid,
            user_level=user_decision_quality_level,
            user_evidence=user_evidence,
            user_reflection=user_reflection,
            system_calculator=self._make_system_decision_quality_calculator(period_days),
            level_scorer=self._decision_quality_level_to_score,
            entity_type="user_choices",
            insight_generator=self._generate_choice_gap_insights,
            recommendation_generator=self._generate_choice_gap_recommendations,
        )

    def _make_system_decision_quality_calculator(self, period_days: int) -> Any:
        """Create a system calculator for dual-track decision quality assessment."""

        async def _calculate(
            _entity: Any, u_uid: str
        ) -> tuple[DecisionQualityLevel, float, list[str]]:
            return await self._calculate_system_decision_quality_for_dual_track(u_uid, period_days)

        return _calculate

    async def _calculate_system_decision_quality_for_dual_track(
        self, user_uid: str, period_days: int = 30
    ) -> tuple[DecisionQualityLevel, float, list[str]]:
        """
        Calculate system-measured decision quality from choices data.

        Metrics considered:
        - Outcome quality (for decided choices with outcomes)
        - Principle alignment (decisions aligned with principles)
        - Decision rate (ability to decide vs staying pending)
        - Confidence calibration (high confidence → good outcomes)

        Returns:
            Tuple of (DecisionQualityLevel, score 0.0-1.0, evidence list)
        """
        from datetime import date, timedelta

        evidence: list[str] = []

        # Get choices for period
        start_date = date.today() - timedelta(days=period_days)
        choices_result = await self.backend.find_by(user_uid=user_uid)

        if choices_result.is_error or not choices_result.value:
            evidence.append("No choices found in analysis period")
            return DecisionQualityLevel.STRUGGLING, 0.0, evidence

        all_choices = choices_result.value
        # Filter to period (using created_at)
        period_choices = [
            c for c in all_choices if c.created_at and c.created_at.date() >= start_date
        ]

        if not period_choices:
            evidence.append(f"No choices created in last {period_days} days")
            return DecisionQualityLevel.STRUGGLING, 0.1, evidence

        total_choices = len(period_choices)
        evidence.append(f"{total_choices} choices in period")

        # Calculate decision rate (decided vs pending)
        decided = [c for c in period_choices if c.selected_option_uid is not None]
        decision_rate = len(decided) / total_choices if total_choices > 0 else 0.0
        evidence.append(f"Decision rate: {decision_rate:.0%}")

        # Calculate outcome quality (for choices with recorded satisfaction scores)
        # satisfaction_score is 1-5, normalize to 0-1
        choices_with_satisfaction = [c for c in decided if c.satisfaction_score is not None]
        avg_outcome_quality = 0.0
        if choices_with_satisfaction:
            avg_outcome_quality = sum(
                (c.satisfaction_score or 0) / 5.0 for c in choices_with_satisfaction
            ) / len(choices_with_satisfaction)
            evidence.append(f"Average outcome quality: {avg_outcome_quality:.0%}")

        # Calculate principle alignment via relationships
        principle_aligned_count = 0
        if self.relationships:
            for choice in decided[:10]:  # Sample first 10 for efficiency
                rel_result = await self.relationships.get_related_uids(
                    choice.uid,
                    RelationshipName.ALIGNED_WITH_PRINCIPLE.value,
                    "outgoing",
                )
                if rel_result.is_ok and rel_result.value:
                    principle_aligned_count += 1

        principle_rate = principle_aligned_count / min(len(decided), 10) if decided else 0.0
        if principle_aligned_count > 0:
            evidence.append(f"{principle_aligned_count} decisions aligned with principles")

        # Calculate quality calibration (decisions with good outcomes)
        calibration_score = 0.5  # Default neutral
        # Use satisfaction_score >= 4 as "good outcome" (4-5 on 1-5 scale)
        if choices_with_satisfaction:
            good_outcomes = [
                c
                for c in choices_with_satisfaction
                if c.satisfaction_score and c.satisfaction_score >= 4
            ]
            calibration_score = len(good_outcomes) / len(choices_with_satisfaction)
            evidence.append(f"Good outcome rate: {calibration_score:.0%}")

        # Weighted composite score
        # Outcome quality: 35%, Decision rate: 25%, Principle alignment: 25%, Calibration: 15%
        composite_score = (
            avg_outcome_quality * 0.35
            + decision_rate * 0.25
            + principle_rate * 0.25
            + calibration_score * 0.15
        )

        # Map to DecisionQualityLevel
        system_level = DecisionQualityLevel.from_score(composite_score)

        return system_level, composite_score, evidence

    @staticmethod
    def _decision_quality_level_to_score(level: DecisionQualityLevel) -> float:
        """Convert DecisionQualityLevel to numeric score."""
        return level.to_score()

    @staticmethod
    def _generate_choice_gap_insights(direction: str, gap: float, entity_name: str) -> list[str]:
        """Generate choice-specific insights based on perception gap."""
        insights: list[str] = []

        if direction == "aligned":
            insights.append("Your self-perception of decision quality matches measured outcomes.")
            insights.append(
                "This awareness helps you make appropriate decisions for each situation."
            )
        elif direction == "user_higher":
            insights.append(f"Self-assessment exceeds measured decision quality (gap: {gap:.0%}).")
            insights.append("Consider reviewing past decision outcomes more carefully.")
            if gap > 0.25:
                insights.append(
                    "Overconfidence in decision-making may lead to insufficient analysis."
                )
        else:  # system_higher
            insights.append(f"Your decision quality is better than you perceive (gap: {gap:.0%}).")
            insights.append("You may be too self-critical about your choices.")
            if gap > 0.25:
                insights.append("Your decisions have been leading to good outcomes!")

        return insights

    @staticmethod
    def _generate_choice_gap_recommendations(
        direction: str, _gap: float, _entity: Any, evidence: list[str]
    ) -> list[str]:
        """Generate choice-specific recommendations to close the gap."""
        recommendations: list[str] = []

        if direction == "user_higher":
            recommendations.append("Track decision outcomes more systematically.")
            recommendations.append("Align more decisions with your core principles.")
            recommendations.append("Take more time for complex decisions.")
            if any("outcome" in e.lower() for e in evidence):
                recommendations.append("Review outcomes of past decisions to learn from them.")
        elif direction == "system_higher":
            recommendations.append("Acknowledge your strong decision-making abilities.")
            recommendations.append("Trust your judgment on routine decisions.")
            recommendations.append("Build on this strength by tackling more impactful choices.")
        else:  # aligned
            recommendations.append("Maintain your current decision-making practices.")
            recommendations.append("Continue reviewing outcomes to stay calibrated.")

        return recommendations

    # =========================================================================
    # PRINCIPLE-CHOICE INTEGRATION METHODS (January 2026)
    # =========================================================================

    async def analyze_principle_adherence(
        self,
        user_uid: str,
        period_days: int = 90,
    ) -> Result[dict[str, Any]]:
        """
        Analyze how well user's choices adhere to their principles.

        This method provides insight into the alignment between a user's
        stated principles and their actual decision-making behavior.

        Args:
            user_uid: User identifier
            period_days: Period to analyze (default 90 days)

        Returns:
            Result containing:
            - overall_adherence_score: float (0.0-1.0)
            - principle_breakdown: dict mapping principle_uid to adherence data
            - aligned_choices_count: int
            - unaligned_choices_count: int
            - most_aligned_principle: str | None
            - least_aligned_principle: str | None
            - recommendations: list[str]
        """
        # Query for choices with principle alignment in the period
        query = """
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(c:Ku {ku_type: 'choice'})
        WHERE c.created_at >= datetime() - duration({days: $period_days})

        OPTIONAL MATCH (c)-[:ALIGNED_WITH_PRINCIPLE]->(p:Ku {ku_type: 'principle'})

        WITH c,
             collect(DISTINCT p.uid) AS principle_uids,
             CASE WHEN count(p) > 0 THEN 1 ELSE 0 END AS is_aligned

        RETURN
            count(c) AS total_choices,
            sum(is_aligned) AS aligned_count,
            collect({
                choice_uid: c.uid,
                principles: principle_uids,
                satisfaction: c.satisfaction_score
            }) AS choice_details
        """

        result = await self.backend.execute_query(
            query,
            {"user_uid": user_uid, "period_days": period_days},
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        if not result.value:
            return Result.ok(
                {
                    "overall_adherence_score": 0.0,
                    "principle_breakdown": {},
                    "aligned_choices_count": 0,
                    "unaligned_choices_count": 0,
                    "most_aligned_principle": None,
                    "least_aligned_principle": None,
                    "recommendations": ["No choices found - start tracking decisions"],
                }
            )

        record = result.value[0]
        total_choices = record.get("total_choices", 0)
        aligned_count = record.get("aligned_count", 0)
        choice_details = record.get("choice_details", [])

        if total_choices == 0:
            return Result.ok(
                {
                    "overall_adherence_score": 0.0,
                    "principle_breakdown": {},
                    "aligned_choices_count": 0,
                    "unaligned_choices_count": 0,
                    "most_aligned_principle": None,
                    "least_aligned_principle": None,
                    "recommendations": ["No choices found - start tracking decisions"],
                }
            )

        # Calculate overall adherence score
        overall_score = aligned_count / total_choices

        # Build principle breakdown
        def _empty_principle_entry() -> dict[str, Any]:
            return {"aligned_count": 0, "choice_uids": [], "avg_satisfaction": 0.0}

        principle_breakdown: dict[str, dict[str, Any]] = defaultdict(_empty_principle_entry)
        satisfaction_sums: dict[str, float] = defaultdict(float)

        for detail in choice_details:
            for p_uid in detail.get("principles", []):
                if p_uid:
                    principle_breakdown[p_uid]["aligned_count"] += 1
                    principle_breakdown[p_uid]["choice_uids"].append(detail["choice_uid"])
                    if detail.get("satisfaction"):
                        satisfaction_sums[p_uid] += detail["satisfaction"]

        # Calculate average satisfaction per principle
        for p_uid, data in principle_breakdown.items():
            count = data["aligned_count"]
            if count > 0 and satisfaction_sums.get(p_uid):
                data["avg_satisfaction"] = (
                    satisfaction_sums[p_uid] / count / 5.0
                )  # Normalize to 0-1

        # Find most/least aligned principles
        most_aligned = None
        least_aligned = None
        if principle_breakdown:
            sorted_principles = sorted(
                principle_breakdown.items(),
                key=get_aligned_count,
                reverse=True,
            )
            most_aligned = sorted_principles[0][0]
            if len(sorted_principles) > 1:
                least_aligned = sorted_principles[-1][0]

        # Generate recommendations
        recommendations: list[str] = []
        if overall_score < 0.3:
            recommendations.append("Consider linking more choices to your core principles")
        if aligned_count < total_choices - aligned_count:
            recommendations.append("Review unaligned choices - are they serving your values?")
        if most_aligned and principle_breakdown[most_aligned]["aligned_count"] > 5:
            recommendations.append("Strong alignment with principle - continue building on this")
        if overall_score >= 0.7:
            recommendations.append(
                "Excellent principle adherence - your decisions reflect your values"
            )

        return Result.ok(
            {
                "overall_adherence_score": round(overall_score, 3),
                "principle_breakdown": dict(principle_breakdown),
                "aligned_choices_count": aligned_count,
                "unaligned_choices_count": total_choices - aligned_count,
                "most_aligned_principle": most_aligned,
                "least_aligned_principle": least_aligned,
                "recommendations": recommendations,
            }
        )

    async def detect_principle_choice_conflicts(
        self,
        choice_uid: str,
        user_uid: str,
    ) -> Result[dict[str, Any]]:
        """
        Detect conflicts between a choice and user's principles.

        Analyzes:
        1. Direct conflicts - choice explicitly conflicts with a principle
        2. Implicit conflicts - choice options may violate principles
        3. Missing alignment - important decisions without principle guidance

        Args:
            choice_uid: Choice identifier
            user_uid: User identifier

        Returns:
            Result containing:
            - has_conflicts: bool
            - direct_conflicts: list of conflicting principles with severity
            - unaligned_warning: bool (True if important choice lacks principle alignment)
            - mitigation_strategies: list of resolution approaches
        """
        # Query for choice and its principle relationships
        query = """
        MATCH (c:Ku {uid: $choice_uid, ku_type: 'choice'})

        // Get aligned principles
        OPTIONAL MATCH (c)-[:ALIGNED_WITH_PRINCIPLE]->(aligned:Ku {ku_type: 'principle'})

        // Get any conflicting principles
        OPTIONAL MATCH (c)-[:CONFLICTS_WITH_PRINCIPLE]->(conflicting:Ku {ku_type: 'principle'})

        // Get user's core principles for comparison
        OPTIONAL MATCH (u:User {uid: $user_uid})-[:OWNS]->(core:Ku {ku_type: 'principle'})
        WHERE core.strength IN ['CORE', 'STRONG']

        RETURN
            c.uid AS choice_uid,
            c.title AS choice_title,
            c.impact_level AS impact_level,
            collect(DISTINCT aligned.uid) AS aligned_uids,
            collect(DISTINCT {
                uid: conflicting.uid,
                name: conflicting.name
            }) AS conflicts,
            collect(DISTINCT core.uid) AS core_principle_uids
        """

        result = await self.backend.execute_query(
            query,
            {"choice_uid": choice_uid, "user_uid": user_uid},
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        if not result.value:
            return Result.fail(Errors.not_found(resource="Choice", identifier=choice_uid))

        record = result.value[0]
        aligned_uids = [u for u in record.get("aligned_uids", []) if u]
        conflicts = [c for c in record.get("conflicts", []) if c.get("uid")]
        core_principle_uids = [u for u in record.get("core_principle_uids", []) if u]
        impact_level = record.get("impact_level", "low")

        # Determine if unaligned warning applies
        # High-impact choices should be aligned with at least one principle
        unaligned_warning = (
            impact_level in ["high", "critical"]
            and len(aligned_uids) == 0
            and len(core_principle_uids) > 0
        )

        # Build direct conflicts list
        direct_conflicts = [
            {
                "principle_uid": c["uid"],
                "principle_name": c.get("name", "Unknown"),
                "conflict_reason": "Choice explicitly conflicts with stated principle",
                "severity": "high",
            }
            for c in conflicts
        ]

        # Generate mitigation strategies
        mitigation_strategies: list[str] = []
        if direct_conflicts:
            mitigation_strategies.append("Review choice alignment with conflicting principles")
            mitigation_strategies.append(
                "Consider alternative approaches that honor all principles"
            )
            mitigation_strategies.append("Discuss trade-offs with a trusted advisor")
        if unaligned_warning:
            mitigation_strategies.append(
                "Link this high-impact choice to relevant principles for better guidance"
            )
            mitigation_strategies.append(
                "Consider which core principles should inform this decision"
            )

        return Result.ok(
            {
                "has_conflicts": len(direct_conflicts) > 0,
                "direct_conflicts": direct_conflicts,
                "unaligned_warning": unaligned_warning,
                "aligned_principle_count": len(aligned_uids),
                "mitigation_strategies": mitigation_strategies,
            }
        )

    async def predict_decision_quality(
        self,
        choice_uid: str,
        user_uid: str,
    ) -> Result[dict[str, Any]]:
        """
        Predict decision quality based on principle alignment and historical patterns.

        Uses a 4-factor model:
        1. Principle alignment (35%) - Is the choice guided by principles?
        2. Knowledge-informed (25%) - Is the choice informed by knowledge?
        3. Historical correlation (25%) - Past aligned choices vs satisfaction
        4. Complexity-guidance ratio (15%) - Guidance relative to complexity

        Args:
            choice_uid: Choice identifier
            user_uid: User identifier

        Returns:
            Result containing:
            - predicted_quality_score: float (0.0-1.0)
            - confidence: float (0.0-1.0)
            - quality_factors: breakdown by factor
            - historical_correlation: float
            - recommendations: list[str]
        """
        from core.services.choices.choice_relationships import ChoiceRelationships

        # Get choice
        choice_result = await self.backend.get(choice_uid)
        if choice_result.is_error:
            return Result.fail(choice_result.expect_error())

        choice = choice_result.value
        if not choice:
            return Result.fail(Errors.not_found(resource="Choice", identifier=choice_uid))

        # Fetch relationships
        rels = await ChoiceRelationships.fetch(choice_uid, self.relationships)

        # Factor 1: Principle alignment (35% weight)
        principle_count = len(rels.aligned_principle_uids)
        if principle_count == 0:
            principle_factor = 0.0
        elif principle_count == 1:
            principle_factor = 0.25
        else:
            principle_factor = min(0.35, principle_count * 0.12)

        # Factor 2: Knowledge-informed (25% weight)
        knowledge_count = len(rels.informed_by_knowledge_uids)
        if knowledge_count == 0:
            knowledge_factor = 0.0
        else:
            knowledge_factor = min(0.25, knowledge_count * 0.08)

        # Factor 3: Historical correlation (25% weight)
        # Query past decisions with similar patterns
        historical_query = """
        MATCH (u:User {uid: $user_uid})-[:OWNS]->(c:Ku {ku_type: 'choice'})
        WHERE c.satisfaction_score IS NOT NULL
        OPTIONAL MATCH (c)-[:ALIGNED_WITH_PRINCIPLE]->(p:Ku {ku_type: 'principle'})
        WITH c, count(p) AS principle_count
        RETURN
            avg(CASE WHEN principle_count > 0 THEN c.satisfaction_score ELSE null END) AS aligned_avg,
            avg(CASE WHEN principle_count = 0 THEN c.satisfaction_score ELSE null END) AS unaligned_avg,
            count(c) AS total_choices
        """

        hist_result = await self.backend.execute_query(
            historical_query,
            {"user_uid": user_uid},
        )

        historical_factor = 0.125  # Default neutral
        historical_correlation = 0.0
        if hist_result.is_ok and hist_result.value:
            record = hist_result.value[0]
            aligned_avg = record.get("aligned_avg") or 3.0
            unaligned_avg = record.get("unaligned_avg") or 3.0
            total_choices = record.get("total_choices", 0)

            if total_choices >= 5:  # Need enough data
                # Calculate correlation (positive if aligned choices have better satisfaction)
                correlation = (aligned_avg - unaligned_avg) / 5.0
                historical_correlation = correlation

                if rels.is_principle_aligned() and aligned_avg > unaligned_avg:
                    historical_factor = 0.25
                elif not rels.is_principle_aligned() and unaligned_avg > aligned_avg:
                    historical_factor = 0.20
                else:
                    historical_factor = 0.125

        # Factor 4: Complexity-guidance ratio (15% weight)
        # Choice model always has calculate_decision_complexity method
        complexity = choice.calculate_decision_complexity()
        guidance_strength = principle_count * 0.2 + knowledge_count * 0.1
        if complexity > 0:
            complexity_factor = 0.15 * min(1.0, guidance_strength / complexity)
        else:
            complexity_factor = 0.15 * min(1.0, guidance_strength)

        # Calculate predicted score
        predicted_score = (
            principle_factor + knowledge_factor + historical_factor + complexity_factor
        )
        predicted_score = min(1.0, max(0.0, predicted_score))

        # Calculate confidence based on data availability
        confidence = 0.5  # Base confidence
        if (
            hist_result.is_ok
            and hist_result.value
            and hist_result.value[0].get("total_choices", 0) >= 10
        ):
            confidence += 0.2
        if rels.is_principle_aligned():
            confidence += 0.15
        if rels.is_informed_decision():
            confidence += 0.15
        confidence = min(1.0, confidence)

        # Generate recommendations
        recommendations: list[str] = []
        if not rels.is_principle_aligned():
            recommendations.append("Link this choice to relevant principles for better outcomes")
        if not rels.is_informed_decision():
            recommendations.append("Consider researching more before deciding")
        if complexity > 0.7 and principle_count < 2:
            recommendations.append("Complex decision - ensure multiple principles guide you")
        if predicted_score >= 0.7:
            recommendations.append("Good decision foundation - proceed with confidence")

        return Result.ok(
            {
                "predicted_quality_score": round(predicted_score, 3),
                "confidence": round(confidence, 3),
                "quality_factors": {
                    "principle_alignment": round(principle_factor, 3),
                    "knowledge_informed": round(knowledge_factor, 3),
                    "historical_pattern": round(historical_factor, 3),
                    "complexity_guidance": round(complexity_factor, 3),
                },
                "historical_correlation": round(historical_correlation, 3),
                "recommendations": recommendations,
            }
        )

    async def calculate_life_path_contribution_via_principles(
        self,
        choice_uid: str,
        user_uid: str,
    ) -> Result[dict[str, Any]]:
        """
        Calculate how a choice contributes to life path via principle alignment.

        Graph traversal: Choice -> Principle -> LifePath

        This method traces the contribution chain from a specific choice
        through aligned principles to the user's ultimate life path.

        Args:
            choice_uid: Choice identifier
            user_uid: User identifier

        Returns:
            Result containing:
            - total_contribution_score: float (0.0-1.0)
            - direct_contribution: float (if Choice -> LifePath exists)
            - principle_mediated_contribution: float (via Choice -> Principle -> LifePath)
            - contributing_principles: list with individual contributions
            - life_path_uid: str | None
            - life_path_title: str | None
        """
        # Query for life path contribution via principles
        query = """
        MATCH (c:Ku {uid: $choice_uid, ku_type: 'choice'})

        // Get user's life path
        OPTIONAL MATCH (u:User {uid: $user_uid})-[:ULTIMATE_PATH]->(lp:Ku {ku_type: 'learning_path'})

        // Direct contribution (if any)
        OPTIONAL MATCH (c)-[direct:SERVES_LIFE_PATH]->(lp)

        // Principle-mediated contribution
        OPTIONAL MATCH (c)-[:ALIGNED_WITH_PRINCIPLE]->(p:Ku {ku_type: 'principle'})
                       -[pserve:SERVES_LIFE_PATH]->(lp)

        RETURN
            lp.uid AS life_path_uid,
            lp.title AS life_path_title,
            direct.contribution_score AS direct_score,
            collect(DISTINCT {
                uid: p.uid,
                name: p.name,
                contribution: pserve.contribution_score
            }) AS principle_contributions
        """

        result = await self.backend.execute_query(
            query,
            {"choice_uid": choice_uid, "user_uid": user_uid},
        )

        if result.is_error:
            return Result.fail(result.expect_error())

        if not result.value:
            return Result.ok(
                {
                    "total_contribution_score": 0.0,
                    "direct_contribution": 0.0,
                    "principle_mediated_contribution": 0.0,
                    "contributing_principles": [],
                    "life_path_uid": None,
                    "life_path_title": None,
                    "message": "Choice not found or no life path defined",
                }
            )

        record = result.value[0]
        life_path_uid = record.get("life_path_uid")

        if not life_path_uid:
            return Result.ok(
                {
                    "total_contribution_score": 0.0,
                    "direct_contribution": 0.0,
                    "principle_mediated_contribution": 0.0,
                    "contributing_principles": [],
                    "life_path_uid": None,
                    "life_path_title": None,
                    "message": "No life path defined for user",
                }
            )

        direct_score = record.get("direct_score") or 0.0
        principle_contributions = record.get("principle_contributions", [])

        # Filter valid contributions (have both uid and contribution score)
        valid_contributions = [
            {
                "uid": p["uid"],
                "name": p.get("name", "Unknown"),
                "contribution": p["contribution"],
            }
            for p in principle_contributions
            if p.get("uid") and p.get("contribution")
        ]

        # Calculate principle-mediated contribution (average of contributions)
        principle_mediated = 0.0
        if valid_contributions:
            principle_mediated = sum(p["contribution"] for p in valid_contributions) / len(
                valid_contributions
            )

        # Total contribution: weighted combination
        # Direct contribution is weighted more (60%) if it exists
        # Principle-mediated fills in the remaining (40%) or full (100%) if no direct
        if direct_score > 0:
            total_score = (direct_score * 0.6) + (principle_mediated * 0.4)
        else:
            total_score = principle_mediated

        total_score = min(1.0, total_score)

        return Result.ok(
            {
                "total_contribution_score": round(total_score, 3),
                "direct_contribution": round(direct_score, 3),
                "principle_mediated_contribution": round(principle_mediated, 3),
                "contributing_principles": valid_contributions,
                "life_path_uid": life_path_uid,
                "life_path_title": record.get("life_path_title"),
            }
        )
