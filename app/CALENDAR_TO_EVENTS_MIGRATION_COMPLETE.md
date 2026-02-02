# Calendar to Events Migration - Complete

**Date:** 2026-02-02
**Status:** ✅ Complete - One Path Forward Achieved

## Summary

Successfully replaced `/calendar` namespace with `/events` as the canonical path for the unified temporal calendar view. This implements true "One Path Forward" with zero redirects and minimal complexity.

## Changes Made

### Phase 1: Route Path Updates (calendar_routes.py)

**Removed redirect:**
- Line 348-358: Deleted `/events` → `/calendar` redirect entirely

**Updated route decorators:**
- Line 348: `@rt("/events")` - Default calendar view
- Line 354: `@rt("/events/month/{year}/{month}")` - Month view grid
- Line 417: `@rt("/events/week/{date_str}")` - Week timeline
- Line 489: `@rt("/events/day/{date_str}")` - Day timeline
- Line 669: `@rt("/events/calendar/quick-create")` - Quick create modal
- Line 744: `@rt("/events/calendar/habit/{habit_uid}/record/{status}")` - Habit recording
- Line 816: `@rt("/events/calendar/item-details/{item_id}")` - Item details modal
- Line 616: `@rt("/api/events/calendar/reschedule", methods=["PATCH"])` - API reschedule

**Updated navbar highlighting:**
- Lines 376, 445, 511: Changed `active_page="calendar"` → `active_page="events"` (3 occurrences)

**Updated navigation links in calendar_routes.py:**
- All `href="/calendar"` → `href="/events"`
- All `href=f"/calendar/month/` → `href=f"/events/month/`
- All `href=f"/calendar/week/` → `href=f"/events/week/`
- All `href=f"/calendar/day/` → `href=f"/events/day/`

**Updated HTMX target:**
- Line 278: `hx-post: f"/calendar/habit/{item.source_uid}/complete"` → `f"/events/calendar/habit/{item.source_uid}/complete"`

### Phase 2: Navigation Config (ui/layouts/nav_config.py)

**Line 40:**
```python
# BEFORE
NavItem("Calendar", "/calendar", "calendar"),

# AFTER
NavItem("Events", "/events", "events"),
```

**Changes:**
- Display name: "Calendar" → "Events"
- Link: `/calendar` → `/events`
- Page key: `"calendar"` → `"events"`

### Phase 3: Component Links

**ui/profile/domain_views.py:**
- Lines 818, 821, 1440: All `/calendar` → `/events` (3 occurrences)

**components/dashboard_components.py:**
- Line 87: `href="/calendar"` → `href="/events"`

**adapters/inbound/events_ui.py:**
- Lines 98-100: Updated quick actions
  - `/calendar/create` → `/events/create`
  - `/calendar` → `/events`
  - `/calendar?view=upcoming` → `/events?view=upcoming`

**components/calendar_components.py:**
- All `"hx-get": f"/calendar/item-details/` → `"hx-get": f"/events/calendar/item-details/` (3 occurrences)
- All `"hx-post": f"/calendar/habit/` → `"hx-post": f"/events/calendar/habit/` (3 occurrences)
- `"hx-post": "/calendar/quick-create"` → `"hx-post": "/events/calendar/quick-create"`
- All `f"/calendar/day/` → `f"/events/day/`
- All `f"/calendar/week/` → `f"/events/week/`
- All `f"/calendar/month/` → `f"/events/month/`

**adapters/inbound/advanced_routes.py:**
- Line 48: `@rt("/calendar/optimize")` → `@rt("/events/calendar/optimize")`
- Line 125: `@rt("/calendar/cognitive-load")` → `@rt("/events/calendar/cognitive-load")`

### Phase 4: Verification

**Syntax check:** ✅ All 7 modified Python files compile successfully

**Route verification:**
- 7 main routes under `/events/*`
- 1 API route under `/api/events/calendar/*`
- Zero `/calendar` routes remain

**Remaining `/calendar` references:**
- Documentation files only (`.claude/skills/`, markdown docs)
- No functional code references remaining

## Files Modified

| File | Lines Changed | Type |
|------|---------------|------|
| `adapters/inbound/calendar_routes.py` | ~25 | Route decorators, links, HTMX targets |
| `ui/layouts/nav_config.py` | 1 | Navigation config |
| `ui/profile/domain_views.py` | 3 | Component links |
| `components/dashboard_components.py` | 1 | Dashboard link |
| `adapters/inbound/events_ui.py` | 3 | Quick action links |
| `components/calendar_components.py` | ~13 | HTMX targets, view switcher links |
| `adapters/inbound/advanced_routes.py` | 2 | Advanced feature routes |

**Total:** 7 files, ~48 line changes

## Route Migration Table

### Main UI Routes

| Old Route | New Route | Purpose |
|-----------|-----------|---------|
| `/calendar` | `/events` | Default calendar view (redirects to current month) |
| `/calendar/month/{y}/{m}` | `/events/month/{y}/{m}` | Month view grid |
| `/calendar/week/{date}` | `/events/week/{date}` | Week timeline |
| `/calendar/day/{date}` | `/events/day/{date}` | Day timeline |

### API/Fragment Routes

| Old Route | New Route | Purpose |
|-----------|-----------|---------|
| `/calendar/quick-create` | `/events/calendar/quick-create` | HTMX quick create |
| `/calendar/habit/{uid}/record/{s}` | `/events/calendar/habit/{uid}/record/{s}` | Record habit |
| `/calendar/item-details/{id}` | `/events/calendar/item-details/{id}` | Item details modal |
| `/api/calendar/reschedule` | `/api/events/calendar/reschedule` | API reschedule |
| `/calendar/optimize` | `/events/calendar/optimize` | Calendar optimization |
| `/calendar/cognitive-load` | `/events/calendar/cognitive-load` | Cognitive load analysis |

