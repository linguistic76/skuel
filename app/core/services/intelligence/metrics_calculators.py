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
    from core.services.intelligence.cross_domain_contexts import (
        ChoiceCrossContext,
        EventCrossContext,
        FinanceCrossContext,
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
    - dependent_count: Number of dependent tasks
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
        "dependent_count": len(context.dependent_task_uids),
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
    - supporting_goal_count: Goals this choice supports
    - conflicting_goal_count: Goals this choice conflicts with
    - knowledge_grounding_count: Knowledge informing decision
    - has_conflicts: Boolean indicating goal conflicts
    - is_principled: Boolean if informed by principles
    - decision_clarity_score: How clear the decision is (0.0-1.0)

    Args:
        choice: ChoiceDTO or Choice entity
        context: ChoiceCrossContext with cross-domain relationships

    Returns:
        Dictionary of calculated metrics
    """
    # Decision clarity: high when grounded in principles/knowledge, low when conflicted
    clarity_factors = [
        context.is_principle_informed(),  # +0.33 if principled
        context.has_knowledge_base(),  # +0.33 if knowledge-grounded
        not context.has_conflicts(),  # +0.33 if no conflicts
    ]
    decision_clarity = sum(1 for f in clarity_factors if f) / len(clarity_factors)

    return {
        "principle_guidance_count": len(context.informing_principle_uids),
        "supporting_goal_count": len(context.supporting_goal_uids),
        "conflicting_goal_count": len(context.conflicting_goal_uids),
        "knowledge_grounding_count": len(context.required_knowledge_uids),
        "total_goal_impact": len(context.all_goal_uids()),
        "has_conflicts": context.has_conflicts(),
        "is_principled": context.is_principle_informed(),
        "has_knowledge_base": context.has_knowledge_base(),
        "decision_clarity_score": round(decision_clarity, 2),
    }


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


def calculate_finance_metrics(expense: Any, context: FinanceCrossContext) -> dict[str, Any]:
    """
    Calculate standard metrics for finance/expense analysis.

    Metrics produced:
    - supporting_goal_count: Goals this expense supports
    - supporting_habit_count: Habits this expense enables
    - knowledge_investment_count: Learning investments
    - is_goal_aligned: Boolean if expense supports goals
    - is_learning_investment: Boolean if expense is educational
    - purpose_score: How purposeful the expense is (0.0-1.0)

    Args:
        expense: ExpenseDTO or Expense entity
        context: FinanceCrossContext with cross-domain relationships

    Returns:
        Dictionary of calculated metrics
    """
    # Purpose score: expenses tied to goals/habits/learning are more purposeful
    purpose_factors = [
        context.is_goal_supporting(),
        context.is_lifestyle_supporting(),
        context.is_learning_investment(),
    ]
    purpose_score = sum(1 for f in purpose_factors if f) / len(purpose_factors)

    return {
        "supporting_goal_count": len(context.supporting_goal_uids),
        "supporting_habit_count": len(context.supporting_habit_uids),
        "knowledge_investment_count": len(context.knowledge_investment_uids),
        "is_goal_aligned": context.is_goal_supporting(),
        "is_lifestyle_supporting": context.is_lifestyle_supporting(),
        "is_learning_investment": context.is_learning_investment(),
        "purpose_score": round(purpose_score, 2),
    }


def calculate_knowledge_metrics(ku: Any, context: KnowledgeCrossContext) -> dict[str, Any]:
    """
    Calculate standard metrics for knowledge unit analysis.

    Metrics produced:
    - prerequisite_count: Number of prerequisites
    - dependent_count: Number of dependents (who build on this)
    - application_count: Tasks applying this knowledge
    - learning_step_count: Learning steps teaching this
    - supported_goal_count: Goals this knowledge supports
    - is_foundational: Boolean if many dependents
    - is_applied: Boolean if being used in tasks
    - curriculum_integration_score: How integrated into learning paths

    Args:
        ku: KnowledgeUnitDTO or KnowledgeUnit entity
        context: KnowledgeCrossContext with cross-domain relationships

    Returns:
        Dictionary of calculated metrics
    """
    # Curriculum integration: in learning paths + has tasks applying it
    curriculum_factors = [
        context.is_curriculum_integrated(),
        context.is_applied(),
        bool(context.supported_goal_uids),
    ]
    curriculum_score = sum(1 for f in curriculum_factors if f) / len(curriculum_factors)

    return {
        "prerequisite_count": len(context.prerequisite_knowledge_uids),
        "dependent_count": len(context.dependent_knowledge_uids),
        "application_count": len(context.applying_task_uids),
        "learning_step_count": len(context.learning_step_uids),
        "supported_goal_count": len(context.supported_goal_uids),
        "has_prerequisites": context.has_prerequisites(),
        "is_foundational": context.is_foundational(),
        "is_applied": context.is_applied(),
        "is_curriculum_integrated": context.is_curriculum_integrated(),
        "curriculum_integration_score": round(curriculum_score, 2),
    }
