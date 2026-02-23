"""
Unified Priority Scoring Framework
===================================

Type-safe, composable scoring system for activity domain prioritization.

Design Philosophy:
- Scores are normalized to 0.0-1.0 range
- Each domain defines weighted scoring components
- Components can be shared across domains (e.g., deadline_proximity)
- UserContext provides cross-domain intelligence

Architecture:
    ScoringComponent (enum) - Named scoring factors
    ComponentScore (dataclass) - Individual component result
    PriorityScore (dataclass) - Weighted composite score
    DomainScoringStrategy (protocol) - Domain-specific implementations

Common Scoring Components:
- DEADLINE_PROXIMITY: How close is a deadline (Tasks, Goals, Events, Choices)
- PRIORITY_LEVEL: Explicit priority enum value (Tasks, Goals)
- GOAL_ALIGNMENT: Supports/affects active goals (Events, Habits, Choices)
- STREAK_PROTECTION: Maintains active streaks (Habits)
- PROGRESS_MOMENTUM: Work already invested (Goals)
- URGENCY_LEVEL: Explicit urgency indicator (Choices)
- STRENGTH_LEVEL: Core vs exploring (Principles)

Usage:
    from core.models.search.scoring import (
        PriorityScore, ScoringComponent, score_goal
    )

    # Score a goal with context
    score = score_goal(goal, user_context)
    print(f"Priority: {score.total}")  # 0.0-1.0
    print(f"Components: {score.breakdown}")  # {"deadline": 0.8, ...}

Version: 1.0.0
Date: 2025-11-29
"""

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from core.models.enums import Priority
    from core.models.choice.choice import Choice
    from core.models.event.event import Event
    from core.models.goal.goal import Goal as Goal
    from core.models.habit.habit import Habit as Habit
    from core.models.principle.principle import Principle
    from core.models.task.task import Task as Task
    from core.services.user import UserContext


# =============================================================================
# SCORING COMPONENT ENUM - Shared vocabulary for scoring factors
# =============================================================================


class ScoringComponent(str, Enum):
    """
    Named scoring factors used across activity domains.

    Each component represents a specific reason why an entity
    should be prioritized higher or lower.
    """

    # Time-based (applies to: Tasks, Goals, Events, Choices)
    DEADLINE_PROXIMITY = "deadline_proximity"
    OVERDUE = "overdue"

    # Priority/Urgency (applies to: Tasks, Goals, Choices)
    PRIORITY_LEVEL = "priority_level"
    URGENCY_LEVEL = "urgency_level"

    # Goal alignment (applies to: Tasks, Events, Habits, Choices)
    GOAL_ALIGNMENT = "goal_alignment"
    ACTIVE_GOAL_SUPPORT = "active_goal_support"

    # Progress (applies to: Goals, Tasks)
    PROGRESS_MOMENTUM = "progress_momentum"
    NEAR_COMPLETION = "near_completion"

    # Habit-specific
    STREAK_PROTECTION = "streak_protection"
    STREAK_AT_RISK = "streak_at_risk"
    TIME_SINCE_COMPLETION = "time_since_completion"
    FREQUENCY_ALIGNMENT = "frequency_alignment"

    # Event-specific
    HABIT_REINFORCEMENT = "habit_reinforcement"
    EVENT_TYPE_PRIORITY = "event_type_priority"

    # Principle-specific
    STRENGTH_LEVEL = "strength_level"
    NEEDS_REVIEW = "needs_review"
    ALIGNMENT_STATUS = "alignment_status"
    ACTIONABILITY = "actionability"

    # Cross-domain
    CONTEXT_ALIGNMENT = "context_alignment"
    LEARNING_ALIGNMENT = "learning_alignment"
    IMPACT_POTENTIAL = "impact_potential"


# =============================================================================
# SCORE DATACLASSES - Type-safe score results
# =============================================================================


@dataclass(frozen=True)
class ComponentScore:
    """
    Individual scoring component result.

    Represents one factor's contribution to the total priority score.
    """

    component: ScoringComponent
    raw_value: float  # Unnormalized value (domain-specific scale)
    weight: float  # Component weight (0.0-1.0)
    normalized: float  # Normalized to 0.0-1.0 range
    reason: str = ""  # Human-readable explanation

    @property
    def weighted(self) -> float:
        """Get weighted contribution to total score."""
        return self.normalized * self.weight


