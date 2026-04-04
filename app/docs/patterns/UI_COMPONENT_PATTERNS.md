---
title: UI Component Patterns
updated: '2026-03-25'
category: patterns
related_skills:
  - accessibility-guide
  - base-page-architecture
  - custom-sidebar-patterns
  - ui-css
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

**Core Skills:** [@base-page-architecture](../../.claude/skills/base-page-architecture/SKILL.md), [@ui-css](../../.claude/skills/ui-css/SKILL.md), [@tailwind-css](../../.claude/skills/tailwind-css/SKILL.md), [@html-htmx](../../.claude/skills/html-htmx/SKILL.md), [@js-alpine](../../.claude/skills/js-alpine/SKILL.md)

**Advanced Skills:** [@custom-sidebar-patterns](../../.claude/skills/custom-sidebar-patterns/SKILL.md), [@html-navigation](../../.claude/skills/html-navigation/SKILL.md), [@skuel-component-composition](../../.claude/skills/skuel-component-composition/SKILL.md), [@accessibility-guide](../../.claude/skills/accessibility-guide/SKILL.md)

For hands-on implementation:
1. Invoke `@base-page-architecture` for BasePage patterns and page types
2. Invoke `@ui-css` for MonsterUI (FrankenUI + Tailwind) components
3. Invoke `@tailwind-css` for utility-first styling
4. Invoke `@html-htmx` for server communication patterns
5. Invoke `@js-alpine` for client-side interactivity
6. Invoke `@custom-sidebar-patterns` for advanced navigation
7. Invoke `@accessibility-guide` for WCAG 2.1 Level AA compliance
8. Continue below for complete component architecture

**Related Documentation:**
- [/ui/activities/sidebar.py](/ui/activities/sidebar.py) - Activities sidebar items
- [/ui/study/layout.py](/ui/study/layout.py) - Study sidebar example

---

## Overview

SKUEL uses a layered UI component architecture built on MonsterUI (FrankenUI + Tailwind). This document explains the component system and how to use it.

**Key Files:**
- `/ui/` - SKUEL UI design system (components, patterns, layouts, tokens)
- `/ui/layouts/base_page.py` - Unified page wrapper
- `/ui/layouts/page_types.py` - Page type definitions (HUB vs STANDARD)
- `/ui/tokens.py` - Spacing, container, and styling tokens
- `/ui/palette.py` - Centralized hex color constants (SemanticColor, RelationshipColor, EventTypeColor, FrequencyColor, CalendarFallback)
- `/ui/buttons.py`, `/ui/cards.py`, `/ui/forms/`, `/ui/modals.py`, `/ui/feedback.py`, `/ui/layout.py`, `/ui/navigation.py`, `/ui/data.py` - MonsterUI wrappers (8 focused modules, March 2026)

---

## Unified UX Design System

**Core Principle:** Two controlled page paradigms with consistent spacing and container widths.

### Page Types

| Type | Sidebar | Container | Use Case |
|------|---------|-----------|----------|
| `STANDARD` | None | `max-w-6xl` centered | Most pages (search, activity domains, forms) |
| `HUB` | Left (w-64) | Flexible | Multi-domain dashboards (Admin Dashboard) |
| `CUSTOM` | STANDARD + custom layout | Flexible | Complex layouts |

**Evolution (2026-02-01):** Profile Hub migrated from legacy `ProfileLayout` to `STANDARD` page type with custom sidebar implementation.

**Evolution (2026-02-06):** Activity Domains moved from profile sidebar to navbar avatar dropdown.

**Evolution (2026-02-16):** Events moved from main navbar to avatar dropdown — all 6 Activity Domains in one place.

**Evolution (2026-03-11):** Major restructure into three focused areas. Navbar gains icon links: **A** (`/activities`) and **S** (`/study`). Profile stripped to lean (Focus + Steady + Settings). Activity domains at `/activities/{domain}` with Activity sidebar. Avatar dropdown removed — avatar is a direct link to `/profile`.

**Evolution (2026-03-13):** `/study` is the student workspace hub landing page. Sub-pages are top-level routes (`/submit`, `/submissions`, `/exercise-reports`, `/activity-reports`, `/submit-activity-report`) sharing a 5-item Study sidebar. `/study` landing shows vertically-stacked workspace cards. Old `/submissions/*` and `/learn/*` UI paths redirect 301 to the new top-level routes.

**Evolution (2026-03-17a):** Navbar gains **C** (Curriculum) icon between A and S. All three icons (A, C, S) now have hover dropdown menus. `/curriculum` landing shows 4-card grid. Curriculum sub-pages (`/lessons`, `/path-steps`, `/learning-paths`, `/exercises`) share a 4-item Curriculum sidebar. Exercises moved from Study sidebar to Curriculum sidebar.

**Evolution (2026-03-17b):** **A** icon removed from navbar. Activity links moved to avatar hover dropdown (`_avatar_dropdown()`). Navbar now: C, S + avatar (hover → Activities) + logout. `/profile` stripped of sidebar — uses `BasePage` directly. Journals card on `/activities` replaced with lightweight link. Sidebar badges loaded async via `GET /api/sidebar/badges` (HTMX OOB swap with `CountBadge` + `StatusBadge`).

