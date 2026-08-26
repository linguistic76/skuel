---
related_skills:
- ui-browser
---
# Alpine.js Architecture
*Last updated: 2026-08-04*
## Related Skills

For implementation guidance, see:
- [@ui-browser](../../.claude/skills/ui-browser/SKILL.md)

## Overview

SKUEL uses **Alpine.js** as the single JavaScript framework for all client-side UI state management. This document describes the architecture, patterns, and implementation details.

## Versioning Policy

**Self-hosted, version-pinned:** SKUEL vendors Alpine.js locally rather than using CDN.

| Aspect | Policy |
|--------|--------|
| **Location** | `/static/vendor/alpinejs/alpine.{version}.min.js` |
| **Current Version** | 3.14.8 |
| **CDN Usage** | None - fully self-hosted |

**Why self-host?**
- **Version stability** - Same version for all users, all deployments
- **No CDN dependency** - Works offline, no third-party outages
- **Explicit upgrades** - Version changes are deliberate, not automatic

**To upgrade Alpine.js:**
```bash
# Download new version
curl -sL "https://unpkg.com/alpinejs@X.Y.Z/dist/cdn.min.js" \
  -o static/vendor/alpinejs/alpine.X.Y.Z.min.js
```

Then update the version in **two** places — no page or route needs editing, but
both of these do:

1. **`ALPINE_VERSION` in `ui/theme.py`.** `skuel_headers()` interpolates it into
   the single `<script>` tag the whole app serves.
2. **`PRECACHE_URLS` in `static/service-worker.js`**, which hardcodes the
   *versioned* filename — **and bump `CACHE_VERSION` in the same file.** The PWA
   precache is not optional bookkeeping: `install` calls `cache.addAll()`, which
   rejects **wholesale** if any single URL 404s, so a stale entry pointing at the
   old filename breaks service-worker installation for every client. Without the
   `CACHE_VERSION` bump, already-installed clients keep serving the old Alpine
   indefinitely. The file says so itself at the top.

Finally update this file + CLAUDE.md for the prose references.

> The same two-place rule applies to **HTMX** (`HTMX_VERSION` in `ui/theme.py`
> plus its own `PRECACHE_URLS` entry), and to any other vendored asset whose
> filename carries a version.

## Core Philosophy

> "Alpine.js handles UI state, HTMX handles server communication"

| Layer | Technology | Responsibility |
|-------|------------|----------------|
| **UI State** | Alpine.js | Modals, toggles, filtering, animations |
| **Server Communication** | HTMX | Form submissions, content loading |
| **Presentation** | FastHTML | HTML generation with Python |

**The Rule:** If it needs the server, use HTMX. If it's purely UI, use Alpine.

## HTMX Version Standardization (Critical)

SKUEL standardizes on **HTMX 1.9.10** across all pages for navigation consistency.

### Why Version Consistency Matters

FastHTML's `fast_app()` includes HTMX 2.0.7 by default. When different pages use different HTMX versions, navigation breaks:
- Navbar links may reload but stay on the same URL
- Multiple clicks required for navigation to work
- Inconsistent behavior across page types

### The Solution: One Emitter

Consistency is structural, not a convention pages have to follow.
`ui/theme.py:skuel_headers()` is the **only** place in the tree that emits the
HTMX or Alpine `<script>` tag, and `build_head()` is the only way a page gets
them — so no page *can* pin a different version. `HTMX_VERSION` and
`ALPINE_VERSION` in that module are the single source for both.

Pages therefore do not hand-assemble `Head()`. A page that does gets no HTMX, no
Alpine, no `skuel.js` and no compiled CSS. See § *There is no second path* below,
and CLAUDE.md § UI Component Pattern.

> This section previously prescribed the opposite — every page returning its own
> `Html(...)` with hand-written `<script>` tags, and HTMX pulled from
> `unpkg.com`. Both are now wrong: nothing is LOADED from a CDN at runtime (see
> the Version Matrix below — HTMX and Alpine are vendored under
> `/static/vendor/`; the `curl` above downloads FROM unpkg in order to vendor a
> new version, which is not the same thing), and hand-built heads were the very
> failure mode the single emitter removed.

### Version Matrix

| Component | Version | Source |
|-----------|---------|--------|
| HTMX | 1.9.10 | Self-hosted (`/static/vendor/`) |
| Alpine.js | 3.14.8 | Self-hosted (`/static/vendor/`) |
| Tailwind CSS | (compiled) | `static/css/output.css` (Tailwind CLI) |
| Lucide icons | 1.22.0 | Self-hosted (`/static/vendor/lucide/`) |

