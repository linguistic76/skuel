"""
Context-First Types - User-Aware Entity Representations
========================================================

These types represent entities enriched with user context, enabling
personalized filtering, ranking, and insights in relationship queries.

**Core Philosophy:** "Filter by readiness, rank by relevance, enrich with insights"

**Pattern Overview:**
- Standard relationship queries return raw entities
- Context-first queries return ContextualEntity types
- Each type includes readiness, relevance, and actionable insights

**Naming Convention:**
- Standard: get_task_dependencies(uid) -> list[Task]
- Context-First: get_task_dependencies_for_user(uid, context) -> ContextualDependencies

**Entity Type Discriminator (November 28, 2025):**

All ContextualEntity subclasses have an `entity_type` property for unified dispatch:

| Class               | entity_type   |
|---------------------|---------------|
| ContextualEntity    | "entity"      |
| ContextualTask      | "task"        |
| ContextualKnowledge | "knowledge"   |
| ContextualHabit     | "habit"       |
| ContextualGoal      | "goal"        |
| ContextualEvent     | "event"       |
| ContextualPrinciple | "principle"   |
| ContextualChoice    | "choice"      |

This enables dictionary dispatch and match statements:

```python
# Dictionary dispatch
categorizers = {"task": task_list, "knowledge": ku_list}
for entity in entities:
    if entity.entity_type in categorizers:
        categorizers[entity.entity_type].append(entity)

# Match statement (Python 3.10+)
match entity.entity_type:
    case "task":
        handle_task(entity)
    case "knowledge":
        handle_knowledge(entity)
```

**Integration Points:**
- UserContext: Provides ~240 fields for personalization
- Relationship Services: Consume context to enrich results
- UserContextIntelligence: Combines context-first queries for flagship methods

Version: 1.1.0
Date: November 28, 2025
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.services.user.unified_user_context import UserContext


# =============================================================================
# SCORING ENGINE - Pure Functions for Contextual Entity Scoring
# =============================================================================


def _compute_readiness(
    required_knowledge: list[str],
    required_tasks: list[str],
    knowledge_mastery: dict[str, float],
    completed_task_uids: set[str] | list[str],
    threshold: float = 0.7,
) -> float:
    """
    Calculate readiness score based on prerequisites met.

    Args:
        required_knowledge: Knowledge prerequisite UIDs
        required_tasks: Task prerequisite UIDs
        knowledge_mastery: Map of ku_uid -> mastery level (0.0-1.0)
        completed_task_uids: Set of completed task UIDs
        threshold: Minimum mastery to consider "met"

    Returns:
        Score from 0.0 (no prerequisites met) to 1.0 (all met)
    """
    total = len(required_knowledge) + len(required_tasks)
    if total == 0:
        return 1.0

    met = 0
    for ku_uid in required_knowledge:
        if knowledge_mastery.get(ku_uid, 0.0) >= threshold:
            met += 1
    for task_uid in required_tasks:
        if task_uid in completed_task_uids:
            met += 1

    return met / total


def _compute_relevance(
    goal_uids: list[str],
    principle_uids: list[str],
    active_goal_uids: set[str] | list[str],
    primary_goal_focus: str,
    core_principle_uids: set[str] | list[str],
    principle_priorities: dict[str, float],
) -> float:
    """
    Calculate relevance score based on goal and principle alignment.

    Args:
        goal_uids: Goals this entity contributes to
        principle_uids: Principles this entity aligns with
        active_goal_uids: User's active goals
        primary_goal_focus: User's primary goal UID
        core_principle_uids: User's core principles
        principle_priorities: Map of principle_uid -> priority weight

    Returns:
        Score from 0.0 (not relevant) to 1.0 (highly relevant)
    """
    goal_score = 0.0
    principle_score = 0.0

    if goal_uids:
        aligned = len([g for g in goal_uids if g in active_goal_uids])
        goal_score = aligned / len(goal_uids)
        if primary_goal_focus in goal_uids:
            goal_score = min(1.0, goal_score + 0.2)

    if principle_uids:
        aligned_principles = [p for p in principle_uids if p in core_principle_uids]
        principle_score = len(aligned_principles) / len(principle_uids)
        for p_uid in aligned_principles:
            priority = principle_priorities.get(p_uid, 0.5)
            principle_score *= 0.5 + priority * 0.5

    if goal_uids and principle_uids:
        return (goal_score * 0.6) + (principle_score * 0.4)
    elif goal_uids:
        return goal_score
    elif principle_uids:
        return principle_score
    else:
        return 0.5


def _compute_urgency(
    deadline: date | None,
    is_at_risk: bool,
    streak_at_risk: bool,
) -> float:
    """
    Calculate urgency score based on time pressure and risk.

    Args:
        deadline: Entity deadline (if any)
        is_at_risk: Whether entity is flagged at risk
        streak_at_risk: Whether a streak is at risk

    Returns:
        Score from 0.0 (no urgency) to 1.0 (critical urgency)
    """
    urgency = 0.0

    if deadline:
        days_until = (deadline - date.today()).days
        if days_until < 0:
            urgency = 1.0
        elif days_until == 0:
            urgency = 0.9
        elif days_until <= 3:
            urgency = 0.7
        elif days_until <= 7:
            urgency = 0.5
        else:
            urgency = 0.2

    if is_at_risk:
        urgency = max(urgency, 0.8)
    if streak_at_risk:
        urgency = max(urgency, 0.85)

    return min(1.0, urgency)


def _compute_priority(
    dimensions: tuple[float, ...],
    weights: tuple[float, ...],
) -> float:
    """
    Calculate combined priority score from N dimensions and weights.

    Args:
        dimensions: Tuple of score values (0.0-1.0 each)
        weights: Tuple of weights (should sum to ~1.0)

    Returns:
        Combined priority score, capped at 1.0
    """
    return min(1.0, sum(d * w for d, w in zip(dimensions, weights, strict=False)))


def _compute_blocking_reasons(
    required_knowledge: list[str],
    required_tasks: list[str],
    knowledge_mastery: dict[str, float],
    completed_task_uids: set[str] | list[str],
    max_reasons: int = 3,
) -> list[str]:
    """
    Identify reasons blocking engagement with an entity.

    Args:
        required_knowledge: Knowledge prerequisite UIDs
        required_tasks: Task prerequisite UIDs
        knowledge_mastery: Map of ku_uid -> mastery level
        completed_task_uids: Set of completed task UIDs
        max_reasons: Maximum reasons to return

    Returns:
        List of blocking reason strings
    """
    reasons: list[str] = []

    for ku_uid in required_knowledge:
        mastery = knowledge_mastery.get(ku_uid, 0.0)
        if mastery < 0.7:
            reasons.append(f"Missing knowledge: {ku_uid} (mastery: {mastery:.0%})")
            if len(reasons) >= max_reasons:
                return reasons

    for task_uid in required_tasks:
        if task_uid not in completed_task_uids:
            reasons.append(f"Incomplete prerequisite: {task_uid}")
            if len(reasons) >= max_reasons:
                return reasons

    return reasons


# =============================================================================
# BASE CONTEXTUAL TYPES
# =============================================================================


@dataclass(frozen=True)
class ContextualEntity:
    """
    Base class for entities enriched with user context.

    All contextual types derive from this, ensuring consistent
    scoring and insight patterns across domains.

    **Scores (0.0-1.0):**
    - readiness_score: How ready is user for this? (prerequisites met)
    - relevance_score: How relevant to user's goals/priorities?
    - priority_score: Combined priority for ranking

    **Insights:**
    - blocking_reasons: What prevents user from engaging?
    - unlocks: What completing/mastering this enables
    - learning_gaps: Knowledge needed but not mastered
    """

    uid: str
    title: str

    # Context-derived scores (0.0-1.0)
    readiness_score: float = 0.0
    relevance_score: float = 0.0
    priority_score: float = 0.0

    # Context-derived insights
    blocking_reasons: tuple[str, ...] = field(default_factory=tuple)
    unlocks: tuple[str, ...] = field(default_factory=tuple)
    learning_gaps: tuple[str, ...] = field(default_factory=tuple)

    # Metadata
    enriched_at: datetime = field(default_factory=datetime.now)

    def is_ready(self, threshold: float = 0.7) -> bool:
        """Check if entity is ready for user engagement."""
        return self.readiness_score >= threshold

    def is_relevant(self, threshold: float = 0.5) -> bool:
        """Check if entity is relevant to user's goals."""
        return self.relevance_score >= threshold

    def is_high_priority(self, threshold: float = 0.7) -> bool:
        """Check if entity should be prioritized."""
        return self.priority_score >= threshold

    def has_blockers(self) -> bool:
        """Check if there are blocking reasons."""
        return len(self.blocking_reasons) > 0

    @property
    def entity_type(self) -> str:
        """
        Return entity type for categorization and dispatch.

        Subclasses override to return their specific type:
        - "task", "knowledge", "habit", "goal", "event"

        This enables unified dispatch patterns:
        - match entity.entity_type: case "task": ...
        - categorizers[entity.entity_type].append(entity)
        """
        return "entity"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "uid": self.uid,
            "title": self.title,
            "entity_type": self.entity_type,
            "readiness_score": self.readiness_score,
            "relevance_score": self.relevance_score,
            "priority_score": self.priority_score,
            "blocking_reasons": list(self.blocking_reasons),
            "unlocks": list(self.unlocks),
            "learning_gaps": list(self.learning_gaps),
            "is_ready": self.is_ready(),
            "is_relevant": self.is_relevant(),
            "is_high_priority": self.is_high_priority(),
        }


