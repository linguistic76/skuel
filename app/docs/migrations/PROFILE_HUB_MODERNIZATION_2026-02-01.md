# Profile Hub Modernization - Complete

> **Note (2026-02-09):** The `profile_sidebar.css`, `profile_sidebar.js`, and `build_profile_sidebar()` described below were superseded by the unified Tailwind + Alpine.js sidebar in commit `949f201`. See `@custom-sidebar-patterns`.

**Date:** 2026-02-01
**Status:** ✅ Complete (sidebar files superseded 2026-02-09)
**Migration:** Legacy ProfileLayout → Modern BasePage + Custom Sidebar → Unified SidebarPage

---

## Summary

Migrated Profile Hub from legacy `ProfileLayout` class to modern `BasePage` architecture with a custom `/nous`-style sidebar. Implemented SKUEL's "One Path Forward" philosophy by completely removing legacy code with zero deprecation period.

---

## Phase 1: UX Harmonization (Implementation)

### New Files Created (3)

1. **`/static/css/profile_sidebar.css` (2.5KB)**
   - Fixed sidebar with collapse animation
   - Smooth CSS transitions (transform 0.3s ease)
   - Mobile responsive (full-width drawer <1024px)
   - Desktop collapses to 48px edge

2. **`/static/js/profile_sidebar.js` (1.7KB)**
   - `toggleProfileSidebar()` vanilla JavaScript function
   - localStorage persistence (`profile-sidebar-collapsed`)
   - Mobile overlay behavior
   - Window resize handler

3. **Custom layout implementation in `/ui/profile/layout.py`**
   - `build_profile_sidebar()` function (105 lines)
   - Refactored `create_profile_page()` to use BasePage (70 lines)

### Modified Files (3)

1. **`/ui/profile/layout.py`**
   - Added `build_profile_sidebar()` - extracts sidebar building logic
   - Refactored `create_profile_page()` - now uses BasePage with custom layout
   - Added `request: Request | None` parameter for auto-detection
   - Returns `PageType.STANDARD` with custom container (not HUB)

2. **`/ui/layouts/base_page.py`**
   - Added `profile_sidebar.js` script include

3. **`/adapters/inbound/user_profile_ui.py`**
   - Added `request=request` to both profile route calls (lines 658, 733)

### Architecture Comparison

**Before (Legacy):**
```
ProfileLayout (Div only)
├── create_navbar() - Manual
├── DaisyUI drawer (checkbox + peer)
├── Alpine.js swipe handlers
└── Returns Div, not full HTML
```

**After (Modern):**
```
BasePage (Full Html document)
├── Unified head with all includes
├── Auto navbar via create_navbar_for_request()
├── Custom /nous-style sidebar
└── Pure CSS animations + vanilla JS
```

### UX Features

**Desktop (>1024px):**
- Sidebar visible (256px width)
- Chevron toggle on sidebar right edge
- Collapses to 48px edge, content expands
- State persists via localStorage

**Mobile (≤1024px):**
- Sidebar hidden by default
- Hamburger menu opens drawer
- Semi-transparent overlay
- Smooth slide-in (85% width, max 320px)

---

## Phase 2: One Path Forward (Legacy Cleanup)

### Files Modified (8)

1. **`/ui/profile/layout.py`** (-175 lines)
   - Removed ProfileLayout class entirely
   - Removed ProfileLayout.render() method
   - Removed ProfileLayout._build_sidebar_menu() method
   - Removed unused imports: Input, Label, create_navbar
   - Updated docstring to reflect modern pattern
   - File size: 520 → 345 lines (-34%)

2. **`/ui/profile/__init__.py`**
   - Removed ProfileLayout from imports
   - Removed ProfileLayout from __all__
   - Added build_profile_sidebar to exports

3. **`/adapters/inbound/user_profile_ui.py`**
   - Updated comment: "Uses BasePage with /nous-style sidebar"

4-7. **Route files** (habits_ui.py, events_ui.py, goals_ui.py, todoist_task_components.py)
   - Updated comments: "Profile Hub integration" (was "ProfileLayout integration")

8. **`/ui/admin/layout.py`**
   - Updated comment to avoid ProfileLayout reference

### Code Consolidation

**Before (Two Paths):**
```python
# Legacy path
layout = ProfileLayout(title, domains, ...)
return layout.render(content)  # Returns Div

# Modern path (still wrapping legacy)
return create_profile_page(content, domains, ...)
```

**After (One Path):**
```python
# THE path
return create_profile_page(content, domains, request=request)
```

### Verification Results

- ✅ Zero ProfileLayout references in Python files
- ✅ All imports work correctly
- ✅ Server starts without errors
- ✅ Profile routes functional (401 auth required, as expected)
- ✅ Static CSS/JS accessible (HTTP 200)

---

## Key Achievements

