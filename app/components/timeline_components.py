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
    from components.timeline_components import render_timeline_viewer_page
"""

__version__ = "2.0"  # Vis.js Timeline version


from fasthtml.common import (
    H1,
    Body,
    Button,
    Div,
    Head,
    Html,
    Input,
    Label,
    Link,
    Meta,
    Option,
    P,
    Script,
    Select,
    Span,
    Title,
)


def render_timeline_viewer_page(
    src: str | None = None,
    project: str | None = None,
    user_uid: str | None = None,
) -> Html:
    """
    Render the Vis.js timeline viewer page.

    Uses Alpine.js for state management and Vis.js Timeline for visualization.

    Args:
        src: Timeline source URL (optional, defaults to visualization API)
        project: Optional project filter
        user_uid: User UID for data filtering

    Returns:
        Complete HTML page for timeline viewer
    """
    # Build data URL
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

    return Html(
        Head(
            Title("SKUEL Timeline"),
            Meta(name="viewport", content="width=device-width, initial-scale=1"),
            # Vis.js Timeline CSS (local vendor)
            Link(rel="stylesheet", href="/static/vendor/vis-timeline/vis-timeline-graph2d.min.css"),
            # Custom timeline styles
            Link(rel="stylesheet", href="/static/css/timeline.css"),
            Link(rel="icon", href="/static/shared-assets/favicon.ico"),
            # Alpine.js (local)
            Script(src="/static/vendor/alpinejs/alpine.3.14.8.min.js", defer=True),
        ),
        Body(
            # Header
            _render_header(),
            # Main content wrapper with Alpine.js
            Div(
                # Controls row
                _render_controls(),
                # Filters
                _render_filters(project, user_uid),
                # Timeline container
                _render_timeline_container(),
                cls="timeline-page",
                **{"x-data": f"timelineVis('{data_url}')"},
            ),
            # Vis.js Timeline library (local vendor)
            Script(src="/static/vendor/vis-timeline/vis-timeline-graph2d.min.js"),
            # SKUEL Alpine.js components
            Script(src="/static/js/skuel.js"),
        ),
    )


def _render_header() -> Div:
    """Render the page header."""
    return Div(
        Div(
            H1("Timeline", style="margin: 0; color: #1e293b;"),
            P(
                "Interactive schedule visualization",
                style="margin: 0.5rem 0 0 0; color: #64748b; font-size: 0.9rem;",
            ),
            cls="container",
        ),
        cls="header",
    )


def _render_controls() -> Div:
    """Render zoom and view controls."""
    return Div(
        # Zoom controls
        Div(
            Span("Zoom:", cls="text-sm text-base-content/70 mr-2"),
            Button(
                "+",
                cls="btn btn-sm btn-ghost",
                **{"@click": "zoomIn()"},
                title="Zoom in",
            ),
            Button(
                "-",
                cls="btn btn-sm btn-ghost",
                **{"@click": "zoomOut()"},
                title="Zoom out",
            ),
            Button(
                "Fit All",
                cls="btn btn-sm btn-ghost",
                **{"@click": "fit()"},
                title="Fit all items",
            ),
            cls="flex items-center gap-1",
        ),
        # Refresh button
        Button(
            "Refresh",
            cls="btn btn-sm btn-primary",
            **{"@click": "refresh()"},
        ),
        cls="controls flex justify-between items-center p-4 border-b",
    )


def _render_filters(project: str | None = None, user_uid: str | None = None) -> Div:
    """Render the filter controls."""
    return Div(
        Div(
            Label("Start Date", cls="text-sm font-medium"),
            Input(
                type="date",
                name="startDate",
                cls="input input-bordered input-sm w-full",
                **{"x-ref": "startDate"},
            ),
            cls="filter-group",
        ),
        Div(
            Label("End Date", cls="text-sm font-medium"),
            Input(
                type="date",
                name="endDate",
                cls="input input-bordered input-sm w-full",
                **{"x-ref": "endDate"},
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
                cls="input input-bordered input-sm w-full",
                **{"x-ref": "project"},
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
                cls="select select-bordered select-sm w-full",
                **{"x-ref": "groupBy"},
            ),
            cls="filter-group",
        ),
        Button(
            "Apply Filters",
            cls="btn btn-sm btn-primary",
            **{"@click": "applyFilters()"},
        ),
        # Hidden user_uid for API calls
        Input(type="hidden", name="user_uid", value=user_uid or "", **{"x-ref": "userUid"}),
        cls="filters grid grid-cols-2 md:grid-cols-5 gap-4 p-4 bg-base-200",
    )


def _render_timeline_container() -> Div:
    """Render the timeline container with loading states."""
    return Div(
        # Loading indicator
        Div(
            Span(cls="loading loading-spinner loading-lg"),
            P("Loading timeline...", cls="mt-2 text-base-content/70"),
            cls="flex flex-col items-center justify-center h-full",
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
                cls="btn btn-sm btn-error mt-2",
                **{"@click": "refresh()"},
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
        cls="timeline-container h-[70vh] border rounded-lg bg-base-100",
    )


def render_timeline_error(error_message: str) -> Html:
    """
    Render a timeline error page.

    Args:
        error_message: Error message to display

    Returns:
        Error page HTML
    """
    return Html(
        Head(Title("Timeline Error")),
        Body(
            H1("Timeline Error", cls="text-2xl font-bold text-error"),
            P(f"Error: {error_message}", cls="mt-4"),
            P("Please check the server logs for more details.", cls="text-base-content/70"),
            Button(
                "Go Back",
                cls="btn btn-primary mt-4",
                onclick="history.back()",
            ),
        ),
    )


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
                Button("+", cls="btn btn-xs btn-ghost", **{"@click": "zoomIn()"}),
                Button("-", cls="btn btn-xs btn-ghost", **{"@click": "zoomOut()"}),
                Button("Fit", cls="btn btn-xs btn-ghost", **{"@click": "fit()"}),
                cls="absolute top-2 right-2 flex gap-1 z-10",
            )
        )

    return Div(
        *controls,
        # Loading
        Div(
            Span(cls="loading loading-spinner loading-sm"),
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
