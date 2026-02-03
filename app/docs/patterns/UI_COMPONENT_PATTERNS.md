---
title: UI Component Patterns
updated: '2026-02-03'
category: patterns
related_skills:
  - accessibility-guide
  - base-page-architecture
  - custom-sidebar-patterns
  - daisyui
  - html-htmx
  - html-navigation
  - js-alpine
  - skuel-component-composition
  - tailwind-css
related_docs: []
---
# UI Component Patterns

*Last updated: 2026-02-01*

**Core Principle:** "BasePage for consistency, custom layouts for special cases"

## Quick Start

**Core Skills:** [@base-page-architecture](../../.claude/skills/base-page-architecture/SKILL.md), [@daisyui](../../.claude/skills/daisyui/SKILL.md), [@tailwind-css](../../.claude/skills/tailwind-css/SKILL.md), [@html-htmx](../../.claude/skills/html-htmx/SKILL.md), [@js-alpine](../../.claude/skills/js-alpine/SKILL.md)

**Advanced Skills:** [@custom-sidebar-patterns](../../.claude/skills/custom-sidebar-patterns/SKILL.md), [@html-navigation](../../.claude/skills/html-navigation/SKILL.md), [@skuel-component-composition](../../.claude/skills/skuel-component-composition/SKILL.md), [@accessibility-guide](../../.claude/skills/accessibility-guide/SKILL.md)

For hands-on implementation:
1. Invoke `@base-page-architecture` for BasePage patterns and page types
2. Invoke `@daisyui` for pre-built accessible UI components
3. Invoke `@tailwind-css` for utility-first styling
4. Invoke `@html-htmx` for server communication patterns
5. Invoke `@js-alpine` for client-side interactivity
6. Invoke `@custom-sidebar-patterns` for advanced navigation
7. Invoke `@accessibility-guide` for WCAG 2.1 Level AA compliance
8. Continue below for complete component architecture

**Related Documentation:**
- [/ui/profile/layout.py](/ui/profile/layout.py) - Profile Hub custom sidebar example

---

## Overview

SKUEL uses a layered UI component architecture built on Tailwind CSS and DaisyUI 5. This document explains the component system and how to use it.

**Key Files:**
- `/ui/` - SKUEL UI design system (primitives, patterns, layouts, tokens)
- `/ui/layouts/base_page.py` - Unified page wrapper
- `/ui/layouts/page_types.py` - Page type definitions (HUB vs STANDARD)
- `/ui/tokens.py` - Spacing, container, and styling tokens
- `/core/ui/daisy_components.py` - DaisyUI wrappers (legacy, still usable)

---

## Unified UX Design System

**Core Principle:** Two controlled page paradigms with consistent spacing and container widths.

### Page Types

| Type | Sidebar | Container | Use Case |
|------|---------|-----------|----------|
| `STANDARD` | None | `max-w-6xl` centered | Most pages (search, activity domains, forms) |
| `HUB` | Left (w-64) | Flexible | Multi-domain dashboards (Admin Dashboard) |
| `CUSTOM` | STANDARD + custom layout | Flexible | Complex layouts (Profile Hub with /nous-style sidebar) |

**Evolution (2026-02-01):** Profile Hub migrated from legacy `ProfileLayout` to `STANDARD` page type with custom sidebar implementation. This provides more control while maintaining BasePage consistency.

### BasePage Usage

```python
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType

# Standard page (most common)
return BasePage(
    content,
    title="Tasks",
    request=request,
    active_page="tasks",
)

# Hub page with sidebar (Admin Dashboard)
return BasePage(
    content,
    page_type=PageType.HUB,
    sidebar=sidebar_menu,
    title="Admin Dashboard",
    request=request,
)

# Custom sidebar layout (Profile Hub pattern)
from ui.profile.layout import build_profile_sidebar, create_profile_page

sidebar = build_profile_sidebar(domains, active_domain, user_display_name)
return create_profile_page(
    content,
    domains=domain_items,
    request=request,  # Auto-detects auth/admin state
    extra_css=["/static/css/profile_sidebar.css"],
)
```

### Profile Hub Custom Sidebar Pattern

**Added:** 2026-02-01

The Profile Hub uses a custom `/nous`-style sidebar implementation that provides more control than the standard `PageType.HUB` pattern.

**Key Features:**
- Fixed sidebar (256px) with smooth collapse animation
- Pure CSS + vanilla JavaScript (no Alpine.js complexity)
- localStorage persistence of collapsed state
- Mobile: Full-width drawer with overlay
- Desktop: Collapses to 48px edge, chevron toggle button

**Implementation:**
```python
from ui.profile.layout import build_profile_sidebar, create_profile_page
from ui.profile.layout import ProfileDomainItem

# Build domain items for sidebar
domains = [
    ProfileDomainItem(
        name="Tasks",
        slug="tasks",
        icon="✅",
        count=10,
        active_count=3,
        status="healthy",
        href="/profile/tasks",
        insight_count=2,
    ),
    # ... more domains
]

# Create page with custom sidebar
return create_profile_page(
    content=main_content,
    domains=domains,
    active_domain="tasks",  # Highlight active
    user_display_name="John Doe",
    title="Profile Hub",
    request=request,  # Enables auto-detection
)
```

