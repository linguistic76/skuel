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


def _uids(context_dict: dict[str, Any], *keys: str) -> list[str]:
    """Collect entity UIDs from one or more cross-domain context buckets.

    ``UnifiedRelationshipService.get_cross_domain_context()`` emits one bucket per
    config ``context_field_name`` (e.g. ``contributing_habits``, ``required_knowledge``),
    each a list of ``{"uid", "title", ...}`` dicts. A single typed field often
    aggregates several buckets — a goal's supporting habits span the
    ``contributing``/``essential``/``critical``/``optional`` SUPPORTS_GOAL tiers, and a
    principle's aligned habits span both INSPIRES_HABIT (outgoing) and EMBODIES_PRINCIPLE
    (incoming). UIDs are de-duplicated across buckets, order-preserving. Tolerant of the
    raw ``str`` form in case a producer hands back bare UIDs.
    """
    out: list[str] = []
    seen: set[str] = set()
    for key in keys:
        for entity in context_dict.get(key) or []:
            uid = entity.get("uid") if isinstance(entity, dict) else entity
            if uid and uid not in seen:
                seen.add(uid)
                out.append(uid)
    return out


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
        """Extract typed context from a get_cross_domain_context() response.

        Keys are the TASKS_CONFIG ``context_field_name`` buckets, NOT generic domain
        names. Prerequisite tasks are DEPENDS_ON (``dependencies``); dependent tasks are
        the incoming BLOCKED_BY (``dependents``); contributing goals span
        CONTRIBUTES_TO_GOAL (``contributing_goals``) and the single FULFILLS_GOAL
        (``goal_context``); aligned principles are ALIGNED_WITH_PRINCIPLE
        (``aligned_principles``); knowledge spans REQUIRES_KNOWLEDGE
        (``required_knowledge``) and APPLIES_KNOWLEDGE (``applied_knowledge``).
        """
        return cls(
            prerequisite_task_uids=_uids(context_dict, "dependencies"),
            dependent_task_uids=_uids(context_dict, "dependents"),
            required_knowledge_uids=_uids(context_dict, "required_knowledge"),
            applied_knowledge_uids=_uids(context_dict, "applied_knowledge"),
            contributing_goal_uids=_uids(context_dict, "contributing_goals", "goal_context"),
            aligned_principle_uids=_uids(context_dict, "aligned_principles"),
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
        """Extract typed context from a get_cross_domain_context() response.

        Keys are the GOAPS_CONFIG ``context_field_name`` buckets, NOT generic
        domain names — supporting habits span the four SUPPORTS_GOAL-incoming tiers
        and guiding principles span both the outgoing/incoming directions.
        """
        return cls(
            supporting_task_uids=_uids(context_dict, "contributing_tasks"),
            supporting_habit_uids=_uids(
                context_dict,
                "contributing_habits",
                "essential_habits",
                "critical_habits",
                "optional_habits",
            ),
            required_knowledge_uids=_uids(context_dict, "required_knowledge"),
            learning_path_uids=_uids(context_dict, "aligned_paths", "required_paths"),
            sub_goal_uids=_uids(context_dict, "sub_goals"),
            guiding_principle_uids=_uids(
                context_dict, "aligned_principles", "guiding_principles_incoming"
            ),
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
        """Extract typed context from a get_cross_domain_context() response.

        Keys are the HABITS_CONFIG ``context_field_name`` buckets. Aligned principles
        span BOTH directions — EMBODIES_PRINCIPLE (outgoing, ``embodied_principles``)
        and INSPIRES_HABIT (incoming, ``inspiring_principles``) — mirroring the
        symmetric aggregation on ``PrincipleCrossContext.aligned_habit_uids``. The
        incoming bucket populates now that ``get_cross_domain_context()`` traverses
        both directions and categorizes per-mapping ``direction`` (it was structurally
        empty under the former outgoing-only traversal).

        The other now-live incoming habit buckets (``reinforcing_habits``,
        ``enabling_habits``, ``reinforcing_events``, ``reinforcing_tasks``,
        ``impacting_choices``) are intentionally NOT surfaced as typed fields — no
        metric or dashboard consumes them. They remain in the raw response dict for any
        future consumer; promote them here only when something reads them.
        """
        return cls(
            linked_goal_uids=_uids(context_dict, "supported_goals"),
            knowledge_reinforcement_uids=_uids(context_dict, "reinforced_knowledge"),
            aligned_principle_uids=_uids(
                context_dict, "embodied_principles", "inspiring_principles"
            ),
            prerequisite_habit_uids=_uids(context_dict, "prerequisite_habits"),
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
        """Extract typed context from a get_cross_domain_context() response.

        Keys are the EVENTS_CONFIG ``context_field_name`` buckets, NOT generic domain
        names. Supporting goals span CONTRIBUTES_TO_GOAL (``supported_goals``) and the
        milestone CELEBRATES_GOAL (``celebrated_goals``); reinforcing habits span the
        outgoing REINFORCES_HABIT (``reinforced_habits``) and the incoming
        PRACTICED_AT_EVENT (``practiced_habits``); practiced knowledge is
        APPLIES_KNOWLEDGE (``applied_knowledge``).
        """
        return cls(
            supporting_goal_uids=_uids(context_dict, "supported_goals", "celebrated_goals"),
            reinforcing_habit_uids=_uids(context_dict, "reinforced_habits", "practiced_habits"),
            practicing_knowledge_uids=_uids(context_dict, "applied_knowledge"),
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
    - informing_principle_uids: Principles that inform/guide this choice
    - affected_goal_uids: Goals this choice affects
    - required_knowledge_uids: Knowledge informing the decision

    Note: there is no supporting-vs-conflicting goal split. The choice↔goal
    relationship is a single, polarity-free ``AFFECTS_GOAL`` edge (config bucket
    ``affected_goals``); the former ``conflicting_goal_uids`` field had no graph
    source — nothing writes a "conflicting goal" edge — so it was dropped rather than
    wired to an edge nobody emits. Add it back only alongside a real edge (or an
    ``AFFECTS_GOAL`` polarity property) that something writes.

    Usage:
        context = ChoiceCrossContext.from_dict(context_dict)
        if context.affects_goals():
            print(f"Choice affects {len(context.affected_goal_uids)} goals")
    """

    informing_principle_uids: list[str] = field(default_factory=list)
    affected_goal_uids: list[str] = field(default_factory=list)
    required_knowledge_uids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, context_dict: dict[str, Any]) -> ChoiceCrossContext:
        """Extract typed context from a get_cross_domain_context() response.

        Keys are the CHOICES_CONFIG ``context_field_name`` buckets, NOT generic domain
        names. Informing principles span both directions — INFORMED_BY_PRINCIPLE
        (outgoing, ``aligned_principles``) and GUIDES_CHOICE (incoming,
        ``guiding_principles``); goals come from the single AFFECTS_GOAL edge
        (``affected_goals``); knowledge from INFORMED_BY_KNOWLEDGE
        (``informed_by_knowledge``).
        """
        return cls(
            informing_principle_uids=_uids(
                context_dict, "aligned_principles", "guiding_principles"
            ),
            affected_goal_uids=_uids(context_dict, "affected_goals"),
            required_knowledge_uids=_uids(context_dict, "informed_by_knowledge"),
        )

    def is_principle_informed(self) -> bool:
        """Check if choice is informed by principles."""
        return bool(self.informing_principle_uids)

    def affects_goals(self) -> bool:
        """Check if choice affects any goals."""
        return bool(self.affected_goal_uids)

    def has_knowledge_base(self) -> bool:
        """Check if choice has knowledge grounding."""
        return bool(self.required_knowledge_uids)


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
        """Extract typed context from a get_cross_domain_context() response.

        Keys are the PRINCIPLES_CONFIG ``context_field_name`` buckets; aligned habits
        span INSPIRES_HABIT (outgoing) and EMBODIES_PRINCIPLE (incoming).
        """
        return cls(
            guided_goal_uids=_uids(context_dict, "guided_goals"),
            informed_choice_uids=_uids(context_dict, "guided_choices"),
            grounding_knowledge_uids=_uids(context_dict, "grounding_knowledge"),
            aligned_habit_uids=_uids(context_dict, "inspired_habits", "embodying_habits"),
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
class KnowledgeCrossContext:
    """
    Typed cross-domain context for knowledge units (Kus).

    Contains UIDs of related entities:
    - path_step_uids: PathSteps that compose (USES_KU) or train (TRAINS_KU) this Ku

    Note: a Ku is the atomic ontology node, so its only cross-domain reach is the
    curriculum layer. In the graph, Activity domains (Task/Goal/Habit/Choice) attach
    their knowledge edges to PathSteps (``entity_type='path_step'``), NEVER to a ``:Ku``,
    and KU_CONFIG traverses only USES_KU/TRAINS_KU. The former
    ``prerequisite_knowledge``/``dependent_knowledge``/``applying_task``/
    ``supported_goal`` fields read generic keys KU_CONFIG never emits and had no usable
    config source, so they were dropped rather than wired to edges nothing surfaces.
    Ku↔Ku PREREQUISITE_FOR edges do exist but sit outside KU_CONFIG's traversal — restore
    prerequisite/dependent fields only alongside the matching KU_CONFIG mappings.

    Usage:
        context = KnowledgeCrossContext.from_dict(context_dict)
        if context.is_curriculum_integrated():
            print("This Ku is taught by learning steps")
    """

    path_step_uids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, context_dict: dict[str, Any]) -> KnowledgeCrossContext:
        """Extract typed context from a get_cross_domain_context() response.

        Keys are the KU_CONFIG ``context_field_name`` buckets — PathSteps that compose
        (USES_KU, ``used_by_steps``) or train (TRAINS_KU, ``trained_by_steps``) this Ku.
        """
        return cls(
            path_step_uids=_uids(context_dict, "used_by_steps", "trained_by_steps"),
        )

    def is_curriculum_integrated(self) -> bool:
        """Check if knowledge is taught by any learning step."""
        return bool(self.path_step_uids)


# Type alias for union of all context types
CrossDomainContext = (
    TaskCrossContext
    | GoalCrossContext
    | HabitCrossContext
    | EventCrossContext
    | ChoiceCrossContext
    | PrincipleCrossContext
    | KnowledgeCrossContext
)
