# Chartjs - Quick Reference

> **Fast lookup** for common syntax, methods, and operations

---

## Canonical Snippets

### Chart card — the ONE invocation SKUEL uses

```python
def _chart_card(data_url: str, chart_type: str) -> Any:
    return Div(
        Canvas(**{"x-ref": "canvas", "width": "400", "height": "300", "class": "max-w-full"}),
        Div("Loading chart...", cls="text-center text-muted-foreground py-8", **{"x-show": "loading"}),
        Div(Span("Error: ", cls="font-bold"), Span(**{"x-text": "error"}),
            cls="text-error text-center py-8", **{"x-show": "error"}),
        **{"x-data": f"chartVis('{data_url}', '{chart_type}')",
           "class": "bg-background p-4 rounded-lg shadow"},
    )
```

**When to use**: Every chart. `chartVis(dataUrl, chartType)` (Alpine component in `static/js/skuel.js`) fetches the JSON config and renders into `x-ref="canvas"` — no inline `new Chart(...)` scripts, ever. Live copies: `ui/insights/components.py::_chart_card`, `ui/lifepath/alignment.py::_alignment_radar`.

### Loading Chart.js on a page

```python
return BasePage(
    content, title="Insights | SKUEL", request=request,
    extra_scripts=["/static/vendor/chart.js/chart.umd.js"],
)
```

**When to use**: Every chart page. `BasePage`/`SidebarPage` build their own `<head>` via `build_head()`, so fast_app-level `chartjs_headers()` never reaches them — omit `extra_scripts` and `chartVis` fails silently into its error state with "Chart is not defined". Time-scale charts also need `/static/vendor/chart.js/chartjs-adapter-date-fns.3.min.js`.

### Route serving a Chart.js config

```python
@rt("/api/visualizations/completion")
@boundary_handler()
async def get_completion_chart(request: Request) -> Result[ChartJsConfig]:
    user_uid = require_authenticated_user(request)
    period = request.query_params.get("period", "week")
    return await vis_service.get_completion_chart_data(user_uid=user_uid, period=period)
```

**When to use**: New chart-data endpoints. `boundary_handler()` serializes the `Result[ChartJsConfig]` to JSON; `chartVis` passes the payload straight to `new Chart(ctx, config)`. Hand-built configs via `JSONResponse` also work (`/api/lifepath/alignment/chart` in `adapters/inbound/lifepath_ui.py`).

### Formatting data → config (`VisualizationService`)

```python
service.format_completion_chart(completed=[3, 5], total=[5, 7], labels=["Mon", "Tue"])  # line|bar, % rate
service.format_distribution_chart({"high": 4, "low": 9}, title="Priority")             # pie|doughnut|bar
service.format_streak_chart([{"name": "Run", "current": 3, "best": 12}])               # horizontal bar
```

**When to use**: Standard chart shapes. Pure sync formatters in `core/services/visualization_service.py` — callers supply pre-fetched data; fetching/aggregation lives in `VisualizationAggregationService` (`core/services/analytics/visualization_aggregation_service.py`). All return `Result[ChartJsConfig]` and fail on empty/mismatched data.

### Dataset shape (`ChartDataset` dataclass)

```python
ChartDataset(label="Completion Rate (%)", data=rates,
             backgroundColor=SemanticColor.SUCCESS,   # str or list[str] (color-per-slice)
             borderColor=SemanticColor.SUCCESS, borderWidth=2,
             fill=False, tension=0.1)
```

**When to use**: Building configs by hand. camelCase field names are the Chart.js wire API (`# noqa: N815`). Distribution charts cycle `SemanticColor.ALL`; pie/doughnut use `borderColor="#ffffff"`.

---

## Key Infrastructure

| Piece | Location | Notes |
|-------|----------|-------|
| Vendored Chart.js **v4.5.1** | `static/vendor/chart.js/chart.umd.js` | UMD global `Chart` |
| Date adapter (time scales) | `static/vendor/chart.js/chartjs-adapter-date-fns.3.min.js` | Included by `chartjs_headers()` only |
| `chartjs_headers()` | `ui/theme.py` | For fast_app `hdrs=` contexts, NOT BasePage pages |
| `chartVis` Alpine component | `static/js/skuel.js` (~line 592) | fetch → destroy old → `new Chart`; `refresh(newUrl)`, `destroy()` |
| `VisualizationService` | `core/services/visualization_service.py` | Pure formatter — Chart.js + Frappe Gantt |
| `VisualizationAggregationService` | `core/services/analytics/visualization_aggregation_service.py` | Fetches domain data, delegates formatting; wired in `services_bootstrap/compose.py` |
| `ChartJsConfig` TypedDict | `core/ports/query_types.py` | Route return type |
| `SemanticColor` palette | `core/utils/palette.py` | PRIMARY/SUCCESS/WARNING/DANGER/INFO/NEUTRAL + `.ALL` cycle |

**Live endpoints:** `/api/visualizations/{completion,priority-distribution,streaks,status-distribution}` (`adapters/inbound/visualization_api.py`) · `/api/insights/charts/{impact,domain,type}-distribution,action-rate` (`adapters/inbound/insights_api.py`) · `/api/lifepath/alignment/chart` (radar, `adapters/inbound/lifepath_ui.py`).

**Data flow:** route → `VisualizationAggregationService` (fetch + aggregate) → `VisualizationService` (format) → `Result[ChartJsConfig]` JSON → `chartVis` → `new Chart(canvas, config)`.

---

## Common Pitfalls

| Problem | Solution |
|---------|----------|
| "Chart is not defined" (silent error state) | BasePage builds its own `<head>` — pass `extra_scripts=["/static/vendor/chart.js/chart.umd.js"]`; `chartjs_headers()` won't reach it |
| Canvas-reuse error on re-render | `chartVis` already destroys before recreating (`loadChart`); on element removal Alpine calls its `destroy()`. Don't hand-roll a second `new Chart` on the same canvas |
| Chart dead after HTMX swap | Alpine auto-initializes swapped-in `x-data` trees — never call `htmx.process()`/`Alpine.initTree` from `htmx:load` (known loop bug) |
| Component "not defined" at page load | `Alpine.data()` registrations must run in an `alpine:init` listener, not DOMContentLoaded — register there, in `skuel.js` if shared or a page-local bundle if one surface needs it |
| Time axis renders as category labels | Time scales need the date-fns adapter script; `extra_scripts` callers must add it explicitly |
| Chart collapses to 0 height | Configs set `maintainAspectRatio: False` — keep explicit `width`/`height` attrs on the `Canvas` (or a sized container) |
| `create_chart_view()` from older skill docs | Doesn't exist in the codebase — use the `_chart_card` Canvas + `chartVis` pattern above |
| snake_case dataset keys | Chart.js expects camelCase (`backgroundColor`); dataclasses mirror it with `# noqa: N815` |
| Empty datasets 500 or render blank | Formatters return `Result.fail(Errors.validation(...))` on empty/length-mismatched input — guard upstream (insights hides charts under 3 insights) |
| Hardcoded hex colors | Use `SemanticColor` (charts) / `RelationshipColor` (Vis.js edges) from `core/utils/palette.py` |

---

**See Also**: [SKILL.md](SKILL.md) for the five-layer architecture and full examples
**See Also**: [chart-types-reference.md](chart-types-reference.md) for per-type config options
**See Also**: [activity-domain-charts.md](activity-domain-charts.md) for domain-specific chart recipes
**See Also**: [fasthtml-patterns.md](fasthtml-patterns.md) for FT container patterns