**Files:**
- `/ui/profile/layout.py` - `build_profile_sidebar()`, `create_profile_page()`
- `/static/css/profile_sidebar.css` - Sidebar animations and responsive behavior
- `/static/js/profile_sidebar.js` - Toggle function with localStorage

**Why Custom vs HUB:**
- More control over sidebar collapse behavior
- `/nous`-style toggle pattern (cleaner UX)
- Sidebar state persistence across sessions
- Matches documentation (/nous, /docs) patterns

#### Configuration-Driven Domain Stats

**Added:** 2026-02-03

**Core Principle:** "Configuration over repetition for domain statistics"

The Profile Hub uses a configuration-driven pattern to calculate domain statistics (counts, active counts, status) from `UserContext`, eliminating repetitive if-elif blocks.

**Pattern Benefits:**
- **DRY Compliance:** 80-line if-elif block reduced to 11-line config lookup (86% reduction)
- **Type Safety:** Protocol-based configuration with MyPy enforcement
- **Maintainability:** Adding new domains requires only config changes, no route logic changes
- **SKUEL012 Compliant:** Uses named functions instead of lambdas

**Configuration Structure:**

```python
from ui.profile.domain_stats_config import DOMAIN_STATS_CONFIG

# Configuration lookup replaces if-elif blocks
config = DOMAIN_STATS_CONFIG.get("tasks")
if config:
    count = config.count_fn(context)           # Total items
    active = config.active_fn(context)         # Active/pending items
    status_args = config.status_args_fn(context)  # Args for status calculator
    status = config.status_fn(*status_args)    # "healthy" | "warning" | "critical"
```

**Adding a New Domain:**

```python
# 1. Add extractor functions in /ui/profile/domain_stats_config.py
def projects_count(ctx: UserContext) -> int:
    """Calculate total project count."""
    return len(ctx.active_project_uids) + len(ctx.completed_project_uids)

def projects_active(ctx: UserContext) -> int:
    """Calculate active project count."""
    return len(ctx.active_project_uids)

def projects_status_args(ctx: UserContext) -> tuple[int]:
    """Extract status args for projects."""
    return (len(ctx.overdue_projects),)

# 2. Add configuration entry
DOMAIN_STATS_CONFIG["projects"] = DomainStatsConfig(
    count_fn=projects_count,
    active_fn=projects_active,
    status_fn=DomainStatus.calculate_projects_status,
    status_args_fn=projects_status_args,
)

# 3. Done! No changes needed in user_profile_ui.py route logic
```

**Edge Cases Handled:**
- **Habits:** `active = count` (special case - all active habits are counted)
- **Events:** First status arg hardcoded to 0 (missed_today not tracked separately)
- **Principles:** Uses int values for decisions, not UID lists
- **Learning:** Custom status function with complex prerequisite logic
- **Unknown domains:** Fallback to `count=0, active=0, status="healthy"`

**Files:**
- `/ui/profile/domain_stats_config.py` - Configuration and extractor functions
- `/adapters/inbound/user_profile_ui.py` - Uses configuration in `_build_domain_items()`
- `/tests/unit/ui/test_domain_stats_config.py` - 31 tests covering all domains

**Type Safety:**
```python
from ui.profile.domain_stats_config import DomainStatsConfig, StatusCalculator

class StatusCalculator(Protocol):
    """Protocol for domain status calculator functions."""
    def __call__(self, *args: int) -> str: ...

@dataclass(frozen=True)
class DomainStatsConfig:
    count_fn: Callable[[UserContext], int]
    active_fn: Callable[[UserContext], int]
    status_fn: StatusCalculator
    status_args_fn: Callable[[UserContext], tuple[int, ...]]
```

**Before Refactoring (80 lines):**
```python
# Repetitive if-elif blocks in user_profile_ui.py
if slug == "tasks":
    count = len(context.active_task_uids) + len(context.completed_task_uids)
    active = len(context.active_task_uids)
    status = DomainStatus.calculate_tasks_status(
        len(context.overdue_task_uids),
        len(context.blocked_task_uids),
    )
elif slug == "events":
    # ... 8 more lines
# ... 4 more similar blocks
```

**After Refactoring (11 lines):**
```python
# Clean configuration lookup
config = DOMAIN_STATS_CONFIG.get(slug)
if config:
    count = config.count_fn(context)
    active = config.active_fn(context)
    status_args = config.status_args_fn(context)
    status = config.status_fn(*status_args)
else:
    count = 0
    active = 0
    status = "healthy"
```

### Design Tokens

```python
from ui.tokens import Spacing, Container, Card

# Container widths
Container.STANDARD  # "max-w-6xl mx-auto" (default)
Container.NARROW    # "max-w-4xl mx-auto"
Container.WIDE      # "max-w-7xl mx-auto"

# Spacing patterns
Spacing.PAGE        # "p-6 lg:p-8"
Spacing.SECTION     # "space-y-8"
Spacing.CONTENT     # "space-y-4"

# Card styling
Card.BASE           # "bg-base-100 border border-base-200 rounded-lg"
Card.INTERACTIVE    # Card.BASE + hover shadow
Card.PADDING        # "p-6"
```