# =============================================================================
# DOMAIN-SPECIFIC CONTEXTUAL TYPES
# =============================================================================


@dataclass(frozen=True)
class ContextualTask(ContextualEntity):
    """
    Task enriched with user context.

    **Additional Context:**
    - can_start: All prerequisites met?
    - estimated_time_minutes: Time to complete
    - contributes_to_goals: Which active goals this advances
    - applies_knowledge: Knowledge units practiced by this task

    **Use Cases:**
    - get_actionable_tasks_for_user(): Tasks ready to start
    - get_learning_tasks_for_user(): Tasks that reinforce learning
    - get_goal_tasks_for_user(): Tasks advancing active goals
    """

    can_start: bool = False
    estimated_time_minutes: int = 0
    contributes_to_goals: tuple[str, ...] = field(default_factory=tuple)
    applies_knowledge: tuple[str, ...] = field(default_factory=tuple)

    # Task-specific context
    is_overdue: bool = False
    is_milestone: bool = False
    dependency_count: int = 0
    dependent_count: int = 0  # Tasks waiting on this one

    @classmethod
    def from_entity_and_context(
        cls,
        uid: str,
        title: str,
        context: "UserContext",
        *,
        goal_uids: list[str] | None = None,
        knowledge_uids: list[str] | None = None,
        prerequisite_knowledge: list[str] | None = None,
        prerequisite_tasks: list[str] | None = None,
        deadline: date | None = None,
        estimated_time_minutes: int = 0,
        readiness_override: float | None = None,
        relevance_override: float | None = None,
        urgency_override: float | None = None,
        priority_override: float | None = None,
        weights: tuple[float, float, float] = (0.4, 0.4, 0.2),
    ) -> "ContextualTask":
        """
        Factory: build a ContextualTask from entity data + UserContext.

        Standard path: readiness from prerequisites, relevance from goals,
        urgency from deadline/overdue, priority from weighted sum.
        """
        req_knowledge = prerequisite_knowledge or []
        req_tasks = prerequisite_tasks or []
        goals = goal_uids or []
        applies_ku = knowledge_uids or []

        readiness = (
            readiness_override
            if readiness_override is not None
            else _compute_readiness(
                req_knowledge,
                req_tasks,
                context.knowledge_mastery,
                context.completed_task_uids,
            )
        )
        relevance = (
            relevance_override
            if relevance_override is not None
            else _compute_relevance(
                goals,
                [],
                context.active_goal_uids,
                context.primary_goal_focus,
                context.core_principle_uids,
                context.principle_priorities,
            )
        )
        is_overdue = uid in context.overdue_task_uids
        urgency = (
            urgency_override
            if urgency_override is not None
            else _compute_urgency(
                deadline=deadline,
                is_at_risk=is_overdue,
                streak_at_risk=False,
            )
        )
        priority = (
            priority_override
            if priority_override is not None
            else _compute_priority(
                (readiness, relevance, urgency),
                weights,
            )
        )
        blocking = _compute_blocking_reasons(
            req_knowledge,
            req_tasks,
            context.knowledge_mastery,
            context.completed_task_uids,
        )

        return cls(
            uid=uid,
            title=title,
            readiness_score=readiness,
            relevance_score=relevance,
            priority_score=priority,
            can_start=readiness >= 0.7,
            blocking_reasons=tuple(blocking),
            contributes_to_goals=tuple(goals),
            applies_knowledge=tuple(applies_ku),
            is_overdue=is_overdue,
            is_milestone=uid in context.milestone_tasks,
            estimated_time_minutes=estimated_time_minutes,
            dependency_count=len(req_knowledge) + len(req_tasks),
        )

    @property
    def entity_type(self) -> str:
        return "task"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        base = super().to_dict()
        base.update(
            {
                "can_start": self.can_start,
                "estimated_time_minutes": self.estimated_time_minutes,
                "contributes_to_goals": list(self.contributes_to_goals),
                "applies_knowledge": list(self.applies_knowledge),
                "is_overdue": self.is_overdue,
                "is_milestone": self.is_milestone,
                "dependency_count": self.dependency_count,
                "dependent_count": self.dependent_count,
            }
        )
        return base


