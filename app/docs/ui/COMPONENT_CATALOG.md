# SKUEL UI Component Catalog

**Last Updated:** 2026-03-10
**Status:** Complete — MonsterUI consolidated (primitives layer removed)

---

## Overview

This catalog documents all UI components in SKUEL's design system, organized into three tiers:

1. **MonsterUI Wrappers** - Semantic component wrappers (buttons, cards, badges, forms, layout, text, feedback)
2. **Patterns** - Composed reusable components (headers, cards, grids)
3. **Layouts** - Page structures (BasePage, domain layouts)

All components follow MonsterUI (FrankenUI + Tailwind) conventions and WCAG 2.1 Level AA accessibility standards.

> **Note (2026-03-10):** The `ui/primitives/` layer was removed. All unique value was absorbed into the MonsterUI wrapper modules: typography helpers → `ui/text.py`, StatusBadge/PriorityBadge → `ui/feedback.py`, FlexItem/Row/Stack → `ui/layout.py`, CardLink → `ui/cards.py`, ButtonLink/IconButton → `ui/buttons.py`.

---

## Quick Reference

| Category | Components | Location |
|----------|------------|----------|
| **Buttons** | Button, ButtonLink, IconButton, ButtonT | `ui/buttons.py` |
| **Cards** | Card, CardBody, CardTitle, CardActions, CardFigure, CardLink, CardT | `ui/cards.py` |
| **Forms** | Input, Select, Textarea, Checkbox, Radio, Toggle, Range, LabelInput, LabelTextArea, LabelSelect, LabelCheckbox | `ui/forms/` |
| **Feedback** | Alert, Badge, StatusBadge, PriorityBadge, Loading, Progress, RadialProgress | `ui/feedback.py` |
| **Layout** | DivHStacked, DivVStacked, DivFullySpaced, DivCentered, Grid, Container, Row, Stack, FlexItem, Size | `ui/layout.py` |
| **Typography** | PageTitle, SectionTitle, CardTitle, Subtitle, BodyText, SmallText, Caption, TruncatedText | `ui/text.py` |
| **Patterns** | PageHeader, EntityCard, StatsGrid, EmptyState, ErrorBanner, etc. | `ui/patterns/*.py` |
| **Layouts** | BasePage, Navbar, Domain Layouts | `ui/layouts/*.py` |

---

# MonsterUI Component Modules

Thin Python wrappers around FastHTML FT components with MonsterUI styling.
These are the **lowest-level SKUEL building blocks** — imported directly in route files and views.

**Module map** (March 2026 — decomposed from `daisy_components.py`):

| Module | Symbols |
|--------|---------|
| `ui.layout` | `Size`, `DivHStacked`, `DivVStacked`, `DivFullySpaced`, `DivCentered`, `Grid`, `Container` |
| `ui.buttons` | `ButtonT`, `Button` |
| `ui.cards` | `CardT`, `Card`, `CardBody`, `CardTitle`, `CardActions`, `CardFigure` |
| `ui.forms` | `Input`, `Select`, `Textarea`, `Checkbox`, `Radio`, `Toggle`, `Range`, `LabelInput`, `LabelTextArea`, `LabelSelect`, `LabelCheckbox` |
| `ui.modals` | `Modal`, `ModalBox`, `ModalAction`, `ModalBackdrop` |
| `ui.feedback` | `AlertT`, `BadgeT`, `ProgressT`, `LoadingT`, `Alert`, `Badge`, `Loading`, `Progress`, `RadialProgress`, `get_submission_status_badge_class` |
| `ui.navigation` | `Navbar`, `NavbarStart`, `NavbarCenter`, `NavbarEnd`, `Menu`, `MenuItem`, `Dropdown`, `DropdownTrigger`, `DropdownContent`, `Tabs`, `Tab` |
| `ui.data` | `Table`, `TableFromDicts`, `TableFromLists`, `TableT`, `Divider`, `DividerSplit`, `DividerT` |

