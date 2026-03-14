"""
Visualization Components
========================

FastHTML components for rendering visualization containers.

These components:
- Load vendor libraries from /static/vendor/
- Set up Alpine.js data bindings
- Provide loading states and error handling
- Work with VisualizationService API endpoints

Usage:
    from ui.goals.visualization import (
        create_chart_view,
        create_timeline_view,
        create_gantt_view,
    )

    # In a route
    content = create_chart_view(
        data_url="/api/visualizations/completion",
        chart_type="line",
        title="Task Completion"
    )
"""

from fasthtml.common import H3, Canvas, Div, Link, P, Script, Span

from ui.buttons import Button, ButtonT
from ui.cards import Card
from ui.feedback import Loading, LoadingT
from ui.layout import Size

# =============================================================================
# Library Script Tags
# =============================================================================


def chart_js_scripts() -> list:
    """Return script tags for Chart.js (local vendor)."""
    return [
        Script(src="/static/vendor/chart.js/chart.umd.js"),
    ]


def visjs_scripts() -> list:
    """Return script and link tags for Vis.js Timeline (local vendor)."""
    return [
        Link(
            href="/static/vendor/vis-timeline/vis-timeline-graph2d.min.css",
            rel="stylesheet",
        ),
        Script(src="/static/vendor/vis-timeline/vis-timeline-graph2d.min.js"),
    ]


def gantt_scripts() -> list:
    """Return script and link tags for Frappe Gantt (local vendor)."""
    return [
        Link(
            href="/static/vendor/frappe-gantt/frappe-gantt.min.css",
            rel="stylesheet",
        ),
        Script(src="/static/vendor/frappe-gantt/frappe-gantt.min.js"),
    ]


# =============================================================================
# Chart.js Components
# =============================================================================


def create_chart_view(
    data_url: str,
    chart_type: str = "line",
    title: str | None = None,
    height: str = "h-64",
    width: str = "w-full",
    include_scripts: bool = True,
) -> Div:
    """
    Create a Chart.js visualization container.

    Args:
        data_url: API endpoint returning Chart.js config JSON
        chart_type: Chart type (line, bar, pie, doughnut, radar)
        title: Optional title above chart
        height: Tailwind height class
        width: Tailwind width class
        include_scripts: Whether to include script tags (set False if already loaded)

    Returns:
        FastHTML Div element with Chart.js container
    """
    content = []

    # Add scripts if requested
    if include_scripts:
        content.extend(chart_js_scripts())

    # Title
    if title:
        content.append(H3(title, cls="text-lg font-semibold mb-2"))

    # Chart container with Alpine.js binding
    content.append(
        Div(
            # Loading state
            Div(
                Loading(variant=LoadingT.spinner, size=Size.md),
                P("Loading chart...", cls="text-sm text-muted-foreground mt-2"),
                cls="flex flex-col items-center justify-center h-full",
                **{"x-show": "loading"},
            ),
            # Error state
            Div(
                P(
                    "Failed to load chart: ",
                    Span(**{"x-text": "error"}),
                    cls="text-error text-sm",
                ),
                cls="flex items-center justify-center h-full",
                **{"x-show": "error"},
            ),
            # Canvas for chart
            Canvas(
                **{"x-ref": "canvas"},
                cls=f"{width} {height}",
                **{"x-show": "!loading && !error"},
            ),
            cls=f"relative {height}",
            **{"x-data": f"chartVis('{data_url}', '{chart_type}')"},
        )
    )

    return Div(*content, cls="chart-container")


def create_completion_chart(
    user_uid: str,
    period: str = "week",
    title: str = "Task Completion Rate",
) -> Div:
    """
    Create a task completion rate chart.

    Args:
        user_uid: User UID for filtering
        period: Time period (day, week, month)
        title: Chart title

    Returns:
        Chart.js line chart component
    """
    data_url = f"/api/visualizations/completion?user_uid={user_uid}&period={period}"
    return create_chart_view(data_url, "line", title)


def create_distribution_chart(
    data_url: str,
    title: str = "Distribution",
    chart_type: str = "doughnut",
) -> Div:
    """
    Create a distribution chart (pie, doughnut, or bar).

    Args:
        data_url: API endpoint returning distribution data
        title: Chart title
        chart_type: pie, doughnut, or bar

    Returns:
        Chart.js chart component
    """
    return create_chart_view(data_url, chart_type, title)


def create_streak_chart(
    user_uid: str,
    title: str = "Habit Streaks",
) -> Div:
    """
    Create a habit streak horizontal bar chart.

    Args:
        user_uid: User UID for filtering
        title: Chart title

    Returns:
        Chart.js horizontal bar chart component
    """
    data_url = f"/api/visualizations/streaks?user_uid={user_uid}"
    return create_chart_view(data_url, "bar", title)