@dataclass(frozen=True)
class ContextualKnowledge(ContextualEntity):
    """
    Knowledge unit enriched with user context.

    **Additional Context:**
    - user_mastery: User's current mastery level (0.0-1.0)
    - prerequisites_met: All required knowledge mastered?
    - application_opportunities: Tasks/habits that apply this knowledge

    **Use Cases:**
    - get_ready_to_learn_for_user(): Knowledge with prerequisites met
    - get_learning_gaps_for_user(): Knowledge blocking progress
    - get_application_opportunities_for_user(): Where to practice
    """

    user_mastery: float = 0.0
    prerequisites_met: bool = False
    application_opportunities: tuple[str, ...] = field(default_factory=tuple)

    # Knowledge-specific context
    prerequisite_count: int = 0
    dependent_count: int = 0  # Knowledge that requires this
    substance_score: float = 0.0  # Real-world application level

    @classmethod
    def from_entity_and_context(
        cls,
        uid: str,
        title: str,
        context: "UserContext",
        *,
        prerequisite_uids: list[str] | None = None,
        application_task_uids: list[str] | None = None,
        dependent_count: int = 0,
        substance_score: float = 0.0,
        readiness_override: float | None = None,
        relevance_override: float | None = None,
        priority_override: float | None = None,
        weights: tuple[float, ...] = (0.5, 0.3, 0.2),
    ) -> "ContextualKnowledge":
        """
        Factory: build a ContextualKnowledge from entity data + UserContext.

        Standard path: mastery from context, prereqs_met check, readiness = 1.0
        if met else 0.3, relevance = 1.0 - mastery (gap-based), third dimension =
        dependent_count/5 (impact).
        """
        prereqs = prerequisite_uids or []
        applications = application_task_uids or []

        user_mastery = context.knowledge_mastery.get(uid, 0.0)
        prereqs_met = (
            all(context.knowledge_mastery.get(p, 0.0) >= 0.7 for p in prereqs) if prereqs else True
        )

        readiness = (
            readiness_override if readiness_override is not None else (1.0 if prereqs_met else 0.3)
        )
        relevance = (
            relevance_override
            if relevance_override is not None
            else (1.0 - user_mastery if user_mastery < 0.9 else 0.1)
        )

        if priority_override is not None:
            priority = priority_override
        else:
            dims = (readiness, relevance, min(1.0, dependent_count / 5))
            # Support 2D or 3D weights
            priority = _compute_priority(dims[: len(weights)], weights)

        blocking_reasons: list[str] = []
        if not prereqs_met:
            missing = [p for p in prereqs if context.knowledge_mastery.get(p, 0.0) < 0.7]
            blocking_reasons = [f"Missing prerequisite: {p}" for p in missing[:3]]

        return cls(
            uid=uid,
            title=title,
            readiness_score=readiness,
            relevance_score=relevance,
            priority_score=priority,
            user_mastery=user_mastery,
            prerequisites_met=prereqs_met,
            blocking_reasons=tuple(blocking_reasons),
            application_opportunities=tuple(applications),
            prerequisite_count=len(prereqs),
            dependent_count=dependent_count,
            substance_score=substance_score,
        )

    def mastery_category(self) -> str:
        """Categorize mastery level."""
        if self.user_mastery >= 0.9:
            return "expert"
        elif self.user_mastery >= 0.7:
            return "competent"
        elif self.user_mastery >= 0.4:
            return "developing"
        elif self.user_mastery > 0:
            return "beginner"
        else:
            return "unstarted"

    @property
    def entity_type(self) -> str:
        return "knowledge"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        base = super().to_dict()
        base.update(
            {
                "user_mastery": self.user_mastery,
                "prerequisites_met": self.prerequisites_met,
                "application_opportunities": list(self.application_opportunities),
                "prerequisite_count": self.prerequisite_count,
                "dependent_count": self.dependent_count,
                "substance_score": self.substance_score,
                "mastery_category": self.mastery_category(),
            }
        )
        return base


