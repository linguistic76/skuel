"""
Domain-Specific Metrics Calculators
===================================

Standard metrics calculators for cross-domain context analysis.

Each calculator takes an entity and its path-aware typed context, returning a
dictionary of metrics specific to that domain. These are plugged into
``BaseAnalyticsService._analyze_entity_with_typed_context()`` via the ``metrics_fn``
parameter, sourced from the canonical typed reader
``UnifiedRelationshipService.get_cross_domain_context_typed`` (path_aware_types).

Philosophy: "Metrics reveal the story of the entity in its context"

Usage:
    from core.services.intelligence.metrics_calculators import (
        calculate_task_cross_domain_metrics,
    )

    result = await self._analyze_entity_with_typed_context(
        uid,
        metrics_fn=calculate_task_cross_domain_metrics,
    )
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.models.graph.path_aware_types import (
        ChoiceCrossContext as PathAwareChoiceCrossContext,
    )
    from core.models.graph.path_aware_types import (
        EventCrossContext as PathAwareEventCrossContext,
    )
    from core.models.graph.path_aware_types import (
        GoalCrossContext as PathAwareGoalCrossContext,
    )
    from core.models.graph.path_aware_types import (
        HabitCrossContext as PathAwareHabitCrossContext,
    )
    from core.models.graph.path_aware_types import (
        PrincipleCrossContext as PathAwarePrincipleCrossContext,
    )
    from core.models.graph.path_aware_types import (
        TaskCrossContext as PathAwareTaskCrossContext,
    )


# ---------------------------------------------------------------------------
# Tasks — path-aware lens over the CANONICAL typed reader
# (get_cross_domain_context_typed → path_aware_types.TaskCrossContext).
# Powers the cross-domain block composed into get_domain_insights
# (GET /api/tasks/insights) via BaseAnalyticsService._analyze_entity_with_typed_context,
# ALONGSIDE Task's distinctive graph-intel readiness block (knowledge_prerequisites).
# Scope is cross-domain ONLY: required/applied knowledge + contributing goals.
# Same-domain task→task dependencies live in the lateral-relationships system, not here.
# This is the "unify + elevate" lens — it does NOT replace the readiness capability,
# it sits beside it.
# ---------------------------------------------------------------------------


def calculate_task_cross_domain_metrics(
    task: Any, context: PathAwareTaskCrossContext
) -> dict[str, Any]:
    """Cross-domain lens over the path-aware task context: how the task connects to the
    knowledge it requires/applies and the goals it contributes to, plus a cascade-impact
    block and a path-aware rollup.

    Scope is cross-domain only (knowledge + goals); same-domain task→task dependencies are
    NOT part of this context. Surfaces the path-aware knowledge/goal lists so consumers can
    read UIDs directly off path-aware entities, and ADDS ``cascade_impact`` (via
    :meth:`PathAwareAnalyzer.calculate_cascade_impact`) and ``path_aware_context``
    (distance/strength rollups).
    """
    from core.services.intelligence.path_aware_analyzer import PathAwareAnalyzer

    required_knowledge = context.required_knowledge
    applied_knowledge = context.applied_knowledge
    contributing_goals = context.contributing_goals
    all_knowledge = required_knowledge + applied_knowledge

    has_required_knowledge = bool(required_knowledge)
    has_applied_knowledge = bool(applied_knowledge)
    has_goal_support = bool(contributing_goals)

    # Cascade counts ALL cross-domain fields consistently: goals + all knowledge
    # (required + applied), matching the rollups below.
    cascade = PathAwareAnalyzer.calculate_cascade_impact(
        goals=contributing_goals, knowledge=all_knowledge
    )

    return {
        # Flat metric keys derived from path-aware entities.
        "required_knowledge_count": len(required_knowledge),
        "applied_knowledge_count": len(applied_knowledge),
        "knowledge_coverage": len(all_knowledge),
        "goal_support_count": len(contributing_goals),
        "has_required_knowledge": has_required_knowledge,
        "has_applied_knowledge": has_applied_knowledge,
        "has_goal_support": has_goal_support,
        # Path-aware entity lists so the consumer reads UIDs off path-aware entities.
        "required_knowledge": required_knowledge,
        "applied_knowledge": applied_knowledge,
        "contributing_goals": contributing_goals,
        # Rich path-aware additions.
        "cascade_impact": cascade,
        "path_aware_context": {
            "total_strong_connections": context.strong_connections(),
            "direct_connections_count": (
                len(context.direct_knowledge)
                + len(context.direct_applied_knowledge)
                + len(context.direct_goals)
            ),
            "max_path_depth": context.max_path_depth,
            "avg_path_strength": context.avg_strength(),
        },
    }


def task_recommendations(
    task: Any, context: PathAwareTaskCrossContext, metrics: dict[str, Any]
) -> list[str]:
    """Path-aware recommendations for the task cross-domain lens: inline connection nudges
    plus the analyzer's path-strength recommendations (weak/missing-direct/deep-cascade)."""
    from core.services.intelligence.path_aware_analyzer import PathAwareAnalyzer

    required_knowledge = context.required_knowledge
    applied_knowledge = context.applied_knowledge
    contributing_goals = context.contributing_goals
    all_knowledge = required_knowledge + applied_knowledge

    recommendations: list[str] = []
    if not contributing_goals:
        recommendations.append("Connect this task to at least one goal it contributes to")
    if not all_knowledge:
        recommendations.append("Link this task to the knowledge it requires or applies")
    recommendations.extend(
        PathAwareAnalyzer.generate_recommendations(
            goals=contributing_goals, knowledge=all_knowledge
        )
    )
    return recommendations


