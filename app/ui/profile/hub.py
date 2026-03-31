"""Profile hub page — live actionable hub for learning state.

The /profile page shows the user's active learning state: Kus they're
interacting with, lessons being studied, exercises with Submit buttons,
submissions (tabbed: My Submissions | Submit | Request Report),
and recent reports.

See: /docs/patterns/HUB_PAGE_PATTERN.md
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fasthtml.common import A, Div, P, Span

from core.services.user.unified_user_context import UserContext
from ui.patterns.empty_state import EmptyState

# ---------------------------------------------------------------------------
# Activity domain configuration
# ---------------------------------------------------------------------------

_ACTIVITY_DOMAIN_CONFIG: dict[str, dict[str, str]] = {
    "tasks": {
        "label": "Task",
        "badge_cls": "bg-blue-500/10 text-blue-600",
        "route": "/tasks/detail",
    },
    "goals": {
        "label": "Goal",
        "badge_cls": "bg-emerald-500/10 text-emerald-600",
        "route": "/goals/detail",
    },
    "habits": {
        "label": "Habit",
        "badge_cls": "bg-violet-500/10 text-violet-600",
        "route": "/habits/detail",
    },
    "events": {
        "label": "Event",
        "badge_cls": "bg-orange-500/10 text-orange-600",
        "route": "/events/detail",
    },
    "choices": {
        "label": "Choice",
        "badge_cls": "bg-pink-500/10 text-pink-600",
        "route": "/choices/detail",
    },
    "principles": {
        "label": "Principle",
        "badge_cls": "bg-slate-500/10 text-slate-600",
        "route": "/principles/detail",
    },
}

_DOMAIN_ORDER: dict[str, int] = {d: i for i, d in enumerate(_ACTIVITY_DOMAIN_CONFIG)}


def ProfileHubView(context: UserContext) -> Div:
    """Profile hub — live learning state with actionable sections."""
    return Div(
        _personal_header(context),
        _activities_section(context),
        _knowledge_section(context),
        _path_steps_section(context),
        _exercises_section(context),
        _submissions_section(),
        _reports_section(),
        _nous_section(),
        _settings_link(),
    )


# ---------------------------------------------------------------------------
# Section header helper
# ---------------------------------------------------------------------------


def _section_header(title: str, view_all_href: str, count: int = 0) -> Div:
    """Section title with optional count badge and 'View all' link."""
    parts: list[Any] = [
        Span(
            title,
            cls="text-xs font-semibold uppercase tracking-wider text-muted-foreground",
        ),
    ]
    if count > 0:
        parts.append(
            Span(
                str(count),
                cls="text-xs font-medium bg-primary/10 text-primary px-2 py-0.5 rounded-full",
            )
        )
    parts.append(
        A(
            "View all",
            href=view_all_href,
            cls="ml-auto text-xs text-muted-foreground hover:text-primary",
        )
    )
    return Div(*parts, cls="flex items-center gap-2 mb-3")


# ---------------------------------------------------------------------------
# Compact row helper
# ---------------------------------------------------------------------------


def _compact_row(
    title: str,
    href: str,
    badges: list[Any] | None = None,
    action: Any | None = None,
) -> Div:
    """Compact row: clickable title + optional badges + optional action."""
    left = A(
        title,
        href=href,
        cls="text-sm font-medium text-foreground hover:text-primary truncate",
    )
    badge_items = badges or []
    parts: list[Any] = [left, *badge_items]
    if action is not None:
        parts.append(action)
    return Div(
        *parts,
        cls="flex items-center gap-2 py-2 px-3 rounded-lg hover:bg-muted/50 transition-colors",
    )


# ---------------------------------------------------------------------------
# Activities section — top 5 urgent/relevant items across 6 Activity Domains
# ---------------------------------------------------------------------------


def _score_task(uid: str, context: UserContext) -> tuple[float, str, str]:
    """Return (score, badge_text, badge_cls) for a task."""
    score = 10.0
    badge_text = "Active"
    badge_cls = "bg-muted text-muted-foreground"

    if uid in context.overdue_task_uids:
        score = 100.0
        badge_text = "Overdue"
        badge_cls = "bg-destructive/10 text-destructive"
    elif uid in context.today_task_uids:
        score = 70.0
        badge_text = "Today"
        badge_cls = "bg-warning/10 text-warning"
    elif uid in context.this_week_task_uids:
        score = 40.0
        badge_text = "This week"
        badge_cls = "bg-muted text-muted-foreground"

    if uid == context.current_task_focus:
        score += 20.0
    score += context.task_priorities.get(uid, 0.0) * 15.0
    if uid in context.blocked_task_uids:
        score += 5.0
        badge_text = "Blocked"
        badge_cls = "bg-destructive/10 text-destructive"

    return score, badge_text, badge_cls


def _score_goal(uid: str, context: UserContext) -> tuple[float, str, str]:
    """Return (score, badge_text, badge_cls) for a goal."""
    if uid in context.at_risk_goals:
        return 70.0, "At risk", "bg-destructive/10 text-destructive"

    progress = context.goal_progress.get(uid, 0.0)
    if progress > 0:
        return 10.0, f"{progress:.0%}", "bg-success/10 text-success"
    return 10.0, "Active", "bg-muted text-muted-foreground"


def _score_habit(uid: str, context: UserContext) -> tuple[float, str, str]:
    """Return (score, badge_text, badge_cls) for a habit."""
    if uid in context.at_risk_habits:
        return 70.0, "At risk", "bg-destructive/10 text-destructive"

    streak = context.habit_streaks.get(uid, 0)
    if streak > 0:
        return 40.0, f"{streak}d streak", "bg-success/10 text-success"
    if uid in context.daily_habits:
        return 15.0, "Daily", "bg-muted text-muted-foreground"
    return 10.0, "Active", "bg-muted text-muted-foreground"


def _score_event(uid: str, context: UserContext) -> tuple[float, str, str]:
    """Return (score, badge_text, badge_cls) for an event."""
    if uid in context.today_event_uids:
        return 100.0, "Today", "bg-warning/10 text-warning"
    if uid in context.upcoming_event_uids[:3]:
        return 40.0, "Upcoming", "bg-muted text-muted-foreground"
    return 10.0, "Scheduled", "bg-muted text-muted-foreground"


def _score_choice(uid: str, context: UserContext) -> tuple[float, str, str]:
    """Return (score, badge_text, badge_cls) for a choice."""
    if uid in context.pending_choice_uids:
        return 100.0, "Pending", "bg-warning/10 text-warning"
    return 10.0, "Resolved", "bg-muted text-muted-foreground"


def _score_principle(uid: str, context: UserContext) -> tuple[float, str, str]:
    """Return (score, badge_text, badge_cls) for a principle."""
    score = 10.0
    if uid == context.current_principle_focus:
        return 20.0, "Focus", "bg-primary/10 text-primary"
    if uid in context.core_principle_uids:
        return score, "Core", "bg-muted text-muted-foreground"
    return score, "Active", "bg-muted text-muted-foreground"


_DomainScorer = Callable[[str, "UserContext"], tuple[float, str, str]]

_DOMAIN_SCORERS: dict[str, _DomainScorer] = {
    "tasks": _score_task,
    "goals": _score_goal,
    "habits": _score_habit,
    "events": _score_event,
    "choices": _score_choice,
    "principles": _score_principle,
}


def _score_for_domain(domain: str, uid: str, context: UserContext) -> tuple[float, str, str]:
    """Dispatch scoring to the domain-specific function."""
    scorer = _DOMAIN_SCORERS.get(domain)
    if scorer is None:
        return 0.0, "", ""
    return scorer(uid, context)


def _rank_activity_items(context: UserContext, limit: int = 5) -> list[dict[str, Any]]:
    """Select the top *limit* most urgent/relevant items across all 6 Activity Domains."""
    candidates: list[tuple[float, int, str, dict[str, Any]]] = []

    for domain, config in _ACTIVITY_DOMAIN_CONFIG.items():
        for rich_item in context.entities_rich.get(domain, []):
            entity = rich_item.get("entity", {})
            uid = entity.get("uid", "")
            title = entity.get("title", uid)
            if not uid:
                continue

            score, meta_text, meta_cls = _score_for_domain(domain, uid, context)

            candidates.append(
                (
                    -score,
                    _DOMAIN_ORDER.get(domain, 99),
                    title,
                    {
                        "uid": uid,
                        "title": title,
                        "domain": domain,
                        "href": f"{config['route']}?uid={uid}",
                        "domain_label": config["label"],
                        "domain_badge_cls": config["badge_cls"],
                        "meta_badge_text": meta_text,
                        "meta_badge_cls": meta_cls,
                    },
                )
            )

    candidates.sort(key=_candidate_sort_key)
    return [c[3] for c in candidates[:limit]]


def _candidate_sort_key(
    item: tuple[float, int, str, dict[str, Any]],
) -> tuple[float, int, str]:
    """Sort key for activity candidates: (-score, domain_order, title)."""
    return (item[0], item[1], item[2])


def _activities_section(context: UserContext) -> Div:
    """Top 5 urgent/relevant items across all 6 Activity Domains."""
    ranked = _rank_activity_items(context)

    rows: list[Div] = []
    for item in ranked:
        domain_badge = Span(
            item["domain_label"],
            cls=f"text-[10px] font-medium px-1.5 py-0.5 rounded {item['domain_badge_cls']}",
        )
        badges: list[Any] = [domain_badge]
        if item["meta_badge_text"]:
            badges.append(
                Span(
                    item["meta_badge_text"],
                    cls=f"text-[10px] font-medium px-1.5 py-0.5 rounded {item['meta_badge_cls']}",
                )
            )
        rows.append(_compact_row(item["title"], item["href"], badges))

    total_count = sum(len(context.entities_rich.get(d, [])) for d in _ACTIVITY_DOMAIN_CONFIG)

    content: Div
    if rows:
        content = Div(*rows)
    else:
        content = EmptyState(
            "No activities yet",
            description="Upload activity data to see tasks, goals, habits, and more here.",
            action_text="Upload Activity Data",
            action_href="/upload",
            cls="py-6",
        )

    return Div(
        _section_header("Activities", "/activity-reports", total_count),
        content,
        cls="mb-6",
    )


# ---------------------------------------------------------------------------
# Knowledge section — bookmarked + recently viewed Kus
# ---------------------------------------------------------------------------


def _knowledge_section(context: UserContext) -> Div:
    """Kus the user is interacting with — bookmarked and recently viewed."""
    # Merge bookmarked + recently viewed, preserving order (bookmarked first)
    seen: set[str] = set()
    ku_uids: list[str] = []
    for uid in context.ku_bookmarked_uids:
        if uid not in seen:
            ku_uids.append(uid)
            seen.add(uid)
    for uid in context.recently_viewed_ku_uids:
        if uid not in seen:
            ku_uids.append(uid)
            seen.add(uid)

    # Look up in knowledge_units_rich for titles and metadata
    rows: list[Div] = []
    for uid in ku_uids[:10]:
        rich = context.knowledge_units_rich.get(uid)
        if rich:
            ku_data = rich.get("ku", {})
            title = ku_data.get("title", uid)
            namespace = ku_data.get("namespace", "")
        else:
            title = uid
            namespace = ""

        badges: list[Any] = []
        if uid in context.ku_bookmarked_uids:
            badges.append(
                Span(
                    "pinned",
                    cls="text-[10px] font-medium bg-amber-500/10 text-amber-600 px-1.5 py-0.5 rounded",
                )
            )
        if namespace:
            badges.append(
                Span(
                    namespace,
                    cls="text-[10px] font-medium bg-muted text-muted-foreground px-1.5 py-0.5 rounded",
                )
            )
        mastery = context.knowledge_mastery.get(uid)
        if mastery is not None and mastery > 0:
            badges.append(
                Span(
                    f"{mastery:.0%}",
                    cls="text-[10px] font-medium bg-success/10 text-success px-1.5 py-0.5 rounded",
                )
            )

        rows.append(_compact_row(title, f"/ku/read?uid={uid}", badges))

    content: Div
    if rows:
        content = Div(*rows)
    else:
        content = EmptyState(
            "No knowledge units yet",
            description="Browse and bookmark Kus to see them here.",
            action_text="Explore Knowledge",
            action_href="/ku",
            cls="py-6",
        )

    return Div(
        _section_header("Knowledge", "/ku", len(ku_uids)),
        content,
        cls="mb-6",
    )


# ---------------------------------------------------------------------------
# Path Steps section — currently studying
# ---------------------------------------------------------------------------


def _path_steps_section(context: UserContext) -> Div:
    """Path steps the user is actively studying (via IN_PROGRESS relationship)."""
    rows: list[Div] = []
    for ps in context.current_path_steps:
        rows.append(
            _compact_row(
                ps["title"],
                f"/path-steps/get?uid={ps['uid']}",
            )
        )

    content: Div
    if rows:
        content = Div(*rows)
    else:
        content = EmptyState(
            "No active path steps",
            description="Path steps appear here when you start learning their knowledge units.",
            action_text="Browse Path Steps",
            action_href="/path-steps",
            cls="py-6",
        )

    return Div(
        _section_header("Path Steps", "/path-steps", len(rows)),
        content,
        cls="mb-6",
    )


# ---------------------------------------------------------------------------
# Exercises section — assigned work with Submit buttons
# ---------------------------------------------------------------------------


def _exercises_section(context: UserContext) -> Div:
    """Assigned exercises with inline Submit action."""
    rows: list[Div] = []

    # Unsubmitted exercises — primary actionable items
    for ex in context.unsubmitted_exercises:
        badges: list[Any] = []
        if ex.get("due_date"):
            badges.append(
                Span(
                    f"Due {ex['due_date']}",
                    cls="text-[10px] font-medium bg-warning/10 text-warning px-1.5 py-0.5 rounded",
                )
            )
        submit_btn = A(
            "Submit",
            href=f"/submit?exercise_uid={ex['uid']}",
            cls="text-xs font-medium bg-primary text-primary-foreground px-3 py-1 rounded hover:bg-primary/90 whitespace-nowrap",
        )
        rows.append(
            _compact_row(ex["title"], f"/exercises/read?uid={ex['uid']}", badges, submit_btn)
        )

    # Pending revised exercises — revision requests
    for rev in context.pending_revised_exercises:
        badges_rev: list[Any] = [
            Span(
                f"Revision #{rev.get('revision_number', 1)}",
                cls="text-[10px] font-medium bg-destructive/10 text-destructive px-1.5 py-0.5 rounded",
            )
        ]
        submit_btn = A(
            "Submit",
            href=f"/submit?exercise_uid={rev['uid']}",
            cls="text-xs font-medium bg-primary text-primary-foreground px-3 py-1 rounded hover:bg-primary/90 whitespace-nowrap",
        )
        rows.append(
            _compact_row(rev["title"], f"/exercises/read?uid={rev['uid']}", badges_rev, submit_btn)
        )

    content: Div
    if rows:
        content = Div(*rows)
    else:
        content = EmptyState(
            "No exercises assigned",
            description="Exercises appear here when a teacher assigns them to your group.",
            action_text="Browse Exercises",
            action_href="/exercises",
            cls="py-6",
        )

    return Div(
        _section_header("Exercises", "/exercises", context.assigned_exercise_count),
        content,
        cls="mb-6",
    )


# ---------------------------------------------------------------------------
# Submissions section — tabbed (My Submissions | Submit | Request Report)
# ---------------------------------------------------------------------------


def _sub_tab_button(label: str, tab_id: str) -> Any:
    """Tab button for the submissions section (Alpine.js state)."""
    return A(
        label,
        role="tab",
        cls="px-3 py-1.5 text-xs font-medium cursor-pointer transition-colors rounded-t border-b-2",
        **{
            ":aria-selected": f"subTab === '{tab_id}'",
            "@click": f"subTab = '{tab_id}'; htmx.trigger('#sub-tab-panel-{tab_id}', 'tab-activate')",
            ":class": f"subTab === '{tab_id}' ? 'border-primary text-primary bg-background' : 'border-transparent text-muted-foreground hover:text-foreground hover:border-border'",
        },
    )


def _sub_tab_panel(tab_id: str, hx_get: str, default: bool = False) -> Div:
    """Tab panel with HTMX lazy-loaded content for submissions section."""
    attrs: dict[str, str] = {
        "x-show": f"subTab === '{tab_id}'",
        "hx-get": hx_get,
        "hx-trigger": "load" if default else "tab-activate once",
        "hx-swap": "innerHTML",
    }
    if not default:
        attrs["x-cloak"] = ""

    return Div(
        P("Loading...", cls="text-center text-muted-foreground py-4"),
        id=f"sub-tab-panel-{tab_id}",
        role="tabpanel",
        **attrs,
    )


def _submissions_section() -> Div:
    """Submissions section with Alpine.js tabs: My Submissions | Submit | Request Report."""
    return Div(
        Span(
            "Submissions",
            cls="text-xs font-semibold uppercase tracking-wider text-muted-foreground",
        ),
        Div(
            Div(
                _sub_tab_button("My Submissions", "list"),
                _sub_tab_button("Submit", "submit"),
                _sub_tab_button("Request Report", "report"),
                role="tablist",
                cls="flex gap-1 border-b border-border mb-3",
            ),
            _sub_tab_panel("list", "/submissions/list", default=True),
            _sub_tab_panel("submit", "/api/profile/submissions/submit-form"),
            _sub_tab_panel("report", "/api/profile/submissions/report-form"),
            **{"x-data": "{ subTab: 'list' }"},
            cls="mt-3",
        ),
        cls="mb-6",
    )


# ---------------------------------------------------------------------------
# Reports section — HTMX lazy-loaded summaries
# ---------------------------------------------------------------------------


def _reports_section() -> Div:
    """Reports section with HTMX lazy-loaded summaries."""
    skeleton = Div(
        Div(cls="h-4 bg-muted rounded w-3/4 animate-pulse"),
        Div(cls="h-4 bg-muted rounded w-1/2 animate-pulse mt-2"),
        Div(cls="h-4 bg-muted rounded w-2/3 animate-pulse mt-2"),
        cls="py-3 px-3",
    )

    return Div(
        # Exercise Reports
        Div(
            _section_header("Exercise Reports", "/exercise-reports"),
            Div(
                skeleton,
                id="exercise-reports-summary",
                hx_get="/api/profile/reports/exercise-summary",
                hx_trigger="load",
                hx_swap="innerHTML",
            ),
            cls="mb-4",
        ),
        # Activity Reports
        Div(
            _section_header("Activity Reports", "/activity-reports"),
            Div(
                skeleton,
                id="activity-reports-summary",
                hx_get="/api/profile/reports/activity-summary",
                hx_trigger="load",
                hx_swap="innerHTML",
            ),
            cls="mb-4",
        ),
        cls="mb-6",
    )


# ---------------------------------------------------------------------------
# Personal header — Focus + Velocity (preserved from original)
# ---------------------------------------------------------------------------


def _personal_header(context: UserContext) -> Div:
    """Focus + Velocity compact header."""
    return Div(_focus_line(context), _velocity_line(context), cls="mb-2")


def _focus_line(context: UserContext) -> Div:
    """Current task focus — compact inline."""
    if not context.current_task_focus:
        return Div(
            Span("\U0001f3af", cls="text-lg mr-2"),
            Span("No current focus set", cls="text-sm text-muted-foreground"),
            cls="flex items-center mb-2",
        )

    task_title = "Current Task"
    for task_data in context.entities_rich.get("tasks", []):
        task = task_data.get("entity", {})
        if task.get("uid") == context.current_task_focus:
            task_title = task.get("title", "Current Task")
            break

    return Div(
        Span("\U0001f3af", cls="text-lg mr-2"),
        Span("Focus: ", cls="text-sm font-medium text-muted-foreground"),
        Span(task_title, cls="text-sm font-medium text-primary"),
        cls="flex items-center mb-2",
    )


def _velocity_line(context: UserContext) -> Div:
    """Overall velocity — compact inline indicator."""
    total_velocity = sum(context.velocity_by_domain.values())
    total_time = sum(context.time_invested_hours_by_domain.values())

    if total_velocity > 0.5:
        icon, label, color = "\U0001f680", "Strong Momentum", "text-success"
    elif total_velocity > 0:
        icon, label, color = "\U0001f4c8", "Building", "text-primary"
    elif total_velocity > -0.3:
        icon, label, color = "\u27a1\ufe0f", "Steady", "text-muted-foreground"
    else:
        icon, label, color = "\U0001f4c9", "Slowing", "text-warning"

    return Div(
        Span(icon, cls="text-lg mr-2"),
        Span(label, cls=f"text-sm font-medium {color}"),
        Span(" \u00b7 ", cls="text-foreground/30 mx-2"),
        Span(f"{total_time:.1f}h invested", cls="text-sm text-muted-foreground"),
        cls="flex items-center mb-4",
    )


# ---------------------------------------------------------------------------
# Nous — shared knowledge feed (placeholder)
# ---------------------------------------------------------------------------


def _nous_section() -> Div:
    """Nous section — placeholder for the shared knowledge feed.

    Nous will surface RevisedExercise submissions shared by other learners
    in a feed format (blog / news-feed style). This section establishes
    the concept and marks it for future development.
    """
    return Div(
        Span(
            "Nous",
            cls="text-xs font-semibold uppercase tracking-wider text-muted-foreground",
        ),
        Div(
            Div(
                Div(
                    Span("\U0001f4e1", cls="text-2xl"),
                    Span(
                        "Nous",
                        cls="text-base font-semibold text-foreground",
                    ),
                    Span(
                        "Coming Soon",
                        cls="ml-auto text-xs font-medium bg-muted text-muted-foreground px-2 py-0.5 rounded-full",
                    ),
                    cls="flex items-center gap-2",
                ),
                cls="mb-3",
            ),
            P(
                "A shared knowledge feed of revised exercises from the community "
                "\u2014 learn from how others transfer and apply knowledge.",
                cls="text-sm text-muted-foreground mb-3",
            ),
            Div(
                Span("\U0001f4dd Revised Exercises", cls="text-xs text-muted-foreground"),
                Span(" \u00b7 ", cls="text-foreground/20"),
                Span("\U0001f465 Community Shared", cls="text-xs text-muted-foreground"),
                Span(" \u00b7 ", cls="text-foreground/20"),
                Span("\U0001f4f0 Feed Format", cls="text-xs text-muted-foreground"),
                cls="flex items-center gap-1",
            ),
            cls="bg-background rounded-xl p-5 shadow-sm border border-dashed border-border",
        ),
        cls="mb-6",
    )


# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------


def _settings_link() -> Div:
    """Compact settings + upload links at the bottom."""
    return Div(
        Div(
            A(
                Span("\u2699\ufe0f", cls="mr-2"),
                "Settings",
                href="/profile/settings",
                cls="text-sm text-muted-foreground hover:text-foreground",
            ),
            A(
                Span("\u2b06\ufe0f", cls="mr-2"),
                "Upload Activity Data",
                href="/upload",
                cls="text-sm text-muted-foreground hover:text-foreground ml-6",
            ),
            cls="flex items-center gap-2",
        ),
        cls="mt-4 pt-6 border-t border-border",
    )