@dataclass(frozen=True)
class ContextualGoal(ContextualEntity):
    """
    Goal enriched with user context.

    **Additional Context:**
    - current_progress: User's progress percentage (0.0-1.0)
    - contributing_tasks: Active tasks advancing this goal
    - contributing_habits: Habits reinforcing this goal
    - knowledge_gaps: Knowledge needed for goal completion

    **Use Cases:**
    - get_advancing_goals_for_user(): Goals with active momentum
    - get_stalled_goals_for_user(): Goals needing attention
    - get_achievable_goals_for_user(): Goals near completion
    """

    current_progress: float = 0.0
    contributing_tasks: tuple[str, ...] = field(default_factory=tuple)
    contributing_habits: tuple[str, ...] = field(default_factory=tuple)
    knowledge_required: tuple[str, ...] = field(default_factory=tuple)

    # Goal-specific context
    days_to_deadline: int | None = None
    is_at_risk: bool = False
    milestone_count: int = 0
    milestones_completed: int = 0

    @classmethod
    def from_entity_and_context(
        cls,
        uid: str,
        title: str,
        context: "UserContext",
        *,
        contributing_task_uids: list[str] | None = None,
        contributing_habit_uids: list[str] | None = None,
        required_knowledge_uids: list[str] | None = None,
        readiness_override: float | None = None,
        relevance_override: float | None = None,
        urgency_override: float | None = None,
        priority_override: float | None = None,
        weights: tuple[float, ...] = (0.3, 0.4, 0.2, 0.1),
    ) -> "ContextualGoal":
        """
        Factory: build a ContextualGoal from entity data + UserContext.

        Standard path: 4D — readiness from knowledge prereqs, relevance from
        active+primary focus, progress from context, urgency from deadline/at-risk.
        """
        tasks = contributing_task_uids or []
        habits = contributing_habit_uids or []
        knowledge = required_knowledge_uids or []

        progress = context.goal_progress.get(uid, 0.0)

        readiness = (
            readiness_override
            if readiness_override is not None
            else _compute_readiness(
                knowledge,
                [],
                context.knowledge_mastery,
                context.completed_task_uids,
            )
        )
        relevance = (
            relevance_override
            if relevance_override is not None
            else (1.0 if uid in context.active_goal_uids else 0.5)
        )

        deadline = context.goal_deadlines.get(uid)
        days_to_deadline = None
        if deadline:
            days_to_deadline = (deadline - date.today()).days

        is_at_risk = uid in context.at_risk_goals
        urgency = (
            urgency_override
            if urgency_override is not None
            else _compute_urgency(
                deadline=deadline,
                is_at_risk=is_at_risk and progress < 0.3,
                streak_at_risk=False,
            )
        )

        if priority_override is not None:
            priority = priority_override
        else:
            dims = (readiness, relevance, progress, urgency)
            priority = _compute_priority(dims[: len(weights)], weights)

        learning_gaps = [ku for ku in knowledge if context.knowledge_mastery.get(ku, 0.0) < 0.7]

        return cls(
            uid=uid,
            title=title,
            readiness_score=readiness,
            relevance_score=relevance,
            priority_score=priority,
            current_progress=progress,
            contributing_tasks=tuple(tasks),
            contributing_habits=tuple(habits),
            knowledge_required=tuple(knowledge),
            learning_gaps=tuple(learning_gaps[:5]),
            days_to_deadline=days_to_deadline,
            is_at_risk=is_at_risk,
        )

    def is_near_completion(self, threshold: float = 0.8) -> bool:
        """Check if goal is near completion."""
        return self.current_progress >= threshold

    def is_stalled(self, progress_threshold: float = 0.1) -> bool:
        """Check if goal has minimal progress."""
        return self.current_progress < progress_threshold

    @property
    def entity_type(self) -> str:
        return "goal"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        base = super().to_dict()
        base.update(
            {
                "current_progress": self.current_progress,
                "contributing_tasks": list(self.contributing_tasks),
                "contributing_habits": list(self.contributing_habits),
                "knowledge_required": list(self.knowledge_required),
                "days_to_deadline": self.days_to_deadline,
                "is_at_risk": self.is_at_risk,
                "milestone_count": self.milestone_count,
                "milestones_completed": self.milestones_completed,
                "is_near_completion": self.is_near_completion(),
                "is_stalled": self.is_stalled(),
            }
        )
        return base


@dataclass(frozen=True)
class ContextualHabit(ContextualEntity):
    """
    Habit enriched with user context.

    **Additional Context:**
    - current_streak: User's current streak count
    - completion_rate: Recent completion percentage (0.0-1.0)
    - is_at_risk: Streak in danger of breaking?
    - supports_goals: Goals this habit contributes to

    **Use Cases:**
    - get_at_risk_habits_for_user(): Habits needing attention
    - get_keystone_habits_for_user(): High-impact habits
    - get_goal_habits_for_user(): Habits supporting active goals
    """

    current_streak: int = 0
    completion_rate: float = 0.0
    is_at_risk: bool = False
    supports_goals: tuple[str, ...] = field(default_factory=tuple)

    # Habit-specific context
    is_keystone: bool = False
    days_since_last: int = 0
    best_streak: int = 0
    applies_knowledge: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_entity_and_context(
        cls,
        uid: str,
        title: str,
        context: "UserContext",
        *,
        supported_goal_uids: list[str] | None = None,
        applied_knowledge_uids: list[str] | None = None,
        is_due_today: bool = False,
        current_streak: int | None = None,
        completion_rate: float | None = None,
        is_keystone: bool | None = None,
        days_since_last: int = 0,
        best_streak: int = 0,
        readiness_override: float | None = None,
        relevance_override: float | None = None,
        urgency_override: float | None = None,
        priority_override: float | None = None,
        weights: tuple[float, float, float] = (0.3, 0.3, 0.4),
    ) -> "ContextualHabit":
        """
        Factory: build a ContextualHabit from entity data + UserContext.

        Standard path: readiness = 1.0 (habits always ready), relevance from
        goal alignment + streak, urgency from at-risk/streak flags + is_due_today.
        """
        goals = supported_goal_uids or []
        knowledge = applied_knowledge_uids or []

        streak = current_streak if current_streak is not None else context.habit_streaks.get(uid, 0)
        rate = (
            completion_rate
            if completion_rate is not None
            else context.habit_completion_rates.get(uid, 0.0)
        )
        at_risk = uid in context.at_risk_habits
        keystone = is_keystone if is_keystone is not None else uid in context.keystone_habits

        readiness = readiness_override if readiness_override is not None else 1.0

        if relevance_override is not None:
            relevance = relevance_override
        else:
            goal_relevance = _compute_relevance(
                goals,
                [],
                context.active_goal_uids,
                context.primary_goal_focus,
                context.core_principle_uids,
                context.principle_priorities,
            )
            streak_relevance = min(1.0, streak / 30)
            relevance = (goal_relevance * 0.6) + (streak_relevance * 0.4)

        urgency = (
            urgency_override
            if urgency_override is not None
            else _compute_urgency(
                deadline=None,
                is_at_risk=at_risk or is_due_today,
                streak_at_risk=at_risk,
            )
        )

        priority = (
            priority_override
            if priority_override is not None
            else _compute_priority(
                (readiness, relevance, urgency),
                weights,
            )
        )

        return cls(
            uid=uid,
            title=title,
            readiness_score=readiness,
            relevance_score=relevance,
            priority_score=priority,
            current_streak=streak,
            completion_rate=rate,
            is_at_risk=at_risk,
            supports_goals=tuple(goals),
            is_keystone=keystone,
            days_since_last=days_since_last,
            best_streak=best_streak,
            applies_knowledge=tuple(knowledge),
        )

    def streak_status(self) -> str:
        """Categorize streak health."""
        if self.is_at_risk:
            return "at_risk"
        elif self.current_streak >= 30:
            return "strong"
        elif self.current_streak >= 7:
            return "building"
        elif self.current_streak > 0:
            return "starting"
        else:
            return "broken"

    @property
    def entity_type(self) -> str:
        return "habit"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        base = super().to_dict()
        base.update(
            {
                "current_streak": self.current_streak,
                "completion_rate": self.completion_rate,
                "is_at_risk": self.is_at_risk,
                "supports_goals": list(self.supports_goals),
                "is_keystone": self.is_keystone,
                "days_since_last": self.days_since_last,
                "best_streak": self.best_streak,
                "applies_knowledge": list(self.applies_knowledge),
                "streak_status": self.streak_status(),
            }
        )
        return base


