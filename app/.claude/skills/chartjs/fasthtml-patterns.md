# Chart.js + FastHTML Integration Patterns

This guide shows how to integrate Chart.js with FastHTML in SKUEL.

## Core Principle

> All charting uses `create_chart_view()` and the `chartVis()` Alpine component.

Python generates the HTML structure, Alpine handles loading/rendering, and the VisualizationService API returns Chart.js configurations.

## Basic Integration

### Pattern 1: Using Built-in Components

The simplest approach - use existing components from `visualization_components.py`:

```python
from ui.goals.visualization import create_chart_view

def analytics_page():
    return Div(
        H2("Analytics Dashboard"),
        create_chart_view(
            data_url="/api/visualizations/completion",
            chart_type="line",
            title="Task Completion Rate",
        ),
    )
```

**What `create_chart_view()` generates:**

```html
<div class="chart-container">
    <script src="/static/vendor/chart.js/chart.umd.js"></script>
    <h3 class="text-lg font-semibold mb-2">Task Completion Rate</h3>
    <div class="relative h-64" x-data="chartVis('/api/visualizations/completion', 'line')">
        <!-- Loading state -->
        <div x-show="loading" class="flex flex-col items-center justify-center h-full">
            <span class="uk-spinner"></span>
            <p class="text-sm text-base-content/70 mt-2">Loading chart...</p>
        </div>
        <!-- Error state -->
        <div x-show="error" class="flex items-center justify-center h-full">
            <p class="text-error text-sm">Failed to load chart: <span x-text="error"></span></p>
        </div>
        <!-- Canvas -->
        <canvas x-ref="canvas" class="w-full h-64" x-show="!loading && !error"></canvas>
    </div>
</div>
```

### Pattern 2: Multiple Charts (Scripts Once)

When rendering multiple charts, include scripts only once:

```python
from ui.goals.visualization import create_chart_view

def multi_chart_page():
    return Div(
        H2("Multi-Chart Dashboard"),

        # First chart - includes scripts
        create_chart_view(
            data_url="/api/visualizations/completion",
            chart_type="line",
            title="Completion Rate",
            include_scripts=True,  # Default
        ),

        # Subsequent charts - scripts already loaded
        create_chart_view(
            data_url="/api/visualizations/priority-distribution",
            chart_type="doughnut",
            title="Priority Distribution",
            include_scripts=False,  # Don't duplicate scripts
        ),

        create_chart_view(
            data_url="/api/visualizations/streaks",
            chart_type="bar",
            title="Habit Streaks",
            include_scripts=False,
        ),
    )
```

### Pattern 3: Chart Grid Layout

Using Tailwind grid for responsive chart layouts:

```python
from ui.goals.visualization import create_chart_view

def chart_grid():
    return Div(
        Div(
            create_chart_view(
                "/api/visualizations/completion",
                "line",
                "Completion",
                include_scripts=True,
            ),
            cls="card bg-base-100 shadow-sm p-4",
        ),
        Div(
            create_chart_view(
                "/api/visualizations/priority-distribution",
                "doughnut",
                "Priorities",
                include_scripts=False,
            ),
            cls="card bg-base-100 shadow-sm p-4",
        ),
        Div(
            create_chart_view(
                "/api/visualizations/streaks",
                "bar",
                "Streaks",
                include_scripts=False,
            ),
            cls="card bg-base-100 shadow-sm p-4 md:col-span-2",  # Wide on desktop
        ),
        cls="grid grid-cols-1 md:grid-cols-2 gap-4",
    )
```

## Component Customization

### Custom Height and Width

```python
create_chart_view(
    data_url="/api/visualizations/completion",
    chart_type="line",
    title="Tall Chart",
    height="h-96",   # Tailwind height class
    width="w-full",  # Tailwind width class
)
```

### Without Title

```python
create_chart_view(
    data_url="/api/visualizations/completion",
    chart_type="line",
    title=None,  # No title rendered
)
```

## Manual Chart Construction

When you need more control, build the structure manually:

```python
from fasthtml.common import Div, Canvas, H3, P, Span, Script

def custom_chart(data_url: str, chart_type: str = "line") -> Div:
    """Custom chart with manual structure."""
    return Div(
        # Scripts
        Script(src="/static/vendor/chart.js/chart.umd.js"),

        # Title
        H3("Custom Chart Title", cls="text-lg font-semibold mb-2"),

        # Chart container with Alpine binding
        Div(
            # Loading state
            Div(
                Loading(variant=LoadingT.spinner, size=Size.md),
                P("Loading...", cls="text-sm mt-2"),
                cls="flex flex-col items-center justify-center h-full",
                **{"x-show": "loading"},
            ),

            # Error state
            Div(
                P("Error: ", Span(**{"x-text": "error"}), cls="text-error"),
                cls="flex items-center justify-center h-full",
                **{"x-show": "error"},
            ),

            # Canvas
            Canvas(
                cls="w-full h-64",
                **{"x-ref": "canvas", "x-show": "!loading && !error"},
            ),

            cls="relative h-64",
            **{"x-data": f"chartVis('{data_url}', '{chart_type}')"},
        ),
    )
```

## Dynamic Charts with HTMX

### Refresh Chart on Filter Change

