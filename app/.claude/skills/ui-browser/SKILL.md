---
name: ui-browser
description: Expert guide for SKUEL's browser interactivity layer — HTMX for server communication + Alpine.js for client-side state. Use when adding dynamic behavior, AJAX requests, reactive UI, client-side toggles, modals, dropdowns, form submissions without page reload, or when the user mentions HTMX, Alpine.js, hypermedia, reactive, client-side state, hx-* attributes, x-data, AJAX, or interactive components.
allowed-tools: Read, Grep, Glob
---

# Browser Interactivity: HTMX + Alpine.js

## Core Philosophy

> "Two tools, one clear boundary — HTMX talks to the server, Alpine manages the client."

| Layer | Tool | Responsibility |
|-------|------|----------------|
| **Server communication** | HTMX | Data fetching, form submission, partial page updates |
| **Client UI state** | Alpine.js | Toggles, modals, dropdowns, animations, gestures |
| **No tool needed** | HTML5 | Progressive enhancement (details/summary, dialog) |

**The Rule:** If it needs the server, use HTMX. If it's purely UI state, use Alpine. If HTML5 native elements suffice, use those.

---

## Decision Table: Alpine vs HTMX

| Scenario | Use | Why |
|----------|-----|-----|
| Load data from server | **HTMX** | Server owns the data |
| Submit a form | **HTMX** | Persistence is server-side |
| Navigate between pages | **HTMX** + standard links | URL/history management |
| Toggle modal open/close | **Alpine** | Pure UI state |
| Animate elements in/out | **Alpine** | Client-side transitions |
| Touch/swipe gestures | **Alpine** | Real-time input handling |
| Dropdown menus | **Alpine** | Instant responsiveness |
| Form field show/hide | **Alpine** | Immediate user feedback |
| Loading indicator during request | **Both** | Alpine shows, HTMX triggers |
| Search with debounce | **HTMX** | Input triggers server query |
| Infinite scroll | **HTMX** | Load more from server |
| Tab panels (pre-loaded content) | **Alpine** | Toggle visibility only |
| Tab panels (server-fetched) | **HTMX** | Fetch on tab switch |

---

## HTMX: The Request Lifecycle

HTMX extends HTML by giving every element access to the full HTTP protocol.

### Quick Start

```html
<!-- Button that makes a POST, replaces itself with response -->
<button hx-post="/api/like" hx-swap="outerHTML">Like (0)</button>
<!-- Server returns: <button hx-post="/api/like" hx-swap="outerHTML">Like (1)</button> -->
```

### 1. Trigger — When to Request

```html
<!-- Default: click for buttons, submit for forms, change for inputs -->
<button hx-get="/data">Click triggers GET</button>

<!-- Explicit triggers -->
<div hx-get="/data" hx-trigger="mouseenter">Hover to load</div>
<div hx-get="/data" hx-trigger="load">Load on page load</div>
<div hx-get="/data" hx-trigger="revealed">Load when scrolled into view</div>
<div hx-get="/data" hx-trigger="every 5s">Poll every 5 seconds</div>

<!-- Modifiers -->
<input hx-get="/search" hx-trigger="keyup changed delay:300ms" name="q">
<button hx-get="/data" hx-trigger="click once">Load once</button>
```

### 2. Request — What to Send

```html
<!-- Form values sent automatically -->
<input name="search" hx-get="/search" hx-trigger="input changed delay:300ms">

<!-- Include extra inputs -->
<div hx-include="[name='filters']">
  <input name="filters" value="active">
  <button hx-get="/items">Filter</button>
</div>

<!-- Static JSON values -->
<button hx-post="/action" hx-vals='{"status": "complete"}'>Complete</button>

<!-- Dynamic JS values -->
<button hx-post="/action" hx-vals="js:{timestamp: Date.now()}">Action</button>
```

### 3. HTTP Verbs

