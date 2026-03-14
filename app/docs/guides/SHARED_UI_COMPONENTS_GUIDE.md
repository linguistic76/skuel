---
title: Shared UI Components Guide
updated: 2026-01-29
status: current
category: guides
tags: [components, guide, guides, shared]
related: [AUTH_PATTERNS.md]
---

# Shared UI Components Guide

**Version:** 2.0.0 (January 2026)
**Status:** Production Ready
**Location:** `/ui/patterns/entity_dashboard.py`

> **Related:** For page-level layout (page types, container widths, spacing tokens), see the **Unified UX Design System** in `/docs/patterns/UI_COMPONENT_PATTERNS.md`. This guide covers dashboard *content* patterns.

## Overview

The Shared UI Components library provides reusable dashboard patterns for all SKUEL domains. It eliminates duplicate code across 15+ UI files and ensures consistent user experience.

**Version 2.0.0 Changes (January 2026):**
- ✅ Migrated to MonsterUI (FrankenUI + Tailwind) component library
- ✅ Type-safe component imports (Button, Card, Input, Select with typed variants)
- ✅ Enum-based variants replace string classes (ButtonT.primary instead of "btn-primary")
- ✅ Backwards compatibility maintained for action config dictionaries
- ✅ Updated wizard path (`/habits/wizard/step1` instead of `/habits/create`)

### Core Principle

**"Write once, render everywhere"**

All dashboards (Tasks, Habits, Goals, Events, Finance, etc.) share the same underlying patterns:
- Stats cards (MonsterUI Card component)
- Quick action buttons (MonsterUI Button with typed variants)
- Entity lists/grids
- Filters and search (MonsterUI Select/Input)
- Empty states
- Detail views

Instead of copying these patterns 15 times, we implement them once in `SharedUIComponents`.

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    SharedUIComponents                          │
│  (Generic patterns - works for ANY entity type)               │
├──────────────────────────────────────────────────────────────┤
│  • render_entity_dashboard()  ← Main dashboard layout        │
│  • render_stats_cards()       ← Statistics display           │
│  • render_quick_actions()     ← Action buttons               │
│  • render_entity_list()       ← List view with filters       │
│  • render_entity_grid()       ← Grid view layout             │
│  • render_category_filter()   ← Filter dropdown              │
│  • render_search_bar()        ← Search input                 │
│  • render_empty_state()       ← No items state               │
│  • render_detail_view()       ← Single entity details        │
└──────────────────────────────────────────────────────────────┘
                              ▲
                              │
                    Uses (composition)
                              │
