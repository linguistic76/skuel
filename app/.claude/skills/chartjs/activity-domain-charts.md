# Activity Domain Charts

Specific Chart.js patterns for each of SKUEL's 6 activity domains.

## Overview

Each activity domain has unique metrics that benefit from different chart types:

| Domain | Primary Chart | Secondary Charts |
|--------|--------------|------------------|
| **Tasks** | Line (completion) | Doughnut (status), Bar (priority) |
| **Goals** | Line (progress) | Bar (milestones), Doughnut (status) |
| **Habits** | Horizontal Bar (streaks) | Doughnut (categories), Heatmap |
| **Events** | Bar (hours/week) | Pie (types), Line (attendance) |
| **Choices** | Doughnut (status) | Bar (by domain) |
| **Principles** | Radar (alignment) | Doughnut (strength) |

---

## Tasks Domain

### Key Metrics

- Completion rate (% completed vs total)
- Priority distribution (critical, high, medium, low)
- Status breakdown (completed, in progress, blocked, draft)
- Time tracking (estimated vs actual minutes)
- Overdue count

### Task Completion Rate (Line)

```python
from components.visualization_components import create_chart_view

def task_completion_chart(user_uid: str, period: str = "week"):
    """Task completion rate over time."""
    return create_chart_view(
        data_url=f"/api/visualizations/completion?user_uid={user_uid}&period={period}",
        chart_type="line",
        title="Task Completion Rate",
    )
```

**API Response Format:**
```json
{
    "type": "line",
    "data": {
        "labels": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "datasets": [{
            "label": "Completion Rate (%)",
            "data": [60, 75, 80, 72, 85, 90, 88],
            "borderColor": "#10B981",
            "fill": true
        }]
    }
}
```

### Priority Distribution (Doughnut)

```python
def priority_distribution_chart(user_uid: str):
    """Task priority breakdown."""
    return create_chart_view(
        data_url=f"/api/visualizations/priority-distribution?user_uid={user_uid}",
        chart_type="doughnut",
        title="Priority Distribution",
    )
```

**Colors (from VisualizationService):**
- Critical: `#EF4444` (red)
- High: `#F59E0B` (amber)
- Medium: `#3B82F6` (blue)
- Low: `#10B981` (green)

### Status Breakdown (Pie)

```python
def status_breakdown_chart(user_uid: str):
    """Task status distribution."""
    return create_chart_view(
        data_url=f"/api/visualizations/status-distribution?user_uid={user_uid}",
        chart_type="pie",
        title="Task Status",
    )
```

### Complete Tasks Dashboard

```python
def tasks_analytics_dashboard(user_uid: str):
    """Full tasks analytics page."""
    return Div(
        H1("Tasks Analytics", cls="text-2xl font-bold mb-6"),

        Div(
            # Completion trend (wide)
            Div(
                task_completion_chart(user_uid, "week"),
                cls="card bg-base-100 shadow-sm p-4 md:col-span-2",
            ),

            # Priority (small)
            Div(
                priority_distribution_chart(user_uid),
                cls="card bg-base-100 shadow-sm p-4",
            ),

            # Status (small)
            Div(
                status_breakdown_chart(user_uid),
                cls="card bg-base-100 shadow-sm p-4",
            ),

            cls="grid grid-cols-1 md:grid-cols-2 gap-4",
        ),
    )
```

---

## Goals Domain

### Key Metrics

- Progress percentage (0-100%)
- Milestone completion rate
- Goal status distribution
- Timeframe breakdown (daily, weekly, monthly, yearly)
- On-track vs at-risk count

### Goal Progress Trend (Line)

```python
def goal_progress_chart(user_uid: str, goal_uid: str | None = None):
    """Goal progress over time."""
    url = f"/api/goals/progress-trend?user_uid={user_uid}"
    if goal_uid:
        url += f"&goal_uid={goal_uid}"

    return create_chart_view(
        data_url=url,
        chart_type="line",
        title="Goal Progress",
    )
```

### Milestone Completion (Bar)

```python
def milestone_chart(goal_uid: str):
    """Milestone completion for a specific goal."""
    return Div(
        H3("Milestones"),
        Div(
            Canvas(**{"x-ref": "canvas"}),
            **{"x-data": f"chartVis('/api/goals/{goal_uid}/milestones', 'bar')"},
        ),
        Script(src="/static/vendor/chart.js/chart.umd.js"),
    )
```