**Import pattern:**
```python
from ui.buttons import Button, ButtonT
from ui.cards import Card, CardBody
from ui.forms import Input, LabelInput, LabelTextArea, LabelSelect, LabelCheckbox, Select, Textarea
from ui.feedback import Alert, AlertT, Badge, Progress, ProgressT, get_submission_status_badge_class
from ui.layout import Container, DivHStacked, DivVStacked, Size
from ui.modals import Modal, ModalAction, ModalBackdrop, ModalBox
from ui.navigation import Dropdown, DropdownContent, DropdownTrigger, Menu, MenuItem, Navbar
from ui.data import Divider, DividerSplit, DividerT, Table, TableFromDicts, TableFromLists, TableT
# Standard FastHTML elements (Div, Span, Option, Thead, Tbody, etc.)
from fasthtml.common import Div, Option, Span
```

**Note on `Size`:** Shared sizing enum used by buttons, forms, badges, and loading. Lives in `ui.layout` as the canonical location to avoid circular imports.

---

# Primitives

Basic building blocks for all SKUEL interfaces.

---

## Button

**Location:** `/ui/buttons.py`

Styled buttons for actions and navigation.

### Button(text, variant, size, **kwargs)

Primary action button.

**Parameters:**
- `text: str` - Button label
- `variant: str` - Style variant (default: "primary")
  - `"primary"` - Blue accent background
  - `"secondary"` - Gray background with border
  - `"ghost"` - Transparent with hover
  - `"danger"` - Red for destructive actions
- `size: str` - Size variant (default: "md")
  - `"sm"` - Small (px-3 py-1.5)
  - `"md"` - Medium (px-4 py-2)
  - `"lg"` - Large (px-6 py-3)
- `**kwargs` - Additional attributes (type, disabled, hx_post, etc.)

**Examples:**
```python
from ui.buttons import Button

# Primary action
Button("Save Changes", variant="primary")

# Secondary action
Button("Cancel", variant="secondary", size="sm")

# Destructive action
Button("Delete", variant="danger")

# With HTMX
Button("Submit", hx_post="/api/submit", hx_target="#result")
```

### ButtonLink(text, href, variant, size, **kwargs)

Button-styled link for navigation.

**Parameters:**
- `text: str` - Link label
- `href: str` - URL destination
- `variant: str` - Same as Button
- `size: str` - Same as Button
- `**kwargs` - Additional attributes

**Examples:**
```python
from ui.buttons import ButtonLink

# Navigation button
ButtonLink("View Details", href="/tasks/123", variant="primary")

# External link
ButtonLink("Learn More", href="https://example.com", variant="secondary")
```

---

## Card

**Location:** `/ui/cards.py`

Container component for grouping related content.

### Card(*children, padding, **kwargs)

Generic card container.

**Parameters:**
- `*children` - Content elements to display in card
- `padding: str` - Tailwind padding class (default: "p-4")
- `**kwargs` - Additional attributes (cls, id, etc.)

**Examples:**
```python
from ui.cards import Card
from ui.text import CardTitle
from fasthtml.common import P

# Simple card
Card(
    CardTitle("Task Details"),
    P("Complete the quarterly report by Friday"),
    padding="p-6",
)

# With custom styling
Card(
    H2("Statistics"),
    P("Total: 42"),
    cls="border-2 border-primary bg-primary/5",
)
```

---

## Badge

**Location:** `/ui/feedback.py`

Small labels for status, priority, and categories.

### Badge(text, variant, **kwargs)

Generic badge component.

**Parameters:**
- `text: str` - Badge label
- `variant: str` - Color variant (default: "default")
  - `"default"` - Base color
  - `"primary"` - Accent color
  - `"success"` - Green
  - `"warning"` - Yellow
  - `"error"` - Red
- `**kwargs` - Additional attributes

### StatusBadge(status)

Status-specific badge with predefined styling.

**Parameters:**
- `status: str | None` - Status value (active, completed, pending, etc.)

**Auto-mapped colors:**
- "completed" → Success (green)
- "active", "in_progress" → Primary (blue)
- "pending" → Warning (yellow)
- "cancelled" → Error (red)

