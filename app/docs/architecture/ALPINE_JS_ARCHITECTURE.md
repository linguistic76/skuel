---
related_skills:
- js-alpine
---
# Alpine.js Architecture
*Last updated: 2026-01-15*
## Related Skills

For implementation guidance, see:
- [@js-alpine](../../.claude/skills/js-alpine/SKILL.md)


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

# Update references in:
# - components/timeline_components.py
# - components/search_components.py
# - adapters/inbound/askesis_ui.py
# - adapters/inbound/calendar_routes.py
# - This file + CLAUDE.md
```

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

### The Solution: Explicit Html Documents

All pages must return complete `Html(...)` documents with explicit headers including HTMX 1.9.10:

```python
from fasthtml.common import Html, Head, Body, Script

def my_page():
    return Html(
        Head(
            # HTMX - MUST be 1.9.10 for consistency
            Script(src="https://unpkg.com/htmx.org@1.9.10"),
            # Alpine.js - self-hosted
            Script(src="/static/vendor/alpinejs/alpine.3.14.8.min.js", defer=True),
            # ... other headers
        ),
        Body(content),
    )
```

### Version Matrix

| Component | Version | Source |
|-----------|---------|--------|
| HTMX | 1.9.10 | CDN (unpkg.com) |
| Alpine.js | 3.14.8 | Self-hosted (`/static/vendor/`) |
| DaisyUI | 4.4.19 | CDN |
| Tailwind | Latest | CDN |

**See:** `/docs/patterns/UI_COMPONENT_PATTERNS.md#page-layout-architecture-critical` for detailed patterns.

## File Structure

```
static/js/
└── skuel.js          # Central Alpine.data() component definitions (~400 lines)

components/
├── calendar_components.py   # FastHTML + Alpine directives
├── search_components.py     # FastHTML + Alpine directives
├── timeline_components.py   # FastHTML + Alpine directives
└── ...

.claude/skills/js-alpine/    # Claude Code skill documentation
├── SKILL.md
├── directives-reference.md
├── fasthtml-patterns.md
└── htmx-integration.md
```

## Available Components

All components are defined in `/static/js/skuel.js` using `Alpine.data()`:

### searchSidebar()

Collapsible sidebar with entity-type-aware filter visibility.

**State:**
- `collapsed`: boolean - Sidebar collapsed state (persisted in localStorage)
- `isMobile`: boolean - Viewport width detection
- `entityType`: string - Current entity type for filter filtering

**Methods:**
- `toggle()` - Toggle collapsed state
- `isFilterVisible(group)` - Check if filter group should show
- `setEntityType(type)` - Update entity type

### calendarPage()

Combined modal and drag-drop functionality for calendar views.

**State:**
- `open`: boolean - Modal visibility
- `datetime`: string - ISO datetime for quick-add
- `draggedItemId`: string|null - Currently dragged item

**Methods:**
- `openQuickAdd(defaultDate, defaultHour)` - Open modal with date/time
- `closeQuickAdd()` - Close modal
- `handleDragStart(event, itemId)` - Start drag operation
- `handleDragOver(event)` - Allow drop
- `handleDrop(event, newDateTime)` - Complete reschedule

### calendarModal()

Standalone modal component (when drag-drop not needed).

### calendarDrag()

Standalone drag-drop component (when modal not needed).

### timelineViewer(src)

Markwhen timeline integration with filtering and URL history.

**State:**
- `loading`: boolean - Loading state
- `source`: string - Timeline source URL
- `stats`: object - Timeline statistics
- `timeline`: object - Markwhen instance

**Methods:**
- `loadTimeline(sourceUrl)` - Fetch and render timeline
- `updateTimeline()` - Rebuild source URL from filters

### swipeHandler(totalCards)

Touch gesture handling for card carousels.

**State:**
- `swipeIndex`: number - Current card index
- `touchStartX`: number - Touch start position
- `touchEndX`: number - Touch end position
- `totalCards`: number - Total card count

**Methods:**
- `handleTouchStart(event)` - Record touch start
- `handleTouchEnd(event)` - Process swipe gesture

### collapsible(initiallyOpen)