**Evolution (2026-03-17c):** **⚛️** (Knowledge) icon added as first navbar item, linking to `/ku`. Emoji icons use `text-base` styling (vs `font-semibold text-sm` for letter icons). `/ku` page redesigned from SEL-category grouped sections to flat Ku listing with bookmarks + latest sidebar. Sidebar powered by `UserRelationshipService.get_pinned_entities()` for bookmarks. Navbar order: SKUEL logo → ⚛️ → C → S → avatar → logout → search → bell.

**Evolution (2026-02-09):** All 5 sidebars (Profile, KU, Reports, Journals, Askesis) unified into single Tailwind + Alpine.js component (`SidebarPage`). Custom CSS/JS files (`profile_sidebar.css`, `profile_sidebar.js`) deleted. Mobile uses horizontal MonsterUI tabs instead of drawer/overlay.

**Evolution (2026-03-29):** `/profile` evolved from card grid to **live actionable hub**. Data sourced from `UserContext.build_rich()`. See `ui/profile/hub.py`.

**Evolution (2026-04-03a):** `/profile` Activity Domains changed from Alpine.js tabbed view (one domain visible at a time) to all 6 domains visible as scrollable blocks. Each block has a colored domain header (icon + clickable title + "View all" link) and 3 priority-sorted cards HTMX lazy-loaded from `/api/profile/{slug}/preview`.

**Evolution (2026-04-03b):** Activity Domains extracted from `/profile` into dedicated `/activities` hub with `SidebarPage` sidebar. The old horizontal `ActivityDomainNav` band replaced by collapsible Activity sidebar shared across `/activities`, `/tasks`, `/goals`, `/habits`, `/events`, `/choices`, `/principles`. Avatar dropdown simplified to Profile + Sign out. Activity icon added to navbar `ICON_NAV_ITEMS`. `/profile` retains Focus/Velocity, link to `/activities`, Nous placeholder, and Settings.

**Evolution (2026-03-30):** Tasks and Goals have active read-focused UI views at `/tasks` and `/goals` with HTMX interactions, filtering, and knowledge connections. Tasks icon (check-square) added to navbar between Knowledge and Submissions. Habits, Events, Choices, and Principles read-focused UIs are planned. Navbar order: SKUEL logo → ⚛️ (Knowledge) → Tasks → ⇄ (Submissions) → avatar → logout.

**Evolution (2026-04-03):** Admin accounts redirect to `/` after login instead of `/admin`. The `/` route renders an admin home hub with two cards (Admin → `/admin`, Teaching → `/teaching`). SKUEL logo in navbar left section links to `/`. "Admin Dashboard" and "Teaching" text links removed from navbar center. Admin navbar: SKUEL logo (left) → empty center → avatar + logout with icon (right). Mobile menu has explicit Admin + Teaching + Sign out links.

**Evolution (2026-04-04):** Explore sidebar evolved from text-only "My Learning" sidebar to **graph-centered sidebar**. Hero: `ExploreGraphView` (`ui/explore/graph.py`) — interactive Vis.js force-directed graph with hub mode (learning universe) and entity mode (lateral relationships). Filter tabs (All/Learning/Saved) control both graph node highlighting and list visibility. Sidebar widened to `w-96` (384px) via new `sidebar_width` param on `SidebarPage`. Alpine component: `exploreGraph` in `skuel.js`. API: `GET /api/explore/graph`. Graph expands to full-screen JS overlay on `document.body` (creates a second Vis.js network to escape sidebar `overflow:hidden` + `transform`).

**Background Convention (2026-02-05):** All layout surfaces (navbar, sidebars, body) are `bg-white`. Edges are defined by 1px borders (`border-b border-gray-200` on navbar, `border-r border-gray-200` on sidebars, CSS `border-right` on custom sidebars), not color contrast. Only interactive states (active nav links, hover) use tinted backgrounds.

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

# Sidebar page (Activities, Learn, KU, Reports, Journals, Askesis)
from ui.patterns.sidebar import SidebarItem, SidebarPage

items = [
    SidebarItem("Tasks", "/tasks", "tasks", icon="✅"),
    SidebarItem("Goals", "/goals", "goals", icon="🎯"),
]
return await SidebarPage(
    content=my_content,
    items=items,
    active="tasks",
    title="Activities",
    storage_key="activities-sidebar",
    request=request,
    active_page="activities",
)
```

### Unified Sidebar Pattern (Tailwind + Alpine.js)

**Added:** 2026-02-09 (unified from 3 implementations)

All sidebar pages (Activity Domains, Explore, GradeBook, Library, Teaching) use a single `SidebarPage()` component from `ui/patterns/sidebar.py`.

**Key Features:**
- One component for all 5 sidebar pages
- Desktop: Fixed sidebar (default 256px, configurable via `sidebar_width` param — Explore uses `w-96`/384px for graph) with smooth collapse to 48px edge
- Mobile: Horizontal MonsterUI tabs (no drawer/overlay)
- Alpine.js `collapsibleSidebar` + `Alpine.store()` for shared reactive state
- localStorage persistence of collapsed state
- Screen reader announcements on toggle

**Core API:**
```python
from ui.patterns.sidebar import SidebarItem, SidebarPage

