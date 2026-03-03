---
title: HTMX Version Standardization Guide
updated: 2026-01-15
status: current
category: guides
tags:
- htmx
- fasthtml
- navigation
- layout
- critical
related:
- UI_COMPONENT_PATTERNS.md
- ALPINE_JS_ARCHITECTURE.md
- FASTHTML_ROUTE_REGISTRATION.md
related_skills:
- html-htmx
---

# HTMX Version Standardization Guide

*Last updated: 2026-01-15*

## Overview

**Skill:** [@html-htmx](../../.claude/skills/html-htmx/SKILL.md)

SKUEL standardizes on **HTMX 1.9.10** across all pages. This guide explains why version consistency matters and how to implement it correctly.

## The Problem

FastHTML's `fast_app()` includes HTMX 2.0.7 by default. When a route returns a `Div` (or any non-Html element), FastHTML automatically wraps it with default headers containing HTMX 2.0.7.

This creates a **version mismatch** when some pages explicitly use HTMX 1.9.x while others get the default 2.0.7.

### Symptoms of Version Mismatch

If you observe these behaviors, suspect HTMX version inconsistency:

| Symptom | Description |
|---------|-------------|
| **Page reloads but stays** | Clicking navbar links reloads the page but URL doesn't change |
| **Multiple clicks required** | Navigation works after 2-3 clicks |
| **Inconsistent behavior** | Some pages navigate correctly, others don't |
| **No JS errors** | Browser console shows no errors |

### Root Cause

```
Page A (explicit Html)     Page B (returns Div)
├── HTMX 1.9.10            ├── HTMX 2.0.7 (FastHTML default)
├── Navigation works       ├── Navigation broken
└── Explicit headers       └── Auto-wrapped headers
```

When navigating from Page A to Page B (or vice versa), the different HTMX versions handle link clicks differently, causing navigation failures.

## The Solution

**All pages must return complete `Html(...)` documents with explicit headers.**

### Correct Pattern

```python
from fasthtml.common import Html, Head, Body, Meta, Link, Script, Title

def my_page(content, title="My Page"):
    return Html(
        Head(
            Meta(charset="UTF-8"),
            Meta(name="viewport", content="width=device-width, initial-scale=1.0"),
            Title(f"{title} - SKUEL"),
            # DaisyUI CSS
            Link(
                href="https://cdn.jsdelivr.net/npm/daisyui@4.4.19/dist/full.min.css",
                rel="stylesheet",
                type="text/css",
            ),
            # Tailwind CSS
            Script(src="https://cdn.tailwindcss.com"),
            # HTMX - MUST be 1.9.10 for navigation consistency
            Script(src="https://unpkg.com/htmx.org@1.9.10"),
            # Alpine.js - self-hosted
            Script(src="/static/vendor/alpinejs/alpine.3.14.8.min.js", defer=True),
            # SKUEL custom assets
            Link(rel="stylesheet", href="/static/css/output.css"),
            Link(rel="stylesheet", href="/static/css/skuel.css"),
            Script(src="/static/js/skuel.js"),
        ),
        Body(
            content,
            cls="bg-base-200",
        ),
        **{"data-theme": "light"},
    )
```

### Incorrect Pattern

```python
# BAD: Returns Div - FastHTML wraps with HTMX 2.0.7
def my_page(content):
    return Div(
        navbar,
        content,
        cls="min-h-screen",
    )  # Navigation WILL break!
```

## Activity Domain Pattern

All Activity Domains (Tasks, Goals, Habits, Events, Choices, Principles) use the shared `create_activity_page()` function:

```python
from ui.layouts.activity_layout import create_activity_page

def create_tasks_page(content, request=None, **kwargs):
    return create_activity_page(
        content=content,
        domain="tasks",
        request=request,
        **kwargs,
    )
```

### Key Files

| File | Purpose |
|------|---------|
| `/ui/layouts/activity_layout.py` | Shared layout returning `Html` document |
| `/ui/tasks/layout.py` | Tasks - delegates to `create_activity_page()` |
| `/ui/goals/layout.py` | Goals - delegates to `create_activity_page()` |
| `/ui/habits/layout.py` | Habits - delegates to `create_activity_page()` |
| `/ui/events/layout.py` | Events - delegates to `create_activity_page()` |
| `/ui/patterns/entity_dashboard.py` | `render_entity_dashboard()` returns `Html` |

## Version Matrix

SKUEL uses these specific versions for stability:

| Component | Version | Source | Notes |
|-----------|---------|--------|-------|
| **HTMX** | 1.9.10 | CDN (unpkg.com) | Critical for navigation |
| **Alpine.js** | 3.14.8 | Self-hosted | `/static/vendor/alpinejs/` |
| **DaisyUI** | 4.4.19 | CDN | Component library |
| **Tailwind** | Latest | CDN | Utility classes |

