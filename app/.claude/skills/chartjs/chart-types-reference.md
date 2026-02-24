# Chart.js Chart Types Reference

Complete reference for Chart.js chart types as used in SKUEL's activity domain visualizations.

## Overview

Chart.js supports these chart types, each suited to different activity domain metrics:

| Type | Best For | SKUEL Usage |
|------|----------|-------------|
| **Line** | Trends over time | Completion rates, progress |
| **Bar** | Category comparison | Priority distribution, counts |
| **Horizontal Bar** | Ranked lists | Habit streaks |
| **Doughnut/Pie** | Part of whole | Status distribution |
| **Radar** | Multi-dimensional | Principle alignment |
| **Scatter** | Correlation | (Less common in SKUEL) |

---

## Line Charts

Best for showing trends over time.

### Use Cases

- Task completion rate over days/weeks/months
- Goal progress over time
- Habit consistency trends

### Configuration

```python
# VisualizationService.format_completion_chart()
config = {
    "type": "line",
    "data": {
        "labels": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "datasets": [{
            "label": "Completion Rate (%)",
            "data": [60, 75, 80, 72, 85, 90, 88],
            "borderColor": "#10B981",  # success green
            "backgroundColor": "transparent",
            "tension": 0.1,  # Slight curve
            "fill": True,
        }]
    },
    "options": {
        "responsive": True,
        "maintainAspectRatio": False,
        "scales": {
            "y": {
                "beginAtZero": True,
                "max": 100,
                "title": {"display": True, "text": "Completion %"}
            }
        },
        "plugins": {
            "legend": {"display": True, "position": "top"},
            "title": {"display": True, "text": "Task Completion Rate"}
        }
    }
}
```

### FastHTML Usage

```python
from ui.goals.visualization import create_chart_view

def completion_trend():
    return create_chart_view(
        data_url="/api/visualizations/completion?period=week",
        chart_type="line",
        title="Weekly Completion Rate",
    )
```

### Multi-Series Line (Trend Comparison)

```python
# VisualizationService.format_trend_chart()
config = {
    "type": "line",
    "data": {
        "labels": ["Week 1", "Week 2", "Week 3", "Week 4"],
        "datasets": [
            {
                "label": "Tasks",
                "data": [10, 15, 12, 18],
                "borderColor": "#3B82F6",
            },
            {
                "label": "Goals",
                "data": [5, 8, 10, 12],
                "borderColor": "#10B981",
            },
            {
                "label": "Habits",
                "data": [7, 7, 8, 9],
                "borderColor": "#F59E0B",
            }
        ]
    },
    "options": {
        "interaction": {"intersect": False, "mode": "index"},
    }
}
```

---

## Bar Charts

Best for comparing categories or discrete values.

### Vertical Bar (Default)

```python
config = {
    "type": "bar",
    "data": {
        "labels": ["Critical", "High", "Medium", "Low"],
        "datasets": [{
            "label": "Task Count",
            "data": [5, 12, 25, 8],
            "backgroundColor": ["#EF4444", "#F59E0B", "#3B82F6", "#10B981"],
            "borderColor": ["#EF4444", "#F59E0B", "#3B82F6", "#10B981"],
            "borderWidth": 2,
        }]
    },
    "options": {
        "responsive": True,
        "plugins": {
            "legend": {"display": False},
            "title": {"display": True, "text": "Tasks by Priority"}
        }
    }
}
```

### Horizontal Bar (Ranked Lists)

Used for habit streaks where comparison is the focus:

```python
# VisualizationService.format_streak_chart()
config = {
    "type": "bar",
    "data": {
        "labels": ["Meditation", "Exercise", "Reading", "Journaling"],
        "datasets": [
            {
                "label": "Current Streak",
                "data": [14, 7, 45, 3],
                "backgroundColor": "#10B981",
            },
            {
                "label": "Best Streak",
                "data": [21, 30, 45, 15],
                "backgroundColor": "#6366F1",
            }
        ]
    },
    "options": {
        "indexAxis": "y",  # Makes it horizontal
        "plugins": {
            "legend": {"display": True, "position": "top"},
            "title": {"display": True, "text": "Habit Streaks"}
        }
    }
}
```

### Stacked Bar

```python
config = {
    "type": "bar",
    "data": {
        "labels": ["Mon", "Tue", "Wed", "Thu", "Fri"],
        "datasets": [
            {"label": "Completed", "data": [5, 8, 6, 7, 9], "backgroundColor": "#10B981"},
            {"label": "In Progress", "data": [2, 1, 3, 2, 1], "backgroundColor": "#3B82F6"},
            {"label": "Blocked", "data": [1, 0, 1, 0, 0], "backgroundColor": "#EF4444"},
        ]
    },
    "options": {
        "scales": {
            "x": {"stacked": True},
            "y": {"stacked": True}
        }
    }
}
```

---

## Doughnut & Pie Charts

Best for showing parts of a whole.

### Doughnut (Recommended)

Doughnut charts are preferred over pie - easier to compare segments.

```python
# VisualizationService.format_distribution_chart()
config = {
    "type": "doughnut",
    "data": {
        "labels": ["Completed", "In Progress", "Draft", "Blocked"],
        "datasets": [{
            "data": [45, 20, 10, 5],
            "backgroundColor": ["#10B981", "#3B82F6", "#6B7280", "#EF4444"],
            "borderColor": "#ffffff",
            "borderWidth": 2,
        }]
    },
    "options": {
        "responsive": True,
        "plugins": {
            "legend": {"display": True, "position": "right"},
            "title": {"display": True, "text": "Task Status Distribution"}
        }
    }
}
```

### Pie