### Goal Status Distribution (Doughnut)

```python
def goal_status_chart(user_uid: str):
    """Distribution of goal statuses."""
    # Custom endpoint needed - not in default visualization routes
    return create_chart_view(
        data_url=f"/api/goals/status-distribution?user_uid={user_uid}",
        chart_type="doughnut",
        title="Goal Status",
    )
```

---

## Habits Domain

### Key Metrics

- Current streak (days)
- Best streak (days)
- Completion rate (% of scheduled completions)
- Consistency score
- Category breakdown

### Streak Comparison (Horizontal Bar)

The signature chart for habits - comparing current vs best streaks:

```python
from components.visualization_components import create_streak_chart

def habit_streaks(user_uid: str):
    """Habit streak comparison chart."""
    return create_streak_chart(
        user_uid=user_uid,
        title="Habit Streaks",
    )
```

**API Response Format:**
```json
{
    "type": "bar",
    "data": {
        "labels": ["Meditation", "Exercise", "Reading", "Journaling"],
        "datasets": [
            {
                "label": "Current Streak",
                "data": [14, 7, 45, 3],
                "backgroundColor": "#10B981"
            },
            {
                "label": "Best Streak",
                "data": [21, 30, 45, 15],
                "backgroundColor": "#6366F1"
            }
        ]
    },
    "options": {
        "indexAxis": "y"
    }
}
```

### Consistency by Day (Heatmap-like)

Chart.js doesn't have native heatmaps, but you can simulate with a matrix:

```python
def habit_weekly_pattern(user_uid: str, habit_uid: str):
    """Weekly completion pattern."""
    # Use bar chart with days of week
    return create_chart_view(
        data_url=f"/api/habits/{habit_uid}/weekly-pattern?user_uid={user_uid}",
        chart_type="bar",
        title="Weekly Pattern",
    )
```

### Habit Category Breakdown (Doughnut)

```python
def habit_categories_chart(user_uid: str):
    """Habits by category."""
    return create_chart_view(
        data_url=f"/api/habits/category-distribution?user_uid={user_uid}",
        chart_type="doughnut",
        title="Habit Categories",
    )
```

### Complete Habits Dashboard

```python
def habits_analytics_dashboard(user_uid: str):
    """Full habits analytics page."""
    return Div(
        H1("Habits Analytics", cls="text-2xl font-bold mb-6"),

        Div(
            # Streaks (full width)
            Div(
                habit_streaks(user_uid),
                cls="card bg-base-100 shadow-sm p-4 col-span-full",
            ),

            # Categories (half)
            Div(
                habit_categories_chart(user_uid),
                cls="card bg-base-100 shadow-sm p-4",
            ),

            # Weekly pattern placeholder
            Div(
                P("Select a habit to see weekly pattern"),
                cls="card bg-base-100 shadow-sm p-4",
            ),

            cls="grid grid-cols-1 md:grid-cols-2 gap-4",
        ),
    )
```

---

## Events Domain

### Key Metrics

- Scheduled hours per week
- Event type distribution
- Recurring vs one-time ratio
- Attendance/completion

### Hours by Week (Bar)

```python
def event_hours_chart(user_uid: str):
    """Scheduled hours per week."""
    return create_chart_view(
        data_url=f"/api/events/hours-by-week?user_uid={user_uid}",
        chart_type="bar",
        title="Scheduled Hours",
    )
```

### Event Type Distribution (Pie)

```python
def event_types_chart(user_uid: str):
    """Event types breakdown."""
    return create_chart_view(
        data_url=f"/api/events/type-distribution?user_uid={user_uid}",
        chart_type="pie",
        title="Event Types",
    )
```

---

## Choices Domain

### Key Metrics

- Pending vs decided count
- Choices by domain
- Decision quality scores
- Time to decision

### Decision Status (Doughnut)

```python
def choice_status_chart(user_uid: str):
    """Pending vs decided choices."""
    return create_chart_view(
        data_url=f"/api/choices/status-distribution?user_uid={user_uid}",
        chart_type="doughnut",
        title="Decision Status",
    )
```

### Choices by Domain (Bar)

```python
def choices_by_domain_chart(user_uid: str):
    """Choices categorized by life domain."""
    return create_chart_view(
        data_url=f"/api/choices/by-domain?user_uid={user_uid}",
        chart_type="bar",
        title="Choices by Domain",
    )
```