@dataclass(frozen=True)
class PriorityScore:
    """
    Composite priority score with component breakdown.

    Provides both a single total score and detailed breakdown
    for transparency and debugging.
    """

    total: float  # Final score (0.0-1.0)
    components: tuple[ComponentScore, ...] = ()
    entity_uid: str = ""
    entity_type: str = ""

    @property
    def breakdown(self) -> dict[str, float]:
        """Get component scores as a dictionary."""
        return {c.component.value: c.weighted for c in self.components}

    @property
    def top_factors(self) -> list[tuple[str, float, str]]:
        """Get top 3 contributing factors with reasons."""

        def get_weighted_score(component: ComponentScore) -> float:
            return component.weighted

        sorted_components = sorted(self.components, key=get_weighted_score, reverse=True)
        return [(c.component.value, c.weighted, c.reason) for c in sorted_components[:3]]

    def explain(self) -> str:
        """Generate human-readable score explanation."""
        parts = [f"Score: {self.total:.2f}"]
        for name, value, reason in self.top_factors:
            if value > 0:
                parts.append(f"  • {name}: +{value:.2f} ({reason})")
        return "\n".join(parts)


# =============================================================================
# SCORING PROTOCOL - Interface for domain-specific strategies
# =============================================================================


class DomainScoringStrategy(Protocol):
    """
    Protocol for domain-specific scoring implementations.

    Each activity domain implements this protocol to define
    how entities in that domain are scored for prioritization.
    """

    def score(self, entity: Any, context: "UserContext") -> PriorityScore:
        """
        Calculate priority score for an entity.

        Args:
            entity: Domain entity (Task, Goal, Habit, etc.)
            context: User's current context for cross-domain intelligence

        Returns:
            PriorityScore with total and component breakdown
        """
        ...

    @property
    def component_weights(self) -> dict[ScoringComponent, float]:
        """
        Get the weight configuration for this domain.

        Returns:
            Mapping of component to weight (weights should sum to ~1.0)
        """
        ...


# =============================================================================
# SCORING UTILITIES - Shared scoring functions
# =============================================================================


def score_deadline_proximity(
    target_date: date | None,
    today: date | None = None,
    urgent_days: int = 7,
    soon_days: int = 30,
) -> ComponentScore:
    """
    Score based on deadline proximity.

    Returns higher scores for closer deadlines.

    Args:
        target_date: The deadline/target date
        today: Reference date (defaults to today)
        urgent_days: Days threshold for "urgent" (default 7)
        soon_days: Days threshold for "soon" (default 30)

    Returns:
        ComponentScore for deadline proximity
    """
    if today is None:
        today = date.today()

    if target_date is None:
        return ComponentScore(
            component=ScoringComponent.DEADLINE_PROXIMITY,
            raw_value=0.0,
            weight=0.0,
            normalized=0.0,
            reason="No deadline set",
        )

    days_until = (target_date - today).days

    if days_until < 0:
        # Overdue
        normalized = 1.0
        reason = f"Overdue by {abs(days_until)} days"
    elif days_until == 0:
        normalized = 1.0
        reason = "Due today"
    elif days_until == 1:
        normalized = 0.95
        reason = "Due tomorrow"
    elif days_until <= urgent_days:
        normalized = 0.8 + (0.15 * (urgent_days - days_until) / urgent_days)
        reason = f"Due in {days_until} days (urgent)"
    elif days_until <= soon_days:
        normalized = 0.5 + (0.3 * (soon_days - days_until) / soon_days)
        reason = f"Due in {days_until} days (soon)"
    else:
        normalized = max(0.1, 0.5 - (days_until - soon_days) / 365)
        reason = f"Due in {days_until} days"

    return ComponentScore(
        component=ScoringComponent.DEADLINE_PROXIMITY,
        raw_value=float(days_until),
        weight=1.0,  # Weight applied by caller
        normalized=normalized,
        reason=reason,
    )


