---
title: HTMX Accessibility Patterns
updated: '2026-02-02'
category: patterns
related_skills:
- html-htmx
- accessibility-guide
related_docs: []
---
# HTMX Accessibility Patterns

**Date:** 2026-02-02
**Task:** Task 10 - HTMX + Live Region Integration
**WCAG Level:** AA

---

## Overview

SKUEL provides comprehensive accessibility support for HTMX operations through:

1. **`ui/utils/htmx_a11y.py`** - Python utilities for adding accessibility attributes
2. **`static/js/skuel.js`** - Automatic screen reader announcements for HTMX events
3. **`#live-region`** - ARIA live region in `base_page.py` for announcements

---

## Quick Start

**Skills:** [@html-htmx](../../.claude/skills/html-htmx/SKILL.md), [@accessibility-guide](../../.claude/skills/accessibility-guide/SKILL.md)

### Basic Pattern

```python
from fasthtml.common import Form, Input, Button
from ui.utils.htmx_a11y import htmx_create, HTMXOperation

# CREATE operation with automatic announcement
Form(
    Input(name="title", placeholder="Task title"),
    Button("Create Task"),
    **htmx_create(target="#task-list", entity_type="task"),
    hx_post="/api/tasks/create",
)
# Announces: "Creating task..." → "New task added to your list"
```

### Advanced Pattern

```python
from ui.utils.htmx_a11y import htmx_attrs, HTMXOperation

# Custom announcements
Button(
    "Mark as Complete",
    hx_post=f"/api/tasks/{uid}/complete",
    **htmx_attrs(
        operation=HTMXOperation.COMPLETE,
        target="#task-detail",
        announce="Great job! Task completed.",
        announce_loading="Marking task as complete",
    )
)
# Announces: "Marking task as complete..." → "Great job! Task completed."
```

---

## Core API

### `htmx_attrs()` - Generic Attributes

```python
def htmx_attrs(
    operation: HTMXOperation | None = None,
    target: str | None = None,
    announce: str | None = None,
    announce_loading: str | None = None,
    swap: str = "innerHTML",
    indicator: str | None = None,
) -> dict[str, Any]:
```

**Parameters:**
- `operation` - Operation type (determines default announcements)
- `target` - HTMX target selector (e.g., `"#task-list"`)
- `announce` - Custom success announcement (overrides default)
- `announce_loading` - Custom loading announcement (overrides default)
- `swap` - HTMX swap strategy (default: `"innerHTML"`)
- `indicator` - Loading indicator selector

**Returns:** Dictionary for `**` unpacking in FastHTML components

**Example:**
```python
Button(
    "Save Changes",
    hx_post="/api/tasks/update",
    **htmx_attrs(
        operation=HTMXOperation.UPDATE,
        target="#task-detail",
        announce="Changes saved successfully"
    )
)
```

---

## Shortcut Functions

### Creation Operations

```python
htmx_create(target: str, entity_type: str, announce: str | None = None)
```

**Example:**
```python
Form(
    Input(name="title"),
    Button("Create"),
    hx_post="/api/tasks/create",
    **htmx_create("#task-list", "task")
)
# Announces: "Creating task..." → "New task added to your list"
```

### Update Operations

```python
htmx_update(target: str, entity_type: str, announce: str | None = None)
```

**Example:**
```python
Form(
    Input(name="title", value=task.title),
    Button("Save"),
    hx_post=f"/api/tasks/{uid}/update",
    **htmx_update("#task-detail", "task")
)
# Announces: "Updating task..." → "Task updated successfully"
```

### Delete Operations

```python
htmx_delete(target: str, entity_type: str, announce: str | None = None)
```

**Example:**
```python
Button(
    "Delete",
    hx_delete=f"/api/tasks/{uid}",
    **htmx_delete("#task-list", "task"),
    hx_confirm="Delete this task?"
)
# Announces: "Deleting task..." → "Task deleted successfully"
```

### Toggle Operations

```python
htmx_toggle(target: str, entity_type: str, announce: str | None = None)
```

**Example:**
```python
Button(
    "Toggle Complete",
    hx_post=f"/api/tasks/{uid}/toggle",
    **htmx_toggle("#task-detail", "task", "Task status changed")
)
# Announces: "Updating status..." → "Task status changed"
```

### File Uploads

```python
htmx_upload(target: str, file_type: str = "file", announce: str | None = None)
```

