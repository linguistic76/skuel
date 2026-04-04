"""Habits UI view components.

Pure FastHTML components for rendering habit data. No service calls —
routes fetch data and pass it to these components.

Usage:
    from ui.activities.habits_views import HabitList, HABIT_FILTER_CONFIG, HabitStatsBar
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    A,
    Div,
    P,
    Small,
    Span,
)
from monsterui.franken import UkIcon  # type: ignore[import-untyped]

from ui.activities._shared import ConnectionBadges, MetadataField, safe_id
from ui.activities.filter_bar import FilterBarConfig, FilterSelect
from ui.buttons import Button, ButtonT
from ui.cards import Card, CardBody
from ui.feedback import Badge, BadgeT, PriorityBadge, StatusBadge
from ui.layout import Container, DivHStacked
from ui.patterns.empty_state import EmptyState
from ui.patterns.page_header import PageHeader
from ui.patterns.relationships.relationship_section import EntityRelationshipsSection
from ui.patterns.stats_grid import StatItem, StatsGrid
from ui.text import SectionTitle

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
        StatItem(
            label="Keystone",
            value=keystone,
            color="warning" if keystone > 0 else None,
            href="/habits?status=keystone",
        ),
    ]
    return StatsGrid(stats, cols=4)


HABIT_FILTER_CONFIG = FilterBarConfig(
    fragment_url="/habits/list-fragment",
    list_target_id="habit-list",
    filters=[
        FilterSelect(
            name="status",
            label="Status",
            options=[
                ("Active", "active"),
                ("Paused", "paused"),
                ("Completed", "completed"),
                ("Keystone", "keystone"),
                ("All", "all"),
            ],
            default="active",
        ),
        FilterSelect(
            name="category",
            label="Category",
            options=[
                ("All", "all"),
                ("Health", "health"),
                ("Fitness", "fitness"),
                ("Mindfulness", "mindfulness"),
                ("Learning", "learning"),
                ("Productivity", "productivity"),
                ("Creative", "creative"),
                ("Social", "social"),
                ("Financial", "financial"),
            ],
            default="all",
        ),
    ],
    sort_options=[
        ("Streak", "streak"),
        ("Name", "name"),
        ("Recently Created", "created"),
    ],
    sort_default="streak",
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
    return Div(*cards, id="habit-list", cls="mt-4")


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
        icon_cls = "text-green-600"
    elif is_paused:
        new_status = "active"
        icon = "pause"
        icon_cls = "text-yellow-600"
    else:
        new_status = "completed"
        icon = "repeat"
        icon_cls = ""

    toggle_btn = Button(
        UkIcon(icon, height=16, width=16, cls=f"inline {icon_cls}"),
        hx_post=f"/api/habits/{habit.uid}/status",
        hx_vals=f'{{"status": "{new_status}"}}',
        hx_target=f"#habit-{safe_id(habit.uid)}",
        hx_swap="outerHTML",
        variant=ButtonT.neutral,
        size="sm",
        cls="rounded",
        title=f"Mark as {new_status}",
    )

    # Title
    title_cls = "text-muted-foreground line-through" if is_completed else ""
    title_el = A(
        habit.title or "Untitled",
        href=f"/habits/detail?uid={habit.uid}",
        cls=f"hover:underline {title_cls}",
    )

    # Badges
    badges: list[Any] = []
    if habit.polarity:
        polarity_variants = {
            "build": BadgeT.primary,
            "break": BadgeT.error,
            "neutral": BadgeT.neutral,
        }
        badges.append(
            Badge(
                str(habit.polarity.value).title(),
                variant=polarity_variants.get(habit.polarity.value, BadgeT.neutral),
            )
        )
    if habit.habit_category:
        badges.append(Badge(str(habit.habit_category.value).title(), variant=BadgeT.primary))
    if habit.priority:
        badges.append(PriorityBadge(str(habit.priority)))
    if habit.status:
        badges.append(StatusBadge(str(habit.status)))

    # Streak display
    streak_el = Span()
    if habit.current_streak and habit.current_streak > 0:
        streak_el = Small(
            f"Streak: {habit.current_streak}d",
            cls="text-green-600 font-bold ml-2",
        )

    # Frequency
    freq_el = Span()
    if habit.recurrence_pattern:
        freq_el = Small(
            str(habit.recurrence_pattern),
            cls="text-muted-foreground ml-2",
        )

    # Tags
    tags_el = Span()
    if habit.tags:
        tag_badges = [Badge(tag, variant=BadgeT.secondary, cls="mr-2") for tag in habit.tags[:5]]
        tags_el = Div(*tag_badges, cls="mt-2")

    # Connection badges
    conn_el = ConnectionBadges(connections or [])

    # Card assembly
    header = Div(
        toggle_btn,
        Div(
            DivHStacked(title_el, streak_el, freq_el, cls="flex-wrap"),
            DivHStacked(*badges, cls="flex-wrap mt-2") if badges else "",
            tags_el,
            conn_el,
            cls="ml-2 flex-1 min-w-0",
        ),
        cls="flex items-start",
    )

    opacity = "opacity-75" if is_completed or is_paused else ""
    return Card(
        CardBody(header, cls="p-3"),
        id=f"habit-{safe_id(habit.uid)}",
        cls=f"mb-2 {opacity}",
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
        polarity_variants = {
            "build": BadgeT.primary,
            "break": BadgeT.error,
            "neutral": BadgeT.neutral,
        }
        badges.append(
            Badge(
                str(habit.polarity.value).title(),
                variant=polarity_variants.get(habit.polarity.value, BadgeT.neutral),
            )
        )
    if habit.habit_category:
        badges.append(Badge(str(habit.habit_category.value).title(), variant=BadgeT.primary))
    if habit.habit_difficulty:
        badges.append(Badge(str(habit.habit_difficulty.value).title(), variant=BadgeT.primary))
    if habit.priority:
        badges.append(PriorityBadge(str(habit.priority)))
    if habit.status:
        badges.append(StatusBadge(str(habit.status)))

    # Description
    desc_el = Div()
    if habit.description:
        desc_el = Div(P(habit.description), cls="my-4")

    # Streak section
    streak_items: list[Any] = []
    if habit.current_streak:
        streak_items.append(
            MetadataField(
                "Current Streak",
                Span(f"{habit.current_streak} days", cls="text-green-600 font-bold"),
            )
        )
    if habit.best_streak:
        streak_items.append(MetadataField("Best Streak", Span(f"{habit.best_streak} days")))
    if habit.total_completions:
        streak_items.append(MetadataField("Completions", Span(str(habit.total_completions))))
    if habit.success_rate is not None and habit.success_rate > 0:
        streak_items.append(
            MetadataField("Success Rate", Span(f"{int(habit.success_rate * 100)}%"))
        )
    streak_section = Div()
    if streak_items:
        streak_section = Div(
            SectionTitle("Streaks & Progress"),
            Div(
                *streak_items,
                cls="grid grid-cols-2 sm:grid-cols-4 gap-2",
            ),
            cls="my-4",
        )

    # Atomic Habits section (cue/routine/reward)
    atomic_items: list[Any] = []
    if habit.cue:
        atomic_items.append(MetadataField("Cue", P(habit.cue)))
    if habit.routine:
        atomic_items.append(MetadataField("Routine", P(habit.routine)))
    if habit.reward:
        atomic_items.append(MetadataField("Reward", P(habit.reward)))
    atomic_section = Div()
    if atomic_items:
        atomic_section = Div(
            SectionTitle("Atomic Habits"),
            *atomic_items,
            cls="my-4",
        )

    # Identity section
    identity_items: list[Any] = []
    if habit.target_identity:
        identity_items.append(MetadataField("Target Identity", P(habit.target_identity)))
    if habit.reinforces_identity:
        identity_items.append(MetadataField("Reinforces", P(habit.reinforces_identity)))
    if habit.identity_votes_cast:
        identity_items.append(MetadataField("Identity Votes", Span(str(habit.identity_votes_cast))))
    identity_section = Div()
    if identity_items:
        identity_section = Div(
            SectionTitle("Identity"),
            *identity_items,
            cls="my-4",
        )

    # Scheduling info
    sched_items: list[Any] = []
    if habit.recurrence_pattern:
        sched_items.append(MetadataField("Frequency", Span(str(habit.recurrence_pattern))))
    if habit.target_days_per_week:
        sched_items.append(MetadataField("Target Days/Week", Span(str(habit.target_days_per_week))))
    if habit.preferred_time:
        sched_items.append(MetadataField("Preferred Time", Span(str(habit.preferred_time))))
    if habit.duration_minutes:
        sched_items.append(MetadataField("Duration", Span(f"{habit.duration_minutes} min")))
    sched_section = Div()
    if sched_items:
        sched_section = Div(
            SectionTitle("Schedule"),
            Div(
                *sched_items,
                cls="grid grid-cols-2 sm:grid-cols-4 gap-2",
            ),
            cls="my-4",
        )

    # Metadata grid
    meta_items: list[Any] = []
    if habit.started_at:
        meta_items.append(MetadataField("Started", Span(str(habit.started_at)[:10])))
    if habit.completed_at:
        meta_items.append(MetadataField("Completed", Span(str(habit.completed_at)[:10])))
    if habit.created_at:
        meta_items.append(MetadataField("Created", Span(str(habit.created_at)[:10])))
    meta_grid = Div()
    if meta_items:
        meta_grid = Div(
            *meta_items,
            cls="grid grid-cols-2 sm:grid-cols-4 gap-2 my-4",
        )

    # Tags
    tags_el = Div()
    if habit.tags:
        tag_badges = [Badge(tag, variant=BadgeT.secondary, cls="mr-2") for tag in habit.tags]
        tags_el = Div(
            Small("Tags", cls="text-muted-foreground block mb-2"),
            *tag_badges,
            cls="my-4",
        )

    # Connections
    conn_section = Div()
    if connections:
        conn_section = Div(
            SectionTitle("Connections"),
            ConnectionBadges(connections),
            cls="my-4",
        )

    # Lateral relationships
    relationships = EntityRelationshipsSection(
        entity_uid=habit.uid,
        entity_type="habits",
    )

    return Container(
        header,
        DivHStacked(*badges, cls="flex-wrap mb-2") if badges else "",
        desc_el,
        streak_section,
        atomic_section,
        identity_section,
        sched_section,
        meta_grid,
        tags_el,
        conn_section,
        relationships,
        size="3xl",
    )


def _is_keystone(habit: "Habit") -> bool:
    """Check if a habit is a keystone habit (high streak + identity-based)."""
    has_streak = habit.current_streak is not None and habit.current_streak >= 7
    return has_streak or bool(habit.is_identity_habit)


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
