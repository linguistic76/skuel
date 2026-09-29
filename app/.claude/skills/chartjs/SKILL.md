---
name: chartjs
description: Expert guide for Chart.js data visualization in SKUEL. Use when adding or changing a chart — the /insights analytics cards, the life-path alignment radar, the /api/visualizations endpoints — or when the user mentions Chart.js, charts, graphs, visualization, chartVis, ChartJsConfig, or analytics charts.
allowed-tools: Read, Grep, Glob
---

# Chart.js: Data Visualization for SKUEL

A SKUEL chart is three pieces: a service that builds a Chart.js config as a typed
`ChartJsConfig` literal, a JSON route that serves it, and a card whose `chartVis`
Alpine component fetches it and calls `new Chart(canvas, config)`. The server
decides everything the chart shows. The browser adds no chart logic of its own.

## The Live Surface

Every Chart.js chart SKUEL draws today:

| Page | Card | Endpoint | Config built by |
|------|------|----------|-----------------|
| `/insights` (charts section) | `_chart_card(url, type)` — `ui/insights/components.py` | `/api/insights/charts/{impact-distribution,domain-distribution,type-distribution,action-rate}` — `adapters/inbound/insights_api.py` | `InsightStore.get_*_chart` — hand-built `ChartJsConfig` literals |
| `/lifepath/alignment` | `_alignment_radar()` — `ui/lifepath/alignment.py` | `/api/lifepath/alignment/chart` — `adapters/inbound/lifepath_ui.py` | inline in the route (a `JSONResponse`, typed `-> Any`) |
| none | — | `/api/visualizations/{completion,priority-distribution,streaks,status-distribution}` — `adapters/inbound/visualization_api.py` | `VisualizationAggregationService` → `VisualizationService` formatters |

- The insights section renders only when the page's insight list holds at least 3
  insights (`render_charts_section`).
- The `/api/visualizations/*` Chart.js endpoints have **no UI consumer**; the
  module docstring says so. Their tests cover the routes' auth and user scoping
  (against a mocked service) and the formatters' output keys. Nothing exercises the
  Chart.js aggregation end to end.
- The admin dashboard draws **no** Chart.js. Its role distribution is a column of
  `Progress` bars (`AdminAnalyticsComponents.render_user_distribution`, `ui/admin/views.py`).
- Frappe Gantt (`/api/visualizations/gantt/*`) is a STAGED surface with no UI —
  see `docs/roadmap/gantt-visualization-surface.md`. This skill has no Gantt patterns.

## How a Chart Renders

```
page route ── BasePage/SidebarPage(extra_scripts=[chart.umd.js])
   └─ card: Div(x-data="chartVis(url, type)") ⊃ Canvas(x-ref="canvas") + loading + error
         └─ chartVis.init → SKUEL.getJson(url) → destroy old chart → new Chart(ctx, config)
                                   │
route ── @boundary_handler → Result[ChartJsConfig] → JSON body (the config itself, unwrapped)
```

**`chartVis(dataUrl, chartType)`** is registered in `static/js/skuel.js` (inside the
`alpine:init` listener). State: `chart`, `loading`, `error`. Methods: `loadChart(url,
type)`, `refresh(newUrl)`, `destroy()`.

- **The payload's `"type"` decides the chart.** `loadChart(url, type)` never reads
  `type`, so the second argument only documents intent. The live cards pass it anyway.
- **Errors surface in the card.** `SKUEL.getJson` rejects on any non-2xx status. The
  message comes from the error payload's `message` (the boundary's client-safe
  `user_message`), or `Request failed (<status>)`. A page that forgot to load
  Chart.js shows `Chart is not defined` in the same slot. No error is thrown to the page.
- **HTMX swaps need no wiring.** Alpine initializes a `chartVis` card that arrives in
  a swapped fragment. When the card's element leaves the DOM, Alpine calls the
  component's `destroy()`, which tears down the Chart.js instance. This was measured
  against the vendored Alpine 3.14.8 and htmx 1.9.10 in jsdom. The alignment radar
  relies on it: `/lifepath/alignment` is a shell, and the radar arrives in the
  HTMX-loaded `/lifepath/alignment/content` fragment.

### Loading Chart.js

The shell page must load the library itself:

```python
return BasePage(
    content,
    title="Insights | SKUEL",
    request=request,
    active_page="insights",
    extra_scripts=["/static/vendor/chart.js/chart.umd.js"],
)
```

`BasePage` and `SidebarPage` build their own `<head>` (`build_head`), so the
`chartjs_headers()` that `scripts/dev/bootstrap.py` passes to `fast_app(hdrs=...)`
never reach them. Those headers reach only a full-page response that FastHTML wraps
itself. An HTMX fragment carries no `<head>` at all, so a fragment cannot bring
Chart.js with it: load it on the shell. (Measured with a TestClient: `BasePage`
without `extra_scripts` serves zero `chart.umd.js` tags.)