# =============================================================================
# Vis.js Timeline Components
# =============================================================================


def create_timeline_view(
    data_url: str,
    title: str | None = None,
    height: str = "h-96",
    include_scripts: bool = True,
    show_controls: bool = True,
) -> Div:
    """
    Create a Vis.js Timeline visualization container.

    Args:
        data_url: API endpoint returning Vis.js timeline JSON
        title: Optional title above timeline
        height: Tailwind height class
        include_scripts: Whether to include script tags
        show_controls: Whether to show zoom controls

    Returns:
        FastHTML Div element with timeline container
    """
    content = []

    # Add scripts if requested
    if include_scripts:
        content.extend(visjs_scripts())

    # Title and controls row
    header_content = []
    if title:
        header_content.append(H3(title, cls="text-lg font-semibold"))

    if show_controls:
        header_content.append(
            Div(
                Div(
                    "Zoom: ",
                    Button(
                        "+",
                        variant=ButtonT.secondary,
                        size=Size.sm,
                        **{"@click": "zoomIn()"},
                    ),
                    Button(
                        "-",
                        variant=ButtonT.secondary,
                        size=Size.sm,
                        **{"@click": "zoomOut()"},
                    ),
                    Button(
                        "Fit",
                        variant=ButtonT.secondary,
                        size=Size.sm,
                        **{"@click": "fit()"},
                    ),
                    cls="flex items-center gap-1 text-sm",
                ),
                cls="flex items-center gap-2",
            )
        )

    if header_content:
        content.append(Div(*header_content, cls="flex justify-between items-center mb-2"))

    # Timeline container with Alpine.js binding
    content.append(
        Div(
            # Loading state
            Div(
                Loading(variant=LoadingT.spinner, size=Size.md),
                P("Loading timeline...", cls="text-sm text-muted-foreground mt-2"),
                cls="flex flex-col items-center justify-center h-full",
                **{"x-show": "loading"},
            ),
            # Error state
            Div(
                P(
                    "Failed to load timeline: ",
                    Span(**{"x-text": "error"}),
                    cls="text-error text-sm",
                ),
                cls="flex items-center justify-center h-full",
                **{"x-show": "error"},
            ),
            # Timeline container
            Div(
                **{"x-ref": "container"},
                cls=f"w-full {height}",
                **{"x-show": "!loading && !error"},
            ),
            cls=f"relative {height} border rounded-lg",
            **{"x-data": f"timelineVis('{data_url}')"},
        )
    )

    return Div(*content, cls="timeline-container")


def create_calendar_timeline(
    user_uid: str,
    start_date: str | None = None,
    end_date: str | None = None,
    title: str = "Schedule Timeline",
) -> Div:
    """
    Create a calendar timeline from CalendarService data.

    Args:
        user_uid: User UID for filtering
        start_date: Start date (ISO format)
        end_date: End date (ISO format)
        title: Timeline title

    Returns:
        Vis.js timeline component
    """
    params = [f"user_uid={user_uid}"]
    if start_date:
        params.append(f"start_date={start_date}")
    if end_date:
        params.append(f"end_date={end_date}")

    data_url = f"/api/visualizations/timeline?{'&'.join(params)}"
    return create_timeline_view(data_url, title)


def create_tasks_timeline(
    user_uid: str,
    project: str | None = None,
    title: str = "Tasks Timeline",
) -> Div:
    """
    Create a tasks-only timeline.

    Args:
        user_uid: User UID for filtering
        project: Optional project filter
        title: Timeline title

    Returns:
        Vis.js timeline component
    """
    params = [f"user_uid={user_uid}"]
    if project:
        params.append(f"project={project}")

    data_url = f"/api/visualizations/tasks-timeline?{'&'.join(params)}"
    return create_timeline_view(data_url, title)


# =============================================================================
# Frappe Gantt Components
# =============================================================================