# ---------------------------------------------------------------------------
# Habits — path-aware lens over the CANONICAL typed reader
# (get_cross_domain_context_typed → path_aware_types.HabitCrossContext).
# Powers analyze_habit_performance / get_habit_knowledge_reinforcement /
# get_habit_goal_support via BaseAnalyticsService._analyze_entity_with_typed_context.
# Preserves the flat metric keys the habits behavioral-signals mixin reads
# (has_goal_connection / is_knowledge_builder / is_principle_aligned /
# goal_support_count / knowledge_reinforcement_count / prerequisite_habit_count /
# integration_score) and ADDS the rich cascade_impact / path_aware_context blocks.
# ---------------------------------------------------------------------------


def calculate_habit_integration_metrics(
    habit: Any, context: PathAwareHabitCrossContext
) -> dict[str, Any]:
    """Integration lens over the path-aware habit context: how well the habit is woven into
    goals/knowledge/principles, plus a cascade-impact block and a path-aware rollup.

    Emits the flat habit-integration keys the behavioral-signals mixin's payload contract
    reads (so that contract holds), derived from path-aware entities, and
    ADDS ``cascade_impact`` (via :meth:`PathAwareAnalyzer.calculate_cascade_impact`) and
    ``path_aware_context`` (distance/strength rollups). Knowledge/goal/principle/prerequisite
    lists are also surfaced so consumers can read UIDs directly off path-aware entities.
    """
    from core.services.intelligence.path_aware_analyzer import PathAwareAnalyzer

    goals = context.goals
    knowledge = context.knowledge
    principles = context.principles
    prerequisites = context.prerequisites

    has_goal_connection = bool(goals)
    is_knowledge_builder = bool(knowledge)
    is_principle_aligned = bool(principles)

    integration_factors = [has_goal_connection, is_knowledge_builder, is_principle_aligned]
    integration_score = sum(1 for f in integration_factors if f) / len(integration_factors)

    cascade = PathAwareAnalyzer.calculate_cascade_impact(
        goals=goals, knowledge=knowledge, principles=principles, habits=prerequisites
    )

    return {
        # Flat keys preserved for the behavioral-signals payload contract.
        "goal_support_count": len(goals),
        "knowledge_reinforcement_count": len(knowledge),
        "principle_alignment_count": len(principles),
        "prerequisite_habit_count": len(prerequisites),
        "has_goal_connection": has_goal_connection,
        "is_knowledge_builder": is_knowledge_builder,
        "is_principle_aligned": is_principle_aligned,
        "has_prerequisites": bool(prerequisites),
        "integration_score": round(integration_score, 2),
        # Rich path-aware additions.
        "cascade_impact": cascade,
        "path_aware_context": {
            "total_strong_connections": context.strong_connections(),
            "direct_connections_count": (
                len(context.direct_goals)
                + len(context.direct_principles)
                + len(context.direct_knowledge)
                + len(context.direct_prerequisites)
            ),
            "max_path_depth": context.max_path_depth,
            "avg_path_strength": context.avg_strength(),
        },
    }