### Page Header & Section Header

```python
from ui.patterns import PageHeader, SectionHeader

# Page header with optional subtitle and actions
PageHeader("Tasks", subtitle="Manage your daily work")
PageHeader("Goals", actions=Button("Create Goal", variant=ButtonT.primary))

# Section header with optional action link
SectionHeader("Recent Tasks")
SectionHeader("Active Goals", action=A("View All", href="/goals"))
```

### CSS Spacing Tokens

Defined in `/static/css/input.css`:

```css
:root {
  --space-page: 1.5rem;        /* p-6 */
  --space-page-lg: 2rem;       /* lg:p-8 */
  --space-section: 2rem;       /* Between sections */
  --space-content: 1rem;       /* Between items */
  --space-card: 1.5rem;        /* Card padding */
}
```

---

## Import Pattern (DaisyUI Wrappers)

```python
# Pure HTML elements from FastHTML
from fasthtml.common import H1, H2, H3, P, A, Form, Li, Ul

# SKUEL DaisyUI wrappers
from core.ui.daisy_components import (
    # Buttons
    Button, ButtonT,
    # Cards
    Card, CardBody, CardTitle, CardActions, CardT,
    # Feedback
    Alert, AlertT,
    Badge, BadgeT,
    # Forms
    Input, InputT, Select, Textarea,
    FormControl, Label, LabelText,
    Checkbox, Radio, Toggle, Range,
    # Modals
    Modal, ModalBox, ModalAction, ModalBackdrop,
    # Progress & Loading
    Progress, ProgressT, RadialProgress,
    Loading, LoadingT,
    # Layout
    Div, Span, Grid, Container,
    DivHStacked, DivVStacked, DivFullySpaced, DivCentered,
    # Navigation
    Navbar, NavbarStart, NavbarCenter, NavbarEnd,
    Menu, MenuItem, Tabs, Tab,
    # Dropdown
    Dropdown, DropdownTrigger, DropdownContent,
    # Data Display
    Table, Thead, Tbody, Tr, Th, Td,
    Stats, Stat, StatTitle, StatValue, StatDesc, StatFigure,
    Avatar, AvatarGroup,
    # Utility
    Tooltip, Divider, Size,
)

# Theme for app initialization
from core.ui.theme import daisy_headers, Theme
```

---

## Theme Headers

All SKUEL pages use `daisy_headers()` for consistent styling:

```python
from fasthtml.common import fast_app
from core.ui.theme import daisy_headers, Theme

# Default (light theme)
app, rt = fast_app(hdrs=daisy_headers())

# With custom theme
app, rt = fast_app(hdrs=daisy_headers(theme=Theme.dark))

# With PWA support
from core.ui.theme import pwa_headers
app, rt = fast_app(hdrs=(*daisy_headers(), *pwa_headers()))
```

**What `daisy_headers()` includes:**
- Meta viewport tags
- DaisyUI 5 CSS (CDN)
- Tailwind CSS (CDN)
- HTMX 1.9.10
- Alpine.js 3.14.8 (self-hosted)
- Lucide icons (optional)
- SKUEL custom CSS/JS

---

## Type-Safe Variants

SKUEL uses Python enums for type-safe DaisyUI variants:

### Buttons

```python
# Primary action
Button("Submit", variant=ButtonT.primary)

# Secondary/Ghost
Button("Cancel", variant=ButtonT.ghost)
Button("Back", variant=ButtonT.secondary)

# Semantic colors
Button("Delete", variant=ButtonT.error)
Button("Save", variant=ButtonT.success)
Button("Warn", variant=ButtonT.warning)

# With size
Button("Small", variant=ButtonT.primary, size=Size.sm)
Button("Large", variant=ButtonT.primary, size=Size.lg)

# Outline style
Button("Outline", variant=ButtonT.primary, outline=True)

# With HTMX
Button("Load More", variant=ButtonT.ghost, hx_get="/items?page=2", hx_target="#list")
```

### Alerts

```python
Alert("Operation successful!", variant=AlertT.success)
Alert("Warning: Check your input", variant=AlertT.warning)
Alert("Error occurred", variant=AlertT.error)
Alert("Info message", variant=AlertT.info)
```

### Badges

```python
Badge("Active", variant=BadgeT.success)
Badge("Pending", variant=BadgeT.warning)
Badge("High", variant=BadgeT.error)
Badge("5", variant=BadgeT.primary, size=Size.sm)
```

### Progress

```python
Progress(value=75, variant=ProgressT.primary)
Progress(value=100, variant=ProgressT.success)
RadialProgress(75, variant=ButtonT.success)
```

---

## Card Pattern

**Always wrap card content in `CardBody`:**

```python
Card(
    CardBody(
        H2("Title"),
        P("Description"),
        Button("Action", variant=ButtonT.primary)
    ),
    cls="hover:shadow-lg"  # Additional classes optional
)
```

### Card with Actions

