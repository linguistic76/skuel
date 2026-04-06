"""Personal header — Focus + Velocity compact display.

Shared between /home and /profile pages. Requires UserContext.

For pages that don't already have UserContext loaded (e.g. /tasks),
use ``personal_header_placeholder()`` — an HTMX div that lazy-loads
the header via ``GET /api/personal-header`` without blocking the page render.
"""

from fasthtml.common import Div, Span

from core.services.user.unified_user_context import UserContext


def personal_header_placeholder() -> Div:
    """HTMX placeholder that lazy-loads the Focus + Velocity header.

    Use this instead of ``personal_header(context)`` when you don't
    already have a UserContext — avoids running the MEGA_QUERY on the
    critical path of the page render.
    """
    return Div(
        id="personal-header",
        hx_get="/api/personal-header",
        hx_trigger="load",
        hx_swap="outerHTML",
    )


def personal_header(context: UserContext) -> Div:
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