### PriorityBadge(priority)

Priority-specific badge with predefined styling.

**Parameters:**
- `priority: str | None` - Priority value (critical, high, medium, low)

**Auto-mapped colors:**
- "critical", "high" → Error (red)
- "medium" → Warning (yellow)
- "low" → Success (green)

**Examples:**
```python
from ui.feedback import Badge, StatusBadge, PriorityBadge

# Generic badge
Badge("New", variant="primary")

# Status badge (auto-styled)
StatusBadge("completed")  # Green badge
StatusBadge("in_progress")  # Blue badge

# Priority badge (auto-styled)
PriorityBadge("critical")  # Red badge
PriorityBadge("low")  # Green badge
```

---

## Input

**Location:** `/ui/forms/components.py`

Form input components with consistent styling.

### Input(name, type, placeholder, value, required, error, **kwargs)

Styled text input field.

**Parameters:**
- `name: str` - Input name attribute
- `type: str` - Input type (default: "text")
- `placeholder: str` - Placeholder text
- `value: str` - Default value
- `required: bool` - Whether field is required (default: False)
- `error: str | None` - Error message to display
- `**kwargs` - Additional attributes

### TextArea(name, placeholder, value, rows, required, error, **kwargs)

Multi-line text input.

**Parameters:**
- `name: str` - Input name
- `placeholder: str` - Placeholder text
- `value: str` - Default value
- `rows: int` - Number of rows (default: 4)
- `required: bool` - Required field (default: False)
- `error: str | None` - Error message
- `**kwargs` - Additional attributes

### Select(name, options, value, required, **kwargs)

Dropdown select input.

**Parameters:**
- `name: str` - Select name
- `options: list[tuple[str, str]]` - List of (value, label) pairs
- `value: str` - Selected value
- `required: bool` - Required field (default: False)
- `**kwargs` - Additional attributes

**Examples:**
```python
from ui.forms import Input, Textarea, Select

# Text input
Input(
    name="title",
    placeholder="Enter task title",
    required=True,
)

# With error
Input(
    name="email",
    type="email",
    error="Invalid email format",
)

# Text area
TextArea(
    name="description",
    placeholder="Enter description",
    rows=6,
)

# Select dropdown
Select(
    name="priority",
    options=[
        ("low", "Low Priority"),
        ("medium", "Medium Priority"),
        ("high", "High Priority"),
    ],
    value="medium",
)
```

---

## Layout

**Location:** `/ui/layout.py`

Flexible layout primitives for responsive design.

### Row(*children, gap, align, justify, **kwargs)

Horizontal flex container.

**Parameters:**
- `*children` - Child elements
- `gap: int` - Gap size (0-12, default: 3)
- `align: str` - Vertical alignment (start, center, end, baseline)
- `justify: str` - Horizontal justification (start, center, end, between, around)
- `**kwargs` - Additional attributes

### Column(*children, gap, align, **kwargs)

Vertical flex container.

**Parameters:**
- `*children` - Child elements
- `gap: int` - Gap size (0-12, default: 3)
- `align: str` - Horizontal alignment
- `**kwargs` - Additional attributes

### FlexItem(child, grow, shrink, basis, **kwargs)

Flexible item within Row/Column.

**Parameters:**
- `child` - Single child element
- `grow: bool` - Allow growth (flex-grow-1)
- `shrink: bool` - Allow shrinking (flex-shrink)
- `basis: str` - Flex basis
- `**kwargs` - Additional attributes

**Examples:**
```python
from ui.layout import Row, FlexItem

# Horizontal row with gap
Row(
    Button("Save"),
    Button("Cancel", variant="secondary"),
    gap=2,
    justify="end",
)

# Vertical column
Column(
    H2("Title"),
    P("Description"),
    Button("Action"),
    gap=4,
)

# Flexible layout
Row(
    FlexItem(CardTitle("Task"), grow=True),  # Takes available space
    FlexItem(Badge("New"), shrink=False),    # Fixed size
)
```

---

## Text