```python
Card(
    CardBody(
        CardTitle(H3("Task Name")),
        P("Task description here", cls="text-base-content/70"),
        CardActions(
            Button("Edit", variant=ButtonT.ghost, size=Size.sm),
            Button("Complete", variant=ButtonT.success, size=Size.sm),
        )
    )
)
```

### Card Variants

```python
# Bordered card
Card(CardBody(...), variant=CardT.bordered)

# Compact card (less padding)
Card(CardBody(...), variant=CardT.compact)

# Side layout (horizontal)
Card(CardBody(...), variant=CardT.side)
```

---

## Form Components

### Basic Form

```python
from fasthtml.common import Form

Form(
    FormControl(
        Label(LabelText("Email")),
        Input(type="email", name="email", placeholder="Enter email"),
    ),
    FormControl(
        Label(LabelText("Password")),
        Input(type="password", name="password"),
    ),
    FormControl(
        Label(LabelText("Remember me")),
        Checkbox(name="remember", variant=ButtonT.primary),
    ),
    Button("Sign In", variant=ButtonT.primary, type="submit"),
    hx_post="/login",
    hx_target="#result",
)
```

### Select and Textarea

```python
from fasthtml.common import Option

FormControl(
    Label(LabelText("Priority")),
    Select(
        Option("Select...", value=""),
        Option("High", value="high"),
        Option("Medium", value="medium"),
        Option("Low", value="low"),
        name="priority"
    ),
)

FormControl(
    Label(LabelText("Description")),
    Textarea(name="description", rows="4", placeholder="Enter description..."),
)
```

### Input Variants

```python
Input(variant=InputT.bordered)  # Default
Input(variant=InputT.primary)
Input(variant=InputT.error)  # For validation errors
Input(size=Size.sm)  # Small input
```

---

## Layout Helpers

### Flex Layouts

```python
# Horizontal stack
DivHStacked(
    Button("Left"),
    Button("Right"),
    gap=2
)

# Vertical stack
DivVStacked(
    H1("Title"),
    P("Description"),
    gap=4
)

# Space between (e.g., header with title and actions)
DivFullySpaced(
    H2("Dashboard"),
    Button("Add New", variant=ButtonT.primary),
)

# Centered content
DivCentered(
    Loading(size=Size.lg),
    cls="h-screen"
)
```

### Grid Layout

```python
# Responsive grid (1 col mobile, 2 on sm, 3 on md+)
Grid(
    Card(CardBody(H3("Card 1"))),
    Card(CardBody(H3("Card 2"))),
    Card(CardBody(H3("Card 3"))),
    cols=3,
    gap=4
)

# Fixed columns (no responsive)
Grid(
    Card(...), Card(...),
    cols=2,
    responsive=False
)
```

### Container

```python
Container(
    H1("Page Title"),
    P("Content"),
    size="7xl"  # max-width
)
```

---

## Modal Pattern

```python
# Modal definition
Modal("confirm-modal",
    ModalBox(
        H3("Confirm Delete"),
        P("Are you sure you want to delete this item?"),
        ModalAction(
            Button("Cancel", variant=ButtonT.ghost,
                   onclick="document.getElementById('confirm-modal').close()"),
            Button("Delete", variant=ButtonT.error,
                   hx_delete="/api/items/123",
                   hx_target="#item-list"),
        )
    ),
    ModalBackdrop(),  # Click outside to close
)

# Open modal with JavaScript
Button("Delete",
       onclick="document.getElementById('confirm-modal').showModal()",
       variant=ButtonT.error)
```

---

## Navigation Components

### Navbar

```python
Navbar(
    NavbarStart(
        A("SKUEL", href="/", cls="text-xl font-bold")
    ),
    NavbarCenter(
        Menu(
            MenuItem(A("Dashboard", href="/", cls="active")),
            MenuItem(A("Tasks", href="/tasks")),
            MenuItem(A("Goals", href="/goals")),
            horizontal=True
        )
    ),
    NavbarEnd(
        Button("Logout", variant=ButtonT.ghost, size=Size.sm)
    )
)
```

### Tabs

```python
Tabs(
    Tab("All", active=True, hx_get="/tasks?filter=all", hx_target="#task-list"),
    Tab("Active", hx_get="/tasks?filter=active", hx_target="#task-list"),
    Tab("Completed", hx_get="/tasks?filter=completed", hx_target="#task-list"),
    boxed=True
)
```

### Dropdown

```python
Dropdown(
    DropdownTrigger(Button("Options", variant=ButtonT.ghost)),
    DropdownContent(
        MenuItem(A("Edit", href="#")),
        MenuItem(A("Duplicate", href="#")),
        MenuItem(A("Delete", href="#", cls="text-error")),
    ),
    end=True  # Align to right
)
```

---

## Data Display

### Stats

```python
Stats(
    Stat(
        StatFigure(Span("", cls="text-3xl"), i="lucide-check-circle"),
        StatTitle("Tasks Completed"),
        StatValue("42"),
        StatDesc("This week"),
    ),
    Stat(
        StatTitle("Goals Progress"),
        StatValue("78%"),
        StatDesc("On track"),
    ),
)
```