The date-fns adapter (`chartjs-adapter-date-fns.3.min.js`) loads only through
`chartjs_headers()`. No live chart uses a time scale; a page that adds one must list
the adapter in `extra_scripts` too.

## The Wire Contract: `ChartJsConfig`

`core/ports/query_types.py` declares the payload as TypedDicts (`total=False`):

```python
class ChartJsDataset(TypedDict, total=False):
    label: str
    data: list[int] | list[float]
    backgroundColor: str | list[str]
    borderColor: str | list[str]
    borderWidth: int
    fill: bool
    tension: float


class ChartJsData(TypedDict, total=False):
    labels: list[str]
    datasets: list[ChartJsDataset]


class ChartJsConfig(TypedDict, total=False):
    type: str
    data: ChartJsData
    options: dict[str, Any]  # boundary: consumed by the Chart.js library
```

- **Construct the literal, never `cast()` a dict into it.** `chartVis` hands the
  payload to `new Chart` unmodified, so a renamed key breaks the chart and no Python
  test notices. A literal returned as `Result[ChartJsConfig]` is checked: mypy reports
  `typeddict-unknown-key` for a misspelled dataset key, measured through
  `Result.ok({...})`.
- **Dataset keys outside the declared set are mypy errors.** A radar's
  `pointBackgroundColor` is one. Declare the key on `ChartJsDataset` before you emit
  it. (The lifepath radar emits it today only because its route is untyped.)
- **`options` is free-form** (`dict[str, Any]`), so nothing checks option names.
  Check them against the Chart.js v4 docs.
- **JSON only.** The config crosses the wire as JSON, so function-valued options
  (tick `callback`s, tooltip formatters) cannot be expressed. Use static options
  (`ticks.stepSize`, `scales.y.max`) or leave the Chart.js default.
- `tests/unit/services/test_visualization_wire_shape.py` pins the formatter output
  keys; `_chart_config_to_dict` returns the literal for the same reason.

## Adding a Chart

### 1. Build the config in a service

If the shape is one `VisualizationService` already formats, reuse it (pure, sync,
no domain dependencies):

| Formatter | Chart | Input |
|-----------|-------|-------|
| `format_completion_chart(completed, total, labels, chart_type="line")` | line or bar, % per period | parallel count lists |
| `format_distribution_chart(data, title, chart_type="doughnut")` | pie, doughnut or bar | `{label: count}` |
| `format_streak_chart(streaks)` | horizontal bar, current vs best | `[{"name", "current", "best"}]` |

Each returns `Result[ChartJsConfig]`. `format_distribution_chart` and
`format_streak_chart` fail with `Errors.validation` on empty input.
`format_completion_chart` fails only when its three lists differ in length. Three empty
lists pass and produce a chart with no points.

Otherwise build the literal, as `InsightStore` does:

```python
from operator import itemgetter

from core.models.type_hints import UserUID
from core.ports.query_types import ChartJsConfig
from core.utils.palette import SemanticColor
from core.utils.result_simplified import Result


async def get_domain_distribution_chart(self, user_uid: UserUID) -> Result[ChartJsConfig]:
    result = await self.get_active_insights(user_uid=user_uid, limit=200)
    if result.is_error:
        return Result.fail(result)

    counts: dict[str, int] = {}
    for insight in result.value:
        counts[insight.domain] = counts.get(insight.domain, 0) + 1
    ranked = sorted(counts.items(), key=itemgetter(1), reverse=True)

    return Result.ok(
        {
            "type": "bar",
            "data": {
                "labels": [domain.title() for domain, _ in ranked],
                "datasets": [
                    {
                        "label": "Active Insights",
                        "data": [count for _, count in ranked],
                        "backgroundColor": SemanticColor.PRIMARY,
                    }
                ],
            },
            "options": {
                "responsive": True,
                "plugins": {"legend": {"display": False}},
                "scales": {"y": {"beginAtZero": True, "ticks": {"stepSize": 1}}},
            },
        }
    )
```

### 2. Serve it

```python
@rt("/api/insights/charts/domain-distribution")
@boundary_handler()
async def domain_distribution_chart(request: Request) -> Result[ChartJsConfig]:
    user_uid = require_authenticated_user(request)
    return await insight_store.get_domain_distribution_chart(user_uid)
```

`boundary_handler` serializes the config itself as the JSON body, and an error as the
client-safe error payload with its HTTP status. The user comes from the session,
**never a `user_uid` query parameter**. Every live chart route reads the
authenticated user and ignores a `?user_uid=`; `test_visualization_api_routes.py`
pins that for `/api/visualizations/completion`. A route that read the parameter
would let any user chart another user's data (an IDOR).