---

## Principles Domain

### Key Metrics

- Alignment level (FLOURISHING, ALIGNED, EXPLORING, DRIFTING)
- Principle strength (core, strong, moderate, developing)
- Category distribution
- Alignment history

### Alignment Radar

Radar charts are ideal for showing principle alignment across categories:

```python
def principle_alignment_radar(user_uid: str):
    """Multi-dimensional principle alignment."""
    return Div(
        H3("Principle Alignment", cls="text-lg font-semibold mb-2"),
        Div(
            Canvas(**{"x-ref": "canvas"}, cls="w-full h-80"),
            **{"x-data": f"chartVis('/api/principles/alignment-radar?user_uid={user_uid}', 'radar')"},
        ),
        Script(src="/static/vendor/chart.js/chart.umd.js"),
    )
```

**Expected API Response:**
```json
{
    "type": "radar",
    "data": {
        "labels": ["Spiritual", "Ethical", "Personal", "Professional", "Health", "Creative"],
        "datasets": [{
            "label": "Alignment Score",
            "data": [85, 92, 78, 88, 70, 65],
            "backgroundColor": "rgba(59, 130, 246, 0.2)",
            "borderColor": "#3B82F6"
        }]
    },
    "options": {
        "scales": {
            "r": {
                "beginAtZero": true,
                "max": 100
            }
        }
    }
}
```

### Strength Distribution (Doughnut)

```python
def principle_strength_chart(user_uid: str):
    """Principle strength levels."""
    return create_chart_view(
        data_url=f"/api/principles/strength-distribution?user_uid={user_uid}",
        chart_type="doughnut",
        title="Principle Strength",
    )
```

---

## Cross-Domain Dashboard

Combining charts from multiple domains:

```python
def life_analytics_dashboard(user_uid: str):
    """Cross-domain life analytics."""
    return Div(
        H1("Life Analytics", cls="text-2xl font-bold mb-6"),

        # Row 1: Tasks + Goals
        Div(
            Div(
                task_completion_chart(user_uid, "week"),
                cls="card bg-base-100 shadow-sm p-4",
            ),
            Div(
                goal_progress_chart(user_uid),
                cls="card bg-base-100 shadow-sm p-4",
            ),
            cls="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4",
        ),

        # Row 2: Habits (full width)
        Div(
            habit_streaks(user_uid),
            cls="card bg-base-100 shadow-sm p-4 mb-4",
        ),

        # Row 3: Principles + Events
        Div(
            Div(
                principle_alignment_radar(user_uid),
                cls="card bg-base-100 shadow-sm p-4",
            ),
            Div(
                event_hours_chart(user_uid),
                cls="card bg-base-100 shadow-sm p-4",
            ),
            cls="grid grid-cols-1 md:grid-cols-2 gap-4",
        ),
    )
```

---

## Adding New Domain Charts

When creating charts for new metrics:

### 1. Add API Endpoint

```python
# In visualization_routes.py or domain-specific routes
@rt("/api/visualizations/{domain}/new-metric")
@boundary_handler()
async def get_new_metric(request: Request):
    user_uid = require_authenticated_user(request)

    # Get data from service
    result = await services.domain_service.get_metric_data(user_uid)

    if result.is_error:
        return JSONResponse({"error": result.error}, status_code=500)

    # Use VisualizationService to format
    chart_result = vis_service.format_distribution_chart(
        result.value,
        "Metric Title",
        "doughnut"
    )

    return JSONResponse(chart_result.value)
```

### 2. Create FastHTML Component

```python
def new_metric_chart(user_uid: str):
    """Description of what this chart shows."""
    return create_chart_view(
        data_url=f"/api/visualizations/domain/new-metric?user_uid={user_uid}",
        chart_type="doughnut",
        title="New Metric",
    )
```

### 3. Add to Dashboard

```python
def domain_dashboard(user_uid: str):
    return Div(
        # Existing charts...
        new_metric_chart(user_uid),
    )
```

---

## Related Files

- [SKILL.md](SKILL.md) - Main Chart.js guide
- [chart-types-reference.md](chart-types-reference.md) - Chart type catalog
- [fasthtml-patterns.md](fasthtml-patterns.md) - Python integration
- `/core/services/visualization_service.py` - Data transformation