**Location:** `/ui/text.py`

Typography components for consistent text styling.

### CardTitle(text, truncate, **kwargs)

Card title with optional truncation.

**Parameters:**
- `text: str` - Title text
- `truncate: bool` - Truncate long text (default: False)
- `**kwargs` - Additional attributes

### SmallText(text, **kwargs)

Small secondary text.

**Parameters:**
- `text: str` - Text content
- `**kwargs` - Additional attributes

### TruncatedText(text, lines, **kwargs)

Text truncated to specified number of lines.

**Parameters:**
- `text: str` - Text content
- `lines: int` - Number of lines before truncation (default: 1)
- `**kwargs` - Additional attributes

**Examples:**
```python
from ui.text import CardTitle, SmallText, TruncatedText

# Card title
CardTitle("Complete Quarterly Report")

# Truncated title
CardTitle(
    "Very long title that might overflow the container",
    truncate=True,
)

# Small metadata text
SmallText("Due: Dec 15, 2024")

# Multi-line truncation
TruncatedText(
    "Long description that will be truncated after 2 lines...",
    lines=2,
)
```

---

# Patterns

Composed components built from primitives for common UI patterns.

---

## PageHeader

**Location:** `/ui/patterns/page_header.py`

Consistent header for all pages with title and optional actions.

### PageHeader(title, subtitle, actions, breadcrumbs, **kwargs)

Page header component.

**Parameters:**
- `title: str` - Page title
- `subtitle: str | None` - Optional subtitle
- `actions: Any` - Optional action buttons
- `breadcrumbs: list[tuple[str, str]]` - Optional breadcrumb links [(label, href), ...]
- `**kwargs` - Additional attributes

**Examples:**
```python
from ui.patterns.page_header import PageHeader
from ui.buttons import Button, ButtonLink

# Simple header
PageHeader(title="Tasks")

# With subtitle and actions
PageHeader(
    title="Tasks",
    subtitle="Manage your tasks and projects",
    actions=ButtonLink("New Task", href="/tasks/new", variant="primary"),
)

# With breadcrumbs
PageHeader(
    title="Task Details",
    breadcrumbs=[
        ("Home", "/"),
        ("Tasks", "/tasks"),
        ("Details", None),  # Current page
    ],
)
```

---

## EntityCard

**Location:** `/ui/patterns/entity_card.py`

Universal card for displaying domain entities with variant support.

### EntityCard(title, description, status, priority, metadata, actions, config, **kwargs)

**NEW: Phase 3, Task 4 - Variant System**

Generic entity card supporting three display variants.

**Parameters:**
- `title: str` - Entity title
- `description: str` - Optional description
- `status: str | None` - Status (active, completed, etc.)
- `priority: str | None` - Priority (critical, high, medium, low)
- `metadata: list[str] | None` - Metadata items
- `actions: Any` - Optional action buttons
- `href: str | None` - Optional link URL
- `config: CardConfig | None` - Variant configuration (NEW!)
- `**kwargs` - Additional attributes

### CardVariant (Enum)

Display variants:
- `DEFAULT` - Full layout (description, metadata, actions)
- `COMPACT` - Title + badges only
- `HIGHLIGHTED` - Full layout + border + background

### CardConfig (Dataclass)

Configuration for variants:

**Factory Methods:**
- `CardConfig.default()` - Standard card (main lists)
- `CardConfig.compact()` - Condensed card (sidebars, mobile)
- `CardConfig.highlighted()` - Emphasized card (pinned items)

**Examples:**
```python
from ui.patterns.entity_card import EntityCard, CardConfig, CardVariant

# Default card (full layout)
EntityCard(
    title="Complete quarterly report",
    description="Draft and finalize Q4 report",
    status="in_progress",
    priority="high",
    metadata=["Due: Dec 15", "Project: Q4"],
)

# Compact card (sidebar)
EntityCard(
    title="Complete quarterly report",
    status="in_progress",
    priority="high",
    config=CardConfig.compact(),  # Hides description & metadata
)

# Highlighted card (pinned item)
EntityCard(
    title="URGENT: Board meeting prep",
    description="Prepare materials",
    priority="critical",
    config=CardConfig.highlighted(),  # Adds border + background
)

# Responsive
config = CardConfig.compact() if is_mobile else CardConfig.default()
EntityCard(title=task.title, config=config)
```


