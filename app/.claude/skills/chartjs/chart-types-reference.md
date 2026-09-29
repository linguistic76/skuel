# Chart.js Chart Types Reference

The chart types SKUEL emits, and the exact configs that emit them. Each config below
is copied from a live builder: a `VisualizationService` formatter, an `InsightStore`
method, or the lifepath radar route. Options not shown are Chart.js v4 defaults
(vendored build: v4.5.1).

## Overview

| Type | Emitted by | Drawn on |
|------|------------|----------|
| `line` | `format_completion_chart(chart_type="line")` | nothing yet (`/api/visualizations/completion`) |
| `bar` | `format_completion_chart(chart_type="bar")`, `format_distribution_chart(chart_type="bar")`, `InsightStore.get_domain_distribution_chart` | `/insights` (domain distribution) |
| horizontal `bar` | `format_streak_chart` | nothing yet (`/api/visualizations/streaks`) |
| `doughnut` | `format_distribution_chart` (default), `InsightStore.get_impact_distribution_chart`, `.get_type_distribution_chart` | `/insights` |
| half `doughnut` (gauge) | `InsightStore.get_action_rate_chart` | `/insights` |
| `pie` | `format_distribution_chart(chart_type="pie")` (the status distribution) | nothing yet |
| `radar` | `/api/lifepath/alignment/chart` route | `/lifepath/alignment` |

Every config is JSON, so **no option may be a function**. Chart.js accepts
`ticks.callback` and tooltip callbacks only from JavaScript, and `chartVis` passes the
fetched JSON straight to `new Chart`. Express everything as static values.

## Dataset Defaults (`ChartDataset`)

`VisualizationService` builds datasets from this dataclass, then serializes them with
`_chart_config_to_dict`, which writes all seven keys on every dataset:

```python
@dataclass
class ChartDataset:
    label: str
    data: list[float | int]
    backgroundColor: str | list[str] = "#3B82F6"  # noqa: N815 (Chart.js API)
    borderColor: str | list[str] = "#2563EB"  # noqa: N815 (Chart.js API)
    borderWidth: int = 2  # noqa: N815 (Chart.js API)
    fill: bool = False
    tension: float = 0.1  # Line smoothing
```

Those seven keys are exactly `ChartJsDataset`'s declared set. A hand-built literal may
omit any of them (`total=False`) but may not add one without declaring it first.

---

## Line: Completion Rate

`format_completion_chart(completed, total, labels)` turns parallel count lists into a
percent per period (`round(c / t * 100, 1)`, 0 when `t` is 0):

```python
{
    "type": "line",
    "data": {
        "labels": ["Mon", "Tue", "Wed"],
        "datasets": [{
            "label": "Completion Rate (%)",
            "data": [60.0, 75.0, 0],
            "backgroundColor": "transparent",
            "borderColor": SemanticColor.SUCCESS,
            "borderWidth": 2,
            "fill": True,
            "tension": 0.1,
        }],
    },
    "options": {
        "responsive": True,
        "maintainAspectRatio": False,
        "scales": {"y": {"beginAtZero": True, "max": 100,
                         "title": {"display": True, "text": "Completion %"}}},
        "plugins": {"legend": {"display": True, "position": "top"},
                    "title": {"display": True, "text": "Task Completion Rate"}},
    },
}
```

With `chart_type="bar"` the same formatter fills the bars with `SemanticColor.SUCCESS`
and sets `fill: False`. `VisualizationAggregationService.get_completion_chart_data`
supplies the counts: 7 daily points for `week`, 10 three-day buckets for `month`,
13 seven-day buckets for `quarter`.

`maintainAspectRatio: False` makes Chart.js take the chart's height from its parent.
The Chart.js responsive docs require that parent to be relatively positioned, sized,
and dedicated to the canvas. The insights card doesn't meet that, and its configs
leave the option at its default (`True`). Give the parent an explicit height before
you draw a formatter config in a card.

## Bar

### Distribution (`format_distribution_chart(chart_type="bar")`)

One dataset colored per bar from the `SemanticColor.ALL` cycle, with borders in the
same colors (`borderWidth: 2`) and the legend at the top.

### Insights by domain (`InsightStore.get_domain_distribution_chart`)

```python
{
    "type": "bar",
    "data": {
        "labels": ["Tasks", "Habits"],              # domain.title(), sorted by count desc
        "datasets": [{"label": "Active Insights", "data": [5, 2],
                      "backgroundColor": "rgba(59, 130, 246, 0.8)"}],
    },
    "options": {
        "responsive": True,
        "plugins": {"legend": {"display": False},
                    "title": {"display": True, "text": "Insights by Domain"}},
        "scales": {"y": {"beginAtZero": True, "ticks": {"stepSize": 1}}},
    },
}
```

`ticks.stepSize: 1` keeps an integer count axis from showing 0.5 steps. It is the
JSON-safe alternative to a tick `callback`.

## Horizontal Bar: Habit Streaks

`format_streak_chart([{"name", "current", "best"}, ...])`:

```python
{
    "type": "bar",
    "data": {
        "labels": ["Meditation", "Reading"],
        "datasets": [
            {"label": "Current Streak", "data": [14, 45],
             "backgroundColor": SemanticColor.SUCCESS, "borderColor": SemanticColor.SUCCESS, ...},
            {"label": "Best Streak", "data": [21, 45],
             "backgroundColor": SemanticColor.INFO, "borderColor": SemanticColor.INFO, ...},
        ],
    },
    "options": {
        "responsive": True,
        "maintainAspectRatio": False,
        "indexAxis": "y",  # horizontal bars
        "plugins": {"legend": {"display": True, "position": "top"},
                    "title": {"display": True, "text": "Habit Streaks"}},
    },
}
```