### Tables

```python
Table(
    Thead(
        Tr(
            Th("Name"),
            Th("Status"),
            Th("Actions"),
        )
    ),
    Tbody(
        Tr(
            Td("Task 1"),
            Td(Badge("Active", variant=BadgeT.success)),
            Td(Button("Edit", variant=ButtonT.ghost, size=Size.xs)),
        ),
        Tr(
            Td("Task 2"),
            Td(Badge("Pending", variant=BadgeT.warning)),
            Td(Button("Edit", variant=ButtonT.ghost, size=Size.xs)),
        ),
    ),
    zebra=True
)
```

---

## Loading States

```python
# Spinner (default)
Loading(size=Size.md)

# Different types
Loading(variant=LoadingT.dots)
Loading(variant=LoadingT.ring)
Loading(variant=LoadingT.bars)

# HTMX loading indicator
Button("Save",
       variant=ButtonT.primary,
       hx_post="/save",
       hx_indicator="#loading")

Div(Loading(size=Size.sm), id="loading", cls="htmx-indicator")
```

---

## SKUEL-Specific Patterns

### Activity Domain Card

```python
def TaskCard(task: Task) -> Any:
    """Render a task card with status and actions."""
    return Card(
        CardBody(
            DivFullySpaced(
                CardTitle(H4(task.title)),
                Badge(task.status.value, variant=_status_badge(task.status)),
            ),
            P(task.description or "No description", cls="text-base-content/70 text-sm"),
            DivHStacked(
                Badge(task.priority.value, variant=_priority_badge(task.priority)),
                Span(f"Due: {task.due_date}", cls="text-xs text-base-content/50") if task.due_date else None,
                gap=2
            ),
            CardActions(
                Button("Edit", variant=ButtonT.ghost, size=Size.sm,
                       hx_get=f"/tasks/{task.uid}/edit", hx_target="#modal"),
                Button("Complete", variant=ButtonT.success, size=Size.sm,
                       hx_post=f"/api/tasks/{task.uid}/complete", hx_target="#task-list"),
            ),
        ),
        cls=f"border-l-4 {_priority_border(task.priority)}"
    )
```

### Empty State

```python
def EmptyState(message: str, action_text: str = None, action_url: str = None) -> Any:
    """Render an empty state message."""
    return DivCentered(
        DivVStacked(
            Span("", data_lucide="inbox", cls="w-16 h-16 text-base-content/30"),
            P(message, cls="text-base-content/60"),
            Button(action_text, variant=ButtonT.primary, hx_get=action_url) if action_text else None,
            gap=4, align="center"
        ),
        cls="py-12"
    )
```

---

## Common Anti-Patterns

### Don't Use Raw DaisyUI Classes on Wrappers

```python
# BAD: Redundant - Button already adds "btn btn-primary"
Button("Click", cls="btn btn-primary")

# GOOD: Use the variant enum
Button("Click", variant=ButtonT.primary)
```

### Don't Mix Old FrankenUI/MonsterUI Patterns

```python
# BAD: Old MonsterUI pattern (removed)
from monsterui.all import Button, Card  # DELETED

# GOOD: Use SKUEL wrappers
from core.ui.daisy_components import Button, Card
```

### Do Use Tailwind for Custom Styling

```python
# GOOD: Tailwind for layout customization
Card(
    CardBody(...),
    cls="mt-4 hover:shadow-lg transition-shadow"
)
```

### Do Add `cls` for Additional Classes

```python
# GOOD: Extra classes via cls parameter
Button("Full Width", variant=ButtonT.primary, cls="w-full")
Badge("New", variant=BadgeT.error, cls="animate-pulse")
```

---

## Responsive Patterns

### Mobile-First Grid

```python
Grid(
    Card(...), Card(...), Card(...),
    cols=3,  # 1 on mobile, 2 on sm, 3 on md+
    responsive=True  # Default
)
```

### Hide/Show by Breakpoint

```python
# Show only on mobile
Div(..., cls="lg:hidden")

# Hide on mobile, show on desktop
Div(..., cls="hidden lg:block")
```

### Drawer for Mobile Navigation

Use the existing `drawer_layout.py` pattern for responsive sidebars.

---

## Activity Domain UI Error Handling Pattern

*Added: 2026-01-24*

**Core Principle:** "Typed params, Result[T] propagation, visible error banners"

All Activity domain UI routes (Tasks, Goals, Habits, Events, Choices, Principles) follow a consistent error-handling pattern that makes failures visible to users instead of silently returning empty lists.

### Pattern Components

#### 1. Typed Query Parameters

```python
from dataclasses import dataclass

@dataclass
class Filters:
    """Typed filters for list queries."""
    status: str
    sort_by: str

@dataclass
class CalendarParams:
    """Typed params for calendar view."""
    calendar_view: str
    current_date: date
```

#### 2. Parsing Helpers

