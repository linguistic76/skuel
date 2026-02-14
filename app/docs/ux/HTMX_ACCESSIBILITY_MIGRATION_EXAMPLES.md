# HTMX Accessibility Migration Examples

**Date:** 2026-02-02
**Task:** Task 10 - Real-world migration examples

---

## Overview

This document shows before/after examples of migrating existing HTMX forms to use the new `htmx_a11y` utilities for WCAG 2.1 Level AA compliance.

---

## Example 1: Task Toggle (Simple Button)

### Before

```python
# adapters/inbound/tasks_ui.py (line ~1174)
Button(
    "✓ Toggle Complete",
    **{"hx-post": f"/tasks/{task.uid}/toggle", "hx-target": "body"},
    variant=ButtonT.success if task.status != KuStatus.COMPLETED else ButtonT.ghost,
)
```

**Issues:**
- ❌ No screen reader announcement
- ❌ No `aria-busy` state
- ❌ No contextual message

### After

```python
from ui.utils.htmx_a11y import htmx_toggle

Button(
    "✓ Toggle Complete",
    hx_post=f"/tasks/{task.uid}/toggle",
    **htmx_toggle(
        target="body",
        entity_type="task",
        announce="Task marked as complete" if task.status != KuStatus.COMPLETED else "Task reopened"
    ),
    variant=ButtonT.success if task.status != KuStatus.COMPLETED else ButtonT.ghost,
)
```

**Benefits:**
- ✅ Announces "Updating status..." → "Task marked as complete"
- ✅ `aria-busy="true"` during operation
- ✅ Contextual message based on current state

---

## Example 2: Habit Tracking (Domain-Specific)

### Before

```python
# adapters/inbound/habits_ui.py (line ~2186)
Button(
    "✓ Track Today",
    **{"hx-post": f"/api/habits/{habit.uid}/track", "hx-target": "body"},
    variant=ButtonT.success,
)
```

**Issues:**
- ❌ No screen reader announcement
- ❌ Generic target (`body`)

### After

```python
from ui.utils.htmx_a11y import htmx_attrs, HTMXOperation, habit_announcement

Button(
    "✓ Track Today",
    hx_post=f"/api/habits/{habit.uid}/track",
    **htmx_attrs(
        operation=HTMXOperation.TRACK,
        target="#habit-detail",  # More specific target
        announce=habit_announcement(HTMXOperation.TRACK),  # "Habit tracked for today"
    ),
    variant=ButtonT.success,
)
```

**Benefits:**
- ✅ Announces "Tracking..." → "Habit tracked for today"
- ✅ Specific target for partial page update
- ✅ Domain-aware messaging

---

## Example 3: Form Submission (Learning Enrollment)

### Before

```python
# adapters/inbound/learning_ui.py (line ~233)
Button(
    "Enroll in Path",
    cls="btn-sm flex-1",
    **{
        "hx-post": f"/api/learning/enroll/{path['uid']}",
        "hx-target": "#main-content",
    },
)
```

**Issues:**
- ❌ No screen reader announcement
- ❌ No loading state

### After

```python
from ui.utils.htmx_a11y import htmx_attrs, HTMXOperation

Button(
    "Enroll in Path",
    cls="btn-sm flex-1",
    hx_post=f"/api/learning/enroll/{path['uid']}",
    **htmx_attrs(
        operation=HTMXOperation.ENROLL,
        target="#main-content",
        announce=f"Enrolled in {path.get('title', 'learning path')} successfully",
        announce_loading=f"Enrolling in {path.get('title', 'learning path')}",
    ),
)
```

**Benefits:**
- ✅ Announces "Enrolling in [Path Name]..." → "Enrolled in [Path Name] successfully"
- ✅ Personalized messages with path title
- ✅ Clear feedback for user

---

## Example 4: File Upload Form (Voice Journal)

### Before

```python
# adapters/inbound/journals_ui.py (line ~304)
Form(
    Input(type="file", name="audio_file", accept=".mp3,.wav,.m4a"),
    Button("Upload Voice Journal", type="submit"),
    # HTMX attributes
    **{
        "hx-post": "/journals/upload/voice",
        "hx-target": "#voice-upload-status",
        "hx-swap": "outerHTML",
        "hx-encoding": "multipart/form-data",
    },
)
```

**Issues:**
- ❌ No screen reader announcement for upload progress
- ❌ Manual multipart encoding specification

### After

```python
from ui.utils.htmx_a11y import htmx_upload

Form(
    Input(type="file", name="audio_file", accept=".mp3,.wav,.m4a"),
    Button("Upload Voice Journal", type="submit"),
    hx_post="/journals/upload/voice",
    **htmx_upload(
        target="#voice-upload-status",
        file_type="voice journal",
        announce="Voice journal uploaded and transcription started",
    ),
    hx_swap="outerHTML",  # Custom swap (overrides default innerHTML)
)
```

