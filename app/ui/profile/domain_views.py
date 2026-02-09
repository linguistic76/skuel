"""Domain-specific view components for profile page.

Each view shows a combined layout:
- Summary stats at top
- List of items below
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import H2, H3, A, Button, Div, Label, Li, Option, P, Select, Span, Ul

from core.services.user.unified_user_context import UserContext
from ui.patterns.empty_state import EmptyState

if TYPE_CHECKING:
    from core.services.user.intelligence.types import (
        CrossDomainSynergy,
        DailyWorkPlan,
        LearningStep,
        LifePathAlignment,
    )


def DomainFilterControls(domain: str, total_count: int) -> Div:
    """Filter and sort controls for domain views (Phase 3, Task 12).

    Args:
        domain: Domain name (tasks, goals, habits, etc.)
        total_count: Total number of items in the domain

    Returns:
        Div with filter/sort controls
    """
    # Domain-specific filter presets
    filter_presets = {
        "tasks": [
            ("all", "All Tasks"),
            ("overdue", "Overdue"),
            ("high_priority", "High Priority"),
            ("this_week", "This Week"),
        ],
        "goals": [
            ("all", "All Goals"),
            ("at_risk", "At Risk"),
            ("near_complete", "Almost Done"),
        ],
        "habits": [
            ("all", "All Habits"),
            ("at_risk", "At Risk"),
            ("keystone", "Keystone"),
        ],
        "events": [
            ("all", "All Events"),
            ("today", "Today"),
            ("this_week", "This Week"),
        ],
        "choices": [("all", "All Choices")],
        "principles": [("all", "All Principles")],
    }

    # Domain-specific sort options
    sort_options = {
        "tasks": [
            ("priority", "Priority"),
            ("due_date", "Due Date"),
            ("title", "Alphabetical"),
        ],
        "goals": [
            ("priority", "Priority"),
            ("target_date", "Target Date"),
            ("progress", "Progress"),
            ("title", "Alphabetical"),
        ],
        "habits": [
            ("streak", "Streak"),
            ("title", "Alphabetical"),
        ],
        "events": [
            ("start_date", "Date"),
            ("title", "Alphabetical"),
        ],
        "choices": [
            ("created", "Recent"),
            ("title", "Alphabetical"),
        ],
        "principles": [
            ("strength", "Strength"),
            ("title", "Alphabetical"),
        ],
    }

    presets = filter_presets.get(domain, [("all", "All")])
    sorts = sort_options.get(domain, [("title", "Alphabetical")])

    # Filter preset buttons
    filter_buttons = []
    for value, label in presets:
        filter_buttons.append(
            Button(
                label,
                cls="btn btn-sm",
                x_bind_class=f"{{'btn-primary': filterPreset === '{value}', 'btn-ghost': filterPreset !== '{value}'}}",
                x_on_click=f"filterPreset = '{value}'",
            )
        )

    return Div(
        Div(
            # Sort dropdown
            Div(
                Label("Sort by:", cls="text-sm font-medium text-base-content mr-2"),
                Select(
                    *[Option(label, value=value) for value, label in sorts],
                    cls="select select-sm select-bordered",
                    x_model="sortBy",
                ),
                cls="flex items-center gap-2",
            ),
            # Filter buttons
            Div(
                Label("Filter:", cls="text-sm font-medium text-base-content mr-2"),
                Div(*filter_buttons, cls="flex gap-2 flex-wrap"),
                cls="flex items-center gap-2",
            ),
            # Show all toggle
            Div(
                Button(
                    Span(
                        "Show All",
                        x_show="!showAll",
                    ),
                    Span(
                        f"Show Less (showing {total_count})",
                        x_show="showAll",
                    ),
                    cls="btn btn-sm btn-ghost",
                    x_on_click="toggleShowAll()",
                ),
                cls="ml-auto",
            ),
            cls="flex items-center gap-4 flex-wrap",
        ),
        cls="p-4 bg-base-200 rounded-lg mb-4",
        x_data="domainFilter()",
    )


def DomainIntelligenceCard(
    title: str,
    recommendations: list[tuple[str, str]],
) -> Div:
    """Contextual intelligence card for domain-specific recommendations (Phase 2, Task 7).

    Args:
        title: Card title (e.g., "Today's Focus", "Habit Synergies")
        recommendations: List of (text, type) tuples where type is "info", "warning", or "success"

    Returns:
        Intelligence card with recommendations
    """
    if not recommendations:
        return Div()  # No recommendations, return empty

    type_icons = {
        "info": "💡",
        "warning": "⚠️",
        "success": "✓",
        "priority": "⭐",
    }

    items = []
    for text, rec_type in recommendations:
        icon = type_icons.get(rec_type, "•")
        items.append(
            Li(
                Span(icon, cls="mr-2"),
                Span(text, cls="text-sm text-base-content"),
                cls="flex items-start py-2",
            )
        )

    return Div(
        H3(title, cls="text-md font-semibold text-base-content mb-3"),
        Ul(*items, cls="space-y-1"),
        cls="p-4 bg-primary/5 rounded-lg border border-primary/20 mb-6",
    )


def DomainSummaryCard(
    title: str,
    icon: str,
    stats: list[tuple[str, int | str]],
    status: str,
) -> Div:
    """Summary card with key stats for a domain.

    Args:
        title: Domain name
        icon: Emoji icon
        stats: List of (label, value) tuples
        status: "healthy", "warning", "critical"
        color: Accent color name

    Returns:
        Card div with stats
    """
    status_colors = {
        "healthy": "bg-success/10 border-success",
        "warning": "bg-warning/10 border-warning",
        "critical": "bg-error/10 border-error",
    }
    status_bg = status_colors.get(status, "bg-base-100 border-base-300 shadow-sm")

    stats_html = []
    for label, value in stats:
        stats_html.append(
            Div(
                Div(str(value), cls="text-2xl font-bold text-base-content"),
                Div(label, cls="text-sm text-base-content/60"),
                cls="text-center",
            )
        )

    return Div(
        Div(
            Span(icon, cls="text-3xl"),
            H3(title, cls="text-xl font-semibold text-base-content"),
            cls="flex items-center gap-3 mb-4",
        ),
        Div(*stats_html, cls="grid grid-cols-3 gap-4"),
        cls=f"p-6 rounded-xl border-2 {status_bg}",
    )


def EmptyState_for_domain(domain: str, message: str) -> Div:
    """Actionable empty state for a domain (Phase 1, Task 5).

    Args:
        domain: Domain name (tasks, habits, goals, etc.)
        message: Empty state message

    Returns:
        EmptyState with CTA button
    """
    domain_config = {
        "tasks": {
            "icon": "✅",
            "action_text": "Create your first task →",
            "action_href": "/tasks/create",
            "description": "Tasks help you track what needs to be done",
        },
        "habits": {
            "icon": "🔄",
            "action_text": "Create your first habit →",
            "action_href": "/habits/create",
            "description": "Habits build consistency over time",
        },
        "goals": {
            "icon": "🎯",
            "action_text": "Create your first goal →",
            "action_href": "/goals/create",
            "description": "Goals give you direction and purpose",
        },
        "events": {
            "icon": "📅",
            "action_text": "Create your first event →",
            "action_href": "/events/create",
            "description": "Events help you plan your time",
        },
        "choices": {
            "icon": "🤔",
            "action_text": "Record your first choice →",
            "action_href": "/choices/create",
            "description": "Choices track your decision-making patterns",
        },
        "principles": {
            "icon": "⚖️",
            "action_text": "Define your first principle →",
            "action_href": "/principles/create",
            "description": "Principles guide your decisions",
        },
    }

    config = domain_config.get(domain, {})
    return EmptyState(
        title=message,
        description=config.get("description", ""),
        action_text=config.get("action_text"),
        action_href=config.get("action_href"),
        icon=config.get("icon"),
    )


def _item_list(
    items: list[dict[str, Any]],
    empty_message: str,
    item_href_prefix: str = "",
    domain: str = "",
    focus_uid: str | None = None,
    limit: int = 50,
) -> Div:
    """Generic item list component.

    Phase 3, Task 11: Added focus_uid support for deep linking with highlight.
    Phase 3, Task 12: Added limit parameter and filter data attributes.

    Args:
        items: List of item dictionaries with title, uid, status
        empty_message: Message to show when no items
        item_href_prefix: URL prefix for item links (e.g., "/tasks")
        domain: Domain name for actionable empty states
        focus_uid: Optional entity UID to highlight
        limit: Maximum number of items to render (default 50)
    """
    if not items:
        # Use actionable empty state if domain is provided (Phase 1, Task 5)
        if domain:
            return EmptyState_for_domain(domain, empty_message)
        # Fallback to basic empty state
        return Div(
            P(empty_message, cls="text-base-content/60 italic text-center py-8"),
            cls="bg-base-200 rounded-lg",
        )

    list_items = []
    for idx, item in enumerate(items[:limit]):  # Limit to specified count
        title = item.get("title", "Untitled")
        uid = item.get("uid", "")
        status = item.get("status", "")
        href = f"{item_href_prefix}/{uid}" if item_href_prefix and uid else None

        # Phase 3, Task 12: Extract filter metadata
        is_overdue = item.get("is_overdue", False)
        is_high_priority = item.get("is_high_priority", False)
        is_this_week = item.get("is_this_week", False)

        status_badge = ""
        if status:
            status_colors = {
                "completed": "text-success",
                "in_progress": "text-warning",
                "pending": "text-base-content/60",
                "overdue": "text-error",
                "at_risk": "text-error",
                "keystone": "text-success",
                "near_complete": "text-primary",
            }
            status_color = status_colors.get(status, "text-base-content/60")
            status_badge = Span(
                status.replace("_", " ").title(),
                cls=f"text-xs font-medium {status_color}",
            )

        item_content = Div(
            Span(title, cls="font-medium text-base-content"),
            status_badge,
            cls="flex items-center justify-between",
        )

        # Phase 3, Task 12: Build x-show expression for filtering
        # Show if: matches filter AND (showAll OR index < 10)
        x_show_expr = f"matchesFilter('{status}', {str(is_overdue).lower()}, {str(is_high_priority).lower()}, {str(is_this_week).lower()}) && (showAll || {idx} < 10)"

        # Phase 3, Task 11 & 12: Add data attributes and x-show for filtering
        item_attrs = {
            "data_uid": uid,  # For focus targeting
            "x_show": x_show_expr,  # For filtering
        }

        if href:
            list_items.append(
                A(
                    item_content,
                    href=href,
                    cls="block p-3 hover:bg-base-200 rounded-lg transition-colors",
                    **item_attrs,
                )
            )
        else:
            list_items.append(
                Div(
                    item_content,
                    cls="p-3 rounded-lg",
                    **item_attrs,
                )
            )

    # Phase 3, Task 11: Wrap in Alpine component for focus handling
    # Phase 3, Task 12: Always wrap in domainFilter for filtering
    wrapper_attrs = {"x_data": "domainFilter()"}

    # Phase 3, Task 11: Add focus handler if focus_uid present
    if focus_uid:
        wrapper_attrs["x_init"] = (
            f"$nextTick(() => {{ if (window.profileFocusHandler) {{ var handler = profileFocusHandler('{focus_uid}'); handler.scrollToFocused.call({{ $el: $el, focusUid: '{focus_uid}' }}); }} }})"
        )

    return Div(*list_items, cls="space-y-1", **wrapper_attrs)


def TasksDomainView(context: UserContext, focus_uid: str | None = None) -> Div:
    """Tasks domain: stats + task list from context.

    Phase 3, Task 11: Added focus_uid parameter for deep linking.
    """
    # Calculate stats
    total = len(context.active_task_uids) + len(context.completed_task_uids)
    active = len(context.active_task_uids)
    overdue = len(context.overdue_task_uids)

    # Determine status
    if overdue > 3:
        status = "critical"
    elif overdue > 0:
        status = "warning"
    else:
        status = "healthy"

    stats = [
        ("Total", total),
        ("Active", active),
        ("Overdue", overdue),
    ]

    # Build items list from rich data if available
    # Phase 3, Task 12: Increased limit to 50 for filtering/sorting
    items = []
    for task_data in context.active_tasks_rich[:50]:
        task = task_data.get("task", {})
        uid = task.get("uid", "")
        # Phase 3, Task 12: Add filter metadata
        is_overdue = uid in context.overdue_task_uids
        # Derive high priority from task_priorities dict (threshold >= 0.7)
        is_high_priority = context.task_priorities.get(uid, 0.0) >= 0.7
        # Note: is_this_week would require due_date field - placeholder for now
        is_this_week = False  # TODO: Calculate based on task.due_date

        items.append(
            {
                "title": task.get("title", "Untitled Task"),
                "uid": uid,
                "status": "overdue" if is_overdue else "in_progress",
                "is_overdue": is_overdue,
                "is_high_priority": is_high_priority,
                "is_this_week": is_this_week,
            }
        )

    # Fallback if no rich data
    if not items and context.active_task_uids:
        items = [
            {
                "title": f"Task {uid[:8]}...",
                "uid": uid,
                "status": "in_progress",
                "is_overdue": uid in context.overdue_task_uids,
                "is_high_priority": context.task_priorities.get(uid, 0.0) >= 0.7,
                "is_this_week": False,
            }
            for uid in context.active_task_uids[:50]
        ]

    # Phase 2, Task 7: Domain-specific intelligence
    recommendations = []
    if overdue > 0:
        recommendations.append(
            (f"{overdue} task{'s' if overdue != 1 else ''} overdue - prioritize today", "warning")
        )
    # Derive high priority tasks from task_priorities (threshold >= 0.7)
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
    # Derive goal-aligned tasks count from tasks_by_goal
    goal_aligned_count = sum(len(tasks) for tasks in context.tasks_by_goal.values())
    if goal_aligned_count > 0:
        recommendations.append((f"{goal_aligned_count} tasks aligned with active goals", "success"))
    if not recommendations and active > 0:
        recommendations.append(("Tasks are on track - keep up the momentum!", "success"))

    intelligence_card = (
        DomainIntelligenceCard("Today's Focus", recommendations) if recommendations else Div()
    )

    # Phase 3, Task 11: Add "Back to Insights" link if coming from insights
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

    return Div(
        back_link,  # Phase 3, Task 11
        DomainSummaryCard("Tasks", "✅", stats, status),
        intelligence_card,  # NEW: Contextual intelligence
        H3("Active Tasks", cls="text-lg font-semibold text-base-content mt-6 mb-4"),
        DomainFilterControls("tasks", len(items)),  # Phase 3, Task 12: Filter controls
        _item_list(
            items, "No active tasks", "/tasks", domain="tasks", focus_uid=focus_uid, limit=50
        ),
        A(
            "View All Tasks →",
            href="/tasks",
            cls="inline-block mt-4 text-primary hover:text-primary-hover font-medium",
        ),
    )


def HabitsDomainView(context: UserContext, focus_uid: str | None = None) -> Div:
    """Habits domain: stats + habit list with streaks.

    Phase 3, Task 11: Added focus_uid parameter for deep linking.
    """
    total = len(context.active_habit_uids)
    at_risk = len(context.at_risk_habits)
    keystone = len(context.keystone_habits)

    if at_risk > 2:
        status = "critical"
    elif at_risk > 0:
        status = "warning"
    else:
        status = "healthy"

    stats = [
        ("Active", total),
        ("At Risk", at_risk),
        ("Keystone", keystone),
    ]

    # Phase 3, Task 12: Increased limit to 50, added filter metadata
    items = []
    for habit_data in context.active_habits_rich[:50]:
        habit = habit_data.get("habit", {})
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
                "is_overdue": is_at_risk,  # For filter compatibility
                "is_high_priority": is_keystone,  # For filter compatibility
                "is_this_week": False,
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

    # Phase 2, Task 7: Domain-specific intelligence
    recommendations = []
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
    # Check for strong streaks
    strong_streaks = [s for s in context.habit_streaks.values() if s >= 7]
    if strong_streaks:
        best_streak = max(strong_streaks)
        recommendations.append((f"Best streak: {best_streak} days - maintain momentum!", "success"))
    if not recommendations and total > 0:
        recommendations.append(("All habits are healthy - consistent progress!", "success"))

    intelligence_card = (
        DomainIntelligenceCard("Habit Intelligence", recommendations) if recommendations else Div()
    )

    # Phase 3, Task 11: Add "Back to Insights" link if coming from insights
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

    return Div(
        back_link,  # Phase 3, Task 11
        DomainSummaryCard("Habits", "🔄", stats, status),
        intelligence_card,  # NEW: Contextual intelligence
        H3("Active Habits", cls="text-lg font-semibold text-base-content mt-6 mb-4"),
        DomainFilterControls("habits", len(items)),  # Phase 3, Task 12
        _item_list(
            items, "No active habits", "/habits", domain="habits", focus_uid=focus_uid, limit=50
        ),
        A(
            "View All Habits →",
            href="/habits",
            cls="inline-block mt-4 text-primary hover:text-primary-hover font-medium",
        ),
    )


def GoalsDomainView(context: UserContext, focus_uid: str | None = None) -> Div:
    """Goals domain: stats + goal progress list.

    Phase 3, Task 11: Added focus_uid parameter for deep linking.
    """
    total = len(context.active_goal_uids)
    at_risk = len(context.at_risk_goals)
    completed = len(context.completed_goal_uids)

    if at_risk > 0:
        status = "critical"
    elif len(context.get_stalled_goals()) > 0:
        status = "warning"
    else:
        status = "healthy"

    stats = [
        ("Active", total),
        ("Completed", completed),
        ("At Risk", at_risk),
    ]

    items = []
    # Phase 3, Task 12: Increased limit, added filter metadata
    for goal_data in context.active_goals_rich[:50]:
        goal = goal_data.get("goal", {})
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
                "is_this_week": False,
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

    # Phase 2, Task 7: Domain-specific intelligence
    recommendations = []
    if at_risk > 0:
        recommendations.append(
            (f"{at_risk} goal{'s' if at_risk != 1 else ''} at risk - needs attention", "warning")
        )

    stalled = len(context.get_stalled_goals())
    if stalled > 0:
        recommendations.append(
            (f"{stalled} goal{'s' if stalled != 1 else ''} stalled - review progress", "warning")
        )

    # Check for near-completion goals
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

    intelligence_card = (
        DomainIntelligenceCard("Goal Progress", recommendations) if recommendations else Div()
    )

    # Phase 3, Task 11: Add "Back to Insights" link if coming from insights
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

    return Div(
        back_link,  # Phase 3, Task 11
        DomainSummaryCard("Goals", "🎯", stats, status),
        intelligence_card,  # NEW: Contextual intelligence
        H3("Active Goals", cls="text-lg font-semibold text-base-content mt-6 mb-4"),
        DomainFilterControls("goals", len(items)),  # Phase 3, Task 12
        _item_list(
            items, "No active goals", "/goals", domain="goals", focus_uid=focus_uid, limit=50
        ),
        A(
            "View All Goals →",
            href="/goals",
            cls="inline-block mt-4 text-primary hover:text-primary-hover font-medium",
        ),
    )


def EventsDomainView(context: UserContext, focus_uid: str | None = None) -> Div:
    """Events domain: stats + upcoming events.

    Phase 3, Task 11: Added focus_uid parameter for deep linking.
    """
    total_today = len(context.today_event_uids)
    upcoming = len(context.upcoming_event_uids)
    missed = len(context.missed_event_uids)

    if missed > 0:
        status = "critical"
    elif total_today > 3:
        status = "warning"
    else:
        status = "healthy"

    stats = [
        ("Today", total_today),
        ("Upcoming", upcoming),
        ("Missed", missed),
    ]

    items = []
    for event_data in context.active_events_rich[:10]:
        event = event_data.get("event", {})
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

    # Phase 2, Task 7: Domain-specific intelligence
    recommendations = []
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

    intelligence_card = (
        DomainIntelligenceCard("Schedule Overview", recommendations) if recommendations else Div()
    )

    # Phase 3, Task 11: Add "Back to Insights" link if coming from insights
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

    return Div(
        back_link,  # Phase 3, Task 11
        DomainSummaryCard("Events", "📅", stats, status),
        intelligence_card,  # NEW: Contextual intelligence
        H3("Upcoming Events", cls="text-lg font-semibold text-base-content mt-6 mb-4"),
        _item_list(items, "No upcoming events", "/events", domain="events", focus_uid=focus_uid),
        A(
            "View Calendar →",
            href="/events",
            cls="inline-block mt-4 text-primary hover:text-primary-hover font-medium",
        ),
    )


def PrinciplesDomainView(context: UserContext, focus_uid: str | None = None) -> Div:
    """Principles domain: stats + alignment view.

    Phase 3, Task 11: Added focus_uid parameter for deep linking.
    """
    total = len(context.core_principle_uids)
    aligned = context.decisions_aligned_with_principles
    against = context.decisions_against_principles

    if against > aligned:
        status = "critical"
    elif aligned < against * 2 and (aligned + against) > 0:
        status = "warning"
    else:
        status = "healthy"

    stats = [
        ("Total", total),
        ("Aligned", aligned),
        ("Against", against),
    ]

    items = []
    for principle_data in context.core_principles_rich[:10]:
        principle = principle_data.get("principle", {})
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

    # Phase 2, Task 7: Domain-specific intelligence
    recommendations = []
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

    intelligence_card = (
        DomainIntelligenceCard("Principle Alignment", recommendations) if recommendations else Div()
    )

    # Phase 3, Task 11: Add "Back to Insights" link if coming from insights
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

    return Div(
        back_link,  # Phase 3, Task 11
        DomainSummaryCard("Principles", "⚖️", stats, status),
        intelligence_card,  # NEW: Contextual intelligence
        H3("Core Principles", cls="text-lg font-semibold text-base-content mt-6 mb-4"),
        _item_list(
            items, "No principles defined", "/principles", domain="principles", focus_uid=focus_uid
        ),
        A(
            "View All Principles →",
            href="/principles",
            cls="inline-block mt-4 text-primary hover:text-primary-hover font-medium",
        ),
    )


def ChoicesDomainView(context: UserContext, focus_uid: str | None = None) -> Div:
    """Choices domain: stats + pending/resolved.

    Phase 3, Task 11: Added focus_uid parameter for deep linking.
    """
    pending = len(context.pending_choice_uids)
    resolved = len(context.resolved_choice_uids)
    total = pending + resolved

    if pending > 5:
        status = "critical"
    elif pending > 0:
        status = "warning"
    else:
        status = "healthy"

    stats = [
        ("Total", total),
        ("Pending", pending),
        ("Resolved", resolved),
    ]

    items = []
    for choice_data in context.recent_choices_rich[:10]:
        choice = choice_data.get("choice", {})
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

    # Phase 2, Task 7: Domain-specific intelligence
    recommendations = []
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

    intelligence_card = (
        DomainIntelligenceCard("Decision Status", recommendations) if recommendations else Div()
    )

    # Phase 3, Task 11: Add "Back to Insights" link if coming from insights
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

    return Div(
        back_link,  # Phase 3, Task 11
        DomainSummaryCard("Choices", "🔀", stats, status),
        intelligence_card,  # NEW: Contextual intelligence
        H3("Pending Choices", cls="text-lg font-semibold text-base-content mt-6 mb-4"),
        _item_list(items, "No pending choices", "/choices", domain="choices", focus_uid=focus_uid),
        A(
            "View All Choices →",
            href="/choices",
            cls="inline-block mt-4 text-primary hover:text-primary-hover font-medium",
        ),
    )


def KnowledgeDomainView(context: UserContext, services: Any = None, user_uid: str = "") -> Div:
    """Knowledge domain: all KUs with user's VIEWED/BOOKMARKED status.

    Queries Neo4j for all KU nodes and enriches with per-user relationships.

    Args:
        context: UserContext (used for mastered/in_progress status)
        services: Services container (for Neo4j driver access)
        user_uid: Current user's UID (for relationship queries)
    """
    # The KU list is populated via the route handler which queries Neo4j
    # This view is a placeholder that expects ku_items to be passed via
    # the route handler wrapping this in a Div
    mastered = len(context.mastered_knowledge_uids)
    in_progress = len(context.in_progress_knowledge_uids)
    ready = len(context.ready_to_learn_uids)

    return Div(
        H2("Knowledge Units", cls="text-2xl font-bold mb-2"),
        P(
            "All knowledge units in the curriculum. Track your learning progress.",
            cls="text-base-content/70 mb-6",
        ),
        # Quick stats row
        Div(
            Div(
                Span(str(mastered), cls="text-xl font-bold text-success"),
                Span(" mastered", cls="text-sm text-base-content/60"),
                cls="flex items-baseline gap-1",
            ),
            Div(
                Span(str(in_progress), cls="text-xl font-bold text-warning"),
                Span(" in progress", cls="text-sm text-base-content/60"),
                cls="flex items-baseline gap-1",
            ),
            Div(
                Span(str(ready), cls="text-xl font-bold text-info"),
                Span(" ready", cls="text-sm text-base-content/60"),
                cls="flex items-baseline gap-1",
            ),
            cls="flex gap-6 mb-6",
        ),
        # KU list placeholder - actual items injected by route handler
        Div(id="ku-list-content"),
        # Link to main KU listing
        A(
            "Browse All Knowledge →",
            href="/knowledge",
            cls="inline-block mt-4 text-primary hover:text-primary-hover font-medium",
        ),
    )


def LearningStepsDomainView(_context: UserContext, _focus_uid: str | None = None) -> Div:
    """Learning Steps domain: placeholder for LS nodes (not yet created).

    Shows a clean empty state explaining what learning steps are.
    """
    return Div(
        H2("Learning Steps", cls="text-2xl font-bold mb-2"),
        P(
            "Structured sequences within a learning path.",
            cls="text-base-content/70 mb-6",
        ),
        # Empty state
        Div(
            Span("📝", cls="text-4xl mb-3 block"),
            H3("No learning steps available yet", cls="text-lg font-semibold mb-2"),
            P(
                "Learning steps are ordered sequences of Knowledge Units "
                "within a Learning Path. They provide structured, teacher-directed "
                "curriculum progression.",
                cls="text-sm text-base-content/60 mb-4 max-w-md",
            ),
            A(
                "Explore Knowledge Units →",
                href="/knowledge",
                cls="btn btn-sm btn-primary",
            ),
            cls="text-center py-12 bg-base-200 rounded-xl",
        ),
    )


def LearningPathsDomainView(context: UserContext, focus_uid: str | None = None) -> Div:
    """Learning Paths domain: enrolled paths with progress + ready to learn.

    Shows:
    - Active learning paths with progress
    - Knowledge ready to learn (prerequisites met)
    """
    # Phase 3, Task 11: Add "Back to Insights" link if coming from insights
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

    return Div(
        back_link,
        H2("Learning Paths", cls="text-2xl font-bold mb-2"),
        P(
            "Structured learning journeys through the curriculum.",
            cls="text-base-content/70 mb-6",
        ),
        # Learning Paths section
        H3("Your Paths", cls="text-lg font-semibold text-base-content mt-2 mb-4"),
        _learning_paths_list(context),
        # Ready to Learn section
        H3("Ready to Learn", cls="text-lg font-semibold text-base-content mt-6 mb-4"),
        _ready_to_learn_list(context),
        # Link to knowledge page
        A(
            "Browse Knowledge →",
            href="/knowledge",
            cls="inline-block mt-4 text-primary hover:text-primary-hover font-medium",
        ),
    )


def _learning_paths_list(context: UserContext) -> Div:
    """List of enrolled learning paths with progress."""
    if not context.enrolled_paths_rich:
        if not context.enrolled_path_uids:
            return EmptyState("No learning paths enrolled")
        # Fallback if no rich data
        items = [
            Div(
                Span("🗺️", cls="mr-2"),
                Span(f"Path {uid[:12]}...", cls="font-medium text-base-content"),
                cls="flex items-center p-3 bg-base-100 rounded-lg",
            )
            for uid in context.enrolled_path_uids[:5]
        ]
        return Div(*items, cls="space-y-2")

    # Build items from rich data
    items = []
    for path_data in context.enrolled_paths_rich[:5]:
        path = path_data.get("path", {})
        graph_context = path_data.get("graph_context", {})

        title = path.get("title", "Learning Path")
        uid = path.get("uid", "")
        progress = graph_context.get("progress", 0.0)
        progress_percent = int(progress * 100)

        # Determine if this is the current focus path
        is_current = uid == context.current_learning_path_uid

        items.append(
            A(
                Div(
                    Div(
                        Span("🗺️", cls="mr-2"),
                        Span(title, cls="font-medium text-base-content flex-1"),
                        Span(
                            "Active" if is_current else "",
                            cls="text-xs text-primary font-medium",
                        )
                        if is_current
                        else None,
                        cls="flex items-center mb-2",
                    ),
                    # Progress bar
                    Div(
                        Div(
                            cls="h-2 bg-primary rounded-full transition-all",
                            style=f"width: {progress_percent}%",
                        ),
                        cls="h-2 bg-base-200 rounded-full w-full",
                    ),
                    Div(
                        Span(f"{progress_percent}% complete", cls="text-xs text-base-content/60"),
                        cls="mt-1",
                    ),
                    cls="w-full",
                ),
                href=f"/learning/paths/{uid}" if uid else "#",
                cls="block p-3 bg-base-100 rounded-lg hover:bg-base-200 transition-colors",
            )
        )

    return Div(*items, cls="space-y-2") if items else EmptyState("No learning paths enrolled")


def _ready_to_learn_list(context: UserContext) -> Div:
    """List of knowledge units ready to learn (prerequisites met)."""
    ready_uids = list(context.ready_to_learn_uids)[:5]

    if not ready_uids:
        # Check if there are blocked items
        if context.prerequisites_needed:
            blocked_count = len(context.prerequisites_needed)
            return Div(
                P(
                    f"{blocked_count} knowledge units blocked by prerequisites",
                    cls="text-base-content/60 text-sm",
                ),
                P(
                    "Complete prerequisite knowledge to unlock more",
                    cls="text-base-content/60 text-xs mt-1",
                ),
                cls="bg-base-200 rounded-lg p-4",
            )
        return EmptyState("No knowledge ready to learn")

    # Try to get titles from knowledge_units_rich if available
    items = []
    for uid in ready_uids:
        ku_data = context.knowledge_units_rich.get(uid, {})
        ku = ku_data.get("ku", {})
        title = ku.get("title", uid) if ku else uid

        items.append(
            A(
                Span("💡", cls="mr-2"),
                Span(title, cls="font-medium text-base-content"),
                href=f"/learning/ku/{uid}",
                cls="flex items-center p-3 bg-base-100 rounded-lg hover:bg-base-200 transition-colors",
            )
        )

    return Div(*items, cls="space-y-2")


def _chart_visualizations_section() -> Div:
    """Chart.js visualizations section (Phase 1, Task 2).

    Displays:
    - Alignment radar chart (5 dimensions)
    - 30-day domain progress timeline
    """
    from fasthtml.common import Canvas

    return Div(
        H3("Visual Analytics", cls="text-xl font-semibold text-base-content mb-4"),
        # Two-column grid for charts
        Div(
            # Alignment Radar Chart
            Div(
                Div(
                    Canvas(
                        **{
                            "x-ref": "canvas",
                            "width": "400",
                            "height": "400",
                            "class": "max-w-full",
                        }
                    ),
                    Div(
                        "Loading chart...",
                        cls="text-center text-base-content/60 py-8",
                        **{"x-show": "loading"},
                    ),
                    Div(
                        Span("Error: ", cls="font-bold"),
                        Span(**{"x-text": "error"}),
                        cls="text-error text-center py-8",
                        **{"x-show": "error"},
                    ),
                    **{"x-data": "chartVis('/api/profile/charts/alignment', 'radar')"},
                ),
                cls="card bg-base-100 shadow-sm p-6",
            ),
            # Domain Progress Timeline
            Div(
                Div(
                    Canvas(
                        **{
                            "x-ref": "canvas",
                            "width": "600",
                            "height": "300",
                            "class": "max-w-full",
                        }
                    ),
                    Div(
                        "Loading chart...",
                        cls="text-center text-base-content/60 py-8",
                        **{"x-show": "loading"},
                    ),
                    Div(
                        Span("Error: ", cls="font-bold"),
                        Span(**{"x-text": "error"}),
                        cls="text-error text-center py-8",
                        **{"x-show": "error"},
                    ),
                    **{"x-data": "chartVis('/api/profile/charts/domain-progress', 'line')"},
                ),
                cls="card bg-base-100 shadow-sm p-6",
            ),
            cls="grid grid-cols-1 lg:grid-cols-2 gap-6",
        ),
        cls="mb-8",
    )


def OverviewView(
    context: UserContext,
    daily_plan: "DailyWorkPlan | None" = None,
    alignment: "LifePathAlignment | None" = None,
    synergies: "list[CrossDomainSynergy] | None" = None,
    learning_steps: "list[LearningStep] | None" = None,
) -> Div:
    """Overview: Life path alignment + intelligence recommendations + progress metrics.

    Operates in two modes:
    - Basic mode (all intelligence params None): Core profile data only
    - Full mode (all intelligence params provided): Full intelligence features

    Displays (Full mode):
    - Chart visualizations (Phase 1, Task 2): Alignment radar + domain progress timeline
    - Life path alignment breakdown (5 dimensions) - from intelligence
    - Daily work plan (today's optimal focus) - from intelligence
    - High-leverage actions (cross-domain synergies) - from intelligence
    - Next learning steps - from intelligence

    Displays (Both modes):
    - Current task focus (if set)
    - Overall velocity/momentum summary
    - Per-domain progress grid with velocity indicators
    - Cross-domain insights (warnings, notifications)

    Args:
        context: UserContext with ~240 fields of user state
        daily_plan: DailyWorkPlan from intelligence service (optional)
        alignment: LifePathAlignment from intelligence service (optional)
        synergies: list of CrossDomainSynergy from intelligence service (optional)
        learning_steps: list of LearningStep from intelligence service (optional)
    """
    # Check if intelligence is available (all params provided = full mode)
    _has_intelligence = daily_plan is not None and alignment is not None

    # Phase 1, Task 3: Use HTMX to load intelligence section with skeleton loading state
    # Phase 4, Task 15: Added caching with Alpine.js to reduce 2-3s load times
    from ui.patterns.skeleton import SkeletonIntelligence

    header = Div(
        H2("Activity Overview", cls="text-xl font-semibold text-base-content"),
        P(
            Span("Intelligence data ", cls="text-base-content/50"),
            Span(
                **{"x-text": "lastUpdatedText", "x-show": "hasCache"},
                cls="text-sm text-base-content/50",
            ),
            cls="text-sm mt-0.5",
            id="intelligence-status",
        ),
        cls="mb-4",
    )

    # Intelligence section with caching (Phase 4, Task 15)
    # Shows cached data immediately, fetches fresh data in background
    intelligence_section = Div(
        # Skeleton shown only when loading with no cache
        Div(
            SkeletonIntelligence(),
            **{"x-show": "loading && !hasCache"},
        ),
        # Cached/fresh content
        Div(
            **{
                "x-html": "intelligenceHtml",
                "x-show": "hasCache",
            },
        ),
        # Error state
        Div(
            Div(
                Span("⚠️ ", cls="text-2xl mr-2"),
                Span("Failed to load intelligence data", cls="font-medium"),
                cls="flex items-center",
            ),
            P(
                "Using cached data. Will retry in 5 minutes.",
                cls="text-sm text-base-content/60 mt-2",
                **{"x-show": "hasCache"},
            ),
            cls="alert alert-warning",
            **{"x-show": "error"},
        ),
        id="intelligence-container",
        **{
            "x-data": "intelligenceCache()",
            "x-init": "$nextTick(() => init())",
        },
    )

    return Div(
        header,
        intelligence_section,
        # Core profile components (always shown)
        _current_focus_card(context),
        _velocity_summary(context),
        _domain_progress_grid(context),
        _overview_insights(context),
    )


def _intelligence_unavailable_card() -> Div:
    """Card shown when intelligence services are not configured.

    Informs users that intelligence features require additional setup,
    while core profile functionality remains available.
    """
    features = [
        ("📋", "Daily Work Plan", "Prioritized tasks and habits for today"),
        ("🎯", "Life Path Alignment", "5-dimension alignment scoring"),
        ("🔗", "Cross-Domain Synergies", "High-leverage action identification"),
        ("📚", "Learning Recommendations", "Optimal next learning steps"),
    ]

    feature_items = [
        Div(
            Span(icon, cls="mr-2"),
            Div(
                Span(name, cls="font-medium text-sm"),
                P(desc, cls="text-xs text-base-content/60"),
                cls="flex flex-col",
            ),
            cls="flex items-start py-2",
        )
        for icon, name, desc in features
    ]

    return Div(
        Div(
            H3("Intelligence Features", cls="text-lg font-semibold text-base-content"),
            cls="mb-4",
        ),
        Div(
            P(
                "Intelligence features are not currently configured.",
                cls="text-base-content/70 mb-3",
            ),
            P(
                "Core profile features are available. Intelligence features include:",
                cls="text-sm text-base-content/60 mb-4",
            ),
            Div(*feature_items, cls="space-y-1"),
            cls="p-4 bg-base-200 rounded-lg border border-base-300",
        ),
        cls="mb-6",
    )


def _overview_insights(context: UserContext) -> Div:
    """Cross-domain insights — shown only when actionable, no gray box."""
    insights = []

    # Check for overdue tasks
    if context.overdue_task_uids:
        insights.append(
            _insight_item(
                "warning",
                f"{len(context.overdue_task_uids)} overdue tasks need attention",
                "/profile/tasks",
            )
        )

    # Check for at-risk habits
    if context.at_risk_habits:
        insights.append(
            _insight_item(
                "warning",
                f"{len(context.at_risk_habits)} habits at risk of breaking streak",
                "/profile/habits",
            )
        )

    # Check for pending choices
    if len(context.pending_choice_uids) > 3:
        insights.append(
            _insight_item(
                "info",
                f"{len(context.pending_choice_uids)} choices awaiting your decision",
                "/profile/choices",
            )
        )

    # Check for today's events
    if context.today_event_uids:
        insights.append(
            _insight_item(
                "info",
                f"{len(context.today_event_uids)} events scheduled for today",
                "/events",
            )
        )

    if not insights:
        return Div(
            Div(cls="border-t border-base-200 mt-8 mb-6"),
            P("Everything looks good! You're on track.", cls="text-sm text-base-content/50"),
        )

    return Div(
        Div(cls="border-t border-base-200 mt-8 mb-6"),
        H3(
            "Insights",
            cls="text-sm font-semibold uppercase tracking-wider text-base-content/50 mb-3",
        ),
        Div(*insights, cls="space-y-2"),
    )


def _insight_item(level: str, message: str, href: str) -> A:
    """Single insight item."""
    icons = {
        "warning": "⚠️",
        "info": "ℹ️",
        "success": "✓",
    }
    icon = icons.get(level, "•")

    return A(
        Span(icon, cls="mr-2"),
        Span(message),
        href=href,
        cls="flex items-center p-3 bg-base-100 rounded-lg hover:bg-base-200 transition-colors text-base-content/70 hover:text-base-content",
    )


def _current_focus_card(context: UserContext) -> Div:
    """Current task focus — compact inline element."""
    if not context.current_task_focus:
        return A(
            Span("🎯", cls="text-lg mr-2"),
            Span(
                "No current focus set",
                cls="text-sm text-base-content/50 group-hover:text-primary transition-colors",
            ),
            href="/profile/tasks",
            cls="flex items-center mb-4 group",
            **{"hx-boost": "false"},
        )

    # Get task title from rich data if available
    task_title = "Current Task"
    for task_data in context.active_tasks_rich:
        task = task_data.get("task", {})
        if task.get("uid") == context.current_task_focus:
            task_title = task.get("title", "Current Task")
            break

    return Div(
        Span("🎯", cls="text-lg mr-2"),
        Span("Focus: ", cls="text-sm font-medium text-base-content/50"),
        A(
            task_title,
            href=f"/tasks/get?uid={context.current_task_focus}",
            cls="text-sm font-medium text-primary hover:underline",
        ),
        cls="flex items-center mb-4",
    )


def _velocity_summary(context: UserContext) -> Div:
    """Overall velocity — compact inline indicator, not a gray box."""
    total_velocity = sum(context.velocity_by_domain.values())
    total_time = sum(context.time_invested_hours_by_domain.values())

    # Determine momentum status
    if total_velocity > 0.5:
        momentum = ("🚀", "Strong Momentum", "text-success")
    elif total_velocity > 0:
        momentum = ("📈", "Building", "text-primary")
    elif total_velocity > -0.3:
        momentum = ("➡️", "Steady", "text-base-content/60")
    else:
        momentum = ("📉", "Slowing", "text-warning")

    icon, label, color = momentum

    return Div(
        Span(icon, cls="text-lg mr-2"),
        Span(label, cls=f"text-sm font-medium {color}"),
        Span(" · ", cls="text-base-content/30 mx-2"),
        Span(f"{total_time:.1f}h invested", cls="text-sm text-base-content/50"),
        cls="flex items-center mb-6",
    )


def _domain_progress_grid(context: UserContext) -> Div:
    """Per-domain item counts — the hero element of the profile page.

    Large, colorful cards with left accent borders showing item counts
    per domain. Each domain gets a primary count (big number) and a
    secondary breakdown for context.
    """
    # (icon, name, primary_count, primary_label, secondary_count, secondary_label)
    domain_data = [
        (
            "✅",
            "Tasks",
            len(context.active_task_uids),
            "active",
            len(context.completed_task_uids),
            "completed",
        ),
        (
            "🔄",
            "Habits",
            len(context.active_habit_uids),
            "active",
            len(context.at_risk_habits),
            "at risk",
        ),
        (
            "🎯",
            "Goals",
            len(context.active_goal_uids),
            "active",
            len(context.completed_goal_uids),
            "completed",
        ),
        (
            "📅",
            "Events",
            len(context.upcoming_event_uids),
            "upcoming",
            len(context.today_event_uids),
            "today",
        ),
        (
            "⚖️",
            "Principles",
            len(context.core_principle_uids),
            "total",
            len(context.principle_conflicts),
            "conflicts",
        ),
        (
            "🔀",
            "Choices",
            len(context.pending_choice_uids),
            "pending",
            len(context.resolved_choice_uids),
            "resolved",
        ),
    ]

    domain_items = []
    for icon, name, primary, primary_label, secondary, secondary_label in domain_data:
        # Secondary line (only shown when count > 0)
        secondary_el = (
            Span(f"{secondary} {secondary_label}", cls="text-sm text-base-content/50")
            if secondary > 0
            else None
        )

        domain_items.append(
            Div(
                # Domain header
                Div(
                    Span(icon, cls="text-xl"),
                    Span(name, cls="text-base font-semibold text-base-content"),
                    cls="flex items-center gap-2 mb-3",
                ),
                # Primary count — the hero number
                Div(
                    Span(str(primary), cls="text-3xl font-bold text-base-content"),
                    Span(primary_label, cls="text-sm text-base-content/50 ml-2"),
                    cls="flex items-baseline",
                ),
                # Secondary breakdown
                Div(
                    secondary_el,
                    cls="mt-1 min-h-[1.25rem]",
                )
                if secondary_el
                else Div(cls="mt-1 min-h-[1.25rem]"),
                cls="bg-white rounded-xl p-5 shadow-sm hover:shadow-md transition-shadow",
            )
        )

    return Div(
        *domain_items,
        cls="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 lg:gap-5",
    )


# =============================================================================
# Intelligence Components (Phase 3)
# =============================================================================


def _daily_work_plan_card(plan: "DailyWorkPlan") -> Div:
    """Daily work plan card showing today's optimal focus.

    Displays prioritized items across domains with capacity utilization.

    Args:
        plan: DailyWorkPlan from intelligence service (REQUIRED)
    """
    # Capacity bar
    capacity_percent = int(plan.workload_utilization * 100)
    capacity_color = "bg-success" if plan.fits_capacity else "bg-warning"

    # Build priority sections
    priority_sections = []

    # Priority 1: At-risk habits (streak protection)
    at_risk_habits = [h for h in plan.contextual_habits if getattr(h, "streak_at_risk", False)]
    if at_risk_habits:
        habit_items = [
            Div(
                Span("🔄", cls="mr-2"),
                Span(getattr(h, "title", "Habit"), cls="text-sm"),
                Span(
                    f"({getattr(h, 'current_streak', 0)}-day streak)",
                    cls="text-xs text-base-content/60 ml-2",
                ),
                cls="flex items-center py-1",
            )
            for h in at_risk_habits[:3]
        ]
        priority_sections.append(
            Div(
                P("PRIORITY 1: At-risk habits", cls="text-xs font-bold text-warning mb-1"),
                *habit_items,
                cls="mb-3",
            )
        )

    # Priority 2: Overdue/urgent tasks
    urgent_tasks = [t for t in plan.contextual_tasks if getattr(t, "is_overdue", False)]
    if urgent_tasks:
        task_items = [
            Div(
                Span("⚠️", cls="mr-2"),
                Span(getattr(t, "title", "Task"), cls="text-sm text-error"),
                cls="flex items-center py-1",
            )
            for t in urgent_tasks[:3]
        ]
        priority_sections.append(
            Div(
                P("PRIORITY 2: Overdue tasks", cls="text-xs font-bold text-error mb-1"),
                *task_items,
                cls="mb-3",
            )
        )
    elif plan.tasks:
        # Show regular tasks if no urgent ones
        task_items = [
            Div(
                Span("✅", cls="mr-2"),
                Span(getattr(t, "title", "Task"), cls="text-sm"),
                cls="flex items-center py-1",
            )
            for t in plan.contextual_tasks[:3]
        ]
        if task_items:
            priority_sections.append(
                Div(
                    P("PRIORITY 2: Tasks", cls="text-xs font-bold text-base-content/60 mb-1"),
                    *task_items,
                    cls="mb-3",
                )
            )

    # Priority 3: Learning
    if plan.learning and plan.contextual_knowledge:
        learning_items = [
            Div(
                Span("📚", cls="mr-2"),
                Span(getattr(k, "title", "Knowledge"), cls="text-sm"),
                Span(
                    f"({getattr(k, 'estimated_time_minutes', 30)} min)",
                    cls="text-xs text-base-content/60 ml-2",
                ),
                cls="flex items-center py-1",
            )
            for k in plan.contextual_knowledge[:2]
        ]
        priority_sections.append(
            Div(
                P("PRIORITY 3: Learning", cls="text-xs font-bold text-base-content/60 mb-1"),
                *learning_items,
                cls="mb-3",
            )
        )

    # Fallback if no priorities
    if not priority_sections:
        if plan.rationale:
            priority_sections.append(
                Div(P(plan.rationale, cls="text-sm text-base-content/60 italic"))
            )
        else:
            priority_sections.append(
                Div(P("No specific priorities for today", cls="text-sm text-base-content/60"))
            )

    # Warnings
    warnings_section = None
    if plan.warnings:
        warnings_section = Div(
            *[
                Div(
                    Span("⚠️", cls="mr-1 text-xs"),
                    Span(w, cls="text-xs text-warning"),
                    cls="flex items-center",
                )
                for w in plan.warnings[:2]
            ],
            cls="mt-3 pt-3 border-t border-base-300",
        )

    return Div(
        # Header
        Div(
            Span("📅", cls="text-2xl mr-3"),
            Span("TODAY'S FOCUS", cls="font-bold text-base-content"),
            cls="flex items-center mb-3",
        ),
        # Capacity bar
        Div(
            P(f"Capacity: {capacity_percent}% utilized", cls="text-xs text-base-content/60 mb-1"),
            Div(
                Div(
                    cls=f"h-2 {capacity_color} rounded-full transition-all",
                    style=f"width: {min(capacity_percent, 100)}%",
                ),
                cls="h-2 bg-base-200 rounded-full w-full",
            ),
            cls="mb-4",
        ),
        # Priority sections
        *priority_sections,
        # Warnings
        warnings_section,
        cls="bg-primary/5 border border-accent/20 rounded-xl p-4 mb-6",
    )


def _alignment_breakdown(alignment: "LifePathAlignment") -> Div:
    """Life path alignment breakdown showing 5 dimensions.

    Displays the overall alignment score with dimension-by-dimension breakdown.

    Args:
        alignment: LifePathAlignment from intelligence service (REQUIRED)
    """
    # Overall score and status
    overall_percent = int(alignment.overall_score * 100)
    level_colors = {
        "flourishing": "text-success",
        "aligned": "text-primary",
        "exploring": "text-base-content/60",
        "drifting": "text-warning",
    }
    level_color = level_colors.get(alignment.alignment_level, "text-base-content/60")
    level_icon = {"flourishing": "✓", "aligned": "✓", "exploring": "~", "drifting": "!"}.get(
        alignment.alignment_level, "~"
    )

    # Dimension bars
    dimensions = [
        ("Knowledge", alignment.knowledge_score, "📚"),
        ("Activity", alignment.activity_score, "✅"),
        ("Goals", alignment.goal_score, "🎯"),
        ("Principles", alignment.principle_score, "⚖️"),
        ("Momentum", alignment.momentum_score, "🚀"),
    ]

    dimension_bars = []
    for name, score, icon in dimensions:
        score_percent = int(score * 100)
        dimension_bars.append(
            Div(
                Div(
                    Span(icon, cls="text-sm w-6"),
                    Span(name, cls="text-xs text-base-content/60 w-20"),
                    Div(
                        Div(
                            cls="h-2 bg-primary rounded-full",
                            style=f"width: {score_percent}%",
                        ),
                        cls="h-2 bg-base-200 rounded-full flex-1",
                    ),
                    Span(f"{score_percent}%", cls="text-xs text-base-content/60 w-10 text-right"),
                    cls="flex items-center gap-2",
                ),
                cls="py-1",
            )
        )

    # Strengths and gaps
    insights_section = []
    if alignment.strengths:
        insights_section.append(
            Div(
                P("Strengths:", cls="text-xs font-semibold text-success mb-1"),
                P(alignment.strengths[0], cls="text-xs text-base-content/60"),
                cls="flex-1",
            )
        )
    if alignment.gaps:
        insights_section.append(
            Div(
                P("Gaps:", cls="text-xs font-semibold text-warning mb-1"),
                P(alignment.gaps[0], cls="text-xs text-base-content/60"),
                cls="flex-1",
            )
        )

    return Div(
        # Header with overall score
        Div(
            Span("🎯", cls="text-2xl mr-3"),
            Div(
                Span(f"LIFE PATH ALIGNMENT: {overall_percent}%", cls="font-bold text-base-content"),
                Span(
                    f" {level_icon} {alignment.alignment_level.upper()}",
                    cls=f"text-sm ml-2 {level_color}",
                ),
                cls="flex items-center",
            ),
            cls="flex items-center mb-4",
        ),
        # Dimension breakdown
        Div(*dimension_bars, cls="mb-4"),
        # Insights row
        Div(*insights_section, cls="flex gap-4") if insights_section else None,
        cls="bg-base-200 rounded-xl p-4 mb-6",
    )


def _synergies_card(synergies: "list[CrossDomainSynergy]") -> Div:
    """High-leverage actions card showing cross-domain synergies.

    Displays detected synergies between entities across domains.

    Args:
        synergies: List of CrossDomainSynergy from intelligence service (REQUIRED, may be empty)
    """
    # Empty list is valid data - user genuinely has no synergies
    if len(synergies) == 0:
        return Div(
            Div(
                Span("🚀", cls="text-xl mr-2"),
                Span("HIGH-LEVERAGE ACTIONS", cls="font-bold text-base-content/60"),
                cls="flex items-center mb-2",
            ),
            P("No synergies detected yet", cls="text-sm text-base-content/60"),
            cls="bg-base-200 rounded-lg p-4 mb-6",
        )

    synergy_items = []
    for synergy in synergies[:3]:
        score_percent = int(synergy.synergy_score * 100)

        # Format synergy type arrow
        domain_arrow = f"{synergy.source_domain.title()}→{synergy.target_domain.title()}"

        synergy_items.append(
            Div(
                # Header with score
                Div(
                    Span(domain_arrow, cls="font-medium text-sm text-base-content"),
                    Span(f"(score: {score_percent}%)", cls="text-xs text-base-content/60 ml-2"),
                    cls="flex items-center mb-1",
                ),
                # Rationale
                P(
                    synergy.rationale[:80] + "..."
                    if len(synergy.rationale) > 80
                    else synergy.rationale,
                    cls="text-xs text-base-content/60",
                ),
                # Targets count
                P(
                    f"Affects {len(synergy.target_uids)} {synergy.target_domain}(s)",
                    cls="text-xs text-primary mt-1",
                ),
                cls="py-2 border-b border-base-300 last:border-0",
            )
        )

    return Div(
        # Header
        Div(
            Span("🚀", cls="text-xl mr-2"),
            Span("HIGH-LEVERAGE ACTIONS", cls="font-bold text-base-content"),
            cls="flex items-center mb-3",
        ),
        # Synergy items
        *synergy_items,
        cls="bg-base-200 rounded-xl p-4 mb-6",
    )


def _learning_steps_card(steps: "list[LearningStep]") -> Div:
    """Next learning steps card showing prioritized learning recommendations.

    Displays recommended knowledge units to learn with context.

    Args:
        steps: List of LearningStep from intelligence service (REQUIRED, may be empty)
    """
    # Empty list is valid data - no recommendations available
    if len(steps) == 0:
        return Div(
            Div(
                Span("📚", cls="text-xl mr-2"),
                Span("NEXT LEARNING STEPS", cls="font-bold text-base-content/60"),
                cls="flex items-center mb-2",
            ),
            P("No learning recommendations available", cls="text-sm text-base-content/60"),
            cls="bg-base-200 rounded-lg p-4 mb-6",
        )

    step_items = []
    for i, step in enumerate(steps[:3], 1):
        priority_percent = int(step.priority_score * 100)

        step_items.append(
            A(
                Div(
                    # Number and title
                    Div(
                        Span(f"{i}.", cls="font-bold text-primary mr-2"),
                        Span(step.title, cls="font-medium text-base-content"),
                        cls="flex items-center mb-1",
                    ),
                    # Stats row
                    Div(
                        Span(f"Priority: {priority_percent}%", cls="text-xs text-base-content/60"),
                        Span("|", cls="mx-2 text-base-content/60"),
                        Span(
                            f"{step.estimated_time_minutes} min", cls="text-xs text-base-content/60"
                        ),
                        cls="flex items-center mb-1",
                    ),
                    # Context
                    Div(
                        Span(
                            f"Aligns: {len(step.aligns_with_goals)} goals",
                            cls="text-xs text-primary",
                        )
                        if step.aligns_with_goals
                        else None,
                        Span("|", cls="mx-2 text-base-content/60")
                        if step.aligns_with_goals and step.unlocks_count
                        else None,
                        Span(
                            f"Unlocks: {step.unlocks_count}",
                            cls="text-xs text-primary",
                        )
                        if step.unlocks_count
                        else None,
                        cls="flex items-center",
                    )
                    if step.aligns_with_goals or step.unlocks_count
                    else None,
                    cls="py-2 border-b border-base-300 last:border-0",
                ),
                href=f"/learning/ku/{step.ku_uid}",
                cls="block hover:bg-base-200/50 -mx-2 px-2 rounded transition-colors",
            )
        )

    return Div(
        # Header
        Div(
            Span("📚", cls="text-xl mr-2"),
            Span("NEXT LEARNING STEPS", cls="font-bold text-base-content"),
            cls="flex items-center mb-3",
        ),
        # Step items
        *step_items,
        cls="bg-base-200 rounded-xl p-4 mb-6",
    )


__all__ = [
    "ChoicesDomainView",
    "DomainSummaryCard",
    "EventsDomainView",
    "GoalsDomainView",
    "HabitsDomainView",
    "KnowledgeDomainView",
    "LearningPathsDomainView",
    "LearningStepsDomainView",
    "OverviewView",
    "PrinciplesDomainView",
    "TasksDomainView",
]