**Example:**
```python
Form(
    Input(type="file", name="audio_file", accept=".mp3,.wav"),
    Button("Upload"),
    hx_post="/api/transcription/upload",
    **htmx_upload("#upload-status", "audio file")
)
# Announces: "Uploading audio file..." → "Audio file uploaded successfully"
# Includes: hx-encoding="multipart/form-data"
```

### Search Operations

```python
htmx_search(target: str, announce: str | None = None)
```

**Example:**
```python
Form(
    Input(name="query", placeholder="Search tasks..."),
    Button("Search"),
    hx_post="/api/search",
    **htmx_search("#search-results")
)
# Announces: "Searching..." → "Search complete. Results updated."
```

---

## Domain-Specific Announcements

For common operations, use domain-specific announcement helpers:

```python
from ui.utils.htmx_a11y import (
    task_announcement,
    habit_announcement,
    goal_announcement,
)

# Get contextual message
msg = task_announcement(HTMXOperation.CREATE)
# Returns: "New task added to your list"

msg = habit_announcement(HTMXOperation.TRACK)
# Returns: "Habit tracked for today"

msg = goal_announcement(HTMXOperation.COMPLETE)
# Returns: "Goal marked as achieved"
```

**Use with `htmx_attrs()`:**
```python
Button(
    "Track Habit",
    hx_post=f"/api/habits/{uid}/track",
    **htmx_attrs(
        operation=HTMXOperation.TRACK,
        target="#habit-detail",
        announce=habit_announcement(HTMXOperation.TRACK)
    )
)
```

---

## HTMXOperation Enum

All available operation types:

```python
class HTMXOperation(str, Enum):
    # Creation
    CREATE = "create"
    ADD = "add"
    ENROLL = "enroll"
    UPLOAD = "upload"

    # Update
    UPDATE = "update"
    EDIT = "edit"
    SAVE = "save"
    TOGGLE = "toggle"
    TRACK = "track"
    DECIDE = "decide"

    # Deletion
    DELETE = "delete"
    REMOVE = "remove"
    CANCEL = "cancel"

    # Query
    LOAD = "load"
    REFRESH = "refresh"
    SEARCH = "search"

    # Completion
    COMPLETE = "complete"
    SUBMIT = "submit"
    PROCESS = "process"
```

---

## Automatic Announcement System

### How It Works

1. **Loading State** (`htmx:beforeRequest`)
   - Adds `aria-busy="true"` to target element
   - Checks for `data-announce-loading` attribute
   - Falls back to auto-detection from URL path

2. **Success State** (`htmx:afterSwap`)
   - Removes `aria-busy` from target element
   - Checks for `data-announce` attribute (triggering element → swapped content)
   - Falls back to auto-detection from URL path

3. **Error States** (`htmx:responseError`, `htmx:sendError`)
   - Removes `aria-busy`
   - Announces specific error messages (404, 403, network errors)
   - Uses `assertive` priority for immediate notification

### Auto-Detection Rules

**Path Pattern → Operation:**
- `/create` → "Creating..." / "Created successfully"
- `/update`, `/edit`, `/save` → "Updating..." / "Updated successfully"
- `/delete`, `/remove` → "Deleting..." / "Deleted successfully"
- `/complete` → "Completing..." / "Completed successfully"
- `/upload` → "Uploading..." / "Uploaded successfully"
- `/track` → "Tracking..." / "Tracked successfully"
- `/enroll` → "Enrolling..." / "Enrolled successfully"
- `/toggle` → "Updating status..." / "Status updated"
- `/decide` → "Recording decision..." / "Decision recorded"

---

## Best Practices

### ✅ DO

**Use domain-specific shortcuts:**
```python
# Good - Clear and concise
**htmx_create("#task-list", "task")
```

**Provide contextual messages:**
```python
# Good - User-friendly message
**htmx_toggle("#task-detail", "task", "Task marked as complete")
```

**Use assertive priority for critical actions:**
```python
# Good - Deletion is important
Button(
    "Delete",
    hx_delete=f"/api/tasks/{uid}",
    **htmx_delete("#task-list", "task"),
    hx_confirm="Delete this task?"
)
```

### ❌ DON'T

**Don't use generic messages:**
```python
# Bad - Not helpful
**htmx_attrs(announce="Action completed")
```

**Don't skip announcements for mutations:**
```python
# Bad - No announcement
Button("Create", hx_post="/api/tasks/create")
```

**Don't forget file encoding for uploads:**
```python
# Bad - Will fail
Button("Upload", hx_post="/upload")

# Good - Uses htmx_upload() which adds encoding
**htmx_upload("#status", "file")
```

---

## Real-World Examples

### Task Creation Form

