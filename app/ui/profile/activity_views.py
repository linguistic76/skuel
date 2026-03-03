"""Config-driven Activity Domain view components for profile page.

Six Activity Domains (Tasks, Habits, Goals, Events, Principles, Choices) share
the same layout — only the data-extraction logic varies per domain.

Public API: six thin wrapper functions with unchanged signatures.

Internal: ActivityDomainViewConfig + ActivityDomainView are implementation details.

See: /docs/architecture/UNIFIED_USER_ARCHITECTURE.md
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from fasthtml.common import H3, A, Div

from core.services.user.unified_user_context import UserContext
from ui.profile._shared import (
    DomainFilterControls,
    DomainIntelligenceCard,
    DomainSummaryCard,
    _item_list,
)

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

type StatsResult = tuple[list[tuple[str, int | str]], str]
type Recommendation = tuple[str, str]


def _is_this_week(date_value: str | date | None) -> bool:
    """Check if a date falls within the current Monday-Sunday week."""
    if date_value is None:
        return False
    if isinstance(date_value, str):
        try:
            date_value = date.fromisoformat(date_value)
        except ValueError:
            return False
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    return week_start <= date_value <= week_end


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ActivityDomainViewConfig:
    """Configuration for a single Activity Domain view layout.

    All layout decisions (filter controls, item limit, section title, etc.) are
    expressed declaratively here; ActivityDomainView implements the single layout.
    """

    domain: str
    title: str
    icon: str
    section_title: str
    href_prefix: str
    view_all_text: str
    empty_message: str
    intelligence_card_title: str
    show_filter_controls: bool
    item_limit: int
    stats_fn: Callable[[UserContext], StatsResult]
    items_fn: Callable[[UserContext], list[dict[str, Any]]]
    recommendations_fn: Callable[[UserContext], list[Recommendation]]


# ---------------------------------------------------------------------------
# Single layout implementation
# ---------------------------------------------------------------------------


def ActivityDomainView(
    config: ActivityDomainViewConfig,
    context: UserContext,
    focus_uid: str | None = None,
) -> Div:
    """Render a domain view using the provided config and context.

    Internal — consumers use the six public wrapper functions.
    """
    stats, status = config.stats_fn(context)
    items = config.items_fn(context)
    recommendations = config.recommendations_fn(context)

    intelligence_card = (
        DomainIntelligenceCard(config.intelligence_card_title, recommendations)
        if recommendations
        else Div()
    )

    back_link = Div()
    if focus_uid:
        back_link = Div(
            A(
                "← Back to Insights",
                href="/insights",
                cls="inline-block mb-4 text-sm text-primary hover:text-primary-hover",
            ),
            cls="mb-2",
        )

    filter_controls = (
        DomainFilterControls(config.domain, len(items)) if config.show_filter_controls else Div()
    )

    return Div(
        back_link,
        DomainSummaryCard(config.title, config.icon, stats, status),
        intelligence_card,
        H3(config.section_title, cls="text-lg font-semibold text-base-content mt-6 mb-4"),
        filter_controls,
        _item_list(
            items,
            config.empty_message,
            config.href_prefix,
            domain=config.domain,
            focus_uid=focus_uid,
            limit=config.item_limit,
        ),
        A(
            config.view_all_text,
            href=config.href_prefix,
            cls="inline-block mt-4 text-primary hover:text-primary-hover font-medium",
        ),
    )


# ---------------------------------------------------------------------------
# Tasks — extraction functions
# ---------------------------------------------------------------------------


def _tasks_stats(context: UserContext) -> StatsResult:
    total = len(context.active_task_uids) + len(context.completed_task_uids)
    active = len(context.active_task_uids)
    overdue = len(context.overdue_task_uids)
    if overdue > 3:
        status = "critical"
    elif overdue > 0:
        status = "warning"
    else:
        status = "healthy"
    return [("Total", total), ("Active", active), ("Overdue", overdue)], status


def _tasks_items(context: UserContext) -> list[dict[str, Any]]:
    items = []
    for task_data in context.entities_rich.get("tasks", [])[:50]:
        task = task_data.get("entity", {})
        uid = task.get("uid", "")
        is_overdue = uid in context.overdue_task_uids
        is_high_priority = context.task_priorities.get(uid, 0.0) >= 0.7
        items.append(
            {
                "title": task.get("title", "Untitled Task"),
                "uid": uid,
                "status": "overdue" if is_overdue else "in_progress",
                "is_overdue": is_overdue,
                "is_high_priority": is_high_priority,
                "is_this_week": uid in context.this_week_task_uids,
            }
        )
    if not items and context.active_task_uids:
        items = [
            {
                "title": f"Task {uid[:8]}...",
                "uid": uid,
                "status": "in_progress",
                "is_overdue": uid in context.overdue_task_uids,
                "is_high_priority": context.task_priorities.get(uid, 0.0) >= 0.7,
                "is_this_week": uid in context.this_week_task_uids,
            }
            for uid in context.active_task_uids[:50]
        ]
    return items


def _tasks_recommendations(context: UserContext) -> list[Recommendation]:
    overdue = len(context.overdue_task_uids)
    active = len(context.active_task_uids)
    recommendations: list[Recommendation] = []
    if overdue > 0:
        recommendations.append(
            (f"{overdue} task{'s' if overdue != 1 else ''} overdue - prioritize today", "warning")
        )
    high_priority_tasks = [
        uid for uid, priority in context.task_priorities.items() if priority >= 0.7
    ]
    if high_priority_tasks:
        high_pri_count = min(len(high_priority_tasks), 3)
        recommendations.append(
            (
                f"{high_pri_count} high-priority task{'s' if high_pri_count != 1 else ''} need attention",
                "priority",
            )
        )
    goal_aligned_count = sum(len(tasks) for tasks in context.tasks_by_goal.values())
    if goal_aligned_count > 0:
        recommendations.append((f"{goal_aligned_count} tasks aligned with active goals", "success"))
    if not recommendations and active > 0:
        recommendations.append(("Tasks are on track - keep up the momentum!", "success"))
    return recommendations


# ---------------------------------------------------------------------------
# Habits — extraction functions
# ---------------------------------------------------------------------------


def _habits_stats(context: UserContext) -> StatsResult:
    total = len(context.active_habit_uids)
    at_risk = len(context.at_risk_habits)
    keystone = len(context.keystone_habits)
    if at_risk > 2:
        status = "critical"
    elif at_risk > 0:
        status = "warning"
    else:
        status = "healthy"
    return [("Active", total), ("At Risk", at_risk), ("Keystone", keystone)], status


def _habits_items(context: UserContext) -> list[dict[str, Any]]:
    items = []
    for habit_data in context.entities_rich.get("habits", [])[:50]:
        habit = habit_data.get("entity", {})
        uid = habit.get("uid", "")
        streak = context.habit_streaks.get(uid, 0)
        is_at_risk = uid in context.at_risk_habits
        is_keystone = uid in context.keystone_habits
        items.append(
            {
                "title": f"{habit.get('title', 'Habit')} ({streak} day streak)",
                "uid": uid,
                "status": "keystone"
                if is_keystone
                else ("at_risk" if is_at_risk else "in_progress"),
                "is_overdue": is_at_risk,
                "is_high_priority": is_keystone,
                "is_this_week": _is_this_week(habit.get("next_due_date")),
            }
        )
    if not items and context.active_habit_uids:
        items = [
            {
                "title": f"Habit ({context.habit_streaks.get(uid, 0)} days)",
                "uid": uid,
                "status": "at_risk" if uid in context.at_risk_habits else "in_progress",
                "is_overdue": uid in context.at_risk_habits,
                "is_high_priority": uid in context.keystone_habits,
                "is_this_week": False,
            }
            for uid in context.active_habit_uids[:50]
        ]
    return items


def _habits_recommendations(context: UserContext) -> list[Recommendation]:
    at_risk = len(context.at_risk_habits)
    keystone = len(context.keystone_habits)
    total = len(context.active_habit_uids)
    recommendations: list[Recommendation] = []
    if at_risk > 0:
        recommendations.append(
            (
                f"{at_risk} habit{'s' if at_risk != 1 else ''} at risk of breaking - check in today",
                "warning",
            )
        )
    if keystone > 0:
        recommendations.append(
            (
                f"{keystone} keystone habit{'s' if keystone != 1 else ''} driving your success",
                "success",
            )
        )
    strong_streaks = [s for s in context.habit_streaks.values() if s >= 7]
    if strong_streaks:
        best_streak = max(strong_streaks)
        recommendations.append((f"Best streak: {best_streak} days - maintain momentum!", "success"))
    if not recommendations and total > 0:
        recommendations.append(("All habits are healthy - consistent progress!", "success"))
    return recommendations


# ---------------------------------------------------------------------------
# Goals — extraction functions
# ---------------------------------------------------------------------------


def _goals_stats(context: UserContext) -> StatsResult:
    total = len(context.active_goal_uids)
    at_risk = len(context.at_risk_goals)
    completed = len(context.completed_goal_uids)
    if at_risk > 0:
        status = "critical"
    elif len(context.get_stalled_goals()) > 0:
        status = "warning"
    else:
        status = "healthy"
    return [("Active", total), ("Completed", completed), ("At Risk", at_risk)], status


def _goals_items(context: UserContext) -> list[dict[str, Any]]:
    items = []
    for goal_data in context.entities_rich.get("goals", [])[:50]:
        goal = goal_data.get("entity", {})
        uid = goal.get("uid", "")
        progress = context.goal_progress.get(uid, 0)
        is_at_risk = uid in context.at_risk_goals
        is_near_complete = progress >= 0.8
        items.append(
            {
                "title": f"{goal.get('title', 'Goal')} ({int(progress * 100)}%)",
                "uid": uid,
                "status": "near_complete"
                if is_near_complete
                else ("at_risk" if is_at_risk else "in_progress"),
                "is_overdue": is_at_risk,
                "is_high_priority": is_near_complete,
                "is_this_week": _is_this_week(goal.get("target_date")),
            }
        )
    if not items and context.active_goal_uids:
        items = [
            {
                "title": f"Goal ({int(context.goal_progress.get(uid, 0) * 100)}%)",
                "uid": uid,
                "status": "at_risk" if uid in context.at_risk_goals else "in_progress",
                "is_overdue": uid in context.at_risk_goals,
                "is_high_priority": context.goal_progress.get(uid, 0) >= 0.8,
                "is_this_week": False,
            }
            for uid in context.active_goal_uids[:50]
        ]
    return items


def _goals_recommendations(context: UserContext) -> list[Recommendation]:
    at_risk = len(context.at_risk_goals)
    completed = len(context.completed_goal_uids)
    recommendations: list[Recommendation] = []
    if at_risk > 0:
        recommendations.append(
            (f"{at_risk} goal{'s' if at_risk != 1 else ''} at risk - needs attention", "warning")
        )
    stalled = len(context.get_stalled_goals())
    if stalled > 0:
        recommendations.append(
            (f"{stalled} goal{'s' if stalled != 1 else ''} stalled - review progress", "warning")
        )
    near_complete = [p for p in context.goal_progress.values() if p >= 0.8]
    if near_complete:
        recommendations.append(
            (
                f"{len(near_complete)} goal{'s' if len(near_complete) != 1 else ''} almost complete - push to finish!",
                "priority",
            )
        )
    if completed > 0 and len(recommendations) == 0:
        recommendations.append(
            (
                f"{completed} goal{'s' if completed != 1 else ''} achieved - celebrate wins!",
                "success",
            )
        )
    return recommendations


# ---------------------------------------------------------------------------
# Events — extraction functions
# ---------------------------------------------------------------------------


def _events_stats(context: UserContext) -> StatsResult:
    total_today = len(context.today_event_uids)
    upcoming = len(context.upcoming_event_uids)
    missed = len(context.missed_event_uids)
    if missed > 0:
        status = "critical"
    elif total_today > 3:
        status = "warning"
    else:
        status = "healthy"
    return [("Today", total_today), ("Upcoming", upcoming), ("Missed", missed)], status


def _events_items(context: UserContext) -> list[dict[str, Any]]:
    items = []
    for event_data in context.entities_rich.get("events", [])[:10]:
        event = event_data.get("entity", {})
        uid = event.get("uid", "")
        items.append(
            {
                "title": event.get("title", "Event"),
                "uid": uid,
                "status": "pending" if uid in context.today_event_uids else "in_progress",
            }
        )
    if not items and context.today_event_uids:
        items = [
            {"title": f"Event {uid[:8]}...", "uid": uid, "status": "pending"}
            for uid in context.today_event_uids[:10]
        ]
    return items


def _events_recommendations(context: UserContext) -> list[Recommendation]:
    missed = len(context.missed_event_uids)
    total_today = len(context.today_event_uids)
    upcoming = len(context.upcoming_event_uids)
    recommendations: list[Recommendation] = []
    if missed > 0:
        recommendations.append(
            (f"{missed} event{'s' if missed != 1 else ''} missed - reschedule today", "warning")
        )
    if total_today > 0:
        recommendations.append(
            (f"{total_today} event{'s' if total_today != 1 else ''} scheduled today", "info")
        )
    if total_today > 5:
        recommendations.append(("Heavy schedule today - prioritize key events", "warning"))
    if upcoming > 0:
        recommendations.append(
            (f"{upcoming} upcoming event{'s' if upcoming != 1 else ''} this week", "info")
        )
    return recommendations


# ---------------------------------------------------------------------------
# Principles — extraction functions
# ---------------------------------------------------------------------------


def _principles_stats(context: UserContext) -> StatsResult:
    total = len(context.core_principle_uids)
    aligned = context.decisions_aligned_with_principles
    against = context.decisions_against_principles
    if against > aligned:
        status = "critical"
    elif aligned < against * 2 and (aligned + against) > 0:
        status = "warning"
    else:
        status = "healthy"
    return [("Total", total), ("Aligned", aligned), ("Against", against)], status


def _principles_items(context: UserContext) -> list[dict[str, Any]]:
    items = []
    for principle_data in context.entities_rich.get("principles", [])[:10]:
        principle = principle_data.get("entity", {})
        uid = principle.get("uid", "")
        priority = context.principle_priorities.get(uid, 0.5)
        items.append(
            {
                "title": f"{principle.get('title', 'Principle')} (priority: {priority:.1f})",
                "uid": uid,
                "status": "in_progress",
            }
        )
    if not items and context.core_principle_uids:
        items = [
            {
                "title": f"Principle (priority: {context.principle_priorities.get(uid, 0.5):.1f})",
                "uid": uid,
                "status": "in_progress",
            }
            for uid in context.core_principle_uids[:10]
        ]
    return items


def _principles_recommendations(context: UserContext) -> list[Recommendation]:
    total = len(context.core_principle_uids)
    aligned = context.decisions_aligned_with_principles
    against = context.decisions_against_principles
    recommendations: list[Recommendation] = []
    if against > aligned:
        recommendations.append(
            (f"{against} recent decisions went against your principles", "warning")
        )
    if aligned > 0:
        recommendations.append(
            (
                f"{aligned} decision{'s' if aligned != 1 else ''} aligned with principles - strong integrity!",
                "success",
            )
        )
    if total == 0:
        recommendations.append(("Define your core principles to guide decisions", "info"))
    elif aligned == 0 and against == 0:
        recommendations.append(("Track choices to see principle alignment", "info"))
    return recommendations


# ---------------------------------------------------------------------------
# Choices — extraction functions
# ---------------------------------------------------------------------------


def _choices_stats(context: UserContext) -> StatsResult:
    pending = len(context.pending_choice_uids)
    resolved = len(context.resolved_choice_uids)
    total = pending + resolved
    if pending > 5:
        status = "critical"
    elif pending > 0:
        status = "warning"
    else:
        status = "healthy"
    return [("Total", total), ("Pending", pending), ("Resolved", resolved)], status


def _choices_items(context: UserContext) -> list[dict[str, Any]]:
    items = []
    for choice_data in context.entities_rich.get("choices", [])[:10]:
        choice = choice_data.get("entity", {})
        uid = choice.get("uid", "")
        items.append(
            {
                "title": choice.get("title", "Choice"),
                "uid": uid,
                "status": "pending" if uid in context.pending_choice_uids else "completed",
            }
        )
    if not items and context.pending_choice_uids:
        items = [
            {"title": f"Choice {uid[:8]}...", "uid": uid, "status": "pending"}
            for uid in context.pending_choice_uids[:10]
        ]
    return items


def _choices_recommendations(context: UserContext) -> list[Recommendation]:
    pending = len(context.pending_choice_uids)
    resolved = len(context.resolved_choice_uids)
    total = pending + resolved
    recommendations: list[Recommendation] = []
    if pending > 5:
        recommendations.append(
            (f"{pending} choices awaiting decision - address high-priority ones first", "warning")
        )
    elif pending > 0:
        recommendations.append(
            (
                f"{pending} choice{'s' if pending != 1 else ''} pending - make time for reflection",
                "info",
            )
        )
    if resolved > 0:
        recommendations.append(
            (
                f"{resolved} choice{'s' if resolved != 1 else ''} resolved - review outcomes",
                "success",
            )
        )
    if total == 0:
        recommendations.append(("Track important decisions to improve decision-making", "info"))
    return recommendations


# ---------------------------------------------------------------------------
# Per-domain config instances (module-level constants)
# ---------------------------------------------------------------------------

TASKS_VIEW_CONFIG = ActivityDomainViewConfig(
    domain="tasks",
    title="Tasks",
    icon="✅",
    section_title="Active Tasks",
    href_prefix="/tasks",
    view_all_text="View All Tasks →",
    empty_message="No active tasks",
    intelligence_card_title="Today's Focus",
    show_filter_controls=True,
    item_limit=50,
    stats_fn=_tasks_stats,
    items_fn=_tasks_items,
    recommendations_fn=_tasks_recommendations,
)

HABITS_VIEW_CONFIG = ActivityDomainViewConfig(
    domain="habits",
    title="Habits",
    icon="🔄",
    section_title="Active Habits",
    href_prefix="/habits",
    view_all_text="View All Habits →",
    empty_message="No active habits",
    intelligence_card_title="Habit Intelligence",
    show_filter_controls=True,
    item_limit=50,
    stats_fn=_habits_stats,
    items_fn=_habits_items,
    recommendations_fn=_habits_recommendations,
)

GOALS_VIEW_CONFIG = ActivityDomainViewConfig(
    domain="goals",
    title="Goals",
    icon="🎯",
    section_title="Active Goals",
    href_prefix="/goals",
    view_all_text="View All Goals →",
    empty_message="No active goals",
    intelligence_card_title="Goal Progress",
    show_filter_controls=True,
    item_limit=50,
    stats_fn=_goals_stats,
    items_fn=_goals_items,
    recommendations_fn=_goals_recommendations,
)

EVENTS_VIEW_CONFIG = ActivityDomainViewConfig(
    domain="events",
    title="Events",
    icon="📅",
    section_title="Upcoming Events",
    href_prefix="/events",
    view_all_text="View Calendar →",
    empty_message="No upcoming events",
    intelligence_card_title="Schedule Overview",
    show_filter_controls=False,
    item_limit=10,
    stats_fn=_events_stats,
    items_fn=_events_items,
    recommendations_fn=_events_recommendations,
)

PRINCIPLES_VIEW_CONFIG = ActivityDomainViewConfig(
    domain="principles",
    title="Principles",
    icon="⚖️",
    section_title="Core Principles",
    href_prefix="/principles",
    view_all_text="View All Principles →",
    empty_message="No principles defined",
    intelligence_card_title="Principle Alignment",
    show_filter_controls=False,
    item_limit=10,
    stats_fn=_principles_stats,
    items_fn=_principles_items,
    recommendations_fn=_principles_recommendations,
)

CHOICES_VIEW_CONFIG = ActivityDomainViewConfig(
    domain="choices",
    title="Choices",
    icon="🔀",
    section_title="Pending Choices",
    href_prefix="/choices",
    view_all_text="View All Choices →",
    empty_message="No pending choices",
    intelligence_card_title="Decision Status",
    show_filter_controls=False,
    item_limit=10,
    stats_fn=_choices_stats,
    items_fn=_choices_items,
    recommendations_fn=_choices_recommendations,
)


# ---------------------------------------------------------------------------
# Public wrapper functions — unchanged signatures
# ---------------------------------------------------------------------------


def TasksDomainView(context: UserContext, focus_uid: str | None = None) -> Div:
    """Tasks domain: stats + task list from context."""
    return ActivityDomainView(TASKS_VIEW_CONFIG, context, focus_uid)


def HabitsDomainView(context: UserContext, focus_uid: str | None = None) -> Div:
    """Habits domain: stats + habit list with streaks."""
    return ActivityDomainView(HABITS_VIEW_CONFIG, context, focus_uid)


def GoalsDomainView(context: UserContext, focus_uid: str | None = None) -> Div:
    """Goals domain: stats + goal progress list."""
    return ActivityDomainView(GOALS_VIEW_CONFIG, context, focus_uid)


def EventsDomainView(context: UserContext, focus_uid: str | None = None) -> Div:
    """Events domain: stats + upcoming events."""
    return ActivityDomainView(EVENTS_VIEW_CONFIG, context, focus_uid)


def PrinciplesDomainView(context: UserContext, focus_uid: str | None = None) -> Div:
    """Principles domain: stats + alignment view."""
    return ActivityDomainView(PRINCIPLES_VIEW_CONFIG, context, focus_uid)


def ChoicesDomainView(context: UserContext, focus_uid: str | None = None) -> Div:
    """Choices domain: stats + pending/resolved."""
    return ActivityDomainView(CHOICES_VIEW_CONFIG, context, focus_uid)
