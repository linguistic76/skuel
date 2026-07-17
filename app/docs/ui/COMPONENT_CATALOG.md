# SKUEL UI Component Catalog

**Last Updated:** 2026-06-30
**Status:** Complete — ADR-071 migration finished. SKUEL-owned pure-Tailwind component layer; MonsterUI/FrankenUI/DaisyUI removed.

---

## Overview

This catalog documents all UI components in SKUEL's design system, organized into three tiers:

1. **SKUEL Components** - Semantic component wrappers (buttons, cards, badges, forms, layout, feedback) in `ui.components` + the `ui/` wrapper modules
2. **Patterns** - Composed reusable components (headers, cards, grids)
3. **Layouts** - Page structures (BasePage, domain layouts)

All components are SKUEL-owned pure Tailwind + Alpine.js (ADR-071) and follow WCAG 2.1 Level AA accessibility standards.

> **Note (2026-03-10):** The `ui/primitives/` layer was removed. All unique value was absorbed into the wrapper modules: typography helpers → `ui/text.py`, StatusBadge/PriorityBadge → `ui/feedback.py`, FlexItem/Row/Stack → `ui/layout.py`, CardLink → `ui/cards.py`, ButtonLink/IconButton → `ui/buttons.py`.
> **Note (2026-06-26 PR E):** `ui/buttons.py`, `ui/cards.py`, and `ui/text.py` deleted. `ButtonLink` moved to `ui/primitives.py` (Tailwind `A()` wrapper, `cls=ButtonT.style, size="sm"` API). Typography helpers replaced by `section_label()` or inline Tailwind.
> **Note (2026-06-30 ADR-071 complete):** `Button`/`ButtonT`, all `Card*`, forms, nav, data, feedback, and layout components are SKUEL-owned pure Tailwind, importable from `ui.components`. `from monsterui.franken import ...` no longer works — there is no `monsterui` (or `daisyui`) dependency.

---

## Quick Reference

| Category | Components | Location |
|----------|------------|----------|
| **Buttons** | Button, ButtonT | `ui.components` |
| **ButtonLink** | ButtonLink | `ui/primitives.py` (`A()` wrapper, `cls=ButtonT.X`) |
| **Cards** | Card, CardBody, CardHeader, CardTitle, CardFooter | `ui.components` |
| **Primitives** | `icon_tile`, `section_label`, `primary_btn`, `card_row`, `ButtonLink`, `SelectableOptionRow`, `dropdown_menu`, `dropdown_separator`, `UploadDropzone`, `SelectedFileCard` | `ui/primitives.py` |
| **Forms** | Input, Select, Textarea, Checkbox, Radio, Toggle, Range, LabelInput, LabelTextArea, LabelSelect, LabelCheckbox | `ui/forms/` |
| **Feedback** | Alert, Badge, StatusBadge, PriorityBadge, Loading, Progress, RadialProgress | `ui/feedback.py` |
| **Layout** | DivHStacked, DivVStacked, DivFullySpaced, DivCentered, Grid, Container, Row, Stack, FlexItem, Size | `ui/layout.py` |
| **Patterns** | PageHeader, CardGenerator, StatsGrid, EmptyState, ErrorBanner, MetadataBadge, etc. | `ui/patterns/*.py` |
| **Layouts** | BasePage, Navbar, Domain Layouts | `ui/layouts/*.py` |

---

# SKUEL Component Modules

Thin Python wrappers around FastHTML FT components encoding Tailwind class strings (pure Tailwind + Alpine.js, ADR-071).
These are the **lowest-level SKUEL building blocks** — imported directly in route files and views. Everything is re-exported from `ui.components`.

**Module map** (June 2026 — `ui/buttons.py` + `ui/cards.py` + `ui/text.py` deleted PR E):

| Module | Symbols |
|--------|---------|
| `ui.components` | The unified import surface — re-exports Button/ButtonT, Card*, forms, feedback, layout, data, Icon, TabContainer, Accordion, Divider |
| `ui.primitives` | `icon_tile`, `section_label`, `primary_btn`, `card_row`, `ButtonLink`, `SelectableOptionRow`, `dropdown_menu`, `dropdown_separator`, `UploadDropzone`, `SelectedFileCard` |
| `ui.layout` | `Size`, `DivHStacked`, `DivVStacked`, `DivFullySpaced`, `DivCentered`, `Grid`, `Container` |
| `ui.forms` | `Input`, `Select`, `Textarea`, `Checkbox`, `Radio`, `Toggle`, `Range`, `LabelInput`, `LabelTextArea`, `LabelSelect`, `LabelCheckbox` |
| `ui.patterns.modal` | `AlpineModal` — standardized Alpine.js modal wrapper (backdrop, transitions, close-on-backdrop) |
| `ui.feedback` | `AlertT`, `BadgeT`, `ProgressT`, `Alert`, `Badge`, `Loading`, `Progress`, `RadialProgress` |
| `ui.enum_helpers` | `get_submission_status_badge_class`, `get_status_badge_class`, `get_priority_badge_class`, ... |
| `ui.navigation` | `Navbar`, `NavbarStart`, `NavbarCenter`, `NavbarEnd`, `Menu`, `MenuItem`, `Dropdown`, `DropdownTrigger`, `DropdownContent`, `Tabs`, `Tab` |
| `ui.data` | `Table`, `TableFromDicts`, `TableFromLists`, `TableT`, `Divider`, `DividerSplit`, `DividerT` |

