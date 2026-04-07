---
name: chartjs
description: Expert guide for Chart.js data visualization in SKUEL. Use when building analytics dashboards, activity domain charts (Tasks, Goals, Habits progress), completion rates, distribution charts, or when the user mentions Chart.js, graphs, charts, visualization, metrics, or analytics.
allowed-tools: Read, Grep, Glob
---

# Chart.js: Data Visualization for SKUEL

## Core Philosophy

> "Data becomes insight through visualization. Charts tell the story that numbers cannot."

In SKUEL, Chart.js visualizes the 6 activity domains (Tasks, Goals, Habits, Events, Choices, Principles) through a clean four-layer architecture:

| Layer | Responsibility | Component |
|-------|----------------|-----------|
| **Data** | Fetch domain metrics | Domain services (TasksService, etc.) |
| **Transform** | Format for Chart.js JSON | `VisualizationService` |
| **Render** | Alpine component loads chart | `chartVis()` in skuel.js |
| **Container** | FastHTML generates HTML | `create_chart_view()` |

**The Rule:** All chart rendering goes through Alpine.js components. No inline JavaScript.

## Quick Start

### Example 1: Task Completion Rate (Line Chart)

```python
from ui.goals.visualization import create_chart_view

def task_analytics_page():
    return Div(
        H2("Task Analytics"),
        create_chart_view(
            data_url="/api/visualizations/completion?period=week",
            chart_type="line",
            title="Weekly Completion Rate",
        ),
    )
```

### Example 2: Priority Distribution (Doughnut)

```python
from ui.goals.visualization import create_chart_view

def priority_breakdown():
    return create_chart_view(
        data_url="/api/visualizations/priority-distribution",
        chart_type="doughnut",
        title="Task Priority Distribution",
    )
```

### Example 3: Habit Streaks (Horizontal Bar)

```python
from ui.goals.visualization import create_chart_view

def habit_dashboard():
    return create_chart_view(
        data_url="/api/visualizations/streaks",
        chart_type="bar",
        title="Habit Streaks",
    )
```

## SKUEL Architecture

### Key Files

| File | Purpose |
|------|---------|
| `/static/js/skuel.js` | `chartVis()` Alpine component (lines 514-571) |
| `/core/services/visualization_service.py` | Data transformation to Chart.js JSON (canonical; `ui/visualization/` re-exports) |
| `/ui/goals/visualization.py` | FastHTML component wrappers |
| `/adapters/inbound/visualization_routes.py` | API endpoints returning Chart.js configs |
| `/static/vendor/chart.js/` | Chart.js library (local vendor) |

### The chartVis() Alpine Component

Defined in `skuel.js`, this component:
1. Fetches chart config from API
2. Creates Chart.js instance
3. Handles loading/error states
4. Supports refresh and destroy

```javascript
Alpine.data('chartVis', function(dataUrl, chartType) {
    return {
        chart: null,
        loading: true,
        error: null,

        init: function() {
            this.loadChart(dataUrl, chartType || 'line');
        },

        loadChart: function(url, type) { /* ... */ },
        refresh: function(newUrl) { /* ... */ },
        destroy: function() { /* ... */ }
    };
});
```

**Usage in HTML:**
```html
<div x-data="chartVis('/api/visualizations/completion', 'line')">
    <canvas x-ref="canvas"></canvas>
</div>
```

### VisualizationService Methods

| Method | Returns | Use Case |
|--------|---------|----------|
| `format_completion_chart()` | Line/bar config | Completion rates over time |
| `format_distribution_chart()` | Pie/doughnut/bar config | Category distributions |
| `format_trend_chart()` | Multi-series line config | Trend comparisons |
| `format_streak_chart()` | Horizontal bar config | Habit streaks |

### API Endpoints

| Endpoint | Chart Type | Data |
|----------|------------|------|
| `/api/visualizations/completion` | Line | Task completion rate |
| `/api/visualizations/priority-distribution` | Doughnut | Priority breakdown |
| `/api/visualizations/status-distribution` | Pie | Status breakdown |
| `/api/visualizations/streaks` | Horizontal bar | Habit streaks |

## Chart Type Selection

### For Activity Domains

| Domain | Recommended Charts | Why |
|--------|-------------------|-----|
| **Tasks** | Line (trends), Doughnut (status), Bar (priority) | Show progress over time, current state |
| **Goals** | Line (progress), Bar (milestones), Gauge (current) | Track advancement toward targets |
| **Habits** | Horizontal bar (streaks), Heatmap (consistency) | Compare habits, show patterns |
| **Events** | Bar (hours/week), Pie (type distribution) | Time allocation insights |
| **Choices** | Pie (pending vs decided), Bar (by domain) | Decision status overview |
| **Principles** | Radar (alignment), Doughnut (strength) | Multi-dimensional comparison |

### By Data Type

| Data Type | Chart Type | Example |
|-----------|------------|---------|
| Time series | Line | Completion rate over weeks |
| Categories | Doughnut/Pie | Priority distribution |
| Comparison | Bar | Streak current vs best |
| Multi-dimensional | Radar | Principle alignment |
| Progress | Gauge (via plugins) | Goal progress % |

## Color Schemes

SKUEL centralizes all visualization colors in `core/utils/palette.py` (importable as either `from core.utils.palette import SemanticColor` or `from ui.palette import SemanticColor`):

