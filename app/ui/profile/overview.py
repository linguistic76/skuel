"""Overview and intelligence view components for profile page.

Contains:
- OverviewView: The main overview tab (always shown)
- _intelligence_unavailable_card: Shown when intelligence services are off
- render_domain_card_preview: HTMX fragment for domain card item lists
- Chart visualizations section (Visual Analytics tab)
- All private helpers for daily plan, alignment, synergies, learning steps

See: /docs/architecture/UNIFIED_USER_ARCHITECTURE.md
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import H2, H3, A, Canvas, Div, Li, P, Span, Ul

from core.models.enums import Priority
from core.services.user.unified_user_context import UserContext

if TYPE_CHECKING:
    from core.models.context_types import (
        CrossDomainSynergy,
        DailyWorkPlan,
        LearningStep,
        LifePathAlignment,
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
    - Chart visualizations: Alignment radar + domain progress timeline
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

    # , Task 3: Use HTMX to load intelligence section with skeleton loading state
    # , Task 15: Added caching with Alpine.js to reduce 2-3s load times
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

    # Intelligence section with caching
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
    for task_data in context.entities_rich.get("tasks", []):
        task = task_data.get("entity", {})
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


def _card_preview_skeleton() -> Div:
    """Animated skeleton shown in domain cards while HTMX loads item lists."""
    return Div(
        Div(cls="h-4 bg-base-200 rounded animate-pulse"),
        Div(cls="h-4 bg-base-200 rounded animate-pulse w-4/5"),
        Div(cls="h-4 bg-base-200 rounded animate-pulse w-3/5"),
        cls="space-y-2 py-1",
    )


_PREVIEW_DOMAIN_HREFS: dict[str, str] = {
    "tasks": "/tasks",
    "goals": "/goals",
    "habits": "/habits",
    "events": "/events",
    "choices": "/choices",
    "principles": "/principles",
}

_PREVIEW_PRIORITY_COLORS: dict[Priority, str] = {
    Priority.CRITICAL: "bg-red-500",
    Priority.HIGH: "bg-orange-500",
    Priority.MEDIUM: "bg-blue-500",
    Priority.LOW: "bg-gray-400",
}

_PREVIEW_PRIORITY_LABELS: dict[Priority, str] = {
    Priority.CRITICAL: "P1",
    Priority.HIGH: "P2",
    Priority.MEDIUM: "P3",
    Priority.LOW: "P4",
}


def render_domain_card_preview(items: list[Any], slug: str) -> Div:
    """Render domain card preview HTML fragment.

    Called from the /api/profile/{slug}/preview endpoint.
    Shows up to 5 active items sorted by priority with a "View all" link.

    Args:
        items: Pre-filtered and pre-sorted list of domain items (max 5).
        slug: Domain slug used for the "View all" link.
    """
    view_href = _PREVIEW_DOMAIN_HREFS.get(slug, f"/{slug}")

    if not items:
        return Div(
            P(
                f"No active {slug}",
                cls="text-sm text-base-content/40 text-center py-3",
            ),
            A(
                f"View all {slug} →",
                href=view_href,
                cls="text-xs text-primary hover:underline block text-center",
            ),
        )

    def _priority_dot(item: Any) -> Span:
        """Compact priority indicator: colored dot + P-label."""
        raw = getattr(item, "priority", Priority.LOW)
        # Services may return string values instead of Priority enum instances
        if not isinstance(raw, Priority):
            try:
                raw = Priority(str(raw).lower())
            except ValueError:
                raw = Priority.LOW
        color = _PREVIEW_PRIORITY_COLORS.get(raw, "bg-gray-400")
        label = _PREVIEW_PRIORITY_LABELS.get(raw, "P4")
        return Span(
            Span(cls=f"w-2 h-2 rounded-full {color} shrink-0"),
            Span(label, cls="text-xs font-medium text-base-content/50 w-5"),
            cls="inline-flex items-center gap-1 shrink-0",
            title=f"Priority: {raw.value.title()}",
        )

    rows = [
        Li(
            _priority_dot(item),
            Span(
                getattr(item, "title", "Untitled"),
                cls="text-sm text-base-content truncate flex-1 min-w-0",
            ),
            cls="flex items-center gap-2 py-1.5",
        )
        for item in items
    ]

    return Div(
        Ul(*rows, cls="divide-y divide-base-200"),
        A(
            f"View all {slug} →",
            href=view_href,
            cls="text-xs text-primary hover:underline mt-3 inline-block",
        ),
    )


def _domain_progress_grid(context: UserContext) -> Div:
    """Per-domain cards — Activity Domains load item lists via HTMX.

    The 6 Activity Domains (Tasks, Habits, Goals, Events, Principles,
    Choices) show a compact priority-sorted item list loaded asynchronously.
    Knowledge and Journals use static stat displays.
    """
    # Activity Domain cards: active count badge in header + HTMX-loaded item list
    activity_data: list[tuple[str, str, str, int, str]] = [
        ("✅", "Tasks", "tasks", len(context.active_task_uids), "/tasks?view=create"),
        ("🔄", "Habits", "habits", len(context.active_habit_uids), "/habits?view=create"),
        ("🎯", "Goals", "goals", len(context.active_goal_uids), "/goals?view=create"),
        ("📅", "Events", "events", len(context.upcoming_event_uids), "/events?view=create"),
        (
            "⚖️",
            "Principles",
            "principles",
            len(context.core_principle_uids),
            "/principles?view=create",
        ),
        (
            "🔀",
            "Choices",
            "choices",
            len(context.pending_choice_uids),
            "/choices?view=create",
        ),
    ]

    domain_items: list[Any] = []
    for icon, name, slug, active_count, create_href in activity_data:
        create_btn = A(
            "+",
            href=create_href,
            cls="w-7 h-7 flex items-center justify-center rounded-full "
            "text-base-content/40 hover:text-base-content hover:bg-base-200 "
            "transition-colors text-lg font-bold leading-none",
            title=f"New {name.removesuffix('s')}",
        )
        domain_items.append(
            Div(
                # Header: icon + name + active count + create button
                Div(
                    Div(
                        Span(icon, cls="text-xl"),
                        Span(name, cls="text-base font-semibold text-base-content"),
                        Span(str(active_count), cls="badge badge-sm badge-ghost"),
                        cls="flex items-center gap-2",
                    ),
                    create_btn,
                    cls="flex items-center justify-between mb-3",
                ),
                # HTMX-loaded item list (skeleton shown while loading)
                Div(
                    _card_preview_skeleton(),
                    hx_get=f"/api/profile/{slug}/preview",
                    hx_trigger="load",
                    hx_swap="innerHTML",
                    cls="min-h-[100px]",
                ),
                cls="bg-base-100 rounded-xl p-5 shadow-sm hover:shadow-md transition-shadow",
            )
        )

    # Knowledge card (static stat — no items endpoint needed)
    total_knowledge = len(context.mastered_knowledge_uids) + len(context.in_progress_knowledge_uids)
    mastered = len(context.mastered_knowledge_uids)
    knowledge_secondary = (
        Span(f"{mastered} mastered", cls="text-sm text-base-content/50") if mastered > 0 else None
    )
    domain_items.append(
        Div(
            Div(
                Div(
                    Span("📖", cls="text-xl"),
                    Span("Knowledge", cls="text-base font-semibold text-base-content"),
                    cls="flex items-center gap-2",
                ),
                cls="flex items-center justify-between mb-3",
            ),
            Div(
                Span(str(total_knowledge), cls="text-3xl font-bold text-base-content"),
                Span("studied", cls="text-sm text-base-content/50 ml-2"),
                cls="flex items-baseline",
            ),
            Div(knowledge_secondary, cls="mt-1 min-h-[1.25rem]")
            if knowledge_secondary
            else Div(cls="mt-1 min-h-[1.25rem]"),
            cls="bg-base-100 rounded-xl p-5 shadow-sm hover:shadow-md transition-shadow",
        )
    )

    # Journals card (CTA — submit a new entry)
    domain_items.append(
        Div(
            Div(
                Div(
                    Span("📓", cls="text-xl"),
                    Span("Journals", cls="text-base font-semibold text-base-content"),
                    cls="flex items-center gap-2",
                ),
                A(
                    "+",
                    href="/journals/submit",
                    cls="w-7 h-7 flex items-center justify-center rounded-full "
                    "text-base-content/40 hover:text-base-content hover:bg-base-200 "
                    "transition-colors text-lg font-bold leading-none",
                    title="Submit journal",
                ),
                cls="flex items-center justify-between mb-3",
            ),
            P(
                "Submit a journal entry to track your progress.",
                cls="text-sm text-base-content/50",
            ),
            A(
                "Submit journal →",
                href="/journals/submit",
                cls="text-xs text-primary hover:underline mt-2 inline-block",
            ),
            cls="bg-base-100 rounded-xl p-5 shadow-sm hover:shadow-md transition-shadow",
        )
    )

    return Div(
        *domain_items,
        cls="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 lg:gap-5",
    )


# =============================================================================
# Intelligence Components
# =============================================================================


def _chart_visualizations_section() -> Div:
    """Chart.js visualizations section.

    Displays:
    - Alignment radar chart (5 dimensions)
    - 30-day domain progress timeline
    """
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
                            f"{step.estimated_time_minutes} min",
                            cls="text-xs text-base-content/60",
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