def score_priority_level(
    priority: "Priority | None",
) -> ComponentScore:
    """
    Score based on explicit Priority enum value.

    Args:
        priority: Priority enum value or None

    Returns:
        ComponentScore for priority level
    """
    from core.models.enums import Priority

    if priority is None:
        return ComponentScore(
            component=ScoringComponent.PRIORITY_LEVEL,
            raw_value=0.0,
            weight=1.0,
            normalized=0.5,  # Default to medium
            reason="No priority set",
        )

    # Type-safe scoring based on Priority enum
    score_map = {
        Priority.CRITICAL: (1.0, "Critical priority"),
        Priority.HIGH: (0.8, "High priority"),
        Priority.MEDIUM: (0.5, "Medium priority"),
        Priority.LOW: (0.25, "Low priority"),
    }

    normalized, reason = score_map.get(priority, (0.5, f"Priority: {priority.value}"))

    return ComponentScore(
        component=ScoringComponent.PRIORITY_LEVEL,
        raw_value=float(priority.to_numeric()),
        weight=1.0,
        normalized=normalized,
        reason=reason,
    )


def score_goal_alignment(
    goal_uid: str | None,
    active_goal_uids: list[str] | None,
) -> ComponentScore:
    """
    Score based on alignment with user's active goals.

    Args:
        goal_uid: The goal UID this entity relates to
        active_goal_uids: User's currently active goal UIDs

    Returns:
        ComponentScore for goal alignment
    """
    if goal_uid is None:
        return ComponentScore(
            component=ScoringComponent.GOAL_ALIGNMENT,
            raw_value=0.0,
            weight=1.0,
            normalized=0.0,
            reason="No goal relationship",
        )

    if active_goal_uids and goal_uid in active_goal_uids:
        return ComponentScore(
            component=ScoringComponent.GOAL_ALIGNMENT,
            raw_value=1.0,
            weight=1.0,
            normalized=1.0,
            reason="Supports active goal",
        )

    return ComponentScore(
        component=ScoringComponent.GOAL_ALIGNMENT,
        raw_value=0.5,
        weight=1.0,
        normalized=0.3,
        reason="Has goal relationship",
    )


def score_progress_momentum(
    progress_percentage: float | None,
) -> ComponentScore:
    """
    Score based on progress momentum.

    Prioritizes items with active progress (not stalled, not complete).

    Args:
        progress_percentage: Current progress (0-100)

    Returns:
        ComponentScore for progress momentum
    """
    if progress_percentage is None:
        progress_percentage = 0.0

    if 25 <= progress_percentage <= 75:
        # Active progress zone - highest priority
        normalized = 0.9
        reason = f"Active progress ({progress_percentage:.0f}%)"
    elif progress_percentage > 75:
        # Near completion - high priority to finish
        normalized = 0.8
        reason = f"Near completion ({progress_percentage:.0f}%)"
    elif progress_percentage > 0:
        # Started but slow - moderate priority
        normalized = 0.5
        reason = f"Started ({progress_percentage:.0f}%)"
    else:
        # Not started - lower priority
        normalized = 0.3
        reason = "Not started"

    return ComponentScore(
        component=ScoringComponent.PROGRESS_MOMENTUM,
        raw_value=progress_percentage,
        weight=1.0,
        normalized=normalized,
        reason=reason,
    )


def score_streak_protection(
    current_streak: int | None,
    last_completed: date | None,
    today: date | None = None,
) -> ComponentScore:
    """
    Score based on streak protection needs.

    Higher scores for streaks at risk of breaking.

    Args:
        current_streak: Current streak count
        last_completed: Date of last completion
        today: Reference date (defaults to today)

    Returns:
        ComponentScore for streak protection
    """
    if today is None:
        today = date.today()

    if current_streak is None or current_streak == 0:
        return ComponentScore(
            component=ScoringComponent.STREAK_PROTECTION,
            raw_value=0.0,
            weight=1.0,
            normalized=0.3,
            reason="No active streak",
        )

    if last_completed is None:
        return ComponentScore(
            component=ScoringComponent.STREAK_PROTECTION,
            raw_value=float(current_streak),
            weight=1.0,
            normalized=0.8,
            reason=f"Streak of {current_streak} - needs attention",
        )

    # Type signature guarantees last_completed is date (not datetime)
    # Callers are responsible for converting datetime to date before calling
    days_since = (today - last_completed).days

    if days_since >= 2:
        # Streak at high risk
        normalized = 1.0
        reason = f"Streak of {current_streak} at risk ({days_since} days)"
    elif days_since >= 1:
        # Needs completion today
        if current_streak >= 7:
            normalized = 0.95
            reason = f"Protect {current_streak}-day streak"
        else:
            normalized = 0.85
            reason = f"Maintain {current_streak}-day streak"
    else:
        # Completed today
        if current_streak >= 7:
            normalized = 0.4
            reason = f"Streak of {current_streak} maintained"
        else:
            normalized = 0.2
            reason = "Already completed today"

    return ComponentScore(
        component=ScoringComponent.STREAK_PROTECTION,
        raw_value=float(current_streak),
        weight=1.0,
        normalized=normalized,
        reason=reason,
    )