def habit_recommendations(
    habit: Any, context: PathAwareHabitCrossContext, metrics: dict[str, Any]
) -> list[str]:
    """Path-aware recommendations for the habit lens: inline integration nudges plus the
    analyzer's path-strength recommendations (weak/missing-direct/deep-cascade)."""
    from core.services.intelligence.path_aware_analyzer import PathAwareAnalyzer

    goals = context.goals
    knowledge = context.knowledge
    principles = context.principles

    recommendations: list[str] = []
    if not goals:
        recommendations.append("Link this habit to at least one supporting goal")
    if not knowledge:
        recommendations.append("Connect this habit to knowledge areas for learning reinforcement")
    if not principles:
        recommendations.append("Align this habit with your core principles")
    recommendations.extend(
        PathAwareAnalyzer.generate_recommendations(
            goals=goals, knowledge=knowledge, principles=principles
        )
    )
    return recommendations


# ---------------------------------------------------------------------------
# Goals — path-aware lens over the CANONICAL typed reader
# (get_cross_domain_context_typed → path_aware_types.GoalCrossContext).
# Powers get_goal_progress_dashboard / get_goal_completion_forecast /
# get_goal_learning_requirements via
# BaseAnalyticsService._analyze_entity_with_typed_context.
# Preserves the flat metric keys the goals analytics mixin reads
# (task_support_count / habit_support_count / knowledge_requirement_count /
# learning_path_count / sub_goal_count / principle_guidance_count /
# support_coverage / total_support_count / has_habit_system /
# has_curriculum_alignment / is_well_supported) and ADDS the rich
# cascade_impact / path_aware_context blocks.
# ---------------------------------------------------------------------------


def calculate_goal_progress_metrics(
    goal: Any, context: PathAwareGoalCrossContext
) -> dict[str, Any]:
    """Progress/support lens over the path-aware goal context: how well-supported the goal
    is across tasks/habits/knowledge, plus a cascade-impact block and a path-aware rollup.

    Emits the flat goal-support keys the analytics mixin's payload contract reads (so that
    contract holds), derived from path-aware entities, and ADDS
    ``cascade_impact`` (via :meth:`PathAwareAnalyzer.calculate_cascade_impact`) and
    ``path_aware_context`` (distance/strength rollups).
    """
    from core.services.intelligence.path_aware_analyzer import PathAwareAnalyzer

    tasks = context.tasks
    habits = context.habits
    knowledge = context.knowledge
    subgoals = context.subgoals
    principles = context.principles
    learning_paths = context.learning_paths
    # Upward (parent) + downward (sub) goal links both count as goal connections —
    # keep cascade aligned with the path-aware rollups, which include parent_goal.
    related_goals = subgoals + ([context.parent_goal] if context.parent_goal else [])

    # support_coverage: three dimensions (tasks / habits / knowledge).
    support_dimensions = [bool(tasks), bool(habits), bool(knowledge)]
    support_coverage = sum(1 for d in support_dimensions if d) / 3.0

    has_habit_system = bool(habits)
    has_curriculum_alignment = bool(learning_paths)
    total_support_count = len(tasks) + len(habits)

    cascade = PathAwareAnalyzer.calculate_cascade_impact(
        goals=related_goals,
        tasks=tasks,
        habits=habits,
        knowledge=knowledge,
        principles=principles,
    )

    return {
        # Flat keys preserved for the analytics-mixin payload contract.
        "task_support_count": len(tasks),
        "habit_support_count": len(habits),
        "knowledge_requirement_count": len(knowledge),
        "learning_path_count": len(learning_paths),
        "sub_goal_count": len(subgoals),
        "principle_guidance_count": len(principles),
        "support_coverage": round(support_coverage, 2),
        "total_support_count": total_support_count,
        "has_habit_system": has_habit_system,
        "has_curriculum_alignment": has_curriculum_alignment,
        "is_well_supported": support_coverage >= 0.67,  # At least 2/3 dimensions
        # Rich path-aware additions.
        "cascade_impact": cascade,
        "path_aware_context": {
            "total_strong_connections": context.strong_connections(),
            "direct_connections_count": (
                len(context.direct_tasks)
                + len(context.direct_habits)
                + len(context.direct_knowledge)
                + len(context.direct_principles)
                + len(context.direct_learning_paths)
                + len([g for g in context.subgoals if g.distance == 1])
                + (1 if context.parent_goal and context.parent_goal.distance == 1 else 0)
            ),
            "max_path_depth": context.max_path_depth,
            "avg_path_strength": context.avg_strength(),
        },
    }


