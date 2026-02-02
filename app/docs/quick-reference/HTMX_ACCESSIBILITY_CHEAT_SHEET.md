# HTMX Accessibility Cheat Sheet

**Quick Reference for Task 10 - HTMX + Live Region Integration**

---

## One-Line Import

```python
from ui.utils.htmx_a11y import htmx_create, htmx_update, htmx_delete, htmx_toggle, htmx_upload, htmx_search
```

---

## Common Patterns

### Create Form

```python
Form(
    Input(name="title"),
    Button("Create"),
    hx_post="/api/tasks/create",
    **htmx_create("#task-list", "task")
)
```
**Announces:** "Creating task..." → "New task added to your list"

---

### Update Form

```python
Form(
    Input(name="title", value=entity.title),
    Button("Save"),
    hx_post=f"/api/tasks/{uid}/update",
    **htmx_update("#task-detail", "task")
)
```
**Announces:** "Updating task..." → "Task updated successfully"

---

### Delete Button

```python
Button(
    "Delete",
    hx_delete=f"/api/tasks/{uid}",
    **htmx_delete("#task-list", "task"),
    hx_confirm="Delete this task?"
)
```
**Announces:** "Deleting task..." → "Task deleted successfully"

---

### Toggle Button (Completion)

```python
Button(
    "Mark Complete",
    hx_post=f"/api/tasks/{uid}/toggle",
    **htmx_toggle("#task-detail", "task")
)
```
**Announces:** "Updating status..." → "Task status updated"

---

### File Upload

```python
Form(
    Input(type="file", name="audio", accept=".mp3,.wav"),
    Button("Upload"),
    hx_post="/api/transcription/upload",
    **htmx_upload("#status", "audio file")
)
```
**Announces:** "Uploading audio file..." → "Audio file uploaded successfully"
**Auto-adds:** `hx-encoding="multipart/form-data"`

---

### Search Form

```python
Form(
    Input(name="query", placeholder="Search..."),
    hx_post="/api/search",
    **htmx_search("#results")
)
```
**Announces:** "Searching..." → "Search complete. Results updated."

---

## Custom Announcements

### Method 1: Shortcut with Custom Message

```python
**htmx_create(
    "#list",
    "task",
    announce="Great! Your task is now on the list."
)
```

### Method 2: Generic with Full Control

```python
from ui.utils.htmx_a11y import htmx_attrs, HTMXOperation

**htmx_attrs(
    operation=HTMXOperation.CREATE,
    target="#list",
    announce="Success message",
    announce_loading="Loading message"
)
```

### Method 3: Domain-Specific Helper

```python
from ui.utils.htmx_a11y import habit_announcement, HTMXOperation

announce = habit_announcement(HTMXOperation.TRACK)
# Returns: "Habit tracked for today"
```

---

## HTMXOperation Types

```python
from ui.utils.htmx_a11y import HTMXOperation

# Creation
HTMXOperation.CREATE    # "Created successfully"
HTMXOperation.ADD       # "Added successfully"
HTMXOperation.ENROLL    # "Enrolled successfully"
HTMXOperation.UPLOAD    # "Uploaded successfully"

# Update
HTMXOperation.UPDATE    # "Updated successfully"
HTMXOperation.EDIT      # "Changes saved"
HTMXOperation.SAVE      # "Saved successfully"
HTMXOperation.TOGGLE    # "Status changed"
HTMXOperation.TRACK     # "Tracked successfully"
HTMXOperation.DECIDE    # "Decision recorded"

# Deletion
HTMXOperation.DELETE    # "Deleted successfully"
HTMXOperation.REMOVE    # "Removed successfully"
HTMXOperation.CANCEL    # "Cancelled successfully"

# Query
HTMXOperation.LOAD      # "Content loaded"
HTMXOperation.REFRESH   # "Refreshed successfully"
HTMXOperation.SEARCH    # "Search complete"

# Completion
HTMXOperation.COMPLETE  # "Completed successfully"
HTMXOperation.SUBMIT    # "Submitted successfully"
HTMXOperation.PROCESS   # "Processing complete"
```

---

## Auto-Detection (No Utility Needed)

These URL patterns are **automatically detected**:

| URL Contains | Announcement |
|--------------|--------------|
| `/create` | "Creating..." → "Created successfully" |
| `/update` | "Updating..." → "Updated successfully" |
| `/edit` | "Saving changes..." → "Changes saved" |
| `/save` | "Saving..." → "Saved successfully" |
| `/delete` | "Deleting..." → "Deleted successfully" |
| `/complete` | "Completing..." → "Completed successfully" |
| `/upload` | "Uploading..." → "Uploaded successfully" |
| `/track` | "Tracking..." → "Tracked successfully" |
| `/toggle` | "Updating status..." → "Status updated" |

**Example (no utility needed):**
```python
Button("Save", hx_post="/api/tasks/update")
# Automatically announces: "Updating..." → "Updated successfully"
```

---

## Error Announcements (Automatic)

| Error | Message |
|-------|---------|
| 404 | "Item not found" |
| 403 | "Permission denied" |
| 400 | "Invalid request" |
| 500+ | "Server error. Please try again later." |
| Network | "Network error. Please check your connection." |

**Priority:** All errors use `assertive` (interrupts screen reader)

---

## Manual JavaScript

```javascript
// Polite announcement (default)
window.SKUEL.announce("Task created", "polite");

// Assertive announcement (urgent)
window.SKUEL.announce("Error occurred", "assertive");

// Check live region
document.getElementById('live-region').textContent;

// Check aria-busy
document.getElementById('task-list').getAttribute('aria-busy');
```

---

## Testing Quick Start

### 1. Visual Test

- Trigger HTMX operation
- Verify content swaps
- Check DevTools for `aria-busy` toggle

### 2. Screen Reader Test

**Enable:**
- Windows: NVDA (Alt+Ctrl+N)
- macOS: VoiceOver (Cmd+F5)

**Listen for:**
1. Loading: "Creating task..."
2. Success: "New task added to your list"

### 3. Manual Test Page

```
http://localhost:5001/tests/manual/test_ux_accessibility_tasks_9_10.html
```

---

## Migration Checklist

- [ ] Import `htmx_a11y` utilities
- [ ] Replace `**{"hx-post": ...}` with `hx_post=...`
- [ ] Add `**htmx_create()` (or appropriate helper)
- [ ] Test with screen reader
- [ ] Verify `aria-busy` toggles
- [ ] Check custom announcements work

---

## When to Use Each Helper

| Operation | Helper | Example |
|-----------|--------|---------|
| Creating new entity | `htmx_create` | Create task, add goal |
| Updating existing | `htmx_update` | Edit task, save form |
| Deleting entity | `htmx_delete` | Delete task, remove habit |
| Status change | `htmx_toggle` | Mark complete, toggle active |
| File upload | `htmx_upload` | Upload audio, upload document |
| Search/filter | `htmx_search` | Search tasks, filter results |
| Custom operation | `htmx_attrs` | Any operation with custom needs |

---

## Complete Documentation

**Full API Reference:**
`/docs/patterns/HTMX_ACCESSIBILITY_PATTERNS.md`

**Real-World Examples:**
`/docs/ux/HTMX_ACCESSIBILITY_MIGRATION_EXAMPLES.md`

**Source Code:**
`/ui/utils/htmx_a11y.py`

---

## Pro Tips

✅ **DO:**
- Use domain-specific shortcuts (`htmx_create`, `htmx_update`)
- Provide contextual messages ("Task added to your list")
- Test with actual screen reader
- Use specific targets (`#task-list`) instead of `body`

❌ **DON'T:**
- Use generic messages ("Action completed")
- Skip announcements for mutations (POST/PUT/DELETE)
- Forget file encoding for uploads (use `htmx_upload()`)
- Use manual `**{"hx-post": ...}` when helpers exist

---

## Example: Complete Task Form

```python
from fasthtml.common import Form, Input, Textarea, Button, Div
from ui.utils.htmx_a11y import htmx_create

def task_create_form() -> FT:
    """Fully accessible task creation form."""
    return Form(
        Div(
            Input(
                name="title",
                placeholder="Task title",
                cls="input input-bordered",
                required=True,
            ),
            cls="form-control",
        ),
        Div(
            Textarea(
                name="description",
                placeholder="Description",
                cls="textarea textarea-bordered",
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

**Result:**
- ✅ Screen reader announces: "Creating task..." → "New task added to your list"
- ✅ `aria-busy="true"` during operation
- ✅ Automatic error handling (404, network errors)
- ✅ WCAG 2.1 Level AA compliant

---

**That's it! One line adds full accessibility.**
