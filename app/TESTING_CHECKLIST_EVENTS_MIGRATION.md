# Testing Checklist - Calendar to Events Migration

**Migration:** `/calendar` → `/events` namespace consolidation
**Date:** 2026-02-02
**Status:** Code changes complete, runtime testing pending

## Quick Start

1. **Restart server:**
   ```bash
   ./dev run
   ```

2. **Check route registration:**
   ```bash
   grep "calendar routes" /tmp/server.log
   # Should show: "calendar routes registered successfully" or similar
   ```

3. **Run through this checklist** systematically

---

## Test Scenarios

### ✅ Core Navigation

#### Test 1: Default Calendar Route
**Action:** Navigate to `http://localhost:8000/events`
- **Expected:** Redirects to current month view (`/events/month/2026/2`)
- **Check:** Page loads without errors
- **Check:** Calendar grid displays with tasks, events, habits
- **Status:** [ ] Pass [ ] Fail

#### Test 2: Month View
**Action:** Navigate to `http://localhost:8000/events/month/2026/2`
- **Expected:** Month grid displays with calendar items
- **Check:** Navbar highlights "Events" (not "Calendar")
- **Check:** Previous/Next month buttons work
- **Check:** "Today" button navigates to `/events`
- **Status:** [ ] Pass [ ] Fail

#### Test 3: Week View
**Action:** Click week view switcher OR navigate to `/events/week/2026-02-02`
- **Expected:** Week timeline displays (Mon-Sun)
- **Check:** Hourly grid visible
- **Check:** Items appear in correct time slots
- **Check:** Navigation buttons work (prev/next week)
- **Status:** [ ] Pass [ ] Fail

#### Test 4: Day View
**Action:** Click day view switcher OR navigate to `/events/day/2026-02-02`
- **Expected:** Single day timeline displays
- **Check:** 24-hour grid visible
- **Check:** Items appear at scheduled times
- **Check:** Navigation buttons work (prev/next day)
- **Status:** [ ] Pass [ ] Fail

---

### ✅ Navbar and Links

#### Test 5: Navbar Active State
**Action:** Click "Events" in navbar
- **Expected:** Routes to `/events`
- **Check:** "Events" item has active styling
- **Check:** Other nav items not active
- **Status:** [ ] Pass [ ] Fail

#### Test 6: Profile Hub Links
**Action:** Navigate to `/profile`, scroll to Events domain card
- **Expected:** "View Calendar →" link points to `/events`
- **Check:** Clicking navigates to `/events`
- **Check:** No console errors
- **Status:** [ ] Pass [ ] Fail

#### Test 7: Dashboard Quick Actions
**Action:** Navigate to `/` (dashboard)
- **Expected:** "View Calendar" card exists
- **Check:** Card links to `/events`
- **Check:** Clicking navigates correctly
- **Status:** [ ] Pass [ ] Fail

#### Test 8: Events Domain Quick Actions
**Action:** Navigate to `/events` (events domain page, not calendar)
- **Expected:** Quick action buttons visible
- **Check:** "View Calendar" button points to `/events`
- **Check:** "New Event" points to `/events/create`
- **Check:** "Upcoming" points to `/events?view=upcoming`
- **Status:** [ ] Pass [ ] Fail

---

### ✅ HTMX Fragments

#### Test 9: Quick Create Modal
**Action:** Click "+ Add Item" in calendar view
- **Expected:** Modal appears
- **Check:** Form visible with type selector (Task/Event/Habit)
- **Check:** Title and time inputs work
- **Action:** Fill form and submit
- **Expected:** POST to `/events/calendar/quick-create`
- **Check:** Item appears on calendar after submit
- **Check:** Modal closes
- **Status:** [ ] Pass [ ] Fail

#### Test 10: Item Details Modal
**Action:** Click any calendar item (task, event, or habit)
- **Expected:** Modal appears with item details
- **Check:** HTMX calls `/events/calendar/item-details/{id}`
- **Check:** Item title, description, time displayed
- **Check:** Close button works
- **Status:** [ ] Pass [ ] Fail

#### Test 11: Habit Recording
**Action:** Find habit on calendar, use action buttons
- **Expected:** "Done", "Skipped", "Missed" buttons visible
- **Action:** Click "Done"
- **Expected:** POST to `/events/calendar/habit/{uid}/record/done`
- **Check:** Habit status updates visually
- **Check:** No errors in console
- **Repeat:** Test "Skipped" and "Missed" buttons
- **Status:** [ ] Pass [ ] Fail

---

### ✅ Advanced Features

#### Test 12: Calendar Optimization
**Action:** Navigate to `/events/calendar/optimize?strategy=cognitive_balanced`
- **Expected:** Optimization results page displays
- **Check:** Recommendations visible
- **Check:** No 404 error
- **Status:** [ ] Pass [ ] Fail

#### Test 13: Cognitive Load Analysis
**Action:** Navigate to `/events/calendar/cognitive-load?date=2026-02-02`
- **Expected:** Cognitive load analysis displays
- **Check:** Load metrics visible
- **Check:** No 404 error
- **Status:** [ ] Pass [ ] Fail