def goal_recommendations(
    goal: Any, context: PathAwareGoalCrossContext, metrics: dict[str, Any]
) -> list[str]:
    """Path-aware recommendations for the goal lens: inline support nudges plus the
    analyzer's path-strength recommendations (weak/missing-direct/deep-cascade)."""
    from core.services.intelligence.path_aware_analyzer import PathAwareAnalyzer

    tasks = context.tasks
    habits = context.habits
    knowledge = context.knowledge
    subgoals = context.subgoals
    principles = context.principles

    recommendations: list[str] = []
    if len(tasks) < 3:
        recommendations.append("Consider breaking down this goal into more specific tasks")
    if not habits:
        recommendations.append("Create habits to support consistent progress toward this goal")
    if not context.learning_paths and knowledge:
        recommendations.append("Develop learning paths for required knowledge areas")
    recommendations.extend(
        PathAwareAnalyzer.generate_recommendations(
            goals=subgoals, tasks=tasks, habits=habits, knowledge=knowledge, principles=principles
        )
    )
    return recommendations


def goal_learning_recommendations(
    goal: Any, context: PathAwareGoalCrossContext, metrics: dict[str, Any]
) -> list[str]:
    """Learning-specific recommendations for the goal *learning-requirements* lens —
    prerequisite-knowledge guidance, distinct from the progress lens's support nudges
    (``goal_recommendations``). Mirrors the pre-convergence learning callback so the
    ``get_goal_learning_requirements`` payload keeps its prerequisite semantics."""
    knowledge_gap_count = metrics.get("knowledge_requirement_count", 0)
    has_learning_paths = metrics.get("has_curriculum_alignment", False)

    recommendations: list[str] = []
    if knowledge_gap_count > 0:
        recommendations.append(
            f"Master {knowledge_gap_count} knowledge areas before starting this goal"
        )
        if not has_learning_paths:
            recommendations.append(
                "Create a learning path to systematically acquire required knowledge"
            )
    else:
        recommendations.append("You have sufficient knowledge to begin working on this goal")
        recommendations.append("Define required knowledge areas for better goal planning")
    return recommendations


# ---------------------------------------------------------------------------
# Events — path-aware lens over the CANONICAL typed reader
# (get_cross_domain_context_typed → path_aware_types.EventCrossContext).
# Powers analyze_event_performance / get_domain_insights via
# BaseAnalyticsService._analyze_entity_with_typed_context. Preserves the flat
# metric keys analyze_event_performance's payload is rebuilt from
# (goal_support_count / habit_reinforcement_count / knowledge_practice_count /
# has_goal_support / has_habit_reinforcement / has_learning_component) and ADDS
# the rich cascade_impact / path_aware_context blocks. The event payload surfaces
# NO recommendations list, so there is no event_recommendations callback.
# ---------------------------------------------------------------------------