```python
from core.utils.palette import SemanticColor

# Semantic chart colors (for color cycling, datasets)
SemanticColor.PRIMARY   # "#3B82F6" (Blue)
SemanticColor.SUCCESS   # "#10B981" (Green)
SemanticColor.WARNING   # "#F59E0B" (Amber)
SemanticColor.DANGER    # "#EF4444" (Red)
SemanticColor.INFO      # "#6366F1" (Indigo)
SemanticColor.NEUTRAL   # "#6B7280" (Gray)
SemanticColor.ALL       # List of all 6 for color cycling
```

For Priority and Status colors, use the enum methods directly:

```python
from core.models.enums import Priority, EntityStatus

Priority.CRITICAL.get_color()      # "#DC2626"
EntityStatus.COMPLETED.get_color() # "#10B981"
```

## FastHTML Integration Pattern

### Basic Chart Container

```python
from ui.goals.visualization import create_chart_view

# Simple usage
chart = create_chart_view(
    data_url="/api/visualizations/completion",
    chart_type="line",
    title="Completion Rate",
    height="h-64",
    width="w-full",
    include_scripts=True,  # Include Chart.js script tag
)
```

### Custom Chart with Options

```python
from fasthtml.common import Div, Canvas, H3, Script

def custom_chart(data_url: str, options: dict):
    """Custom chart with specific options."""
    return Div(
        H3("Custom Chart", cls="text-lg font-semibold mb-2"),
        Div(
            Canvas(**{"x-ref": "canvas"}, cls="w-full h-64"),
            **{"x-data": f"chartVis('{data_url}', 'bar')"},
        ),
        Script(src="/static/vendor/chart.js/chart.umd.js"),
    )
```

### Dashboard with Multiple Charts

```python
from ui.goals.visualization import (
    create_chart_view,
    create_visualization_dashboard,
)

def analytics_dashboard(user_uid: UserUID):
    """Complete analytics dashboard."""
    return create_visualization_dashboard(
        user_uid=user_uid,
        include_charts=True,
        include_timeline=True,
        include_gantt=False,
    )
```

## Best Practices

### 1. Use Existing Components

```python
# GOOD: Use existing components
from ui.goals.visualization import create_chart_view
chart = create_chart_view(data_url, chart_type, title)

# AVOID: Rebuilding from scratch
Div(Canvas(), Script("new Chart(...)"))
```

### 2. Load Scripts Once

```python
# GOOD: Include scripts only on first chart
create_chart_view(url1, "line", include_scripts=True)
create_chart_view(url2, "bar", include_scripts=False)  # Already loaded

# AVOID: Including scripts multiple times
```

### 3. Use Alpine Component for State

```python
# GOOD: Alpine handles loading/error
Div(
    Span("Loading...", **{"x-show": "loading"}),
    Canvas(**{"x-show": "!loading && !error"}),
    **{"x-data": "chartVis('/api/...')"},
)

# AVOID: Manual state management
```

### 4. Responsive Sizing

```python
# GOOD: Use Tailwind responsive classes
Canvas(cls="w-full h-64 md:h-96")

# GOOD: Use maintainAspectRatio option
options = {"responsive": True, "maintainAspectRatio": False}
```

### 5. Consistent Colors

```python
# GOOD: Use centralized palette colors
from core.utils.palette import SemanticColor
colors = SemanticColor.ALL

# AVOID: Hardcoding colors
backgroundColor = "#ff0000"  # Use SemanticColor.DANGER instead
```

## Anti-Patterns

### 1. Don't Create Charts Inline

```html
<!-- WRONG: Inline JavaScript -->
<script>
    new Chart(ctx, { type: 'line', data: {...} });
</script>

<!-- RIGHT: Use Alpine component -->
<div x-data="chartVis('/api/visualizations/completion', 'line')">
    <canvas x-ref="canvas"></canvas>
</div>
```

### 2. Don't Fetch Data in Alpine

```python
# WRONG: Fetching in Alpine x-init
Div(**{"x-data": "{}", "x-init": "fetch('/api/data').then(...)"})

# RIGHT: Let chartVis() handle fetching
Div(**{"x-data": "chartVis('/api/visualizations/completion')"})
```

### 3. Don't Skip Loading States

```python
# WRONG: No loading state
Canvas(**{"x-ref": "canvas"})

# RIGHT: Include loading/error states
Div(
    Span("Loading...", **{"x-show": "loading"}),
    Span(**{"x-show": "error", "x-text": "error"}),
    Canvas(**{"x-show": "!loading && !error"}),
)
```

## Related Visualization Components

SKUEL also includes:

| Component | Purpose | Alpine Component |
|-----------|---------|-----------------|
| Vis.js Timeline | Interactive timeline | `timelineVis()` |
| Frappe Gantt | Project planning | `ganttVis()` |

**See:** Timeline and Gantt patterns in this skill's reference docs.

## Additional Resources

- [chart-types-reference.md](chart-types-reference.md) - Complete chart type catalog
- [fasthtml-patterns.md](fasthtml-patterns.md) - Python/FastHTML integration
- [activity-domain-charts.md](activity-domain-charts.md) - Domain-specific patterns

## Related Skills

- **[js-alpine](../js-alpine/SKILL.md)** - `chartVis()` Alpine component for chart state management
- **[monsterui](../monsterui/SKILL.md)** - Card containers for chart dashboards
- **[daisyui](../ui-css/SKILL.md)** - Loading spinners, error states

## Foundation

- **[js-alpine](../js-alpine/SKILL.md)** - Understanding Alpine.data() components

## See Also

- `/core/services/visualization_service.py` - VisualizationService source (canonical)
- Chart.js Docs: https://www.chartjs.org/docs/