@dataclass(frozen=True)
class ContextualEvent(ContextualEntity):
    """
    Event enriched with user context.

    **Additional Context:**
    - fits_schedule: Does event fit user's available time?
    - supports_habits: Habits this event reinforces
    - applies_knowledge: Knowledge practiced at event

    **Use Cases:**
    - get_upcoming_events_for_user(): Upcoming relevant events
    - get_habit_events_for_user(): Events reinforcing habits
    - get_learning_events_for_user(): Events for knowledge practice
    """

    fits_schedule: bool = True
    supports_habits: tuple[str, ...] = field(default_factory=tuple)
    applies_knowledge: tuple[str, ...] = field(default_factory=tuple)

    # Event-specific context
    days_until: int = 0
    duration_minutes: int = 0
    is_recurring: bool = False
    attendance_streak: int = 0

    @classmethod
    def from_entity_and_context(
        cls,
        uid: str,
        title: str,
        _context: "UserContext",
        *,
        days_until: int = 0,
        duration_minutes: int = 0,
        supports_habits: list[str] | None = None,
        applies_knowledge: list[str] | None = None,
    ) -> "ContextualEvent":
        """
        Factory: build a ContextualEvent from entity data + UserContext.

        Standard path: is_today check, readiness/relevance/priority from proximity.
        _context accepted for interface uniformity; scores derived from proximity.
        """
        is_today = days_until == 0
        return cls(
            uid=uid,
            title=title,
            readiness_score=1.0 if is_today else 0.8,
            relevance_score=0.9 if is_today else 0.7,
            priority_score=0.95 if is_today else 0.7,
            days_until=days_until,
            duration_minutes=duration_minutes,
            supports_habits=tuple(supports_habits or []),
            applies_knowledge=tuple(applies_knowledge or []),
        )

    @property
    def entity_type(self) -> str:
        return "event"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        base = super().to_dict()
        base.update(
            {
                "fits_schedule": self.fits_schedule,
                "supports_habits": list(self.supports_habits),
                "applies_knowledge": list(self.applies_knowledge),
                "days_until": self.days_until,
                "duration_minutes": self.duration_minutes,
                "is_recurring": self.is_recurring,
                "attendance_streak": self.attendance_streak,
            }
        )
        return base


