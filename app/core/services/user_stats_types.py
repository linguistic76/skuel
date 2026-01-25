"""
User Statistics Types (Pattern 3C Migration)
===========================================

Frozen dataclasses for user profile statistics returns.
Replaces dict[str, Any] with strongly-typed, immutable structures.

Pattern 3C Phase 1: High-Priority Public API Types

ProfileHubData Integration:
- Built FROM UserContext (single source of truth)
- ProfileHubData is a computed, serializable view
- UserContext contains the rich domain awareness
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.services.user import UserContext


@dataclass(frozen=True)
class TasksStats:
    """Task statistics for a user."""

    total_active: int
    completed_today: int
    completed_this_week: int
    overdue: int
    completion_rate: float


@dataclass(frozen=True)
class HabitsStats:
    """Habit statistics for a user."""

    total_active: int
    current_streak: int
    longest_streak: int
    consistency_rate: float


@dataclass(frozen=True)
class GoalsStats:
    """Goal statistics for a user."""

    total_active: int
    on_track: int
    at_risk: int
    completed: int
    average_progress: float


@dataclass(frozen=True)
class LearningStats:
    """Learning statistics for a user."""

    knowledge_mastered: int
    paths_active: int
    paths_completed: int
    mastery_average: float
    total_learning_time_hours: float


@dataclass(frozen=True)
class EventsStats:
    """Event statistics for a user."""

    total_upcoming: int
    this_week: int
    this_month: int
    attended: int


@dataclass(frozen=True)
class ChoicesStats:
    """Choice statistics for a user."""

    total_active: int
    pending: int
    resolved: int
    deferred: int


@dataclass(frozen=True)
class PrinciplesStats:
    """Principle statistics for a user."""

    total_active: int
    practicing: int
    avg_alignment: float
    needs_review: int


@dataclass(frozen=True)
class JournalsStats:
    """Journal statistics for a user."""

    total_entries: int
    this_week: int
    this_month: int
    avg_per_week: float


@dataclass(frozen=True)
class FinanceStats:
    """Finance statistics for a user."""

    total_expenses: int
    this_month_spending: float
    active_budgets: int
    over_budget_count: int


@dataclass(frozen=True)
class OverallMetrics:
    """Overall metrics across all domains."""

    activity_score: float
    completion_rate: float
    productivity_score: float
    total_active_items: int
    completed_today: int


@dataclass(frozen=True)
class DomainStatsAggregate:
    """Aggregated statistics across all user domains."""

    tasks: TasksStats
    habits: HabitsStats
    goals: GoalsStats
    learning: LearningStats
    events: EventsStats
    choices: ChoicesStats
    principles: PrinciplesStats
    journals: JournalsStats
    finance: FinanceStats


@dataclass(frozen=True)
class ProfileHubData:
    """
    Complete profile hub data with type safety.

    Pattern 3C + UserContext Integration:
    - Built FROM UserContext (single source of truth)
    - ProfileHubData is a computed, serializable view
    - Includes full context for rich domain awareness

    Architecture:
    - user: Core user identity
    - context: THE source of truth (UserContext with all UIDs and relationships)
    - domain_stats: Computed statistical view (counts, rates)
    - overall_metrics: Computed cross-domain metrics
    - recent_activities: Recent actions across domains
    - recommendations: AI-generated suggestions
    """

    user: Any  # User type - avoid circular import
    context: Any  # UserContext - avoid circular import, use TYPE_CHECKING
    domain_stats: DomainStatsAggregate
    overall_metrics: OverallMetrics
    recent_activities: list[dict[str, Any]]
    recommendations: list[dict[str, str]]
    aggregated_at: str

    @staticmethod
    def from_context(
        user: Any,
        context: "UserContext",
        recent_activities: list[dict[str, Any]],
        recommendations: list[dict[str, str]],
    ) -> "ProfileHubData":
        """
        Build ProfileHubData from UserContext.

        This is THE way - context is the source of truth,
        ProfileHubData is the computed statistical view.

        Args:
            user: User entity
            context: Complete unified user context (the source of truth)
            recent_activities: Recent actions (not yet in context)
            recommendations: AI recommendations

        Returns:
            ProfileHubData with stats computed from context
        """
        # Compute domain stats from context
        domain_stats = _compute_domain_stats_from_context(context)

        # Compute overall metrics from context
        overall_metrics = _compute_overall_metrics_from_context(context)

        return ProfileHubData(
            user=user,
            context=context,
            domain_stats=domain_stats,
            overall_metrics=overall_metrics,
            recent_activities=recent_activities,
            recommendations=recommendations,
            aggregated_at=datetime.now(UTC).isoformat(),
        )


# =============================================================================
# HELPER FUNCTIONS - Compute Stats from UserContext
# =============================================================================


def _compute_domain_stats_from_context(context: "UserContext") -> DomainStatsAggregate:
    """
    Compute all domain statistics from UserContext.

    Single source of truth: UserContext contains the rich data,
    this function computes the statistical view.
    """
    # Tasks stats - computed from context UIDs and relationships
    tasks_stats = TasksStats(
        total_active=len(context.active_task_uids),
        completed_today=sum(
            1 for uid in context.today_task_uids if uid in context.completed_task_uids
        ),
        completed_this_week=sum(
            1 for uid in context.this_week_task_uids if uid in context.completed_task_uids
        ),
        overdue=len(context.overdue_task_uids),
        completion_rate=_calculate_task_completion_rate(context),
    )

    # Habits stats - computed from context streaks and rates
    habits_stats = HabitsStats(
        total_active=len(context.active_habit_uids),
        current_streak=max(context.habit_streaks.values()) if context.habit_streaks else 0,
        longest_streak=max(context.habit_streaks.values()) if context.habit_streaks else 0,
        consistency_rate=(
            sum(context.habit_completion_rates.values()) / len(context.habit_completion_rates)
            if context.habit_completion_rates
            else 0.0
        ),
    )

    # Goals stats - computed from context progress and deadlines
    goals_stats = GoalsStats(
        total_active=len(context.active_goal_uids),
        on_track=sum(
            1 for uid in context.active_goal_uids if context.goal_progress.get(uid, 0) >= 0.5
        ),
        at_risk=sum(
            1 for uid in context.active_goal_uids if context.goal_progress.get(uid, 0) < 0.3
        ),
        completed=len(context.completed_goal_uids),
        average_progress=(
            sum(context.goal_progress.values()) / len(context.goal_progress)
            if context.goal_progress
            else 0.0
        ),
    )

    # Learning stats - computed from context knowledge mastery
    learning_stats = LearningStats(
        knowledge_mastered=len(context.mastered_knowledge_uids),
        paths_active=len(context.enrolled_path_uids),
        paths_completed=len(context.completed_path_uids),
        mastery_average=(
            sum(context.knowledge_mastery.values()) / len(context.knowledge_mastery)
            if context.knowledge_mastery
            else 0.0
        ),
        total_learning_time_hours=sum(context.time_invested_hours_by_domain.values()),
    )

    # Events stats - computed from context event UIDs
    events_stats = EventsStats(
        total_upcoming=len(context.upcoming_event_uids),
        this_week=sum(
            1 for uid in context.upcoming_event_uids if uid in context.today_event_uids
        ),  # Simplified
        this_month=len(context.upcoming_event_uids),  # Simplified
        attended=sum(context.event_attendance.values()),
    )

    # Choices, Principles, Journals, Finance - simplified defaults
    # (These would be computed from context when those fields are added)
    choices_stats = ChoicesStats(total_active=0, pending=0, resolved=0, deferred=0)

    principles_stats = PrinciplesStats(
        total_active=len(context.core_principle_uids),
        practicing=0,  # Would need context field
        avg_alignment=(
            sum(context.principle_alignment_by_domain.values())
            / len(context.principle_alignment_by_domain)
            if context.principle_alignment_by_domain
            else 0.0
        ),
        needs_review=0,
    )

    journals_stats = JournalsStats(total_entries=0, this_week=0, this_month=0, avg_per_week=0.0)

    finance_stats = FinanceStats(
        total_expenses=0, this_month_spending=0.0, active_budgets=0, over_budget_count=0
    )

    return DomainStatsAggregate(
        tasks=tasks_stats,
        habits=habits_stats,
        goals=goals_stats,
        learning=learning_stats,
        events=events_stats,
        choices=choices_stats,
        principles=principles_stats,
        journals=journals_stats,
        finance=finance_stats,
    )


def _compute_overall_metrics_from_context(context: "UserContext") -> OverallMetrics:
    """
    Compute overall cross-domain metrics from UserContext.
    """
    # Activity score (0-100) based on workload
    activity_score = context.current_workload_score * 100

    # Overall completion rate (weighted average across domains)
    task_completion = _calculate_task_completion_rate(context)
    habit_consistency = (
        sum(context.habit_completion_rates.values()) / len(context.habit_completion_rates)
        if context.habit_completion_rates
        else 0.0
    )
    goal_progress = (
        sum(context.goal_progress.values()) / len(context.goal_progress)
        if context.goal_progress
        else 0.0
    )
    learning_mastery = (
        sum(context.knowledge_mastery.values()) / len(context.knowledge_mastery)
        if context.knowledge_mastery
        else 0.0
    )

    completion_rate = (
        task_completion * 0.3
        + habit_consistency * 0.3
        + goal_progress * 0.2
        + learning_mastery * 0.2
    )

    # Productivity score (completed items today)
    completed_today_count = sum(
        1 for uid in context.today_task_uids if uid in context.completed_task_uids
    )
    current_streak_sum = sum(context.habit_streaks.values())
    productivity_score = min(completed_today_count * 2.0 + current_streak_sum * 0.5, 100.0)

    # Total active items
    total_active_items = (
        len(context.active_task_uids)
        + len(context.active_habit_uids)
        + len(context.active_goal_uids)
        + len(context.enrolled_path_uids)
    )

    return OverallMetrics(
        activity_score=round(activity_score, 1),
        completion_rate=round(completion_rate, 2),
        productivity_score=round(productivity_score, 1),
        total_active_items=total_active_items,
        completed_today=completed_today_count,
    )


def _calculate_task_completion_rate(context: "UserContext") -> float:
    """Calculate task completion rate from context."""
    total_tasks = len(context.active_task_uids) + len(context.completed_task_uids)
    if total_tasks == 0:
        return 0.0
    return len(context.completed_task_uids) / total_tasks
