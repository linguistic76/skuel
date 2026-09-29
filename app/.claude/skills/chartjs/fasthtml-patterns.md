# Chart.js + FastHTML Integration Patterns

How the live chart pages are put together. Every pattern here names the file it
comes from. There is no shared chart component module: each page owns its card.

## Core Principle

> Python renders the card, `chartVis` fetches and draws, and a JSON route returns the whole
> Chart.js config as a `Result[ChartJsConfig]`.

## Pattern 1: The Card

From `ui/insights/components.py`:

```python
from fasthtml.common import Canvas, Div, Span


def _chart_card(data_url: str, chart_type: str) -> Div:
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

What each part does:

- `x-data="chartVis(url, type)"`: the component fetches `url` at init. The payload's
  `"type"` picks the chart; the second argument is never read.
- `Canvas(x-ref="canvas")`: the component draws into `this.$refs.canvas` and fails
  with `Canvas element not found` without it.
- The `x-show="loading"` and `x-show="error"` siblings: the component's two other
  states. `error` holds the server's client-safe message.
- `"class"` goes in the attribute dict because the `x-data` key already forces the dict form.

`ui/lifepath/alignment.py::_alignment_radar()` is the same shape with a fixed URL, a
360×360 canvas and `cls="mb-6"` instead of the card styling.

## Pattern 2: A Chart Section Gated on Data

From `ui/insights/components.py`. The page decides whether there is enough data to
chart, so the cards never render just to show an error:

```python
def render_charts_section(insight_count: int) -> Div | None:
    """Render the visual analytics charts section. Returns None if insufficient data."""
    if insight_count < 3:
        return None

    return Div(
        H3("Visual Analytics", cls="text-xl font-bold mb-4"),
        Div(
            _chart_card("/api/insights/charts/impact-distribution", "doughnut"),
            _chart_card("/api/insights/charts/domain-distribution", "bar"),
            _chart_card("/api/insights/charts/type-distribution", "doughnut"),
            _chart_card("/api/insights/charts/action-rate", "doughnut"),
            cls="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6",
        ),
        cls="mb-8",
    )
```

The grid is one column on a phone and two from `md:` up. The route
(`adapters/inbound/insights_ui.py`) places the section in its content and loads
Chart.js on the page:

```python
charts_section = render_charts_section(len(insights))
content = Div(
    # ... header, filters ...
    charts_section if charts_section else Div(),
    # ... insight cards ...
)
return BasePage(
    content,
    title="Insights | SKUEL",
    page_type=PageType.STANDARD,
    request=request,
    active_page="insights",
    extra_scripts=["/static/vendor/chart.js/chart.umd.js"],
)
```

## Pattern 3: A Chart Inside a Shell-First Fragment

From `adapters/inbound/lifepath_ui.py`. The page route returns a shell with a lazy
placeholder, and the chart arrives in the HTMX fragment that replaces it:

```python
@rt("/lifepath/alignment")
def alignment_dashboard(request: Request) -> FT:
    """Alignment dashboard — shell only, content loads via HTMX."""
    require_authenticated_user(request)
    if not lifepath_service:
        return _service_unavailable_page()
    content = content_loading_placeholder(
        "/lifepath/alignment/content", "lifepath-alignment-content"
    )
    return lifepath_sidebar_page(
        "alignment",
        content,
        request,
        extra_scripts=["/static/vendor/chart.js/chart.umd.js"],
    )
```

Two rules follow from this shape:

1. **Chart.js loads on the shell.** The fragment
   (`/lifepath/alignment/content` → `render_alignment_dashboard` → `_alignment_radar()`)
   is swapped in with no `<head>`, so it cannot bring a script tag that the shell
   didn't. `lifepath_sidebar_page` forwards `extra_scripts` to `SidebarPage`.
2. **The swap needs no init code.** Alpine initializes the `chartVis` tree in the
   swapped-in fragment, and calls `destroy()` if a later swap removes it. This was
   measured against the vendored Alpine 3.14.8 and htmx 1.9.10.

## Pattern 4: The Chart-Data Route

From `adapters/inbound/insights_api.py`:

```python
@rt("/api/insights/charts/impact-distribution")
@boundary_handler(success_status=200)
async def impact_distribution_chart(request: Request) -> Result[ChartJsConfig]:
    """Chart.js doughnut chart config for impact distribution."""
    user_uid = require_authenticated_user(request)
    return await insight_store.get_impact_distribution_chart(user_uid)
```

- The return type is `Result[ChartJsConfig]`: never `Any`, never a bare `dict`.
- `boundary_handler` turns `Result.ok(config)` into a JSON body that is the config
  itself, which is what `new Chart(ctx, config)` needs. `Result.fail(...)` becomes the
  client-safe error payload with its HTTP status. `chartVis` rejects on non-2xx and
  shows the payload's `message`.
- The user comes from `require_authenticated_user`. A chart URL never carries
  `user_uid`; `adapters/inbound/visualization_api.py` notes the IDOR it closed by
  dropping that parameter.
- `request: Request` is imported from `adapters.inbound.fasthtml_types` (SKUEL035).

## Pattern 5: Re-pointing a Chart (`refresh`)

`chartVis` exposes `refresh(newUrl)`, which re-runs `loadChart` against a new URL
(or the original one when called with no argument). **No live page calls it yet.**
A control inside the card's `x-data` scope can drive it:

```python
from fasthtml.common import Canvas, Div, Option

from ui.components import Select  # the Tailwind-styled native <select>


def completion_chart_card() -> Div:
    base = "/api/visualizations/completion?period="
    return Div(
        Select(
            Option("Week", value="week"),
            Option("Month", value="month"),
            Option("Quarter", value="quarter"),
            aria_label="Completion period",
            full_width=False,
            **{"x-on:change": f"refresh('{base}' + $event.target.value)"},
        ),
        Canvas(**{"x-ref": "canvas", "width": "400", "height": "300", "class": "max-w-full"}),
        # ... loading / error slots as in Pattern 1 ...
        **{"x-data": f"chartVis('{base}week', 'line')"},
    )
```

`period` accepts `week`, `month` or `quarter`; anything else is a 400
(`Errors.validation`), which lands in the card's error slot. (This was measured with
the real `skuel.js` and Alpine in jsdom: the change handler fetched the new URL, and a
400 body's `message` filled the error slot. A failed refresh leaves the previous
chart drawn beside the error, because only a successful load destroys it.) The other approach is to
re-render the whole card through an HTMX swap with a new URL. Alpine destroys the old
instance and initializes the new one.

## What Not to Build

- **A second chart wrapper that loads its own `Script(src=chart.umd.js)`.** Load the
  library once, on the shell, with `extra_scripts`.
- **`x-on:htmx:before-swap="destroy()"`.** It's redundant, because Alpine calls
  `destroy()` when the element is removed.
- **Cache headers on chart routes.** No live chart route sets one, and a chart reads
  user-owned data. Measure first if a chart ever needs caching.

## Related Files

- [SKILL.md](SKILL.md): the live surface, wire contract and add-a-chart recipe
- [chart-types-reference.md](chart-types-reference.md): the configs SKUEL emits, per type
- [QUICK_REFERENCE.md](QUICK_REFERENCE.md): snippets and pitfalls
- `/ui/insights/components.py`: `_chart_card()` and `render_charts_section()`
- `/ui/lifepath/alignment.py`: `_alignment_radar()`
