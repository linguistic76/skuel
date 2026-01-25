---
name: js-alpine
description: Expert guide to Alpine.js - lightweight reactive JavaScript for HTML. Use when building interactive UI components, managing client-side state, working with x-data/x-show/x-on directives, creating touch gestures, modals, dropdowns, form validation, or when the user mentions Alpine.js, reactivity, client-side state, or interactive components.
allowed-tools: Read, Grep, Glob
---

# Alpine.js: Lightweight Reactivity for HTML

## Core Philosophy

> "Alpine is a rugged, minimal tool for composing behavior directly in your markup."

Alpine.js fills the gap between HTMX (server-driven) and full frameworks (React/Vue). In SKUEL:

| Layer | Responsibility | Technology |
|-------|----------------|------------|
| **Server State** | Data persistence, business logic | FastHTML + HTMX |
| **Client State** | UI state, animations, gestures | Alpine.js |

**The Rule:** If it needs the server, use HTMX. If it's purely UI, use Alpine.

## Quick Start

### Installation (SKUEL - Local)

```python
# SKUEL uses vendored Alpine.js (no CDN dependency)
Script(src="/static/vendor/alpinejs/alpine.3.14.8.min.js", defer=True)
```

### Installation (CDN - for reference)

```html
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.14.8/dist/cdn.min.js"></script>
```

### Example 1: Toggle Visibility

```html
<div x-data="{ open: false }">
    <button x-on:click="open = !open">Toggle</button>
    <div x-show="open" x-transition>
        Content appears/disappears with animation
    </div>
</div>
```

### Example 2: Dropdown Menu

```html
<div x-data="{ expanded: false }" x-on:click.outside="expanded = false">
    <button x-on:click="expanded = !expanded">Menu</button>
    <ul x-show="expanded" x-transition.origin.top>
        <li><a href="#">Option 1</a></li>
        <li><a href="#">Option 2</a></li>
    </ul>
</div>
```

### Example 3: Form Validation

```html
<form x-data="{ email: '', valid: false }"
      x-on:input="valid = $el.checkValidity()">
    <input type="email" x-model="email" required placeholder="Email">
    <button type="submit" x-bind:disabled="!valid">Submit</button>
</form>
```

## Directive Quick Reference

| Directive | Purpose | Example |
|-----------|---------|---------|
| `x-data` | Initialize component state | `x-data="{ count: 0 }"` |
| `x-show` | Toggle CSS display | `x-show="open"` |
| `x-if` | Conditional rendering (DOM) | `<template x-if="show">` |
| `x-for` | Loop/repeat elements | `<template x-for="item in items">` |
| `x-on` / `@` | Event listeners | `x-on:click="handle()"` or `@click` |
| `x-model` | Two-way data binding | `x-model="name"` |
| `x-bind` / `:` | Dynamic attributes | `x-bind:class="active"` or `:class` |
| `x-text` | Set text content | `x-text="message"` |
| `x-html` | Set HTML content | `x-html="richContent"` |
| `x-transition` | Enter/leave animations | `x-transition` |
| `x-ref` | Element reference | `x-ref="input"` → `$refs.input` |
| `x-cloak` | Hide until initialized | `x-cloak` (with CSS) |
| `x-init` | Run on initialization | `x-init="fetchData()"` |
| `x-effect` | Reactive side effects | `x-effect="console.log(count)"` |
| `x-ignore` | Skip Alpine processing | `x-ignore` |

## Magic Properties

| Property | Purpose | Example |
|----------|---------|---------|
| `$el` | Current element | `$el.focus()` |
| `$refs` | Named element references | `$refs.input.value` |
| `$store` | Global state store | `$store.user.name` |
| `$watch` | Watch data changes | `$watch('count', val => ...)` |
| `$dispatch` | Dispatch custom event | `$dispatch('saved', { id: 1 })` |
| `$nextTick` | Run after DOM update | `$nextTick(() => ...)` |
| `$root` | Root component element | `$root.dataset.id` |
| `$data` | Component data object | `$data.count` |
| `$id` | Generate unique ID | `$id('input')` |

## When to Use Alpine vs HTMX

