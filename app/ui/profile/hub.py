"""Profile hub page — live actionable hub for learning state.

The /profile page shows the user's active learning state: Kus they're
interacting with, path steps being studied, exercises with Submit buttons,
submissions (tabbed: My Submissions | Submit | Request Report),
and recent reports.

See: /docs/patterns/HUB_PAGE_PATTERN.md
"""

from __future__ import annotations

from typing import Any

from fasthtml.common import H1, A, Div, P, Span
from monsterui.franken import UkIcon

from core.services.user.unified_user_context import UserContext
from ui.patterns.empty_state import EmptyState

# ---------------------------------------------------------------------------
# Activity domain tab configuration
# ---------------------------------------------------------------------------

# (label, tab_id, icon, hex_color) — mirrors ActivityDomainNav domain config
_ACTIVITY_TABS: list[tuple[str, str, str, str]] = [
    ("Tasks", "tasks", "check-square", "#3B82F6"),
    ("Goals", "goals", "target", "#F59E0B"),
    ("Habits", "habits", "repeat", "#10B981"),
    ("Events", "events", "calendar", "#8B5CF6"),
    ("Choices", "choices", "git-branch", "#F97316"),
    ("Principles", "principles", "compass", "#EC4899"),
]


def ProfileHubView(context: UserContext) -> Div:
    """Profile hub — Activity Domains + activity report request."""
    return Div(
        _activities_section(),
        _request_activity_report_section(),
        _nous_section(),
        _settings_link(),
        _personal_header(context),
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
            "View all →",
            href=view_all_href,
            cls="ml-auto text-xs font-medium text-primary/60 hover:text-primary transition-colors",
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
# Activities section — tabbed view of all 6 Activity Domains
# ---------------------------------------------------------------------------


_TAB_LINK_BASE = (
    "display: inline-flex; align-items: center; gap: 0.4rem; "
    "padding: 0.65rem 1rem; font-size: 0.72rem; font-weight: 600; "
    "letter-spacing: 0.07em; text-transform: uppercase; "
    "text-decoration: none; border-bottom: 3px solid transparent; "
    "white-space: nowrap; cursor: pointer; transition: opacity 0.15s; "
    "background: none; border-top: none; border-left: none; border-right: none;"
)


def _activity_tab_button(label: str, tab_id: str, icon: str, color: str) -> Any:
    """Tab button styled to match ActivityDomainNav — icon + uppercase + colored border."""
    return A(
        UkIcon(icon, cls="size-3"),
        label,
        role="tab",
        style=_TAB_LINK_BASE,
        **{
            ":aria-selected": f"actTab === '{tab_id}'",
            "@click": f"actTab = '{tab_id}'; htmx.trigger('#act-tab-panel-{tab_id}', 'tab-activate')",
            ":style": (
                f"actTab === '{tab_id}' ? "
                f"'{_TAB_LINK_BASE} color: {color}; border-bottom-color: {color}; font-weight: 800;' : "
                f"'{_TAB_LINK_BASE} color: var(--muted-foreground);'"
            ),
        },
    )


def _activity_tab_panel(tab_id: str, default: bool = False) -> Div:
    """Tab panel with HTMX lazy-loaded content from the domain list-fragment endpoint."""
    attrs: dict[str, str] = {
        "x-show": f"actTab === '{tab_id}'",
        "hx-get": f"/api/profile/{tab_id}/preview",
        "hx-trigger": "load" if default else "tab-activate once",
        "hx-swap": "innerHTML",
    }
    if not default:
        attrs["x-cloak"] = ""

    return Div(
        P("Loading...", cls="text-center text-muted-foreground py-4"),
        id=f"act-tab-panel-{tab_id}",
        role="tabpanel",
        **attrs,
    )


def _activities_section() -> Div:
    """Activity Domains — tabbed: Tasks | Goals | Habits | Events | Choices | Principles.

    Each tab lazily loads its domain list-fragment (same view as the full domain page).
    """
    return Div(
        Div(
            *[
                _activity_tab_button(label, tab_id, icon, color)
                for label, tab_id, icon, color in _ACTIVITY_TABS
            ],
            role="tablist",
            style=(
                "display: flex; flex-wrap: wrap; "
                "border-top: 1px solid var(--border); "
                "border-bottom: 2px solid var(--border); "
                "background-color: var(--background); "
                "margin-bottom: 1.25rem;"
            ),
        ),
        *[
            _activity_tab_panel(tab_id, default=(i == 0))
            for i, (_, tab_id, _, _) in enumerate(_ACTIVITY_TABS)
        ],
        **{"x-data": "{ actTab: 'tasks' }"},
        cls="mb-6",
    )


# ---------------------------------------------------------------------------
# Request Activity Report section — inline form below Activity Domains
# ---------------------------------------------------------------------------


def _request_activity_report_section() -> Div:
    """Activity Report request form — lazily loaded below the Activity Domains tabs."""
    from ui.patterns.generate_report import (
        render_activity_report_request_card,
        render_recent_reports_section,
    )

    return Div(
        render_activity_report_request_card(),
        render_recent_reports_section(),
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

        rows.append(_compact_row(title, f"/explore/ku/{uid}", badges))

    content: Div
    if rows:
        content = Div(*rows)
    else:
        content = EmptyState(
            "No knowledge units yet",
            description="Browse and bookmark Kus to see them here.",
            action_text="Explore Knowledge",
            action_href="/explore",
            cls="py-6",
        )

    return Div(
        _section_header("Knowledge", "/explore", len(ku_uids)),
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
                f"/explore/ps/{ps['uid']}",
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
            action_href="/explore",
            cls="py-6",
        )

    return Div(
        _section_header("Path Steps", "/explore", len(rows)),
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
        rows.append(_compact_row(ex["title"], f"/exercises/{ex['uid']}/view", badges, submit_btn))

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
            _compact_row(rev["title"], f"/exercises/{rev['uid']}/view", badges_rev, submit_btn)
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


def submissions_section() -> Div:
    """Submissions section with Alpine.js tabs: My Submissions | Submit | Request Report | Exercise Reports | Activity Reports."""
    return Div(
        Div(
            H1("Submissions", cls="text-lg font-bold text-foreground whitespace-nowrap"),
            Div(
                _sub_tab_button("My Submissions", "list"),
                _sub_tab_button("Submit", "submit"),
                _sub_tab_button("Request Report", "report"),
                _sub_tab_button("Exercise Reports", "exercise-reports"),
                _sub_tab_button("Activity Reports", "activity-reports"),
                role="tablist",
                cls="flex gap-1 border-b border-border",
            ),
            cls="flex items-end gap-6 mb-3",
        ),
        _sub_tab_panel("list", "/submissions/list", default=True),
        _sub_tab_panel("submit", "/api/profile/submissions/submit-form"),
        _sub_tab_panel("report", "/api/profile/submissions/report-form"),
        _sub_tab_panel("exercise-reports", "/reports/list"),
        _sub_tab_panel("activity-reports", "/reports/activity-list"),
        **{"x-data": "{ subTab: 'list' }"},
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
