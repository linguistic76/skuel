# Profile UI Components

*Last updated: 2026-02-03*

**Location:** `/ui/profile/`

This directory contains the Profile Hub UI components, implementing a custom `/nous`-style sidebar with configuration-driven domain statistics.

## Overview

The Profile Hub provides a unified view of all user activity and curriculum domains with:
- Custom collapsible sidebar (256px → 48px)
- Real-time domain statistics (count, active, status)
- Configuration-driven pattern (eliminates code duplication)
- Responsive design (mobile drawer, desktop sidebar)

## Files

| File | Purpose | Lines |
|------|---------|-------|
| `layout.py` | Sidebar layout & page wrapper | 390 |
| `domain_stats_config.py` | Configuration-driven stats extraction | 247 |
| `badges.py` | Status & count badge components | 183 |
| `domain_views.py` | Domain-specific content views | 2200 |
| `__init__.py` | Public exports | 35 |

## Key Patterns

### 1. Configuration-Driven Domain Statistics

**Problem:** Repetitive if-elif blocks for calculating domain stats from `UserContext` (80 lines).

**Solution:** Configuration-based extraction with named functions.

**Implementation:**

```python
# /ui/profile/domain_stats_config.py
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

class StatusCalculator(Protocol):
    def __call__(self, *args: int) -> str: ...

@dataclass(frozen=True)
class DomainStatsConfig:
    count_fn: Callable[[UserContext], int]
    active_fn: Callable[[UserContext], int]
    status_fn: StatusCalculator
    status_args_fn: Callable[[UserContext], tuple[int, ...]]

# Configuration dictionary (6 activity domains)
DOMAIN_STATS_CONFIG: dict[str, DomainStatsConfig] = {
    "tasks": DomainStatsConfig(
        count_fn=tasks_count,
        active_fn=tasks_active,
        status_fn=DomainStatus.calculate_tasks_status,
        status_args_fn=tasks_status_args,
    ),
    # ... 5 more domains
}
```

**Usage:**

```python
# Clean 11-line lookup (replaces 80-line if-elif)
config = DOMAIN_STATS_CONFIG.get(slug)
if config:
    count = config.count_fn(context)
    active = config.active_fn(context)
    status_args = config.status_args_fn(context)
    status = config.status_fn(*status_args)
```

**Benefits:**
- **86% line reduction** (80 → 11 lines in route logic)
- **Type-safe** with MyPy enforcement
- **SKUEL012 compliant** (named functions, not lambdas)
- **DRY compliant** (single source of truth)
- **Easy extension** (add domain = config entry, no route changes)

**Edge Cases:**
- Habits: `active = count` (all active habits counted)
- Events: First status arg = 0 (missed_today not tracked separately)
- Principles: Uses int decision counts, not UIDs
- Learning: Custom status function with prerequisite logic

**Tests:** `/tests/unit/ui/test_domain_stats_config.py` (31 tests, 100% passing)

### 2. Sidebar Layout (Unified)

**Pattern:** Collapsible sidebar using unified `SidebarPage()` component.

```python
from ui.patterns.sidebar import SidebarItem, SidebarPage

# Build sidebar items
items = [
    SidebarItem("Overview", "/profile", "overview", icon="📊"),
    SidebarItem("Shared", "/profile/shared", "shared", icon="📬"),
    SidebarItem("Knowledge", "/profile/knowledge", "knowledge", icon="📚"),
]

# Create page
return await SidebarPage(
    content=main_content,
    items=items,
    active="overview",
    title=user_display_name or "Your Profile",
    subtitle="Profile",
    storage_key="profile-sidebar",
    item_renderer=_profile_item_renderer,  # Custom renderer for badges
    title_href="/profile",
    request=request,
    active_page="profile/hub",
)
```

**Features:**
- Fixed 256px sidebar (collapses to 48px on desktop)
- Mobile: Horizontal DaisyUI tabs (no drawer/overlay)
- localStorage persistence via Alpine.js `collapsibleSidebar` + `Alpine.store()`
- Smooth Tailwind transitions (300ms)
- Chevron toggle button with screen reader announcements

**Files:**
- `/ui/patterns/sidebar.py` - Unified sidebar component
- `/ui/profile/layout.py` - Profile-specific `create_profile_page()` wrapper
- `/static/js/skuel.js` (lines 917-953) - `collapsibleSidebar` Alpine component

**See:** `@custom-sidebar-patterns` for complete implementation guide

### 3. Domain Status Badges

**Component:** `DomainStatus` calculator + `StatusBadge` UI

```python
from ui.profile.badges import DomainStatus, StatusBadge, CountBadge

# Status calculation
status = DomainStatus.calculate_tasks_status(
    overdue_count=2,
    blocked_count=1,
)  # Returns: "warning" (overdue > 0)

# Status badge (colored dot)
StatusBadge(status)  # 🟢 healthy, 🟡 warning, 🔴 critical

# Count badge
CountBadge(count=10, active=3)  # "3/10"
```