@dataclass(frozen=True)
class ContextualPrinciple(ContextualEntity):
    """
    Principle enriched with user context.

    **Additional Context:**
    - alignment_score: How aligned is user's behavior? (0.0-1.0)
    - guided_goals: Goals inspired by this principle
    - guided_choices: Decisions aligned with this principle

    **Use Cases:**
    - get_core_principles_for_user(): User's highest priority principles
    - get_misaligned_principles_for_user(): Principles needing attention
    - get_principles_needing_attention_for_user(): Principles that need review/practice
    - get_contextual_principles_for_user(): Principles relevant to today's activities

    **Planning Service Fields (January 2026):**
    - attention_score: How urgently does this principle need attention? (0.0-1.0)
    - alignment_trend: Is alignment improving, declining, or stable?
    - days_since_reflection: Days since last reflection on this principle
    - attention_reasons: Why does this principle need attention?
    - suggested_action: Actionable recommendation
    - connected_task_uids: Today's tasks connected to this principle
    - connected_event_uids: Today's events connected to this principle
    - connected_goal_uids: Active goals connected to this principle
    - practice_opportunity: Description of today's practice opportunity
    """

    alignment_score: float = 0.0
    guided_goals: tuple[str, ...] = field(default_factory=tuple)
    guided_choices: tuple[str, ...] = field(default_factory=tuple)

    # Principle-specific context
    is_core: bool = False
    grounding_knowledge: tuple[str, ...] = field(default_factory=tuple)

    # Planning service fields (January 2026)
    attention_score: float = 0.0
    # NOTE: relevance_score inherited from ContextualEntity (no redeclaration)
    alignment_trend: str = "stable"  # "improving", "declining", "stable"
    days_since_reflection: int = 0
    attention_reasons: tuple[str, ...] = field(default_factory=tuple)
    suggested_action: str = ""
    connected_task_uids: tuple[str, ...] = field(default_factory=tuple)
    connected_event_uids: tuple[str, ...] = field(default_factory=tuple)
    connected_goal_uids: tuple[str, ...] = field(default_factory=tuple)
    practice_opportunity: str = ""

    @classmethod
    def from_entity_and_context(
        cls,
        uid: str,
        title: str,
        context: "UserContext",
        *,
        alignment_score: float = 0.5,
        days_since_reflection: int = 0,
        alignment_trend: str = "stable",
        attention_reasons: list[str] | None = None,
        suggested_action: str = "",
        connected_task_uids: list[str] | None = None,
        connected_event_uids: list[str] | None = None,
        connected_goal_uids: list[str] | None = None,
        practice_opportunity: str = "",
        priority_override: float | None = None,
        relevance_override: float | None = None,
    ) -> "ContextualPrinciple":
        """
        Factory: build a ContextualPrinciple from entity data + UserContext.

        Standard path: readiness = 1.0, relevance = alignment_score,
        priority = 0.8 if core else 0.5.

        Attention path (when days_since_reflection > 0): compute attention_score.
        """
        is_core = uid in context.core_principle_uids

        relevance = relevance_override if relevance_override is not None else alignment_score

        # Attention path: compute attention_score when reflection data available
        attention_score = 0.0
        if days_since_reflection > 0:
            reflection_urgency = min(1.0, days_since_reflection / 28)
            alignment_weakness = 1.0 - alignment_score
            trend_score = 0.0
            if alignment_trend == "declining":
                trend_score = 1.0
            elif alignment_trend == "stable":
                trend_score = 0.3
            attention_score = (
                (reflection_urgency * 0.4) + (alignment_weakness * 0.35) + (trend_score * 0.25)
            )

        priority = (
            priority_override
            if priority_override is not None
            else (attention_score if attention_score > 0 else (0.8 if is_core else 0.5))
        )

        return cls(
            uid=uid,
            title=title,
            readiness_score=1.0,
            relevance_score=relevance,
            priority_score=priority,
            alignment_score=alignment_score,
            is_core=is_core,
            attention_score=attention_score,
            alignment_trend=alignment_trend,
            days_since_reflection=days_since_reflection,
            attention_reasons=tuple(attention_reasons or []),
            suggested_action=suggested_action,
            connected_task_uids=tuple(connected_task_uids or []),
            connected_event_uids=tuple(connected_event_uids or []),
            connected_goal_uids=tuple(connected_goal_uids or []),
            practice_opportunity=practice_opportunity,
        )

    @property
    def entity_type(self) -> str:
        return "principle"

    def needs_attention(self, threshold: float = 0.5) -> bool:
        """Check if principle needs attention based on attention score."""
        return self.attention_score >= threshold

    def has_practice_opportunity(self) -> bool:
        """Check if there are connected activities for practice."""
        return bool(
            self.connected_task_uids or self.connected_event_uids or self.connected_goal_uids
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        base = super().to_dict()
        base.update(
            {
                "alignment_score": self.alignment_score,
                "guided_goals": list(self.guided_goals),
                "guided_choices": list(self.guided_choices),
                "is_core": self.is_core,
                "grounding_knowledge": list(self.grounding_knowledge),
                "attention_score": self.attention_score,
                "relevance_score": self.relevance_score,
                "alignment_trend": self.alignment_trend,
                "days_since_reflection": self.days_since_reflection,
                "attention_reasons": list(self.attention_reasons),
                "suggested_action": self.suggested_action,
                "connected_task_uids": list(self.connected_task_uids),
                "connected_event_uids": list(self.connected_event_uids),
                "connected_goal_uids": list(self.connected_goal_uids),
                "practice_opportunity": self.practice_opportunity,
                "needs_attention": self.needs_attention(),
                "has_practice_opportunity": self.has_practice_opportunity(),
            }
        )
        return base


@dataclass(frozen=True)
class ContextualChoice(ContextualEntity):
    """
    Choice/decision enriched with user context.

    **Additional Context:**
    - informed_by_knowledge: Knowledge informing this decision
    - aligned_principles: Principles this choice aligns with
    - resulting_goals: Goals that may emerge from this choice

    **Use Cases:**
    - get_pending_decisions_for_user(): Decisions awaiting resolution
    - get_principle_aligned_choices_for_user(): Choices matching values
    """

    informed_by_knowledge: tuple[str, ...] = field(default_factory=tuple)
    aligned_principles: tuple[str, ...] = field(default_factory=tuple)
    resulting_goals: tuple[str, ...] = field(default_factory=tuple)

    # Choice-specific context
    is_resolved: bool = False
    impact_score: float = 0.0

    @classmethod
    def from_entity_and_context(
        cls,
        uid: str,
        title: str,
        context: "UserContext",
        *,
        priority_level: str = "medium",
        informed_by_knowledge: list[str] | None = None,
        aligned_principles: list[str] | None = None,
    ) -> "ContextualChoice":
        """
        Factory: build a ContextualChoice from entity data + UserContext.

        Standard path: readiness = 1.0, relevance boosted by core principle
        alignment, priority from enum.
        """
        principles = aligned_principles or []
        core_principles = context.core_principle_uids or []

        # Relevance: higher when aligned with user's core principles
        if principles and core_principles:
            core_overlap = sum(1 for p in principles if p in core_principles)
            relevance = min(1.0, 0.5 + (core_overlap / len(principles)) * 0.5)
        else:
            relevance = 0.7

        priority_scores = {"urgent": 0.9, "high": 0.7, "medium": 0.5, "low": 0.3}
        priority = priority_scores.get(priority_level.lower(), 0.5)

        return cls(
            uid=uid,
            title=title,
            readiness_score=1.0,
            relevance_score=relevance,
            priority_score=priority,
            informed_by_knowledge=tuple(informed_by_knowledge or []),
            aligned_principles=tuple(principles),
            is_resolved=False,
        )

    @property
    def entity_type(self) -> str:
        return "choice"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        base = super().to_dict()
        base.update(
            {
                "informed_by_knowledge": list(self.informed_by_knowledge),
                "aligned_principles": list(self.aligned_principles),
                "resulting_goals": list(self.resulting_goals),
                "is_resolved": self.is_resolved,
                "impact_score": self.impact_score,
            }
        )
        return base


# =============================================================================
# PRINCIPLE PLANNING TYPES (January 2026)
# =============================================================================


@dataclass(frozen=True)
class PracticeOpportunity:
    """
    An activity that could strengthen principle alignment.

    **Purpose:** Identifies specific activities (tasks, events, goals) that offer
    opportunities to practice and reinforce a particular principle.

    **Use Cases:**
    - get_principle_practice_opportunities_for_user(): Find today's practice opportunities
    - Daily planning: Show how principles connect to scheduled activities
    - Reflection prompts: Suggest what to reflect on after completing activities

    **Fields:**
    - principle_uid/name: The principle this opportunity strengthens
    - activity_type: Type of activity ("task", "event", "goal", "habit")
    - activity_uid/title: The specific activity
    - opportunity_type: How this activity relates to the principle
    - guidance: Actionable suggestion for the user

    Version: 1.0.0
    Date: January 2026
    """

    principle_uid: str
    principle_name: str
    activity_type: str  # "task", "event", "goal", "habit"
    activity_uid: str
    activity_title: str
    opportunity_type: str  # "direct_alignment", "practice_context", "reflection_trigger"
    guidance: str

    def is_today(self) -> bool:
        """Check if this is a today-relevant opportunity."""
        return self.activity_type in ("task", "event")

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "principle_uid": self.principle_uid,
            "principle_name": self.principle_name,
            "activity_type": self.activity_type,
            "activity_uid": self.activity_uid,
            "activity_title": self.activity_title,
            "opportunity_type": self.opportunity_type,
            "guidance": self.guidance,
            "is_today": self.is_today(),
        }


