"""
Cross-Domain Context Dataclasses
================================

Typed containers for cross-domain context data.

These dataclasses provide type-safe extraction from untyped context dictionaries
returned by relationship services, enabling:
- IDE autocomplete for field access
- Compile-time type checking
- Consistent metrics calculation helpers

Note: These are distinct from path_aware_types.py which contains PathAware* types
with distance/strength metadata for graph traversal. These contexts store UIDs
for cross-domain relationship queries.

Philosophy: "Type safety where it matters - at the boundary between layers"
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TaskCrossContext:
    """
    Typed cross-domain context for tasks.

    Contains UIDs of related entities across domains:
    - prerequisite_task_uids: Tasks that must be completed first
    - dependent_task_uids: Tasks that depend on this task
    - required_knowledge_uids: Knowledge needed to complete task
    - applied_knowledge_uids: Knowledge this task applies/practices
    - contributing_goal_uids: Goals this task fulfills
    - aligned_principle_uids: Principles this task aligns with

    Usage:
        context_dict = await relationships.get_task_cross_domain_context(uid)
        context = TaskCrossContext.from_dict(context_dict)
        if context.has_dependencies():
            print(f"Task has {len(context.prerequisite_task_uids)} prerequisites")
    """

    prerequisite_task_uids: list[str] = field(default_factory=list)
    dependent_task_uids: list[str] = field(default_factory=list)
    required_knowledge_uids: list[str] = field(default_factory=list)
    applied_knowledge_uids: list[str] = field(default_factory=list)
    contributing_goal_uids: list[str] = field(default_factory=list)
    aligned_principle_uids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, context_dict: dict[str, Any]) -> TaskCrossContext:
        """Extract typed context from untyped dict."""
        return cls(
            prerequisite_task_uids=context_dict.get("prerequisite_tasks", []),
            dependent_task_uids=context_dict.get("dependent_tasks", []),
            required_knowledge_uids=context_dict.get("required_knowledge", []),
            applied_knowledge_uids=context_dict.get("applied_knowledge", []),
            contributing_goal_uids=context_dict.get("goals", []),
            aligned_principle_uids=context_dict.get("principles", []),
        )

    def total_knowledge_count(self) -> int:
        """Total knowledge connections (required + applied)."""
        return len(self.required_knowledge_uids) + len(self.applied_knowledge_uids)

    def has_dependencies(self) -> bool:
        """Check if task has any dependencies (prerequisite tasks or required knowledge)."""
        return bool(self.prerequisite_task_uids or self.required_knowledge_uids)

    def has_goal_support(self) -> bool:
        """Check if task supports any goals."""
        return bool(self.contributing_goal_uids)

    def has_principle_alignment(self) -> bool:
        """Check if task aligns with any principles."""
        return bool(self.aligned_principle_uids)


@dataclass(frozen=True)
class GoalCrossContext:
    """
    Typed cross-domain context for goals.

    Contains UIDs of related entities:
    - supporting_task_uids: Tasks that fulfill this goal
    - supporting_habit_uids: Habits that support this goal
    - required_knowledge_uids: Knowledge required for goal achievement
    - learning_path_uids: Learning paths aligned with this goal
    - sub_goal_uids: Child goals (goal hierarchy)
    - guiding_principle_uids: Principles guiding this goal

    Usage:
        context = GoalCrossContext.from_dict(context_dict)
        coverage = context.support_coverage()  # 0.0 - 1.0
    """

    supporting_task_uids: list[str] = field(default_factory=list)
    supporting_habit_uids: list[str] = field(default_factory=list)
    required_knowledge_uids: list[str] = field(default_factory=list)
    learning_path_uids: list[str] = field(default_factory=list)
    sub_goal_uids: list[str] = field(default_factory=list)
    guiding_principle_uids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, context_dict: dict[str, Any]) -> GoalCrossContext:
        """Extract typed context from untyped dict."""
        return cls(
            supporting_task_uids=context_dict.get("tasks", []),
            supporting_habit_uids=context_dict.get("habits", []),
            required_knowledge_uids=context_dict.get("knowledge", []),
            learning_path_uids=context_dict.get("learning_paths", []),
            sub_goal_uids=context_dict.get("sub_goals", []),
            guiding_principle_uids=context_dict.get("principles", []),
        )

    def support_coverage(self) -> float:
        """
        Calculate how well-supported the goal is (0.0-1.0).

        Three dimensions of support:
        - Tasks (execution)
        - Habits (sustained behavior)
        - Knowledge (capability)
        """
        has_tasks = bool(self.supporting_task_uids)
        has_habits = bool(self.supporting_habit_uids)
        has_knowledge = bool(self.required_knowledge_uids)
        return sum([has_tasks, has_habits, has_knowledge]) / 3.0

    def has_system_support(self) -> bool:
        """Check if goal has habit system support (James Clear style)."""
        return bool(self.supporting_habit_uids)

    def has_curriculum_alignment(self) -> bool:
        """Check if goal has learning path alignment."""
        return bool(self.learning_path_uids)

    def total_support_count(self) -> int:
        """Total count of supporting elements (tasks + habits)."""
        return len(self.supporting_task_uids) + len(self.supporting_habit_uids)


@dataclass(frozen=True)
class HabitCrossContext:
    """
    Typed cross-domain context for habits.

    Contains UIDs of related entities:
    - linked_goal_uids: Goals this habit supports
    - knowledge_reinforcement_uids: Knowledge this habit reinforces
    - aligned_principle_uids: Principles this habit aligns with
    - prerequisite_habit_uids: Habits that should be established first

    Usage:
        context = HabitCrossContext.from_dict(context_dict)
        if context.is_knowledge_builder():
            print("This habit reinforces learning")
    """

    linked_goal_uids: list[str] = field(default_factory=list)
    knowledge_reinforcement_uids: list[str] = field(default_factory=list)
    aligned_principle_uids: list[str] = field(default_factory=list)
    prerequisite_habit_uids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, context_dict: dict[str, Any]) -> HabitCrossContext:
        """Extract typed context from untyped dict."""
        return cls(
            linked_goal_uids=context_dict.get("goals", []),
            knowledge_reinforcement_uids=context_dict.get("knowledge", []),
            aligned_principle_uids=context_dict.get("principles", []),
            prerequisite_habit_uids=context_dict.get("prerequisite_habits", []),
        )

    def is_goal_connected(self) -> bool:
        """Check if habit supports any goals."""
        return bool(self.linked_goal_uids)

    def is_knowledge_builder(self) -> bool:
        """Check if habit reinforces knowledge/skills."""
        return bool(self.knowledge_reinforcement_uids)

    def is_principle_aligned(self) -> bool:
        """Check if habit aligns with principles."""
        return bool(self.aligned_principle_uids)

    def has_prerequisites(self) -> bool:
        """Check if habit has prerequisite habits."""
        return bool(self.prerequisite_habit_uids)


@dataclass(frozen=True)
class EventCrossContext:
    """
    Typed cross-domain context for events.

    Contains UIDs of related entities:
    - supporting_goal_uids: Goals this event supports
    - reinforcing_habit_uids: Habits this event reinforces
    - practicing_knowledge_uids: Knowledge practiced in this event

    Usage:
        context = EventCrossContext.from_dict(context_dict)
        if context.has_learning_component():
            print("This event involves learning")
    """

    supporting_goal_uids: list[str] = field(default_factory=list)
    reinforcing_habit_uids: list[str] = field(default_factory=list)
    practicing_knowledge_uids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, context_dict: dict[str, Any]) -> EventCrossContext:
        """Extract typed context from untyped dict."""
        return cls(
            supporting_goal_uids=context_dict.get("goals", []),
            reinforcing_habit_uids=context_dict.get("habits", []),
            practicing_knowledge_uids=context_dict.get("knowledge", []),
        )

    def has_goal_support(self) -> bool:
        """Check if event supports any goals."""
        return bool(self.supporting_goal_uids)

    def has_learning_component(self) -> bool:
        """Check if event involves knowledge practice."""
        return bool(self.practicing_knowledge_uids)

    def has_habit_reinforcement(self) -> bool:
        """Check if event reinforces habits."""
        return bool(self.reinforcing_habit_uids)

    def total_connections(self) -> int:
        """Total count of cross-domain connections."""
        return (
            len(self.supporting_goal_uids)
            + len(self.reinforcing_habit_uids)
            + len(self.practicing_knowledge_uids)
        )


@dataclass(frozen=True)
class ChoiceCrossContext:
    """
    Typed cross-domain context for choices (decisions).

    Contains UIDs of related entities:
    - informing_principle_uids: Principles that inform this choice
    - supporting_goal_uids: Goals this choice supports
    - conflicting_goal_uids: Goals this choice may conflict with
    - required_knowledge_uids: Knowledge needed for informed decision

    Usage:
        context = ChoiceCrossContext.from_dict(context_dict)
        if context.has_conflicts():
            print("Warning: choice has goal conflicts")
    """

    informing_principle_uids: list[str] = field(default_factory=list)
    supporting_goal_uids: list[str] = field(default_factory=list)
    conflicting_goal_uids: list[str] = field(default_factory=list)
    required_knowledge_uids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, context_dict: dict[str, Any]) -> ChoiceCrossContext:
        """Extract typed context from untyped dict."""
        return cls(
            informing_principle_uids=context_dict.get("principles", []),
            supporting_goal_uids=context_dict.get("supporting_goals", []),
            conflicting_goal_uids=context_dict.get("conflicting_goals", []),
            required_knowledge_uids=context_dict.get("knowledge", []),
        )

    def is_principle_informed(self) -> bool:
        """Check if choice is informed by principles."""
        return bool(self.informing_principle_uids)

    def has_conflicts(self) -> bool:
        """Check if choice has any goal conflicts."""
        return bool(self.conflicting_goal_uids)

    def has_knowledge_base(self) -> bool:
        """Check if choice has knowledge grounding."""
        return bool(self.required_knowledge_uids)

    def all_goal_uids(self) -> list[str]:
        """All goals (supporting + conflicting)."""
        return self.supporting_goal_uids + self.conflicting_goal_uids


@dataclass(frozen=True)
class PrincipleCrossContext:
    """
    Typed cross-domain context for principles.

    Contains UIDs of related entities:
    - guided_goal_uids: Goals guided by this principle
    - informed_choice_uids: Choices informed by this principle
    - grounding_knowledge_uids: Knowledge this principle is grounded in
    - aligned_habit_uids: Habits aligned with this principle

    Usage:
        context = PrincipleCrossContext.from_dict(context_dict)
        influence = context.influence_score()  # How broadly it influences behavior
    """

    guided_goal_uids: list[str] = field(default_factory=list)
    informed_choice_uids: list[str] = field(default_factory=list)
    grounding_knowledge_uids: list[str] = field(default_factory=list)
    aligned_habit_uids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, context_dict: dict[str, Any]) -> PrincipleCrossContext:
        """Extract typed context from untyped dict."""
        return cls(
            guided_goal_uids=context_dict.get("goals", []),
            informed_choice_uids=context_dict.get("choices", []),
            grounding_knowledge_uids=context_dict.get("knowledge", []),
            aligned_habit_uids=context_dict.get("habits", []),
        )

    # Alias properties for simpler access patterns
    @property
    def goal_uids(self) -> list[str]:
        """Alias for guided_goal_uids."""
        return self.guided_goal_uids

    @property
    def choice_uids(self) -> list[str]:
        """Alias for informed_choice_uids."""
        return self.informed_choice_uids

    @property
    def habit_uids(self) -> list[str]:
        """Alias for aligned_habit_uids."""
        return self.aligned_habit_uids

    def is_action_guiding(self) -> bool:
        """Check if principle guides goals or habits."""
        return bool(self.guided_goal_uids or self.aligned_habit_uids)

    def is_knowledge_grounded(self) -> bool:
        """Check if principle is grounded in knowledge."""
        return bool(self.grounding_knowledge_uids)

    def influence_score(self) -> float:
        """
        Calculate principle's influence breadth (0.0-1.0).

        Four dimensions of influence:
        - Goals (direction)
        - Choices (decisions)
        - Habits (behavior)
        - Knowledge (grounding)
        """
        has_goals = bool(self.guided_goal_uids)
        has_choices = bool(self.informed_choice_uids)
        has_habits = bool(self.aligned_habit_uids)
        has_knowledge = bool(self.grounding_knowledge_uids)
        return sum([has_goals, has_choices, has_habits, has_knowledge]) / 4.0

    def total_influence_count(self) -> int:
        """Total count of influenced elements (goals + habits + choices)."""
        return (
            len(self.guided_goal_uids)
            + len(self.aligned_habit_uids)
            + len(self.informed_choice_uids)
        )


@dataclass(frozen=True)
class FinanceCrossContext:
    """
    Typed cross-domain context for finance/expenses.

    Contains UIDs of related entities:
    - supporting_goal_uids: Goals this expense supports
    - supporting_habit_uids: Habits this expense enables
    - knowledge_investment_uids: Knowledge investments (courses, books)

    Usage:
        context = FinanceCrossContext.from_dict(context_dict)
        if context.is_learning_investment():
            print("This is a learning investment")
    """

    supporting_goal_uids: list[str] = field(default_factory=list)
    supporting_habit_uids: list[str] = field(default_factory=list)
    knowledge_investment_uids: list[str] = field(default_factory=list)
    supporting_task_uids: list[str] = field(default_factory=list)

    # Alias properties for simpler access patterns
    @property
    def goal_uids(self) -> list[str]:
        """Alias for supporting_goal_uids."""
        return self.supporting_goal_uids

    @property
    def task_uids(self) -> list[str]:
        """Alias for supporting_task_uids."""
        return self.supporting_task_uids

    @property
    def knowledge_uids(self) -> list[str]:
        """Alias for knowledge_investment_uids."""
        return self.knowledge_investment_uids

    @classmethod
    def from_dict(cls, context_dict: dict[str, Any]) -> FinanceCrossContext:
        """Extract typed context from untyped dict."""
        return cls(
            supporting_goal_uids=context_dict.get("goals", []),
            supporting_habit_uids=context_dict.get("habits", []),
            knowledge_investment_uids=context_dict.get("knowledge_investments", []),
            supporting_task_uids=context_dict.get("tasks", []),
        )

    def is_goal_supporting(self) -> bool:
        """Check if expense supports goals."""
        return bool(self.supporting_goal_uids)

    def is_learning_investment(self) -> bool:
        """Check if expense is a learning investment."""
        return bool(self.knowledge_investment_uids)

    def is_lifestyle_supporting(self) -> bool:
        """Check if expense supports habits/lifestyle."""
        return bool(self.supporting_habit_uids)


@dataclass(frozen=True)
class KnowledgeCrossContext:
    """
    Typed cross-domain context for knowledge units.

    Contains UIDs of related entities:
    - prerequisite_knowledge_uids: Knowledge required before this
    - dependent_knowledge_uids: Knowledge that builds on this
    - applying_task_uids: Tasks that apply this knowledge
    - learning_step_uids: Learning steps that teach this
    - supported_goal_uids: Goals this knowledge supports

    Usage:
        context = KnowledgeCrossContext.from_dict(context_dict)
        if context.is_foundational():
            print("This is foundational knowledge with many dependents")
    """

    prerequisite_knowledge_uids: list[str] = field(default_factory=list)
    dependent_knowledge_uids: list[str] = field(default_factory=list)
    applying_task_uids: list[str] = field(default_factory=list)
    learning_step_uids: list[str] = field(default_factory=list)
    supported_goal_uids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, context_dict: dict[str, Any]) -> KnowledgeCrossContext:
        """Extract typed context from untyped dict."""
        return cls(
            prerequisite_knowledge_uids=context_dict.get("prerequisites", []),
            dependent_knowledge_uids=context_dict.get("dependents", []),
            applying_task_uids=context_dict.get("tasks", []),
            learning_step_uids=context_dict.get("learning_steps", []),
            supported_goal_uids=context_dict.get("goals", []),
        )

    def has_prerequisites(self) -> bool:
        """Check if knowledge has prerequisites."""
        return bool(self.prerequisite_knowledge_uids)

    def is_foundational(self) -> bool:
        """Check if knowledge is foundational (has dependents)."""
        return len(self.dependent_knowledge_uids) > 2

    def is_applied(self) -> bool:
        """Check if knowledge is being applied in tasks."""
        return bool(self.applying_task_uids)

    def is_curriculum_integrated(self) -> bool:
        """Check if knowledge is part of learning paths."""
        return bool(self.learning_step_uids)


# Type alias for union of all context types
CrossDomainContext = (
    TaskCrossContext
    | GoalCrossContext
    | HabitCrossContext
    | EventCrossContext
    | ChoiceCrossContext
    | PrincipleCrossContext
    | FinanceCrossContext
    | KnowledgeCrossContext
)