Expand/collapse sections with smooth transitions.

**State:**
- `expanded`: boolean - Current state

**Methods:**
- `toggle()` - Toggle expanded state

### loadingButton()

Loading state during HTMX requests.

**State:**
- `loading`: boolean - Loading state

## FastHTML Integration Pattern

Alpine directives are passed as `**kwargs` in FastHTML components:

```python
from fasthtml.common import Div
from core.ui.daisy_components import Button

def my_component() -> Div:
    return Div(
        Button(
            "Toggle",
            **{"x-on:click": "toggle()"},
        ),
        Div(
            "Content",
            **{
                "x-show": "!collapsed",
                "x-transition": "",
            },
        ),
        cls="my-component",
        **{"x-data": "searchSidebar()"},
    )
```

**Key patterns:**
- Use `**{"x-directive": "value"}` syntax for Alpine attributes
- Reference centralized components: `x-data="componentName()"`
- Combine multiple directives with multiple `**{}` spreads

## Loading Alpine.js

### SKUEL Pages (Standard)

SKUEL's `daisy_headers()` automatically includes Alpine.js (self-hosted for stability):

```python
from fasthtml.common import fast_app
from core.ui.theme import daisy_headers

app, rt = fast_app(
    hdrs=daisy_headers(),  # Includes Alpine.js 3.14.8
)
```

### Standalone Pages (Timeline, Search, etc.)

For pages with custom headers, load Alpine.js from the vendored local file:

```python
from fasthtml.common import Html, Head, Script

def standalone_page():
    return Html(
        Head(
            Script(
                src="/static/vendor/alpinejs/alpine.3.14.8.min.js",
                defer=True
            ),
        ),
        Body(
            # Content...
            Script(src="/static/js/skuel.js"),
            **{"x-data": "timelineViewer('/api/timeline')"},
        ),
    )
```

## Common Directives

| Directive | Purpose | Example |
|-----------|---------|---------|
| `x-data` | Initialize component | `x-data="searchSidebar()"` |
| `x-show` | Toggle visibility (CSS) | `x-show="!collapsed"` |
| `x-if` | Conditional render (DOM) | `<template x-if="show">` |
| `x-on:event` | Event handler | `x-on:click="toggle()"` |
| `x-model` | Two-way binding | `x-model="datetime"` |
| `x-bind:attr` | Dynamic attribute | `x-bind:class="'base ' + modifier"` |
| `x-ref` | Element reference | `x-ref="container"` |
| `x-transition` | CSS transitions | `x-transition` |

## Adding New Components

1. **Define in skuel.js:**

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

Alpine handles UI state, HTMX handles server communication:

```python
Div(
    Button(
        Span("Save", **{"x-show": "!loading"}),
        Span("Saving...", **{"x-show": "loading"}),
        hx_post="/api/save",
        hx_target="#result",
        **{"x-bind:disabled": "loading"},
    ),
    **{
        "x-data": "loadingButton()",
        "x-on:htmx:before-request": "loading = true",
        "x-on:htmx:after-request": "loading = false",
    },
)
```

## Migration History

**January 15, 2026:** Self-hosted Alpine.js, removed CDN dependency.
- Downloaded Alpine.js 3.14.8 to `/static/vendor/alpinejs/`
- Updated 4 standalone page components to use local file
- Rationale: Version stability, offline capability, explicit upgrades

**January 2026:** Consolidated all JavaScript into centralized Alpine.js architecture.

**Migrated files:**
- `search_sidebar.js` (189 lines) → `searchSidebar()` in skuel.js
- `calendar.js` (108 lines) → `calendarPage()` in skuel.js
- `timeline_viewer.js` (147 lines) → `timelineViewer()` in skuel.js

**Deleted files:**
- `journals_audio_upload.js` (323 lines) - Legacy code

**Result:** Single source of truth for all JavaScript behavior, no external dependencies.

## Related Documentation

- **CLAUDE.md:** Quick reference (Alpine.js Architecture section)
- **Skills:** `/.claude/skills/js-alpine/` - Detailed skill documentation
- **FastHTML:** `/docs/fasthtml-llms.txt` - FastHTML patterns
