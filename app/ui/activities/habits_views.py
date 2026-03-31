"""Habits UI view components.

Pure FastHTML components for rendering habit data. No service calls —
routes fetch data and pass it to these components.

Usage:
    from ui.activities.habits_views import HabitList, HabitFilterBar, HabitStatsBar
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    H3,
    A,
    Button,
    Div,
    Form,
    Label,
    Option,
    P,
    Select,
    Small,
    Span,
)

from ui.feedback import PriorityBadge, StatusBadge
from ui.patterns.empty_state import EmptyState
from ui.patterns.page_header import PageHeader
from ui.patterns.relationships.relationship_section import EntityRelationshipsSection
from ui.patterns.stats_grid import StatItem, StatsGrid

if TYPE_CHECKING:
    from fasthtml.common import FT

    from core.models.habit.habit import Habit


def HabitStatsBar(habits: list["Habit"]) -> "FT":
    """Quick stats bar showing habit counts."""
    total = len(habits)
    active = sum(1 for h in habits if h.status and h.status.value in ("active", "in_progress"))
    avg_streak = 0.0
    streaks = [h.current_streak for h in habits if h.current_streak and h.current_streak > 0]
    if streaks:
        avg_streak = sum(streaks) / len(streaks)
    keystone = sum(1 for h in habits if _is_keystone(h))

    stats = [
        StatItem(label="Total", value=total, href="/habits?status=all"),
        StatItem(label="Active", value=active, color="primary", href="/habits?status=active"),
        StatItem(
            label="Avg Streak",
            value=f"{avg_streak:.1f}",
            color="success" if avg_streak > 0 else None,
        ),
        StatItem(label="Keystone", value=keystone, color="warning" if keystone > 0 else None, href="/habits?status=keystone"),
    ]
    return StatsGrid(stats, cols=4)


def HabitFilterBar(
    status_filter: str = "active",
    category_filter: str = "all",
    sort_by: str = "streak",
) -> "FT":
    """Filter and sort controls for the habit list. HTMX-powered."""
    return Form(
        Div(
            Div(
                Label("Status", cls="uk-form-label"),
                Select(
                    Option("Active", value="active", selected=status_filter == "active"),
                    Option("Paused", value="paused", selected=status_filter == "paused"),
                    Option("Completed", value="completed", selected=status_filter == "completed"),
                    Option("Keystone", value="keystone", selected=status_filter == "keystone"),
                    Option("All", value="all", selected=status_filter == "all"),
                    name="status",
                    cls="uk-select uk-form-small",
                ),
                cls="uk-form-controls",
            ),
            Div(
                Label("Category", cls="uk-form-label"),
                Select(
                    Option("All", value="all", selected=category_filter == "all"),
                    Option("Health", value="health", selected=category_filter == "health"),
                    Option("Fitness", value="fitness", selected=category_filter == "fitness"),
                    Option(
                        "Mindfulness",
                        value="mindfulness",
                        selected=category_filter == "mindfulness",
                    ),
                    Option("Learning", value="learning", selected=category_filter == "learning"),
                    Option(
                        "Productivity",
                        value="productivity",
                        selected=category_filter == "productivity",
                    ),
                    Option("Creative", value="creative", selected=category_filter == "creative"),
                    Option("Social", value="social", selected=category_filter == "social"),
                    Option("Financial", value="financial", selected=category_filter == "financial"),
                    name="category",
                    cls="uk-select uk-form-small",
                ),
                cls="uk-form-controls",
            ),
            Div(
                Label("Sort", cls="uk-form-label"),
                Select(
                    Option("Streak", value="streak", selected=sort_by == "streak"),
                    Option("Name", value="name", selected=sort_by == "name"),
                    Option("Recently Created", value="created", selected=sort_by == "created"),
                    name="sort_by",
                    cls="uk-select uk-form-small",
                ),
                cls="uk-form-controls",
            ),
            cls="uk-grid uk-grid-small uk-child-width-1-3@s uk-child-width-auto@m",
            **{"uk-grid": "true"},
        ),
        hx_get="/habits/list-fragment",
        hx_target="#habit-list",
        hx_trigger="change",
        hx_include="[name]",
        cls="uk-margin-bottom",
    )


def HabitList(
    habits: list["Habit"],
    connections_map: dict[str, list[dict[str, str]]] | None = None,
) -> "FT":
    """Render a list of habit cards. Returns a replaceable container for HTMX."""
    if not habits:
        return Div(
            EmptyState(
                title="No habits found",
                description="Upload YAML files to add habits, or adjust your filters.",
                action_text="Upload Habits",
                action_href="/upload",
            ),
            id="habit-list",
        )

    cards = [
        HabitCard(habit, connections_map.get(habit.uid, []) if connections_map else [])
        for habit in habits
    ]
    return Div(*cards, id="habit-list", cls="uk-margin-top")


def HabitCard(
    habit: "Habit",
    connections: list[dict[str, str]] | None = None,
) -> "FT":
    """Single habit card with streak, polarity, category, and connections."""
    is_completed = habit.status and habit.status.value == "completed"
    is_paused = habit.status and habit.status.value == "paused"

    # Status toggle button
    if is_completed:
        new_status = "active"
        icon = "check"
        icon_cls = "uk-text-success"
    elif is_paused:
        new_status = "active"
        icon = "pause"
        icon_cls = "uk-text-warning"
    else:
        new_status = "completed"
        icon = "repeat"
        icon_cls = ""

    toggle_btn = Button(
        Span(
            cls=f"uk-icon {icon_cls}",
            **{"uk-icon": icon},
        ),
        hx_post=f"/api/habits/{habit.uid}/status",
        hx_vals=f'{{"status": "{new_status}"}}',
        hx_target=f"#habit-{_safe_id(habit.uid)}",
        hx_swap="outerHTML",
        cls="uk-button uk-button-default uk-button-small uk-border-rounded",
        title=f"Mark as {new_status}",
    )

    # Title
    title_cls = "uk-text-muted uk-text-line-through" if is_completed else ""
    title_el = A(
        habit.title or "Untitled",
        href=f"/habits/detail?uid={habit.uid}",
        cls=f"uk-link-text {title_cls}",
    )

    # Badges
    badges: list[Any] = []
    if habit.polarity:
        polarity_colors = {"build": "uk-badge-primary", "break": "uk-badge-danger", "neutral": ""}
        badges.append(
            Span(
                str(habit.polarity.value).title(),
                cls=f"uk-badge {polarity_colors.get(habit.polarity.value, '')}",
            )
        )
    if habit.habit_category:
        badges.append(Span(str(habit.habit_category.value).title(), cls="uk-badge"))
    if habit.priority:
        badges.append(PriorityBadge(str(habit.priority)))
    if habit.status:
        badges.append(StatusBadge(str(habit.status)))

    # Streak display
    streak_el = Span()
    if habit.current_streak and habit.current_streak > 0:
        streak_el = Small(
            f"Streak: {habit.current_streak}d",
            cls="uk-text-success uk-text-bold uk-margin-small-left",
        )

    # Frequency
    freq_el = Span()
    if habit.recurrence_pattern:
        freq_el = Small(
            str(habit.recurrence_pattern),
            cls="uk-text-muted uk-margin-small-left",
        )

    # Tags
    tags_el = Span()
    if habit.tags:
        tag_badges = [
            Span(tag, cls="uk-badge uk-badge-secondary uk-margin-small-right")
            for tag in habit.tags[:5]
        ]
        tags_el = Div(*tag_badges, cls="uk-margin-small-top")

    # Connection badges
    conn_el = _ConnectionBadges(connections or [])

    # Card assembly
    header = Div(
        toggle_btn,
        Div(
            Div(title_el, streak_el, freq_el, cls="uk-flex uk-flex-middle uk-flex-wrap"),
            Div(*badges, cls="uk-flex uk-flex-wrap uk-flex-middle uk-margin-small-top")
            if badges
            else "",
            tags_el,
            conn_el,
            cls="uk-margin-small-left uk-width-expand",
        ),
        cls="uk-flex uk-flex-top",
    )

    opacity = "uk-opacity-75" if is_completed or is_paused else ""
    return Div(
        header,
        id=f"habit-{_safe_id(habit.uid)}",
        cls=f"uk-card uk-card-default uk-card-body uk-card-small uk-margin-small-bottom {opacity}",
    )


def HabitDetailView(
    habit: "Habit",
    connections: list[dict[str, str]],
) -> "FT":
    """Full detail page for a single habit."""
    # Subtitle
    subtitle_parts: list[str] = []
    if habit.status:
        subtitle_parts.append(str(habit.status).replace("_", " ").title())
    if habit.polarity:
        subtitle_parts.append(str(habit.polarity.value).title())
    subtitle = " · ".join(subtitle_parts) if subtitle_parts else None

    header = PageHeader(habit.title or "Untitled Habit", subtitle=subtitle)

    # Badges
    badges: list[Any] = []
    if habit.polarity:
        polarity_colors = {"build": "uk-badge-primary", "break": "uk-badge-danger", "neutral": ""}
        badges.append(
            Span(
                str(habit.polarity.value).title(),
                cls=f"uk-badge {polarity_colors.get(habit.polarity.value, '')}",
            )
        )
    if habit.habit_category:
        badges.append(Span(str(habit.habit_category.value).title(), cls="uk-badge"))
    if habit.habit_difficulty:
        badges.append(Span(str(habit.habit_difficulty.value).title(), cls="uk-badge"))
    if habit.priority:
        badges.append(PriorityBadge(str(habit.priority)))
    if habit.status:
        badges.append(StatusBadge(str(habit.status)))

    # Description
    desc_el = Div()
    if habit.description:
        desc_el = Div(P(habit.description, cls="uk-text-default"), cls="uk-margin")

    # Streak section
    streak_items: list[Any] = []
    if habit.current_streak:
        streak_items.append(
            Div(
                Small("Current Streak", cls="uk-text-muted uk-display-block"),
                Span(f"{habit.current_streak} days", cls="uk-text-success uk-text-bold"),
            )
        )
    if habit.best_streak:
        streak_items.append(
            Div(
                Small("Best Streak", cls="uk-text-muted uk-display-block"),
                Span(f"{habit.best_streak} days"),
            )
        )
    if habit.total_completions:
        streak_items.append(
            Div(
                Small("Completions", cls="uk-text-muted uk-display-block"),
                Span(str(habit.total_completions)),
            )
        )
    if habit.success_rate is not None and habit.success_rate > 0:
        streak_items.append(
            Div(
                Small("Success Rate", cls="uk-text-muted uk-display-block"),
                Span(f"{int(habit.success_rate * 100)}%"),
            )
        )
    streak_section = Div()
    if streak_items:
        streak_section = Div(
            H3("Streaks & Progress", cls="uk-heading-small"),
            Div(
                *streak_items,
                cls="uk-grid uk-grid-small uk-child-width-1-2@s uk-child-width-1-4@m",
                **{"uk-grid": "true"},
            ),
            cls="uk-margin",
        )

    # Atomic Habits section (cue/routine/reward)
    atomic_items: list[Any] = []
    if habit.cue:
        atomic_items.append(
            Div(
                Small("Cue", cls="uk-text-muted uk-display-block"),
                P(habit.cue, cls="uk-text-default"),
            )
        )
    if habit.routine:
        atomic_items.append(
            Div(
                Small("Routine", cls="uk-text-muted uk-display-block"),
                P(habit.routine, cls="uk-text-default"),
            )
        )
    if habit.reward:
        atomic_items.append(
            Div(
                Small("Reward", cls="uk-text-muted uk-display-block"),
                P(habit.reward, cls="uk-text-default"),
            )
        )
    atomic_section = Div()
    if atomic_items:
        atomic_section = Div(
            H3("Atomic Habits", cls="uk-heading-small"),
            *atomic_items,
            cls="uk-margin",
        )

    # Identity section
    identity_items: list[Any] = []
    if habit.target_identity:
        identity_items.append(
            Div(
                Small("Target Identity", cls="uk-text-muted uk-display-block"),
                P(habit.target_identity, cls="uk-text-default"),
            )
        )
    if habit.reinforces_identity:
        identity_items.append(
            Div(
                Small("Reinforces", cls="uk-text-muted uk-display-block"),
                P(habit.reinforces_identity, cls="uk-text-default"),
            )
        )
    if habit.identity_votes_cast:
        identity_items.append(
            Div(
                Small("Identity Votes", cls="uk-text-muted uk-display-block"),
                Span(str(habit.identity_votes_cast)),
            )
        )
    identity_section = Div()
    if identity_items:
        identity_section = Div(
            H3("Identity", cls="uk-heading-small"),
            *identity_items,
            cls="uk-margin",
        )

    # Scheduling info
    sched_items: list[Any] = []
    if habit.recurrence_pattern:
        sched_items.append(
            Div(
                Small("Frequency", cls="uk-text-muted uk-display-block"),
                Span(str(habit.recurrence_pattern)),
            )
        )
    if habit.target_days_per_week:
        sched_items.append(
            Div(
                Small("Target Days/Week", cls="uk-text-muted uk-display-block"),
                Span(str(habit.target_days_per_week)),
            )
        )
    if habit.preferred_time:
        sched_items.append(
            Div(
                Small("Preferred Time", cls="uk-text-muted uk-display-block"),
                Span(str(habit.preferred_time)),
            )
        )
    if habit.duration_minutes:
        sched_items.append(
            Div(
                Small("Duration", cls="uk-text-muted uk-display-block"),
                Span(f"{habit.duration_minutes} min"),
            )
        )
    sched_section = Div()
    if sched_items:
        sched_section = Div(
            H3("Schedule", cls="uk-heading-small"),
            Div(
                *sched_items,
                cls="uk-grid uk-grid-small uk-child-width-1-2@s uk-child-width-1-4@m",
                **{"uk-grid": "true"},
            ),
            cls="uk-margin",
        )

    # Metadata grid
    meta_items: list[Any] = []
    if habit.started_at:
        meta_items.append(
            Div(
                Small("Started", cls="uk-text-muted uk-display-block"),
                Span(str(habit.started_at)[:10]),
            )
        )
    if habit.completed_at:
        meta_items.append(
            Div(
                Small("Completed", cls="uk-text-muted uk-display-block"),
                Span(str(habit.completed_at)[:10]),
            )
        )
    if habit.created_at:
        meta_items.append(
            Div(
                Small("Created", cls="uk-text-muted uk-display-block"),
                Span(str(habit.created_at)[:10]),
            )
        )
    meta_grid = Div()
    if meta_items:
        meta_grid = Div(
            *meta_items,
            cls="uk-grid uk-grid-small uk-child-width-1-2@s uk-child-width-1-4@m uk-margin",
            **{"uk-grid": "true"},
        )

    # Tags
    tags_el = Div()
    if habit.tags:
        tag_badges = [
            Span(tag, cls="uk-badge uk-badge-secondary uk-margin-small-right") for tag in habit.tags
        ]
        tags_el = Div(
            Small("Tags", cls="uk-text-muted uk-display-block uk-margin-small-bottom"),
            *tag_badges,
            cls="uk-margin",
        )

    # Connections
    conn_section = Div()
    if connections:
        conn_section = Div(
            H3("Connections", cls="uk-heading-small"),
            _ConnectionBadges(connections),
            cls="uk-margin",
        )

    # Lateral relationships
    relationships = EntityRelationshipsSection(
        entity_uid=habit.uid,
        entity_type="habits",
    )

    return Div(
        header,
        Div(*badges, cls="uk-flex uk-flex-wrap uk-flex-middle uk-margin-small-bottom")
        if badges
        else "",
        desc_el,
        streak_section,
        atomic_section,
        identity_section,
        sched_section,
        meta_grid,
        tags_el,
        conn_section,
        relationships,
        cls="uk-container uk-container-small",
    )


def _ConnectionBadges(connections: list[dict[str, str]]) -> "FT":
    """Render typed connection badges for a habit's cross-domain links."""
    if not connections:
        return Span()

    conn_icons = {
        "goal": ("target", "/goals/detail?uid="),
        "ku": ("atom", "/ku/get?uid="),
        "principle": ("compass", "/principles/detail?uid="),
        "event": ("calendar", "/events/detail?uid="),
        "path_step": ("list", "#"),
        "learning_path": ("map", "#"),
    }

    badges: list[Any] = []
    for conn in connections:
        target_type = conn.get("target_type", "")
        title = conn.get("title", conn.get("target_uid", "?"))
        target_uid = conn.get("target_uid", "")
        icon, base_href = conn_icons.get(target_type, ("link", "#"))
        href = f"{base_href}{target_uid}" if base_href != "#" else "#"

        badges.append(
            A(
                Span(
                    cls="uk-icon uk-margin-small-right", **{"uk-icon": f"icon: {icon}; ratio: 0.75"}
                ),
                title,
                href=href,
                cls="uk-badge uk-margin-small-right",
                style="text-decoration: none;",
            )
        )

    return Div(*badges, cls="uk-margin-small-top")