### Redirect Removed

| Route | Action | Status |
|-------|--------|--------|
| `/events` → `/calendar` | DELETE | ✅ Removed (lines 348-358) |

## Architecture Changes

**What Changed:**
- Route namespace: `/calendar/*` → `/events/*`
- Navbar item: "Calendar" → "Events"
- Active page key: `"calendar"` → `"events"`

**What Stayed the Same:**
- `CalendarService` name (correct abstraction - aggregates temporal items)
- All functionality unchanged
- View components unchanged
- HTMX patterns unchanged

## Why /events is the Right Path

1. **Semantic clarity:** A calendar IS the UI for viewing events
2. **Domain alignment:** Tasks with due dates are "events in time"
3. **Habit integration:** Habits with schedules are "recurring events"
4. **One Path Forward:** Single route namespace, zero redirects
5. **User mental model:** "Events" includes tasks, events, and habits

## Testing Checklist

### ✅ Syntax Verification
- [x] All 7 Python files compile successfully
- [x] No syntax errors

### Manual Testing (To Be Done)

**Primary Routes:**
- [ ] Navigate to `http://localhost:8000/events`
  - Expected: Redirects to current month (`/events/month/2026/2`)
  - Check: Page loads, shows unified calendar
- [ ] Navigate to `/events/month/2026/2`
  - Expected: Month view grid displays
  - Check: Navbar highlights "Events"
- [ ] Navigate to `/events/week/2026-02-02`
  - Expected: Week timeline displays
- [ ] Navigate to `/events/day/2026-02-02`
  - Expected: Day timeline displays

**Navigation:**
- [ ] Click "Events" in navbar
  - Expected: Navigates to `/events`
  - Check: Active state highlights correctly
- [ ] Check Profile Hub domain links
  - Expected: Calendar link points to `/events`
- [ ] Check Dashboard quick actions
  - Expected: View calendar link points to `/events`

**Backward Compatibility:**
- [ ] Navigate to `http://localhost:8000/calendar`
  - Expected: 404 (route no longer exists)
  - Result: Clean break, no redirect loops

**HTMX Fragments:**
- [ ] Test quick-create modal
  - Expected: POST to `/events/calendar/quick-create` works
- [ ] Test habit recording
  - Expected: POST to `/events/calendar/habit/{uid}/record/{status}` works

## Success Criteria

✅ **Implementation Complete:**
- [x] `/events` route created (default calendar view)
- [x] All 7 main routes migrated to `/events/*` namespace
- [x] Navbar updated to "Events" with correct page key
- [x] All component links updated
- [x] All HTMX targets updated
- [x] Redirect removed (no `/events` → `/calendar` redirect)
- [x] Syntax check passes
- [x] Zero `/calendar` references in production code

⏳ **Runtime Verification (Pending Server Restart):**
- [ ] Routes registered successfully
- [ ] Navigation works correctly
- [ ] HTMX fragments functional
- [ ] No 404s or redirect loops

## Risk Assessment

**Risk Level:** ✅ LOW

**Why:**
- Simple path replacement (find/replace)
- No business logic changes
- No service refactoring needed
- All changes verified via syntax check

**Potential Issues:**
- Missed `/calendar` reference → Zero found in production code
- HTMX form targets → All updated systematically
- Redirect loop → Redirect removed entirely, clean break

## Implementation Philosophy

This migration embodies SKUEL's "One Path Forward" principle:

**BEFORE (Complexity):**
- `/events` redirects to `/calendar` (301)
- Two mental models: "events domain" vs "calendar view"
- Redirect adds latency and complexity

**AFTER (Simplicity):**
- `/events` IS the calendar (no redirect)
- One mental model: "events" includes all temporal items
- Direct routing, zero indirection

**Result:** Cleaner architecture, better semantics, faster routing.

## CalendarService Remains Correct

**Service Name:** `CalendarService` - No change needed

**Why:**
- Abstraction is correct: aggregates temporal items across domains
- Implementation detail: routes can live under `/events/*`
- Separation of concerns: service layer ≠ route namespace

**Design Pattern:**
```
Route Layer:     /events/*           (User-facing path)
Service Layer:   CalendarService     (Aggregation abstraction)
Domain Layer:    Tasks, Events, Habits (Business entities)
```

## Next Steps

1. **Server restart:** Apply changes to running application
2. **Manual testing:** Verify all routes and navigation (see checklist)
3. **Monitor logs:** Check for any unexpected 404s or errors
4. **User testing:** Verify bookmarks redirect gracefully (or accept clean break)
5. **Documentation:** Update skill docs if needed (optional)

## Rollback Plan (If Needed)

If critical issues arise:

1. Revert 7 modified files from git
2. Restart server
3. Investigate issue
4. Re-apply changes with fixes

**Git command:**
```bash
git checkout HEAD -- adapters/inbound/calendar_routes.py ui/layouts/nav_config.py ui/profile/domain_views.py components/dashboard_components.py adapters/inbound/events_ui.py components/calendar_components.py adapters/inbound/advanced_routes.py
```

## Notes

- **No backward compatibility redirect added** - clean break preferred
- **Documentation files retain `/calendar`** - examples only, not production code
- **CalendarService name unchanged** - correct abstraction layer
- **All 7 files compile successfully** - syntax verified

---

**Migration Type:** Route namespace consolidation (One Path Forward)
**Impact:** Low (path changes only, zero logic changes)
**Verification:** Syntax check ✅, Runtime testing ⏳