items = [
    SidebarItem("Submit", "/submit", "submit", icon="📤"),
    SidebarItem("My Submissions", "/submissions", "submissions", icon="📝"),
    SidebarItem("Exercise Reports", "/exercise-reports", "exercise-reports", icon="📋"),
    SidebarItem("Activity Reports", "/activity-reports", "activity-reports", icon="📊"),
    SidebarItem("Submit Activity Report", "/submit-activity-report", "submit-activity-report", icon="⚡"),
]

return await SidebarPage(
    content=main_content,
    items=items,
    active="submit",
    title="Study",
    storage_key="study-sidebar",
    request=request,
    active_page="study",
)
```

**Extension Points:**
- `extra_sidebar_sections` — additional content below nav items (Explore uses for graph hero + filtered lists)
- `item_renderer` — custom render function for complex items (Profile uses for badges)
- `sidebar_width` — custom width class (`w-64` default, `w-80`, `w-96`). Explore uses `w-96` (384px) to accommodate the Vis.js graph hero. Width config auto-derives collapse offset and content margin.
- `description` field on SidebarItem — two-line layout (Askesis uses for subtitles)

**Files:**
- `/ui/patterns/sidebar.py` - `SidebarItem`, `SidebarNav`, `SidebarPage`
- `/static/js/skuel.js` (lines 917-953) - `collapsibleSidebar` Alpine component

**See:** `@custom-sidebar-patterns` for complete implementation guide

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
Spacing.PAGE        # "p-4 sm:p-6 lg:p-8"
Spacing.SECTION     # "space-y-8"
Spacing.CONTENT     # "space-y-4"

# Card styling
Card.BASE           # "bg-background border border-border rounded-lg"
Card.INTERACTIVE    # Card.BASE + hover shadow
Card.PADDING        # "p-6"
```

### Page Header & Section Header

Adopted across all 6 Activity Domain dashboards, Study hub, Curriculum hub, Admin dashboard, Analytics, Calendar, LifePath, and Timeline. Every `SidebarPage` content area starts with a `PageHeader`.

```python
from ui.patterns import PageHeader, SectionHeader

# Page header with optional subtitle and actions
PageHeader("Tasks", subtitle="Manage your daily tasks")
PageHeader("Goals", subtitle="Track and achieve your goals")

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

## Import Pattern (MonsterUI Wrappers)

```python
# Pure HTML elements from FastHTML
from fasthtml.common import H1, H2, H3, P, A, Form, Li, Ul

# SKUEL MonsterUI wrappers — 8 focused modules (March 2026)
from ui.buttons import Button, ButtonT
from ui.cards import Card, CardBody, CardTitle, CardActions, CardT
from ui.enum_helpers import get_submission_status_badge_class
from ui.feedback import Alert, AlertT, Badge, BadgeT, Loading, LoadingT, Progress, ProgressT, RadialProgress
from ui.forms import Checkbox, Input, LabelCheckbox, LabelInput, LabelSelect, LabelTextArea, Radio, Range, Select, Textarea, Toggle
from ui.layout import Container, DivCentered, DivFullySpaced, DivHStacked, DivVStacked, Grid, Size
from ui.modals import Modal, ModalAction, ModalBackdrop, ModalBox
from ui.navigation import Dropdown, DropdownContent, DropdownTrigger, Menu, MenuItem, Navbar, NavbarCenter, NavbarEnd, NavbarStart, Tab, Tabs
from ui.data import Divider, DividerSplit, DividerT, Table, TableFromDicts, TableFromLists, TableT
# Standard FastHTML elements — always from fasthtml.common
from fasthtml.common import Div, Option, Span, Tbody, Td, Th, Thead, Tr

# Theme for app initialization
from ui.theme import monster_headers, Theme
```

---

## Theme Headers

All SKUEL pages use `monster_headers()` for consistent styling:

```python
from fasthtml.common import fast_app
from ui.theme import monster_headers, Theme

# Default (light theme)
app, rt = fast_app(hdrs=monster_headers())

# With custom theme
app, rt = fast_app(hdrs=monster_headers(theme=Theme.dark))

# With PWA support
from ui.theme import pwa_headers
app, rt = fast_app(hdrs=(*monster_headers(), *pwa_headers()))
```

**What `monster_headers()` includes:**
- Meta viewport tags
- MonsterUI (FrankenUI + Tailwind) styles (loaded via `monster_headers()`)
- HTMX 1.9.10
- Alpine.js 3.14.8 (self-hosted)
- Lucide icons (optional)
- SKUEL custom CSS/JS

### `build_head()` — Canonical `<head>` for Full Documents

Pages that return complete `Html()` documents (rather than partial HTMX fragments) use `build_head()` from `base_page.py`. This is the **single source of truth** for all `<head>` content — `BasePage` delegates to it. Never construct a `Head(...)` manually.

```python
from ui.layouts.base_page import build_head