```python
def parse_filters(request) -> Filters:
    """Extract filter parameters from request query params."""
    return Filters(
        status=request.query_params.get("filter_status", "active"),
        sort_by=request.query_params.get("sort_by", "default"),
    )

def parse_calendar_params(request) -> CalendarParams:
    """Extract calendar view parameters."""
    calendar_view = request.query_params.get("calendar_view", "month")
    date_str = request.query_params.get("date", "")

    try:
        current_date = date.fromisoformat(date_str) if date_str else date.today()
    except ValueError:
        current_date = date.today()

    return CalendarParams(calendar_view=calendar_view, current_date=current_date)
```

#### 3. Error Banner Component

```python
def render_error_banner(message: str) -> Div:
    """Render error banner for UI failures."""
    return Div(
        Div(
            P("⚠️ Error", cls="font-bold text-error"),
            P(message, cls="text-sm"),
            cls="alert alert-error",
        ),
        cls="mb-4",
    )
```

#### 4. Data Helpers Return Result[T]

```python
from core.utils.result_simplified import Errors, Result

async def get_all_tasks(user_uid: str) -> Result[list[Any]]:
    """Get all tasks for user."""
    try:
        result = await tasks_service.get_user_tasks(user_uid)
        if result.is_error:
            logger.warning(f"Failed to fetch tasks: {result.error}")
            return result  # Propagate the error
        return Result.ok(result.value or [])
    except Exception as e:
        logger.error(
            "Error fetching all tasks",
            extra={
                "user_uid": user_uid,
                "error_type": type(e).__name__,
                "error_message": str(e),
            },
        )
        return Errors.system(f"Failed to fetch tasks: {e}")

async def get_filtered_tasks(...) -> Result[tuple[list[Any], dict]]:
    """Get filtered and sorted tasks with stats."""
    try:
        tasks_result = await get_all_tasks(user_uid)

        # Check for errors
        if tasks_result.is_error:
            logger.warning(f"Failed to fetch tasks for filtering: {tasks_result.error}")
            return tasks_result  # Propagate the error

        tasks = tasks_result.value
        # ... filtering logic ...
        return Result.ok((tasks, stats))
    except Exception as e:
        logger.error(...)
        return Errors.system(f"Failed to filter tasks: {e}")
```

#### 5. Route Handlers Check Errors

**Main Dashboard:**
```python
@rt("/tasks")
async def tasks_dashboard(request) -> Any:
    user_uid = require_authenticated_user(request)
    view = request.query_params.get("view", "list")

    # Parse using helpers
    filters = parse_filters(request)
    calendar_params = parse_calendar_params(request)

    # Get data with Result[T]
    filtered_result = await get_filtered_tasks(user_uid, filters.status, filters.sort_by)

    # CHECK FOR ERRORS - show banner instead of empty list
    if filtered_result.is_error:
        error_content = Div(
            TasksViewComponents.render_view_tabs(active_view=view),
            render_error_banner(f"Failed to load tasks: {filtered_result.error}"),
            cls=f"{Spacing.PAGE} {Container.WIDE}",
        )
        return create_tasks_page(error_content, request=request)

    # Extract values only after error check
    tasks, stats = filtered_result.value
    # ... render views ...
```

**HTMX Fragments:**
```python
@rt("/tasks/view/list")
async def tasks_view_list(request) -> Any:
    """HTMX fragment for list view."""
    user_uid = require_authenticated_user(request)
    filters = parse_filters(request)

    filtered_result = await get_filtered_tasks(user_uid, filters.status, filters.sort_by)

    # Handle errors (return banner directly for HTMX swap)
    if filtered_result.is_error:
        return render_error_banner(f"Failed to load tasks: {filtered_result.error}")

    tasks, stats = filtered_result.value
    return TasksViewComponents.render_list_view(...)
```

### Benefits

1. **User-visible errors** - Clear error messages instead of empty lists
2. **Debuggability** - Full error context in logs (user_uid, error type, message)
3. **Consistency** - All Activity domains follow same pattern
4. **Type safety** - Dataclasses prevent param extraction errors
5. **Maintainability** - Single pattern to understand across all domains

### Implementation Status

| Domain | Status | Notes |
|--------|--------|-------|
| Tasks | ✅ Complete | Reference implementation |
| Goals | ✅ Complete | Calendar-enabled |
| Habits | ✅ Complete | Calendar-enabled |
| Events | ✅ Complete | Calendar-first design |
| Choices | ✅ Complete | Analytics instead of calendar |
| Principles | ✅ Complete | Analytics + bug fixes applied |

**Reference Files:**
- `/adapters/inbound/tasks_ui.py` - Reference pattern
- `/adapters/inbound/goals_ui.py` - Complete implementation
- `/adapters/inbound/habits_ui.py` - Complete implementation
- `/adapters/inbound/events_ui.py` - Complete implementation
- `/adapters/inbound/choice_ui.py` - Complete implementation
- `/adapters/inbound/principles_ui.py` - Complete implementation

---

## Activity Domain Pure Computation Helpers

*Added: 2026-01-24*

**Core Principle:** "Separate I/O from computation - extract testable pure functions"

Following the error handling refactoring, all Activity domain UI routes were further improved by extracting pure computation functions from monolithic "god helper" orchestrators.

### Problem: God Helper Anti-Pattern