# =============================================================================
# AGGREGATE CONTEXTUAL TYPES
# =============================================================================


@dataclass(frozen=True)
class ContextualDependencies:
    """
    Complete dependency analysis enriched with user context.

    **Purpose:** Provide actionable dependency information for an entity,
    categorized by user's readiness to engage.

    **Categories:**
    - ready_dependencies: User can engage with these now
    - blocked_dependencies: User needs to complete prerequisites first

    **Insights:**
    - recommended_next_action: Most impactful action to take
    - learning_path_suggestion: Knowledge to acquire for unblocking
    """

    entity_uid: str
    entity_type: str  # "Task", "Goal", "Habit", etc.

    # Categorized by readiness
    ready_dependencies: tuple[ContextualEntity, ...] = field(default_factory=tuple)
    blocked_dependencies: tuple[ContextualEntity, ...] = field(default_factory=tuple)

    # Categorized by type
    knowledge_requirements: tuple[ContextualKnowledge, ...] = field(default_factory=tuple)
    task_requirements: tuple[ContextualTask, ...] = field(default_factory=tuple)
    habit_requirements: tuple[ContextualHabit, ...] = field(default_factory=tuple)

    # Aggregated insights
    total_blocking_items: int = 0
    estimated_unblock_time_minutes: int = 0
    highest_priority_blocker: str | None = None

    # User-specific recommendations
    recommended_next_action: str = ""
    learning_path_suggestion: tuple[str, ...] = field(default_factory=tuple)

    # Metadata
    analyzed_at: datetime = field(default_factory=datetime.now)

    def is_fully_ready(self) -> bool:
        """Check if all dependencies are met."""
        return self.total_blocking_items == 0

    def get_critical_blockers(self, limit: int = 3) -> list[ContextualEntity]:
        """Get highest priority blockers."""

        def get_relevance_score(entity: ContextualEntity) -> float:
            return entity.relevance_score

        sorted_blockers = sorted(self.blocked_dependencies, key=get_relevance_score, reverse=True)
        return list(sorted_blockers[:limit])

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "entity_uid": self.entity_uid,
            "entity_type": self.entity_type,
            "ready_dependencies": [d.to_dict() for d in self.ready_dependencies],
            "blocked_dependencies": [d.to_dict() for d in self.blocked_dependencies],
            "knowledge_requirements": [k.to_dict() for k in self.knowledge_requirements],
            "task_requirements": [t.to_dict() for t in self.task_requirements],
            "habit_requirements": [h.to_dict() for h in self.habit_requirements],
            "total_blocking_items": self.total_blocking_items,
            "estimated_unblock_time_minutes": self.estimated_unblock_time_minutes,
            "highest_priority_blocker": self.highest_priority_blocker,
            "recommended_next_action": self.recommended_next_action,
            "learning_path_suggestion": list(self.learning_path_suggestion),
            "is_fully_ready": self.is_fully_ready(),
        }


# =============================================================================
# INTELLIGENCE OUTPUT TYPES
# =============================================================================


@dataclass(frozen=True)
class LifePathAlignment:
    """
    Comprehensive life path alignment analysis.

    **Philosophy:** "Everything flows toward the life path"

    Measures how well a user's daily activities, knowledge,
    habits, goals, and principles align with their ultimate life path.

    **Alignment Dimensions:**
    1. Knowledge Alignment (25%): Mastery of life path knowledge
    2. Activity Alignment (25%): Tasks/habits supporting life path goals
    3. Goal Alignment (20%): Active goals contributing to life path
    4. Principle Alignment (15%): Values supporting life path direction
    5. Momentum (15%): Recent activity trend toward life path

    **Score Scale:**
    - 0.0-0.3: Drifting (significant misalignment)
    - 0.4-0.6: Exploring (some alignment, room for growth)
    - 0.7-0.8: Aligned (actively living the path)
    - 0.9-1.0: Flourishing (fully integrated, embodied)
    """

    # Overall score
    overall_score: float  # 0.0-1.0
    alignment_level: str  # "drifting", "exploring", "aligned", "flourishing"

    # Dimension scores (0.0-1.0 each)
    knowledge_score: float  # Mastery of life path knowledge
    activity_score: float  # Tasks/habits supporting life path
    goal_score: float  # Goals contributing to life path
    principle_score: float  # Values supporting life path
    momentum_score: float  # Recent trend toward life path

    # Insights
    strengths: tuple[str, ...] = ()  # What's working well
    gaps: tuple[str, ...] = ()  # Where alignment is lacking
    recommendations: tuple[str, ...] = ()  # Actionable next steps

    # Supporting data
    life_path_uid: str | None = None
    life_path_milestones_completed: int = 0
    life_path_milestones_total: int = 0
    aligned_goals: tuple[str, ...] = ()  # Goal UIDs aligned with life path
    supporting_habits: tuple[str, ...] = ()  # Habit UIDs supporting life path
    knowledge_gaps: tuple[str, ...] = ()  # KU UIDs needing more application