┌──────────────────────────────────────────────────────────────┐
│              Domain-Specific UI Components                    │
│  (Only what's unique to each domain)                         │
├──────────────────────────────────────────────────────────────┤
│  • HabitUIComponents.render_habit_card()                     │
│  • TaskUIComponents.render_task_card()                       │
│  • GoalUIComponents.render_goal_card()                       │
│  etc.                                                         │
└──────────────────────────────────────────────────────────────┘
```

## Quick Start

**Import Pattern (January 2026):**
```python
from ui.patterns.entity_dashboard import SharedUIComponents

# MonsterUI components are imported internally by SharedUIComponents
# You don't need to import them directly unless building custom renderers:
from ui.buttons import Button, ButtonT
from ui.cards import Card
from ui.forms import Input, Select
from ui.layout import Size
```

### 1. Basic Dashboard

```python
from ui.patterns.entity_dashboard import SharedUIComponents

def render_habits_dashboard(habits, stats):
    return SharedUIComponents.render_entity_dashboard(
        title="🎯 Habit Tracker",
        stats={
            'total': {'label': 'Total Habits', 'value': 42, 'color': 'blue'},
            'active': {'label': 'Active', 'value': 38, 'color': 'green'}
        },
        entities=habits,
        entity_renderer=HabitUIComponents.render_habit_card,
        quick_actions=[
            {'label': '➕ New Habit', 'href': '/habits/wizard/step1', 'variant': 'primary'}
        ],
        categories=["health", "productivity", "learning"],
        filter_endpoint="/habits/filter"
    )
```

### 2. Stats Cards Only

```python
stats = SharedUIComponents.render_stats_cards({
    'total': {'label': 'Total Tasks', 'value': 125, 'color': 'blue'},
    'completed': {'label': 'Completed', 'value': 78, 'color': 'green'},
    'overdue': {'label': 'Overdue', 'value': 12, 'color': 'red'}
})
```

### 3. Entity Grid Layout

```python
grid = SharedUIComponents.render_entity_grid(
    entities=goals,
    entity_renderer=lambda g: GoalCard(g),
    columns=3
)
```

### 4. Empty State

```python
empty = SharedUIComponents.render_empty_state(
    icon="📋",
    title="No tasks yet",
    message="Create your first task to get started",
    action={'label': 'Create Task', 'href': '/tasks/create', 'variant': 'primary'}
)
```

## Component Reference

### render_entity_dashboard()

**Purpose:** Complete dashboard layout with stats, actions, and entity list.

**Returns:** Complete `Html` document (not `Div`) using `build_head()` from `base_page.py`.

> **Important:** This function returns a full `Html(build_head(...), Body(...))` document to ensure consistent HTMX versioning across all pages. The `<head>` is provided by `build_head()` — the single source of truth for all vendor library versions (MonsterUI, HTMX, Alpine.js, etc.). See [UI Component Patterns - Page Layout Architecture](/docs/patterns/UI_COMPONENT_PATTERNS.md#page-layout-architecture-critical) for details.

**Parameters:**
- `title` (str): Dashboard title with emoji (e.g., "🎯 Habit Tracker")
- `stats` (Dict[str, Dict]): Statistics cards configuration
- `entities` (List[Any]): List of entity instances
- `entity_renderer` (Callable): Function that renders a single entity
- `quick_actions` (List[Dict], optional): Action button configurations
- `categories` (List[str], optional): Category names for filtering
- `show_filter` (bool, default=True): Show category filter dropdown
- `filter_endpoint` (str, optional): HTMX endpoint for filtering
- `navbar` (Any, optional): Custom navbar (default: auto-generated from request)
- `request` (Request, optional): **RECOMMENDED** - Starlette request for automatic auth detection
- `current_user` (str, optional): Fallback user display name (if no request)
- `is_authenticated` (bool, default=False): Fallback auth status (if no request)
- `active_page` (str, optional): Current page slug for navbar highlighting

**Authentication (January 2026):**

The `request` parameter is the **recommended** way to handle navbar authentication. When provided, the navbar automatically detects:
- User's logged-in status from session
- User's display name for dropdown
- Admin role status (shows both "Admin Dashboard" and "Profile Hub")

```python
# ✅ RECOMMENDED: Pass request for automatic auth detection
dashboard = SharedUIComponents.render_entity_dashboard(
    title="📋 Task Manager",
    stats=stats,
    entities=tasks,
    entity_renderer=TaskCard,
    request=request,           # Auto-detects auth from session
    active_page="tasks",       # Highlights "Tasks" in navbar
)

# ❌ LEGACY: Manual auth parameters (still supported)
dashboard = SharedUIComponents.render_entity_dashboard(
    title="📋 Task Manager",
    stats=stats,
    entities=tasks,
    entity_renderer=TaskCard,
    current_user="user.mike",   # Manual fallback
    is_authenticated=True,      # Manual fallback
    active_page="tasks",
)
```

**Example:**
```python
@rt("/tasks")
async def tasks_dashboard(request):
    user_uid = require_authenticated_user(request)
    tasks = await tasks_service.list(user_uid=user_uid)

    dashboard = SharedUIComponents.render_entity_dashboard(
        title="📋 Task Manager",
        stats={
            'total': {'label': 'Total', 'value': 125, 'color': 'blue'},
            'urgent': {'label': 'Urgent', 'value': 8, 'color': 'red'}
        },
        entities=tasks,
        entity_renderer=lambda t: TaskCard(t),
        quick_actions=[
            {'label': '➕ New', 'href': '/tasks/create', 'variant': 'primary'},
            {'label': '📊 Analytics', 'href': '/tasks/analytics', 'variant': 'secondary'}
        ],
        request=request,        # RECOMMENDED
        active_page="tasks",
    )
    return dashboard
```

### render_stats_cards()

**Purpose:** Display statistics in responsive card grid.

**Parameters:**
- `stats` (Dict[str, Dict]): Mapping of stat_key to `{label, value, color}`

**Color Options:** blue, green, orange, purple, red, gray, yellow, indigo

**Layout:** Responsive grid (1 col mobile → 2 cols tablet → 4 cols desktop)

**Example:**
```python
stats = SharedUIComponents.render_stats_cards({
    'total': {'label': 'Total Habits', 'value': 42, 'color': 'blue'},
    'streaks': {'label': 'Active Streaks', 'value': 18, 'color': 'orange'},
    'completion': {'label': 'Rate', 'value': '87%', 'color': 'green'}
})
```

### render_quick_actions()

**Purpose:** Action buttons for common operations.

**Parameters:**
- `actions` (List[Dict]): Button configurations with `label`, `href`/`hx_get`, `class`

**Example:**
```python
actions = SharedUIComponents.render_quick_actions([
    {'label': '➕ New Task', 'href': '/tasks/create', 'variant': 'primary'},
    {'label': '📊 Analytics', 'hx_get': '/analytics', 'hx_target': '#main', 'variant': 'secondary'},
    {'label': '⚙️ Settings', 'href': '/settings', 'variant': 'ghost'}
])
```

### render_entity_list()

**Purpose:** List view with optional category filter.

**Parameters:**
- `entities` (List[Any]): Entity instances
- `entity_renderer` (Callable): Renders single entity
- `categories` (List[str], optional): Filter categories
- `filter_endpoint` (str, optional): HTMX filter endpoint
- `empty_message` (str, default="No items found"): Empty state text
- `list_id` (str, default="entity-list"): HTML id for HTMX targeting

**Example:**
```python
list_view = SharedUIComponents.render_entity_list(
    entities=tasks,
    entity_renderer=lambda t: TaskCard(t),
    categories=["work", "personal", "urgent"],
    filter_endpoint="/tasks/filter"
)
```

### render_entity_grid()

**Purpose:** Grid layout (alternative to list view).

**Parameters:**
- `entities` (List[Any]): Entity instances
- `entity_renderer` (Callable): Renders single entity
- `columns` (int, default=3): Grid columns (1-4)
- `empty_message` (str): Empty state text

**Example:**
```python
grid = SharedUIComponents.render_entity_grid(
    entities=goals,
    entity_renderer=lambda g: GoalCard(g),
    columns=3
)
```

### render_category_filter()

**Purpose:** Dropdown filter for categories.

**Parameters:**
- `categories` (List[str]): Category names
- `filter_endpoint` (str): HTMX endpoint
- `target_id` (str, default="#entity-list"): HTMX target
- `label` (str, default="Filter by Category"): Filter label

### render_search_bar()

**Purpose:** Search input with HTMX live search.

**Parameters:**
- `search_endpoint` (str): HTMX search endpoint
- `target_id` (str, default="#search-results"): HTMX target
- `placeholder` (str, default="Search..."): Input placeholder

**Example:**
```python
search = SharedUIComponents.render_search_bar(
    search_endpoint="/tasks/search",
    target_id="#task-results",
    placeholder="Search tasks..."
)
```

### render_empty_state()

**Purpose:** Empty state with icon and optional action.

**Parameters:**
- `icon` (str): Emoji icon
- `title` (str): Empty state title
- `message` (str): Explanation message
- `action` (Dict, optional): Action button config

**Example:**
```python
empty = SharedUIComponents.render_empty_state(
    icon="📋",
    title="No tasks yet",
    message="Create your first task to get started",
    action={'label': 'Create Task', 'href': '/tasks/create', 'variant': 'primary'}
)
```

### render_detail_view()

**Purpose:** Single entity detail page layout.

**Parameters:**
- `title` (str): Page title
- `entity_card` (Any): Main entity card component
- `sections` (List[Dict]): Additional sections with `title` and `content`
- `actions` (List[Dict], optional): Action buttons
- `back_link` (str, optional): Back navigation link

**Example:**
```python
detail = SharedUIComponents.render_detail_view(
    title="Task Details",
    entity_card=task_card,
    sections=[
        {'title': 'Progress', 'content': progress_widget},
        {'title': 'Comments', 'content': comments_list}
    ],
    actions=[{'label': 'Edit', 'href': '/tasks/123/edit'}],
    back_link="/tasks"
)
```

## Migration Guide

### Before: Manual Composition

```python
# habits_ui.py - BEFORE (84 lines)
@staticmethod
def render_habits_dashboard(habits, stats):
    navbar = UnifiedComponents.create_navbar()

    # Manual stats cards (30 lines)
    stats_cards = Div(
        Card(
            Div(
                Span(str(stats['total']), cls="text-3xl font-bold text-blue-600"),
                P("Total Habits", cls="text-sm text-gray-600")
            ),
            cls="p-4 text-center"
        ),
        # ... 3 more cards ...
        cls="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8"
    )

    # Manual action buttons (25 lines)
    action_buttons = Div(
        Button("➕ New", variant=ButtonT.primary, ...),
        Button("📊 Analytics", variant=ButtonT.secondary, ...),
        # ... 3 more buttons ...
        cls="flex gap-4 justify-center mb-6"
    )

    # Manual entity list (30 lines)
    entity_list = Card(...)

    return Div(navbar, H1(...), stats_cards, action_buttons, entity_list)
```

### After: Shared Components

```python
# habits_ui.py - AFTER (25 lines)
@staticmethod
def render_habits_dashboard(habits, stats):
    return SharedUIComponents.render_entity_dashboard(
        title="🎯 Habit Tracker",
        stats={
            'total': {'label': 'Total', 'value': stats['total'], 'color': 'blue'},
            'active': {'label': 'Active', 'value': stats['active'], 'color': 'green'}
        },
        entities=habits,
        entity_renderer=HabitUIComponents.render_habit_card,
        quick_actions=[
            {'label': '➕ New', 'href': '/habits/create', 'variant': 'primary'},
            {'label': '📊 Analytics', 'href': '/habits/analytics', 'variant': 'secondary'}
        ]
    )
```

**Lines Saved:** 84 - 25 = **59 lines (70% reduction)**

### Migration Checklist

For each `*_ui.py` file:

- [ ] Identify dashboard rendering function
- [ ] Extract stats card data
- [ ] Extract quick actions
- [ ] Extract entity renderer
- [ ] Replace with `SharedUIComponents.render_entity_dashboard()`
- [ ] Test HTMX interactions
- [ ] Verify responsive layout
- [ ] Update tests

## Impact Analysis

### Code Reduction

| File | Before | After | Savings |
|------|--------|-------|---------|
| habits_ui.py | 84 lines | 25 lines | 59 lines (70%) |
| tasks_ui.py | 78 lines | 22 lines | 56 lines (72%) |
| goals_ui.py | 72 lines | 24 lines | 48 lines (67%) |
| events_ui.py | 68 lines | 20 lines | 48 lines (71%) |
| finance_ui.py | 82 lines | 28 lines | 54 lines (66%) |
| **TOTAL (15 files)** | **~1200 lines** | **~380 lines** | **~820 lines (68%)** |

### Consistency Benefits

1. **Unified Design Language**
   - All dashboards have identical structure
   - Stats cards use consistent colors
   - Action buttons positioned uniformly

2. **Single Source of Truth**
   - Update stats card styling → 15 dashboards change
   - Fix mobile responsiveness → all domains benefit
   - Add accessibility → applies globally

3. **Maintainability**
   - One place to add new patterns
   - Easier onboarding for new developers
   - Reduced testing surface area

### Developer Experience

**Creating a new dashboard:**

| Approach | Time | Lines | Consistency |
|----------|------|-------|-------------|
| Copy-paste | 2-3 hours | ~80 lines | ❌ Drift risk |
| Shared components | 30 minutes | ~25 lines | ✅ Guaranteed |

**Time savings:** 85% reduction in dashboard creation time

## Best Practices

### 1. Use Shared Components for Common Patterns

✅ **DO:**
```python
# Use SharedUIComponents for stats, actions, lists
dashboard = SharedUIComponents.render_entity_dashboard(...)
```

❌ **DON'T:**
```python
# Don't manually compose stats cards
stats = Div(Card(...), Card(...), Card(...))  # This is what SharedUIComponents does!
```

### 2. Keep Domain-Specific Logic in Domain Components

✅ **DO:**
```python
class HabitUIComponents:
    @staticmethod
    def render_habit_card(habit):
        # Habit-specific: identity progress bars, celebration modals
        identity_component = AtomicHabitsComponents.render_identity_progress_bar(...)
        return Card(card, identity_component, buttons)
```

❌ **DON'T:**
```python
# Don't try to make shared components domain-aware
SharedUIComponents.render_entity_dashboard(
    show_identity_bars=True  # NO! This is domain-specific
)
```

### 3. Use Composition, Not Inheritance

✅ **DO:**
```python
# Compose shared components in domain components
def render_habits_dashboard(habits, stats):
    return SharedUIComponents.render_entity_dashboard(
        entity_renderer=HabitUIComponents.render_habit_card  # Composition
    )
```

❌ **DON'T:**
```python
# Don't create subclasses
class HabitUIComponents(SharedUIComponents):  # NO!
    pass
```

### 4. Transform Data, Don't Duplicate Logic

✅ **DO:**
```python
# Transform domain data to shared format
stats_formatted = {
    'total': {'label': 'Total', 'value': len(habits), 'color': 'blue'}
}
SharedUIComponents.render_stats_cards(stats_formatted)
```

❌ **DON'T:**
```python
# Don't create habit-specific stats renderer
HabitUIComponents.render_habit_stats(habits)  # Duplication!
```

## Testing

### Unit Tests

```python
def test_render_stats_cards():
    stats = {
        'total': {'label': 'Total', 'value': 42, 'color': 'blue'}
    }
    result = SharedUIComponents.render_stats_cards(stats)

    assert 'text-blue-600' in str(result)
    assert '42' in str(result)
    assert 'Total' in str(result)
```

### Integration Tests

```python
def test_dashboard_renders_with_real_habits(habits_service):
    habits = await habits_service.backend.list(limit=10)
    stats = calculate_stats(habits)

    dashboard = SharedUIComponents.render_entity_dashboard(
        title="Test Dashboard",
        stats=stats,
        entities=habits.value,
        entity_renderer=lambda h: Card(P(h.name))
    )

    assert dashboard is not None
    assert len(habits.value) > 0
```

## Future Enhancements

### Planned (Q4 2025)

1. **Mobile-Optimized Components**
   - `render_mobile_dashboard()` for touch-first UX
   - Swipe gestures for entity cards
   - Bottom sheet actions

2. **Advanced Filters**
   - `render_multi_select_filter()` for multiple categories
   - Date range picker
   - Search with facets

3. **Data Visualization**
   - `render_trend_chart()` for time series
   - `render_progress_ring()` for completion %
   - `render_heatmap()` for activity patterns

4. **Accessibility**
   - ARIA labels on all interactive elements
   - Keyboard navigation
   - Screen reader optimization

### Community Requests

Track feature requests: [GitHub Issues](https://github.com/your-repo/issues)

## Troubleshooting

### Stats Cards Not Showing

**Problem:** Stats cards render as empty

**Solution:** Verify stats dict format
```python
# ✅ Correct
stats = {'total': {'label': 'Total', 'value': 42, 'color': 'blue'}}

# ❌ Wrong
stats = {'total': 42}  # Missing label and color
```

### HTMX Filter Not Working

**Problem:** Category filter doesn't update entity list

**Solution:** Ensure list has correct `id` matching `target_id`
```python
# Filter targets #entity-list
filter_endpoint="/habits/filter"

# List must have matching id
Div(..., id="entity-list")
```

### Entity Renderer Errors

**Problem:** `entity_renderer` throws exceptions

**Solution:** Check entity type and renderer signature
```python
# ✅ Correct
entity_renderer=lambda h: HabitCard(h)

# ❌ Wrong
entity_renderer=HabitCard  # Missing lambda/call
```

## Support

- **Documentation:** `/docs/SHARED_UI_COMPONENTS_GUIDE.md`
- **Examples:** `/examples/habits_ui_refactored_example.py`
- **Source:** `/ui/patterns/entity_dashboard.py`
- **Tests:** `/tests/test_shared_ui_components.py` (TBD)

## Changelog

### v2.0.0 (January 2026) - MonsterUI Migration
- **BREAKING:** Migrated to MonsterUI wrapper component library
- Replaced all `Div(..., cls="card bg-base-100...")` with `Card(..., cls="...")`
- Replaced button string classes with typed enums (`ButtonT.primary`, `ButtonT.secondary`, etc.)
- Replaced input/select classes with MonsterUI classes (`uk-input`, `uk-select`)
- Added backwards compatibility parser for existing action configs using `"variant": "primary"` style
- Updated wizard paths (`/habits/wizard/step1` instead of `/habits/create`)
- All calling code continues to work with string-based action configs (internal translation to enums)

### v2.1.0 (March 2026)
- `render_entity_dashboard()` now uses `build_head()` from `base_page.py` instead of constructing its own `<head>`
- Fixes stale version reference (now uses canonical version from `ui/theme.py` via `monster_headers()`)
- Removes reference to non-existent `skuel.css` (correct file is `main.css`)
- Single source of truth: all version updates to `build_head()` automatically propagate

### v1.2.0 (January 2026)
- **BREAKING:** `render_entity_dashboard()` now returns `Html` document instead of `Div`
- Changed return type to ensure consistent HTMX 1.9.10 versioning across all pages
- Prevents navigation issues caused by FastHTML's default HTMX 2.0.7 wrapping
- No code changes required for callers - function signature unchanged

### v1.1.0 (January 2026)
- Added `request` parameter to `render_entity_dashboard()` for automatic auth detection
- Added `current_user`, `is_authenticated`, `active_page` parameters for navbar control
- Navbar now uses `create_navbar_for_request()` when request is provided
- Admin users see both "Admin Dashboard" and "Profile Hub" links
- Updated all Activity Domain UI routes to pass request through layouts

### v1.0.0 (October 2025)
- Initial release
- Complete dashboard patterns
- Stats cards, actions, entity lists
- Filter and search components
- Empty states and detail views
- Documentation and examples

---

**Last Updated:** March 6, 2026
**Maintained By:** SKUEL Core Team
**License:** MIT
**Component Library:** MonsterUI (FrankenUI + Tailwind) with type-safe enums (v2.0.0+)
