---
title: HTMX Accessibility Patterns
updated: '2026-02-26'
category: patterns
related_skills:
- html-htmx
- accessibility-guide
related_docs: []
---
# HTMX Accessibility Patterns

**WCAG Level:** AA

---

## Overview

SKUEL provides automatic screen reader announcements for HTMX operations through:

1. **`data-announce` / `data-announce-loading` HTML attributes** - Added to HTMX elements
2. **`static/js/skuel.js`** - Reads attributes on HTMX events, writes to live region
3. **`#live-region`** - ARIA live region in `base_page.py` for announcements

In most cases, no extra code is needed — the auto-detection system infers announcements from URL path patterns.

---

## Auto-Detection (Zero Extra Code)

The JavaScript listener reads the HTMX request URL and auto-detects the operation type:

| URL Pattern | Loading Announcement | Success Announcement |
|-------------|---------------------|---------------------|
| `/create` | "Creating..." | "Created successfully" |
| `/update`, `/edit`, `/save` | "Updating..." | "Updated successfully" |
| `/delete`, `/remove` | "Deleting..." | "Deleted successfully" |
| `/complete` | "Completing..." | "Completed successfully" |
| `/upload` | "Uploading..." | "Uploaded successfully" |
| `/toggle` | "Updating status..." | "Status updated" |

```python
# No extra code needed — URL path triggers auto-detection
Form(
    Input(name="title", placeholder="Task title"),
    Button("Create Task"),
    hx_post="/api/tasks/create",   # ← "/create" triggers auto-detection
    hx_target="#task-list",
)
# Screen reader hears: "Creating..." → "Created successfully"
```

---

## Custom Announcements

Override auto-detection with `data-announce` and `data-announce-loading` attributes:

```python
# Custom success and loading messages
Button(
    "Mark as Complete",
    hx_post=f"/api/tasks/{uid}/complete",
    hx_target="#task-detail",
    **{"data-announce": "Great job! Task completed.",
       "data-announce-loading": "Marking task as complete"},
)
# Screen reader hears: "Marking task as complete..." → "Great job! Task completed."
```

```python
# Success announcement only (loading uses auto-detection)
Div(
    P("Loading...", cls="text-center py-8"),
    hx_get="/api/sel/curriculum-html/self-awareness",
    hx_trigger="load",
    hx_swap="innerHTML",
    **{"data-announce": "Curriculum loaded"},
)
```

---

## How the System Works

### JavaScript Event Handlers (`static/js/skuel.js`)

1. **`htmx:beforeRequest`** — Sets `aria-busy="true"` on target, announces loading state
   - Checks `data-announce-loading` attribute first
   - Falls back to URL path auto-detection

2. **`htmx:afterSwap`** — Clears `aria-busy`, announces success
   - Checks `data-announce` on triggering element first
   - Checks `data-announce` in swapped content second
   - Falls back to URL path auto-detection

3. **`htmx:responseError` / `htmx:sendError`** — Clears `aria-busy`, announces errors
   - 404: "Content not found"
   - 403: "You don't have permission..."
   - Network: "Connection problem..."
   - Uses `assertive` priority (immediate)

### Manual Trigger (JavaScript)

```javascript
// Announce directly from JS
window.SKUEL.announce('Test message', 'polite');

// Check live region content
document.getElementById('live-region').textContent;
```

---

## ARIA Attributes

Use direct ARIA attributes for static content (not HTMX-triggered):

```python
# Error messages that appear dynamically
Div(
    P("Something went wrong"),
    **{"aria-live": "polite"},
)

# Critical alerts (immediate)
Div(
    P("Session expired"),
    **{"aria-live": "assertive", "role": "alert"},
)

# Busy states
Div(
    id="task-list",
    **{"aria-busy": "true"},  # Set during loading, cleared by JS
)
```

---

## Best Practices

### URLs Should Match Operation

Design API URLs to use recognizable path segments (`/create`, `/update`, `/delete`, `/complete`) so auto-detection works without extra attributes.

### Use `data-announce` for Context-Specific Messages

When the auto-detected message wouldn't be user-friendly:
```python
# Auto-detection would say "Updated successfully" — too generic
Button(
    "Save Draft",
    hx_post=f"/api/journals/{uid}/save",
    **{"data-announce": "Draft saved"},
)
```

### Don't Skip Announcements for Mutations

```python
# Bad - no announcement, screen reader user has no feedback
Button("Create", hx_post="/api/tasks/create")

# Good - auto-detection handles it via URL
Button("Create", hx_post="/api/tasks/create", hx_target="#task-list")
```

---

## Testing

### Manual Testing with Screen Reader

1. **Enable Screen Reader:** NVDA (Windows), VoiceOver (macOS: Cmd+F5), Orca (Linux)
2. **Trigger HTMX form submission** — listen for loading announcement
3. **Listen for success announcement** after swap completes
4. **Open DevTools** — inspect target element, verify `aria-busy="true"` appears/disappears

### Browser Console Testing

```javascript
// Manually trigger announcement
window.SKUEL.announce('Test message', 'polite');

// Check live region
document.getElementById('live-region').textContent;
```

---

## WCAG Compliance

**Success Criteria Met:**

- ✅ **4.1.3 Status Messages (Level AA)** — Screen reader announcements via live region
- ✅ **1.3.1 Info and Relationships (Level A)** — ARIA attributes (`aria-busy`, `role="status"`)
- ✅ **3.3.1 Error Identification (Level A)** — Specific error messages for failures

---

## Key Files

- **JavaScript:** `/static/js/skuel.js` — HTMX event handlers + `window.SKUEL.announce()`
- **Live Region:** `/ui/layouts/base_page.py` — `#live-region` aria live region
- **Error Banners:** `/ui/patterns/error_banner.py` — Static `aria-live` usage example