```html
<button hx-get="/resource">GET — retrieve</button>
<form hx-post="/resource">POST — create</form>
<form hx-put="/resource/1">PUT — replace</form>
<button hx-patch="/resource/1" hx-vals='{"field": "value"}'>PATCH — update</button>
<button hx-delete="/resource/1" hx-confirm="Delete?">DELETE — remove</button>
```

### 4. Swap — Where to Put the Response

```html
<!-- innerHTML (default) — replace element's content -->
<div hx-get="/content" hx-swap="innerHTML">Content replaced here</div>

<!-- outerHTML — replace entire element -->
<button hx-get="/new-button" hx-swap="outerHTML">I get replaced</button>

<!-- beforeend — append inside element -->
<ul hx-post="/items" hx-swap="beforeend"><li>New items after me</li></ul>

<!-- afterend — insert after element -->
<div hx-get="/sibling" hx-swap="afterend">Sibling added after</div>

<!-- delete — remove target element -->
<button hx-delete="/item/1" hx-swap="delete">Removes target</button>

<!-- none — side effects only (analytics, etc.) -->
<button hx-post="/track" hx-swap="none">Track only</button>
```

### 5. Target — Which Element to Update

```html
<!-- By CSS selector -->
<button hx-get="/content" hx-target="#content-area">Load into #content-area</button>

<!-- Relative -->
<button hx-delete="/item" hx-target="closest tr">Remove parent row</button>
<button hx-get="/data" hx-target="next .preview">Update next sibling</button>

<!-- Self -->
<div hx-get="/self-update" hx-target="this">Updates itself</div>
```

---

## HTMX & Alpine.js Pattern Recipes

Copy-paste recipes live in **[patterns-reference.md](patterns-reference.md)**:
- **HTMX** — active search, infinite scroll, click-to-edit, form submission, file upload, out-of-band swaps, response headers, shell-first loading, loading states, accessibility.
- **Alpine.js** — AlpineModal, collapsible sections, tabs (the canonical `:style` pattern), click-outside dropdowns, conditional fields, touch swipe, event & transition modifiers.

---

## Alpine.js: Client-Side Reactivity

### Quick Start — CDN vs SKUEL

```python
# SKUEL: vendored, version-pinned
Script(src="/static/vendor/alpinejs/alpine.3.14.8.min.js", defer=True)
```

### Directive Reference

| Directive | Purpose | Example |
|-----------|---------|---------|
| `x-data` | Initialize component state | `x-data="{ count: 0 }"` |
| `x-show` | Toggle CSS display (stays in DOM) | `x-show="open"` |
| `x-if` | Conditional rendering (DOM add/remove) | `<template x-if="show">` |
| `x-for` | Loop/repeat elements | `<template x-for="item in items">` |
| `@click` / `x-on:click` | Event listener | `@click="toggle()"` |
| `x-model` | Two-way data binding | `x-model="name"` |
| `:class` / `x-bind:class` | Dynamic class | `:class="{ active: open }"` |
| `x-text` | Set text content | `x-text="message"` |
| `x-transition` | Enter/leave animation | `x-transition` |
| `x-ref` | Element reference | `x-ref="input"` → `$refs.input` |
| `x-cloak` | Hide until Alpine initializes | CSS rule in `static/css/main.css`: `[x-cloak] { display: none !important }` |
| `x-init` | Run on initialization | `x-init="fetchData()"` |

### Magic Properties

| Property | Purpose |
|----------|---------|
| `$el` | Element evaluating the CURRENT expression — in a method called from a descendant's `x-on:click`, `$el` is that descendant, NOT the component root |
| `$root` | The `x-data` root element — use this to `querySelector` within the component |
| `$refs` | Named element references |
| `$store` | Global Alpine store |
| `$watch` | Watch data changes |
| `$dispatch` | Dispatch custom event |
| `$nextTick` | Run after DOM update |