1. ✅ **Unified Architecture** - Profile Hub uses BasePage like all modern pages
2. ✅ **Zero Legacy Code** - ProfileLayout completely removed (175 lines)
3. ✅ **No Deprecation** - Clean removal following "One Path Forward"
4. ✅ **Better UX** - Smooth animations, localStorage persistence
5. ✅ **Simpler Pattern** - Custom sidebar > DaisyUI drawer complexity
6. ✅ **Full Control** - Explicit HTML document, CSS/JS includes

---

## Files Summary

### Created (2)
- `/static/css/profile_sidebar.css` - Sidebar styles
- `/static/js/profile_sidebar.js` - Toggle logic

### Modified (3 core)
- `/ui/profile/layout.py` - New sidebar builder, refactored page creator (-175 lines)
- `/ui/layouts/base_page.py` - Added JS include
- `/adapters/inbound/user_profile_ui.py` - Added request params

### Updated (5 documentation)
- `/ui/profile/__init__.py` - Updated exports
- `/adapters/inbound/{habits,events,goals}_ui.py` - Comment updates
- `/components/todoist_task_components.py` - Comment update
- `/ui/admin/layout.py` - Comment update

### Deleted (0)
- ProfileLayout kept in git history for reference

---

## Philosophy Applied

**SKUEL's One Path Forward:**

> When a better pattern emerges, the old pattern is removed entirely. No legacy wrappers, no deprecation periods, no alternative paths.

**This migration demonstrates:**
- ❌ No `@deprecated` decorators
- ❌ No compatibility shims
- ❌ No "use X instead" comments
- ✅ Clean removal
- ✅ Update all call sites
- ✅ One canonical way

---

## Implementation Details

### Custom Sidebar Builder

```python
def build_profile_sidebar(
    domains: list[ProfileDomainItem],
    active_domain: str = "",
    user_display_name: str = "",
    curriculum_domains: list[ProfileDomainItem] | None = None,
) -> "FT":
    """Build profile sidebar with toggle button and navigation."""
    # Chevron toggle button
    # Sidebar header (profile name)
    # Overview link
    # Activity Domains section (6 domains)
    # Curriculum section (optional)
```

### Modern Page Creator

```python
def create_profile_page(
    content: Any,
    domains: list[ProfileDomainItem],
    request: "Request | None" = None,  # NEW
    # ... other params
) -> "FT":
    """Create profile page using BasePage with custom sidebar."""
    sidebar = build_profile_sidebar(domains, ...)
    overlay = Div(cls="profile-overlay", onclick="toggleProfileSidebar()")

    wrapped_content = Div(
        overlay,
        sidebar,
        Div(content, cls="profile-content"),
        cls="profile-container",
    )

    return BasePage(
        content=wrapped_content,
        page_type=PageType.STANDARD,  # Not HUB
        extra_css=["/static/css/profile_sidebar.css"],
        request=request,
    )
```

---

## Pattern Evolution

### Layout System History

1. **FrankenUI Era** (pre-2026)
   - MonsterUI components
   - UK-* classes
   - Component DSL overhead

2. **DaisyUI Migration** (January 2026)
   - Phase 1-5 complete
   - MonsterUI removed
   - Type-safe wrappers

3. **BasePage Unification** (January 2026)
   - BasePage for consistency
   - PageType.STANDARD and HUB
   - /insights, /docs modernized

4. **Profile Harmonization** (February 2026) ← THIS
   - Profile Hub uses BasePage
   - Custom /nous-style sidebar
   - Legacy ProfileLayout removed

### One Path Forward: 4 Domains

| Domain | Layout Pattern | Status |
|--------|---------------|--------|
| **Profile Hub** | BasePage + Custom Sidebar | ✅ Modern (2026-02-01) |
| **Admin Dashboard** | BasePage + HUB type | ✅ Modern |
| **Documentation** | BasePage + Custom Layout | ✅ Modern (/nous pattern) |
| **Activity Domains** | BasePage + STANDARD | ✅ Modern |

---

## Related Documentation

- `/docs/patterns/UI_COMPONENT_PATTERNS.md` - Updated with Profile Hub pattern
- `/docs/architecture/UX_MIGRATION_PLAN.md` - Phase 6 complete
- `CLAUDE.md` - UI Component Pattern section updated
- `/docs/migrations/PROFILE_UX_HARMONIZATION_COMPLETE.md` - Detailed implementation
- `/docs/migrations/ONE_PATH_FORWARD_PROFILE_CLEANUP.md` - Detailed cleanup

---

## Conclusion

Profile Hub now uses the modern BasePage architecture with a clean, performant custom sidebar. This eliminates technical debt, provides better UX consistency, and demonstrates SKUEL's commitment to "One Path Forward" - when a better pattern emerges, the old one is removed completely.

**No deprecation. No backward compatibility. Just evolution.**