@dataclass(frozen=True)
class CrossDomainSynergy:
    """
    A detected synergy between entities across different domains.

    **Examples:**
    - Habit->Goal: "Morning meditation" supports "Mental clarity", "Reduce stress"
    - Task->Habit: "Write journal entry" builds "Daily journaling" habit
    - Knowledge->Task: "Python async programming" enables multiple coding tasks
    - Principle->Choice: "Growth mindset" informs career decisions

    **Synergy Score:**
    - 0.0-0.3: Weak synergy (single connection)
    - 0.4-0.6: Moderate synergy (multiple connections)
    - 0.7-1.0: Strong synergy (hub entity, high leverage)
    """

    source_uid: str  # The entity creating synergy
    source_domain: str  # "habit", "task", "knowledge", "principle"
    target_uids: tuple[str, ...] = ()  # Entities benefiting from this
    target_domain: str = ""  # "goal", "habit", "task", "choice"
    synergy_type: str = ""  # "supports", "enables", "builds", "informs"
    synergy_score: float = 0.0  # 0.0-1.0 (higher = more leverage)
    rationale: str = ""  # Human-readable explanation
    recommendations: tuple[str, ...] = ()  # Actionable suggestions


@dataclass(frozen=True)
class LearningStep:
    """A recommended learning step with full context."""

    ku_uid: str
    title: str
    rationale: str = ""
    prerequisites_met: bool = False
    aligns_with_goals: tuple[str, ...] = ()  # Goal UIDs this helps with
    unlocks_count: int = 0  # How many items this unlocks
    estimated_time_minutes: int = 60
    priority_score: float = 0.0  # 0.0-1.0
    application_opportunities: dict[str, tuple[str, ...]] = field(
        default_factory=dict
    )  # Where can this be applied?


@dataclass(frozen=True)
class DailyWorkPlan:
    """
    Comprehensive plan for what to work on today.

    **THE FLAGSHIP OUTPUT** of UserContextIntelligence.get_ready_to_work_on_today()

    **Synthesizes ALL domains:**
    - Activity Domains (6): tasks, habits, goals, events, choices, principles
    - Curriculum Domains (3): ku, ls, lp

    **Respects:**
    - User's available time (capacity)
    - User's energy level (cognitive load)
    - User's current workload (not overloading)
    """

    # Prioritized entity UIDs for each domain
    learning: tuple[str, ...] = ()  # KU UIDs to learn
    tasks: tuple[str, ...] = ()  # Task UIDs to complete
    habits: tuple[str, ...] = ()  # Habit UIDs to maintain
    events: tuple[str, ...] = ()  # Event UIDs to attend
    goals: tuple[str, ...] = ()  # Goal UIDs to advance
    choices: tuple[str, ...] = ()  # Choice UIDs to consider
    principles: tuple[str, ...] = ()  # Principle UIDs to embody

    # Contextual items (enriched with user context)
    contextual_tasks: tuple[ContextualTask, ...] = ()
    contextual_habits: tuple[ContextualHabit, ...] = ()
    contextual_goals: tuple[ContextualGoal, ...] = ()
    contextual_knowledge: tuple[ContextualKnowledge, ...] = ()

    # Capacity metrics
    estimated_time_minutes: int = 0
    fits_capacity: bool = True
    workload_utilization: float = 0.0  # 0.0-1.0

    # Plan metadata
    rationale: str = ""
    priorities: tuple[str, ...] = ()  # Ordered priority list
    warnings: tuple[str, ...] = ()  # Capacity warnings, conflicts


@dataclass(frozen=True)
class ScheduleAwareRecommendation:
    """
    A recommendation that considers the user's schedule and capacity.

    **Schedule-aware recommendations take into account:**
    - Current events and scheduled activities
    - Energy levels and preferred times
    - Available time slots
    - Workload and capacity limits
    - Event conflicts and constraints

    **Recommendation Types:**
    - "learn": Knowledge unit to study
    - "task": Task to complete
    - "habit": Habit to maintain
    - "goal": Goal to advance
    - "rest": Rest recommendation (capacity exceeded)
    - "reschedule": Reschedule suggestion for conflicts
    """

    uid: str  # Entity UID (task_uid, ku_uid, habit_uid, etc.)
    entity_type: str  # "task", "habit", "goal", "knowledge", "event"
    recommendation_type: str  # "learn", "task", "habit", "goal", "rest", "reschedule"
    title: str  # Human-readable title
    rationale: str  # Why this is recommended NOW

    # Schedule context
    suggested_time_slot: str = ""  # "morning", "afternoon", "evening", "now", "later"
    estimated_duration_minutes: int = 30
    fits_available_time: bool = True
    conflicts_with: tuple[str, ...] = ()  # Event UIDs that conflict

    # Scoring (why this is optimal for this time)
    schedule_fit_score: float = 0.0  # 0.0-1.0 (how well it fits schedule)
    energy_match_score: float = 0.0  # 0.0-1.0 (matches current energy)
    priority_score: float = 0.0  # 0.0-1.0 (urgency/importance)
    overall_score: float = 0.0  # Weighted combination

    # Context for decision making
    deadline: str | None = None  # Due date if applicable
    streak_at_risk: bool = False  # For habits: is streak at risk?
    blocks_other_work: bool = False  # Does completing this unblock others?
    life_path_aligned: bool = False  # Aligned with life path?

    # Actionable guidance
    preparation_needed: tuple[str, ...] = ()  # What to prepare
    alternatives: tuple[str, ...] = ()  # Alternative recommendations


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Scoring engine
    "_compute_readiness",
    "_compute_relevance",
    "_compute_urgency",
    "_compute_priority",
    "_compute_blocking_reasons",
    # Base types
    "ContextualEntity",
    # Domain contextual types
    "ContextualTask",
    "ContextualKnowledge",
    "ContextualGoal",
    "ContextualHabit",
    "ContextualEvent",
    "ContextualChoice",
    "ContextualPrinciple",
    # Aggregate types
    "ContextualDependencies",
    "PracticeOpportunity",
    # Intelligence output types
    "DailyWorkPlan",
    "LifePathAlignment",
    "CrossDomainSynergy",
    "LearningStep",
    "ScheduleAwareRecommendation",
]
