"""Habits UI view components.

Pure FastHTML components for rendering habit data. No service calls —
routes fetch data and pass it to these components.

Usage:
    from ui.activities.habits_views import HabitList, HabitStatsBar
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import (
    A,
    Div,
    P,
    Small,
    Span,
)

from core.models.enums.activity_enums import ConsistencyLevel
from core.utils.activity_stats import compute_habit_stats
from ui.activities._shared import (
    ActivityList,
    ConnectionBadges,
    MetadataField,
    PriorityBadgeDropdown,
    safe_id,
)
from ui.components import Button, ButtonT, Card, Icon
from ui.dual_track_card import DualTrackSection
from ui.feedback import Badge, BadgeT, PriorityBadge, StatusBadge
from ui.layout import Container, DivHStacked
from ui.patterns.loading import content_loading_placeholder
from ui.patterns.page_header import PageHeader
from ui.patterns.relationships.relationship_section import EntityRelationshipsSection
from ui.patterns.stats_grid import StatItem, StatsGrid
from ui.primitives import section_label

if TYPE_CHECKING:
    from fasthtml.common import FT

    from core.models.habit.habit import Habit
    from core.services.habits.habits_pattern_service import PatternAnalysis

# HabitPolarity value -> badge variant (build = positive, break = negative).
_POLARITY_VARIANTS: dict[str, BadgeT] = {
    "build": BadgeT.primary,
    "break": BadgeT.error,
    "neutral": BadgeT.neutral,
}


def HabitStatsBar(habits: list["Habit"]) -> "FT":
    """Quick stats bar showing habit counts."""
    s = compute_habit_stats(habits)
    stats = [
        StatItem(label="Total", value=s.total, href="/habits?status=all"),
        StatItem(label="Active", value=s.active, color="primary", href="/habits?status=active"),
        StatItem(
            label="Avg Streak",
            value=f"{s.avg_streak:.1f}",
            color="success" if s.avg_streak > 0 else None,
        ),
        StatItem(
            label="Keystone",
            value=s.keystone_count,
            color="warning" if s.keystone_count > 0 else None,
            href="/habits?status=keystone",
        ),
    ]
    return StatsGrid(stats, cols=4)


def HabitList(
    habits: list["Habit"],
    connections_map: dict[str, list[dict[str, str]]] | None = None,
) -> "FT":
    """Render a list of habit cards. Returns a replaceable container for HTMX."""
    return ActivityList(habits, "habit", HabitCard, connections_map)


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
        Icon(icon, size=16, cls=f"inline {icon_cls}"),
        hx_post=f"/api/habits/{habit.uid}/status",
        hx_vals=f'{{"status": "{new_status}"}}',
        hx_target=f"#habit-{safe_id(habit.uid)}",
        hx_swap="outerHTML",
        cls=(ButtonT.default, "rounded"),
        size="sm",
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
        badges.append(
            Badge(
                str(habit.polarity.value).title(),
                variant=_POLARITY_VARIANTS.get(habit.polarity.value, BadgeT.neutral),
            )
        )
    if habit.habit_category:
        badges.append(Badge(str(habit.habit_category.value).title(), variant=BadgeT.primary))
    badges.append(
        PriorityBadgeDropdown(
            habit.uid,
            str(habit.priority) if habit.priority else None,
            domain="habits",
            singular="habit",
        )
    )
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
        header,
        id=f"habit-{safe_id(habit.uid)}",
        cls=f"mb-2 p-3 {opacity}",
    )


def _insight_card(pattern: dict[str, Any], positive: bool) -> "FT":
    """Single pattern insight card with confidence badge + recommendation."""
    confidence_pct = int(float(pattern.get("confidence", 0.0)) * 100)
    badge_variant = BadgeT.success if positive else BadgeT.warning
    return Card(
        DivHStacked(
            Span(str(pattern.get("pattern", "")), cls="font-medium"),
            Badge(f"{confidence_pct}% confidence", variant=badge_variant),
            cls="justify-between flex-wrap gap-2",
        ),
        Small(str(pattern.get("recommendation", "")), cls="text-muted-foreground"),
        cls="mb-2 p-3 space-y-1",
    )


def HabitInsightsSection(analysis: "PatternAnalysis") -> "FT":
    """Atomic Habits pattern insights (success + failure patterns).

    Rendered by the /habits/insights-fragment HTMX endpoint and swapped into
    the #habit-insights placeholder on the habit detail page.
    """
    body: list[Any] = []
    if analysis.success_patterns:
        body.append(Small("What's working", cls="text-muted-foreground block mb-1"))
        body.extend(_insight_card(p, positive=True) for p in analysis.success_patterns)
    if analysis.failure_patterns:
        body.append(Small("What needs attention", cls="text-muted-foreground block mb-1 mt-2"))
        body.extend(_insight_card(p, positive=False) for p in analysis.failure_patterns)
    if not body:
        body.append(
            P(
                "No patterns detected yet — keep completing this habit to build signal.",
                cls="text-muted-foreground text-sm",
            )
        )

    return Div(
        section_label("Pattern Insights"),
        *body,
        id="habit-insights",
        cls="my-4",
    )


def _choice_links(choices: list[dict[str, Any]]) -> "FT":
    """Render linked choice titles for one direction of the Habit ↔ Choice lens."""
    return Div(
        *[
            A(
                str(c.get("title") or c.get("uid", "Untitled choice")),
                href=f"/choices/detail?uid={c.get('uid', '')}",
                cls="block hover:underline text-sm",
            )
            for c in choices
        ],
        cls="space-y-1",
    )


def HabitChoicesSection(
    informed_choices: list[dict[str, Any]],
    impacting_choices: list[dict[str, Any]],
) -> "FT":
    """Habit ↔ Choice lens: choices this habit informed + choices impacting it.

    Graph edges: (Habit)-[:INFORMS_CHOICE]->(Choice) and
    (Choice)-[:IMPACTS_HABIT]->(Habit). Rendered by the
    /habits/choices-fragment HTMX endpoint into #habit-choices.
    Empty state renders nothing visible (matching neighboring optional sections).
    """
    if not informed_choices and not impacting_choices:
        return Div(id="habit-choices")

    columns: list[Any] = []
    if informed_choices:
        columns.append(
            MetadataField("Choices this habit informed", _choice_links(informed_choices))
        )
    if impacting_choices:
        columns.append(
            MetadataField("Choices impacting this habit", _choice_links(impacting_choices))
        )

    return Div(
        section_label("Choices"),
        Div(*columns, cls="grid grid-cols-1 sm:grid-cols-2 gap-2"),
        id="habit-choices",
        cls="my-4",
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
        badges.append(
            Badge(
                str(habit.polarity.value).title(),
                variant=_POLARITY_VARIANTS.get(habit.polarity.value, BadgeT.neutral),
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
            section_label("Streaks & Progress"),
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
            section_label("Atomic Habits"),
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
            section_label("Identity"),
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
            section_label("Schedule"),
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
            section_label("Connections"),
            ConnectionBadges(connections),
            cls="my-4",
        )

    # Habit ↔ Choice lens — HTMX-loaded (graph fetch happens in the fragment route)
    choices_section = content_loading_placeholder(
        f"/habits/choices-fragment?uid={habit.uid}", "habit-choices"
    )

    # Atomic Habits pattern insights — HTMX-loaded (analyze_patterns runs in the fragment route)
    insights_section = content_loading_placeholder(
        f"/habits/insights-fragment?uid={habit.uid}", "habit-insights"
    )

    # Dual-track self-assessment (perception gap + trend) — ADR-030
    dual_track_section = DualTrackSection(
        domain="habits",
        entity_uid=habit.uid,
        level_enum=ConsistencyLevel,
        label="Consistency",
        prompt="How consistent do you feel you've been with this habit?",
        checkins=habit.dual_track_checkins,
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
        choices_section,
        insights_section,
        dual_track_section,
        relationships,
        size="3xl",
    )