| Scenario | Use | Why |
|----------|-----|-----|
| Load data from server | **HTMX** | Server owns the data |
| Submit forms | **HTMX** | Persistence is server-side |
| Navigate between pages | **HTMX** | URL/history management |
| Toggle modal open/close | **Alpine** | Pure UI state |
| Animate elements | **Alpine** | Client-side transitions |
| Touch/swipe gestures | **Alpine** | Real-time input handling |
| Dropdown menus | **Alpine** | Instant responsiveness |
| Form validation feedback | **Alpine** | Immediate user feedback |
| Loading indicator during request | **Both** | Alpine shows, HTMX triggers |

## Common Patterns

### Modal Dialog

```html
<div x-data="{ open: false }">
    <button x-on:click="open = true">Open Modal</button>

    <div x-show="open"
         x-transition:enter="ease-out duration-300"
         x-transition:enter-start="opacity-0"
         x-transition:enter-end="opacity-100"
         x-transition:leave="ease-in duration-200"
         x-transition:leave-start="opacity-100"
         x-transition:leave-end="opacity-0"
         class="fixed inset-0 bg-black/50"
         x-on:click="open = false">

        <div class="modal-content" x-on:click.stop>
            <h2>Modal Title</h2>
            <p>Modal content here</p>
            <button x-on:click="open = false">Close</button>
        </div>
    </div>
</div>
```

### Collapsible Section

```html
<div x-data="{ expanded: false }">
    <button x-on:click="expanded = !expanded" class="w-full flex justify-between">
        <span>Section Title</span>
        <span x-text="expanded ? '▲' : '▼'"></span>
    </button>
    <div x-show="expanded" x-transition x-collapse>
        Section content that expands/collapses
    </div>
</div>
```

### Tabs

```html
<div x-data="{ tab: 'first' }">
    <nav>
        <button x-on:click="tab = 'first'" x-bind:class="{ 'active': tab === 'first' }">
            First
        </button>
        <button x-on:click="tab = 'second'" x-bind:class="{ 'active': tab === 'second' }">
            Second
        </button>
    </nav>
    <div x-show="tab === 'first'">First tab content</div>
    <div x-show="tab === 'second'">Second tab content</div>
</div>
```

### Touch Swipe Handler (SKUEL Pattern)

```html
<div x-data="swipeHandler()"
     x-on:touchstart="handleTouchStart($event)"
     x-on:touchend="handleTouchEnd($event)">
    <div x-show="currentIndex === 0" x-transition>Card 1</div>
    <div x-show="currentIndex === 1" x-transition>Card 2</div>
    <div x-show="currentIndex === 2" x-transition>Card 3</div>
</div>

<script>
document.addEventListener('alpine:init', () => {
    Alpine.data('swipeHandler', () => ({
        currentIndex: 0,
        touchStartX: 0,
        touchEndX: 0,
        totalCards: 3,

        handleTouchStart(event) {
            this.touchStartX = event.changedTouches[0].screenX;
        },

        handleTouchEnd(event) {
            this.touchEndX = event.changedTouches[0].screenX;
            const threshold = 50;

            if (this.touchEndX < this.touchStartX - threshold) {
                // Swipe left - next
                if (this.currentIndex < this.totalCards - 1) {
                    this.currentIndex++;
                }
            }
            if (this.touchEndX > this.touchStartX + threshold) {
                // Swipe right - previous
                if (this.currentIndex > 0) {
                    this.currentIndex--;
                }
            }
        }
    }))
})
</script>
```

### Loading State with HTMX

```html
<div x-data="{ loading: false }"
     x-on:htmx:before-request="loading = true"
     x-on:htmx:after-request="loading = false">

    <button hx-get="/api/data" hx-target="#results">
        <span x-show="!loading">Load Data</span>
        <span x-show="loading">Loading...</span>
    </button>

    <div id="results"></div>
</div>
```

## Event Modifiers

| Modifier | Effect | Example |
|----------|--------|---------|
| `.prevent` | preventDefault() | `@submit.prevent` |
| `.stop` | stopPropagation() | `@click.stop` |
| `.outside` | Click outside element | `@click.outside="close()"` |
| `.window` | Listen on window | `@keydown.window` |
| `.document` | Listen on document | `@scroll.document` |
| `.once` | Only fire once | `@click.once` |
| `.debounce` | Debounce handler | `@input.debounce.300ms` |
| `.throttle` | Throttle handler | `@scroll.throttle.100ms` |
| `.self` | Only if target is self | `@click.self` |
| `.camel` | camelCase event name | `@custom-event.camel` |

