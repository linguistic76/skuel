"""Lean profile view — Focus + Steady measurements only.

This is the stripped-down /profile page. Activity domains live at /activities.
Learning content lives at /learn.
"""

from fasthtml.common import H2, A, Div, Span

from core.services.user.unified_user_context import UserContext
from ui.buttons import ButtonLink, ButtonT
from ui.layout import Size


def LeanProfileView(context: UserContext) -> Div:
    """Lean profile: Focus measurement + Steady measurement + Settings link.

    Args:
        context: UserContext with ~240 fields of user state
    """
    return Div(
        _header(),
        _current_focus_card(context),
        _velocity_summary(context),
        _settings_link(),
        cls="max-w-2xl",
    )


def _header() -> Div:
    return Div(
        H2("Your Profile", cls="text-xl font-semibold text-foreground"),
        cls="mb-6",
    )


def _current_focus_card(context: UserContext) -> Div:
    """Current task focus — compact inline element."""
    if not context.current_task_focus:
        return A(
            Span("🎯", cls="text-lg mr-2"),
            Span(
                "No current focus set",
                cls="text-sm text-muted-foreground group-hover:text-primary transition-colors",
            ),
            href="/tasks",
            cls="flex items-center mb-4 group",
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
        A(
            task_title,
            href=f"/tasks/get?uid={context.current_task_focus}",
            cls="text-sm font-medium text-primary hover:underline",
        ),
        cls="flex items-center mb-4",
    )


def _velocity_summary(context: UserContext) -> Div:
    """Overall velocity — compact inline indicator."""
    total_velocity = sum(context.velocity_by_domain.values())
    total_time = sum(context.time_invested_hours_by_domain.values())

    if total_velocity > 0.5:
        momentum = ("🚀", "Strong Momentum", "text-success")
    elif total_velocity > 0:
        momentum = ("📈", "Building", "text-primary")
    elif total_velocity > -0.3:
        momentum = ("➡️", "Steady", "text-muted-foreground")
    else:
        momentum = ("📉", "Slowing", "text-warning")

    icon, label, color = momentum

    return Div(
        Span(icon, cls="text-lg mr-2"),
        Span(label, cls=f"text-sm font-medium {color}"),
        Span(" · ", cls="text-foreground/30 mx-2"),
        Span(f"{total_time:.1f}h invested", cls="text-sm text-muted-foreground"),
        cls="flex items-center mb-6",
    )


def _settings_link() -> Div:
    return Div(
        ButtonLink(
            Span("⚙️", cls="mr-2"),
            "Settings",
            href="/profile/settings",
            variant=ButtonT.ghost,
            size=Size.sm,
            cls="text-muted-foreground hover:text-foreground",
        ),
        cls="mt-8 pt-6 border-t border-border",
    )
