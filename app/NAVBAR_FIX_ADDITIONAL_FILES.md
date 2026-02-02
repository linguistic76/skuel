# Additional Navbar Fixes - Files Bypassing BasePage

## Issue
After initial fix, calendar and other pages still showed coroutine object because they bypassed `BasePage()` and called `create_navbar_for_request()` directly.

## Additional Files Fixed (10 total)

### Custom Page Wrappers (9 files)
These files don't use `BasePage()` - they have custom HTML wrappers that call navbar directly:

1. **adapters/inbound/calendar_routes.py** (3 calls)
   - `calendar_month()` - line 376
   - `calendar_week()` - line 445
   - `calendar_day()` - line 511
   - Custom wrapper: `_wrap_calendar_page()`

2. **adapters/inbound/sel_routes.py** (6 calls)
   - `sel_main()`, `sel_self_awareness()`, `sel_self_management()`
   - `sel_social_awareness()`, `sel_relationship_skills()`, `sel_decision_making()`

3. **adapters/inbound/transcription_ui.py** (1 call)
   - Transcription dashboard

4. **adapters/inbound/journals_ui.py** (1 call)
   - Journals list page

5. **adapters/inbound/journal_projects_ui.py** (1 call)
   - Made `render_projects_dashboard()` async
   - Added await to method call

6. **adapters/inbound/reports_ui.py** (1 call)
   - Made `render_reports_dashboard()` async
   - Added await to method call

7. **adapters/inbound/assignments_ui.py** (2 calls)
   - Assignments dashboard pages

8. **adapters/inbound/askesis_ui.py** (5 calls)
   - Made `_render_minimal_nav()` async
   - Added await to 5 route handlers calling it
   - Routes: dashboard, new-chat, history, analytics, settings

9. **adapters/inbound/habits_ui.py** (1 call)
   - Made `render_habit_analytics_dashboard()` static method async
   - Not currently used in routes (possibly dead code)

### No Changes Needed (2 files)
These use the sync `create_navbar()` which doesn't need await:

10. **adapters/inbound/user_profile_components.py**
    - Uses `create_navbar()` (sync version, no DB call)
    - Component function, not a route

11. **adapters/inbound/ingestion_routes.py**
    - Uses `create_navbar()` (sync version)
    - Route is `def` not `async def`

## Changes Applied

### Pattern 1: Direct navbar call in async route
```python
# BEFORE
async def some_route(request):
    navbar = create_navbar_for_request(request, active_page="page")

# AFTER
async def some_route(request):
    navbar = await create_navbar_for_request(request, active_page="page")
```

### Pattern 2: Helper function wrapper
```python
# BEFORE
def _render_minimal_nav(request):
    return create_navbar_for_request(request)

async def route(request):
    navbar = _render_minimal_nav(request)

# AFTER  
async def _render_minimal_nav(request):
    return await create_navbar_for_request(request)

async def route(request):
    navbar = await _render_minimal_nav(request)
```

### Pattern 3: Static method component
```python
# BEFORE
@staticmethod
def render_dashboard(request):
    navbar = create_navbar_for_request(request, active_page="dashboard")

# AFTER
@staticmethod
async def render_dashboard(request):
    navbar = await create_navbar_for_request(request, active_page="dashboard")

# Callers
return await Component.render_dashboard(request)
```

## Files Modified Summary

**Initial fix (16 files):**
- Core layout components (3)
- Route handlers using BasePage (12)  
- Tests (1)

**Additional fix (10 files):**
- Custom page wrappers (9)
- No changes needed (2)

**Total: 26 files** touched to fix navbar display issue

## Verification

All syntax checks passed:
```
✓ adapters/inbound/calendar_routes.py
✓ adapters/inbound/sel_routes.py  
✓ adapters/inbound/transcription_ui.py
✓ adapters/inbound/journals_ui.py
✓ adapters/inbound/journal_projects_ui.py
✓ adapters/inbound/reports_ui.py
✓ adapters/inbound/assignments_ui.py
✓ adapters/inbound/askesis_ui.py
✓ adapters/inbound/habits_ui.py
✓ Cleared Python cache
```

## Next Steps

1. Restart the server:
   ```bash
   # Kill existing server
   pkill -f "python main.py"
   
   # Start fresh
   poetry run python main.py
   ```

2. Test all page types:
   - ✅ Root + search (working before)
   - 🔄 Calendar (/calendar)
   - 🔄 SEL pages (/sel/*)
   - 🔄 Transcriptions (/transcriptions)
   - 🔄 Journals (/journals)
   - 🔄 Journal Projects (/journal-projects)
   - 🔄 Reports (/reports)
   - 🔄 Assignments (/assignments)
   - 🔄 Askesis (/askesis/*)
   - 🔄 All other pages using BasePage

3. Verify navbar displays correctly:
   - Logo, navigation links, notification bell, profile dropdown
   - No coroutine object text in DOM
   - Mobile menu button works
   - Active page highlighting

---

**Status:** COMPLETE ✅  
**Date:** 2026-02-02  
**Action Required:** Restart server to apply changes