**Before:** Single 50-90 line functions mixing I/O with computation:
```python
async def get_filtered_tasks(...) -> Result[tuple[list[Any], dict[str, int]]]:
    """God helper doing 5 things: fetch, stats, filter, sort."""
    try:
        # 1. Fetch all (I/O) - 10 lines
        tasks_result = await get_all_tasks(user_uid)

        # 2. Calculate stats (computation) - 15 lines
        stats = {"total": len(tasks), "completed": ..., "overdue": ...}

        # 3. Filter by project (computation) - 10 lines
        if project:
            tasks = [t for t in tasks if t.project == project]

        # 4. Filter by status (computation) - 15 lines
        if status_filter == "active":
            tasks = [t for t in tasks if t.status != "completed"]
        # ... more filter cases

        # 5. Sort (computation + complex logic) - 30 lines
        if sort_by == "due_date":
            tasks = sorted(tasks, key=get_task_due_date_sort_key)
        # ... more sort options

        return Result.ok((tasks, stats))
```

**Issues:**
- Cannot unit test stats/filter/sort logic without async mocks
- Single Responsibility Principle violated
- 90 lines doing 5 distinct things
- Difficult to modify one aspect without affecting others

### Solution: Extract Pure Helpers

**Pattern:** Create 3-4 pure, testable functions:

```python
# ========================================================================
# PURE COMPUTATION HELPERS (Testable without mocks)
# ========================================================================

def compute_task_stats(tasks: list[Any]) -> dict[str, int]:
    """
    Calculate task statistics.

    Pure function: testable without database or async.
    """
    today = date.today()
    return {
        "total": len(tasks),
        "completed": sum(1 for t in tasks if t.status == ActivityStatus.COMPLETED),
        "overdue": sum(
            1 for t in tasks
            if t.due_date and t.due_date < today and t.status != ActivityStatus.COMPLETED
        ),
    }


def apply_task_filters(
    tasks: list[Any],
    project: str | None = None,
    status_filter: str = "active",
) -> list[Any]:
    """
    Apply filter criteria to task list.

    Pure function: testable without database or async.
    """
    # Filter: project
    if project:
        tasks = [t for t in tasks if t.project == project]

    # Filter: status
    if status_filter == "active":
        tasks = [t for t in tasks if t.status != ActivityStatus.COMPLETED]
    elif status_filter == "completed":
        tasks = [t for t in tasks if t.status == ActivityStatus.COMPLETED]

    return tasks


def apply_task_sort(tasks: list[Any], sort_by: str = "due_date") -> list[Any]:
    """
    Sort tasks by specified field.

    Pure function: testable without database or async.
    """
    if sort_by == "due_date":
        return sorted(tasks, key=get_task_due_date_sort_key)
    elif sort_by == "priority":
        priority_order = {Priority.CRITICAL: 0, Priority.HIGH: 1, ...}
        return sorted(tasks, key=make_priority_order_getter(priority_order))
    elif sort_by == "created_at":
        return sorted(tasks, key=get_created_at_attr, reverse=True)
    else:
        return sorted(tasks, key=get_task_due_date_sort_key)
```

**Refactored Orchestrator** (reduced from 90 to 18 lines):
```python
async def get_filtered_tasks(...) -> Result[tuple[list[Any], dict[str, int]]]:
    """
    Get filtered and sorted tasks for user.

    Orchestrates: fetch (I/O) → stats → filter → sort.
    Pure computation delegated to testable helper functions.
    """
    try:
        # I/O: Fetch all tasks
        tasks_result = await get_all_tasks(user_uid)
        if tasks_result.is_error:
            return tasks_result

        tasks = tasks_result.value

        # Computation: Calculate stats BEFORE filtering
        stats = compute_task_stats(tasks)

        # Computation: Apply filters
        filtered_tasks = apply_task_filters(tasks, project, status_filter)

        # Computation: Apply sort
        sorted_tasks = apply_task_sort(filtered_tasks, sort_by)

        return Result.ok((sorted_tasks, stats))

    except Exception as e:
        logger.error("Error filtering tasks", extra={...})
        return Errors.system(f"Failed to filter tasks: {e}")
```

### Early Form Validation Pattern

**Before:** Validation happened deep in Pydantic layer with generic errors.

**After:** Early validation with clear, user-friendly messages:

```python
def validate_task_form_data(form_data: dict[str, Any]) -> Result[None]:
    """
    Validate task form data early.

    Pure function: returns clear error messages for UI.
    """
    # Required fields
    title = form_data.get("title", "").strip()
    if not title:
        return Errors.validation("Task title is required")

    if len(title) > 200:
        return Errors.validation("Task title must be 200 characters or less")

    # Date validation
    scheduled_date_str = form_data.get("scheduled_date", "")
    due_date_str = form_data.get("due_date", "")

    if scheduled_date_str and due_date_str:
        try:
            scheduled = date.fromisoformat(scheduled_date_str)
            due = date.fromisoformat(due_date_str)
            if due < scheduled:
                return Errors.validation("Due date cannot be before scheduled date")
        except ValueError:
            return Errors.validation("Invalid date format")

    return Result.ok(None)


async def create_task_from_form(form_data: dict[str, Any], user_uid: str) -> Result[Any]:
    """Create task from form data with early validation."""

    # VALIDATE EARLY
    validation_result = validate_task_form_data(form_data)
    if validation_result.is_error:
        return validation_result  # Return validation error to UI

    # Continue with form processing...
```