def create_gantt_view(
    data_url: str,
    title: str | None = None,
    height: str = "h-96",
    include_scripts: bool = True,
    show_view_modes: bool = True,
) -> Div:
    """
    Create a Frappe Gantt visualization container.

    Args:
        data_url: API endpoint returning Gantt JSON
        title: Optional title above chart
        height: Tailwind height class
        include_scripts: Whether to include script tags
        show_view_modes: Whether to show view mode selector

    Returns:
        FastHTML Div element with Gantt container
    """
    content = []

    # Add scripts if requested
    if include_scripts:
        content.extend(gantt_scripts())

    # Title and view mode selector row
    header_content = []
    if title:
        header_content.append(H3(title, cls="text-lg font-semibold"))

    if show_view_modes:
        header_content.append(
            Div(
                Span(
                    "Day",
                    cls="uk-btn uk-btn-sm",
                    **{":class": "viewMode === 'Day' ? 'uk-btn-primary' : 'uk-btn-default'"},
                    **{"@click": "setViewMode('Day')"},
                ),
                Span(
                    "Week",
                    cls="uk-btn uk-btn-sm",
                    **{":class": "viewMode === 'Week' ? 'uk-btn-primary' : 'uk-btn-default'"},
                    **{"@click": "setViewMode('Week')"},
                ),
                Span(
                    "Month",
                    cls="uk-btn uk-btn-sm",
                    **{":class": "viewMode === 'Month' ? 'uk-btn-primary' : 'uk-btn-default'"},
                    **{"@click": "setViewMode('Month')"},
                ),
                cls="flex items-center gap-1",
            )
        )

    if header_content:
        content.append(Div(*header_content, cls="flex justify-between items-center mb-2"))

    # Gantt container with Alpine.js binding
    content.append(
        Div(
            # Loading state
            Div(
                Loading(variant=LoadingT.spinner, size=Size.md),
                P("Loading Gantt chart...", cls="text-sm text-muted-foreground mt-2"),
                cls="flex flex-col items-center justify-center h-full",
                **{"x-show": "loading"},
            ),
            # Error state
            Div(
                P(
                    "Failed to load Gantt: ",
                    Span(**{"x-text": "error"}),
                    cls="text-error text-sm",
                ),
                cls="flex items-center justify-center h-full",
                **{"x-show": "error"},
            ),
            # Gantt container
            Div(
                **{"x-ref": "container"},
                cls=f"w-full {height} overflow-x-auto",
                **{"x-show": "!loading && !error"},
            ),
            cls=f"relative {height} border rounded-lg",
            **{"x-data": f"ganttVis('{data_url}')"},
        )
    )

    return Div(*content, cls="gantt-container")


def create_project_gantt(
    goal_uid: str,
    title: str = "Project Timeline",
) -> Div:
    """
    Create a Gantt chart for a goal with its tasks.

    Args:
        goal_uid: Goal UID
        title: Chart title

    Returns:
        Frappe Gantt component
    """
    data_url = f"/api/visualizations/gantt/goal/{goal_uid}"
    return create_gantt_view(data_url, title)


def create_tasks_gantt(
    user_uid: str,
    project: str | None = None,
    title: str = "Tasks Gantt",
) -> Div:
    """
    Create a Gantt chart for user tasks.

    Args:
        user_uid: User UID
        project: Optional project filter
        title: Chart title

    Returns:
        Frappe Gantt component
    """
    params = [f"user_uid={user_uid}"]
    if project:
        params.append(f"project={project}")

    data_url = f"/api/visualizations/gantt/tasks?{'&'.join(params)}"
    return create_gantt_view(data_url, title)


# =============================================================================
# Combined Dashboard Components
# =============================================================================


def create_visualization_dashboard(
    user_uid: str,
    include_charts: bool = True,
    include_timeline: bool = True,
    include_gantt: bool = False,
) -> Div:
    """
    Create a combined visualization dashboard.

    Args:
        user_uid: User UID
        include_charts: Whether to include Chart.js charts
        include_timeline: Whether to include timeline
        include_gantt: Whether to include Gantt

    Returns:
        Dashboard component with multiple visualizations
    """
    sections = []

    # Add library scripts once at the top
    scripts_added = {"chart": False, "timeline": False, "gantt": False}

    if include_charts:
        # Completion rate chart
        sections.append(
            Card(
                create_chart_view(
                    f"/api/visualizations/completion?user_uid={user_uid}&period=week",
                    "line",
                    "Weekly Completion Rate",
                    include_scripts=not scripts_added["chart"],
                ),
                cls="bg-background shadow-sm p-4",
            )
        )
        scripts_added["chart"] = True

        # Distribution chart
        sections.append(
            Card(
                create_chart_view(
                    f"/api/visualizations/priority-distribution?user_uid={user_uid}",
                    "doughnut",
                    "Task Priority Distribution",
                    include_scripts=False,  # Already loaded
                ),
                cls="bg-background shadow-sm p-4",
            )
        )

    if include_timeline:
        sections.append(
            Card(
                create_timeline_view(
                    f"/api/visualizations/timeline?user_uid={user_uid}",
                    "Schedule Overview",
                    include_scripts=not scripts_added["timeline"],
                ),
                cls="bg-background shadow-sm p-4 col-span-2",
            )
        )
        scripts_added["timeline"] = True

    if include_gantt:
        sections.append(
            Card(
                create_gantt_view(
                    f"/api/visualizations/gantt/tasks?user_uid={user_uid}",
                    "Task Dependencies",
                    include_scripts=not scripts_added["gantt"],
                ),
                cls="bg-background shadow-sm p-4 col-span-2",
            )
        )
        scripts_added["gantt"] = True

    return Div(
        *sections,
        cls="grid grid-cols-1 md:grid-cols-2 gap-4",
    )