### Key Modifiers

```html
<input x-on:keydown.enter="submit()">
<input x-on:keydown.escape="cancel()">
<input x-on:keydown.arrow-up="previous()">
<input x-on:keydown.ctrl.s="save()">
```

## Transition Modifiers

```html
<!-- Basic -->
<div x-show="open" x-transition>

<!-- Custom timing -->
<div x-show="open"
     x-transition:enter="transition ease-out duration-300"
     x-transition:enter-start="opacity-0 scale-95"
     x-transition:enter-end="opacity-100 scale-100"
     x-transition:leave="transition ease-in duration-200"
     x-transition:leave-start="opacity-100 scale-100"
     x-transition:leave-end="opacity-0 scale-95">

<!-- Origin modifiers -->
<div x-show="open" x-transition.origin.top.left>
<div x-show="open" x-transition.scale.80>
<div x-show="open" x-transition.duration.500ms>
```

## SKUEL Component Architecture

SKUEL centralizes ALL Alpine.data() components in `/static/js/skuel.js`. This single file contains all reusable components:

| Component | Purpose | Key State |
|-----------|---------|-----------|
| `searchSidebar()` | Sidebar toggle + filter visibility | `collapsed`, `entityType` |
| `searchFilters()` | Horizontal filter bar | `entityType`, `showAdvanced` |
| `calendarPage()` | Combined modal + drag-drop | `open`, `datetime`, `draggedItemId` |
| `calendarModal()` | Standalone quick-add modal | `open`, `datetime` |
| `calendarDrag()` | Standalone drag-drop | `draggedItemId` |
| `timelineViewer(src)` | Timeline loading + filtering | `loading`, `source`, `stats` |
| `swipeHandler(totalCards)` | Touch swipe for carousels | `swipeIndex` |
| `collapsible(initiallyOpen)` | Expand/collapse sections | `expanded` |
| `loadingButton()` | Loading state during requests | `loading` |
| `chartVis(url, type)` | Chart.js visualization | `chart`, `loading`, `error` |
| `timelineVis(url)` | Vis.js Timeline | `timeline`, `loading`, `error` |
| `ganttVis(url)` | Frappe Gantt chart | `gantt`, `loading`, `viewMode` |

**Usage in FastHTML:**
```python
# Reference centralized component
Div(
    content,
    **{"x-data": "searchSidebar()"},  # Component from skuel.js
)
```

**Adding new components:** Define in `skuel.js` inside the `alpine:init` event listener.

## Visualization Components

SKUEL includes Alpine components for Chart.js, Vis.js Timeline, and Frappe Gantt:

### Chart.js Integration (`chartVis`)

```python
from components.visualization_components import create_chart_view

# Simple usage - creates full Alpine component wrapper
chart = create_chart_view(
    data_url="/api/visualizations/completion",
    chart_type="line",
    title="Completion Rate",
)
```

**Manual usage in FastHTML:**
```python
Div(
    Canvas(**{"x-ref": "canvas"}),
    **{"x-data": "chartVis('/api/visualizations/completion', 'line')"},
)
```

**Component methods:**
- `loadChart(url, type)` - Load chart from API
- `refresh(newUrl)` - Reload with optional new URL
- `destroy()` - Clean up chart instance

### Timeline Integration (`timelineVis`)

```python
from components.visualization_components import create_timeline_view

timeline = create_timeline_view(
    data_url="/api/visualizations/timeline",
    title="Schedule Timeline",
)
```

**Component methods:**
- `refresh(newUrl)` - Reload timeline
- `fit()` - Fit all items in view
- `zoomIn()` / `zoomOut()` - Zoom controls

### Gantt Integration (`ganttVis`)

```python
from components.visualization_components import create_gantt_view

gantt = create_gantt_view(
    data_url="/api/visualizations/gantt/tasks",
    title="Project Timeline",
)
```

**Component methods:**
- `refresh(newUrl)` - Reload Gantt
- `setViewMode(mode)` - 'Day', 'Week', 'Month'

**See:** Chart.js Skill for detailed visualization patterns.

## Best Practices

### 1. Keep State Close to Usage