---

## StatsGrid

**Location:** `/ui/patterns/stats_grid.py`

Grid layout for displaying statistics cards.

### StatsGrid(*stat_cards, columns, **kwargs)

Statistics grid container.

**Parameters:**
- `*stat_cards` - StatCard components
- `columns: int` - Number of columns (default: 3)
- `**kwargs` - Additional attributes

### StatCard(label, value, icon, trend, **kwargs)

Individual statistics card.

**Parameters:**
- `label: str` - Stat label
- `value: str | int` - Stat value
- `icon: str | None` - Optional emoji icon
- `trend: str | None` - Trend indicator (+5%, -3%, etc.)
- `**kwargs` - Additional attributes

**Examples:**
```python
from ui.patterns.stats_grid import StatsGrid, StatCard

# Stats dashboard
StatsGrid(
    StatCard(label="Total Tasks", value=42, icon="📋"),
    StatCard(label="Completed", value=28, icon="✅", trend="+12%"),
    StatCard(label="In Progress", value=14, icon="🔄"),
    columns=3,
)
```

---

## EmptyState

**Location:** `/ui/patterns/empty_state.py`

Friendly empty state for lists with no items.

### EmptyState(title, message, action_label, action_href, icon, **kwargs)

Empty state component.

**Parameters:**
- `title: str` - Empty state title
- `message: str` - Explanation message
- `action_label: str | None` - Call-to-action button label
- `action_href: str | None` - Call-to-action button URL
- `icon: str` - Emoji icon (default: "📭")
- `**kwargs` - Additional attributes

**Examples:**
```python
from ui.patterns.empty_state import EmptyState

# Simple empty state
EmptyState(
    title="No tasks found",
    message="Create your first task to get started",
)

# With action button
EmptyState(
    title="No tasks found",
    message="Create your first task to get started",
    action_label="Create Task",
    action_href="/tasks/new",
    icon="✨",
)
```

---

## ErrorBanner

**Location:** `/ui/patterns/error_banner.py`

**NEW: Phase 3, Task 2 - User-Friendly Error Rendering**

User-friendly error messages with optional technical details.

### render_error_banner(user_message, technical_details, severity, show_details)

Error banner component.

**Parameters:**
- `user_message: str` - User-facing error message
- `technical_details: str | None` - Developer/debug info (optional)
- `severity: str` - Alert severity (default: "error")
  - `"error"` - Red alert (default)
  - `"warning"` - Yellow alert
  - `"info"` - Blue alert
  - `"success"` - Green alert
- `show_details: bool` - Force show technical details (default: False)

**Technical Details:**
- Shown in DEBUG mode automatically
- Hidden in production unless `show_details=True`
- Displayed in collapsible `<details>` element

**Examples:**
```python
from ui.patterns.error_banner import render_error_banner

# Simple error
render_error_banner("Unable to load tasks")

# With technical details (shown in DEBUG mode)
render_error_banner(
    "Unable to save task",
    technical_details="Database connection timeout",
    severity="error",
)

# Warning (non-critical)
render_error_banner(
    "Some data may be incomplete",
    severity="warning",
)
```

### render_inline_error(message)

Inline error for form fields.

**Parameters:**
- `message: str` - Error message

**Example:**
```python
from ui.patterns.error_banner import render_inline_error

Div(
    Input(name="email", cls="input-error"),
    render_inline_error("Invalid email format"),
)
```

---

## SectionHeader

**Location:** `/ui/patterns/section_header.py`

Header for page sections with optional actions.

### SectionHeader(title, actions, **kwargs)

Section header component.

**Parameters:**
- `title: str` - Section title
- `actions: Any` - Optional action buttons
- `**kwargs` - Additional attributes