**Import pattern:**
```python
from ui.components import Button, ButtonT, Card, CardBody, CardHeader, CardTitle
from ui.primitives import ButtonLink, section_label
from ui.forms import Input, LabelInput, LabelTextArea, LabelSelect, LabelCheckbox, Select, Textarea
from ui.enum_helpers import get_submission_status_badge_class
from ui.feedback import Alert, AlertT, Badge, Progress, ProgressT
from ui.layout import Container, DivHStacked, DivVStacked, Size
from ui.patterns.modal import AlpineModal  # Standardized Alpine.js modal wrapper
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

**Location:** `ui.components` (pure Tailwind — `ui/buttons.py` deleted PR E)

Styled buttons for actions and navigation.

### Button(*c, cls, **kwargs)

Primary action button. Pass style via `cls=ButtonT.X` (not `variant=`).

**Parameters:**
- `*c` - Button label / content
- `cls: ButtonT | tuple[ButtonT, ...]` - Style variant. Use a tuple to combine variant + size.
  - `ButtonT.primary` - Blue accent background
  - `ButtonT.secondary` - Gray background with border
  - `ButtonT.ghost` - Transparent with hover
  - `ButtonT.destructive` - Red for destructive actions
- `size` - Geometry as a string: `"xs"` / `"sm"` / `"md"` (default) / `"lg"` / `"xl"`. Style (`cls`) and geometry (`size`) are separate kwargs and never collide.
- `**kwargs` - Additional attributes (type, disabled, hx_post, etc.)

**Examples:**
```python
from ui.components import Button, ButtonT

# Primary action
Button("Save Changes", cls=ButtonT.primary)

# Secondary action, small — style via cls=, geometry via size=
Button("Cancel", cls=ButtonT.secondary, size="sm")

# Destructive action
Button("Delete", cls=ButtonT.destructive)

# With HTMX
Button("Submit", cls=ButtonT.primary, hx_post="/api/submit", hx_target="#result")
```

### ButtonLink(text, href, cls, size, **kwargs)

Button-styled link for navigation. Lives in `ui/primitives.py`. Pure Tailwind — no UIkit dependency. Use for all action CTAs — not raw `A()` with ad-hoc Tailwind. Raw `A()` is reserved for entity title links, breadcrumbs, sidebar navigation, and inline contextual text links.

**Parameters:**
- `*c` - Link label
- `href: str` - URL destination
- `cls: ButtonT | str | tuple` - Button style variant (colour/border/hover). Use `ButtonT.*` style tokens.
- `size: str` - Geometry: `"xs"`, `"sm"`, `"md"` (default), `"lg"`, `"xl"`
- `**kwargs` - Additional attributes (target, rel, download, x_show, etc.)

**Variant/Size Convention:**

| Action Type | cls | size | Examples |
|---|---|---|---|
| Primary CTA | `ButtonT.primary` | `"sm"` | Submit, Start Ingestion |
| View/Navigate | `ButtonT.ghost` | `"sm"` | View Report, Download, ← Back |
| "View all" section links | `ButtonT.ghost` | `"xs"` | View all →, See all |

**Examples:**
```python
from ui.components import ButtonT
from ui.primitives import ButtonLink

# Primary action CTA
ButtonLink("Submit →", href="/submit?exercise_uid=123", cls=ButtonT.primary, size="sm")

# View/navigate action
ButtonLink("View Report →", href="/reports/456", cls=ButtonT.ghost, size="sm")

# Section "view all" link
ButtonLink("View all →", href="/tasks", cls=ButtonT.ghost, size="xs")

# External link
ButtonLink("Open →", href="https://example.com", cls=ButtonT.ghost,
           target="_blank", rel="noopener noreferrer")
```

---

## Card

**Location:** `ui.components`. Import as `from ui.components import Card, CardBody, CardHeader, CardTitle, CardFooter`.

Container component for grouping related content.

**`cls` gotcha:** `ui.components` handle `cls=None` correctly via `_cls()`. Never pass `cls=None` to a raw FT component — it renders as the literal string `"None"` in the HTML class attribute.

### Card(*children, cls, **kwargs)

Generic card container. Renders a `<div>` with `rounded-lg border bg-card text-card-foreground shadow-sm`. Style variations via `cls=` + Tailwind tokens (e.g. `Card.INTERACTIVE` from `ui.tokens`).

**Parameters:**
- `*children` - Content elements (use `CardBody`, `CardHeader`, `CardTitle`, `CardFooter`)
- `cls: str | tuple` - Additional Tailwind classes
- `**kwargs` - Passed to the underlying `<div>` (HTMX, Alpine, id, etc.)

**Examples:**
```python
from ui.components import Card, CardBody, CardHeader, CardTitle, CardFooter
from fasthtml.common import P

# Standard card
Card(
    CardHeader(CardTitle("Task Details")),
    CardBody(P("Complete the quarterly report by Friday")),
)

