"""Overview and intelligence view components for profile page.

Contains:
- OverviewView: The main overview tab (always shown)
- _intelligence_unavailable_card: Shown when intelligence services are off
- render_domain_card_preview: HTMX fragment for domain card item lists
- Chart visualizations section (Visual Analytics tab)
- All private helpers for daily plan, alignment, synergies, path steps

See: /docs/architecture/UNIFIED_USER_ARCHITECTURE.md
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import H2, H3, A, Canvas, Div, P, Span

from core.models.enums import Priority
from core.services.user.unified_user_context import UserContext
from ui.components import Card
from ui.feedback import Alert, AlertT, Badge, BadgeT, Progress, ProgressT
from ui.patterns.empty_state import EmptyState

if TYPE_CHECKING:
    from core.models.context_types import (
        ContextualGoal,
        CrossDomainSynergy,
        DailyWorkPlan,
        LifePathAlignment,
        PathStep,
    )


def OverviewView(
    context: UserContext,
    daily_plan: "DailyWorkPlan | None" = None,
    alignment: "LifePathAlignment | None" = None,
    synergies: "list[CrossDomainSynergy] | None" = None,
    path_steps: "list[PathStep] | None" = None,
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
    - Next path steps - from intelligence

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
        path_steps: list of PathStep from intelligence service (optional)
    """
    # Check if intelligence is available (all params provided = full mode)
    _has_intelligence = daily_plan is not None and alignment is not None

    # HTMX-loaded intelligence section with Alpine.js cache to absorb 2-3s load time
    from ui.patterns.skeleton import SkeletonIntelligence

    header = Div(
        H2("Activity Overview", cls="text-xl font-semibold text-foreground"),
        P(
            Span("Intelligence data ", cls="text-muted-foreground"),
            Span(
                **{"x-text": "lastUpdatedText", "x-show": "hasCache"},
                cls="text-sm text-muted-foreground",
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
        Alert(
            Div(
                Span("⚠️ ", cls="text-2xl mr-2"),
                Span("Failed to load intelligence data", cls="font-medium"),
                cls="flex items-center",
            ),
            P(
                "Using cached data. Will retry in 5 minutes.",
                cls="text-sm text-muted-foreground mt-2",
                **{"x-show": "hasCache"},
            ),
            variant=AlertT.warning,
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
        ("📚", "Learning Recommendations", "Optimal next path steps"),
    ]

    feature_items = [
        Div(
            Span(icon, cls="mr-2"),
            Div(
                Span(name, cls="font-medium text-sm"),
                P(desc, cls="text-xs text-muted-foreground"),
                cls="flex flex-col",
            ),
            cls="flex items-start py-2",
        )
        for icon, name, desc in features
    ]

    return Div(
        Div(
            H3("Intelligence Features", cls="text-lg font-semibold text-foreground"),
            cls="mb-4",
        ),
        Div(
            P(
                "Intelligence features are not currently configured.",
                cls="text-muted-foreground mb-3",
            ),
            P(
                "Core profile features are available. Intelligence features include:",
                cls="text-sm text-muted-foreground mb-4",
            ),
            Div(*feature_items, cls="space-y-1"),
            cls="p-4 bg-muted rounded-lg border border-border",
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
                "/tasks",
            )
        )

    # Check for at-risk habits (rich-context only; silent at standard depth)
    if at_risk := context.at_risk_habits_or_empty():
        insights.append(
            _insight_item(
                "warning",
                f"{len(at_risk)} habits at risk of breaking streak",
                "/habits",
            )
        )

    # Check for pending choices
    if len(context.pending_choice_uids) > 3:
        insights.append(
            _insight_item(
                "info",
                f"{len(context.pending_choice_uids)} choices awaiting your decision",
                "/choices",
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
            Div(cls="border-t border-border mt-8 mb-6"),
            P("Everything looks good! You're on track.", cls="text-sm text-muted-foreground"),
        )

    return Div(
        Div(cls="border-t border-border mt-8 mb-6"),
        H3(
            "Insights",
            cls="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-3",
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
        cls="flex items-center p-3 bg-background rounded-lg hover:bg-muted transition-colors text-muted-foreground hover:text-foreground",
    )


def _card_preview_skeleton() -> Div:
    """Animated skeleton shown in domain cards while HTMX loads item lists."""
    return Div(
        Div(cls="h-4 bg-muted rounded animate-pulse"),
        Div(cls="h-4 bg-muted rounded animate-pulse w-4/5"),
        Div(cls="h-4 bg-muted rounded animate-pulse w-3/5"),
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
    """Render domain card preview as a row of 3 cards.

    Called from the /api/profile/{slug}/preview endpoint.
    Shows up to 3 active items sorted by priority.

    Args:
        items: Pre-filtered and pre-sorted list of domain items (max 3).
        slug: Domain slug used for the detail link.
    """
    view_href = _PREVIEW_DOMAIN_HREFS.get(slug, f"/{slug}")
    detail_base = f"/{slug}/detail"

    if not items:
        return Div(
            P(
                f"No active {slug}",
                cls="text-sm text-foreground/40 text-center py-3",
            ),
        )

    def _priority_dot(item: Any) -> Span:
        """Colored priority dot."""
        raw = getattr(item, "priority", Priority.LOW)
        if not isinstance(raw, Priority):
            try:
                raw = Priority(str(raw).lower())
            except ValueError:
                raw = Priority.LOW
        color = _PREVIEW_PRIORITY_COLORS.get(raw, "bg-gray-400")
        label = _PREVIEW_PRIORITY_LABELS.get(raw, "P4")
        return Span(
            Span(cls=f"w-2 h-2 rounded-full {color} shrink-0"),
            Span(label, cls="text-[10px] font-medium text-muted-foreground"),
            cls="inline-flex items-center gap-1",
            title=f"Priority: {raw.value.title()}",
        )

    def _square_card(item: Any) -> A:
        """Compact square card — clickable, links to detail page."""
        uid = getattr(item, "uid", "")
        title = getattr(item, "title", "Untitled") or "Untitled"
        return A(
            _priority_dot(item),
            Span(
                title,
                cls="text-xs font-medium text-foreground line-clamp-3 leading-snug mt-1 min-h-[3rem]",
            ),
            href=f"{detail_base}?uid={uid}" if uid else view_href,
            cls=(
                "flex flex-col justify-between p-2.5 rounded-lg border border-border "
                "bg-muted/30 hover:bg-muted/60 hover:border-primary/30 transition-colors "
                "min-h-[80px] no-underline"
            ),
        )

    cards = [_square_card(item) for item in items]

    return Div(
        Div(*cards, cls="grid grid-cols-3 gap-2"),
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
            "text-foreground/40 hover:text-foreground hover:bg-muted "
            "transition-colors text-lg font-bold leading-none",
            title=f"New {name.removesuffix('s')}",
        )
        domain_items.append(
            Div(
                # Header: icon + name + active count + create button
                Div(
                    Div(
                        Span(icon, cls="text-xl"),
                        Span(name, cls="text-base font-semibold text-foreground"),
                        Badge(str(active_count), variant=BadgeT.ghost),
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
                cls="bg-background rounded-xl p-5 shadow-sm hover:shadow-md transition-shadow",
            )
        )

    # Knowledge card (static stat — no items endpoint needed)
    total_knowledge = len(context.mastered_knowledge_uids) + len(context.in_progress_knowledge_uids)
    mastered = len(context.mastered_knowledge_uids)
    knowledge_secondary = (
        Span(f"{mastered} mastered", cls="text-sm text-muted-foreground") if mastered > 0 else None
    )
    domain_items.append(
        Div(
            Div(
                Div(
                    Span("📖", cls="text-xl"),
                    Span("Knowledge", cls="text-base font-semibold text-foreground"),
                    cls="flex items-center gap-2",
                ),
                cls="flex items-center justify-between mb-3",
            ),
            Div(
                Span(str(total_knowledge), cls="text-3xl font-bold text-foreground"),
                Span("studied", cls="text-sm text-muted-foreground ml-2"),
                cls="flex items-baseline",
            ),
            Div(knowledge_secondary, cls="mt-1 min-h-[1.25rem]")
            if knowledge_secondary
            else Div(cls="mt-1 min-h-[1.25rem]"),
            cls="bg-background rounded-xl p-5 shadow-sm hover:shadow-md transition-shadow",
        )
    )

    # Journals card (CTA — submit a new entry)
    domain_items.append(
        Div(
            Div(
                Div(
                    Span("📓", cls="text-xl"),
                    Span("Journals", cls="text-base font-semibold text-foreground"),
                    cls="flex items-center gap-2",
                ),
                A(
                    "+",
                    href="/submissions/journal",
                    cls="w-7 h-7 flex items-center justify-center rounded-full "
                    "text-foreground/40 hover:text-foreground hover:bg-muted "
                    "transition-colors text-lg font-bold leading-none",
                    title="Submit journal",
                ),
                cls="flex items-center justify-between mb-3",
            ),
            P(
                "Submit a journal entry to track your progress.",
                cls="text-sm text-muted-foreground",
            ),
            A(
                "Submit journal →",
                href="/submissions/journal",
                cls="text-xs text-primary hover:underline mt-2 inline-block",
            ),
            cls="bg-background rounded-xl p-5 shadow-sm hover:shadow-md transition-shadow",
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
        H3("Visual Analytics", cls="text-xl font-semibold text-foreground mb-4"),
        # Two-column grid for charts
        Div(
            # Alignment Radar Chart
            Card(
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
                        cls="text-center text-muted-foreground py-8",
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
                cls="bg-background shadow-sm p-6",
            ),
            # Domain Progress Timeline
            Card(
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
                        cls="text-center text-muted-foreground py-8",
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
                cls="bg-background shadow-sm p-6",
            ),
            cls="grid grid-cols-1 lg:grid-cols-2 gap-6",
        ),
        cls="mb-8",
    )


def _engaged_ps_section(plan: "DailyWorkPlan") -> "Div | None":
    """One collapsible row per active PS engagement, surfacing the spawned
    items that are still on today's plan.

    Engagements that spawned no plan items today still render a header row so
    consumers can see "you're engaged with X" even when no spawned activity
    is on today's plan (per ADR-059 bucketing semantics).

    Returns None when ``plan.engaged_ps_groups`` is empty — typical for users
    who haven't engaged with any PathSteps yet.
    """
    if not plan.engaged_ps_groups:
        return None

    title_lookup: dict[str, str] = {}
    for t in plan.contextual_tasks:
        title_lookup[t.uid] = getattr(t, "title", t.uid)
    for h in plan.contextual_habits:
        title_lookup[h.uid] = getattr(h, "title", h.uid)
    for g in plan.contextual_goals:
        title_lookup[g.uid] = getattr(g, "title", g.uid)

    domain_emojis = {
        "task": "✅",
        "habit": "🔄",
        "event": "📅",
        "goal": "🎯",
        "choice": "🤔",
        "principle": "⚖️",
    }

    group_blocks = []
    for group in plan.engaged_ps_groups:
        ps_slug = group.ps_uid.rsplit(":", 1)[-1] or group.ps_uid
        state = group.engagement.state
        state_variant = BadgeT.success if state == "completed" else BadgeT.info

        pending_pairs: list[tuple[str, str]] = []
        for uid in group.pending_task_uids:
            pending_pairs.append(("task", uid))
        for uid in group.pending_habit_uids:
            pending_pairs.append(("habit", uid))
        for uid in group.pending_event_uids:
            pending_pairs.append(("event", uid))
        for uid in group.pending_goal_uids:
            pending_pairs.append(("goal", uid))
        for uid in group.pending_choice_uids:
            pending_pairs.append(("choice", uid))
        for uid in group.pending_principle_uids:
            pending_pairs.append(("principle", uid))

        item_rows = [
            Div(
                Span(domain_emojis.get(domain, "•"), cls="mr-2"),
                Span(title_lookup.get(uid, uid), cls="text-sm"),
                cls="flex items-center py-1 pl-4",
            )
            for domain, uid in pending_pairs[:6]
        ]

        total_spawned = len(group.engagement.spawned_instance_uids)
        progress_text = (
            f"{len(pending_pairs)} of {total_spawned} pending" if total_spawned else "engaged"
        )

        group_blocks.append(
            Div(
                Div(
                    Span("📘", cls="mr-2"),
                    Span(ps_slug, cls="text-sm font-medium"),
                    Badge(state, variant=state_variant, cls="ml-2 text-xs"),
                    Span(progress_text, cls="text-xs text-muted-foreground ml-2"),
                    cls="flex items-center py-1",
                ),
                *item_rows,
                cls="mb-2",
            )
        )

    return Div(
        P("🔗 ENGAGED PATHSTEPS", cls="text-xs font-bold text-primary mb-1"),
        *group_blocks,
        cls="mb-3",
    )


def _goal_learning_requirements_line(goal: "ContextualGoal") -> "Span | None":
    """Render a goal's mastery-aware learning-requirements summary, or None.

    Reads the ``learning_requirements`` payload that ``ContextualGoal`` now sources
    from the single ``PrerequisiteChecker`` split (truthful against the user's
    ``knowledge_mastery`` — see the consolidated lens). Returns None when the goal
    requires no knowledge, so goals without prerequisites render no clutter.
    """
    reqs = goal.learning_requirements
    if not reqs:
        return None

    knowledge = reqs["knowledge_requirements"]
    if knowledge["total_required"] == 0:
        return None

    if reqs["learning_analysis"]["ready_to_start"]:
        return Span("✓ ready to start", cls="text-xs text-success ml-2")

    gaps = len(knowledge["knowledge_gaps"])
    hours = reqs["learning_paths"]["estimated_learning_time"]
    return Span(
        f"{knowledge['total_mastered']}/{knowledge['total_required']} mastered "
        f"({knowledge['mastery_percentage']:.0f}%) · "
        f"{gaps} gap{'s' if gaps != 1 else ''} · ~{hours}h to learn",
        cls="text-xs text-warning ml-2",
    )


def _goal_focus_section(plan: "DailyWorkPlan") -> "Div | None":
    """Advancing goals with their mastery-aware learning requirements.

    Surfaces what knowledge still blocks each goal the daily plan recommends
    advancing — the production rendering of the consolidated learning-requirements
    lens. Returns None when the plan has no contextual goals.
    """
    if not plan.contextual_goals:
        return None

    goal_items = [
        Div(
            Span("🎯", cls="mr-2"),
            Span(getattr(g, "title", "Goal"), cls="text-sm"),
            _goal_learning_requirements_line(g),
            cls="flex items-center flex-wrap py-1",
        )
        for g in plan.contextual_goals[:3]
    ]
    return Div(
        P("PRIORITY 4: Advancing goals", cls="text-xs font-bold text-muted-foreground mb-1"),
        *goal_items,
        cls="mb-3",
    )


def _daily_work_plan_card(plan: "DailyWorkPlan") -> Div:
    """Daily work plan card showing today's optimal focus.

    Displays prioritized items across domains with capacity utilization.
    When the user has active PS engagements, those are surfaced above the
    flat priority lists so it's visible which plan items came from engaged
    curriculum.

    Args:
        plan: DailyWorkPlan from intelligence service (REQUIRED)
    """
    # Capacity bar
    capacity_percent = int(plan.workload_utilization * 100)
    capacity_variant = ProgressT.success if plan.fits_capacity else ProgressT.warning

    # Engaged PS section (None when no active engagements)
    engaged_section = _engaged_ps_section(plan)

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
                    cls="text-xs text-muted-foreground ml-2",
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
                    P("PRIORITY 2: Tasks", cls="text-xs font-bold text-muted-foreground mb-1"),
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
                    cls="text-xs text-muted-foreground ml-2",
                ),
                cls="flex items-center py-1",
            )
            for k in plan.contextual_knowledge[:2]
        ]
        priority_sections.append(
            Div(
                P("PRIORITY 3: Learning", cls="text-xs font-bold text-muted-foreground mb-1"),
                *learning_items,
                cls="mb-3",
            )
        )

    # Priority 4: Advancing goals + mastery-aware learning requirements
    goal_section = _goal_focus_section(plan)
    if goal_section is not None:
        priority_sections.append(goal_section)

    # Fallback if no priorities
    if not priority_sections:
        if plan.rationale:
            priority_sections.append(
                Div(P(plan.rationale, cls="text-sm text-muted-foreground italic"))
            )
        else:
            priority_sections.append(EmptyState("No specific priorities for today", cls="py-4"))

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
            cls="mt-3 pt-3 border-t border-border",
        )

    return Div(
        # Header
        Div(
            Span("📅", cls="text-2xl mr-3"),
            Span("TODAY'S FOCUS", cls="font-bold text-foreground"),
            cls="flex items-center mb-3",
        ),
        # Capacity bar
        Div(
            P(f"Capacity: {capacity_percent}% utilized", cls="text-xs text-muted-foreground mb-1"),
            Progress(value=min(capacity_percent, 100), variant=capacity_variant),
            cls="mb-4",
        ),
        # Engaged PS groups (above flat priorities — these are explicit commitments)
        engaged_section,
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
        "exploring": "text-muted-foreground",
        "drifting": "text-warning",
    }
    level_color = level_colors.get(alignment.alignment_level, "text-muted-foreground")
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
                    Span(name, cls="text-xs text-muted-foreground w-20"),
                    Progress(value=score_percent, cls="flex-1"),
                    Span(f"{score_percent}%", cls="text-xs text-muted-foreground w-10 text-right"),
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
                P(alignment.strengths[0], cls="text-xs text-muted-foreground"),
                cls="flex-1",
            )
        )
    if alignment.gaps:
        insights_section.append(
            Div(
                P("Gaps:", cls="text-xs font-semibold text-warning mb-1"),
                P(alignment.gaps[0], cls="text-xs text-muted-foreground"),
                cls="flex-1",
            )
        )

    return Div(
        # Header with overall score
        Div(
            Span("🎯", cls="text-2xl mr-3"),
            Div(
                Span(f"LIFE PATH ALIGNMENT: {overall_percent}%", cls="font-bold text-foreground"),
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
        cls="bg-muted rounded-xl p-4 mb-6",
    )


def _synergies_card(synergies: "list[CrossDomainSynergy]") -> Div:
    """High-leverage actions card showing cross-domain synergies.

    Displays detected synergies between entities across domains.

    Args:
        synergies: List of CrossDomainSynergy from intelligence service (REQUIRED, may be empty)
    """
    # Empty list is valid data - user genuinely has no synergies
    if len(synergies) == 0:
        return EmptyState(
            "No synergies detected yet", icon="🚀", cls="bg-muted rounded-lg p-4 mb-6"
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
                    Span(domain_arrow, cls="font-medium text-sm text-foreground"),
                    Span(f"(score: {score_percent}%)", cls="text-xs text-muted-foreground ml-2"),
                    cls="flex items-center mb-1",
                ),
                # Rationale
                P(
                    synergy.rationale[:80] + "..."
                    if len(synergy.rationale) > 80
                    else synergy.rationale,
                    cls="text-xs text-muted-foreground",
                ),
                # Targets count
                P(
                    f"Affects {len(synergy.target_uids)} {synergy.target_domain}(s)",
                    cls="text-xs text-primary mt-1",
                ),
                cls="py-2 border-b border-border last:border-0",
            )
        )

    return Div(
        # Header
        Div(
            Span("🚀", cls="text-xl mr-2"),
            Span("HIGH-LEVERAGE ACTIONS", cls="font-bold text-foreground"),
            cls="flex items-center mb-3",
        ),
        # Synergy items
        *synergy_items,
        cls="bg-muted rounded-xl p-4 mb-6",
    )


def _path_steps_card(steps: "list[PathStep]") -> Div:
    """Next path steps card showing prioritized learning recommendations.

    Displays recommended knowledge units to learn with context.

    Args:
        steps: List of PathStep from intelligence service (REQUIRED, may be empty)
    """
    # Empty list is valid data - no recommendations available
    if len(steps) == 0:
        return EmptyState(
            "No learning recommendations available", icon="📚", cls="bg-muted rounded-lg p-4 mb-6"
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
                        Span(step.title, cls="font-medium text-foreground"),
                        cls="flex items-center mb-1",
                    ),
                    # Stats row
                    Div(
                        Span(f"Priority: {priority_percent}%", cls="text-xs text-muted-foreground"),
                        Span("|", cls="mx-2 text-muted-foreground"),
                        Span(
                            f"{step.estimated_time_minutes} min",
                            cls="text-xs text-muted-foreground",
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
                        Span("|", cls="mx-2 text-muted-foreground")
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
                    cls="py-2 border-b border-border last:border-0",
                ),
                href=f"/explore/ku/{step.ku_uid}",
                cls="block hover:bg-muted/50 -mx-2 px-2 rounded transition-colors",
            )
        )

    return Div(
        # Header
        Div(
            Span("📚", cls="text-xl mr-2"),
            Span("NEXT LEARNING STEPS", cls="font-bold text-foreground"),
            cls="flex items-center mb-3",
        ),
        # Step items
        *step_items,
        cls="bg-muted rounded-xl p-4 mb-6",
    )