**Examples:**
```python
from ui.patterns.section_header import SectionHeader
from ui.buttons import ButtonLink

# Simple section header
SectionHeader(title="Recent Tasks")

# With action
SectionHeader(
    title="Recent Tasks",
    actions=ButtonLink("View All", href="/tasks"),
)
```

---

## Relationship Patterns

**Location:** `/ui/patterns/relationships/*.py`

**NEW: Phase 5 - Lateral Relationships & Vis.js**

Interactive relationship visualization components.

### EntityRelationshipsSection(entity_uid, entity_type)

Complete relationships section with all three views.

**Parameters:**
- `entity_uid: str` - Entity UID
- `entity_type: str` - Entity type (tasks, goals, etc.)

**Includes:**
1. **BlockingChainView** - Vertical flow chart
2. **AlternativesComparisonGrid** - Side-by-side table
3. **RelationshipGraphView** - Interactive Vis.js graph

### BlockingChainView(entity_uid, entity_type)

Vertical blocking chain visualization.

### AlternativesComparisonGrid(entity_uid, entity_type)

Side-by-side comparison of alternatives.

### RelationshipGraphView(entity_uid, entity_type, depth)

Interactive force-directed graph.

**Parameters:**
- `entity_uid: str` - Entity UID
- `entity_type: str` - Entity type
- `depth: int` - Graph depth (1-3, default: 2)

**Examples:**
```python
from ui.patterns.relationships import EntityRelationshipsSection

# Complete relationships section
EntityRelationshipsSection(
    entity_uid="task_123",
    entity_type="tasks",
)

# Just the graph
RelationshipGraphView(
    entity_uid="task_123",
    entity_type="tasks",
    depth=2,
)
```

---

## Other Patterns

### TreeView

**Location:** `/ui/patterns/tree_view.py`

Hierarchical tree visualization with expand/collapse.

### Breadcrumbs

**Location:** `/ui/patterns/breadcrumbs.py`

Navigation breadcrumbs trail.

### Skeleton

**Location:** `/ui/patterns/skeleton.py`

Loading skeleton placeholders.

---

# Layouts

Page-level layout components and structures.

---

## BasePage

**Location:** `/ui/layouts/base_page.py`

Unified page wrapper for all SKUEL pages.

### BasePage(content, title, request, page_type, sidebar, **kwargs)

Universal page layout.

**Parameters:**
- `content: Any` - Main page content
- `title: str` - Page title (for `<title>` tag)
- `request: Request` - Starlette request object
- `page_type: PageType` - Page type (default: STANDARD)
- `sidebar: Any | None` - Optional custom sidebar
- `**kwargs` - Additional attributes

### PageType (Enum)

Page layout types:
- `STANDARD` - No sidebar, max-w-6xl container
- `HUB` - Left sidebar (w-64), flexible container
- `CUSTOM` - Custom sidebar + STANDARD layout

**Examples:**
```python
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.page_header import PageHeader

# Standard page
BasePage(
    content=Div(
        PageHeader(title="Tasks"),
        # ... content
    ),
    title="Tasks",
    request=request,
)

# Hub page with sidebar
BasePage(
    content=main_content,
    title="Admin Dashboard",
    request=request,
    page_type=PageType.HUB,
    sidebar=admin_sidebar,
)
```

---

## Navbar

**Location:** `/ui/layouts/navbar.py`

Top navigation bar with auth and admin detection.

### create_navbar_for_request(request)

Generate navbar based on request context.

**Parameters:**
- `request: Request` - Starlette request (auto-detects auth/admin)

**Features:**
- Auto-detects authenticated user
- Shows admin-only links for admin users
- Mobile-responsive with hamburger menu
- WCAG 2.1 Level AA compliant
- Focus trap on mobile menu (Phase 2, Task 9)

**Example:**
```python
from ui.layouts.navbar import create_navbar_for_request

navbar = create_navbar_for_request(request)
```

---

## Domain Layouts

**Location:** `/ui/{domain}/layout.py`

Domain-specific layout helpers.

### Task Layout