# Used internally by BasePage
Html(
    build_head("Page Title", extra_css=["/static/css/calendar.css"]),
    Body(content),
)
```

---

## Type-Safe Variants

SKUEL uses Python enums for type-safe MonsterUI variants:

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
        P("Task description here", cls="text-muted-foreground"),
        CardActions(
            Button("Edit", variant=ButtonT.ghost, size=Size.sm),
            Button("Complete", variant=ButtonT.success, size=Size.sm),
        )
    )
)
```

### Card Variants

CardT is re-exported from MonsterUI — use MonsterUI's real variants:

```python
# Default card
Card(CardBody(...), variant=CardT.default)

# Primary emphasis
Card(CardBody(...), variant=CardT.primary)

# Secondary/muted
Card(CardBody(...), variant=CardT.secondary)

# Destructive/danger
Card(CardBody(...), variant=CardT.destructive)

# Hover effect (lift + shadow on hover)
Card(CardBody(...), variant=CardT.hover)
```

---

## Form Components

### Basic Form

```python
from fasthtml.common import Form

Form(
    LabelInput("Email", type="email", name="email", placeholder="Enter email"),
    LabelInput("Password", type="password", name="password"),
    LabelCheckbox("Remember me", name="remember"),
    Button("Sign In", variant=ButtonT.primary, type="submit"),
    hx_post="/login",
    hx_target="#result",
)
```

### Select and Textarea

```python
from fasthtml.common import Option

LabelSelect(
    Option("Select...", value=""),
    Option("High", value="high"),
    Option("Medium", value="medium"),
    Option("Low", value="low"),
    label="Priority",
    name="priority",
)

LabelTextArea("Description", name="description", rows="4", placeholder="Enter description...")
```

### Input Sizing

```python
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

### Tables

**Prefer `TableFromDicts`** for data-driven tables. Pre-render components (Badge, Button) into dict values:

```python
from ui.data import TableFromDicts, TableT

def _cell_render(k, v):
    if k == "Name": return Td(v, cls="font-medium")
    return Td(v)

TableFromDicts(
    header_data=["Name", "Status", "Actions"],
    body_data=[
        {
            "Name": "Task 1",
            "Status": Badge("Active", variant=BadgeT.success),
            "Actions": Button("Edit", variant=ButtonT.ghost, size=Size.xs),
        },
        {
            "Name": "Task 2",
            "Status": Badge("Pending", variant=BadgeT.warning),
            "Actions": Button("Edit", variant=ButtonT.ghost, size=Size.xs),
        },
    ],
    body_cell_render=_cell_render,
    cls=(TableT.striped,),
)
```

Manual `Table(Thead(...), Tbody(...))` is only needed for non-data-driven layouts (hardcoded rows, dynamic column counts, headerless tables). See `docs/roadmap/tables-custom-design.md` for deferred cases.

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
            P(task.description or "No description", cls="text-muted-foreground text-sm"),
            DivHStacked(
                Badge(task.priority.value, variant=_priority_badge(task.priority)),
                Span(f"Due: {task.due_date}", cls="text-xs text-muted-foreground/50") if task.due_date else None,
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

**Location:** `/ui/patterns/empty_state.py`

Adopted across ~40 locations in 25 files (Activity Domains, Curriculum, Study, Admin, Finance, etc.).

```python
from ui.patterns.empty_state import EmptyState

# Primary list view — full CTA
EmptyState(
    title="No tasks found",
    description="Create one to get started!",
    action_text="Create task",
    action_href="/activities/tasks?view=create",
)

# Secondary section — title only
EmptyState(title="No feedback yet")

# With icon
EmptyState(title="No habits for today!", icon="🎉")
```

**Usage rules:** Primary list views get full CTA. Secondary sections get title only. Tiny inline indicators (sidebar `<li>`, analytics cards) stay as `P()` — `EmptyState` with `py-12` is too heavy for compact contexts.

### Learning Loop Fragments (PathStep Detail)

**Location:** `ui/learning_loop/` — shared exercise status helpers + PathStep submission/feedback renderers.

The PathStep detail page (`/explore/ps/{uid}`) HTMX-loads three learning loop sections for authenticated users. Fragment endpoints in `learning_loop_routes.py`, renderers in `ui/learning_loop/`:

- `exercise_status.py` — `render_exercise_list()`, status pills (`_STATUS_PILL`), action links with `from_ps` context. Shared with Library exercises tab (`/library/exercises`).
- `submissions_section.py` — `render_ps_submissions()` — submission rows with status badges.
- `feedback_section.py` — `render_ps_feedback()` — feedback rows with outcome badges, filters to submissions with reports.

```python
# PathStep detail page (explore_ui.py) — authenticated user
Div(
    H3("Exercises", ...),
    Div(id=f"ps-exercises-{uid}",
        hx_get=f"/learning-loop/ps/{uid}/exercises",
        hx_trigger="load", hx_swap="innerHTML"),
    cls="border-t border-border pt-6 mt-8",
)
```

---

## Common Anti-Patterns

### Don't Use Raw MonsterUI Classes on Wrappers

```python
# BAD: Redundant - Button wrapper already adds button classes
Button("Click", cls="uk-btn uk-btn-primary")