**Status Thresholds:**

| Domain | Critical | Warning | Healthy |
|--------|----------|---------|---------|
| Tasks | overdue > 3 OR blocked > 5 | overdue > 0 OR blocked > 0 | Otherwise |
| Events | missed_today > 0 | missed_week > 0 | Otherwise |
| Goals | at_risk > 0 | stalled > 0 | Otherwise |
| Habits | at_risk > 2 | at_risk > 0 | Otherwise |
| Principles | against > aligned | aligned < against * 2 | Otherwise |
| Choices | pending > 5 | pending > 0 | Otherwise |

## Adding a New Domain

**Step 1:** Create extractor functions in `domain_stats_config.py`:

```python
def projects_count(ctx: UserContext) -> int:
    """Calculate total project count."""
    return len(ctx.active_project_uids) + len(ctx.completed_project_uids)

def projects_active(ctx: UserContext) -> int:
    """Calculate active project count."""
    return len(ctx.active_project_uids)

def projects_status_args(ctx: UserContext) -> tuple[int]:
    """Extract status args for projects."""
    return (len(ctx.overdue_projects),)
```

**Step 2:** Add configuration entry:

```python
DOMAIN_STATS_CONFIG["projects"] = DomainStatsConfig(
    count_fn=projects_count,
    active_fn=projects_active,
    status_fn=DomainStatus.calculate_projects_status,
    status_args_fn=projects_status_args,
)
```

**Step 3:** Add status calculator in `badges.py`:

```python
@staticmethod
def calculate_projects_status(overdue_count: int) -> str:
    """Calculate projects domain health status."""
    if overdue_count > 5:
        return "critical"
    elif overdue_count > 0:
        return "warning"
    return "healthy"
```

**Done!** No changes needed in route logic.

## Architecture Decisions

### Why Configuration-Driven?

**Before (2026-02-02):**
- 80 lines of repetitive if-elif blocks in `user_profile_ui.py`
- Adding domain = 8-line block in route file
- DRY violation (same pattern × 6 domains)

**After (2026-02-03):**
- 11-line config lookup in routes
- Adding domain = 3 functions + 1 config entry (no route changes)
- Single source of truth

**Refactoring Metrics:**
- Lines reduced: 60 removed, 26 added (57% net reduction in routes)
- Configuration file: 247 lines (reusable for all domains)
- Tests: 31 comprehensive tests (100% passing)
- Type safety: 100% (MyPy zero errors)

### Why Named Functions (Not Lambdas)?

**SKUEL012 Compliance:** "No lambda expressions - use named functions"

```python
# ❌ Would violate SKUEL012
"status_args": lambda ctx: (len(ctx.overdue_task_uids), len(ctx.blocked_task_uids))

# ✅ Compliant with SKUEL012
def tasks_status_args(ctx: UserContext) -> tuple[int, int]:
    """Extract status args for tasks (overdue_count, blocked_count)."""
    return (len(ctx.overdue_task_uids), len(ctx.blocked_task_uids))
```

**Benefits:**
- Type hints for MyPy enforcement
- Docstrings for self-documentation
- Better stack traces in errors
- IDE autocomplete support

## Related Documentation

- [/docs/patterns/UI_COMPONENT_PATTERNS.md](/docs/patterns/UI_COMPONENT_PATTERNS.md) - Complete UI patterns guide
- [/CLAUDE.md](/CLAUDE.md#ui-component-pattern) - Quick reference
- [/docs/architecture/UNIFIED_USER_ARCHITECTURE.md](/docs/architecture/UNIFIED_USER_ARCHITECTURE.md) - UserContext details

## Migration History

| Date | Change | Impact |
|------|--------|--------|
| 2026-02-01 | Profile Hub custom sidebar implemented | Replaced legacy ProfileLayout |
| 2026-02-03 | Configuration-driven stats pattern | Eliminated 80-line if-elif blocks |

## Future Enhancements

Potential improvements for consideration:

1. **Dynamic Status Thresholds:** Make thresholds configurable per user/admin settings
2. **Trend Indicators:** Show 7-day trend arrows (↑ improving, ↓ declining, → stable)
3. **Domain Health Score:** Aggregate status into 0-100 overall health score
4. **Quick Actions:** Add inline actions to sidebar items (e.g., "Add Task")
5. **Notification Badges:** Integrate with messaging system for alerts

---

**See Also:**
- [@base-page-architecture](/.claude/skills/base-page-architecture/SKILL.md) - BasePage patterns
- [@custom-sidebar-patterns](/.claude/skills/custom-sidebar-patterns/SKILL.md) - Sidebar implementation guide
