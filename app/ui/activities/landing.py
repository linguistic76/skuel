"""Activities landing page — card grid for all activity domains.

No sidebar. Shows 6 Activity Domain cards + Journal + Knowledge at a glance.
Each card links into /activities/{domain} for the full domain view.
"""

from typing import Any

from fasthtml.common import H2, A, Div, Li, P, Span, Ul

from core.models.enums import Priority
from core.services.user.unified_user_context import UserContext
from ui.feedback import Badge, BadgeT


def ActivitiesLandingView(context: UserContext) -> Div:
    """Landing page content for /activities.

    Shows a card grid: 6 Activity Domains (HTMX-loaded item previews)
    + Knowledge (static stat) + Journals (CTA).
    """
    header = Div(
        H2("Activities", cls="text-xl font-semibold text-foreground"),
        P("Your activity domains at a glance.", cls="text-sm text-muted-foreground mt-0.5"),
        cls="mb-6",
    )

    return Div(
        header,
        domain_card_grid(context),
    )


# ---------------------------------------------------------------------------
# Domain card grid
# ---------------------------------------------------------------------------

_ACTIVITY_DOMAINS: list[tuple[str, str, str]] = [
    ("✅", "Tasks", "tasks"),
    ("🔄", "Habits", "habits"),
    ("🎯", "Goals", "goals"),
    ("📅", "Events", "events"),
    ("⚖️", "Principles", "principles"),
    ("🔀", "Choices", "choices"),
]

_ACTIVE_COUNT_GETTERS: dict[str, str] = {
    "tasks": "active_task_uids",
    "habits": "active_habit_uids",
    "goals": "active_goal_uids",
    "events": "upcoming_event_uids",
    "principles": "core_principle_uids",
    "choices": "pending_choice_uids",
}

_CREATE_HREFS: dict[str, str] = {
    "tasks": "/tasks?view=create",
    "habits": "/habits?view=create",
    "goals": "/goals?view=create",
    "events": "/events?view=create",
    "principles": "/principles?view=create",
    "choices": "/choices?view=create",
}

_PRIORITY_COLORS: dict[Priority, str] = {
    Priority.CRITICAL: "bg-red-500",
    Priority.HIGH: "bg-orange-500",
    Priority.MEDIUM: "bg-blue-500",
    Priority.LOW: "bg-gray-400",
}

_PRIORITY_LABELS: dict[Priority, str] = {
    Priority.CRITICAL: "P1",
    Priority.HIGH: "P2",
    Priority.MEDIUM: "P3",
    Priority.LOW: "P4",
}


def _card_preview_skeleton() -> Div:
    """Animated skeleton shown while HTMX loads item lists."""
    return Div(
        Div(cls="h-4 bg-muted rounded animate-pulse"),
        Div(cls="h-4 bg-muted rounded animate-pulse w-4/5"),
        Div(cls="h-4 bg-muted rounded animate-pulse w-3/5"),
        cls="space-y-2 py-1",
    )


def domain_card_grid(context: UserContext) -> Div:
    """8-card grid: 6 Activity Domains + Knowledge + Journals."""
    cards: list[Any] = []

    for icon, name, slug in _ACTIVITY_DOMAINS:
        attr = _ACTIVE_COUNT_GETTERS[slug]
        active_count = len(getattr(context, attr, []))
        create_href = _CREATE_HREFS[slug]

        create_btn = A(
            "+",
            href=create_href,
            cls="w-7 h-7 flex items-center justify-center rounded-full "
            "text-foreground/40 hover:text-foreground hover:bg-muted "
            "transition-colors text-lg font-bold leading-none",
            title=f"New {name.removesuffix('s')}",
        )

        cards.append(
            Div(
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
                Div(
                    _card_preview_skeleton(),
                    hx_get=f"/api/activities/{slug}/preview",
                    hx_trigger="load",
                    hx_swap="innerHTML",
                    cls="min-h-[100px]",
                ),
                cls="bg-background rounded-xl p-5 shadow-sm hover:shadow-md transition-shadow",
            )
        )

    # Knowledge card
    total_knowledge = len(context.mastered_knowledge_uids) + len(context.in_progress_knowledge_uids)
    mastered = len(context.mastered_knowledge_uids)
    knowledge_secondary = (
        Span(f"{mastered} mastered", cls="text-sm text-muted-foreground") if mastered > 0 else None
    )
    cards.append(
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

    # Journals card
    cards.append(
        Div(
            Div(
                Div(
                    Span("📓", cls="text-xl"),
                    Span("Journals", cls="text-base font-semibold text-foreground"),
                    cls="flex items-center gap-2",
                ),
                A(
                    "+",
                    href="/journals/submit",
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
                href="/journals/submit",
                cls="text-xs text-primary hover:underline mt-2 inline-block",
            ),
            cls="bg-background rounded-xl p-5 shadow-sm hover:shadow-md transition-shadow",
        )
    )

    return Div(
        *cards,
        cls="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 lg:gap-5",
    )


def render_activity_card_preview(items: list[Any], slug: str) -> Div:
    """Render domain card preview HTML fragment for /api/activities/{slug}/preview.

    Shows up to 5 active items sorted by priority with a "View all" link.
    """
    view_href = f"/{slug}"

    if not items:
        return Div(
            P(
                f"No active {slug}",
                cls="text-sm text-foreground/40 text-center py-3",
            ),
            A(
                f"View all {slug} →",
                href=view_href,
                cls="text-xs text-primary hover:underline block text-center",
            ),
        )

    def _priority_dot(item: Any) -> Span:
        raw = getattr(item, "priority", Priority.LOW)
        if not isinstance(raw, Priority):
            try:
                raw = Priority(str(raw).lower())
            except ValueError:
                raw = Priority.LOW
        color = _PRIORITY_COLORS.get(raw, "bg-gray-400")
        label = _PRIORITY_LABELS.get(raw, "P4")
        return Span(
            Span(cls=f"w-2 h-2 rounded-full {color} shrink-0"),
            Span(label, cls="text-xs font-medium text-muted-foreground w-5"),
            cls="inline-flex items-center gap-1 shrink-0",
            title=f"Priority: {raw.value.title()}",
        )

    rows = [
        Li(
            _priority_dot(item),
            Span(
                getattr(item, "title", "Untitled"),
                cls="text-sm text-foreground truncate flex-1 min-w-0",
            ),
            cls="flex items-center gap-2 py-1.5",
        )
        for item in items
    ]

    return Div(
        Ul(*rows, cls="divide-y divide-border"),
        A(
            f"View all {slug} →",
            href=view_href,
            cls="text-xs text-primary hover:underline mt-3 inline-block",
        ),
    )