# GOOD: Use the variant enum
Button("Click", variant=ButtonT.primary)
```

### Don't Import Directly from MonsterUI Package

```python
# BAD: Bypasses SKUEL wrappers
from monsterui.all import Button, Card  # Don't use directly

# GOOD: Use SKUEL wrappers
from ui.buttons import Button
from ui.cards import Card
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

### Sidebar for Navigation

Use `SidebarPage` from `ui/patterns/sidebar.py` for all sidebar pages. Desktop: collapsible fixed sidebar. Mobile: horizontal tabs.

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
            variant=AlertT.error,
        ),
        cls="mb-4",
    )
```

#### 4. Data Helpers Return Result[T]

**Shared helper** (`adapters/inbound/ui_helpers.py`):
```python
from adapters.inbound.ui_helpers import fetch_user_entities

async def get_all_goals(user_uid: UserUID) -> Result[list[Any]]:
    """Get all goals for user."""
    return await fetch_user_entities(goals_service.get_user_goals, "goals", user_uid, logger)

# For optional services, pass None when service is unavailable:
async def get_all_events(user_uid: UserUID) -> Result[list[Any]]:
    service_method = events_service.get_user_events if events_service else None
    return await fetch_user_entities(service_method, "events", user_uid, logger)
```

`fetch_user_entities()` handles Result propagation, `or []` defaulting, structured logging, and safety-net exception catching — eliminating ~18 lines of boilerplate per domain.

**Filtering** uses the service facade directly:
```python
filtered_result = await tasks_service.get_filtered_context(
    user_uid, status_filter=filters.status_filter, sort_by=filters.sort_by,
)
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
    return TasksViewComponents.render_list_view(ctx=page_ctx)
```

### Benefits

1. **User-visible errors** - Clear error messages instead of empty lists
2. **Debuggability** - Full error context in logs (user_uid, error type, message)
3. **Consistency** - All Activity domains follow same pattern
4. **Type safety** - Dataclasses prevent param extraction errors
5. **Maintainability** - Single pattern to understand across all domains

### Implementation Status

**Activity Domains** (full pattern: typed params + Result[T] helpers + error banners):

| Domain | Status | Notes |
|--------|--------|-------|
| Tasks | ✅ Complete | Reference implementation |
| Goals | ✅ Complete | Calendar-enabled |
| Habits | ✅ Complete | Calendar-enabled |
| Events | ✅ Complete | Calendar-first design |
| Choices | ✅ Complete | Analytics instead of calendar |
| Principles | ✅ Complete | Analytics + bug fixes applied |

**Non-Activity Domains** (render_error_banner standardized, 2026-03-18):

| Domain | Status | Notes |
|--------|--------|-------|
| Teaching | ✅ Complete | 10 error sites, fixed `.is_ok` → `.is_error` (SKUEL003) |
| Study | ✅ Complete | 12 error sites, HTMX fragments preserve target `id` |
| KU | ✅ Complete | Error banner vs empty state distinction |
| Admin | ✅ Complete | Per-section warning banners via `tuple[data, bool]` helpers |
| Insights | ✅ Complete | Error state with load-more pagination |
| Finance | ✅ Complete | Typed context methods with `Result[TypedDict]` |
| Analytics | ✅ Complete | 8 error sites → `render_inline_error()`, PageHeader adopted |
| LifePath | ✅ Complete | `_error_page`/`_service_unavailable_page` → `render_error_banner`, PageHeader adopted |
| Calendar | ✅ Complete | Custom `Html(Head, Body)` wrapper → `BasePage`, PageHeader adopted |
| GraphQL | ✅ Complete | `text-red-600` → `text-error`, `bg-red-50` → `bg-error/10` |

**Shared Helpers** (`/adapters/inbound/ui_helpers.py`):
- `render_dashboard_error_page(title, subtitle, error_message, view, render_view_tabs, page_creator, request)` — Standard error page for dashboard routes with tabs/nav preserved (all 6 Activity domains). Domains with multiple calls (e.g., Principles) wrap this in a local `_dashboard_error()` helper to DRY the static args.
- `render_entity_not_found_page(entity_label, uid, domain_slug, request)` — Standard "Not Found" full page for detail views (all 6 Activity domains)
- `fetch_user_entities(service_method, domain_name, user_uid, logger)` — Fetch all entities with consistent error handling/logging (4 domains)
- `parse_calendar_params(request)` — Calendar view parameters (4 calendar-enabled domains)

**Reference Files:**
- `/adapters/inbound/tasks_ui.py` - Reference pattern (Activity)
- `/adapters/inbound/goals_ui.py` - Calendar-enabled variant
- `/adapters/inbound/teaching_ui.py` - Hub page pattern: `/teaching` hub (BasePage) → child pages with teaching sidebar (`ui/teaching/nav.py`) + nested student hub at `/teaching/students/{uid}` (BasePage, HTMX preview blocks) → student submissions with Alpine section sidebar
- `/adapters/inbound/study_ui.py` - HTMX fragments with error banners
- `/adapters/inbound/ku_ui.py` - Error state vs empty state
- `/adapters/inbound/admin_dashboard_ui.py` - Per-section partial failure banners via `tuple[data, bool]` helpers
- `/adapters/inbound/insights_ui.py` - Error state with pagination

### Activity Domain Detail Page Pattern

*Harmonized: 2026-02-07*

All 6 Activity Domain detail pages (`/{domain}/{uid}`) follow a single pattern: **inline HTML in the route handler + BasePage wrapper**.

**Required elements:**
1. `require_authenticated_user(request)` for user_uid
2. `service.get_for_user(uid, user_uid)` for ownership-verified fetch
3. BasePage-wrapped error card on failure (not bare `Div` or `Response`)
4. Inline HTML content in the route handler (not delegated to `*ViewComponents` static methods)
5. `Container.STANDARD` + `Spacing.PAGE` tokens on outer content Div
6. `EntityRelationshipsSection(entity_uid=..., entity_type=...)` for lateral relationships
7. `BasePage(content=content, title=..., page_type=PageType.STANDARD, request=request, active_page="{domain}")`

**Reference pattern (from Tasks):**
```python
from adapters.inbound.ui_helpers import render_entity_not_found_page