**Benefits:**
- ✅ Announces "Uploading voice journal..." → "Voice journal uploaded and transcription started"
- ✅ Automatic multipart encoding (via `htmx_upload()`)
- ✅ Contextual file type in message

---

## Example 5: Choice Decision Form

### Before

```python
# adapters/inbound/choice_ui.py (line ~978)
Form(
    # ... form fields ...
    Button("Make Decision", type="submit"),
    **{
        "hx-post": f"/choices/{uid}/decide",
        "hx-target": "body",
    },
)
```

**Issues:**
- ❌ No announcement for decision recording
- ❌ Generic message

### After

```python
from ui.utils.htmx_a11y import htmx_attrs, HTMXOperation

Form(
    # ... form fields ...
    Button("Make Decision", type="submit"),
    hx_post=f"/choices/{uid}/decide",
    **htmx_attrs(
        operation=HTMXOperation.DECIDE,
        target="body",
        announce="Decision recorded. Your choice has been saved.",
        announce_loading="Recording your decision",
    ),
)
```

**Benefits:**
- ✅ Announces "Recording your decision..." → "Decision recorded. Your choice has been saved."
- ✅ Confirms action completion
- ✅ Reassures user their choice is saved

---

## Example 6: Habit Form Save (Complex Form)

### Before

```python
# adapters/inbound/habits_ui.py (line ~2034)
Form(
    # ... many form fields ...
    Button("Save Habit", type="submit"),
    **{
        "hx-post": f"/habits/{uid}/save",
        "hx-target": "#modal",
        "hx-swap": "innerHTML",
    },
)
```

**Issues:**
- ❌ No save confirmation for user
- ❌ No loading state

### After

```python
from ui.utils.htmx_a11y import htmx_update

Form(
    # ... many form fields ...
    Button("Save Habit", type="submit"),
    hx_post=f"/habits/{uid}/save",
    **htmx_update(
        target="#modal",
        entity_type="habit",
        announce="Habit saved successfully. You can close this dialog.",
    ),
    hx_swap="innerHTML",
)
```

**Benefits:**
- ✅ Announces "Updating habit..." → "Habit saved successfully. You can close this dialog."
- ✅ Guides user to next action
- ✅ Clear feedback for form submission

---

## Example 7: Event Form with Custom Target

### Before

```python
# adapters/inbound/events_ui.py (line ~837)
Form(
    # ... event fields ...
    Button("Update Event", type="submit"),
    **{
        "hx-post": f"/events/{uid}/update",
        "hx-target": "body",
        "hx-swap": "innerHTML",
    },
)
```

**Issues:**
- ❌ Full page reload (`body` target)
- ❌ No update confirmation

### After

```python
from ui.utils.htmx_a11y import htmx_update

Form(
    # ... event fields ...
    Button("Update Event", type="submit"),
    hx_post=f"/events/{uid}/update",
    **htmx_update(
        target="#event-detail",  # Partial page update instead of full body
        entity_type="event",
        announce="Event updated. Your calendar has been refreshed.",
    ),
    hx_swap="outerHTML",  # Replace the detail container
)
```

**Benefits:**
- ✅ Partial page update (better performance)
- ✅ Announces "Updating event..." → "Event updated. Your calendar has been refreshed."
- ✅ Contextual message mentions calendar

---

## Example 8: Search with Live Updates

### Before

```python
# No existing example - new pattern
Form(
    Input(name="query", placeholder="Search tasks..."),
    Button("Search", type="submit"),
    **{
        "hx-post": "/api/tasks/search",
        "hx-target": "#search-results",
    },
)
```

**Issues:**
- ❌ No announcement of search completion
- ❌ No result count

### After (Basic)

```python
from ui.utils.htmx_a11y import htmx_search

Form(
    Input(
        name="query",
        placeholder="Search tasks...",
        **{"hx-trigger": "keyup changed delay:500ms"},  # Live search
    ),
    Button("Search", type="submit", cls="hidden"),  # Hidden submit for Enter key
    hx_post="/api/tasks/search",
    **htmx_search("#search-results"),
)
```

### After (Advanced with Result Count)

```python
from ui.utils.htmx_a11y import htmx_attrs, HTMXOperation

# In route handler, return result count in response:
# Div(
#     *search_results,
#     **{"data-announce": f"{len(results)} tasks found"}
# )

Form(
    Input(
        name="query",
        placeholder="Search tasks...",
        **{"hx-trigger": "keyup changed delay:500ms"},
    ),
    Button("Search", type="submit", cls="hidden"),
    hx_post="/api/tasks/search",
    **htmx_attrs(
        operation=HTMXOperation.SEARCH,
        target="#search-results",
        announce_loading="Searching tasks",
        # Success message comes from data-announce in response
    ),
)
```

**Benefits:**
- ✅ Announces "Searching tasks..." → "[X] tasks found"
- ✅ Live search with delay (avoids spam)
- ✅ Result count for screen reader users

---

## Example 9: Transcription Upload

### Before