## Why HTMX 1.9.10?

SKUEL chose HTMX 1.9.10 over 2.0.x for these reasons:

1. **Stability** - 1.9.x is mature and well-tested
2. **Existing code** - Working pages (Search, Askesis, Calendar) already used 1.9.x
3. **Breaking changes** - HTMX 2.0 introduced behavioral changes
4. **Consistency** - Single version eliminates mismatch issues

## SKUEL Pages

Pages using `daisy_headers()` from `ui.theme` get standardized headers including HTMX 1.9.10:

```python
from fasthtml.common import fast_app
from ui.theme import daisy_headers
from ui.cards import Card, CardBody

app, rt = fast_app(hdrs=daisy_headers())

@rt("/")
def homepage():
    return Card(CardBody(...))  # daisy_headers() handles HTMX
```

**Key:** All SKUEL pages use `daisy_headers()` for consistent versioning across the application.

## Debugging Navigation Issues

### Step 1: Check Page Return Type

```python
# In your route handler, verify return type
@rt("/my-page")
async def my_page(request):
    result = build_page_content(...)
    print(f"Return type: {type(result)}")  # Should be Html, not Div
    return result
```

### Step 2: Inspect Page Source

In browser, view page source and search for `htmx.org`:
- Should find: `htmx.org@1.9.10`
- Problem if: `htmx.org@2.0` or no HTMX script

### Step 3: Check Layout Function

Verify your layout function returns `Html`:

```python
# Check the return type annotation
def create_my_page(...) -> "FT":  # FT could be Html or Div
    return Html(...)  # Must be Html, not Div
```

### Step 4: Trace the Call Chain

```
Route handler
    └── Layout function (should return Html)
        └── create_activity_page() or similar
            └── Html(Head(...), Body(...))
```

## Migration Checklist

When fixing a page with navigation issues:

- [ ] Identify the route handler
- [ ] Find what layout function it uses
- [ ] Verify layout returns `Html` (not `Div`)
- [ ] Check headers include HTMX 1.9.10
- [ ] Test navigation from that page
- [ ] Test navigation TO that page from other pages

## Common Mistakes

### Mistake 1: Custom Layout Returning Div

```python
# WRONG
class MyLayout:
    def render(self, content):
        return Div(navbar, content)  # Returns Div!

# RIGHT
class MyLayout:
    def render(self, content):
        return Html(
            Head(...),
            Body(navbar, content),
        )
```

### Mistake 2: Forgetting HTMX Script

```python
# WRONG - missing HTMX
Head(
    Script(src="/static/vendor/alpinejs/alpine.3.14.8.min.js"),
    # No HTMX script!
)

# RIGHT
Head(
    Script(src="https://unpkg.com/htmx.org@1.9.10"),
    Script(src="/static/vendor/alpinejs/alpine.3.14.8.min.js"),
)
```

### Mistake 3: Wrong HTMX Version

```python
# WRONG - using 2.0.x
Script(src="https://unpkg.com/htmx.org@2.0.0")

# RIGHT - using 1.9.10
Script(src="https://unpkg.com/htmx.org@1.9.10")
```

### Mistake 4: Not Using Shared Layout

```python
# WRONG - custom implementation
def create_tasks_page(content):
    return Html(...)  # Duplicates activity_layout.py

# RIGHT - delegate to shared layout
from ui.layouts.activity_layout import create_activity_page

def create_tasks_page(content, request=None):
    return create_activity_page(content, domain="tasks", request=request)
```

## Historical Context

### January 2026 Fix

The navbar navigation bug was traced to HTMX version mismatch:

1. **Working pages** (Search, Askesis, Calendar) created their own `Html` documents with HTMX 1.9.x
2. **Broken pages** (Activity domains) returned `Div` and got HTMX 2.0.7 from FastHTML defaults
3. **Fix:** Changed all Activity Domain layouts to return `Html` with explicit HTMX 1.9.10

**Files Modified:**
- `ui/layouts/activity_layout.py` - Returns `Html` instead of `Div`
- `ui/tasks/layout.py` - Delegates to `create_activity_page()`
- `ui/patterns/entity_dashboard.py` - `render_entity_dashboard()` returns `Html`
- `ui/layouts/navbar.py` - Added `hx-boost="false"` as defensive measure

## See Also

- `/docs/patterns/UI_COMPONENT_PATTERNS.md` - Page Layout Architecture section
- `/docs/architecture/ALPINE_JS_ARCHITECTURE.md` - Alpine.js + HTMX coordination
- `/docs/patterns/FASTHTML_ROUTE_REGISTRATION.md` - Route patterns
- `/.claude/plans/navbar-htmx-boost-fix.md` - Original investigation notes

---

**Last Updated:** January 15, 2026
**Maintained By:** SKUEL Core Team
