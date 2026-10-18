---
updated: 2026-10-18
---

# UX Improvements Integration Guide

This guide provides step-by-step instructions for integrating the newly implemented UX improvements into SKUEL.

---

## Toast Notifications Integration

### Step 1: Add Toast Container to base_page.py

Add this code to `/ui/layouts/base_page.py` in the `Body` section, after the modal container:

```python
# In BasePage() function, inside Body():
Body(
    navbar,
    main_area,
    # Modal container for overlays
    Div(id="modal"),
    # Live region for screen reader announcements
    Div(
        id="live-region",
        role="status",
        cls="sr-only",
        **{"aria-live": "polite", "aria-atomic": "true"},
    ),
    # Toast notification container - ADD THIS
    Div(
        **{"x-data": "toastManager", "x-cloak": ""},
        cls="fixed top-4 right-4 z-50 space-y-2",
        # Template for toast rendering
        Div(
            **{"x-for": "toast in toasts", ":key": "toast.id"},
            Div(
                Div(
                    P(**{"x-text": "toast.message"}, cls="text-sm font-medium"),
                    Button(
                        "×",
                        **{"@click": "dismiss(toast.id)"},
                        cls="ml-4 text-lg",
                    ),
                    cls="flex items-center justify-between",
                ),
                cls="alert shadow-lg max-w-sm",
                **{
                    ":class": """{
                        'alert-success': toast.type === 'success',
                        'alert-error': toast.type === 'error',
                        'alert-info': toast.type === 'info',
                        'alert-warning': toast.type === 'warning'
                    }"""
                },
            ),
        ),
    ),
    cls="bg-white",
)
```

### Step 2: Add Toast Headers in Route Handlers

Update route handlers to include toast headers:

```python
from core.utils.result import Result

@boundary_handler(success_status=201)
async def create_task(request, body):
    result = await service.create_task(...)

    if result.is_ok:
        # Return with toast header
        return Result.ok({
            "task": result.value,
            "_headers": {
                "X-Toast-Message": "Task created successfully",
                "X-Toast-Type": "success"
            }
        })
```

### Step 3: Update boundary_handler to Extract Headers

Modify `@boundary_handler` decorator to extract `_headers` from result and add to response:

```python
# In boundary_handler decorator:
if result.is_ok:
    data = result.value
    headers = {}

    # Extract _headers if present
    if isinstance(data, dict) and "_headers" in data:
        headers = data.pop("_headers")

    response = JSONResponse(data, status_code=success_status)

    # Add custom headers
    for key, value in headers.items():
        response.headers[key] = value

    return response
```

---

## Form Validation Integration

FormGenerator handles all three integration points automatically:

1. **Alpine.js formValidator** — every form gets `x-data="formValidator"` and `@submit="validate($event)"` by default
2. **Error clearing** — every input gets `@input="clearError('field_name')"` for real-time error dismissal
3. **Error display** — each field has a hidden `<div id="field-error">` shown by the `formValidator` Alpine component

```python
# FormGenerator.from_model() produces forms with all validation wiring built in:
from ui.patterns.form_generator import FormGenerator

form = FormGenerator.from_model(
    TaskCreateRequest,
    action="/api/tasks",
    method="POST",
)
# Result: <form x-data="formValidator" @submit="validate($event)" ...>
#   <input name="title" @input="clearError('title')" required ...>
#   <div id="title-error" role="alert" style="display:none;"></div>
# </form>
```

See `/docs/patterns/FORM_GENERATOR_GUIDE.md` for full API reference.

---

## Skeleton Loader Integration

### Example 1: Task List View

Replace empty content with skeleton:

```python
from ui.patterns.skeleton import SkeletonList

# In task list route:
@rt("/tasks")
async def tasks_view(request):
    return BasePage(
        Div(
            id="task-list",
            hx_get="/api/tasks/list",
            hx_trigger="load",
            hx_swap="outerHTML",
            # Show skeleton initially
            SkeletonList(count=5),
        ),
        title="Tasks",
        request=request,
    )
```

### Example 2: Chart Loading State

```python
from ui.patterns.skeleton import SkeletonStats

# In chart component:
Div(
    **{"x-data": "chartVis('/api/lifepath/alignment/chart')"},
    # Loading skeleton
    Div(
        **{"x-show": "loading"},
        SkeletonStats(),
    ),
    # Chart canvas (hidden until loaded)
    Canvas(
        **{"x-show": "!loading", "x-ref": "canvas"},
        id="chart",
    ),
)
```

