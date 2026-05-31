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
| `$el` | Current element |
| `$refs` | Named element references |
| `$store` | Global Alpine store |
| `$watch` | Watch data changes |
| `$dispatch` | Dispatch custom event |
| `$nextTick` | Run after DOM update |

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
| `navbar()` | Mobile menu + profile dropdown | `mobileMenuOpen`, `profileMenuOpen` |
| `searchSidebar()` | Search sidebar toggle | `collapsed`, `entityType` |
| `searchFilters()` | Filter bar | `entityType`, `showAdvanced` |
| `calendarPage()` | Modal + drag-drop | `open`, `datetime`, `draggedItemId` |
| `timelineViewer(src)` | Timeline filtering | `loading`, `source`, `stats` |
| `swipeHandler(total)` | Touch swipe | `swipeIndex` |
| `collapsible(initial)` | Expand/collapse | `expanded` |
| `loadingButton()` | Loading state | `loading` |
| `chartVis(url, type)` | Chart.js | `chart`, `loading`, `error` |
| `timelineVis(url)` | Vis.js Timeline | `timeline`, `loading`, `error` |
| `ganttVis(url)` | Frappe Gantt | `gantt`, `loading`, `viewMode` |
| `collapsibleSidebar(key)` | Sidebar collapse + localStorage | reads `Alpine.store(key)` |
| `relationshipGraph(uid, type)` | Vis.js lateral relationships | `network`, `loading` |
| `exploreGraph(mode, uid, type)` | Explore sidebar Vis.js graph | `network`, `filter`, `expanded` |
| `offlineIndicator` | PWA offline status banner | `isOffline` |

**Usage in FastHTML:**
```python
Div(
    content,
    **{"x-data": "searchSidebar()"},  # Reference centralized component
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

**Why it matters for types:** a `**dict[str, str]` splat into a **MonsterUI component** (`Button`, `Input`, `Select`, …) trips mypy `arg-type` — the dict's `str` values spill onto the component's typed keyword slots (`disabled: bool`, `size: Size | None`). The fix follows the table:

- **Reducible attrs (plain-hyphen + HTMX `hx-on::`) → use the underscore kwarg.** No splat, no suppression. (e.g. `Button("Back", hx_get="/tasks", hx_target="body")`, *not* `**{"hx-get": …}`; `Form(..., hx_on__after_request=expr)`, *not* `**{"hx-on::after-request": expr}`.)
- **Irreducible Alpine attrs (colon / at / dot) → keep the splat + a surgical ignore:** `**{"x-on:click": expr},  # type: ignore[arg-type]  # fasthtml dynamic-attr splat`.

⚠️ **Timing caveat:** that `# type: ignore[arg-type]` is only valid where mypy `arg-type` is **enabled** for the module (per-module `enable_error_code` in `pyproject.toml`). On a tree where `arg-type` is still globally disabled, the ignore is flagged `[unused-ignore]` (`warn_unused_ignores = true`) — so add it **together with** the per-module enable, never before. See `docs/patterns/ANY_USAGE_POLICY.md` § FastHTML boundary surfaces.

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
- `ui-css` — MonsterUI (FrankenUI + Tailwind) for styling interactive components
- `chartjs` — Chart.js visualization via `chartVis()` Alpine component
- HTMX Docs: https://htmx.org/docs/
- Alpine.js Docs: https://alpinejs.dev/