@rt("/tasks/{uid}")
async def task_detail_view(request, uid: str) -> Any:
    user_uid = require_authenticated_user(request)
    result = await tasks_service.get_for_user(uid, user_uid)
    if result.is_error or result.value is None:
        return await render_entity_not_found_page("Task", uid, "tasks", request)
    task = result.value
    content = Div(
        # Domain-specific content cards...
        EntityRelationshipsSection(entity_uid=task.uid, entity_type="tasks"),
        cls=f"{Container.STANDARD} {Spacing.PAGE}",
    )
    return await BasePage(
        content=content, title=task.title,
        page_type=PageType.STANDARD, request=request, active_page="tasks",
    )
```

**Domain-specific content (preserved during harmonization):**
- **Choices** — Options listing, "Make Decision" button (when pending), conditional "Add Option", priority/domain/type metadata badges
- **Principles** — Strength indicator, reflection cards, "View History"/"View All" HTMX fragment swaps (uses `id="view-content"` on content wrapper)
- **Goals** — Confidence bar, guidances, target date, progress tracking

**What was removed:**
- `GoalUIComponents.render_goal_detail()` — inlined into `goals_ui.py` route handler
- `PrinciplesViewComponents.render_principle_detail()` — inlined into `principles_ui.py` route handler
- Duplicate `/choices/{uid}` route (`view_choice`) — removed in favor of existing `choice_detail_view`

---

## Activity Domain Filtered List Queries

*Added: 2026-01-24 | Updated: 2026-03-13 (single-fetch architecture — 1 query per page load)*

**Core Principle:** "One query per page load; compute stats and apply filters in Python from the fetched set"

### Problem: Multiple Redundant Queries

**Before:** Each page load ran 2-4 separate Neo4j queries — a Cypher COUNT for stats, a filtered entity fetch, and (for Tasks) two additional queries for project/assignee dropdown lists. These were parallelized with `asyncio.gather()` but still hit the database multiple times.

### Solution: Single-Fetch `get_filtered_context()` with `FilteredContextProvider` Protocol

All 11 domain facades (6 Activity + 5 Curriculum) expose `get_filtered_context()` returning `Result[ListContext]`, satisfying the `FilteredContextProvider` protocol. Each facade delegates to a shared skeleton (`build_filtered_context()` in `core/services/filtered_context.py`) with domain-specific callables for stats, filters, and sorting.

```python
# Shared skeleton orchestrates: fetch → stats → filter → sort → return
# Sort/filter logic is config-driven via declarative dicts (core/utils/list_helpers.py)
async def get_filtered_context(self, user_uid, status_filter="active", sort_by="due_date"):
    async def fetch_all():
        return await self.core.get_for_user_filtered(user_uid, "all")

    def apply_filters(all_tasks):
        filtered = apply_entity_filter(all_tasks, status_filter, _TASK_FILTER_CONFIG)
        return _apply_task_secondary_filters(filtered, project, assignee, due_filter)

    return await build_filtered_context(
        fetch_all=fetch_all,
        compute_stats=_compute_task_stats,
        apply_filters=apply_filters,
        apply_sort=_apply_task_sort,  # delegates to apply_entity_sort() with _TASK_SORT_CONFIG
        sort_by=sort_by,
        compute_metadata=_compute_task_metadata,  # Tasks only: projects/assignees
    )
