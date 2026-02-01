"""Error Banner Pattern - User-Friendly Error Rendering

Reusable error banner component for displaying Result[T] errors to users.

Usage:
    from ui.patterns.error_banner import render_error_banner

    if result.is_error:
        return BasePage(
            content=render_error_banner(
                "Unable to load tasks",
                result.error.message
            ),
            title="Tasks",
            request=request
        )

WCAG Compliance:
    - role="alert" for screen reader announcements
    - Semantic color coding (error=red, warning=yellow, info=blue)
    - Clear, actionable messages
"""

from typing import TYPE_CHECKING

from fasthtml.common import Details, Div, P, Summary

if TYPE_CHECKING:
    from fasthtml.common import FT


def render_error_banner(
    user_message: str,
    technical_details: str | None = None,
    severity: str = "error",
    show_details: bool = False,
) -> "FT":
    """
    Render user-friendly error banner.

    Args:
        user_message: User-facing error message (clear, actionable)
        technical_details: Developer/debug information (optional)
        severity: Alert severity ('error', 'warning', 'info')
        show_details: Whether to show technical details (default: False, respects DEBUG mode)

    Returns:
        DaisyUI alert component with error message

    Example:
        # Simple error
        render_error_banner("Unable to save task")

        # With technical details (shown in dev mode)
        render_error_banner(
            "Unable to save task",
            technical_details="Database connection timeout",
            severity="error"
        )

        # Warning (non-critical)
        render_error_banner(
            "Some data may be incomplete",
            severity="warning"
        )
    """
    # Map severity to DaisyUI alert classes
    alert_class_map = {
        "error": "alert-error",
        "warning": "alert-warning",
        "info": "alert-info",
        "success": "alert-success",
    }
    alert_class = alert_class_map.get(severity, "alert-error")

    # Icon map for visual distinction
    icon_map = {
        "error": "❌",
        "warning": "⚠️",
        "info": "ℹ️",
        "success": "✅",
    }
    icon = icon_map.get(severity, "❌")

    # Build banner content
    content = [
        Div(
            Span(icon, cls="mr-2", **{"aria-hidden": "true"}),
            Span(user_message, cls="font-semibold"),
            cls="flex items-center"
        )
    ]

    # Conditionally show technical details
    # Check environment variable for DEBUG mode (common pattern in SKUEL)
    try:
        import os
        debug_mode = os.getenv("DEBUG", "false").lower() == "true"
    except Exception:
        debug_mode = False

    if technical_details and (show_details or debug_mode):
        content.append(
            Details(
                Summary("Technical Details (Dev Mode)", cls="cursor-pointer text-sm mt-2"),
                P(
                    technical_details,
                    cls="text-sm mt-2 font-mono bg-base-300 p-2 rounded"
                ),
                cls="mt-2"
            )
        )

    return Div(
        *content,
        cls=f"alert {alert_class} mb-4 shadow-lg",
        role="alert",  # WCAG: Screen reader announcement
        **{"aria-live": "polite"},  # WCAG: Announce dynamically added errors
    )


def render_inline_error(message: str) -> "FT":
    """
    Render inline error message for form fields.

    Args:
        message: Error message for specific field

    Returns:
        Small error text element

    Example:
        Div(
            Input(name="title", cls="input-error"),
            render_inline_error("Title is required"),
        )
    """
    return P(
        message,
        cls="text-error text-sm mt-1",
        role="alert",
        **{"aria-live": "polite"},
    )


def render_empty_state_with_error(
    title: str,
    message: str,
    action_label: str | None = None,
    action_href: str | None = None,
) -> "FT":
    """
    Render empty state with error context.

    Args:
        title: Empty state title
        message: Explanation of why it's empty (include error context)
        action_label: Optional call-to-action button label
        action_href: Optional call-to-action button link

    Returns:
        Empty state component with error context

    Example:
        render_empty_state_with_error(
            "No Tasks Found",
            "Unable to load tasks. Please refresh the page or try again later.",
            action_label="Refresh",
            action_href="/tasks"
        )
    """
    from fasthtml.common import A, Button, H3

    content = [
        H3(title, cls="text-xl font-bold text-base-content/70 mb-2"),
        P(message, cls="text-base-content/60 mb-4"),
    ]

    if action_label and action_href:
        content.append(
            A(
                Button(action_label, cls="btn btn-primary btn-sm"),
                href=action_href,
                cls="inline-block"
            )
        )

    return Div(
        *content,
        cls="text-center py-12 px-4"
    )


# Import Span for use in this module
from fasthtml.common import Span  # noqa: E402


__all__ = [
    "render_error_banner",
    "render_inline_error",
    "render_empty_state_with_error",
]
