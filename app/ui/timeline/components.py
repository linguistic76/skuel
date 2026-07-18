"""
Timeline UI Components
======================

UI components for the Vis.js Timeline viewer.

Replaced Markwhen with Vis.js Timeline (January 2026) for:
- Better interactivity (zoom, pan, drag)
- JSON data format (matches CalendarItem model)
- Grouping support (tasks, events, habits)
- Active maintenance and documentation

Usage:
    from ui.timeline.components import render_timeline_viewer_page
"""

__version__ = "2.0"  # Vis.js Timeline version


from typing import TYPE_CHECKING

from fasthtml.common import Div, Option, P, Span

from core.models.type_hints import UserUID
from ui.components import Button, ButtonT
from ui.feedback import Loading
from ui.forms import Input, Label, Select
from ui.layout import Size
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.page_header import PageHeader
from ui.patterns.skeleton import SkeletonTimeline

if TYPE_CHECKING:
    from fasthtml.common import FT

    from adapters.inbound.fasthtml_types import Request

_VIS_TIMELINE_CSS = "/static/vendor/vis-timeline/vis-timeline-graph2d.min.css"
_VIS_TIMELINE_JS = "/static/vendor/vis-timeline/vis-timeline-graph2d.min.js"


def render_timeline_viewer_page(
    request: "Request",
    src: str | None = None,
    project: str | None = None,
    user_uid: UserUID | None = None,
) -> "FT":
    """Render the Vis.js timeline viewer page via BasePage.

    Args:
        request: Starlette request (for navbar auth detection).
        src: Timeline data source URL (defaults to visualization API).
        project: Optional project filter.
        user_uid: User UID for data filtering.
    """
    if src:
        data_url = src
    else:
        params = []
        if user_uid:
            params.append(f"user_uid={user_uid}")
        if project:
            params.append(f"project={project}")
        param_str = "&".join(params) if params else ""
        data_url = (
            f"/api/visualizations/timeline?{param_str}"
            if param_str
            else "/api/visualizations/timeline"
        )

    content = Div(
        _render_header(),
        Div(
            _render_controls(),
            _render_filters(project, user_uid),
            _render_timeline_container(),
            cls="timeline-page",
            **{"x-data": f"timelineVis('{data_url}')"},
        ),
    )

    return BasePage(
        content,
        title="Timeline",
        page_type=PageType.CUSTOM,
        request=request,
        active_page="timelines",
        extra_css=[_VIS_TIMELINE_CSS, "/static/css/timeline.css"],
        extra_scripts=[_VIS_TIMELINE_JS],
    )


def _render_header() -> Div:
    """Render the page header."""
    return Div(
        Div(
            PageHeader("Timeline", subtitle="Interactive schedule visualization"),
            cls="container",
        ),
        cls="header",
    )


def _render_controls() -> Div:
    """Render zoom and view controls."""
    return Div(
        # Zoom controls
        Div(
            Span("Zoom:", cls="text-sm text-muted-foreground mr-2"),
            Button(
                "+",
                cls=ButtonT.ghost,
                size="sm",
                **{"@click": "zoomIn()"},  # fasthtml dynamic-attr splat
                title="Zoom in",
            ),
            Button(
                "-",
                cls=ButtonT.ghost,
                size="sm",
                **{"@click": "zoomOut()"},  # fasthtml dynamic-attr splat
                title="Zoom out",
            ),
            Button(
                "Fit All",
                cls=ButtonT.ghost,
                size="sm",
                **{"@click": "fit()"},  # fasthtml dynamic-attr splat
                title="Fit all items",
            ),
            cls="flex items-center gap-1",
        ),
        # Refresh button
        Button(
            "Refresh",
            cls=ButtonT.primary,
            size="sm",
            **{"@click": "refresh()"},  # fasthtml dynamic-attr splat
        ),
        cls="controls flex justify-between items-center p-4 border-b",
    )