```html
<!-- GOOD: State scoped to component -->
<div x-data="{ open: false }">
    <button x-on:click="open = true">Open</button>
    <div x-show="open">Content</div>
</div>

<!-- AVOID: Global state when local suffices -->
<script>Alpine.store('modal', { open: false })</script>
```

### 2. Use x-show for Frequent Toggles, x-if for Rare

```html
<!-- x-show: Element stays in DOM, just hidden -->
<div x-show="tab === 'settings'">Fast toggle</div>

<!-- x-if: Element removed/added to DOM -->
<template x-if="showOnce">
    <div>Rarely shown, removed when hidden</div>
</template>
```

### 3. Prefer x-on Shorthand in Templates

```html
<!-- Shorthand is cleaner -->
<button @click="save()">Save</button>
<input @input.debounce="search($event.target.value)">

<!-- Full form for complex handlers -->
<div x-on:custom-event.window="handleCustom($event.detail)">
```

### 4. Extract Reusable Components with Alpine.data()

```javascript
// In a <script> tag or JS file
document.addEventListener('alpine:init', () => {
    Alpine.data('dropdown', () => ({
        open: false,
        toggle() { this.open = !this.open },
        close() { this.open = false }
    }))
})
```

```html
<!-- Usage -->
<div x-data="dropdown()" x-on:click.outside="close()">
    <button @click="toggle()">Menu</button>
    <ul x-show="open">...</ul>
</div>
```

### 5. Use x-cloak to Prevent Flash of Unstyled Content

```css
[x-cloak] { display: none !important; }
```

```html
<div x-data="{ ready: false }" x-init="ready = true" x-cloak>
    <!-- Won't flash before Alpine initializes -->
</div>
```

## Anti-Patterns

### 1. Don't Use Alpine for Server Data

```html
<!-- WRONG: Fetching in Alpine -->
<div x-data x-init="fetch('/api/users').then(...)">

<!-- RIGHT: Let HTMX handle server data -->
<div hx-get="/api/users" hx-trigger="load">
```

### 2. Don't Nest x-data Unnecessarily

```html
<!-- WRONG: Redundant nesting -->
<div x-data="{ outer: true }">
    <div x-data="{ inner: true }">
        <!-- Can't access outer from here easily -->
    </div>
</div>

<!-- RIGHT: Single state container -->
<div x-data="{ outer: true, inner: true }">
    <div><!-- Access both --></div>
</div>
```

### 3. Don't Mix Alpine and HTMX for Same Concern

```html
<!-- WRONG: Both trying to handle visibility -->
<div x-show="visible" hx-get="/content" hx-swap="innerHTML">

<!-- RIGHT: Clear responsibility -->
<div x-data="{ loading: false }"
     @htmx:before-request="loading = true"
     @htmx:after-request="loading = false">
    <span x-show="loading">Loading...</span>
    <div hx-get="/content" hx-trigger="load">
        <!-- Content loaded by HTMX -->
    </div>
</div>
```

## FastHTML Integration

Alpine attributes are passed as `**kwargs` in FastHTML:

```python
from monsterui.franken import Div, Button

def toggle_component():
    return Div(
        Button("Toggle", **{"x-on:click": "open = !open"}),
        Div("Content", **{"x-show": "open", "x-transition": ""}),
        **{"x-data": "{ open: false }"}
    )
```

**See:** [fasthtml-patterns.md](fasthtml-patterns.md) for complete integration patterns.

## Additional Resources

- [directives-reference.md](directives-reference.md) - Complete directive documentation
- [htmx-integration.md](htmx-integration.md) - Alpine + HTMX collaboration patterns
- [fasthtml-patterns.md](fasthtml-patterns.md) - Python/FastHTML integration

## Related Skills

- **[html-htmx](../html-htmx/SKILL.md)** - Server communication (Alpine handles client-side UI state)
- **[fasthtml](../fasthtml/SKILL.md)** - FastHTML components using Alpine directives
- **[chartjs](../chartjs/SKILL.md)** - Chart.js visualization using Alpine components
- **[monsterui](../monsterui/SKILL.md)** - Components styled with Alpine state

## Foundation

- **[html-htmx](../html-htmx/SKILL.md)** - Understanding HTMX for server/client boundary

## See Also

- `/static/js/skuel.js` - All Alpine.data() components
- `/components/calendar_components.py`, `/components/search_components.py` - Component examples
- Alpine.js Docs: https://alpinejs.dev/