**See:** `/docs/patterns/UI_COMPONENT_PATTERNS.md#page-layout-architecture-critical` for detailed patterns.

## File Structure

```
static/js/
├── skuel.js          # SHARED Alpine.data() components (~2600 lines, 22 of the 26)
├── today.js          # page-local: today
├── explore-reading.js  # page-local: exploreReading
├── ku-reading.js     # page-local: kuReading
└── ps-detail.js      # page-local: pathstep

ui/
├── calendar/               # FastHTML + Alpine directives
├── search/                 # FastHTML + Alpine directives
├── patterns/modal.py       # AlpineModal — the shared modal wrapper
└── theme.py                # skuel_headers() — the single Alpine <script> tag

.claude/skills/ui-browser/   # Claude Code skill documentation (HTMX + Alpine.js)
└── SKILL.md
```

## Available Components

There are **26** components, and `skuel.js` is **not** the only registrar — a
natural assumption, and a wrong one. `skuel.js` holds the **22 shared**
components; four page-local bundles register one each and are loaded only by
their own routes.

The table below is the **canonical page-local inventory** — the one place those
four are enumerated; other docs point here rather than repeat the list.

Only the **Component** column is machine-checked (it must equal the set of
components registered outside `skuel.js`). The path columns are ordinary prose
and can rot — note that the file emitting `Script(src=…)` is usually *not* the
renderer that mounts the component, which is easy to get backwards.

<!-- alpine-registry:page-local:begin -->

| Component | Bundle | `Script(src=…)` emitted by | Mounted by |
|-----------|--------|---------------------------|------------|
| `today` | `static/js/today.js` | `ui/today/page.py:78` | `ui/today/page.py` |
| `exploreReading` | `static/js/explore-reading.js` | `adapters/inbound/explore_ui.py:277` | `ui/explore/reading_plan.py` |
| `kuReading` | `static/js/ku-reading.js` | `adapters/inbound/learning_loop_routes.py:169` | `ui/explore/ku_detail.py` |
| `pathstep` | `static/js/ps-detail.js` | `adapters/inbound/learning_loop_routes.py:332` | `ui/explore/ps_detail.py` |

<!-- alpine-registry:page-local:end -->

Put a component in `skuel.js` when more than one page needs it; a page-local
bundle keeps single-surface behaviour off every other page's critical path.