# =============================================================================
# DOMAIN-SPECIFIC SCORING FUNCTIONS
# =============================================================================


def score_task(task: "Task", context: "UserContext") -> PriorityScore:
    """
    Calculate priority score for a task.

    Uses task's existing impact_score() for compatibility,
    wrapped in the unified PriorityScore structure.

    Args:
        task: Task to score
        context: User's current context

    Returns:
        PriorityScore with breakdown
    """
    # Leverage task's existing impact_score method
    impact = task.impact_score()

    # Build component scores for transparency
    components: list[ComponentScore] = []

    # Deadline component
    deadline_score = score_deadline_proximity(task.due_date)
    if deadline_score.normalized > 0:
        components.append(
            ComponentScore(
                component=ScoringComponent.DEADLINE_PROXIMITY,
                raw_value=deadline_score.raw_value,
                weight=0.4,
                normalized=deadline_score.normalized,
                reason=deadline_score.reason,
            )
        )

    # Priority component
    priority_score = score_priority_level(task.priority)
    components.append(
        ComponentScore(
            component=ScoringComponent.PRIORITY_LEVEL,
            raw_value=priority_score.raw_value,
            weight=0.3,
            normalized=priority_score.normalized,
            reason=priority_score.reason,
        )
    )

    # Goal alignment component
    goal_score = score_goal_alignment(
        task.fulfills_goal_uid,
        context.active_goal_uids,
    )
    if goal_score.normalized > 0:
        components.append(
            ComponentScore(
                component=ScoringComponent.GOAL_ALIGNMENT,
                raw_value=goal_score.raw_value,
                weight=0.2,
                normalized=goal_score.normalized,
                reason=goal_score.reason,
            )
        )

    # Learning alignment (from task model)
    learning = task.learning_alignment_score()
    if learning > 0:
        components.append(
            ComponentScore(
                component=ScoringComponent.LEARNING_ALIGNMENT,
                raw_value=learning,
                weight=0.1,
                normalized=learning,
                reason=f"Learning alignment: {learning:.0%}",
            )
        )

    return PriorityScore(
        total=impact,
        components=tuple(components),
        entity_uid=task.uid,
        entity_type="task",
    )


def score_goal(goal: "Goal", context: "UserContext") -> PriorityScore:
    """
    Calculate priority score for a goal.

    Args:
        goal: Goal to score
        context: User's current context

    Returns:
        PriorityScore with breakdown
    """
    components: list[ComponentScore] = []

    # Deadline proximity (weight: 0.35)
    deadline = score_deadline_proximity(goal.target_date)
    components.append(
        ComponentScore(
            component=ScoringComponent.DEADLINE_PROXIMITY,
            raw_value=deadline.raw_value,
            weight=0.35,
            normalized=deadline.normalized,
            reason=deadline.reason,
        )
    )

    # Progress momentum (weight: 0.30)
    progress = score_progress_momentum(goal.progress_percentage)
    components.append(
        ComponentScore(
            component=ScoringComponent.PROGRESS_MOMENTUM,
            raw_value=progress.raw_value,
            weight=0.30,
            normalized=progress.normalized,
            reason=progress.reason,
        )
    )

    # Priority level (weight: 0.25)
    priority = score_priority_level(goal.priority)
    components.append(
        ComponentScore(
            component=ScoringComponent.PRIORITY_LEVEL,
            raw_value=priority.raw_value,
            weight=0.25,
            normalized=priority.normalized,
            reason=priority.reason,
        )
    )

    # Context alignment (weight: 0.10)
    if context.active_goal_uids and goal.uid in context.active_goal_uids:
        components.append(
            ComponentScore(
                component=ScoringComponent.CONTEXT_ALIGNMENT,
                raw_value=1.0,
                weight=0.10,
                normalized=1.0,
                reason="Currently active goal",
            )
        )
    else:
        components.append(
            ComponentScore(
                component=ScoringComponent.CONTEXT_ALIGNMENT,
                raw_value=0.0,
                weight=0.10,
                normalized=0.0,
                reason="Not in active focus",
            )
        )

    # Calculate weighted total
    total = sum(c.weighted for c in components)

    return PriorityScore(
        total=total,
        components=tuple(components),
        entity_uid=goal.uid,
        entity_type="goal",
    )