```python
def filterable_chart():
    return Div(
        # Filter controls
        Div(
            Select(
                Option("Week", value="week"),
                Option("Month", value="month"),
                Option("Quarter", value="quarter"),
                name="period",
                cls="uk-select",
                hx_get="/partials/completion-chart",
                hx_trigger="change",
                hx_target="#chart-container",
            ),
            cls="mb-4",
        ),

        # Chart container (replaced by HTMX)
        Div(
            create_chart_view(
                "/api/visualizations/completion?period=week",
                "line",
                "Completion Rate",
            ),
            id="chart-container",
        ),
    )


# Partial route for HTMX
@rt("/partials/completion-chart")
async def completion_chart_partial(request):
    period = request.query_params.get("period", "week")
    return create_chart_view(
        f"/api/visualizations/completion?period={period}",
        "line",
        "Completion Rate",
        include_scripts=False,  # Already loaded
    )
```

### Chart in Modal

```python
def chart_modal_trigger():
    return Div(
        Button(
            "View Analytics",
            variant=ButtonT.primary,
            hx_get="/partials/analytics-modal",
            hx_target="#modal-content",
            **{"@click": "open = true"},
        ),

        # Modal (using Alpine for open/close)
        Div(
            Div(
                H2("Analytics", cls="text-xl font-bold mb-4"),
                Div(id="modal-content"),
                Button("Close", cls="btn mt-4", **{"@click": "open = false"}),
                cls="bg-white rounded-lg p-6 max-w-2xl w-full",
                **{"@click.stop": ""},
            ),
            cls="fixed inset-0 bg-black/50 flex items-center justify-center",
            **{"x-show": "open", "x-transition": "", "@click": "open = false"},
        ),

        **{"x-data": "{ open: false }"},
    )
```

## User-Specific Charts

### Passing User UID

```python
from adapters.inbound.auth import require_authenticated_user

@rt("/dashboard")
async def dashboard(request):
    user_uid = require_authenticated_user(request)

    return Div(
        H1("Your Dashboard"),
        create_chart_view(
            f"/api/visualizations/completion?user_uid={user_uid}",
            "line",
            "Your Completion Rate",
        ),
        create_chart_view(
            f"/api/visualizations/streaks?user_uid={user_uid}",
            "bar",
            "Your Habit Streaks",
            include_scripts=False,
        ),
    )
```

### Using Built-in User Components

```python
from ui.goals.visualization import (
    create_completion_chart,
    create_streak_chart,
)

@rt("/habits/analytics")
async def habits_analytics(request):
    user_uid = require_authenticated_user(request)

    return Div(
        H1("Habit Analytics"),
        create_streak_chart(user_uid, "Your Streaks"),
        create_completion_chart(user_uid, "week", "Weekly Progress"),
    )
```

## Dashboard Pattern

Full dashboard with multiple visualization types:

```python
from ui.goals.visualization import create_visualization_dashboard

@rt("/analytics")
async def full_analytics(request):
    user_uid = require_authenticated_user(request)

    return Div(
        H1("Analytics Dashboard", cls="text-2xl font-bold mb-6"),

        # Pre-built dashboard component
        create_visualization_dashboard(
            user_uid=user_uid,
            include_charts=True,
            include_timeline=True,
            include_gantt=False,
        ),
    )
```

## Error Handling

The `chartVis()` component handles errors automatically:

```python
# Error appears when API fails
create_chart_view(
    "/api/visualizations/invalid",  # Returns 404/500
    "line",
)
# Alpine shows: "Failed to load chart: Failed to load chart data: 404"
```

### Custom Error Handling

```python
def chart_with_fallback(data_url: str):
    return Div(
        Div(
            # Normal chart content
            Canvas(**{"x-ref": "canvas", "x-show": "!loading && !error"}),

            # Custom error with retry button
            Div(
                P("Chart failed to load", cls="text-error mb-2"),
                Button(
                    "Retry",
                    variant=ButtonT.default, size=Size.sm,
                    **{"@click": f"refresh()"},
                ),
                cls="flex flex-col items-center justify-center h-full",
                **{"x-show": "error"},
            ),

            **{"x-data": f"chartVis('{data_url}', 'line')"},
        ),
    )
```

## Performance Tips

### 1. Lazy Load Charts

Only load charts when visible:

```python
def lazy_chart():
    return Div(
        id="chart-section",
        hx_get="/partials/chart",
        hx_trigger="revealed",  # Load when scrolled into view
        hx_swap="innerHTML",
    )
```

### 2. Cache Chart Data

Use appropriate cache headers in API routes:

```python
@rt("/api/visualizations/completion")
async def get_completion(request):
    # ... generate data ...
    response = JSONResponse(chart_config)
    response.headers["Cache-Control"] = "private, max-age=60"  # 1 minute
    return response
```

### 3. Destroy Charts on Removal

If dynamically removing charts, destroy them first:

```python
Div(
    Canvas(**{"x-ref": "canvas"}),
    **{
        "x-data": "chartVis('/api/...')",
        "x-on:htmx:before-swap": "destroy()",  # Clean up before HTMX replaces
    },
)
```

## Related Files

- [SKILL.md](SKILL.md) - Main Chart.js guide
- [chart-types-reference.md](chart-types-reference.md) - Chart type catalog
- [activity-domain-charts.md](activity-domain-charts.md) - Domain-specific patterns
- `/ui/goals/visualization.py` - Source code for components