The four below are the shared ones worth reading as patterns; for the full
shared list see
[@ui-browser](../../.claude/skills/ui-browser/SKILL.md#skuel-component-architecture),
whose table is machine-checked against the registry.

### searchFilters()

Drives the `/search` facet bar: a horizontal filter bar on desktop (with a
"More filters" disclosure) that becomes an off-canvas drawer on mobile.

The page has **two scope facets** and only one may be set at a time — Type (an
Activity Domain) and Nous (a knowledge topic). Their intersection is empty by
construction, so the markup disables whichever is not in use; see
[SEARCH_ARCHITECTURE.md § UI Mapping](SEARCH_ARCHITECTURE.md).

**State:**
- `entityType`: string - Current entity type (activity scope)
- `nousTopic`: string - Current NOUS topic (knowledge scope)
- `filtersOpen`: boolean - Mobile: off-canvas filter drawer open?
- `moreFilters`: boolean - Desktop: advanced facets revealed?
- `isDesktop`: boolean - ≥1024px, set from `matchMedia` in `init()`
- `filterCount`: number - Active facets, shown on the mobile trigger badge

**Computed (getters):**
- `isKnowledgeMode` - a NOUS topic is chosen; drives the four knowledge filters
- `knowledgeFilterGroups` - which groups those are, read from the `'ku'` entry of
  `entityTypeFilters` (the map, not the dropdown vocabulary — Ku has no Type option)
- `showContextFilters` / `contextFilterLabel` - Tier 2 filters, for **either** scope
- `hasActiveFilters` - any facet or entity type active

**Methods:**
- `isFilterVisible(group)` - Check if a Tier 2 filter group should show, keyed to
  whichever scope facet is set. Also drives each column's `x-bind:disabled`: htmx
  omits disabled elements, so a hidden filter is withheld rather than silently
  narrowing every request
- `adoptScope(event)` - Bound `x-on:change.capture` on the panel. Applies that
  predicate imperatively for the current event, because Alpine's effects flush a
  frame after the synchronous change handlers — capture phase on an ancestor is
  the only way to land before the changed control's own htmx listener
- `updateFilterCount()` - Re-tally active facets (bound to `x-on:change`, bubble
  phase, so it counts what the request will carry)
- `askHref()` - Build the scoped `/askesis?...` URL from live facet inputs
- `clearFilter(name)` / `clearAllFilters()` - Reset one / all facets

### collapsible(initiallyOpen)

Expand/collapse sections with smooth transitions. The minimal component — one
boolean, one method.

**State:**
- `expanded`: boolean - Current state

**Methods:**
- `toggle()` - Toggle expanded state

### chartVis(dataUrl, chartType)

Fetches JSON and renders a Chart.js chart. The reference pattern for a component
that **owns an async load**: it models the request's three outcomes explicitly
rather than leaving the template to guess.

**State:**
- `chart`: object | null - The Chart.js instance
- `loading`: boolean - Request in flight
- `error`: string | null - Failure message, rendered in place of the chart

**Methods:**
- `init()` - Kicks off `loadChart(dataUrl, chartType || 'line')`
- `loadChart(url, type)` - Fetch, destroy any prior chart, render
- `destroy()` - Tear down the Chart.js instance (call on unmount)

### collapsibleSidebar(storageKey, defaultCollapsed)

Sidebar collapse that **survives navigation and is shared between instances**.
State lives in `Alpine.store(storageKey)`, not on the component, so two sidebars
sharing a key stay in lockstep; `toggle()` mirrors it to
`localStorage[storageKey + '-collapsed']`.

**State:**
- `collapsed`: boolean - a *getter* reading `Alpine.store(storageKey)`

**Methods:**
- `init()` - Registers the shared store on first use (desktop restores from `localStorage`)
- `toggle()` - Flips the store and persists it

> **Two capabilities documented here until March 2026 are gone.** Touch/swipe
> gesture handling has no successor — nothing in the tree binds `touchstart`
> today. Button loading state does: it is now HTMX-native, via `hx_indicator`
> pointing at an element with the `htmx-indicator` class (see
> `ui/journals/__init__.py`), or inline component state driven by
> `x-on:htmx:before-request` — not a registry component.

## FastHTML Integration Pattern

Alpine directives are passed as `**kwargs` in FastHTML components:

```python
from fasthtml.common import Div
from ui.components import Button, ButtonT

def my_component() -> Div:
    return Div(
        Button(
            "Toggle",
            **{"x-on:click": "toggle()"},
        ),
        Div(
            "Content",
            **{
                "x-show": "expanded",
                "x-transition": "",
            },
        ),
        cls="my-component",
        **{"x-data": "collapsible(false)"},
    )
```

**Key patterns:**
- Use `**{"x-directive": "value"}` syntax for Alpine attributes
- Reference centralized components: `x-data="componentName()"`
- Combine multiple directives with multiple `**{}` spreads

## Loading Alpine.js

### SKUEL Pages (Standard)

SKUEL's `skuel_headers()` automatically includes Alpine.js (self-hosted for stability):

```python
from fasthtml.common import fast_app
from ui.theme import skuel_headers, chartjs_headers

app, rt = fast_app(
    hdrs=(*skuel_headers(), *chartjs_headers()),  # Includes Alpine.js 3.14.8
)
```

### There is no second path

The single-emitter rule is stated under *HTMX Version Standardization* above and
applies identically to Alpine: `skuel_headers()` emits the tag, `build_head()`
delivers it, and a page that assembles its own `Head()` gets no Alpine, no
`skuel.js` and no compiled CSS.

This section previously documented a "standalone page" pattern for Timeline and
Search that hand-inlined the vendored path. Both surfaces now go through
`build_head()` like everything else, and the `/timelines` surface itself was
deleted in #934.

## Common Directives

| Directive | Purpose | Example |
|-----------|---------|---------|
| `x-data` | Initialize component | `x-data="searchFilters()"` |
| `x-show` | Toggle visibility (CSS) | `x-show="expanded"` |
| `x-if` | Conditional render (DOM) | `<template x-if="show">` |
| `x-on:event` | Event handler | `x-on:click="toggle()"` |
| `x-model` | Two-way binding | `x-model="datetime"` |
| `x-bind:attr` | Dynamic attribute | `x-bind:class="'base ' + modifier"` |
| `x-ref` | Element reference | `x-ref="container"` |
| `x-transition` | CSS transitions | `x-transition` |

## Adding New Components

1. **Define in a `/static/js/` bundle** — `skuel.js` if more than one page needs
   it, otherwise a page-local bundle (see the inventory above):

> ⚠️ Register inside `alpine:init`, **never** `DOMContentLoaded`. Alpine loads `defer` and starts via `queueMicrotask` — it walks the DOM *before* `DOMContentLoaded` fires. Components registered in `DOMContentLoaded` are still undefined when Alpine initializes initial server-rendered `x-data`, throwing "`<component> is not defined`" on hard load (hx-boost navigation masks it via `htmx:load` re-init). See #468.

```javascript
document.addEventListener('alpine:init', function() {
    Alpine.data('myComponent', function(initialValue) {
        return {
            // State
            value: initialValue || '',
            loading: false,

            // Methods
            submit: function() {
                this.loading = true;
                // ... implementation
            },

            // Lifecycle
            init: function() {
                // Called when component initializes
            }
        };
    });
});
```

2. **Reference in FastHTML:**

```python
def my_page():
    return Div(
        # Component content...
        **{"x-data": "myComponent('default')"},
    )
```

## HTMX + Alpine Collaboration

Alpine handles UI state, HTMX handles server communication. For a one-boolean
busy flag there is no registry component — declare the state inline and let
HTMX's lifecycle events drive it:

```python
Div(
    Button(
        Span("Save", **{"x-show": "!busy"}),
        Span("Saving...", **{"x-show": "busy"}),
        hx_post="/api/save",
        hx_target="#result",
        **{"x-bind:disabled": "busy"},
    ),
    **{
        "x-data": "{ busy: false }",
        "x-on:htmx:before-request": "busy = true",
        "x-on:htmx:after-request": "busy = false",
    },
)
```

Register a named component only when the state outlives one element or the logic
is worth a name — and then in `skuel.js` **only if more than one page needs it**;
otherwise a page-local bundle, per the rule above. A spinner with no other
behaviour is better served by HTMX alone — `hx_indicator="#save-spinner"` plus the
`htmx-indicator` class, no Alpine at all.

## Migration History

**January 15, 2026:** Self-hosted Alpine.js, removed CDN dependency.
- Downloaded Alpine.js 3.14.8 to `/static/vendor/alpinejs/`
- Updated 4 standalone page components to use local file
- Rationale: Version stability, offline capability, explicit upgrades

**January 2026:** Consolidated all JavaScript into centralized Alpine.js architecture.

**Migrated files** — and what became of each. The middle column is a *historical*
record: none of those three names is a live component today, so do not copy them.

| Legacy file | Became (Jan 2026) | Today |
|-------------|-------------------|-------|
| `search_sidebar.js` (189 lines) | `searchSidebar()` | **Gone** (deleted as dead, `327f26623`). The `/search` facet bar is `searchFilters()`, a separate component that predates it and is now the sole owner — reshaped into a desktop bar + mobile drawer in #559. |
| `calendar.js` (108 lines) | `calendarPage()` | **Renamed** `calendarLegend()` in #621, when the legend swatches became type filters. Same registration, new name — the capability is live. |
| `timeline_viewer.js` (147 lines) | `timelineViewer()` | **Gone** (deleted as dead, `327f26623`). No successor: the `/timelines` surface was itself deleted in #934. |

**Deleted files:**
- `journals_audio_upload.js` (323 lines) - Legacy code

**Result:** Single source of truth for all JavaScript behavior, no external dependencies.

**March 28, 2026 (`327f26623`):** "clean up dead UI code left behind after Activity
Domain shelving" removed 12 Alpine components in one commit — `accessibleModal`,
`calendarModal`, `choiceOptions`, `dropdownNav`, `focusTrapModal`, `ganttVis`,
`insightSwipeActions`, `loadingButton`, `searchSidebar`, `swipeHandler`,
`taskEditModal`, `timelineViewer` — and updated none of the documentation. That
drift is why the registry is now machine-checked; see *Registry drift* below.

## Registry drift

`skuel.js` is the source of truth for what exists. Two mechanisms keep the docs
honest, and both fail loudly rather than silently:

1. `scripts/smoke_test.py` — `_REGISTRY_COMPONENTS` mounts every registered
   component, and `_assert_registry_in_sync()` fails if it drifts from
   `Alpine.data(` in `skuel.js`. Deleting a component forces this list to change.
2. `tests/unit/docs/test_alpine_docs_registry.py` — asserts that every component
   this file, the ui-browser skill, and the UI development guide name in an
   `x-data` position or a marked registry table is one of those components.

Together: delete a component from `skuel.js`, and the docs that still teach it
fail CI in the same run.

## Related Documentation

- **CLAUDE.md:** Quick reference (Alpine.js Architecture section)
- **Skills:** `/.claude/skills/ui-browser/` - Detailed skill documentation
- **FastHTML:** `/docs/llms.txt/fasthtml-llms.txt` - FastHTML patterns