# Interactive (hover shadow) — compose with token
from ui.tokens import Card as CardTokens
Card(
    CardHeader(CardTitle("Statistics")),
    CardBody(P("Total: 42")),
    cls=CardTokens.INTERACTIVE,
)
```

---

## Badge

**Location:** `/ui/feedback.py`

Small labels for status, priority, and categories. All badges must use these components — never raw `Span()` with hand-rolled Tailwind color classes. Adopted across 20+ files including all Activity Domain views, finance health tier, explore type pills, teaching status, and learning loop status.

### Badge(*c, variant, size, cls, **kwargs)

Generic badge component. Renders as a styled `Span` with `inline-flex items-center rounded-full border font-medium`.

**Parameters:**
- `*c` - Badge content
- `variant: BadgeT | None` - Color variant (default: `BadgeT.primary`). Set to `None` to skip variant colors and provide via `cls`.
  - `BadgeT.primary`, `secondary`, `accent` (violet), `neutral`, `ghost`, `info` (blue), `success` (green), `warning` (yellow), `error` (red), `outline`
- `size: Size | None` - Badge size (`Size.xs`, `sm`, `md`, `lg`; default: `sm`)
- `cls: str` - Additional CSS classes (appended; use with `variant=None` for custom colors)
- `**kwargs` - Additional HTML attributes

### StatusBadge(status, cls="", **kwargs)

Status-aware badge that delegates to `EntityStatus.get_badge_class()` for canonical styling. Covers all 14 EntityStatus values. Use for any value that is a valid `EntityStatus` member.

**Parameters:**
- `status: str | None` - Status value (case-insensitive, underscores or hyphens). Returns `None` if `None`.
- `cls: str` - Additional CSS classes, merged after the status badge class (follows the [cls-merge contract](#text); never collides via `**kwargs`).
- `**kwargs` - Additional attributes passed to Badge (e.g., `size=Size.sm`)

**Implementation:** Converts status string → `EntityStatus` enum → `get_badge_class()` CSS string. Falls back to gray for unknown values.

### PriorityBadge(priority, **kwargs)

Priority-specific badge with predefined styling.

**Parameters:**
- `priority: str | None` - Priority value (critical, urgent, high, medium, normal, low)

**Auto-mapped colors:**
- "critical", "urgent", "high" → Error (red)
- "medium", "normal" → Warning (yellow)
- "low" → Success (green)

### PriorityBadgeDropdown(uid, priority, domain, singular)

Interactive variant for Activity Domain **cards** (`ui/activities/_shared.py`): the badge is a button that opens an Alpine dropdown of the 4 `Priority` levels; picking one POSTs `/api/{domain}/{uid}/priority` via HTMX and swaps the re-rendered card back in. Unset priority renders a ghost "Priority" badge so it can be set inline. Detail pages keep the static `PriorityBadge`.

### Badge selection convention

| What you're displaying | Component | Example |
|---|---|---|
| EntityStatus value | `StatusBadge(status)` | `StatusBadge("active")` |
| Priority value | `PriorityBadge(priority)` | `PriorityBadge("high")` |
| Priority on an Activity card (inline-editable) | `PriorityBadgeDropdown(uid, priority, domain, singular)` | `PriorityBadgeDropdown(task.uid, "high", domain="tasks", singular="task")` |
| Category with a BadgeT match | `Badge(label, variant=BadgeT.xxx)` | `Badge("Ku", variant=BadgeT.accent)` |
| Category with a custom color | `Badge(label, variant=None, cls="...")` | `Badge("Path Step", variant=None, cls="bg-teal-100 text-teal-800 border-teal-200")` |

**Examples:**
```python
from ui.feedback import Badge, BadgeT, StatusBadge, PriorityBadge
from ui.layout import Size

# StatusBadge for EntityStatus values (canonical colors)
StatusBadge("active")       # green
StatusBadge("submitted")    # yellow
StatusBadge("completed")    # green

# PriorityBadge for priorities
PriorityBadge("high")       # red
PriorityBadge("medium")     # yellow

# Badge for category/type pills
Badge("Ku", variant=BadgeT.accent, size=Size.sm)
Badge("Path Step", variant=None, cls="bg-teal-100 text-teal-800 border-teal-200", size=Size.sm)
Badge("5", variant=BadgeT.primary, size=Size.sm)
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
    Button("Cancel", cls=ButtonT.secondary),
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

## Text (DELETED — PR E, 2026-06-26)

`ui/text.py` was deleted. Typography helpers (`SectionTitle`, `SmallText`, `TruncatedText`, etc.) are replaced by:

- **Section labels:** `section_label()` from `ui/primitives.py` (or `H2` / `H3` with Tailwind classes)
- **Small/muted text:** inline `Span("…", cls="text-sm text-muted-foreground")` or `P("…", cls="text-xs text-muted-foreground")`
- **Truncated text:** inline Tailwind `line-clamp-{1|2|3}` via `cls="line-clamp-2"`
- **Card title:** `CardTitle` from `ui.components`

**`cls` handling:** `ui.components` merge extra `cls` internally via `_cls()` and handle `cls=None` safely — no duplicate-kwarg errors.

---

# Patterns

Composed components built from primitives for common UI patterns.

---

## PageHeader

**Location:** `/ui/patterns/page_header.py`

Consistent header for all pages with title and optional actions. Adopted across all 6 Activity Domain dashboards (Tasks, Goals, Habits, Events, Choices, Principles), Study hub, Curriculum hub, Admin dashboard (7 pages), Analytics, Calendar (3 views), LifePath (5 pages), and Timeline.

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
from ui.components import Button, ButtonT
from ui.primitives import ButtonLink

# Simple header
PageHeader(title="Tasks")