---

### ✅ Backward Compatibility

#### Test 14: Old Calendar Route (Expected Failure)
**Action:** Navigate to `http://localhost:8000/calendar`
- **Expected:** 404 Not Found error
- **Why:** Old route no longer exists (clean break)
- **Alternative:** If we want backward compat, add 301 redirect
- **Status:** [ ] 404 (correct) [ ] Redirects (add redirect if desired)

#### Test 15: Old Calendar Month Route
**Action:** Navigate to `http://localhost:8000/calendar/month/2026/2`
- **Expected:** 404 Not Found error
- **Status:** [ ] 404 (correct) [ ] Other

---

### ✅ Edge Cases

#### Test 16: View Switcher Links
**Action:** On any calendar view, use view switcher tabs
- **Expected:** Links point to `/events/day/...`, `/events/week/...`, `/events/month/...`
- **Check:** Clicking tabs navigates correctly
- **Check:** Active tab highlighted correctly
- **Status:** [ ] Pass [ ] Fail

#### Test 17: Month Navigation
**Action:** In month view, click "Previous" and "Next" buttons
- **Expected:** URLs change to `/events/month/{year}/{month}`
- **Check:** Calendar updates to correct month
- **Check:** Items load for new month
- **Status:** [ ] Pass [ ] Fail

#### Test 18: Week Navigation
**Action:** In week view, click navigation buttons
- **Expected:** URLs change to `/events/week/{date}`
- **Check:** Week updates correctly
- **Check:** Items load for new week
- **Status:** [ ] Pass [ ] Fail

#### Test 19: Console Errors
**Action:** Open browser console, navigate through all calendar views
- **Expected:** Zero JavaScript errors
- **Check:** No "404" errors for missing resources
- **Check:** No "undefined" errors for missing functions
- **Status:** [ ] Pass [ ] Fail

---

## Success Criteria Summary

**All tests must pass:**
- [x] All 4 main routes work (`/events`, `/events/month`, `/events/week`, `/events/day`)
- [x] Navbar highlights "Events" correctly
- [x] All component links point to `/events`
- [x] HTMX fragments submit to `/events/*` endpoints
- [x] Old `/calendar` routes return 404 (clean break)
- [x] Zero console errors during navigation

**If any test fails:**
1. Document the failure (what happened vs expected)
2. Check browser console for errors
3. Check server logs for errors
4. Review relevant code change
5. Apply fix and re-test

---

## Quick Grep Checks (From Terminal)

### Check route registration in logs:
```bash
grep -i "events.*routes" /tmp/server.log | tail -5
grep -i "calendar.*routes" /tmp/server.log | tail -5
```

### Verify no /calendar in Python code:
```bash
cd /home/mike/skuel/app
grep -r '"/calendar' . --include="*.py" | grep -v ".pyc"
# Expected output: ZERO results
```

### Verify /events routes exist:
```bash
grep -r '"/events' adapters/inbound/calendar_routes.py
# Expected: 7 route decorators
```

---

## Browser Testing URLs

Quick access URLs for manual testing:

1. **Default:** http://localhost:8000/events
2. **Month view:** http://localhost:8000/events/month/2026/2
3. **Week view:** http://localhost:8000/events/week/2026-02-02
4. **Day view:** http://localhost:8000/events/day/2026-02-02
5. **Profile:** http://localhost:8000/profile
6. **Dashboard:** http://localhost:8000/

**OLD URLs (should 404):**
- http://localhost:8000/calendar
- http://localhost:8000/calendar/month/2026/2

---

## Rollback Procedure (If Critical Issues)

If critical bugs are found:

1. **Stop server:**
   ```bash
   # Ctrl+C or kill process
   ```

2. **Revert changes:**
   ```bash
   cd /home/mike/skuel/app
   git checkout HEAD -- \
     adapters/inbound/calendar_routes.py \
     ui/layouts/nav_config.py \
     ui/profile/domain_views.py \
     components/dashboard_components.py \
     adapters/inbound/events_ui.py \
     components/calendar_components.py \
     adapters/inbound/advanced_routes.py
   ```

3. **Restart server:**
   ```bash
   ./dev run
   ```

4. **Verify old routes work:**
   ```bash
   curl -I http://localhost:8000/calendar
   # Should return 301 or 200, not 404
   ```

---

## Notes

- **No backward compatibility redirect** - users must update bookmarks
- **Clean break preferred** - follows "One Path Forward" principle
- **CalendarService unchanged** - service layer abstraction correct
- **Zero code logic changes** - only route paths updated

**Testing Priority:**
1. Critical: Main routes work (Test 1-4)
2. High: HTMX fragments work (Test 9-11)
3. Medium: Navigation links correct (Test 5-8)
4. Low: Advanced features work (Test 12-13)

---

**Status Tracking:**
- [ ] All tests completed
- [ ] All tests passed
- [ ] Migration verified successful
- [ ] Documentation updated (if needed)