---

## Modal Integration

### Use the shared AlpineModal wrapper

Do not hand-roll the backdrop, transition, click-out or dialog behaviour on
every modal — use `AlpineModal` from `ui/patterns/modal.py`. State stays yours;
the wrapper owns the chrome and the dialog semantics. Give your heading an id
and pass it as `title_id`.

```python
from ui.patterns.modal import AlpineModal

Div(
    Button("Open", **{"@click": "isOpen = true"}),
    AlpineModal(
        H3("Details", id="details-title"),
        Button("Close", **{"@click": "isOpen = false"}),
        show="isOpen",
        close="isOpen = false",
        title_id="details-title",
    ),
    **{"x-data": "{ isOpen: false }"},
)
```

Pass `close="close()"` instead when the modal is backed by a registry component
that needs to do more than flip a boolean — `insightDetailModal(uid)` is the
worked example in `skuel.js`.

### Focus trapping

`AlpineModal` traps focus. The wrapper mounts the shared `alpineModal`
component (`static/js/skuel.js`) beside the caller's state, and it keeps Tab
inside the dialog, restores focus on close and lets Escape close it. Four
constraints shaped it, and any change to it keeps them:

1. **The dialog is found from the component root**, not by `$refs` —
   `AlpineModal` emits no `x-ref`, and a caller may pass its own `id`.
2. **Focus moves only once the modal is displayed.** Alpine reveals `x-show`
   a frame after the state flips, and a browser ignores `focus()` on a hidden
   element; the component waits for the wrapper to be displayed.
3. **Every dismissal runs one path.** Click-out and Escape both run the
   caller's `close` expression, and the component watches the `show`
   expression itself (`x-effect`), so however the modal closes, focus returns.
4. **Escape closes the modal**, handled on the dialog, where focus stays while
   it is open, so no window listener runs while the modal is shut. A control inside that
   uses Escape itself — the entity picker's list — stops the event only while
   it is using it.

The Tab trap and the wait-for-reveal are `window.SKUEL.trapTab(event, dialog)`
and `window.SKUEL.whenDisplayed(el, tries, run, wanted)` in `skuel.js`, shared
with the one dialog built in JavaScript rather than by `AlpineModal` — the
Explore graph's expanded overlay (`exploreGraph.expandGraph`). It moves focus to
its close button when it opens, keeps Tab inside, and on close returns focus to
the expand button once `x-show` has revealed it.

Pinned by `tests/js/alpine-modal.test.js` (vendored Alpine, jsdom),
`tests/unit/ui/test_alpine_modal_markup.py`, and for the overlay
`tests/js/graph-components.test.js`.

---

## Empty State Standardization

### Update Domain List Views

Use consistent EmptyState component:

```python
from ui.patterns.empty_state import EmptyState

# In all domain list views:
if not entities:
    return EmptyState(
        icon="📋",  # Domain-specific emoji
        title="No tasks yet",
        description="Create your first task to get started",
        action_text="Create Task",
        action_url="/tasks/create",
    )
```

### Domain-Specific Icons

- Tasks: 📋
- Goals: 🎯
- Habits: 🔄
- Events: 📅
- Choices: 🤔
- Principles: 💡
- KU: 📚
- PS: 📖
- LP: 🛤️

---

## Safe Zone (notched phones)

The bottom nav (`create_bottom_nav`, `ui/layouts/navbar.py`) pads itself by
`env(safe-area-inset-bottom)` and has a *minimum* height of 4rem, so the
home-indicator inset grows the bar instead of squeezing its tabs. Main content
and the offline banner clear it with the same expression —
`pb-[calc(4rem+env(safe-area-inset-bottom))]` / `bottom-[calc(…)]` in
`ui/layouts/base_page.py`. A new fixed element at the bottom of the viewport
uses that expression; there is no helper class for it.

---

## Live Region Usage

### Announce Content Updates

Add `data-announce` to the triggering element (or any element inside the
swapped content). skuel.js's `htmx:afterSwap` handler announces it after a
successful swap; without it, mutations (non-GET) get a keyword-based default
("Created successfully", "Status updated", ...). `data-announce-loading` on
the triggering element customizes the in-flight announcement.

```python
Button(
    "Search",
    hx_get="/api/search",
    hx_target="#results",
    **{"data-announce": "Search results updated"},
)
```

