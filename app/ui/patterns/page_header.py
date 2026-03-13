"""Page header component for consistent page titles.

Usage:
    from ui.patterns.page_header import PageHeader

    PageHeader("Tasks", subtitle="Manage your daily tasks")
    PageHeader("Goals", actions=Button("Create Goal", variant=ButtonT.primary))
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import H1, Div, P

if TYPE_CHECKING:
    from fasthtml.common import FT


def PageHeader(
    title: str,
    subtitle: str = "",
    actions: Any = None,
    cls: str = "",
) -> "FT":
    """Consistent page header with title, optional subtitle, and actions.

    Args:
        title: Main page title
        subtitle: Optional subtitle or description
        actions: Optional action buttons (right-aligned)
        cls: Additional CSS classes

    Returns:
        Page header component
    """
    title_section = Div(
        H1(title, cls="text-2xl font-bold text-foreground"),
        P(subtitle, cls="text-muted-foreground mt-1") if subtitle else None,
    )

    if actions:
        return Div(
            title_section,
            Div(actions, cls="flex gap-2"),
            cls=f"flex justify-between items-start mb-8 {cls}".strip(),
        )

    return Div(
        title_section,
        cls=f"mb-8 {cls}".strip(),
    )


__all__ = ["PageHeader"]