```python
# adapters/inbound/transcription_ui.py (line ~267)
Form(
    Input(type="file", name="audio_file", accept=".mp3,.wav,.m4a"),
    Button("Upload Audio", type="submit"),
    **{
        "hx-post": "/transcriptions/upload",
        "hx-target": "#upload-status",
        "hx-swap": "outerHTML",
        "hx-encoding": "multipart/form-data",
    },
)
```

**Issues:**
- ❌ No progress indication
- ❌ No completion message

### After

```python
from ui.utils.htmx_a11y import htmx_upload

Form(
    Input(type="file", name="audio_file", accept=".mp3,.wav,.m4a"),
    Button("Upload Audio", type="submit"),
    hx_post="/transcriptions/upload",
    **htmx_upload(
        target="#upload-status",
        file_type="audio file",
        announce="Audio file uploaded. Transcription will begin shortly.",
    ),
    hx_swap="outerHTML",
    hx_indicator="#upload-spinner",  # Optional: show spinner during upload
)
```

**Benefits:**
- ✅ Announces "Uploading audio file..." → "Audio file uploaded. Transcription will begin shortly."
- ✅ Sets user expectation for next step
- ✅ Optional spinner for visual feedback

---

## Example 10: Add Option to Choice

### Before

```python
# adapters/inbound/choice_ui.py (line ~1236)
Form(
    Input(name="option_text", placeholder="New option"),
    Button("Add Option", type="submit"),
    **{
        "hx-post": f"/choices/{uid}/add-option",
        "hx-target": "body",
    },
)
```

**Issues:**
- ❌ No confirmation of option added
- ❌ Full page reload

### After

```python
from ui.utils.htmx_a11y import htmx_create

Form(
    Input(name="option_text", placeholder="New option"),
    Button("Add Option", type="submit"),
    hx_post=f"/choices/{uid}/add-option",
    **htmx_create(
        target="#choice-options",  # Update just the options list
        entity_type="option",
        announce="New option added to the choice",
    ),
    hx_swap="beforeend",  # Append to list instead of replacing
)
```

**Benefits:**
- ✅ Announces "Creating option..." → "New option added to the choice"
- ✅ Partial page update (options list only)
- ✅ Appends instead of replacing (preserves existing options)

---

## Migration Checklist

For each HTMX form/button in your UI:

- [ ] **Import utility:** `from ui.utils.htmx_a11y import htmx_*`
- [ ] **Identify operation:** CREATE, UPDATE, DELETE, TOGGLE, UPLOAD, etc.
- [ ] **Choose helper:** Use shortcut (`htmx_create`) or generic (`htmx_attrs`)
- [ ] **Add attributes:** `**htmx_*(target, entity_type, announce)`
- [ ] **Test with screen reader:** Verify announcements work
- [ ] **Update target if needed:** Use specific selectors instead of `body`

---

## Testing Your Migration

### 1. Visual Verification

**Before operation:**
- No visible change

**During operation:**
- Look for loading spinners (if using `hx-indicator`)
- Check browser DevTools for `aria-busy="true"` on target

**After success:**
- Content swapped correctly
- No console errors

### 2. Screen Reader Verification

**Enable screen reader:**
- Windows: NVDA
- macOS: VoiceOver (Cmd+F5)

**Test flow:**
1. Navigate to form/button
2. Trigger action
3. **Listen for:** "Creating task..." (or custom loading message)
4. **Listen for:** "New task added to your list" (or custom success message)

### 3. Error State Verification

**Trigger error:**
- Disconnect internet
- Trigger 404 by using invalid UID
- Trigger 403 by testing as non-owner

**Listen for:**
- "Network error. Please check your connection."
- "Item not found"
- "Permission denied"

---

## Common Patterns

### Pattern: Form with Submit Button

```python
Form(
    # ... form fields ...
    Button("Submit", type="submit"),
    hx_post="/api/endpoint",
    **htmx_create("#target", "entity_type"),
)
```

### Pattern: Action Button

```python
Button(
    "Action",
    hx_post="/api/action",
    **htmx_toggle("#target", "entity", "Custom message"),
)
```

### Pattern: File Upload

```python
Form(
    Input(type="file", name="file"),
    Button("Upload", type="submit"),
    hx_post="/api/upload",
    **htmx_upload("#status", "file_type"),
)
```

### Pattern: Delete with Confirmation

```python
Button(
    "Delete",
    hx_delete="/api/delete",
    **htmx_delete("#list", "entity"),
    hx_confirm="Are you sure?",
)
```

---

## Next Steps

1. ✅ **Read patterns:** Review `/docs/patterns/HTMX_ACCESSIBILITY_PATTERNS.md`
2. 🔄 **Migrate forms:** Start with high-traffic domains (Tasks, Habits, Goals)
3. 🧪 **Test thoroughly:** Use screen reader for every migrated form
4. 📝 **Document custom cases:** Add new patterns to this doc if needed

---

## Questions?

The migration is straightforward - most cases are 1-2 line changes. The accessibility improvements are automatic once you use the `htmx_a11y` utilities.