# With subtitle and actions
PageHeader(
    title="Tasks",
    subtitle="Manage your tasks and projects",
    actions=ButtonLink("New Task", href="/tasks/new", cls=ButtonT.primary),
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

## CardGenerator

**Location:** `/ui/patterns/card_generator.py`

Dynamic display card generation from dataclass or dict introspection. The primary tool for building both detail cards (labeled fields) and list cards (compact, unlabeled, with header badges and action slots). Accepts dataclasses and plain dicts.

### CardGenerator.from_dataclass(instance, ...)

**Key Parameters:**
- `instance: Any` - Dataclass instance or dict
- `display_fields: list[str] | None` - Only show these fields (None = all)
- `exclude_fields: list[str] | None` - Skip these fields (default: uid, created_at, updated_at)
- `field_renderers: dict[str, Callable] | None` - Custom renderers per field (return None to skip)
- `field_labels: dict[str, str] | None` - Custom labels per field
- `title_field: str | None` - Field for card title (auto-detects 'title' or 'name')
- `show_labels: bool = True` - When False, omit Label wrappers (list card style)
- `actions: Any = None` - Action slot at card bottom with border-t separator
- `header_badges: list[str] | None` - Fields rendered as badges beside title in flex row
- `title_href: str | None` - Makes title a clickable link
- `card_attrs: dict | None` - Extra card attributes (cls, id, etc.)

**Examples:**
```python
from ui.patterns.card_generator import CardGenerator

# Detail card (labeled fields — admin/detail views)
CardGenerator.from_dataclass(
    expense,
    display_fields=["amount", "description", "category", "vendor", "status"],
    field_renderers={"amount": render_amount},
    actions=Div(ButtonLink("View"), ButtonLink("Edit"), cls="flex gap-2"),
)

# List card (compact — no labels, header badges, actions)
CardGenerator.from_dataclass(
    exercise,
    display_fields=["instructions", "model", "context_notes"],
    show_labels=False,
    field_renderers={"model": render_model_badge, "context_notes": render_notes},
    actions=Div(Button("Edit"), Button("Delete"), cls="flex gap-2"),
)

# Dict support + linked title
CardGenerator.from_dataclass(
    path_dict,
    display_fields=["description", "difficulty", "tags"],
    show_labels=False,
    title_href=f"/pathways/path/{path_dict['uid']}",
    actions=Div(ButtonLink("View Details"), Button("Enroll"), cls="flex gap-2"),
)
```

**Convenience Methods:**
- `CardGenerator.from_list(instances, ...)` - Multiple cards in a `space-y-4` container
- `CardGenerator.compact_card(instance, display_fields)` - Minimal styling variant
- `CardGenerator.detailed_card(instance)` - Shows all fields including empty ones

**Adopted in:** exercises_ui, lesson_ui, habits_ui, finance_ui (x2), pathways_ui (x2).

---

## CardGenerator (continued) — List Cards, Teaching Rows, Insight Cards

CardGenerator handles all card use cases via its unified parameter set. Here are additional patterns beyond the detail-card examples above.

### Activity Domain List Cards

Pass a dict with extracted fields. Use `header_badges` for pre-rendered status/priority badges. Use `metadata` for pre-composed metadata rows.

```python
from ui.patterns.card_generator import CardGenerator
from ui.feedback import StatusBadge, PriorityBadge

CardGenerator.from_dataclass(
    {"title": goal.title, "description": goal.description or ""},
    display_fields=["description"],
    header_badges=[
        StatusBadge(str(goal.status)) if goal.status else None,
        PriorityBadge(str(goal.priority)) if goal.priority else None,
    ],
    show_labels=False,
    metadata=[progress_component, f"Due: {target_date}"],
    actions=actions,
    card_attrs={"id": f"goal-{uid}", "cls": f"border-l-4 {border_cls}"},
)
```

### Teaching Row Cards (subtitle + badges + extra)

Use `subtitle` for text below the title, `header_badges` for badge clusters, `extra` for content after actions.

```python
CardGenerator.from_dataclass(
    {"title": "Essay Draft"},
    display_fields=[],
    subtitle="by Student Name",
    header_badges=[feedback_badge, status_badge("pending")],
    show_labels=False,
    actions=ButtonLink("Review", href="/teaching/review/uid", cls=ButtonT.primary, size="sm"),
    extra=feedback_toggle_div,
    card_attrs={"cls": "bg-background shadow-sm mb-2"},
)
```

### Header Badges — Mixed Types

`header_badges` accepts strings (introspected from dataclass), pre-rendered FT components (pass-through), and `None` (skipped). This enables conditional badges.

```python
header_badges=[
    Badge("3 pending", variant=BadgeT.warning),  # FT component — pass-through
    None if item.is_active else Badge("Inactive"),  # Conditional — None skipped
    "status",  # String — introspected from dataclass field
]
```

### Curriculum Link Cards

Use `title_href` for clickable titles and `metadata` for UID display.

```python
CardGenerator.from_dataclass(
    {"title": path_step.title, "description": path_step.description},
    display_fields=["description"],
    show_labels=False,
    metadata=[path_step.uid],
    title_href=f"/explore/ps/{path_step.uid}",
)
```

---

## StatsGrid

**Location:** `/ui/patterns/stats_grid.py`

**Adoption status:** Used across ~16 files (insights, pathways, analytics, finance, admin, profile). No hand-rolled stat grids remain — all use `StatsGrid()`/`StatItem()`. Never use raw `Div()` + grid + Tailwind for stat layouts.

Grid layout for displaying statistics cards. Uses `StatItem` frozen dataclass for type-safe data passing.

### StatItem (frozen dataclass)

Typed data carrier for a single statistic.

**Fields:**
- `label: str` - Stat label
- `value: str | int` - Stat value
- `change: str | None` - Change text (e.g., "+5 this week")
- `trend: str | None` - Trend direction: "up", "down", "neutral"
- `color: str | None` - Semantic color token (e.g., "success", "primary")

### StatsGrid(stats, cols, **kwargs)

Statistics grid container.

**Parameters:**
- `stats: list[StatItem]` - List of StatItem instances
- `cols: int` - Number of columns (default: 4)
- `**kwargs` - Additional attributes

### StatCard(label, value, change, trend, color, **kwargs)

Individual statistics card (lower-level, use StatItem + StatsGrid for grids).

**Parameters:**
- `label: str` - Stat label
- `value: str | int` - Stat value
- `change: str | None` - Change text
- `trend: str | None` - Trend direction
- `color: str | None` - Semantic color token
- `**kwargs` - Additional attributes

**Examples:**
```python
from ui.patterns.stats_grid import StatItem, StatsGrid, StatCard

# Stats grid (preferred)
StatsGrid([
    StatItem(label="Total Tasks", value=42),
    StatItem(label="Completed", value=28, change="+12%", trend="up"),
    StatItem(label="In Progress", value=14),
], cols=3)

# Single stat card with color
StatCard(label="Completion Rate", value="85%", color="success")
```

---

### StatTile(label, value)

Compact centered value-over-label stat tile — no icon, no Card wrapper. Sits inside a
caller-provided grid (e.g. profile `DomainSummaryCard`). Distinct from `IconStat`
(icon-led, label/value order) and `StatCard` (Card-wrapped, label-over-value).

**Parameters:**
- `label: str` - Stat label shown beneath the value
- `value: str | int` - Stat value (coerced to str)

**Example:**
```python
from ui.patterns.stats_grid import StatTile

StatTile("Active", 42)
```

---

## EmptyState

**Location:** `/ui/patterns/empty_state.py`

Friendly empty state for lists with no items. Renders centered content with `py-12` padding.

**Adoption status:** ~75 usages across ~38 files. All Activity Domain list views, curriculum hub, study/submissions, admin, finance, analytics, lifepath, form submissions, teaching, explore, search, notifications, insights, profile, and other domains. No hand-rolled `Div(P("No ..."))` empty states remain — all use `EmptyState()`.

### EmptyState(title, description, action_text, action_href, icon, **kwargs)

Empty state component.

**Parameters:**
- `title: str` - Main message (e.g., "No tasks yet")
- `description: str` - Optional explanatory text (default: "")
- `action_text: str | None` - Optional CTA button label
- `action_href: str | None` - Optional CTA button URL
- `icon: str | None` - Optional emoji icon displayed above title
- `**kwargs` - Additional attributes (supports `cls` merge)

**Usage Rules:**
- **Primary list views:** `EmptyState(title="...", description="...", action_text="Create ...", action_href="/...")`
- **Secondary sections:** `EmptyState(title="...")` — no CTA
- **Tiny inline indicators** (sidebar `<li>`, analytics cards): Leave as `P()` — `EmptyState` with `py-12` is too heavy

**Examples:**
```python
from ui.patterns.empty_state import EmptyState

# Primary list view with CTA
EmptyState(
    title="No tasks found",
    description="Create one to get started!",
    action_text="Create task",
    action_href="/tasks",
)

# Secondary section (no CTA)
EmptyState(title="No feedback yet")

# With icon
EmptyState(title="No habits for today!", icon="🎉")
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
- `show_details: bool` - Whether to render technical details (default: False)

**Technical Details:**
- Rendered only when the caller passes `show_details=True` — the component
  never reads config; route-boundary callers decide (typically
  `get_settings().application.debug`)
- Displayed in collapsible `<details>` element

**Examples:**
```python
from ui.patterns.error_banner import render_error_banner

# Simple error
render_error_banner("Unable to load tasks")

# With technical details (dev-only, gated by the caller)
render_error_banner(
    "Unable to save task",
    technical_details="Database connection timeout",
    severity="error",
    show_details=get_settings().application.debug,
)

# Warning (non-critical)
render_error_banner(
    "Some data may be incomplete",
    severity="warning",
)
```

### render_inline_error(message)

Compact inline error with WCAG accessibility (`role="alert"`, `aria-live="polite"`).

**Parameters:**
- `message: str` - Error message

**Use cases:**
- Form field validation errors
- HTMX fragment error returns (compact, no full banner needed)
- Inline error states in cards or small sections

**Adoption status:** Used across 12 route files for HTMX fragment errors (2026-03-19). Replaced ad-hoc `P("error", cls="text-error")` and `Div("error", cls="text-red-600")` patterns that lacked accessibility attributes.

**Examples:**
```python
from ui.patterns.error_banner import render_inline_error

# Form field error
Div(
    Input(name="email", cls="input-error"),
    render_inline_error("Invalid email format"),
)

# HTMX fragment error return
if result.is_error:
    return render_inline_error("Could not load data")

# HTMX fragment with target ID preservation
if result.is_error:
    return Div(render_inline_error("Report not found"), id="content-section")
```

---

## SectionHeader

**Location:** `/ui/patterns/section_header.py`

**Adoption status:** ~10 usages across ~7 files (groups, insights, exercises, analytics, admin, ingestion, curriculum adaptive). Never use raw `H2()` for section headers outside cards — use `SectionHeader()`. Card-internal titles (`H2` inside `Card()`) are a different semantic role and don't use SectionHeader.

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
from ui.primitives import ButtonLink

# Simple section header
SectionHeader(title="Recent Tasks")

# With action
SectionHeader(
    title="Recent Tasks",
    actions=ButtonLink("View All", href="/tasks"),
)
```

---

## AlpineModal

**Location:** `/ui/patterns/modal.py`

**Adoption status:** Used across ~5 files (calendar, sharing, insights). No hand-rolled modals remain — all use `AlpineModal()`. Never hand-roll modals with raw `Div()` + `fixed inset-0` + manual onclick handlers.

Standardized Alpine.js-controlled modal with backdrop overlay, click-outside-to-close, transitions, and `x-cloak`.

### AlpineModal(*content, show, close, max_width, scrollable, id)

**Parameters:**
- `*content: Any` - Modal body content (header, form, buttons, etc.)
- `show: str` - Alpine.js expression for visibility (e.g., `"isOpen"`, `"shareModal"`)
- `close: str` - Alpine.js expression to close (e.g., `"close()"`, `"shareModal = false"`)
- `max_width: str` - Tailwind max-width class (default: `"max-w-md"`)
- `scrollable: bool` - Whether content scrolls when exceeding viewport height (default: `False`)
- `id: str | None` - Optional DOM id for the modal container

**Examples:**
```python
from ui.patterns.modal import AlpineModal
from ui.components import Button, ButtonT

# Simple modal with Alpine.js state
AlpineModal(
    H3("Edit Item"),
    some_form,
    show="isOpen",
    close="isOpen = false",
)

# HTMX-inserted modal (auto-open pattern for server-rendered fragments)
Div(
    AlpineModal(
        *content,
        show="open",
        close="open = false; $nextTick(() => document.getElementById('my-modal')?.remove())",
        max_width="max-w-2xl",
        scrollable=True,
    ),
    x_data="{ open: true }",
    id="my-modal",
)
```

---

## Relationship Patterns

**Location:** `/ui/patterns/relationships/*.py`

**NEW: Phase 5 - Lateral Relationships & Vis.js**

Interactive relationship visualization components.

### EntityRelationshipsSection(entity_uid, entity_type)

Complete relationships section with all three views. Uses SKUEL's `Accordion` (`multiple=True`) from `ui.components` for collapsible sections — each sub-component is an `AccordionItem` with built-in chevron icons and collapse transitions. Relationship Network starts expanded by default.

**Parameters:**
- `entity_uid: EntityUID` - Entity UID
- `entity_type: str` - Entity type (tasks, goals, etc.)
- `show_blocking_chain: bool` - Show blocking dependencies (default: True)
- `show_alternatives: bool` - Show alternatives (default: True)
- `show_graph: bool` - Show relationship graph (default: True)

**Includes:**
1. **BlockingChainView** - Vertical flow chart
2. **AlternativesComparisonGrid** - Side-by-side table
3. **RelationshipGraphView** - Interactive Vis.js graph (open by default)

### BlockingChainView(entity_uid, entity_type)

Vertical blocking chain visualization.

### AlternativesComparisonGrid(entity_uid, entity_type)

Side-by-side comparison of alternatives.

### RelationshipGraphView(entity_uid, entity_type, depth)

Interactive force-directed graph.

**Parameters:**
- `entity_uid: EntityUID` - Entity UID
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

### ExploreGraphView(mode, entity_uid, entity_type)

**Location:** `/ui/explore/graph.py`

Interactive Vis.js graph for the Explore sidebar. Distinct from `RelationshipGraphView` — designed for sidebar navigation with filter tabs and full-screen expansion.

**Parameters:**
- `mode: str` - `'hub'` (learning universe) or `'entity'` (entity-centered lateral graph)
- `entity_uid: str` - Entity UID (entity mode only)
- `entity_type: str` - `'ku'` or `'ps'` (entity mode only)

**Alpine Component:** `exploreGraph(mode, entity_uid, entity_type)` in `skuel.js`

**Features:**
- Hub mode: "You" center node + studying Kus + in-progress PSes (`GET /api/explore/graph`)
- Entity mode: reuses existing lateral graph API (`GET /api/{domain}/{uid}/lateral/graph`)
- Filter tabs (All/Learning/Saved) dim non-matching nodes
- Full-screen JS overlay on `document.body` (Escape/backdrop click to close) — creates a second Vis.js network to bypass sidebar `overflow:hidden` + `transform`
- Node colors: violet (#8B5CF6) for Ku, teal (#14B8A6) for PS, blue (#3B82F6) for "You"
- Click-to-navigate maps to `/explore/ku/{id}` and `/explore/ps/{id}`

**Examples:**
```python
from ui.explore.graph import ExploreGraphView

# Hub mode — learning universe
ExploreGraphView(mode="hub")

# Entity mode — centered on Ku
ExploreGraphView(mode="entity", entity_uid="ku_abc", entity_type="ku")

# Entity mode — centered on PathStep
ExploreGraphView(mode="entity", entity_uid="ps:step_1", entity_type="ps")
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

Animate-pulse shimmer placeholders that mirror the visual shape of the content being loaded.

| Component | Use case |
|-----------|----------|
| `SkeletonCard()` | Single card loading state |
| `SkeletonList(count=3)` | Hub panels, HTMX fragment containers that load card lists |
| `SkeletonLines(count=3)` | Inline/panel states (expand-on-click panels, tree nodes, small lists) |
| `SkeletonTimeline()` | Vis.js Timeline — full date-axis bar + 7 labelled Gantt rows filling `h-[70vh]` |
| `SkeletonStats()` | Stats/metrics card |
| `SkeletonTable(rows=5)` | Table loading state |
| `SkeletonSidebar(domain_count=7)` | Sidebar with domain item rows |
| `SkeletonDomainView()` | Domain stats summary + item list |

**SVG graph skeleton** — the `ExploreGraphView` component (`ui/explore/graph.py`) embeds a static SVG inside `explore-graph-container`: 5 shimmer circles (hub + 4 satellites) with connecting lines. JS removes it by id (`#explore-graph-skeleton`) just before `new vis.Network()` paints. Not a reusable function — it is baked into the component.

**Rule:** Use `SkeletonList` for hub panels and HTMX containers that load card lists. Use `SkeletonLines` for lightweight inline states (panels, tree nodes). Never use plain `P("Loading...")` or `Span("Loading...")` as a loading placeholder.

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

# Custom page (full-width, page manages its own layout)
BasePage(
    content=main_content,
    title="Activities",
    request=request,
    page_type=PageType.CUSTOM,
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

### Activity Domain Shared Utilities

**Location:** `/ui/activities/_shared.py`

Shared helpers extracted from the 6 Activity Domain view files to eliminate duplication (2026-04-04).

- `MetadataField(label, *value)` — label + value pair for detail page metadata grids. Wraps `Div(Small(label), *value)`. Used ~60 times across all 6 detail views.
- `safe_id(uid)` — converts UIDs to safe HTML id attributes (replaces `.` and `:` with `-`)
- `PRIORITY_ORDER` — sort-key dict: `{"critical": 0, "high": 1, "medium": 2, "low": 3}`
- `CONNECTION_ICONS` — universal icon + href mapping for all 9 cross-domain connection types
- `ConnectionBadges(connections)` — icon+title badge links for outgoing connections (Tasks, Habits, Events, Choices)
- `ConnectionSummary(connections)` — compact icon+count badges for incoming connections (Goals, Principles)

### ActivityFilterBar (Config-Driven Filter Bar)

**Location:** `/ui/activities/filter_bar.py`

Shared config-driven filter bar for all 6 Activity Domain list views (2026-04-04). Eliminates 6 near-identical per-domain filter bar functions with a single data-driven component.

- `FilterSelect(name, label, options, default)` — frozen dataclass configuring one dropdown
- `FilterBarConfig(fragment_url, list_target_id, filters, sort_options, sort_default, columns)` — frozen dataclass for the full filter bar
- `ActivityFilterBar(config, current_values)` — renders the HTMX-powered filter form

All 6 domain filter configs are centralised in `FILTER_CONFIGS: dict[str, FilterBarConfig]` in `filter_bar.py` (2026-04-10). Route files import `FILTER_CONFIGS` and pass `FILTER_CONFIGS["domain"]` to `ActivityFilterBar()`.

**Live category options (2026-06-10):** `with_user_categories(config, categories)` rebuilds the Category dropdown from the user's distinct category values (`service.search.list_user_categories`). Goals/Habits/Principles wire it via `ActivityUIConfig.list_categories` — the content route replaces the static enum options with "All" + live values, drops the dropdown at 0-1 categories, and falls back to the static config if the fetch fails.

**Note:** Uses SKUEL's `Select` from `ui.components`. Both `Select` and `LabelSelect` render native `<select>` elements with Tailwind styling (`_SELECT_BASE`). (Historically MonsterUI's `MLabelSelect` wrapped the control in a `<uk-select>` web component that hid the native element from HTMX `FormData`, silently dropping values on submission — fixed in #345/#349; forms fully migrated to pure Tailwind in #443, MonsterUI removed per ADR-071.)

### Tasks Views (Active)

**Location:** `/ui/activities/tasks_views.py`

Read-focused task view components (2026-03-30). A clean list with HTMX status toggle, priority/status filtering, and knowledge connections. Uses shared utilities from `_shared.py`.

Components: `TaskStatsBar`, `TaskList` (delegates to generic `ActivityList` in `_shared.py`), `TaskCard`. Filter config: `FILTER_CONFIGS["tasks"]` from `filter_bar.py`. Filter logic: `filter_tasks()` in `core/utils/entity_filters.py`.

Routes: `GET /tasks` (page), `GET /tasks/list-fragment` (HTMX), `POST /api/tasks/{uid}/status` (status update).

### Finance Layout

**Location:** `/ui/finance/layout.py`

Finance page layouts with custom sidebar.

### Sidebar Pages

**Location:** `/ui/patterns/sidebar.py`

Unified sidebar component for all sidebar pages (Activity Domains, Explore, GradeBook, Library, Teaching). Uses `PageType.CUSTOM`.

**Functions:**
- `SidebarPage(content, items, active, title, storage_key, request, ...)` - Full page with sidebar
- `SidebarNav(items, active, title, ...)` - Sidebar + mobile tabs (no BasePage wrapper)
- `alpine_section_renderer(state_var)` - Factory for Alpine-driven sidebar items (instant switching, no page navigation)
- `alpine_mobile_section_renderer(state_var)` - Same for mobile horizontal tabs

**Dataclass:**
- `SidebarItem(label, href, slug, icon, description, badge_text, ...)`

**New parameters (2026-04):**
- `title_prefix` - Element before sidebar title (e.g. back arrow)
- `title_icon` - Lucide icon name replacing the text title (e.g. `"graduation-cap"` for Teaching sidebar)
- `alpine_state` - Shared Alpine x-data on wrapper for sidebar + content communication
- `mobile_item_renderer` - Custom renderer for mobile tabs
- `item_renderer` - Custom renderer for desktop sidebar items

**See:** `@skuel-ui` Pattern 5 for Alpine section renderer guide

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
from ui.components import Button, ButtonT
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
    Button("Save", cls=ButtonT.primary, type="submit"),
    hx_post="/api/tasks",
    hx_target="#result",
)
```

## List Pattern

Entity list with empty state:

```python
from ui.patterns.card_generator import CardGenerator
from ui.patterns.empty_state import EmptyState
from ui.patterns.page_header import PageHeader
from ui.feedback import StatusBadge, PriorityBadge

content = Div(
    PageHeader(
        title="Tasks",
        actions=ButtonLink("New Task", href="/tasks/new"),
    ),
    # List or empty state
    Div(
        *[CardGenerator.from_dataclass(
            {"title": task.title, "description": task.description},
            display_fields=["description"],
            header_badges=[StatusBadge(task.status), PriorityBadge(task.priority)],
            show_labels=False,
        ) for task in tasks],
        cls="space-y-3",
    ) if tasks else EmptyState(
        title="No tasks found",
        description="Create your first task to get started",
        action_text="Create Task",
        action_href="/tasks",
    ),
)
```

## Dashboard Pattern

Stats grid + recent items:

```python
from ui.patterns.stats_grid import StatsGrid, StatCard
from ui.patterns.section_header import SectionHeader
from ui.patterns.card_generator import CardGenerator
from ui.feedback import StatusBadge, PriorityBadge

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
        *[CardGenerator.compact_card(
            {"title": task.title},
            display_fields=[],
        ) for task in recent_tasks[:5]],
        cls="space-y-2",
    ),
)
```

## Page Context Pattern

**Location:** `/ui/page_contexts.py`

Per-domain TypedDicts that define the route→UI contract. Routes build a typed context, views consume it.

```python
from ui.page_contexts import TasksPageContext