def score_habit(habit: "Habit", context: "UserContext") -> PriorityScore:
    """
    Calculate priority score for a habit.

    Args:
        habit: Habit to score
        context: User's current context

    Returns:
        PriorityScore with breakdown
    """
    components: list[ComponentScore] = []
    today = date.today()

    # Convert datetime to date for streak calculation
    # habit.last_completed is typed as datetime | None
    last_completed: date | None = None
    if habit.last_completed:
        last_completed = habit.last_completed.date()

    # Streak protection (weight: 0.40)
    streak = score_streak_protection(
        habit.current_streak,
        last_completed,
        today,
    )
    components.append(
        ComponentScore(
            component=ScoringComponent.STREAK_PROTECTION,
            raw_value=streak.raw_value,
            weight=0.40,
            normalized=streak.normalized,
            reason=streak.reason,
        )
    )

    # Time since completion (weight: 0.25)
    if last_completed:
        days_since = (today - last_completed).days
        if days_since >= 3:
            time_normalized = 1.0
            time_reason = f"Overdue ({days_since} days)"
        elif days_since >= 2:
            time_normalized = 0.8
            time_reason = f"{days_since} days since completion"
        elif days_since >= 1:
            time_normalized = 0.6
            time_reason = "Due today"
        else:
            time_normalized = 0.1
            time_reason = "Completed today"
    else:
        time_normalized = 0.7
        time_reason = "Never completed"
        days_since = 0

    components.append(
        ComponentScore(
            component=ScoringComponent.TIME_SINCE_COMPLETION,
            raw_value=float(days_since),
            weight=0.25,
            normalized=time_normalized,
            reason=time_reason,
        )
    )

    # Goal support (weight: 0.20)
    habit_streaks = context.habit_streaks or {}
    if habit.uid and habit.uid in habit_streaks:
        components.append(
            ComponentScore(
                component=ScoringComponent.ACTIVE_GOAL_SUPPORT,
                raw_value=1.0,
                weight=0.20,
                normalized=0.8,
                reason="Supporting active goals",
            )
        )
    else:
        components.append(
            ComponentScore(
                component=ScoringComponent.ACTIVE_GOAL_SUPPORT,
                raw_value=0.0,
                weight=0.20,
                normalized=0.0,
                reason="No active goal support",
            )
        )

    # Frequency alignment (weight: 0.15) - use recurrence_pattern field
    from core.ports import get_enum_value

    freq_value = get_enum_value(habit.recurrence_pattern) if habit.recurrence_pattern else None

    if freq_value == "daily":
        freq_normalized = 1.0
        freq_reason = "Daily habit - needs daily attention"
    elif freq_value == "weekly":
        freq_normalized = 0.7
        freq_reason = "Weekly habit"
    else:
        freq_normalized = 0.4
        freq_reason = f"Frequency: {freq_value or 'unset'}"

    components.append(
        ComponentScore(
            component=ScoringComponent.FREQUENCY_ALIGNMENT,
            raw_value=1.0 if freq_value == "daily" else 0.5,
            weight=0.15,
            normalized=freq_normalized,
            reason=freq_reason,
        )
    )

    # Calculate weighted total
    total = sum(c.weighted for c in components)

    return PriorityScore(
        total=total,
        components=tuple(components),
        entity_uid=habit.uid,
        entity_type="habit",
    )