def _render_filters(project: str | None = None, user_uid: UserUID | None = None) -> Div:
    """Render the filter controls."""
    return Div(
        Div(
            Label("Start Date", cls="text-sm font-medium"),
            Input(
                type="date",
                name="startDate",
                size=Size.sm,
                x_ref="startDate",
            ),
            cls="filter-group",
        ),
        Div(
            Label("End Date", cls="text-sm font-medium"),
            Input(
                type="date",
                name="endDate",
                size=Size.sm,
                x_ref="endDate",
            ),
            cls="filter-group",
        ),
        Div(
            Label("Project", cls="text-sm font-medium"),
            Input(
                type="text",
                name="project",
                placeholder="Filter by project",
                value=project or "",
                size=Size.sm,
                x_ref="project",
            ),
            cls="filter-group",
        ),
        Div(
            Label("Group By", cls="text-sm font-medium"),
            Select(
                Option("By Type", value="type", selected=True),
                Option("By Project", value="project"),
                Option("No Grouping", value="none"),
                name="groupBy",
                size=Size.sm,
                x_ref="groupBy",
            ),
            cls="filter-group",
        ),
        Button(
            "Apply Filters",
            cls=ButtonT.primary,
            size="sm",
            **{"@click": "applyFilters()"},  # fasthtml dynamic-attr splat
        ),
        # Hidden user_uid for API calls
        Input(type="hidden", name="user_uid", value=user_uid or "", x_ref="userUid"),
        cls="filters grid grid-cols-2 md:grid-cols-5 gap-4 p-4 bg-muted",
    )


def _render_timeline_container() -> Div:
    """Render the timeline container with loading states."""
    return Div(
        # Loading skeleton — Gantt-shaped shimmer fills the full container height
        Div(
            SkeletonTimeline(),
            cls="h-full overflow-hidden",
            **{"x-show": "loading"},
        ),
        # Error state
        Div(
            P(
                "Failed to load timeline: ",
                Span(**{"x-text": "error"}),
                cls="text-error",
            ),
            Button(
                "Retry",
                cls=(ButtonT.destructive, "mt-2"),
                size="sm",
                **{"@click": "refresh()"},  # fasthtml dynamic-attr splat
            ),
            cls="flex flex-col items-center justify-center h-full",
            **{"x-show": "error"},
        ),
        # Vis.js Timeline container
        Div(
            **{"x-ref": "container"},
            cls="w-full h-full",
            **{"x-show": "!loading && !error"},
        ),
        cls="timeline-container h-[70vh] border rounded-lg bg-background",
    )


def render_timeline_error(
    error_message: str,
    request: "Request | None" = None,
) -> "FT":
    """Render a timeline error page via BasePage.

    Args:
        error_message: Error message to display.
        request: Starlette request for navbar auth detection.
    """
    content = Div(
        PageHeader("Timeline Error"),
        P(f"Error: {error_message}", cls="mt-4"),
        P("Please check the server logs for more details.", cls="text-muted-foreground mt-2"),
        Button("Go Back", cls=(ButtonT.primary, "mt-4"), onclick="history.back()"),
    )
    return BasePage(content, title="Timeline Error", request=request)


# =============================================================================
# Standalone Timeline Components (for embedding)
# =============================================================================


def create_embedded_timeline(
    data_url: str,
    height: str = "h-96",
    show_controls: bool = True,
) -> Div:
    """
    Create an embedded timeline component for use in other pages.

    Args:
        data_url: API endpoint for timeline data
        height: Tailwind height class
        show_controls: Whether to show zoom controls

    Returns:
        Div element with timeline (requires Vis.js to be loaded)
    """
    controls = []
    if show_controls:
        controls.append(
            Div(
                Button(
                    "+", cls=ButtonT.ghost, size="xs", **{"@click": "zoomIn()"}
                ),  # fasthtml dynamic-attr splat
                Button(
                    "-", cls=ButtonT.ghost, size="xs", **{"@click": "zoomOut()"}
                ),  # fasthtml dynamic-attr splat
                Button(
                    "Fit", cls=ButtonT.ghost, size="xs", **{"@click": "fit()"}
                ),  # fasthtml dynamic-attr splat
                cls="absolute top-2 right-2 flex gap-1 z-10",
            )
        )

    return Div(
        *controls,
        # Loading
        Div(
            Loading(size=Size.sm),
            cls="flex items-center justify-center h-full",
            **{"x-show": "loading"},
        ),
        # Error
        Div(
            Span(**{"x-text": "error"}, cls="text-error text-sm"),
            **{"x-show": "error"},
        ),
        # Container
        Div(
            **{"x-ref": "container"},
            cls=f"w-full {height}",
            **{"x-show": "!loading && !error"},
        ),
        cls=f"relative {height} border rounded-lg",
        **{"x-data": f"timelineVis('{data_url}')"},
    )


__all__ = [
    "create_embedded_timeline",
    "render_timeline_error",
    "render_timeline_viewer_page",
]