def calculate_event_performance_metrics(
    event: Any, context: PathAwareEventCrossContext
) -> dict[str, Any]:
    """Performance lens over the path-aware event context: how the event supports goals,
    reinforces habits, and practices knowledge, plus a cascade-impact block and a
    path-aware rollup.

    Derives the flat keys that ``analyze_event_performance`` rebuilds its nested
    ``goal_support`` / ``habit_reinforcement`` / ``knowledge_reinforcement`` payload from
    (so the ``/api/events/insights`` contract holds), surfaces the path-aware goal/habit/
    knowledge lists so the mixin can read UIDs directly, and ADDS ``cascade_impact`` (via
    :meth:`PathAwareAnalyzer.calculate_cascade_impact`) and ``path_aware_context``.

    NB: per the EVENTS_CONFIG, CONTRIBUTES_TO_GOAL exposes only ``uid``/``title`` (no
    ``contribution_weight``), so the legacy goal-support term always weighed 1.0 — preserved
    here as a flat 1.0 per supported goal.
    """
    from core.services.intelligence.path_aware_analyzer import PathAwareAnalyzer

    goals = context.goals
    habits = context.habits
    knowledge = context.knowledge

    has_goal_support = bool(goals)
    has_habit_reinforcement = bool(habits)
    has_learning_component = bool(knowledge)

    cascade = PathAwareAnalyzer.calculate_cascade_impact(
        goals=goals, habits=habits, knowledge=knowledge
    )

    return {
        # Flat keys preserved for the analyze_event_performance payload contract.
        "goal_support_count": len(goals),
        "habit_reinforcement_count": len(habits),
        "knowledge_practice_count": len(knowledge),
        "total_connections": context.total_connections,
        "has_goal_support": has_goal_support,
        "has_habit_reinforcement": has_habit_reinforcement,
        "has_learning_component": has_learning_component,
        "has_purpose": has_goal_support or has_habit_reinforcement,
        "is_learning_event": has_learning_component,
        # Path-aware entity lists so the mixin reads UIDs off path-aware entities.
        "goals": goals,
        "habits": habits,
        "knowledge": knowledge,
        # Rich path-aware additions.
        "cascade_impact": cascade,
        "path_aware_context": {
            "total_strong_connections": context.strong_connections(),
            "direct_connections_count": (
                len(context.direct_goals)
                + len(context.direct_habits)
                + len(context.direct_knowledge)
            ),
            "max_path_depth": context.max_path_depth,
            "avg_path_strength": context.avg_strength(),
        },
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


# ---------------------------------------------------------------------------
# Principles — path-aware lens over the CANONICAL typed reader
# (get_cross_domain_context_typed → path_aware_types.PrincipleCrossContext).
# Powers assess_principle_alignment (GET /api/principles/insights) via
# BaseAnalyticsService._analyze_entity_with_typed_context.
# Emits the flat principle-influence keys (guided_goal_count / informed_choice_count /
# aligned_habit_count / knowledge_grounding_count / total_influence_count /
# influence_score / is_action_guiding / is_knowledge_grounded / is_lived) AND the keys
# the alignment consumer reads (adherence_score / goal_count / choice_count /
# habit_count / knowledge_count / needs_attention / strong_alignment /
# consistent_practice), then ADDS the rich cascade_impact / path_aware_context blocks.
# ---------------------------------------------------------------------------


def calculate_principle_alignment_metrics(
    principle: Any, context: PathAwarePrincipleCrossContext
) -> dict[str, Any]:
    """Alignment lens over the path-aware principle context: how broadly the principle
    influences goals/choices/habits/knowledge, plus a cascade-impact block and a
    path-aware rollup.

    Derives every metric from path-aware entities. Emits the flat principle-influence keys
    (so any reader of those holds) AND the
    alignment keys ``assess_principle_alignment`` / ``_generate_alignment_recommendations``
    read (``adherence_score`` / ``goal_count`` / ``choice_count`` / ``habit_count`` /
    ``knowledge_count`` / ``needs_attention`` / ``strong_alignment`` /
    ``consistent_practice``). ADDS ``cascade_impact`` (via
    :meth:`PathAwareAnalyzer.calculate_cascade_impact`) and ``path_aware_context``
    (distance/strength rollups).
    """
    from core.services.intelligence.path_aware_analyzer import PathAwareAnalyzer

    goals = context.goals
    choices = context.choices
    knowledge = context.knowledge
    habits = context.habits

    goal_count = len(goals)
    choice_count = len(choices)
    habit_count = len(habits)
    knowledge_count = len(knowledge)

    # influence breadth: four dimensions (goals / choices / habits / knowledge).
    influence_dimensions = [bool(goals), bool(choices), bool(habits), bool(knowledge)]
    influence_score = sum(1 for d in influence_dimensions if d) / 4.0

    # total influence = goals + habits + choices.
    total_influence_count = goal_count + habit_count + choice_count

    is_action_guiding = bool(goals or habits)
    is_knowledge_grounded = bool(knowledge)
    is_lived = is_action_guiding

    # Adherence reflects the principle's influence breadth (the Principle model carries
    # no stored adherence_score). Bands mirror the alignment-recommendation thresholds.
    adherence_score = influence_score
    needs_attention = adherence_score < 0.5
    strong_alignment = adherence_score >= 0.75
    consistent_practice = habit_count > 0

    cascade = PathAwareAnalyzer.calculate_cascade_impact(
        goals=goals, knowledge=knowledge, principles=[], habits=habits
    )

    return {
        # Flat principle-influence keys.
        "guided_goal_count": goal_count,
        "informed_choice_count": choice_count,
        "aligned_habit_count": habit_count,
        "knowledge_grounding_count": knowledge_count,
        "total_influence_count": total_influence_count,
        "influence_score": round(influence_score, 2),
        "is_action_guiding": is_action_guiding,
        "is_knowledge_grounded": is_knowledge_grounded,
        "is_lived": is_lived,
        # Alignment keys the assess_principle_alignment consumer reads.
        "adherence_score": round(adherence_score, 2),
        "goal_count": goal_count,
        "choice_count": choice_count,
        "habit_count": habit_count,
        "knowledge_count": knowledge_count,
        "needs_attention": needs_attention,
        "strong_alignment": strong_alignment,
        "consistent_practice": consistent_practice,
        # Rich path-aware additions.
        "cascade_impact": cascade,
        "path_aware_context": {
            "total_strong_connections": context.strong_connections(),
            "direct_connections_count": (
                len(context.direct_goals)
                + len(context.direct_choices)
                + len(context.direct_knowledge)
                + len(context.direct_habits)
            ),
            "max_path_depth": context.max_path_depth,
            "avg_path_strength": context.avg_strength(),
        },
    }


def principle_recommendations(
    principle: Any, context: PathAwarePrincipleCrossContext, metrics: dict[str, Any]
) -> list[str]:
    """Path-aware recommendations for the principle alignment lens: inline alignment
    nudges (mirroring the legacy ``_generate_alignment_recommendations`` thresholds) plus
    the analyzer's path-strength recommendations (weak/missing-direct/deep-cascade)."""
    from core.services.intelligence.path_aware_analyzer import PathAwareAnalyzer

    goals = context.goals
    knowledge = context.knowledge
    habits = context.habits

    adherence_score = metrics.get("adherence_score", 0.5)
    recommendations: list[str] = []
    if metrics.get("needs_attention", False):
        recommendations.append(
            f"Alignment score is low ({adherence_score:.0%}) - "
            "consider creating goals or habits that embody this principle"
        )
    if not goals:
        recommendations.append("Create at least one goal guided by this principle")
    if not habits:
        recommendations.append("Establish a daily or weekly habit that embodies this principle")
    if metrics.get("total_influence_count", 0) < 5:
        recommendations.append(
            "Increase activities aligned with this principle - consistency builds adherence"
        )
    if metrics.get("strong_alignment", False):
        recommendations.append("Excellent alignment! You're living this principle consistently")
    recommendations.extend(
        PathAwareAnalyzer.generate_recommendations(
            goals=goals, knowledge=knowledge, principles=[], habits=habits
        )
    )
    return recommendations


def principle_gap_insights(direction: str, gap: float, principle_name: str) -> list[str]:
    """Perception-gap insights for principle alignment.

    Shared by both alignment paths: the dual-track template callback
    (ADR-030, _AlignmentIntelligenceMixin) and the single-track
    PrinciplesAlignmentService.assess_with_user_input.
    """
    insights: list[str] = []

    if direction == "aligned":
        insights.append(
            f"Your self-perception of alignment with '{principle_name}' "
            "matches your recorded actions. This indicates healthy self-reflection."
        )
    elif direction == "user_higher":
        insights.append(
            f"Your self-assessment is more positive than your recorded actions suggest "
            f"(gap: {gap:.0%}). Consider: Are there activities expressing this principle "
            "that aren't tracked in SKUEL?"
        )
        if gap > 0.3:
            insights.append(
                "This significant gap may indicate a blind spot in self-perception, "
                "or opportunities to better live out this principle."
            )
    else:  # system_higher
        insights.append(
            f"Your actions show stronger alignment than you perceive (gap: {gap:.0%}). "
            "You may be undervaluing your consistency with this principle."
        )
        if gap > 0.3:
            insights.append(
                "Consider acknowledging your progress - self-recognition strengthens motivation."
            )

    return insights


def principle_gap_recommendations(
    direction: str, _gap: float, principle: Any, evidence: list[str]
) -> list[str]:
    """Perception-gap recommendations for principle alignment (both alignment paths).

    ``principle`` is typed Any to satisfy the dual-track template's generic
    callback signature; the isinstance guard narrows before touching
    Principle-specific fields.
    """
    from core.models.principle.principle import Principle

    recommendations: list[str] = []

    if direction == "aligned":
        recommendations.append("Continue your current approach - your self-awareness is accurate.")
        if isinstance(principle, Principle) and principle.expressions:
            recommendations.append(
                "Consider documenting new expressions of this principle as they arise."
            )
    elif direction == "user_higher":
        recommendations.append(
            "Review your goals and habits to ensure they explicitly connect to this principle."
        )
        if not evidence:
            recommendations.append(
                "Create at least one goal or habit that directly expresses this principle."
            )
        recommendations.append(
            "Track specific instances where you practice this principle over the next week."
        )
    else:  # system_higher
        recommendations.append(
            "Acknowledge the alignment you've already achieved through your actions."
        )
        if evidence:
            recommendations.append(
                f"Celebrate your progress: {len(evidence)} activities already express this principle."
            )
        recommendations.append(
            "Consider reflecting on why your self-perception doesn't match your positive actions."
        )

    return recommendations[:4]