**Location:** `/ui/tasks/layout.py`

Task-specific page layouts.

### Habit Layout

**Location:** `/ui/habits/layout.py`

Habit tracking layouts.

### Finance Layout

**Location:** `/ui/finance/layout.py`

Finance page layouts with custom sidebar.

### Sidebar Pages

**Location:** `/ui/patterns/sidebar.py`

Unified sidebar component for all sidebar pages (Profile, KU, Reports, Journals, Askesis). Uses `PageType.CUSTOM`.

**Functions:**
- `SidebarPage(content, items, active, title, storage_key, request, ...)` - Full page with sidebar
- `SidebarNav(items, active, title, ...)` - Sidebar + mobile tabs (no BasePage wrapper)

**Dataclass:**
- `SidebarItem(label, href, slug, icon, description, badge_text, ...)`

**See:** `@custom-sidebar-patterns` for complete guide

---

## Tokens

**Location:** `/ui/tokens.py`

Design tokens (spacing, sizing, colors).

### Spacing Tokens

```python
SPACING = {
    "section_gap": "gap-8",      # Between major sections
    "card_gap": "gap-4",         # Between cards
    "element_gap": "gap-2",      # Between small elements
}
```

### Container Tokens

```python
CONTAINERS = {
    "standard": "max-w-6xl mx-auto px-4",
    "wide": "max-w-7xl mx-auto px-4",
    "narrow": "max-w-4xl mx-auto px-4",
}
```

### Card Tokens

```python
CARD = {
    "base": "bg-background border border-border rounded-lg shadow-sm",
    "padding": "p-4",
    "gap": "gap-3",
}
```

**Usage:**
```python
from ui.tokens import SPACING, CONTAINERS

Div(
    # ... content
    cls=f"{CONTAINERS['standard']} {SPACING['section_gap']}",
)
```

---

# Usage Patterns

## Form Pattern

Standard form with validation:

```python
from ui.forms import Input, Textarea, Select
from ui.buttons import Button
from ui.patterns.error_banner import render_inline_error
from fasthtml.common import Form, Div

Form(
    Div(
        Input(
            name="title",
            placeholder="Task title",
            required=True,
            error="Title is required" if has_error else None,
        ),
        render_inline_error("Title is required") if has_error else "",
    ),
    TextArea(
        name="description",
        placeholder="Description",
        rows=4,
    ),
    Select(
        name="priority",
        options=[("low", "Low"), ("medium", "Medium"), ("high", "High")],
    ),
    Button("Save", variant="primary", type="submit"),
    hx_post="/api/tasks",
    hx_target="#result",
)
```

## List Pattern

Entity list with empty state:

```python
from ui.patterns.entity_card import EntityCard, CardConfig
from ui.patterns.empty_state import EmptyState
from ui.patterns.page_header import PageHeader

content = Div(
    PageHeader(
        title="Tasks",
        actions=ButtonLink("New Task", href="/tasks/new"),
    ),
    # List or empty state
    Div(
        *[EntityCard(
            title=task.title,
            description=task.description,
            status=task.status,
            priority=task.priority,
            config=CardConfig.default(),
        ) for task in tasks],
        cls="space-y-3",
    ) if tasks else EmptyState(
        title="No tasks found",
        message="Create your first task to get started",
        action_label="Create Task",
        action_href="/tasks/new",
    ),
)
```

## Dashboard Pattern

Stats grid + recent items:

```python
from ui.patterns.stats_grid import StatsGrid, StatCard
from ui.patterns.section_header import SectionHeader
from ui.patterns.entity_card import EntityCard, CardConfig

Div(
    # Stats section
    SectionHeader(title="Overview"),
    StatsGrid(
        StatCard("Total", 42, icon="📋"),
        StatCard("Completed", 28, icon="✅", trend="+12%"),
        StatCard("In Progress", 14, icon="🔄"),
        columns=3,
    ),

    # Recent items section
    SectionHeader(
        title="Recent Tasks",
        actions=ButtonLink("View All", href="/tasks"),
    ),
    Div(
        *[EntityCard(
            title=task.title,
            status=task.status,
            priority=task.priority,
            config=CardConfig.compact(),  # Compact for dashboard
        ) for task in recent_tasks[:5]],
        cls="space-y-2",
    ),
)
```