**`$el` vs `$root` gotcha:** a component method that does `this.$el.querySelector(...)` works when invoked during `init()` (there `$el` IS the root) but silently scopes to the triggering element when invoked from a descendant's event handler — queries return null and reads come back empty. Bug class caught live on /search's Ask button (`askHref`, 2026-07-07). Rule: `this.$root` for component-scoped queries; `this.$el` only when you mean "the element this expression is on."

### x-show vs x-if

```html
<!-- x-show: Element stays in DOM, just hidden — use for frequent toggles -->
<div x-show="tab === 'settings'">Fast toggle (good for modals)</div>

<!-- x-if: Element added/removed from DOM — use for rare, heavy components -->
<template x-if="showExpensiveWidget">
  <div>Rarely shown, destroyed when hidden</div>
</template>
```

---

## SKUEL Component Architecture

All Alpine components live in `/static/js/skuel.js` (centralized, not inline):

| Component | Purpose | Key State |
|-----------|---------|-----------|
| `searchFilters()` | Search filter bar (nous/subtopic faucets, Ask href) | `entityType`, `showAdvanced` |
| `calendarLegend` | Calendar legend type filters (toggle hide/show + hover spotlight, localStorage) | `hidden`, `spotlight` |
| `collapsible(initial)` | Expand/collapse | `expanded` |
| `chartVis(url, type)` | Chart.js | `chart`, `loading`, `error` |
| `timelineVis(url)` | Vis.js Timeline | `timeline`, `loading`, `error` |
| `collapsibleSidebar(key)` | Sidebar collapse + localStorage | reads `Alpine.store(key)` |
| `relationshipGraph(uid, type)` | Vis.js lateral relationships | `network`, `loading` |
| `exploreGraph(mode, uid, type)` | Explore sidebar Vis.js graph | `network`, `filter`, `expanded` |
| `offlineIndicator` | PWA offline status banner | `isOffline` |
| `toastManager()` | Toast notifications | queue, auto-dismiss |
| `entityPicker()` | Entity UID picker with search | query, results |
| `formValidator()` | Client-side form validation | field errors |
| `hierarchyTree()` | Tree view: expand/collapse, keyboard nav, drag-drop | node state |

Table is non-exhaustive — `skuel.js` also registers `domainFilter`, `bulkInsightManager`, `insightDetailModal`, `intelligenceCache`, `profileFocusHandler`, `insightFiltersDebounced`, `exploreSearch`, `revisionForm`, `batchTranscribe`, `userFolderTranscribe`, `submit`. Grep `Alpine.data('` in `/static/js/skuel.js` for the authoritative list.

**Usage in FastHTML:**
```python
Div(
    content,
    **{"x-data": "searchFilters()"},  # Reference centralized component
)
```

**Adding new components:** Define in `skuel.js` inside the `alpine:init` event listener, not inline in templates.

---

## FastHTML Integration

Alpine attributes use `**kwargs` in FastHTML (dashes become underscores, or use string keys):

```python
# Via **kwargs with string keys (preferred for Alpine)
Div(
    Button("Toggle", **{"@click": "open = !open"}),
    Div("Content", **{"x-show": "open", "x-transition": ""}),
    **{"x-data": "{ open: false }"}
)

# For x-data referencing skuel.js component
Div(
    content,
    **{"x-data": "collapsible(true)"},  # initiallyOpen=True
)
```

### Splat vs underscore-kwarg — and the mypy `arg-type` rule

FastHTML maps `_`→`-`: a **single** underscore → one hyphen (`hx_get`→`hx-get`, `x_show`→`x-show`, `x_ref`→`x-ref`), a **double** underscore → two hyphens (`hx_on__after_request`→`hx-on--after-request`). So **prefer the underscore kwarg** whenever the rendered attribute name is reachable by that mapping — it needs no `**{}` splat. The `**{"...": ...}` splat is required **only** for attribute names no `_`→`-` mapping can produce:

| Attribute shape | Example | Kwarg form? |
|-----------------|---------|-------------|
| Plain hyphen (HTMX/Alpine) | `hx-get`, `x-show`, `x-model`, `hx-target` | ✅ `hx_get=`, `x_show=`, … (no splat) |
| HTMX `hx-on::` event | `hx-on::after-request` | ✅ `hx_on__after_request=` — `__`→`--`, and htmx treats `hx-on--evt` as identical to `hx-on::evt` (its colon-free form; verified in htmx 1.9.10) |
| Alpine colon | `x-on:click`, `:class` / `x-bind:class` | ❌ splat only — Alpine has **no** dash form (`x_on_click`→`x-on-click` and `x_on__click`→`x-on--click` are both broken directives) |
| Alpine at-shorthand | `@click`, `@click.outside` | ❌ splat only (`@` not a valid identifier) |
| Alpine dot-modifier | `@click.stop`, `x-on:keyup.debounce.500ms` | ❌ splat only |

The split is by **library**, not by punctuation: HTMX defines a colon-free double-dash alias for `hx-on`, so its event handlers are reducible; Alpine parses on the colon exclusively, so its `x-on:` / `x-bind:` / `@` / `.modifier` attrs are genuinely irreducible.

**Why it matters for types:** a `**dict[str, str]` splat into a **SKUEL FT component** (`Button`, `Input`, `Select`, …) trips mypy `arg-type` — the dict's `str` values spill onto the component's typed keyword slots (`disabled: bool`, `size: Size | None`). The fix follows the table:

- **Reducible attrs (plain-hyphen + HTMX `hx-on::`) → use the underscore kwarg.** No splat, no suppression. (e.g. `Button("Back", hx_get="/tasks", hx_target="body")`, *not* `**{"hx-get": …}`; `Form(..., hx_on__after_request=expr)`, *not* `**{"hx-on::after-request": expr}`.)
- **Irreducible Alpine attrs (colon / at / dot) → keep the splat + a surgical ignore:** `**{"x-on:click": expr},  # type: ignore[arg-type]  # fasthtml dynamic-attr splat`.

⚠️ **Escape DYNAMIC values interpolated into an Alpine/JS expression with `json.dumps()`.** An Alpine handler attribute is *JS source*, so a runtime value spliced into it can break out of its string literal (or inject). Use `json.dumps()` — it emits a properly-escaped JS string literal, and FastHTML's attribute escaping handles the surrounding quotes:

  ```python
  # ✅ tag="it's"  →  setTag("it&#39;s")  (browser-decodes to valid setTag("it's"))
  **{"x-on:click": f"setTag({json.dumps(tag)})"}
  # ❌  setTag('it's')  — the apostrophe ends the JS string; the click throws / injects
  **{"x-on:click": f"setTag('{tag}')"}
  ```

  Only **dynamic** values need this — static literals you control (e.g. `f"filterPreset = '{preset}'"` where `preset` is a hardcoded `"all"`/`"overdue"`) are safe as-is.

⚠️ **A colon/`@` Alpine directive written as an underscore-kwarg renders DEAD, silently.** `x_on_click="open()"` → `x-on-click="open()"`, which Alpine never binds — no error, the click just does nothing. Always use the splat form for colon/`@`/dot attrs. Detect regressions: `grep -rn "x_on_\|x_bind_" ui/ adapters/inbound/`.

⚠️ **Timing note (historical):** the `# type: ignore[arg-type]` is only valid where mypy `arg-type` is **enabled** for the module. `arg-type` is now enforced on all first-party trees (`core`/`services_bootstrap`/`adapters`/`ui`), so in `ui/` the ignore is always "used". During the rollout, adding it before a tree's per-module enable tripped `[unused-ignore]` (`warn_unused_ignores = true`), so each flip landed the ignores together with its `enable_error_code`. See `docs/patterns/ANY_USAGE_POLICY.md` § FastHTML boundary surfaces.

---

## Semantic HTML Foundation

HTMX enhances HTML — use semantic elements, not div soup:

```html
<!-- Structure elements -->
<header>  <nav aria-label="...">  <main>  <article>  <section>  <aside>  <footer>

<!-- Interactive elements (use these before reaching for custom JS) -->
<details><summary>Expandable</summary>Content</details>  <!-- No JS needed -->
<dialog>  <!-- Native modal -->

<!-- Tables (with proper semantics) -->
<table>
  <caption>User List</caption>
  <thead><tr><th scope="col">Name</th></tr></thead>
  <tbody hx-target="closest tr" hx-swap="outerHTML">
    <tr><td>Alice</td><td><button hx-delete="/users/1">Delete</button></td></tr>
  </tbody>
</table>
```

---

## Anti-Patterns

```html
<!-- ❌ Alpine fetching server data -->
<div x-data x-init="fetch('/api/users').then(...)">
<!-- ✅ Let HTMX handle server data -->
<div hx-get="/api/users" hx-trigger="load">

<!-- ❌ Both Alpine and HTMX controlling same visibility -->
<div x-show="visible" hx-get="/content">
<!-- ✅ Clear responsibility -->
<div x-data="{ loading: false }" @htmx:before-request="loading = true">
    <span x-show="loading">...</span>
    <div hx-get="/content" hx-trigger="load">...content...</div>
</div>

<!-- ❌ Unnecessary x-data nesting -->
<nav x-data="{ open: false }">
  <div x-data="{ dropdown: false }">  <!-- Can't easily access open -->
<!-- ✅ Single state container -->
<nav x-data="{ open: false, dropdown: false }">

<!-- ❌ Using GET for mutations -->
<form hx-get="/tasks/create">
<!-- ✅ POST for all mutations -->
<form hx-post="/tasks/create">

<!-- ❌ Alpine inline component (use skuel.js instead) -->
<script>Alpine.data('myWidget', ...)</script>  <!-- In template -->
<!-- ✅ Add to skuel.js -->

<!-- ❌ Re-processing swapped content from an htmx:load listener: HTMX already
     processes hx-* attributes on swap, and Alpine 3's MutationObserver
     initializes new x-data trees automatically. Calling htmx.process() (or
     Alpine.initTree()) from htmx:load re-fires every hx-trigger="load"
     request — every fragment fetched twice (PR #510) -->
<script>document.body.addEventListener('htmx:load', () => htmx.process(document.body))</script>
<!-- ✅ No glue code: let HTMX and Alpine handle their own initialization -->

<!-- ❌ Seeding x-data from a window global set by a sibling inline script
     in an HTMX fragment: htmx defers inline-script evaluation to the settle
     phase, but Alpine initializes the swapped tree first — the global is
     still undefined at init (broke PS "Start learning", 2026-07-05) -->
<script>window.SEED = {...}</script>
<div x-data="myWidget(window.SEED)">
<!-- ✅ Inline the JSON in the x-data expression (FastHTML: x-data=f"myWidget({json.dumps(seed)})") -->
<div x-data="myWidget({uid: 'ps.x', status: 'read'})">

<!-- ❌ x-for on a live element — children's loop-var expressions evaluate
     unscoped (ReferenceError) -->
<li x-for="dep in blocking" x-text="dep.title">
<!-- ✅ x-for lives on <template> -->
<template x-for="dep in blocking" :key="dep.uid"><li x-text="dep.title"></li></template>
```

---

## Key Files

| File | Purpose |
|------|---------|
| `/static/js/skuel.js` | All Alpine.data() components |
| `/static/vendor/alpinejs/alpine.3.14.8.min.js` | Alpine.js (self-hosted) |
| `/ui/layouts/base_page.py` | HTMX + Alpine included automatically |

## See Also

- `skuel-ui` — SKUEL-specific patterns using HTMX + Alpine (forms, navigation, sidebars)
- `ui-css` — CSS layer and Tailwind utilities for styling interactive components
- `chartjs` — Chart.js visualization via `chartVis()` Alpine component
- HTMX Docs: https://htmx.org/docs/
- Alpine.js Docs: https://alpinejs.dev/