def score_event(event: "Event", context: "UserContext") -> PriorityScore:
    """
    Calculate priority score for an event.

    Args:
        event: Event to score
        context: User's current context

    Returns:
        PriorityScore with breakdown
    """
    components: list[ComponentScore] = []
    today = date.today()

    # Time proximity (weight: 0.40)
    if event.event_date:
        days_until = (event.event_date - today).days
        if days_until <= 0:
            time_normalized = 1.0
            time_reason = "Today or overdue"
        elif days_until == 1:
            time_normalized = 0.95
            time_reason = "Tomorrow"
        elif days_until <= 3:
            time_normalized = 0.85
            time_reason = f"In {days_until} days"
        elif days_until <= 7:
            time_normalized = 0.6
            time_reason = f"This week ({days_until} days)"
        else:
            time_normalized = 0.3
            time_reason = f"In {days_until} days"
    else:
        days_until = 0
        time_normalized = 0.0
        time_reason = "No date set"

    components.append(
        ComponentScore(
            component=ScoringComponent.DEADLINE_PROXIMITY,
            raw_value=float(days_until),
            weight=0.40,
            normalized=time_normalized,
            reason=time_reason,
        )
    )

    # Goal support (weight: 0.25) - use milestone_celebration_for_goal field
    # Note: supports_goal_uid is graph-native (SUPPORTS_GOAL relationship)
    goal_alignment = score_goal_alignment(
        event.milestone_celebration_for_goal,  # Use existing field for goal connection
        context.active_goal_uids,
    )
    components.append(
        ComponentScore(
            component=ScoringComponent.GOAL_ALIGNMENT,
            raw_value=goal_alignment.raw_value,
            weight=0.25,
            normalized=goal_alignment.normalized,
            reason=goal_alignment.reason,
        )
    )

    # Habit reinforcement (weight: 0.25)
    if event.reinforces_habit_uid:
        habit_streaks = context.habit_streaks or {}
        streak = habit_streaks.get(event.reinforces_habit_uid, 0)
        if streak > 0:
            habit_normalized = 1.0
            habit_reason = f"Protecting {streak}-day streak"
        else:
            active_habits = context.active_habit_uids or []
            if event.reinforces_habit_uid in active_habits:
                habit_normalized = 0.6
                habit_reason = "Supporting active habit"
            else:
                habit_normalized = 0.3
                habit_reason = "Has habit relationship"
    else:
        habit_normalized = 0.0
        habit_reason = "No habit relationship"

    components.append(
        ComponentScore(
            component=ScoringComponent.HABIT_REINFORCEMENT,
            raw_value=1.0 if event.reinforces_habit_uid else 0.0,
            weight=0.25,
            normalized=habit_normalized,
            reason=habit_reason,
        )
    )

    # Event type priority (weight: 0.10)
    from core.ports import get_enum_value

    event_type = get_enum_value(event.event_type) if event.event_type else None

    learning_types = {"study", "learning", "practice"}
    if event_type in learning_types:
        type_normalized = 1.0
        type_reason = f"Learning event ({event_type})"
    else:
        type_normalized = 0.5
        type_reason = f"Event type: {event_type or 'general'}"

    components.append(
        ComponentScore(
            component=ScoringComponent.EVENT_TYPE_PRIORITY,
            raw_value=1.0 if event_type in learning_types else 0.5,
            weight=0.10,
            normalized=type_normalized,
            reason=type_reason,
        )
    )

    # Calculate weighted total
    total = sum(c.weighted for c in components)

    return PriorityScore(
        total=total,
        components=tuple(components),
        entity_uid=event.uid,
        entity_type="event",
    )