### Custom Announcements

For dynamic announcements use the central announcer (sets aria-live priority
and clears after 3s):

```javascript
// In JavaScript:
window.SKUEL.announce('Task completed', 'polite');
```

---

## Testing Checklist

### After Integration

1. **Toast Notifications**
   - [ ] Create task → Green toast appears
   - [ ] Delete task → Red toast appears
   - [ ] Multiple toasts stack properly
   - [ ] Toasts auto-dismiss after 3 seconds

2. **Form Validation**
   - [ ] Submit empty required field → Inline error shows
   - [ ] Type in field → Error clears immediately
   - [ ] Invalid email → Custom error message
   - [ ] Focus moves to first invalid field

3. **Skeleton Loaders**
   - [ ] Task list shows skeleton on load
   - [ ] Skeleton smoothly transitions to content
   - [ ] No layout shift during transition

4. **Modal Focus Trap**
   - [ ] Tab key loops within modal
   - [ ] Escape key closes modal
   - [ ] Focus restored to trigger button

5. **Safe Zones (iOS)**
   - [ ] Bottom nav not obscured by home indicator
   - [ ] Content not clipped by notch
   - [ ] Works in landscape orientation

6. **Live Region**
   - [ ] HTMX swaps announce to screen reader
   - [ ] No visual impact (sr-only)
   - [ ] Announcements clear after 1 second

---

## Troubleshooting

### Toast Not Appearing

**Check:**
1. Toast container added to `base_page.py`?
2. `toastManager` initialized in Alpine?
3. Response headers include `X-Toast-Message`?
4. MonsterUI alert classes available?

**Debug:**
```javascript
// In console:
Alpine.store('toastManager').show('Test', 'success');
```

---

### Form Validation Not Working

**Check:**
1. Form has `x-data="formValidator"`?
2. Form has `@submit="validate($event)"`?
3. Inputs have proper `name` attributes?
4. Error divs have `id="{name}-error"`?

**Debug:**
```javascript
// Check Alpine data:
Alpine.$data(document.querySelector('form'))
```

---

### Skeleton Not Showing

**Check:**
1. Import statement correct?
2. HTMX `hx-swap="outerHTML"` used?
3. Initial content includes skeleton?
4. CSS animations working?

---

## Performance Considerations

### Skeleton Loaders

- Use only for content that takes >500ms to load
- Limit skeleton count to visible viewport
- Don't overuse - simple spinners OK for fast operations

### Toast Notifications

- Auto-dismiss after 3 seconds (default)
- Limit to 5 toasts max on screen
- Don't spam toasts for bulk operations

### Form Validation

- HTML5 validation is fast (no performance impact)
- Clear errors on input (not on keypress - too frequent)
- Only validate on submit

---

## Next Integration Steps

### Priority Order

1. **Toast Container** (5 minutes)
   - Add to `base_page.py`
   - Test manually

2. **Toast Headers** (30 minutes)
   - Update `boundary_handler`
   - Add to route factories
   - Test CRUD operations

3. **Form Validation** (1 hour)
   - Update `FormGenerator`
   - Test all forms
   - Add custom error messages

4. **Skeleton Loaders** (2 hours)
   - Update domain list views (9 files)
   - Test loading states
   - Optimize count per view

5. **Empty States** (1 hour)
   - Standardize across domains
   - Choose icons
   - Test CTA buttons

---

## Maintenance Notes

### Adding New Forms

Always include:
```python
Form(
    **{"x-data": "formValidator", "@submit": "validate($event)"},
    # ... fields with @input="clearError('{name}')"
)
```

### Adding New Modals

Always use the shared wrapper, with the state declared on the parent:
```python
from ui.patterns.modal import AlpineModal

Div(
    AlpineModal(H3(title, id="my-title"), *content, show="isOpen",
                close="isOpen = false", title_id="my-title"),
    **{"x-data": "{ isOpen: false }"},
)
```

### Adding New List Views

Always include:
```python
from ui.patterns.skeleton import SkeletonList

Div(
    hx_get="/api/...",
    hx_trigger="load",
    SkeletonList(count=5),  # Initial skeleton
)
```

---

## Support

For questions or issues:
1. Check this guide first
2. Check the Alpine.js architecture: `/docs/architecture/ALPINE_JS_ARCHITECTURE.md`
3. Check Alpine.js component JSDoc in `/static/js/skuel.js`
4. Test in isolation with minimal examples
