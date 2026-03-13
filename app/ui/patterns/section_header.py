"""Section header component for consistent section titles.

Usage:
    from ui.patterns.section_header import SectionHeader

    SectionHeader("Recent Tasks")
    SectionHeader("Active Goals", action=A("View All", href="/goals"))
"""

from typing import TYPE_CHECKING, Any

from fasthtml.common import H2, Div

if TYPE_CHECKING:
    from fasthtml.common import FT


def SectionHeader(
    title: str,
    action: Any = None,
    cls: str = "",
) -> "FT":
    """Consistent section header with title and optional action.

    Args:
        title: Section title
        action: Optional action link or button (right-aligned)
        cls: Additional CSS classes

    Returns:
        Section header component
    """
    if action:
        return Div(
            H2(title, cls="text-xl font-semibold text-foreground"),
            action,
            cls=f"flex justify-between items-center mb-6 {cls}".strip(),
        )

    return Div(
        H2(title, cls="text-xl font-semibold text-foreground"),
        cls=f"mb-6 {cls}".strip(),
    )


__all__ = ["SectionHeader"]