```python
config = {
    "type": "pie",
    "data": {
        "labels": ["Critical", "High", "Medium", "Low", "None"],
        "datasets": [{
            "data": [2, 5, 12, 8, 3],
            "backgroundColor": [
                "#EF4444", "#F59E0B", "#3B82F6", "#10B981", "#6B7280"
            ],
        }]
    }
}
```

### Half-Doughnut (Gauge-like)

```python
config = {
    "type": "doughnut",
    "data": {
        "labels": ["Progress", "Remaining"],
        "datasets": [{
            "data": [75, 25],  # 75% complete
            "backgroundColor": ["#10B981", "#E5E7EB"],
            "circumference": 180,  # Half circle
            "rotation": 270,       # Start from bottom
        }]
    },
    "options": {
        "cutout": "70%",  # Thinner ring
        "plugins": {
            "legend": {"display": False},
        }
    }
}
```

---

## Radar Charts

Best for multi-dimensional comparison (e.g., principle alignment across categories).

### Basic Radar

```python
config = {
    "type": "radar",
    "data": {
        "labels": ["Spiritual", "Ethical", "Personal", "Professional", "Health", "Creative"],
        "datasets": [{
            "label": "Principle Alignment",
            "data": [85, 92, 78, 88, 70, 65],
            "backgroundColor": "rgba(59, 130, 246, 0.2)",  # Transparent blue
            "borderColor": "#3B82F6",
            "pointBackgroundColor": "#3B82F6",
        }]
    },
    "options": {
        "scales": {
            "r": {
                "beginAtZero": True,
                "max": 100,
            }
        }
    }
}
```

### Multi-Dataset Radar (Comparison)

```python
config = {
    "type": "radar",
    "data": {
        "labels": ["Learning", "Doing", "Reflecting", "Growing", "Connecting"],
        "datasets": [
            {
                "label": "This Month",
                "data": [80, 75, 60, 70, 85],
                "backgroundColor": "rgba(59, 130, 246, 0.2)",
                "borderColor": "#3B82F6",
            },
            {
                "label": "Last Month",
                "data": [70, 80, 55, 65, 75],
                "backgroundColor": "rgba(16, 185, 129, 0.2)",
                "borderColor": "#10B981",
            }
        ]
    }
}
```

---

## Chart Options Reference

### Common Options

```python
options = {
    # Sizing
    "responsive": True,
    "maintainAspectRatio": False,

    # Plugins
    "plugins": {
        "legend": {
            "display": True,
            "position": "top",  # top, bottom, left, right
        },
        "title": {
            "display": True,
            "text": "Chart Title",
        },
        "tooltip": {
            "enabled": True,
            "mode": "index",  # Show all datasets at x position
        }
    },

    # Scales (for line/bar)
    "scales": {
        "x": {
            "title": {"display": True, "text": "X Axis"},
        },
        "y": {
            "beginAtZero": True,
            "max": 100,
            "title": {"display": True, "text": "Y Axis"},
        }
    },

    # Interaction
    "interaction": {
        "intersect": False,
        "mode": "index",
    },

    # Animation
    "animation": {
        "duration": 750,
    }
}
```

### Scale Options

```python
# Percentage scale
"y": {
    "beginAtZero": True,
    "max": 100,
    "ticks": {
        "callback": lambda value: f"{value}%"
    }
}

# Stacked
"x": {"stacked": True},
"y": {"stacked": True}

# Horizontal bar
"indexAxis": "y"
```

### Dataset Options

```python
dataset = {
    # Common
    "label": "Series Name",
    "data": [1, 2, 3, 4, 5],

    # Colors
    "backgroundColor": "#3B82F6",  # Fill color
    "borderColor": "#2563EB",      # Line/border color
    "borderWidth": 2,

    # Line specific
    "tension": 0.3,     # Curve smoothing (0 = straight)
    "fill": True,       # Fill area under line

    # Point styling
    "pointRadius": 4,
    "pointHoverRadius": 6,
    "pointBackgroundColor": "#3B82F6",

    # Bar specific
    "barThickness": 20,
    "maxBarThickness": 40,
}
```

---

## Activity Domain Mappings

### Tasks

| Metric | Chart Type | Config |
|--------|------------|--------|
| Completion rate | Line | `format_completion_chart()` |
| Priority distribution | Doughnut | `format_distribution_chart()` |
| Status breakdown | Pie | `format_distribution_chart()` |
| Daily counts | Bar | Custom |

### Goals

| Metric | Chart Type | Config |
|--------|------------|--------|
| Progress over time | Line | `format_trend_chart()` |
| Milestone completion | Bar | Custom |
| Goal status | Doughnut | `format_distribution_chart()` |

### Habits

| Metric | Chart Type | Config |
|--------|------------|--------|
| Streaks (current/best) | Horizontal Bar | `format_streak_chart()` |
| Consistency by day | Heatmap (custom) | Custom |
| Category breakdown | Doughnut | `format_distribution_chart()` |

### Events

| Metric | Chart Type | Config |
|--------|------------|--------|
| Hours by week | Bar | Custom |
| Type distribution | Pie | `format_distribution_chart()` |
| Attendance | Line | Custom |

### Choices

| Metric | Chart Type | Config |
|--------|------------|--------|
| Pending vs decided | Doughnut | `format_distribution_chart()` |
| By domain | Bar | Custom |
| Decision quality | Line | Custom |

### Principles

| Metric | Chart Type | Config |
|--------|------------|--------|
| Alignment by category | Radar | Custom |
| Strength distribution | Doughnut | `format_distribution_chart()` |
| Alignment trends | Line | `format_trend_chart()` |

---

## Related Files

- [SKILL.md](SKILL.md) - Main Chart.js guide
- [fasthtml-patterns.md](fasthtml-patterns.md) - Python integration
- [activity-domain-charts.md](activity-domain-charts.md) - Domain-specific examples
