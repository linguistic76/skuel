"""Dashboard layout pattern for domain pages.

This layout provides a consistent structure for domain dashboards
(Tasks, Goals, Habits, etc.) with stats, filters, and entity lists.
"""

from typing import Any

from fasthtml.common import Div

from ui.buttons import ButtonLink, ButtonT
from ui.layout import Container, Row, Size, Stack
from ui.patterns.stats_grid import StatsGrid
from ui.text import PageTitle


def DashboardLayout(
    title: str,
    subtitle: str | None = None,
    stats: list[dict[str, Any]] | None = None,
    quick_actions: list[dict[str, str]] | None = None,
    filters: Any = None,
    content: Any = None,
    **kwargs: Any,
) -> Div:
    """Standard dashboard layout for domain pages.

    This layout provides a consistent structure used across all entity types:
    - Page title with optional subtitle
    - Quick action buttons (top right)
    - Stats grid showing key metrics
    - Optional filter controls
    - Main content area (typically entity list or grid)

    Args:
        title: Page title
        subtitle: Optional subtitle/description
        stats: Optional list of stat dictionaries for StatsGrid
        quick_actions: Optional list of action dictionaries with:
            - label: Button text
            - href: Button URL
            - variant: Optional button variant (default: "primary")
        filters: Optional filter component/content
        content: Main content (entity list, grid, etc.)
        **kwargs: Additional attributes passed to Container

    Returns:
        A Container with the dashboard layout

    Example:
        DashboardLayout(
            title="Tasks",
            subtitle="Manage your tasks and to-dos",
            stats=[
                {"label": "Total", "value": 150},
                {"label": "Active", "value": 42},
                {"label": "Completed", "value": 98},
                {"label": "Overdue", "value": 10, "trend": "down"},
            ],
            quick_actions=[
                {"label": "New Task", "href": "/tasks/create"},
            ],
            filters=TaskFilters(),
            content=TaskList(tasks),
        )
    """
    sections = []

    # Header section: title + quick actions
    if quick_actions:
        variant_map = {v.name: v for v in ButtonT}
        action_buttons = [
            ButtonLink(
                a["label"],
                href=a["href"],
                variant=variant_map.get(a.get("variant", "primary"), ButtonT.primary),
            )
            for a in quick_actions
        ]
        header = Row(
            Div(PageTitle(title, subtitle), cls="flex-1"),
            Div(*action_buttons, cls="flex gap-2 flex-shrink-0"),
            align="items-start",
        )
    else:
        header = PageTitle(title, subtitle)

    sections.append(header)

    # Stats grid
    if stats:
        sections.append(StatsGrid(stats))

    # Filters
    if filters:
        sections.append(Div(filters, cls="py-4"))

    # Main content
    if content:
        sections.append(content)

    return Container(Stack(*sections, gap=6), **kwargs)


def DashboardSection(
    title: str,
    *children: Any,
    actions: list[dict[str, str]] | None = None,
    **kwargs: Any,
) -> Div:
    """Section within a dashboard with optional header actions.

    Use this for grouping content within a dashboard page.

    Args:
        title: Section title
        *children: Section content
        actions: Optional action buttons for the section header
        **kwargs: Additional attributes passed to the section Div

    Returns:
        A Div containing the section

    Example:
        DashboardSection(
            "Recent Tasks",
            TaskList(recent_tasks),
            actions=[{"label": "View All", "href": "/tasks"}],
        )
    """
    from ui.text import SectionTitle

    if actions:
        action_links = [
            ButtonLink(a["label"], href=a["href"], variant=ButtonT.ghost, size=Size.sm)
            for a in actions
        ]
        header = Row(
            Div(SectionTitle(title), cls="flex-1"),
            Div(*action_links, cls="flex gap-2"),
            align="items-center",
        )
    else:
        header = SectionTitle(title)

    base_cls = "mt-8"
    extra_cls = kwargs.pop("cls", "")
    full_cls = f"{base_cls} {extra_cls}".strip()

    return Div(
        header,
        *children,
        cls=full_cls,
        **kwargs,
    )