---

# Accessibility Guidelines

All components follow WCAG 2.1 Level AA standards:

## Keyboard Navigation
- All interactive elements focusable
- Logical tab order
- Visible focus indicators
- Escape key dismisses modals/menus

## Screen Readers
- Semantic HTML elements
- ARIA labels where needed
- Live regions for dynamic content
- Alt text for images/icons

## Color Contrast
- Text: 4.5:1 minimum
- UI elements: 3:1 minimum
- Status colors distinguishable

## Focus Management
- Focus traps in modals (Phase 2, Task 9)
- Focus restoration on close
- Skip links for keyboard users

---

# Migration Guide

## From Custom Cards to EntityCard

**Before:**
```python
Card(
    Div(title, status_badge),
    P(description),
    cls="border-l-4 border-primary",
)
```

**After:**
```python
EntityCard(
    title=title,
    description=description,
    status=status,
    config=CardConfig.default(),
)
```

## From Inline Styles to Tokens

**Before:**
```python
Div(cls="max-w-6xl mx-auto px-4 gap-8")
```

**After:**
```python
from ui.tokens import CONTAINERS, SPACING

Div(cls=f"{CONTAINERS['standard']} {SPACING['section_gap']}")
```

---

# Component Index

Quick alphabetical index:

**MonsterUI Wrappers (ui/*.py):**
- **Alert / AlertT** - `ui.feedback`
- **Badge / BadgeT** - `ui.feedback`
- **Button / ButtonT** - `ui.buttons`
- **Card / CardBody / CardT** - `ui.cards`
- **Checkbox / Radio / Toggle / Range** - `ui.forms`
- **Container / Grid / DivHStacked / DivVStacked** - `ui.layout`
- **Divider / DividerSplit / DividerT** - `ui.data`
- **Dropdown / DropdownTrigger / DropdownContent** - `ui.navigation`
- **Input / Select / Textarea** - `ui.forms`
- **LabelInput / LabelTextArea / LabelSelect / LabelCheckbox** - `ui.forms`
- **Loading / LoadingT** - `ui.feedback`
- **Menu / MenuItem / Navbar** - `ui.navigation`
- **Modal / ModalBox / ModalAction / ModalBackdrop** - `ui.modals`
- **Progress / ProgressT / RadialProgress** - `ui.feedback`
- **Size** - `ui.layout`
- **Table / TableFromDicts / TableFromLists / TableT** - `ui.data`
- **Tabs / Tab** - `ui.navigation`

**Patterns & Layouts:**
- **BasePage** - `/ui/layouts/base_page.py`
- **Breadcrumbs** - `/ui/patterns/breadcrumbs.py`
- **EmptyState** - `/ui/patterns/empty_state.py`
- **EntityCard** - `/ui/patterns/entity_card.py`
- **ErrorBanner** - `/ui/patterns/error_banner.py`
- **Navbar (layout)** - `/ui/layouts/navbar.py`
- **PageHeader** - `/ui/patterns/page_header.py`
- **Relationships** - `/ui/patterns/relationships/*.py`
- **SectionHeader** - `/ui/patterns/section_header.py`
- **Skeleton** - `/ui/patterns/skeleton.py`
- **StatsGrid** - `/ui/patterns/stats_grid.py`
- **TreeView** - `/ui/patterns/tree_view.py`

---

# Related Documentation

- **Error Handling Patterns:** `/docs/patterns/ERROR_HANDLING.md`
- **UI Component Patterns:** `/docs/patterns/UI_COMPONENT_PATTERNS.md`
- **WCAG Accessibility Guide:** `/.claude/skills/accessibility-guide/`
- **MonsterUI Components:** `/.claude/skills/monsterui/`

---

**End of Component Catalog**

For questions or suggestions, see `/docs/INDEX.md` for complete documentation index.
