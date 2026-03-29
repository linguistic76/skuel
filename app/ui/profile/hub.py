"""Profile hub page — grouped card grid (MOC pattern).

The /profile page is a hub: cards with links grouped under section headers.
No sidebar. Uses BasePage(STANDARD).

See: /docs/design-principles/HUB_PAGES.md
"""

from fasthtml.common import A, Div, P, Span

from core.services.user.unified_user_context import UserContext

# Card definitions: (icon, name, href, description)
_KNOWLEDGE_CARDS: list[tuple[str, str, str, str]] = [
    ("📖", "Knowledge", "/ku", "Atomic knowledge units — concepts, facts, vocabulary."),
    ("📚", "Lessons", "/lessons", "Learning content that composes atomic knowledge."),
]

_PRACTICE_CARDS: list[tuple[str, str, str, str]] = [
    ("🏋️", "Exercises", "/exercises", "Practice linked to lessons and knowledge units."),
    ("📤", "Submit Work", "/submit", "Upload submissions for review."),
    ("📝", "Submissions", "/submissions", "Track submitted work and review status."),
]

_REPORTS_CARDS: list[tuple[str, str, str, str]] = [
    ("📋", "Exercise Reports", "/exercise-reports", "Teacher and AI feedback on submissions."),
    ("📊", "Activity Reports", "/activity-reports", "Progress reports across domains."),
]


def ProfileHubView(context: UserContext) -> Div:
    """Profile hub — Focus/Velocity header + grouped card grid."""
    return Div(
        _personal_header(context),
        _card_section("Knowledge", _KNOWLEDGE_CARDS),
        _card_section("Practice", _PRACTICE_CARDS),
        _card_section("Reports", _REPORTS_CARDS),
        _settings_link(),
    )


def _personal_header(context: UserContext) -> Div:
    """Focus + Velocity compact header."""
    focus = _focus_line(context)
    velocity = _velocity_line(context)
    return Div(focus, velocity, cls="mb-2")


def _focus_line(context: UserContext) -> Div:
    """Current task focus — compact inline."""
    if not context.current_task_focus:
        return Div(
            Span("🎯", cls="text-lg mr-2"),
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
        Span("🎯", cls="text-lg mr-2"),
        Span("Focus: ", cls="text-sm font-medium text-muted-foreground"),
        Span(task_title, cls="text-sm font-medium text-primary"),
        cls="flex items-center mb-2",
    )


def _velocity_line(context: UserContext) -> Div:
    """Overall velocity — compact inline indicator."""
    total_velocity = sum(context.velocity_by_domain.values())
    total_time = sum(context.time_invested_hours_by_domain.values())

    if total_velocity > 0.5:
        icon, label, color = "🚀", "Strong Momentum", "text-success"
    elif total_velocity > 0:
        icon, label, color = "📈", "Building", "text-primary"
    elif total_velocity > -0.3:
        icon, label, color = "➡️", "Steady", "text-muted-foreground"
    else:
        icon, label, color = "📉", "Slowing", "text-warning"

    return Div(
        Span(icon, cls="text-lg mr-2"),
        Span(label, cls=f"text-sm font-medium {color}"),
        Span(" · ", cls="text-foreground/30 mx-2"),
        Span(f"{total_time:.1f}h invested", cls="text-sm text-muted-foreground"),
        cls="flex items-center mb-4",
    )


def _card_section(title: str, cards: list[tuple[str, str, str, str]]) -> Div:
    """Section header + 2-column card grid."""
    header = Span(
        title,
        cls="text-xs font-semibold uppercase tracking-wider text-muted-foreground",
    )
    grid = Div(
        *[_hub_card(icon, name, href, desc) for icon, name, href, desc in cards],
        cls="grid grid-cols-1 sm:grid-cols-2 gap-4 lg:gap-5",
    )
    return Div(header, grid, cls="mb-6")


def _hub_card(icon: str, name: str, href: str, description: str) -> A:
    """Single hub card — icon + title + description, links to target page."""
    return A(
        Div(
            Div(
                Span(icon, cls="text-xl"),
                Span(name, cls="text-base font-semibold text-foreground"),
                cls="flex items-center gap-2",
            ),
            cls="mb-3",
        ),
        P(description, cls="text-sm text-muted-foreground"),
        href=href,
        cls="bg-background rounded-xl p-5 shadow-sm hover:shadow-md transition-shadow block",
    )


def _settings_link() -> Div:
    """Compact settings link at the bottom."""
    return Div(
        A(
            Span("⚙️", cls="mr-2"),
            "Settings",
            href="/profile/settings",
            cls="text-sm text-muted-foreground hover:text-foreground",
        ),
        cls="mt-4 pt-6 border-t border-border",
    )
