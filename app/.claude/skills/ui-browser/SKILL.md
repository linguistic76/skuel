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

## HTMX Common Patterns

### Active Search

```html
<input type="search" name="q"
       hx-get="/search"
       hx-trigger="input changed delay:300ms, search"
       hx-target="#results"
       hx-indicator=".htmx-indicator"
       placeholder="Search...">
<span class="htmx-indicator loading loading-spinner loading-sm"></span>
<div id="results"></div>
```

### Infinite Scroll

```html
<div id="items">
  <!-- Items here -->
  <div hx-get="/items?page=2"
       hx-trigger="revealed"
       hx-swap="outerHTML">
    Loading more...
  </div>
</div>
```

### Click to Edit

```html
<!-- View mode -->
<div hx-get="/users/1/edit" hx-trigger="click" hx-swap="outerHTML">
  Click to edit: John Doe
</div>
<!-- Server returns edit form; form submits back with hx-put, returns view mode -->
```

### Form Submission (SKUEL Pattern)

```python
Form(
    # ... form controls ...
    Button("Create Task", type="submit", cls="btn btn-primary"),
    hx_post="/tasks/quick-add",
    hx_target="#task-list",
    hx_swap="beforeend",
    hx_on="htmx:afterRequest: this.reset()",  # Clear form on success
)
```

### HTMX Response Headers (Server → Browser)

```python
# Redirect after action
response.headers["HX-Redirect"] = "/dashboard"

# Trigger client event (Alpine can listen)
response.headers["HX-Trigger"] = "taskCreated"
# or with data: '{"taskCreated": {"id": "task_abc"}}'

# Full page refresh
response.headers["HX-Refresh"] = "true"

# Update browser URL
response.headers["HX-Push-Url"] = "/tasks"
```

### Loading States

```html
<!-- Indicator (shows during request) -->
<button hx-get="/slow-data" hx-indicator="#spinner">Load</button>
<span id="spinner" class="htmx-indicator loading loading-spinner loading-sm"></span>

<!-- Disable element during request -->
<button hx-post="/save" hx-disabled-elt="this">Save</button>

<!-- Alpine + HTMX loading state -->
<div x-data="{ loading: false }"
     @htmx:before-request="loading = true"
     @htmx:after-request="loading = false">
  <button hx-get="/data">
    <span x-show="!loading">Load</span>
    <span x-show="loading" class="loading loading-spinner loading-xs"></span>
  </button>
</div>
```

### Accessibility with HTMX

```html
<!-- Announce updates to screen readers -->
<div aria-live="polite" id="results">
  <!-- HTMX updates here get announced -->
</div>

<!-- Focus first input after swap -->
<form hx-post="/step"
      hx-on:htmx:after-swap="this.querySelector('input')?.focus()">
```

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
| `x-cloak` | Hide until Alpine initializes | Add CSS: `[x-cloak] { display: none }` |
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

## Alpine.js Common Patterns

### Modal

```html
<div x-data="{ open: false }">
  <button @click="open = true" class="btn btn-primary">Open</button>

  <div x-show="open"
       x-transition:enter="transition ease-out duration-200"
       x-transition:enter-start="opacity-0"
       x-transition:enter-end="opacity-100"
       x-transition:leave="transition ease-in duration-150"
       x-transition:leave-start="opacity-100"
       x-transition:leave-end="opacity-0"
       class="fixed inset-0 bg-black/50 z-50"
       @click="open = false">
    <div class="modal-box" @click.stop>
      <h3 class="font-bold text-lg">Modal</h3>
      <div class="modal-action">
        <button @click="open = false" class="btn btn-ghost">Close</button>
      </div>
    </div>
  </div>
</div>
```

### Collapsible Section

```html
<div x-data="{ expanded: false }">
  <button @click="expanded = !expanded" class="flex justify-between w-full">
    <span>Section Title</span>
    <span x-text="expanded ? '▲' : '▼'"></span>
  </button>
  <div x-show="expanded" x-transition>
    Collapsible content
  </div>
</div>
```

### Tabs

```html
<div x-data="{ tab: 'first' }">
  <div class="tabs tabs-boxed">
    <button @click="tab = 'first'" :class="{ 'tab-active': tab === 'first' }" class="tab">First</button>
    <button @click="tab = 'second'" :class="{ 'tab-active': tab === 'second' }" class="tab">Second</button>
  </div>
  <div x-show="tab === 'first'">First content</div>
  <div x-show="tab === 'second'">Second content</div>
</div>
```

### Dropdown with Click-Outside

```html
<div x-data="{ open: false }" @click.outside="open = false" class="relative">
  <button @click="open = !open" class="btn btn-ghost btn-circle">👤</button>
  <div x-show="open" x-transition.origin.top.right
       class="absolute right-0 mt-2 w-48 bg-base-100 rounded-lg shadow-lg z-50">
    <a href="/profile" class="block px-4 py-2 hover:bg-base-200">Profile</a>
    <a href="/logout" class="block px-4 py-2 hover:bg-base-200">Sign out</a>
  </div>
</div>
```

### Conditional Fields (show/hide based on selection)

```html
<div x-data="{ taskType: 'once' }">
  <select x-model="taskType" name="task_type" class="select select-bordered w-full">
    <option value="once">One-time</option>
    <option value="recurring">Recurring</option>
  </select>

  <!-- Only show for recurring -->
  <div x-show="taskType === 'recurring'" x-transition>
    <select name="recurrence_pattern" class="select select-bordered w-full">
      <option value="daily">Daily</option>
      <option value="weekly">Weekly</option>
    </select>
  </div>
</div>
```

### Touch Swipe Handler

```javascript
Alpine.data('swipeHandler', (totalCards) => ({
    currentIndex: 0,
    touchStartX: 0,
    handleTouchStart(event) {
        this.touchStartX = event.changedTouches[0].screenX;
    },
    handleTouchEnd(event) {
        const delta = event.changedTouches[0].screenX - this.touchStartX;
        if (delta < -50 && this.currentIndex < totalCards - 1) this.currentIndex++;
        if (delta > 50 && this.currentIndex > 0) this.currentIndex--;
    }
}));
```

### Event Modifiers

| Modifier | Effect |
|----------|--------|
| `@click.prevent` | preventDefault() |
| `@click.stop` | stopPropagation() |
| `@click.outside` | Only fires outside element |
| `@keydown.enter` | Enter key only |
| `@keydown.escape` | Escape key only |
| `@input.debounce.300ms` | Debounce 300ms |
| `@scroll.throttle.100ms` | Throttle 100ms |

### Transition Modifiers

```html
<!-- Basic -->
<div x-show="open" x-transition>

<!-- Custom -->
<div x-show="open"
     x-transition:enter="transition ease-out duration-300"
     x-transition:enter-start="opacity-0 scale-95"
     x-transition:enter-end="opacity-100 scale-100"
     x-transition:leave="transition ease-in duration-200"
     x-transition:leave-start="opacity-100 scale-100"
     x-transition:leave-end="opacity-0 scale-95">

<!-- Shorthand -->
<div x-show="open" x-transition.origin.top.right>
<div x-show="open" x-transition.scale.95>
<div x-show="open" x-transition.duration.300ms>
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
