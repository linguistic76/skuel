# Chartjs - Quick Reference

> **Fast lookup** for common syntax, methods, and operations

---

## Canonical Snippets

### Chart card — the shape every live chart uses

```python
def _chart_card(data_url: str, chart_type: str) -> Div:
    return Div(
        Canvas(**{"x-ref": "canvas", "width": "400", "height": "300", "class": "max-w-full"}),
        Div("Loading chart...", cls="text-center text-muted-foreground py-8", **{"x-show": "loading"}),
        Div(Span("Error: ", cls="font-bold"), Span(**{"x-text": "error"}),
            cls="text-error text-center py-8", **{"x-show": "error"}),
        **{"x-data": f"chartVis('{data_url}', '{chart_type}')",
           "class": "bg-background p-4 rounded-lg shadow-sm"},
    )
```

**When to use**: Every chart. `chartVis(dataUrl, chartType)` (the Alpine component in `static/js/skuel.js`) fetches the JSON config and renders into `x-ref="canvas"`. Never write an inline `new Chart(...)` script. Live copies: `ui/insights/components.py::_chart_card`, `ui/lifepath/alignment.py::_alignment_radar`. Both are page-local; there is no shared chart component.

### Loading Chart.js on a page

```python
return BasePage(
    content, title="Insights | SKUEL", request=request, active_page="insights",
    extra_scripts=["/static/vendor/chart.js/chart.umd.js"],
)
```

**When to use**: Every chart page, on the **shell**. `BasePage`/`SidebarPage` build their own `<head>` via `build_head()`, so the fast_app-level `chartjs_headers()` never reach them. An HTMX fragment has no `<head>` at all, so it cannot bring the script with it. Leave out `extra_scripts` and the card shows `Chart is not defined` in its error slot. Time-scale charts also need `/static/vendor/chart.js/chartjs-adapter-date-fns.3.min.js`.

### Route serving a Chart.js config

```python
@rt("/api/visualizations/completion")
@boundary_handler()
async def get_completion_chart(request: Request) -> Result[ChartJsConfig]:
    user_uid = require_authenticated_user(request)
    period = request.query_params.get("period", "week")
    return await vis_service.get_completion_chart_data(user_uid=user_uid, period=period)
```

**When to use**: New chart-data endpoints. `boundary_handler()` serializes the config itself as the JSON body, and `chartVis` passes it straight to `new Chart(ctx, config)`. The user always comes from the session, never from a query parameter. `/api/lifepath/alignment/chart` returns a hand-built `JSONResponse` typed `-> Any`; don't copy that shape.

### Formatting data → config (`VisualizationService`)

```python
service.format_completion_chart(completed=[3, 5], total=[5, 7], labels=["Mon", "Tue"])  # line|bar, % rate
service.format_distribution_chart({"high": 4, "low": 9}, title="Priority")             # pie|doughnut|bar
service.format_streak_chart([{"name": "Run", "current": 3, "best": 12}])               # horizontal bar
```

**When to use**: Standard chart shapes. These are pure sync formatters in `core/services/visualization_service.py`; callers supply pre-fetched data. Fetching and aggregation for `/api/visualizations/*` live in `VisualizationAggregationService` (`core/services/analytics/visualization_aggregation_service.py`). Every formatter returns `Result[ChartJsConfig]`. The distribution and streak formatters fail with `Errors.validation` on empty input. The completion formatter fails only on length-mismatched lists, so empty lists give an empty chart.

### Hand-built config (the `InsightStore` shape)

```python
return Result.ok(
    {
        "type": "doughnut",
        "data": {
            "labels": ["Actioned", "Not Actioned"],
            "datasets": [{"label": "Action Rate", "data": [rate, 100 - rate],
                          "backgroundColor": [SemanticColor.SUCCESS, SemanticColor.NEUTRAL]}],
        },
        "options": {"responsive": True, "circumference": 180, "rotation": -90},
    }
)
```

**When to use**: A shape no formatter covers. Return the literal as `Result[ChartJsConfig]`: mypy then flags any dataset key `ChartJsDataset` doesn't declare (`typeddict-unknown-key`, measured). `options` is `dict[str, Any]`, so option names go unchecked.

---

## Key Infrastructure