### 3. Render the card

```python
def _chart_card(data_url: str, chart_type: str) -> FT:
    """Chart card — canvas + loading/error states for the chartVis component."""
    return Div(
        Canvas(**{"x-ref": "canvas", "width": "400", "height": "300", "class": "max-w-full"}),
        Div(
            "Loading chart...",
            cls="text-center text-muted-foreground py-8",
            **{"x-show": "loading"},
        ),
        Div(
            Span("Error: ", cls="font-bold"),
            Span(**{"x-text": "error"}),
            cls="text-error text-center py-8",
            **{"x-show": "error"},
        ),
        **{
            "x-data": f"chartVis('{data_url}', '{chart_type}')",
            "class": "bg-background p-4 rounded-lg shadow-sm",
        },
    )
```

There is **no shared chart component**. `_chart_card` is page-local to insights, and
`_alignment_radar` is its twin with a fixed URL. Copy the shape into the page's
`ui/` module, or promote it to `ui/components/` if a second page needs the same card.
Then add `extra_scripts=["/static/vendor/chart.js/chart.umd.js"]` to the shell page.

### 4. Decide what "no data" looks like

No data looks different per builder, so decide which one your chart gets:

| Builder | With no data |
|---------|--------------|
| `format_distribution_chart`, `format_streak_chart` | `Errors.validation` → 400 → the card's error slot |
| `format_completion_chart` | a chart with no points (the lengths match) |
| `VisualizationAggregationService` priority, status, streak | `Errors.not_found` for "no active tasks/habits" → 404 → the error slot |
| `VisualizationAggregationService` completion | a line at 0%. It always passes 7, 10 or 13 periods |
| `InsightStore.get_*_chart`, the lifepath radar | no emptiness check: domain and type draw an empty chart, impact and the radar draw zeros, and action rate draws a full "Not Actioned" ring |

Insights settles it at the page: `render_charts_section` hides every card below 3
insights. A new chart should do the same, or deliberately accept the error slot.

## Colors

`core/utils/palette.py` holds the chart palette:

```python
from core.utils.palette import SemanticColor

SemanticColor.PRIMARY   # "#3B82F6"
SemanticColor.SUCCESS   # "#10B981"
SemanticColor.WARNING   # "#F59E0B"
SemanticColor.DANGER    # "#EF4444"
SemanticColor.INFO      # "#6366F1"
SemanticColor.NEUTRAL   # "#6B7280"
SemanticColor.ALL       # the six, for cycling (format_distribution_chart uses it)
```

For slices keyed by a domain enum, use the enum's own color: `Priority.get_color()`,
`EntityStatus.get_color()`. The `VisualizationService` formatters use `SemanticColor`;
the four `InsightStore` configs and the lifepath radar still hard-code `rgba(...)`
strings. New configs take the palette.

## Anti-Patterns

| Don't | Do |
|-------|----|
| `Script("new Chart(...)")` inline | a `chartVis` card fed by a JSON route |
| `fetch()` in an `x-init` | let `chartVis` fetch — it owns loading and error state |
| `?user_uid=` in a chart URL | read the user in the route with `require_authenticated_user` |
| `cast(ChartJsConfig, {...})` | return the literal so mypy checks its keys |
| a `callback` in `options` | a static option — the config is JSON |
| Chart.js loaded in a fragment | `extra_scripts` on the shell page |
| `x-on:htmx:before-swap="destroy()"` | nothing — Alpine calls `destroy()` on removal |

## Reference Files

- [QUICK_REFERENCE.md](QUICK_REFERENCE.md) — snippets, infrastructure table, pitfalls
- [chart-types-reference.md](chart-types-reference.md) — the configs SKUEL emits, per chart type
- [fasthtml-patterns.md](fasthtml-patterns.md) — card, page, and route patterns from the live code

## Related Skills

- **[ui-browser](../ui-browser/SKILL.md)** — the Alpine component registry `chartVis` belongs to
- **[ui-css](../ui-css/SKILL.md)** — card containers and semantic color tokens
- **[result-pattern](../result-pattern/SKILL.md)** — `Result[ChartJsConfig]` and `boundary_handler`

## Foundation

- **[ui-browser](../ui-browser/SKILL.md)** — `Alpine.data()` components

## See Also

- `/core/services/visualization_service.py` — `VisualizationService` (Chart.js + Frappe Gantt formatters)
- `/core/services/analytics/visualization_aggregation_service.py` — fetch + aggregate for `/api/visualizations/*`
- `/core/services/insight/insight_store.py` — the four insight chart configs
- Chart.js v4 docs: https://www.chartjs.org/docs/latest/ (vendored build: v4.5.1)