```

**`FilteredContextProvider` protocol** (`core/ports/filtered_context_protocols.py`): Common params `user_uid`, `status_filter`, `sort_by`. Intelligence services call via protocol; UI routes call concrete classes directly for domain-specific params.

**`ListContext` TypedDict** (`core/ports/query_types.py`): `entities` (filtered list), `stats` (dict[str, int | float] — guaranteed `total` + `active` per `BaseStats` contract), `metadata` (dict[str, Any], optional).

**Metadata**: Tasks returns `projects`/`assignees`; Principles, Goals, Habits return `categories` (derived from domain enums — `PrincipleCategory`, `_GOAL_CATEGORIES`, `HabitCategory`). UI routes consume via `ctx.get("metadata", {}).get("categories", [])`. Standalone create forms that don't call `get_filtered_context()` import the enum directly.

**Typed accessors** (`core/utils/list_context_helpers.py`): `get_entities(ctx, Task)` → `list[Task]`, `get_stats(ctx)`, `get_metadata(ctx)`.

**Module-level helpers** (Python-side, in each `*_service.py` facade file):
- `_compute_{domain}_stats(entities)` — stats from full set (all 11 domains, guaranteed `total` + `active`)
- `_{DOMAIN}_SORT_CONFIG: SortConfig` — declarative sort key dict (all 11 domains), consumed by `apply_entity_sort()`
- `_{DOMAIN}_FILTER_CONFIG: FilterConfig` — declarative filter predicate dict (7 domains), consumed by `apply_entity_filter()`
- `_apply_{domain}_sort(entities, sort_by)` — thin wrapper delegating to `apply_entity_sort()` with domain config
- `_apply_task_secondary_filters(tasks, project, assignee, due_filter)` — Tasks only
- `_apply_principle_filters(principles, category_filter, strength_filter, status_filter)` — Principles only (multi-dimensional)
- `_compute_task_metadata(all_tasks)` — Tasks: project/assignee lists
- `_compute_principle_metadata`, `_compute_goal_metadata`, `_compute_habit_metadata` — categories from enums

**Shared generics** (`core/utils/list_helpers.py`): `apply_entity_sort()`, `apply_entity_filter()`, `SortConfig`, `FilterConfig` type aliases, `get_event_sort_datetime()`, `get_sequence_attr()`.

**Intelligence integration:** `UserContextIntelligence.filtered_providers` dict maps domain names to `FilteredContextProvider` facades, enabling on-demand per-domain queries. UserContext is the broad snapshot; `get_filtered_context()` is the zoom lens.

**Tests:** `tests/unit/services/activity/test_activity_query_helpers.py` — 49 tests covering Python-side helpers.

### Typed Context Methods (Non-Activity Domains)

Domains outside the Activity pattern use the same principle — service methods return typed context dicts, routes stay thin:

**Finance** (`FinanceService`): 4 typed context methods (`get_dashboard_context`, `get_budgets_context`, `get_reports_context`, `get_analytics_context`) return domain-specific `TypedDict`s (`FinanceDashboardContext`, etc.). Defined in `core/services/finance_service.py`.

**Choices Analytics** (`ChoicesService.get_analytics_context`): Returns `ChoicesAnalyticsContext` TypedDict with `total_choices`, `total_decisions`, `satisfaction_rate`, `on_time_rate`, `outcomes`. Defined in `core/services/choices_service.py`.

**Insights** (`insights_ui.py`): Module-level `filter_insights()` and `build_filter_query_string()` helpers DRY the filtering logic shared between `insights_dashboard` and `load_more_insights` routes.

**Pattern:** Routes should only do: authenticate → parse → call service → handle error → render. Data assembly, computation, and reshaping belong in service methods.

### Route-Level Conventions

*Updated: 2026-03-18*

Module-level helpers keep route handlers thin. The shared primitives in `form_helpers.py` are adopted by all UI files that handle form data — the 6 Activity domains, plus `auth_ui`, `calendar_ui`, `user_profile_ui`, `lifepath_ui`, `askesis_ui`, and `journals_ui`.

| Helper | Purpose |
|--------|---------|
| `safe_form_string()`, `safe_form_int()`, `safe_form_bool()` | Type-safe extraction from `str \| UploadFile \| None` form values |
| `ActivityFilters` hierarchy | Unified filter base from `form_helpers.py` — Goals/Habits/Events/Choices use base, Tasks use `TaskFilters`, Principles use `PrincipleFilters` |
| `parse_task_filters()`, `parse_principle_filters()`, `parse_activity_filters()` | Domain-specific query param extraction with defaults |
| `parse_enum_safe()`, `parse_date_safe()`, etc. | Shared parsing primitives from `form_helpers.py` |
| `parse_{domain}_create_request(form_data) -> {Domain}CreateRequest` | Pure form→request parsing (no service calls, no side effects) |
| `parse_{domain}_update_payload(form) -> dict[str, Any]` | Pure form→update dict parsing |

```python
# Route handler stays thin:
async def create_task_from_form(form_data: dict[str, Any], user_uid: UserUID) -> Result[Task]:
    create_request = parse_task_create_request(form_data)
    return await tasks_service.create_task(create_request, user_uid)
```

### Form Validation Pattern

**Principle:** Pydantic is the sole validation layer. Do not duplicate field constraints in manual functions.

Field-level constraints (`min_length`, `max_length`, required) live on the request model. Cross-field rules use `@model_validator`. `QuickAddRouteFactory` catches `PydanticValidationError` and renders a user-friendly error banner — no 500s reach the user.

```python
# core/models/task/task_request.py
from pydantic import model_validator