# In route: build typed context
page_ctx: TasksPageContext = {
    "entities": tasks,
    "filters": filters.to_dict(),
    "projects": projects,
    "assignees": assignees,
}
view_content = TasksViewComponents.render_list_view(ctx=page_ctx)
```

Each Activity Domain has a standalone TypedDict with typed entities (`list[Task]`, `list[Goal]`, etc.) and `total=True` for required fields. Optional fields use `NotRequired`.

**Available contexts:** `TasksPageContext`, `GoalsPageContext`, `HabitsPageContext`, `EventsPageContext`, `ChoicesPageContext`, `PrinciplesPageContext`, `CurriculumHubContext`, `CurriculumListContext`, `SubmissionsPageContext`, `KuIndexContext`.

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

## From Custom Cards to CardGenerator

**Before (hand-authored):**
```python
Card(
    Div(H3(title), cls="flex justify-between"),
    P(instructions_preview, cls="text-muted-foreground text-sm"),
    Badge(model, variant=BadgeT.info),
    Div(Button("Edit"), Button("Delete"), cls="flex gap-2"),
    cls="p-4",
)
```

**After (CardGenerator):**
```python
CardGenerator.from_dataclass(
    exercise,
    display_fields=["instructions", "model"],
    show_labels=False,
    field_renderers={"model": render_model_badge},
    actions=Div(Button("Edit"), Button("Delete"), cls="flex gap-2"),
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

**SKUEL Components** (pure Tailwind, all re-exported from `ui.components`):
- **Alert / AlertT** - `ui.feedback`
- **Badge / BadgeT** - `ui.feedback`
- **Button / ButtonT** - `ui.components`
- **ButtonLink** - `ui.primitives` (`cls=ButtonT.X`, not `variant=`)
- **Card / CardBody / CardHeader / CardTitle / CardFooter** - `ui.components`
- **Checkbox / Radio / Toggle / Range** - `ui.forms`
- **Container / Grid / DivHStacked / DivVStacked** - `ui.layout`
- **Divider / DividerSplit / DividerT** - `ui.data`
- **Dropdown / DropdownTrigger / DropdownContent** - `ui.navigation`
- **Input / Select / Textarea** - `ui.forms`
- **LabelInput / LabelTextArea / LabelSelect / LabelCheckbox** - `ui.forms`
- **Loading** - `ui.feedback` (CSS-only spinner — no variant param; use `size=Size.sm/md/lg`)
- **Menu / MenuItem / Navbar** - `ui.navigation`
- **AlpineModal** - `/ui/patterns/modal.py` — standardized Alpine.js modal wrapper (backdrop, transitions, accessibility)
- **Progress / ProgressT / RadialProgress** - `ui.feedback`
- **Size** - `ui.layout`
- **Table / TableFromDicts / TableFromLists / TableT** - `ui.data`
- **Tabs / Tab** - `ui.navigation`

**Patterns & Layouts:**
- **BasePage** - `/ui/layouts/base_page.py`
- **Breadcrumbs** - `/ui/patterns/breadcrumbs.py`
- **CardGenerator** - `/ui/patterns/card_generator.py`
- **EmptyState** - `/ui/patterns/empty_state.py`
- **ErrorBanner** - `/ui/patterns/error_banner.py`
- **MetadataBadge** - `/ui/patterns/metadata_badge.py`
- **Navbar (layout)** - `/ui/layouts/navbar.py`
- **PageHeader** - `/ui/patterns/page_header.py`
- **Relationships** - `/ui/patterns/relationships/*.py`
- **SectionHeader** - `/ui/patterns/section_header.py`
- **Skeleton** - `/ui/patterns/skeleton.py`
- **StatsGrid** - `/ui/patterns/stats_grid.py`
- **TreeView** - `/ui/patterns/tree_view.py`

---

# Cross-Domain Consistency Testing

`tests/unit/ui/test_cross_domain_consistency.py` validates that all 6 activity domain views and 4 hub pages use PageHeader, EmptyState, StatsGrid, and EntityRelationshipsSection consistently. Pure unit tests — no DB, no mocks. Run with `uv run pytest tests/unit/ui/test_cross_domain_consistency.py -v`.

# Related Documentation

- **Error Handling Patterns:** `/docs/patterns/ERROR_HANDLING.md`
- **UI Component Patterns:** `/docs/patterns/UI_COMPONENT_PATTERNS.md`
- **WCAG Accessibility Guide:** `/.claude/skills/accessibility-guide/`
- **SKUEL CSS / `ui.components`:** `/.claude/skills/ui-css/`

---

**End of Component Catalog**

For questions or suggestions, see `/docs/INDEX.md` for complete documentation index.
