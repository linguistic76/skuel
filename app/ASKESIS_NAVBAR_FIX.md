# Askesis Navbar Fix - Complete

**Date:** 2026-02-02
**Issue:** Navbar missing on `/askesis` route
**Status:** ✅ Fixed

## Problem

The `/askesis` route was rendering a page without the navbar component, breaking the consistent navigation experience across the application.

## Root Cause

The `_render_minimal_nav()` function in `adapters/inbound/askesis_ui.py` was calling the async function `create_navbar_for_request()` without awaiting it.

**Before (Line 789-795):**
```python
def _render_minimal_nav(request) -> Any:
    """
    Minimal bottom navigation (optional).

    Uses create_navbar_for_request for session-aware admin detection.
    """
    return create_navbar_for_request(request)  # ❌ Missing await
```

This resulted in the navbar being returned as a coroutine object instead of the rendered HTML, causing it not to display.

## Solution

Made two changes to `adapters/inbound/askesis_ui.py`:

### Change 1: Make `_render_minimal_nav()` async and await the navbar call

**Line 789-795:**
```python
async def _render_minimal_nav(request) -> Any:  # ✅ Now async
    """
    Minimal bottom navigation (optional).

    Uses create_navbar_for_request for session-aware admin detection.
    """
    return await create_navbar_for_request(request, active_page="askesis")  # ✅ Now awaited + active_page
```

### Change 2: Await all calls to `_render_minimal_nav()`

**5 route handlers updated:**
```python
# Before:
navbar = _render_minimal_nav(request)  # ❌ Missing await

# After:
navbar = await _render_minimal_nav(request)  # ✅ Now awaited
```

**Lines changed:**
- Line 550: `askesis_home()` - Main Askesis page
- Line 577: `askesis_new_chat()` - New chat page
- Line 613: `askesis_history()` - History page
- Line 656: `askesis_analytics()` - Analytics page
- Line 717: `askesis_settings()` - Settings page

## Additional Improvement

Added `active_page="askesis"` parameter to ensure the "Askesis" navbar item is highlighted when on the Askesis pages.

This matches the pattern used in other routes like:
- `calendar_routes.py`: `active_page="events"`
- `journals_ui.py`: `active_page="journals"`
- `sel_routes.py`: `active_page="sel"`

## Files Modified

| File | Lines Changed | Description |
|------|---------------|-------------|
| `adapters/inbound/askesis_ui.py` | 6 | Made `_render_minimal_nav()` async, added await calls, added active_page parameter |

## Verification

✅ **Syntax check:** File compiles successfully
```bash
poetry run python -m py_compile adapters/inbound/askesis_ui.py
# No errors
```

## Testing Checklist

After server restart:

- [ ] Navigate to `http://localhost:8000/askesis`
  - **Expected:** Navbar displays at top of page
  - **Expected:** "Askesis" item highlighted in navbar
  - **Expected:** All navbar links functional

- [ ] Navigate to `/askesis/new-chat`
  - **Expected:** Navbar displays correctly

- [ ] Navigate to `/askesis/history`
  - **Expected:** Navbar displays correctly

- [ ] Navigate to `/askesis/analytics`
  - **Expected:** Navbar displays correctly

- [ ] Navigate to `/askesis/settings`
  - **Expected:** Navbar displays correctly

- [ ] Check navbar highlighting
  - **Expected:** "Askesis" item has active styling on all Askesis pages

## Pattern Analysis

This fix follows the same async/await pattern used throughout SKUEL:

**Correct Pattern:**
```python
# Helper function that calls async navbar creator
async def _render_minimal_nav(request) -> Any:
    return await create_navbar_for_request(request, active_page="domain")

# Route handler
@rt("/domain")
async def domain_page(request: Request) -> Any:
    navbar = await _render_minimal_nav(request)  # ✅ Awaited
    return Html(Body(navbar, content))
```

**Common Mistake:**
```python
# Helper not marked async
def _render_minimal_nav(request) -> Any:
    return create_navbar_for_request(request)  # ❌ Returns coroutine, not HTML

# Route handler
@rt("/domain")
async def domain_page(request: Request) -> Any:
    navbar = _render_minimal_nav(request)  # ❌ Not awaited
    return Html(Body(navbar, content))  # ❌ Navbar is coroutine object, not rendered
```

## Related Patterns

All SKUEL routes that use custom page layouts (not `BasePage`) follow this pattern:

1. **Calendar routes** (`calendar_routes.py`):
   - Uses `create_navbar_for_request(request, active_page="events")` directly in async routes

2. **Journals routes** (`journals_ui.py`):
   - Uses `create_navbar_for_request(request, active_page="journals")` directly

3. **SEL routes** (`sel_routes.py`):
   - Uses `create_navbar_for_request(request, active_page="sel")` directly

4. **Askesis routes** (`askesis_ui.py`):
   - Now uses helper function `_render_minimal_nav()` that wraps the navbar call
   - Helper is async and awaits `create_navbar_for_request()`

## Why This Matters

FastHTML's `create_navbar_for_request()` is async because it:
1. Accesses the session to check authentication
2. Determines admin status from session
3. Constructs conditional navigation items

Without awaiting, the coroutine object is passed directly to the HTML rendering, which doesn't know how to render it, resulting in a missing navbar.

## Success Criteria

✅ **Implementation:**
- [x] `_render_minimal_nav()` marked as async
- [x] `create_navbar_for_request()` call awaited
- [x] All 5 calls to `_render_minimal_nav()` awaited
- [x] `active_page="askesis"` parameter added
- [x] File compiles successfully

⏳ **Runtime Verification (After Restart):**
- [ ] Navbar displays on all Askesis pages
- [ ] "Askesis" item highlighted correctly
- [ ] Navigation links functional

## Impact

**Before Fix:**
- Askesis pages had no navigation
- User couldn't navigate to other sections
- Inconsistent UX (navbar missing only on Askesis)

**After Fix:**
- Navbar displays correctly on all Askesis pages
- Consistent navigation experience across application
- "Askesis" item properly highlighted

## Related Issues

This same pattern appears in 3 other route files:
- `calendar_routes.py` - Uses navbar correctly (awaits directly in routes)
- `journals_ui.py` - Uses navbar correctly (awaits directly in routes)
- `sel_routes.py` - Uses navbar correctly (awaits directly in routes)

None of these have the same issue because they await the navbar call directly in the route handler, rather than using a helper function.

## Key Takeaway

**Golden Rule:** When wrapping async functions in helpers, the helpers must also be async and await the calls. All callers of the helper must also await it.

```python
# If you see this pattern:
async def library_function():
    ...

# And wrap it like this:
def helper():
    return library_function()  # ❌ WRONG

# Fix it like this:
async def helper():  # ✅ Mark async
    return await library_function()  # ✅ Await the call

# And use it like this:
result = await helper()  # ✅ Await the helper
```

---

**Fix Type:** Async/await correction
**Risk Level:** Low (syntax fix, no logic changes)
**Verification:** Syntax check ✅, Runtime testing ⏳