### Type Protocols for FastHTML

**Pattern:** Add Protocol types for better type safety:

```python
from typing import Protocol

class RouteDecorator(Protocol):
    """Protocol for FastHTML route decorator."""
    def __call__(self, path: str, methods: list[str] | None = None) -> Any:
        ...

class Request(Protocol):
    """Protocol for Starlette Request (lightweight type hint)."""
    query_params: dict[str, str]
    async def form(self) -> dict[str, Any]:
        ...
```

### Implementation Status

All 6 Activity domains refactored (2026-01-24):

| Domain | Orchestrator | Pure Functions | Validation | Status |
|--------|--------------|----------------|------------|--------|
| Tasks | 90 → 18 lines (80%) | 3 | ✅ | ✅ Complete |
| Goals | 56 → 25 lines (55%) | 3 | ✅ | ✅ Complete |
| Habits | 55 → 25 lines (55%) | 3 | ✅ | ✅ Complete |
| Events | 90 → 18 lines (80%) | 4 | ✅ | ✅ Complete |
| Choices | 59 → 18 lines (69%) | 3 | ✅ | ✅ Complete |
| Principles | 87 → 31 lines (64%) | 4 | ✅ | ✅ Complete |

**Results:**
- **437 lines** monolithic code → **135 lines** orchestration + **302 lines** pure helpers
- **18+ testable functions** created (no async/mocking needed)
- **67% average** complexity reduction

### Testing Strategy

Pure functions are now unit-testable:

```python
# tests/unit/ui/test_tasks_ui_helpers.py

def test_compute_task_stats_empty_list():
    stats = compute_task_stats([])
    assert stats == {"total": 0, "completed": 0, "overdue": 0}

def test_apply_task_filters_status():
    tasks = [Mock(status=ActivityStatus.COMPLETED), Mock(status=ActivityStatus.IN_PROGRESS)]
    filtered = apply_task_filters(tasks, status_filter="active")
    assert len(filtered) == 1

def test_validate_task_form_data_missing_title():
    result = validate_task_form_data({"title": ""})
    assert result.is_error
    assert "title is required" in str(result.error).lower()
```

### Benefits

1. **Testability**: Pure functions testable without database/async
2. **Readability**: Clear separation of I/O vs computation
3. **Maintainability**: Single Responsibility Principle enforced
4. **UX**: Clear validation messages before Pydantic layer
5. **Type Safety**: Protocol types for FastHTML components

### Reference Files

**Complete implementations:**
- `/adapters/inbound/tasks_ui.py` - Reference (all patterns)
- All 6 Activity domain files - See `/docs/migrations/ACTIVITY_UI_CODE_QUALITY_IMPROVEMENTS_2026-01-24.md`

---

## Legacy Pattern Removal (One Path Forward)

**Completed:** 2026-02-01

Following SKUEL's "One Path Forward" philosophy, the legacy `ProfileLayout` class was completely removed with zero deprecation period.

### What Was Removed

- **ProfileLayout class** (175 lines) - Legacy DaisyUI drawer implementation
- **ProfileLayout.render()** method - Returned Div only (not full HTML document)
- **ProfileLayout._build_sidebar_menu()** - Duplicate sidebar logic
- **Unused imports** - `Input`, `Label`, `create_navbar` (no longer needed)

### What Replaced It

**One Path:** `create_profile_page()` using BasePage + custom sidebar

```python
# THE way (no alternatives)
from ui.profile import create_profile_page

return create_profile_page(
    content,
    domains=domain_items,
    request=request,
)
```

### Philosophy Applied

SKUEL does NOT maintain backward compatibility. When a better pattern emerges:
- ❌ No deprecation warnings
- ❌ No compatibility shims
- ❌ No "use X instead" comments
- ✅ Clean removal
- ✅ Update all call sites
- ✅ One canonical way

**Result:** Codebase reduced by 175 lines, zero technical debt, one clear path forward.

---

## See Also

- `/.claude/skills/daisyui/SKILL.md` - DaisyUI 5 component reference
- `/.claude/skills/tailwind-css/SKILL.md` - Tailwind utility reference
- `/.claude/skills/fasthtml/SKILL.md` - FastHTML framework guide
- `/.claude/skills/js-alpine/SKILL.md` - Alpine.js for UI state
- `/docs/patterns/ERROR_HANDLING.md` - Result[T] error handling
- `/docs/migrations/ACTIVITY_UI_ERROR_HANDLING_REFACTORING_2026-01-24.md` - P0 security fixes
- `/docs/migrations/ACTIVITY_UI_CODE_QUALITY_IMPROVEMENTS_2026-01-24.md` - Pure helpers & validation
- `/docs/architecture/UX_MIGRATION_PLAN.md` - Migration history