```python
from fasthtml.common import Form, Input, Textarea, Button, Div
from ui.utils.htmx_a11y import htmx_create

def create_task_form() -> FT:
    return Form(
        Div(
            Input(
                name="title",
                placeholder="Task title",
                cls="input input-bordered w-full",
                required=True,
            ),
            cls="form-control",
        ),
        Div(
            Textarea(
                name="description",
                placeholder="Description (optional)",
                cls="textarea textarea-bordered w-full",
            ),
            cls="form-control mt-4",
        ),
        Button(
            "Create Task",
            type="submit",
            cls="btn btn-primary mt-4",
        ),
        hx_post="/api/tasks/create",
        **htmx_create("#task-list", "task"),
        cls="space-y-4",
    )
```

### Habit Tracking Button

```python
from ui.utils.htmx_a11y import htmx_attrs, HTMXOperation, habit_announcement

def habit_track_button(habit_uid: str) -> FT:
    return Button(
        "✓ Track Today",
        hx_post=f"/api/habits/{habit_uid}/track",
        **htmx_attrs(
            operation=HTMXOperation.TRACK,
            target="#habit-calendar",
            announce=habit_announcement(HTMXOperation.TRACK),
        ),
        cls="btn btn-success",
    )
```

### File Upload Form

```python
from ui.utils.htmx_a11y import htmx_upload

def audio_upload_form() -> FT:
    return Form(
        Input(
            type="file",
            name="audio_file",
            accept=".mp3,.wav,.m4a",
            cls="file-input file-input-bordered",
            required=True,
        ),
        Button(
            "Upload Audio",
            type="submit",
            cls="btn btn-primary mt-4",
        ),
        hx_post="/api/transcription/upload",
        **htmx_upload("#upload-status", "audio file"),
        cls="space-y-4",
    )
```

### Search Form

```python
from ui.utils.htmx_a11y import htmx_search

def task_search_form() -> FT:
    return Form(
        Input(
            name="query",
            placeholder="Search tasks...",
            cls="input input-bordered w-full",
            **{"hx-trigger": "keyup changed delay:500ms"},
        ),
        hx_post="/api/tasks/search",
        **htmx_search("#task-results", "Search results updated"),
        cls="form-control",
    )
```

---

## Testing

### Manual Testing with Screen Reader

1. **Enable Screen Reader:**
   - Windows: NVDA (free) or JAWS
   - macOS: VoiceOver (Cmd+F5)
   - Linux: Orca

2. **Test Operation:**
   - Trigger HTMX form submission
   - Listen for loading announcement ("Creating task...")
   - Listen for success announcement ("New task added to your list")

3. **Verify ARIA:**
   - Open browser DevTools
   - Inspect target element during operation
   - Verify `aria-busy="true"` appears and disappears

### Browser Console Testing

```javascript
// Manually trigger announcement
window.SKUEL.announce('Test message', 'polite');

// Check live region
document.getElementById('live-region').textContent;
```

---

## Migration Guide

### Before (Manual HTMX)

```python
Form(
    Input(name="title"),
    Button("Create"),
    **{
        "hx-post": "/api/tasks/create",
        "hx-target": "#task-list",
        "hx-swap": "innerHTML",
    }
)
# No screen reader announcements
# No aria-busy states
```

### After (With htmx_a11y)

```python
from ui.utils.htmx_a11y import htmx_create

Form(
    Input(name="title"),
    Button("Create"),
    hx_post="/api/tasks/create",
    **htmx_create("#task-list", "task")
)
# ✅ Screen reader announcements
# ✅ aria-busy states
# ✅ Contextual messages
```

---

## WCAG Compliance

**Success Criteria Met:**

- ✅ **4.1.3 Status Messages (Level AA)** - Screen reader announcements via live region
- ✅ **1.3.1 Info and Relationships (Level A)** - ARIA attributes (`aria-busy`, `role="status"`)
- ✅ **3.3.1 Error Identification (Level A)** - Specific error messages for failures

---

## Related Documentation

- **Implementation:** `/ui/utils/htmx_a11y.py`
- **JavaScript:** `/static/js/skuel.js` (HTMX event handlers)
- **Base Page:** `/ui/layouts/base_page.py` (live region)
- **Complete Guide:** `/docs/ux/UX_ACCESSIBILITY_TASKS_9_10_COMPLETE.md`

---

## Questions?

The `htmx_a11y` utilities are ready to use across all domains. Simply import the appropriate helper and add `**htmx_*()` to your forms/buttons for instant accessibility compliance.