class TaskCreateRequest(CreateRequestBase):
    title: str = Field(min_length=1, max_length=200)
    scheduled_date: date | None = None
    due_date: date | None = None

    @model_validator(mode="after")
    def validate_due_after_scheduled(self) -> "TaskCreateRequest":
        """Cross-field rule: due date must not precede scheduled date."""
        if self.due_date and self.scheduled_date:
            if self.due_date < self.scheduled_date:
                raise ValueError("Due date cannot be before scheduled date")
        return self
```

`QuickAddRouteFactory` surfaces Pydantic errors as banners automatically — no per-domain wiring needed:

```python
except PydanticValidationError as e:
    first_error = e.errors()[0]
    field = str(first_error["loc"][-1]) if first_error.get("loc") else None
    msg = first_error.get("msg", "Validation error")
    return render_error_banner(f"{field}: {msg}" if field else msg)
```

**Anti-pattern (eliminated March 2026):** `validate_*_form_data()` functions that duplicated constraints already enforced by Pydantic. These created two sources of truth and introduced bugs (e.g. `validate_principle_form_data` said `max_length=200` while `PrincipleCreateRequest` correctly said `max_length=100`).

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
    headers: _HeadersLike
    method: str
    url: _URLLike
    path_params: dict[str, str]
    client: _ClientLike | None
    async def form(self) -> _FormDataLike: ...
    async def json(self) -> Any: ...
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
    tasks = [Mock(status=EntityStatus.COMPLETED), Mock(status=EntityStatus.ACTIVE)]
    filtered = apply_task_filters(tasks, status_filter="active")
    assert len(filtered) == 1

def test_task_create_request_empty_title():
    with pytest.raises(ValidationError):
        TaskCreateRequest(title="")

def test_task_create_request_due_before_scheduled():
    with pytest.raises(ValidationError, match="Due date cannot be before scheduled date"):
        TaskCreateRequest(
            title="My task",
            scheduled_date=date(2026, 3, 10),
            due_date=date(2026, 3, 5),
        )
```

### Benefits

1. **Testability**: Pure functions testable without database/async
2. **Readability**: Clear separation of I/O vs computation
3. **Maintainability**: Single Responsibility Principle enforced
4. **UX**: Clear validation messages via Pydantic — caught by `QuickAddRouteFactory` and rendered as error banners
5. **Type Safety**: Protocol types for FastHTML components

### Reference Files

**Complete implementations:**
- `/adapters/inbound/tasks_ui.py` - Reference (all patterns)
- All 6 Activity domain files - See `/docs/migrations/ACTIVITY_UI_CODE_QUALITY_IMPROVEMENTS_2026-01-24.md`

---

## Legacy Pattern Removal (One Path Forward)

### Sidebar Unification (2026-02-09)

**Commits:** `949f201` (unify), `5856a7e` (fix shared state bug)

Three sidebar implementations (~590 lines custom CSS/JS) unified into one Tailwind + Alpine.js component.

**What Was Removed:**
- `profile_sidebar.css` (172 lines) — custom CSS for sidebar animations
- `profile_sidebar.js` (121 lines) — vanilla JS toggle + localStorage
- Askesis inline CSS/JS (~300 lines) — separate breakpoints and behavior
- `toggleProfileSidebar()`, `profileSidebarCollapsed`, `ProfileDomainItem`

**What Replaced It:**

```python
# THE way (all 5 sidebar pages)
from ui.patterns.sidebar import SidebarItem, SidebarPage

return await SidebarPage(content=..., items=..., active=..., title=..., ...)
```

**Result:** ~590 lines deleted, ~337 lines added (300 Python + 37 Alpine). One reusable component.

### ProfileLayout Class (2026-02-01)

**What Was Removed:**
- **ProfileLayout class** (175 lines) — legacy drawer implementation
- Replaced by `create_profile_page()` which now uses `SidebarPage()`

### Philosophy Applied

SKUEL does NOT maintain backward compatibility. When a better pattern emerges:
- ❌ No deprecation warnings
- ❌ No compatibility shims
- ❌ No "use X instead" comments
- ✅ Clean removal
- ✅ Update all call sites
- ✅ One canonical way

---

## See Also

- `/.claude/skills/ui-css/SKILL.md` - MonsterUI (FrankenUI + Tailwind) component reference
- `/.claude/skills/tailwind-css/SKILL.md` - Tailwind utility reference
- `/.claude/skills/fasthtml/SKILL.md` - FastHTML framework guide
- `/.claude/skills/js-alpine/SKILL.md` - Alpine.js for UI state
- `/docs/patterns/ERROR_HANDLING.md` - Result[T] error handling
- `/docs/migrations/ACTIVITY_UI_ERROR_HANDLING_REFACTORING_2026-01-24.md` - P0 security fixes
- `/docs/migrations/ACTIVITY_UI_CODE_QUALITY_IMPROVEMENTS_2026-01-24.md` - Pure helpers & validation
- `/docs/architecture/UX_MIGRATION_PLAN.md` - Migration history
