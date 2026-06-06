"""
Domain-Specific Metrics Calculators
===================================

Standard metrics calculators for cross-domain context analysis.

Each calculator takes an entity and its typed context, returning a dictionary
of metrics specific to that domain. These are plugged into
BaseAnalyticsService._analyze_entity_with_context() via the metrics_fn parameter.

Philosophy: "Metrics reveal the story of the entity in its context"

Usage:
    from core.services.intelligence.metrics_calculators import calculate_task_metrics

    result = await context_service.analyze_with_context(
        ...,
        metrics_fn=calculate_task_metrics,
    )
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.models.graph.path_aware_types import (
        ChoiceCrossContext as PathAwareChoiceCrossContext,
    )
    from core.services.intelligence.cross_domain_contexts import (
        ChoiceCrossContext,
        EventCrossContext,
        GoalCrossContext,
        HabitCrossContext,
        KnowledgeCrossContext,
        PrincipleCrossContext,
        TaskCrossContext,
    )


def calculate_task_metrics(task: Any, context: TaskCrossContext) -> dict[str, Any]:
    """
    Calculate standard metrics for task analysis.

    Metrics produced:
    - prerequisite_count: Number of prerequisite tasks
    - knowledge_coverage: Total knowledge connections
    - goal_support_count: Number of goals this task supports
    - principle_alignment_count: Number of aligned principles
    - has_dependencies: Boolean indicating if task has blockers
    - complexity_score: Estimated complexity (0.0-1.0)

    Args:
        task: TaskDTO or Task entity
        context: TaskCrossContext with cross-domain relationships

    Returns:
        Dictionary of calculated metrics
    """
    # Calculate complexity based on dependencies and knowledge requirements
    complexity_base = 0.3  # Base complexity

    # Add complexity for prerequisites
    prereq_factor = min(len(context.prerequisite_task_uids) * 0.1, 0.3)

    # Add complexity for knowledge requirements
    knowledge_factor = min(context.total_knowledge_count() * 0.05, 0.2)

    # Add complexity for goal alignment (more goals = more considerations)
    goal_factor = min(len(context.contributing_goal_uids) * 0.05, 0.2)

    complexity_score = min(complexity_base + prereq_factor + knowledge_factor + goal_factor, 1.0)

    return {
        "prerequisite_count": len(context.prerequisite_task_uids),
        "knowledge_coverage": context.total_knowledge_count(),
        "required_knowledge_count": len(context.required_knowledge_uids),
        "applied_knowledge_count": len(context.applied_knowledge_uids),
        "goal_support_count": len(context.contributing_goal_uids),
        "principle_alignment_count": len(context.aligned_principle_uids),
        "has_dependencies": context.has_dependencies(),
        "has_goal_support": context.has_goal_support(),
        "has_principle_alignment": context.has_principle_alignment(),
        "complexity_score": round(complexity_score, 2),
    }


def calculate_goal_metrics(goal: Any, context: GoalCrossContext) -> dict[str, Any]:
    """
    Calculate standard metrics for goal analysis.

    Metrics produced:
    - task_support_count: Number of tasks fulfilling this goal
    - habit_support_count: Number of supporting habits
    - knowledge_requirement_count: Knowledge units required
    - learning_path_count: Aligned learning paths
    - sub_goal_count: Number of sub-goals
    - support_coverage: How well-supported (0.0-1.0)
    - has_habit_system: Boolean for James Clear-style habit support

    Args:
        goal: GoalDTO or Goal entity
        context: GoalCrossContext with cross-domain relationships

    Returns:
        Dictionary of calculated metrics
    """
    return {
        "task_support_count": len(context.supporting_task_uids),
        "habit_support_count": len(context.supporting_habit_uids),
        "knowledge_requirement_count": len(context.required_knowledge_uids),
        "learning_path_count": len(context.learning_path_uids),
        "sub_goal_count": len(context.sub_goal_uids),
        "principle_guidance_count": len(context.guiding_principle_uids),
        "support_coverage": round(context.support_coverage(), 2),
        "total_support_count": context.total_support_count(),
        "has_habit_system": context.has_system_support(),
        "has_curriculum_alignment": context.has_curriculum_alignment(),
        "is_well_supported": context.support_coverage() >= 0.67,  # At least 2/3 dimensions
    }


def calculate_habit_metrics(habit: Any, context: HabitCrossContext) -> dict[str, Any]:
    """
    Calculate standard metrics for habit analysis.

    Metrics produced:
    - goal_support_count: Number of goals this habit supports
    - knowledge_reinforcement_count: Knowledge units reinforced
    - principle_alignment_count: Aligned principles
    - has_goal_connection: Boolean for goal linkage
    - is_knowledge_builder: Boolean for knowledge reinforcement

    Args:
        habit: HabitDTO or Habit entity
        context: HabitCrossContext with cross-domain relationships

    Returns:
        Dictionary of calculated metrics
    """
    # Calculate integration score - how well integrated into life system
    integration_factors = [
        context.is_goal_connected(),
        context.is_knowledge_builder(),
        context.is_principle_aligned(),
    ]
    integration_score = sum(1 for f in integration_factors if f) / len(integration_factors)

    return {
        "goal_support_count": len(context.linked_goal_uids),
        "knowledge_reinforcement_count": len(context.knowledge_reinforcement_uids),
        "principle_alignment_count": len(context.aligned_principle_uids),
        "prerequisite_habit_count": len(context.prerequisite_habit_uids),
        "has_goal_connection": context.is_goal_connected(),
        "is_knowledge_builder": context.is_knowledge_builder(),
        "is_principle_aligned": context.is_principle_aligned(),
        "has_prerequisites": context.has_prerequisites(),
        "integration_score": round(integration_score, 2),
    }


def calculate_event_metrics(event: Any, context: EventCrossContext) -> dict[str, Any]:
    """
    Calculate standard metrics for event analysis.

    Metrics produced:
    - goal_support_count: Goals this event supports
    - habit_reinforcement_count: Habits this event reinforces
    - knowledge_practice_count: Knowledge practiced in event
    - has_purpose: Boolean if event has clear purpose (goals or habits)
    - is_learning_event: Boolean if event involves knowledge practice

    Args:
        event: EventDTO or Event entity
        context: EventCrossContext with cross-domain relationships

    Returns:
        Dictionary of calculated metrics
    """
    has_purpose = context.has_goal_support() or context.has_habit_reinforcement()

    return {
        "goal_support_count": len(context.supporting_goal_uids),
        "habit_reinforcement_count": len(context.reinforcing_habit_uids),
        "knowledge_practice_count": len(context.practicing_knowledge_uids),
        "total_connections": context.total_connections(),
        "has_goal_support": context.has_goal_support(),
        "has_habit_reinforcement": context.has_habit_reinforcement(),
        "has_learning_component": context.has_learning_component(),
        "has_purpose": has_purpose,
        "is_learning_event": context.has_learning_component(),
    }


def calculate_choice_metrics(choice: Any, context: ChoiceCrossContext) -> dict[str, Any]:
    """
    Calculate standard metrics for choice/decision analysis.

    Metrics produced:
    - principle_guidance_count: Principles informing this choice
    - affected_goal_count: Goals this choice affects
    - knowledge_grounding_count: Knowledge informing decision
    - affects_goals: Boolean indicating goal impact
    - is_principled: Boolean if informed by principles
    - decision_clarity_score: How clear the decision is (0.0-1.0)

    Args:
        choice: ChoiceDTO or Choice entity
        context: ChoiceCrossContext with cross-domain relationships

    Returns:
        Dictionary of calculated metrics
    """
    # Decision clarity: high when grounded in principles AND knowledge. (The former
    # "no goal conflicts" factor is gone — the graph has no conflicting-goal edge; the
    # choice↔goal link is the polarity-free AFFECTS_GOAL.)
    clarity_factors = [
        context.is_principle_informed(),  # +0.5 if principled
        context.has_knowledge_base(),  # +0.5 if knowledge-grounded
    ]
    decision_clarity = sum(1 for f in clarity_factors if f) / len(clarity_factors)

    return {
        "principle_guidance_count": len(context.informing_principle_uids),
        "affected_goal_count": len(context.affected_goal_uids),
        "knowledge_grounding_count": len(context.required_knowledge_uids),
        "affects_goals": context.affects_goals(),
        "is_principled": context.is_principle_informed(),
        "has_knowledge_base": context.has_knowledge_base(),
        "decision_clarity_score": round(decision_clarity, 2),
    }


# ---------------------------------------------------------------------------
# Choices — path-aware lenses over the CANONICAL typed reader
# (get_cross_domain_context_typed → path_aware_types.ChoiceCrossContext).
# These power analyze_choice_impact / get_decision_intelligence via
# BaseAnalyticsService._analyze_entity_with_typed_context. They return plain
# nested dicts; the choices mixin transcribes them into the frozen result types
# (ChoiceImpactAnalysis / DecisionIntelligence).
# ---------------------------------------------------------------------------


def _choice_severity(count: int) -> str:
    """Per-domain impact severity band by affected count."""
    if count > 5:
        return "high"
    if count > 2:
        return "medium"
    if count > 0:
        return "low"
    return "none"


def calculate_choice_impact_metrics(
    choice: Any, context: PathAwareChoiceCrossContext
) -> dict[str, Any]:
    """Impact lens: blast radius, per-domain severity, risk, cascade, path-aware counts.

    Tasks/habits are not part of the choice cross-domain context, so they are always
    empty; goals come from AFFECTS_GOAL (polarity-free → all in ``supporting_goals``),
    principles from the INFORMED_BY_PRINCIPLE / GUIDES_CHOICE union, knowledge from
    INFORMED_BY_KNOWLEDGE. ``total_entities_affected`` excludes knowledge (count of
    goals+tasks+habits+principles), matching the established contract.
    """
    from core.services.intelligence.path_aware_analyzer import PathAwareAnalyzer

    affected_goals = context.all_goals
    affected_principles = context.principles
    knowledge = context.knowledge
    affected_tasks: list[Any] = []  # not in choice cross-domain context
    affected_habits: list[Any] = []

    total_affected = (
        len(affected_goals) + len(affected_tasks) + len(affected_habits) + len(affected_principles)
    )
    domains_affected: list[str] = []
    if affected_goals:
        domains_affected.append("goals")
    if affected_tasks:
        domains_affected.append("tasks")
    if affected_habits:
        domains_affected.append("habits")
    if affected_principles:
        domains_affected.append("principles")

    impact_score = min(
        10.0,
        (
            len(affected_goals) * 2.5
            + len(affected_habits) * 2.0
            + len(affected_tasks) * 1.0
            + len(affected_principles) * 3.0
        ),
    )

    risk_level = "low"
    risk_factors: list[str] = []
    if len(affected_principles) > 0:
        risk_level = "high"
        risk_factors.append(f"May affect {len(affected_principles)} core principles")
    if len(affected_goals) > 3:
        if risk_level != "high":
            risk_level = "medium"
        risk_factors.append(f"Impacts {len(affected_goals)} goals")
    if impact_score > 7.0:
        risk_level = "high"
        risk_factors.append("High overall impact score")

    mitigation: list[str] = []
    if risk_level == "high":
        mitigation.append("Carefully evaluate alignment with principles")
        mitigation.append("Consider phased implementation")
    if len(affected_goals) > 0:
        mitigation.append("Track impact on goal progress")
    if len(affected_habits) > 0:
        mitigation.append("Plan for habit adjustments")

    cascade = PathAwareAnalyzer.calculate_cascade_impact(
        goals=affected_goals, knowledge=knowledge, principles=affected_principles
    )

    return {
        "impact_summary": {
            "total_entities_affected": total_affected,
            "domains_affected": domains_affected,
            "impact_score": impact_score,
        },
        "domain_impact": {
            "goals": {
                "affected": affected_goals,
                "count": len(affected_goals),
                "severity": _choice_severity(len(affected_goals)),
            },
            "tasks": {
                "affected": affected_tasks,
                "count": len(affected_tasks),
                "severity": _choice_severity(len(affected_tasks)),
            },
            "habits": {
                "affected": affected_habits,
                "count": len(affected_habits),
                "severity": _choice_severity(len(affected_habits)),
            },
            "principles": {
                "affected": affected_principles,
                "count": len(affected_principles),
                "severity": _choice_severity(len(affected_principles)),
            },
        },
        "risk_assessment": {
            "risk_level": risk_level,
            "risk_factors": risk_factors,
            "mitigation_suggestions": mitigation,
        },
        "cascade_impact": cascade,
        "path_aware_context": {
            "total_strong_connections": context.strong_connections(),
            "direct_connections_count": len(context.direct_goals) + len(context.direct_principles),
            "max_path_depth": max((e.distance for e in context.all_goals), default=0),
            "avg_path_strength": context.avg_strength(),
        },
    }


def choice_impact_recommendations(
    choice: Any, context: PathAwareChoiceCrossContext, metrics: dict[str, Any]
) -> list[str]:
    """Opportunities for analyze_choice_impact: inline opportunity rules + path-strength
    recommendations (the analyzer's ``opportunities`` list)."""
    from core.services.intelligence.path_aware_analyzer import PathAwareAnalyzer

    goals = context.all_goals
    habits: list[Any] = []
    principles = context.principles
    knowledge = context.knowledge

    opportunities: list[str] = []
    if len(goals) > 2:
        opportunities.append("Opportunity to accelerate multiple goals simultaneously")
    if len(habits) > 0:
        opportunities.append("Opportunity to strengthen habit consistency")
    if len(principles) > 0:
        opportunities.append("Opportunity to live more aligned with principles")
    opportunities.extend(
        PathAwareAnalyzer.generate_recommendations(
            goals=goals, knowledge=knowledge, principles=principles
        )
    )
    return opportunities


def calculate_decision_metrics(choice: Any, context: PathAwareChoiceCrossContext) -> dict[str, Any]:
    """Decision-readiness lens: complexity (model-derived), confidence_needed, stake_level,
    what to consult, plus the cascade/path-aware context shared with the impact lens."""
    from core.services.intelligence.path_aware_analyzer import PathAwareAnalyzer

    related_goals = context.all_goals
    guiding_principles = context.principles
    required_knowledge = context.knowledge
    affected_tasks: list[Any] = []
    affected_habits: list[Any] = []
    affected_goals = related_goals

    complexity = choice.calculate_decision_complexity()
    confidence_needed = "medium"
    if complexity > 7.0:
        confidence_needed = "high"
    elif complexity < 3.0:
        confidence_needed = "low"

    total_impact = len(affected_tasks) + len(affected_goals) + len(affected_habits)
    stake_level = "medium"
    if total_impact > 10:
        stake_level = "high"
    elif total_impact < 3:
        stake_level = "low"

    consider_impact_on: list[str] = []
    if affected_goals:
        consider_impact_on.append("goal progress")
    if affected_habits:
        consider_impact_on.append("habit consistency")
    if affected_tasks:
        consider_impact_on.append("task completion")

    cascade = PathAwareAnalyzer.calculate_cascade_impact(
        goals=related_goals, knowledge=required_knowledge, principles=guiding_principles
    )

    return {
        "context": {
            "goals": related_goals,
            "principles": guiding_principles,
            "knowledge": required_knowledge,
        },
        "impact": {"tasks": affected_tasks, "goals": affected_goals, "habits": affected_habits},
        "decision_analysis": {
            "complexity": complexity,
            "confidence_needed": confidence_needed,
            "stake_level": stake_level,
        },
        "gather_more_info": complexity > 6.0 and len(required_knowledge) > 0,
        "consult_principles": [p.title for p in guiding_principles],
        "consider_impact_on": consider_impact_on,
        "cascade_impact": cascade,
        "path_aware_context": {
            "total_strong_connections": context.strong_connections(),
            "direct_connections_count": len(context.direct_goals) + len(context.direct_principles),
            "max_path_depth": max((e.distance for e in context.all_goals), default=0),
            "avg_path_strength": context.avg_strength(),
        },
    }


def decision_improvement_opportunities(
    choice: Any, context: PathAwareChoiceCrossContext, metrics: dict[str, Any]
) -> list[str]:
    """Improvement opportunities for get_decision_intelligence (path-strength recommendations)."""
    from core.services.intelligence.path_aware_analyzer import PathAwareAnalyzer

    return PathAwareAnalyzer.generate_recommendations(
        goals=context.all_goals, knowledge=context.knowledge, principles=context.principles
    )


def calculate_principle_metrics(principle: Any, context: PrincipleCrossContext) -> dict[str, Any]:
    """
    Calculate standard metrics for principle analysis.

    Metrics produced:
    - guided_goal_count: Goals guided by this principle
    - informed_choice_count: Choices informed by this principle
    - aligned_habit_count: Habits aligned with this principle
    - knowledge_grounding_count: Knowledge grounding this principle
    - influence_score: How broadly it influences (0.0-1.0)
    - is_lived: Boolean if actively guiding behavior

    Args:
        principle: PrincipleDTO or Principle entity
        context: PrincipleCrossContext with cross-domain relationships

    Returns:
        Dictionary of calculated metrics
    """
    # A principle is "lived" if it guides at least one goal or habit
    is_lived = context.is_action_guiding()

    return {
        "guided_goal_count": len(context.guided_goal_uids),
        "informed_choice_count": len(context.informed_choice_uids),
        "aligned_habit_count": len(context.aligned_habit_uids),
        "knowledge_grounding_count": len(context.grounding_knowledge_uids),
        "total_influence_count": context.total_influence_count(),
        "influence_score": round(context.influence_score(), 2),
        "is_action_guiding": context.is_action_guiding(),
        "is_knowledge_grounded": context.is_knowledge_grounded(),
        "is_lived": is_lived,
    }


def calculate_knowledge_metrics(ku: Any, context: KnowledgeCrossContext) -> dict[str, Any]:
    """
    Calculate standard metrics for knowledge unit (Ku) analysis.

    Metrics produced:
    - path_step_count: Learning steps that compose/train this Ku
    - is_curriculum_integrated: Boolean if taught by any learning step

    A Ku's cross-domain reach is its composing PathSteps (KU_CONFIG traverses only
    USES_KU/TRAINS_KU); application, goal-support, and prerequisite chains live at the
    PathStep curriculum layer rather than on the atomic Ku, so they are not surfaced here.

    Args:
        ku: KuDTO or Ku entity
        context: KnowledgeCrossContext with cross-domain relationships

    Returns:
        Dictionary of calculated metrics
    """
    return {
        "path_step_count": len(context.path_step_uids),
        "is_curriculum_integrated": context.is_curriculum_integrated(),
    }