def _is_keystone(habit: "Habit") -> bool:
    """Check if a habit is a keystone habit (high streak + identity-based)."""
    has_streak = habit.current_streak is not None and habit.current_streak >= 7
    return has_streak or bool(habit.is_identity_habit)


def _safe_id(uid: str) -> str:
    """Convert a UID to a safe HTML id attribute value."""
    return uid.replace(".", "-").replace(":", "-")


def filter_habits(
    habits: list["Habit"],
    status_filter: str = "active",
    category_filter: str = "all",
    sort_by: str = "streak",
) -> list["Habit"]:
    """Apply filters and sorting to a habit list."""
    filtered = list(habits)

    # Status filter
    if status_filter == "active":
        filtered = [
            h
            for h in filtered
            if not h.status or h.status.value in ("active", "in_progress", "ready")
        ]
    elif status_filter == "paused":
        filtered = [h for h in filtered if h.status and h.status.value == "paused"]
    elif status_filter == "completed":
        filtered = [h for h in filtered if h.status and h.status.value == "completed"]
    elif status_filter == "keystone":
        filtered = [h for h in filtered if _is_keystone(h)]

    # Category filter
    if category_filter != "all":
        filtered = [
            h for h in filtered if h.habit_category and h.habit_category.value == category_filter
        ]

    # Sort
    def by_streak(h: Any) -> int:
        return -(h.current_streak or 0)

    def by_name(h: Any) -> str:
        return (h.title or "").lower()

    def by_created(h: Any) -> str:
        return str(h.created_at or "")

    if sort_by == "streak":
        filtered.sort(key=by_streak)
    elif sort_by == "name":
        filtered.sort(key=by_name)
    elif sort_by == "created":
        filtered.sort(key=by_created, reverse=True)

    return filtered