| Piece | Location | Notes |
|-------|----------|-------|
| Vendored Chart.js **v4.5.1** | `static/vendor/chart.js/chart.umd.js` | UMD global `Chart` |
| Date adapter (time scales) | `static/vendor/chart.js/chartjs-adapter-date-fns.3.min.js` | Loaded only by `chartjs_headers()`; no live chart uses it |
| `chartjs_headers()` | `ui/theme.py` | fast_app `hdrs=` in `scripts/dev/bootstrap.py`; never reaches a BasePage page |
| `chartVis` Alpine component | `static/js/skuel.js` (`Alpine.data('chartVis', …)`) | `SKUEL.getJson` → destroy old → `new Chart`; `refresh(newUrl)`, `destroy()` |
| `ChartJsConfig` / `ChartJsData` / `ChartJsDataset` | `core/ports/query_types.py` | The wire contract; construct literals, never `cast()` |
| `VisualizationService` | `core/services/visualization_service.py` | Pure formatter: Chart.js + Frappe Gantt |
| `VisualizationAggregationService` | `core/services/analytics/visualization_aggregation_service.py` | Fetches domain data and delegates formatting; wired in `services_bootstrap/compose.py` behind `VisualizationOperations` |
| `InsightStore.get_*_chart` | `core/services/insight/insight_store.py` | Four hand-built configs for `/insights` |
| `SemanticColor` palette | `core/utils/palette.py` | PRIMARY/SUCCESS/WARNING/DANGER/INFO/NEUTRAL + `.ALL` cycle |
| Wire-shape pins | `tests/unit/services/test_visualization_wire_shape.py` | Formatter output keys |

**Live endpoints:** `/api/insights/charts/{impact,domain,type}-distribution` and `/api/insights/charts/action-rate` (`adapters/inbound/insights_api.py`, drawn on `/insights`) · `/api/lifepath/alignment/chart` (radar, `adapters/inbound/lifepath_ui.py`, drawn on `/lifepath/alignment`) · `/api/visualizations/{completion,priority-distribution,streaks,status-distribution}` (`adapters/inbound/visualization_api.py`; no page draws them).

**Data flow:** route → service (`InsightStore`, or `VisualizationAggregationService` → `VisualizationService`) → `Result[ChartJsConfig]` → JSON → `chartVis` → `new Chart(canvas, config)`.

---

## Common Pitfalls

| Problem | Solution |
|---------|----------|
| `Chart is not defined` in the card's error slot | Pass `extra_scripts=["/static/vendor/chart.js/chart.umd.js"]` on the shell page. `chartjs_headers()` doesn't reach BasePage, and fragments carry no `<head>` |
| Changing the second `chartVis` argument changes nothing | `loadChart` never reads it; the payload's `"type"` decides |
| Canvas-reuse error on re-render | `chartVis` destroys before recreating, and Alpine calls its `destroy()` when the card leaves the DOM. Don't hand-roll a second `new Chart` on the same canvas |
| Chart missing after an HTMX swap | Alpine initializes a swapped-in `x-data` tree by itself (measured, Alpine 3.14.8 + htmx 1.9.10). Look at the fragment's markup and the page's scripts, not at init wiring |
| `Alpine.data` component "not defined" | Registrations run in the `alpine:init` listener: in `skuel.js` if shared, in a page-local bundle if one surface needs it |
| Time axis renders as category labels | Time scales need the date-fns adapter; `extra_scripts` callers must list it |
| A tick/tooltip `callback` does nothing | The config is JSON; functions can't cross the wire. Use static options |
| `create_chart_view()` / `ui.goals.visualization` in old notes | Deleted. Use the `_chart_card` shape above |
| snake_case dataset keys | Chart.js expects camelCase (`backgroundColor`). `ChartJsDataset` declares the camelCase names, and the `ChartDataset` dataclass mirrors them with `# noqa: N815` |
| No data shows an error, a blank chart, or zeros | It depends on the builder: the distribution/streak formatters return 400, the aggregation service returns 404 for "no active tasks/habits", the completion formatter and the insight configs draw empty or zero charts. Hide the chart at the page (insights needs 3 insights) or pick the state deliberately. See SKILL.md step 4 |
| Hardcoded hex/rgba colors | `SemanticColor` for charts (`RelationshipColor` is the Vis.js edge palette), both in `core/utils/palette.py` |

---

**See Also**: [SKILL.md](SKILL.md) for the live surface, the wire contract and the add-a-chart recipe
**See Also**: [chart-types-reference.md](chart-types-reference.md) for the configs SKUEL emits per chart type
**See Also**: [fasthtml-patterns.md](fasthtml-patterns.md) for card, page and route patterns