`VisualizationAggregationService.get_streak_chart_data` feeds it every active habit's
`current_streak` / `best_streak`, falling back to 0.

## Doughnut and Pie

### Distribution (`format_distribution_chart`, default `doughnut`)

```python
{
    "type": "doughnut",             # or "pie"
    "data": {
        "labels": ["active", "completed"],          # the dict's keys, in insertion order
        "datasets": [{
            "label": "Task Status Distribution",
            "data": [4.0, 9.0],                     # values cast to float
            "backgroundColor": [SemanticColor.PRIMARY, SemanticColor.SUCCESS],  # ALL, cycled
            "borderColor": "#ffffff",
            "borderWidth": 1,
            ...
        }],
    },
    "options": {
        "responsive": True,
        "maintainAspectRatio": False,
        "plugins": {"legend": {"display": True, "position": "right"},
                    "title": {"display": True, "text": "Task Status Distribution"}},
    },
}
```

The aggregation service labels slices with raw enum values (`priority.value`,
`status.value`), not display names.

### Insight doughnuts (`InsightStore`)

`get_impact_distribution_chart` has four fixed labels (Critical, High, Medium, Low,
which is the insight-impact scale, not `Priority`) and its legend at the bottom.
`get_type_distribution_chart` has one slice per insight type, sorted by count, with
its legend on the right. Both hard-code `rgba(..., 0.8)` fills.

### Half doughnut: gauge (`InsightStore.get_action_rate_chart`)

```python
{
    "type": "doughnut",
    "data": {
        "labels": ["Actioned", "Not Actioned"],
        "datasets": [{"label": "Action Rate", "data": [62.5, 37.5],
                      "backgroundColor": ["rgba(34, 197, 94, 0.8)", "rgba(156, 163, 175, 0.3)"]}],
    },
    "options": {
        "responsive": True,
        "circumference": 180,
        "rotation": -90,
        "plugins": {"legend": {"position": "bottom"},
                    "title": {"display": True, "text": "Action Rate: 62.5%"}},
    },
}
```

`circumference` and `rotation` are doughnut options, so they may sit under `options`
(as here, for every dataset) or on a single dataset.

## Radar: Life-Path Alignment

Built inline in `/api/lifepath/alignment/chart`. The route returns a `JSONResponse`
typed `-> Any`, which is why it can carry keys `ChartJsDataset` doesn't declare:

```python
{
    "type": "radar",
    "data": {
        "labels": ["Knowledge", "Activity", "Goals", "Principles", "Momentum"],
        "datasets": [{
            "label": "Your Alignment",
            "data": [0.8, 0.6, 0.7, 0.5, 0.4],       # dimension scores, 0.0–1.0
            "backgroundColor": "rgba(59, 130, 246, 0.2)",
            "borderColor": "rgba(59, 130, 246, 1)",
            "borderWidth": 2,
            "pointBackgroundColor": "rgba(59, 130, 246, 1)",
            "pointBorderColor": "#fff",
        }],
    },
    "options": {
        "scales": {"r": {"min": 0, "max": 1, "ticks": {"stepSize": 0.2}}},
        "plugins": {"legend": {"display": False}},
    },
}
```

Without a designation, or when the alignment read fails, the route returns the same
frame with zeros, so the radar still draws. A typed version would declare
`pointBackgroundColor` / `pointBorderColor` on `ChartJsDataset` and return
`Result[ChartJsConfig]`.

---

## JSON-Safe Options Reference

All of these are plain values, so they survive the JSON trip:

```python
options = {
    "responsive": True,
    "maintainAspectRatio": False,         # height from the parent — size the parent
    "indexAxis": "y",                     # horizontal bar
    "plugins": {
        "legend": {"display": True, "position": "top"},    # top | bottom | left | right
        "title": {"display": True, "text": "Chart Title"},
        "tooltip": {"enabled": True, "mode": "index"},
    },
    "scales": {
        "x": {"stacked": True, "title": {"display": True, "text": "X"}},
        "y": {"stacked": True, "beginAtZero": True, "max": 100,
              "ticks": {"stepSize": 1}},
        # radar: "r": {"min": 0, "max": 1, "ticks": {"stepSize": 0.2}}
    },
    "interaction": {"intersect": False, "mode": "index"},
    "animation": {"duration": 750},
    "cutout": "70%",                      # doughnut ring thickness
    "circumference": 180,                 # doughnut: half circle
    "rotation": -90,
}
```

`options` is `dict[str, Any]` on `ChartJsConfig`, so mypy doesn't check any of these
names. A misspelled option is ignored silently by Chart.js; check new ones against
https://www.chartjs.org/docs/latest/.

## Choosing a Type

| Data | Type | SKUEL precedent |
|------|------|-----------------|
| A rate per period | `line` (or `bar`) | `format_completion_chart` |
| Counts per category | `doughnut` / `pie`, or `bar` when the categories are many or ranked | `format_distribution_chart`, insights by domain |
| Two measures per item | horizontal `bar`, two datasets | `format_streak_chart` |
| One share of a whole | half `doughnut` | insight action rate |
| Several scores on one scale | `radar` | life-path alignment |

## Related Files

- [SKILL.md](SKILL.md): the live surface, wire contract and add-a-chart recipe
- [fasthtml-patterns.md](fasthtml-patterns.md): card, page and route patterns
- [QUICK_REFERENCE.md](QUICK_REFERENCE.md): snippets and pitfalls
- `/core/services/visualization_service.py`: the formatters
- `/core/services/insight/insight_store.py`: the insight configs
