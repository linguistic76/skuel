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

### Step 1: Update FormGenerator

Add validation attributes to generated forms:

```python
# In FormGenerator.generate_form():
@staticmethod
def generate_form(...):
    return Form(
        **{"x-data": "formValidator", "@submit": "validate($event)"},
        # ... existing fields
    )
```

### Step 2: Add Error Clearing on Input

Update input generation to clear errors on input:

```python
# In FormGenerator._generate_field():
input_attrs = {
    **{"@input": f"clearError('{field_name}')"},
    # ... other attributes
}
```

### Step 3: Pass Pydantic Errors to Input Component

```python
# In route handlers with form errors:
if validation_errors:
    errors_dict = {field: str(error) for field, error in validation_errors.items()}

    return FormGenerator.generate_form(
        model=TaskCreateRequest,
        errors=errors_dict,  # Pass errors to form
        ...
    )
```

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
    **{"x-data": "chartVis('/api/analytics/chart')"},
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

## Focus Trap Modal Integration

### Replace Existing Modals

Update modal components to use `focusTrapModal`:

```python
# Old modal:
Div(
    **{"x-data": "{ isOpen: false }"},
    Button("Open", **{"@click": "isOpen = true"}),
    Div(
        **{"x-show": "isOpen"},
        # Modal content
    ),
)

# New modal with focus trap:
Div(
    **{"x-data": "focusTrapModal(false)"},
    Button("Open", **{"@click": "open()"}),
    Div(
        **{"x-show": "isOpen", "@keydown": "handleKeydown($event)", "x-ref": "modal"},
        # Modal content
        Button("Close", **{"@click": "close()"}),
    ),
)
```

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
- LS: 📖
- LP: 🛤️

---

## Safe Zone CSS Usage

### Mobile Bottom Navigation

Replace hardcoded padding with safe zone class:

```python
# Old:
Div(cls="pb-20")

# New:
Div(cls="mobile-bottom-nav")
```

### Content Padding

For content that might be clipped by notches:

```python
Div(cls="safe-content px-4 py-6")
```

---

## Live Region Usage

### Announce Content Updates

Add `data-live-announce` to HTMX targets:

```python
# In HTMX swap targets:
Div(
    id="results",
    hx_get="/api/search",
    hx_trigger="input delay:500ms",
    **{"data-live-announce": "Search results updated"},
)
```

### Custom Announcements

For dynamic announcements:

```javascript
// In JavaScript:
const liveRegion = document.getElementById('live-region');
liveRegion.textContent = 'Task completed';
setTimeout(() => liveRegion.textContent = '', 1000);
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
4. DaisyUI alert classes available?

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

### Focus Trap Not Working

**Check:**
1. Modal has `x-ref="modal"`?
2. `@keydown="handleKeydown($event)"` added?
3. Focusable elements exist in modal?
4. Alpine initialized properly?

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

Always use:
```python
Div(**{"x-data": "focusTrapModal(false)", "x-ref": "modal"})
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
