"""Setting toggle pattern for configurable behavior display.

Shows a named setting with enabled/disabled status. Useful for any
entity or system with user-configurable behavior.
"""

from fasthtml.common import Div, P, Span


def SettingToggle(name: str, description: str, enabled: bool = True) -> Div:
    """Toggle setting display with status.

    Args:
        name: Setting name
        description: Setting description
        enabled: Current enabled state

    Returns:
        Div with toggle display
    """
    status_color = "text-success" if enabled else "text-muted-foreground"
    status_text = "Enabled" if enabled else "Disabled"

    return Div(
        Div(
            Span(name, cls="font-medium"),
            Span(status_text, cls=f"text-sm {status_color}"),
            cls="flex justify-between items-center",
        ),
        P(description, cls="text-sm text-muted-foreground mt-1"),
        cls="p-3 border border-border rounded cursor-pointer hover:bg-muted",
    )