def score_choice(choice: "Choice", context: "UserContext") -> PriorityScore:
    """
    Calculate priority score for a choice/decision.

    Args:
        choice: Choice to score
        context: User's current context

    Returns:
        PriorityScore with breakdown
    """
    components: list[ComponentScore] = []

    # Deadline proximity (weight: 0.35) - use decision_deadline field
    deadline = score_deadline_proximity(choice.decision_deadline)
    components.append(
        ComponentScore(
            component=ScoringComponent.DEADLINE_PROXIMITY,
            raw_value=deadline.raw_value,
            weight=0.35,
            normalized=deadline.normalized,
            reason=deadline.reason,
        )
    )

    # Priority level (weight: 0.25) - use existing priority field instead of urgency
    from core.ports import get_enum_value

    priority_value = get_enum_value(choice.priority) if choice.priority else None

    priority_scores = {
        "critical": (1.0, "Critical priority"),
        "high": (0.8, "High priority"),
        "medium": (0.5, "Medium priority"),
        "low": (0.25, "Low priority"),
    }
    priority_normalized, priority_reason = priority_scores.get(
        priority_value, (0.5, "No priority set")
    )

    components.append(
        ComponentScore(
            component=ScoringComponent.URGENCY_LEVEL,
            raw_value=1.0 if priority_value == "critical" else 0.5,
            weight=0.25,
            normalized=priority_normalized,
            reason=priority_reason,
        )
    )

    # High stakes indicator (weight: 0.25) - replaces goal alignment
    # Uses existing model method for stakeholder/complexity analysis
    high_stakes = choice.has_high_stakes()
    stakes_normalized = 1.0 if high_stakes else 0.4
    stakes_reason = "High stakes decision" if high_stakes else "Standard decision"

    components.append(
        ComponentScore(
            component=ScoringComponent.GOAL_ALIGNMENT,
            raw_value=1.0 if high_stakes else 0.0,
            weight=0.25,
            normalized=stakes_normalized,
            reason=stakes_reason,
        )
    )

    # Decision complexity as impact proxy (weight: 0.15)
    complexity = choice.calculate_decision_complexity()
    components.append(
        ComponentScore(
            component=ScoringComponent.IMPACT_POTENTIAL,
            raw_value=complexity,
            weight=0.15,
            normalized=complexity,  # Already 0-1
            reason=f"Complexity score: {complexity:.0%}",
        )
    )

    # Calculate weighted total
    total = sum(c.weighted for c in components)

    return PriorityScore(
        total=total,
        components=tuple(components),
        entity_uid=choice.uid,
        entity_type="choice",
    )


def score_principle(principle: "Principle", context: "UserContext") -> PriorityScore:
    """
    Calculate priority score for a principle.

    Args:
        principle: Principle to score
        context: User's current context

    Returns:
        PriorityScore with breakdown
    """
    from core.models.enums.ku_enums import PrincipleStrength

    components: list[ComponentScore] = []

    # Strength level (weight: 0.35)
    strength_scores = {
        PrincipleStrength.CORE: (1.0, "Core principle"),
        PrincipleStrength.STRONG: (0.8, "Strong principle"),
        PrincipleStrength.MODERATE: (0.6, "Moderate principle"),
        PrincipleStrength.DEVELOPING: (0.4, "Developing principle"),
        PrincipleStrength.EXPLORING: (0.2, "Exploring principle"),
    }
    strength_normalized, strength_reason = strength_scores.get(
        principle.strength, (0.5, "Unknown strength")
    )

    components.append(
        ComponentScore(
            component=ScoringComponent.STRENGTH_LEVEL,
            raw_value=strength_normalized,
            weight=0.35,
            normalized=strength_normalized,
            reason=strength_reason,
        )
    )

    # Needs review (weight: 0.25)
    if principle.needs_review():
        review_normalized = 1.0
        review_reason = "Needs review"
    else:
        review_normalized = 0.0
        review_reason = "Recently reviewed"

    components.append(
        ComponentScore(
            component=ScoringComponent.NEEDS_REVIEW,
            raw_value=review_normalized,
            weight=0.25,
            normalized=review_normalized,
            reason=review_reason,
        )
    )

    # Alignment status (weight: 0.25)
    if principle.is_well_aligned():
        alignment_normalized = 0.8
        alignment_reason = "Well aligned - maintain"
    elif principle.has_alignment_issues():
        alignment_normalized = 0.9
        alignment_reason = "Has alignment issues - needs attention"
    else:
        alignment_normalized = 0.5
        alignment_reason = "Alignment unknown"

    components.append(
        ComponentScore(
            component=ScoringComponent.ALIGNMENT_STATUS,
            raw_value=alignment_normalized,
            weight=0.25,
            normalized=alignment_normalized,
            reason=alignment_reason,
        )
    )

    # Actionability (weight: 0.15)
    if principle.has_concrete_behaviors():
        action_normalized = 0.9
        action_reason = "Has concrete behaviors"
    elif principle.is_actionable():
        action_normalized = 0.6
        action_reason = "Actionable principle"
    else:
        action_normalized = 0.3
        action_reason = "Abstract principle"

    components.append(
        ComponentScore(
            component=ScoringComponent.ACTIONABILITY,
            raw_value=action_normalized,
            weight=0.15,
            normalized=action_normalized,
            reason=action_reason,
        )
    )

    # Calculate weighted total
    total = sum(c.weighted for c in components)

    return PriorityScore(
        total=total,
        components=tuple(components),
        entity_uid=principle.uid,
        entity_type="principle",
    )
