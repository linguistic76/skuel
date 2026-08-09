# UI Development Guide

**Last Updated:** 2026-06-30

How to build user interfaces in SKUEL. Covers the component system, page architecture, patterns, and conventions.

> **Component layer (ADR-071):** SKUEL owns its component layer — thin Python FT
> functions encoding Tailwind class strings, in `ui/components/`. MonsterUI / FrankenUI /
> UIkit / DaisyUI are **removed**. Import components from `ui.components` (`Button`, `Card`,
> `Icon`, forms, tables, …); `ButtonLink` lives in `ui.primitives`. The deleted modules
> `ui/buttons.py`, `ui/cards.py`, `ui/text.py` have **no drop-in replacement** — see the
> mapping in each section below.

---

## Architecture Overview

SKUEL renders server-side HTML with FastHTML. The browser gets complete HTML documents — no client-side framework builds pages. Interactivity comes from two lightweight layers:

| Layer | Tool | Role |
|-------|------|------|
| HTML generation | FastHTML (Python) | Build HTML elements as function calls |
| Semantic styling | `ui/components/` (SKUEL-owned, Tailwind CSS) | Component wrappers (`Button`, `Card`, `Badge`) encoding Tailwind class strings |
| Icons | Lucide (server-rendered inline SVG) | `Icon("name")` — no client-side icon runtime (ADR-072) |
| Server communication | HTMX | Partial page updates, form submissions, lazy loading |
| Client-side state | Alpine.js | Toggles, modals, filters, dropdowns |

Every page is a Python function that returns HTML. There is no JSX, no template language, no build step for UI code.

### Quick Decision Matrix

| I need to... | Start here |
|--------------|-----------|
| Build a standard page with list/grid | [Building a Complete Page](#building-a-complete-page) — follow the 5-step pattern |
| Add a form for creating/editing entities | [FormGenerator](#formgenerator--forms-from-pydantic-models) — auto-generates from Pydantic models |
| Show loading states for HTMX content | [Skeleton Loaders](#skeleton-loaders) — `SkeletonList`, `SkeletonCard`, etc. |
| Add a sidebar navigation page | [SidebarPage](#sidebarpage--pages-with-navigation-sidebar) — profile hub pattern |
| Display status/priority with correct colors | [Enum Helpers](#enum-helpers-uienum_helperspy) or `StatusBadge`/`PriorityBadge` |
| Add client-side interactivity (toggles, filters) | [Alpine.js Component Registry](#alpinejs-component-registry) — check if a component already exists |
| Add server-triggered partial updates | [HTMX](#htmx--server-communication) — `hx_get`, `hx_post`, `hx_swap` |
| Style with consistent spacing/containers | [Design Tokens](#design-tokens-uitokenspy) — `Spacing.SECTION`, `Container.STANDARD` |

---

## Component Layers

```
Layouts   → BasePage, SidebarPage, DashboardLayout
              ↓ compose
Patterns  → PageHeader, CardGenerator, StatsGrid, EmptyState, FormGenerator
              ↓ compose
Components → Button, Card, Badge, Input, Select, Alert, Modal, Row, Stack
```

**Components** (`ui/components/` — `button.py`, `card.py`, `form.py`, etc.) are Python FT functions that encode Tailwind class strings with typed parameters. They handle styling. (`ui.feedback`, `ui.layout`, `ui.data` are sibling pure-Tailwind wrapper modules.)

**Patterns** (`ui/patterns/`) compose multiple components into domain-agnostic building blocks. They handle structure.

**Layouts** (`ui/layouts/`) wrap entire pages with consistent chrome (navbar, sidebar, head tags). They handle page-level concerns.

### Where to put new UI code

```
Is it domain-agnostic styling (button, card, input)?
├─ YES → ui/components/ (button.py, card.py, form.py, …)
Is it reusable across multiple domains?
├─ YES → ui/patterns/
Is it domain-specific but reusable within that domain?
├─ YES → ui/{domain}/views.py
Is it one-off UI for a single route?
├─ YES → Inline in the route file (adapters/inbound/*_ui.py)
```

---

## Component Reference

### Buttons (`ui/components/button.py`, `ui/primitives.py`)

`ButtonT` is a `StrEnum` whose values **are** Tailwind class strings. Style goes in `cls=`
(not `variant=`); geometry goes in `size=` (a string, default `"md"`). `cls` and `size`
never collide — `size` classes are applied before the style variant.

```python
from ui.components import Button, ButtonT, Icon
from ui.primitives import ButtonLink   # ButtonLink is NOT in ui.components

# Primary action — style via cls=, NOT variant=
Button("Save", cls=ButtonT.primary)

# With size (string: "xs" | "sm" | "md" | "lg" | "xl")
Button("Delete", cls=ButtonT.destructive, size="sm")

# Navigation (renders <a> styled as button) — same cls=/size= convention
ButtonLink("View Details", href="/tasks/123")
ButtonLink("Back", href="/tasks", cls=ButtonT.ghost, size="sm")

# Icon-only button — IconButton is DELETED. Compose Button + Icon + an aria-label.
Button(Icon("x"), cls=ButtonT.ghost, size="sm", **{"aria-label": "Close"})

# HTMX action (no warning/success variant — see note; use destructive or default + cls)
Button("Archive", cls=ButtonT.default, hx_post="/api/tasks/archive", hx_target="#task-list")
```

**ButtonT variants (slim, semantic):** `default`, `primary`, `secondary`, `ghost`,
`destructive`, `link`.

> ⚠️ **Migration note.** The old MonsterUI `ButtonT` had `accent`/`neutral`/`info`/`success`/
> `warning`/`error`/`outline`. Those are **gone** on `ui.components.ButtonT`. Map `error` →
> `destructive`. For status-colored *badges/alerts* (success/warning/error) use the `ui.feedback`
> components, which keep the full `variant=` enum (see [Feedback](#feedback-uifeedbackpy)) —
> the button and feedback enums are deliberately different.

**Size options:** `"xs"`, `"sm"`, `"md"` (default), `"lg"`, `"xl"`. (The `Size` enum in
`ui.layout` is a `StrEnum` with the same values, so `size=Size.sm` also works, but the
plain string is canonical for buttons.)

### Cards (`ui/components/card.py`)

The card family is `Card`, `CardHeader`, `CardBody`, `CardTitle`, `CardFooter`. There is
**no `variant=`** (style via `cls=`), and `CardActions`, `CardLink`, and `CardT` are
**deleted** — there is no 1:1 replacement.

```python
from ui.components import Card, CardBody, CardHeader, CardTitle, CardFooter, Button, ButtonT

# Standard card
Card(
    CardBody(
        CardTitle("Task Details"),
        P("Complete the quarterly report by Friday"),
    )
)

# Action area — CardFooter replaces the old CardActions (add justify-end for right align)
Card(
    CardBody(
        CardTitle("Habits"),
        P("Track your daily habits"),
        CardFooter(
            Button("Add Habit", cls=ButtonT.primary, size="sm"),
            cls="justify-end gap-2",
        ),
    ),
)

# Clickable card — CardLink is deleted. Wrap the Card in an A(), or add hx_get + cursor.
from fasthtml.common import A
A(
    Card(CardBody(CardTitle("Morning Routine"), P("5 habits tracked"))),
    href="/habits/morning-routine",
    cls="block hover:shadow-md transition-shadow",
)
```

### Forms (`ui/forms/`)

```python
from ui.forms import Input, Select, Textarea, LabelInput, LabelTextArea, LabelSelect, LabelCheckbox, Checkbox
from ui.layout import Size
from fasthtml.common import Option, Form

# Text input (kwargs pass through to HTML <input>)
Input(name="title", placeholder="Enter title", type="text", required=True)

# With validation error
Input(name="email", type="email", error_text="Invalid email address")

# With help text
Input(name="password", type="password", help_text="Must be at least 8 characters")

# Select dropdown (children are <option> elements)
Select(
    Option("Select priority...", value="", disabled=True, selected=True),
    Option("High", value="high"),
    Option("Medium", value="medium"),
    Option("Low", value="low"),
    name="priority",
)

# Textarea
Textarea(name="description", placeholder="Describe the task...", rows=4)

# Checkbox
Checkbox(name="is_public", checked=False)

# Wrapped in a form (LabelInput/LabelTextArea combine label + input)
Form(
    LabelInput("Title", name="title", placeholder="Task title", required=True),
    LabelTextArea("Description", name="description", placeholder="Details..."),
    Button("Create Task", type="submit"),
    method="post",
    action="/api/tasks",
)
```

### Feedback (`ui/feedback.py`)

```python
from ui.feedback import Alert, AlertT, Badge, BadgeT, StatusBadge, PriorityBadge
from ui.feedback import Loading, Progress, ProgressT

# Alerts
Alert("Changes saved successfully!", variant=AlertT.success)
Alert("This action cannot be undone.", variant=AlertT.warning)

# Badges
Badge("New", variant=BadgeT.primary)
Badge("3", variant=BadgeT.error, size=Size.sm)

# Smart badges (auto-map status/priority to colors)
StatusBadge("active")       # -> green badge
StatusBadge("pending")      # -> yellow badge
StatusBadge("blocked")      # -> red badge
PriorityBadge("critical")   # -> red badge
PriorityBadge("low")        # -> green badge

# Loading spinners (CSS-only — no variant param)
Loading()              # md default
Loading(size=Size.sm)

# Progress bars
Progress(value=75, variant=ProgressT.success)
Progress()  # indeterminate

# Radial (circular) progress
from ui.feedback import RadialProgress
RadialProgress(75, size="5rem")            # size is a CSS length (e.g. "4rem", "5rem")
RadialProgress(75, cls="text-success")     # color via cls (variant= is reserved/unused)
```

> The `ui.feedback` components (`Alert`, `Badge`, `Progress`) keep the **full** color enum
> via `variant=` (`AlertT`/`BadgeT`/`ProgressT` all expose `success`/`warning`/`error`/…).
> This is intentionally different from `ui.components.ButtonT`, which is `cls=`-only and slim.

### Layout (`ui/layout.py`)

```python
from ui.layout import Row, Stack, FlexItem, Grid, Container
from ui.layout import DivHStacked, DivVStacked, DivFullySpaced, DivCentered

# Vertical stack (flex-col)
Stack(
    PageHeader("Goals"),
    StatsGrid(stats),
    entity_list,
    gap=6,
)

# Horizontal row with overflow safety
Row(
    FlexItem(CardTitle("Very long title..."), grow=True),
    FlexItem(StatusBadge("active"), shrink=False),
    gap=3,
)

# FlexItem is critical for text truncation in flex layouts
# It adds min-w-0 + overflow-hidden so text can actually shrink.
# TruncatedText is deleted — use a P/Span with Tailwind `truncate` (1 line)
# or `line-clamp-2` (N lines) directly.
Row(
    FlexItem(P(long_title, cls="truncate"), grow=True),   # shrinks properly
    Badge("Due Today", variant=BadgeT.warning),            # stays fixed
)

# Responsive grid
Grid(
    *[CardGenerator.from_dataclass(e, display_fields=["description"], show_labels=False) for e in entities],
    cols=3,        # 1 col mobile, 2 tablet, 3 desktop
    gap=4,
)

# Centered container
Container(
    page_content,
    size="6xl",    # max-w-6xl
)

# Space-between layout (common for headers)
# DivFullySpaced/DivCentered/Center live in ui.components.layout (re-exported by ui.layout)
DivFullySpaced(
    H2("Recent Tasks"),
    ButtonLink("View All", href="/tasks", cls=ButtonT.ghost),
)
```

### Typography — `ui/text.py` is DELETED

`ui/text.py` and all its helpers (`PageTitle`, `SectionTitle`, `Subtitle`, `BodyText`,
`SmallText`, `Caption`, `TruncatedText`) are **gone with no 1:1 replacement.** Page/section
headings now come from **pattern components** that carry the type scale; body text is plain
FastHTML elements with semantic-token Tailwind classes.

| Deleted helper | Use instead |
|----------------|-------------|
| `PageTitle("X", subtitle=…)` | `PageHeader("X", subtitle=…)` from `ui.patterns.page_header` (h1 + subtitle + actions) |
| `SectionTitle("X")` | `SectionHeader("X", action=…)` from `ui.patterns.section_header` (h2 + optional action) |
| `Subtitle("X")` | `H4("X", cls="font-semibold")` (raw FastHTML element) |
| `CardTitle("X")` | `CardTitle("X")` from `ui.components` (unchanged name, new module) |
| `BodyText("X")` | `P("X")` |
| `BodyText("X", muted=True)` | `P("X", cls="text-muted-foreground")` |
| `SmallText("X")` | `Span("X", cls="text-sm text-muted-foreground")` |
| `Caption("X")` | `Span("X", cls="text-xs font-semibold uppercase tracking-wide text-muted-foreground")` (or `section_label()` from `ui.primitives`) |
| `TruncatedText("X", lines=2)` | `P("X", cls="line-clamp-2")` (or `truncate` for 1 line) |

```python
from ui.patterns.page_header import PageHeader
from ui.patterns.section_header import SectionHeader
from ui.components import CardTitle
from fasthtml.common import H4, P, Span

PageHeader("Dashboard", subtitle="Welcome back, Mike")   # h1 + subtitle + optional actions
SectionHeader("Active Goals")                            # h2 + optional action
CardTitle("Morning Routine")                             # card heading (ui.components)
H4("Weekly Summary", cls="font-semibold")                # sub-heading

P("Task details go here")                                # body text
P("Secondary info", cls="text-muted-foreground")         # muted body
Span("Last updated 2 hours ago", cls="text-sm text-muted-foreground")
P("Very long text that overflows...", cls="line-clamp-2")
```

> **Always prefer `PageHeader`/`SectionHeader` over raw `H1()`/`H2()`** — they carry the
> committed type scale (see the `skuel-ui` skill's "Design Direction"). Use raw `H4`/`P`/`Span`
> only for sub-headings and body copy where no pattern component applies.

### Modals (Alpine.js + Tailwind)

Prefer the canonical **`AlpineModal`** helper in `ui/patterns/modal.py` (pure Tailwind +
Alpine, built to avoid the old UIkit conflict). Drop to a raw `Div` only for one-off shapes:

```python
# Alpine.js modal — plain Div with Tailwind + x-show (when AlpineModal doesn't fit)
Div(
    Div(
        H3("Delete Task?", cls="font-bold text-lg"),
        P("This action cannot be undone.", cls="py-4"),
        Div(
            Button("Cancel", cls=ButtonT.ghost, **{"@click": "showModal = false"}),
            Button("Delete", cls=ButtonT.destructive, hx_delete="/api/tasks/123"),
            cls="flex justify-end gap-2",
        ),
        cls="bg-background rounded-lg shadow-lg max-w-lg w-full p-6 relative",
        **{"@click.stop": ""},
    ),
    cls="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4",
    **{"@click": "showModal = false"},
    x_show="showModal",
    x_cloak=True,
)
```

### Data Display (`ui/data.py`)

```python
from ui.data import TableFromDicts, TableT, Divider, DividerSplit, DividerT

# Preferred: TableFromDicts for data-driven tables
TableFromDicts(
    header_data=["Name", "Status", "Due"],
    body_data=[
        {"Name": "Fix bug", "Status": StatusBadge("active"), "Due": "Mar 15"},
        {"Name": "Write docs", "Status": StatusBadge("pending"), "Due": "Mar 20"},
    ],
    cls=(TableT.striped,),
)

# Section divider
Divider()
DividerSplit("OR")  # Divider with centered text
```

---

## Page Architecture

### BasePage — The Universal Wrapper

Every page goes through `BasePage`. It provides the complete HTML document: `<head>` tags, navbar, layout structure, accessibility features, and script loading.

```python
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType

# Standard page (centered content, no sidebar)
BasePage(
    content=my_content,
    title="Tasks",
    page_type=PageType.STANDARD,
    request=request,
    active_page="tasks",
)

# Custom page (full-width, page manages its own layout — used by SidebarPage)
BasePage(
    content=my_content,
    title="Activities",
    page_type=PageType.CUSTOM,
    request=request,
    active_page="activities",
)
```

**BasePage is async** because it reads the request to determine auth state for the navbar. Always `await` it.

**`active_page`** highlights the correct navbar link. Values: `"tasks"`, `"goals"`, `"habits"`, `"events"`, `"choices"`, `"principles"`, `"profile"`, `"admin"`, `"insights"`, etc.

### Page Types

| Type | Sidebar | Container | Use Case |
|------|---------|-----------|----------|
| `STANDARD` | None | `max-w-6xl mx-auto` | Most pages (centered content) |
| `CUSTOM` | None | Full width | Page manages its own layout (used by SidebarPage) |

### SidebarPage — Pages with Navigation Sidebar

```python
from ui.patterns.sidebar import SidebarPage, SidebarItem

items = [
    SidebarItem(label="Tasks", href="/tasks", slug="tasks", icon="✅"),
    SidebarItem(label="Goals", href="/goals", slug="goals", icon="🎯"),
    SidebarItem(label="Habits", href="/habits", slug="habits", icon="🔄"),
]

SidebarPage(
    content=overview_content,
    items=items,
    active="overview",
    title="Profile",
    subtitle="Your activity hub",
    page_title="Profile",
    request=request,
    active_page="profile",
)
```

Desktop: collapsible left sidebar. Mobile: horizontal tab bar at the top.

---

## Pattern Components

### PageHeader

```python
from ui.patterns.page_header import PageHeader

PageHeader(
    "Tasks",
    subtitle="Manage your work",
    actions=Row(
        Button("New Task", cls=ButtonT.primary),
        ButtonLink("Import", href="/tasks/import", cls=ButtonT.ghost),
    ),
)
```

### CardGenerator — Dynamic Card from Dataclass/Dict

The primary tool for generating cards from dataclass instances or dicts. Supports both detail cards (labeled fields) and list cards (compact, unlabeled).

```python
from ui.patterns.card_generator import CardGenerator

# List card — no labels, compact, with actions
CardGenerator.from_dataclass(
    exercise,
    display_fields=["instructions", "model", "context_notes"],
    show_labels=False,
    field_renderers={"model": render_model_badge},
    actions=Div(Button("Edit"), Button("Delete"), cls="flex gap-2"),
)

# Detail card — labeled fields (default)
CardGenerator.from_dataclass(
    expense,
    display_fields=["amount", "description", "category", "status"],
    actions=Div(ButtonLink("View"), ButtonLink("Edit"), cls="flex gap-2"),
)

# Dict support + linked title + header badges
CardGenerator.from_dataclass(
    path_dict,
    display_fields=["description", "difficulty"],
    show_labels=False,
    title_href=f"/pathways/{path_dict['uid']}",
    header_badges=["status"],
)
```

### CardGenerator — List Cards with Badges

For activity domain list views where fields are manually composed as dicts.

```python
from ui.patterns.card_generator import CardGenerator
from ui.feedback import StatusBadge, PriorityBadge

# List card with badges, metadata, and actions
CardGenerator.from_dataclass(
    {"title": "Complete quarterly report", "description": "Summarize Q1 results"},
    display_fields=["description"],
    header_badges=[StatusBadge("active"), PriorityBadge("high")],
    show_labels=False,
    metadata=["Due: Mar 15", "Project: Finance"],
    actions=Button("View", cls=ButtonT.ghost, size="sm"),
)

# Teaching row card with subtitle
CardGenerator.from_dataclass(
    {"title": "Daily standup"},
    display_fields=[],
    subtitle="by Student Name",
    header_badges=[Badge("pending", variant=BadgeT.warning)],
    show_labels=False,
    card_attrs={"cls": "bg-background shadow-sm mb-2"},
)
```

### StatsGrid — Dashboard Metrics

```python
from ui.patterns.stats_grid import StatItem, StatsGrid

StatsGrid([
    StatItem(label="Active", value=42, change="+5 this week", trend="up"),
    StatItem(label="Completed", value=98, trend="neutral"),
    StatItem(label="Overdue", value=3, change="+1", trend="down"),
    StatItem(label="Total", value=143),
])
```

### EmptyState

```python
from ui.patterns.empty_state import EmptyState

EmptyState(
    title="No tasks yet",
    description="Create your first task to get started",
    action_text="Create Task",
    action_href="/tasks?view=create",
    icon="clipboard",
)
```

### Error Handling

```python
from ui.patterns.error_banner import render_error_banner, render_inline_error, render_empty_state_with_error

# Full error banner (for page-level errors)
render_error_banner(
    "Unable to load tasks",
    technical_details="Database connection timeout",
    severity="error",
)

# Inline error (for form fields or sections)
render_inline_error("This field is required")

# Empty state with error context — when a load fails but you want the
# empty-state layout (centered, with optional retry action) instead of a banner
render_empty_state_with_error(
    "No Tasks Found",
    "Unable to load tasks. Please try again later.",
    action_label="Refresh",
    action_href="/tasks",
)
```

### Skeleton Loaders

```python
from ui.patterns.skeleton import SkeletonCard, SkeletonList, SkeletonStats, SkeletonTable
from ui.patterns.skeleton import SkeletonSidebar, SkeletonDomainView

# Use with HTMX lazy loading
Div(
    SkeletonList(count=5),
    hx_get="/api/tasks",
    hx_trigger="load",
    hx_swap="innerHTML",
)

# Profile hub skeletons — used for HTMX lazy-loaded sidebar sections
SkeletonSidebar(domain_count=7)   # Sidebar with domain item placeholders
SkeletonDomainView()               # Stats summary + item list for a single domain
```

### FormGenerator — Forms from Pydantic Models

```python
from ui.patterns.form_generator import FormGenerator

# Pydantic model defines the form structure
class TaskCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, json_schema_extra={"ui_widget": "text"})
    description: str | None = Field(None, json_schema_extra={"ui_widget": "textarea"})
    priority: Priority = Priority.MEDIUM
    due_date: date | None = None

# Generate form automatically
FormGenerator.render(
    model=TaskCreateRequest,
    action="/api/tasks",
    method="post",
    submit_label="Create Task",
)

# Pre-filled for editing
FormGenerator.render(
    model=TaskUpdateRequest,
    action=f"/api/tasks?uid={task.uid}",
    method="post",
    submit_label="Save Changes",
    initial_values={"title": task.title, "description": task.description},
)
```

FormGenerator introspects Pydantic field types to choose widgets:
- `str` → text input (or textarea if field name contains "description", "content", "notes")
- `int`, `float` → number input
- `bool` → checkbox
- `date`, `datetime` → date input
- `Enum` → select dropdown
- `list` → textarea (comma-separated)
- Explicit `json_schema_extra={"ui_widget": "textarea"}` overrides inference

---

## Design Tokens (`ui/tokens.py`)

Consistent spacing, container widths, and text styles. Use these instead of hardcoding Tailwind classes for layout-level concerns.

```python
from ui.tokens import Spacing, Container, Card, Text

# Page-level spacing
Div(
    page_header,
    stats_grid,
    entity_list,
    cls=Spacing.SECTION,       # "space-y-8"
)

# Content-level spacing
Div(
    title,
    description,
    metadata,
    cls=Spacing.CONTENT,       # "space-y-4"
)

# Container widths
Div(content, cls=Container.STANDARD)  # "max-w-6xl mx-auto"
Div(content, cls=Container.NARROW)    # "max-w-4xl mx-auto"
Div(content, cls=Container.WIDE)      # "max-w-7xl mx-auto"
```

---

## Enum Helpers (`ui/enum_helpers.py`)

Bridge layer between UI templates (raw strings) and core enums (which own presentation data). All 22 bridge functions delegate to a single generic `_enum_method()` helper that handles `str → enum → method()` with `ValueError` fallback:

```python
from ui.enum_helpers import (
    get_status_badge_class,
    get_status_border_class,
    get_priority_badge_class,
    get_priority_border_class,
    get_submission_status_badge_class,
)

cls = get_status_badge_class("active")       # "bg-green-100 text-green-800 border-green-200"
cls = get_status_border_class("active")      # "border-l-green-500"
cls = get_priority_badge_class("critical")   # "bg-red-100 text-red-800 border-red-200"
cls = get_priority_border_class("high")      # "border-l-red-500"
```

Presentation data lives on the enums themselves (`EntityStatus.get_badge_class()`, `Priority.get_badge_class()`). To add a new bridge function, use the generic helper:

```python
def get_foo_badge_class(foo: str) -> str:
    return _enum_method(foo, FooEnum, "get_badge_class", "fallback-classes")
```

**Canonical location for `get_submission_status_badge_class`:** `ui.enum_helpers` (not `ui.feedback`).

---

## Interactivity

### HTMX — Server Communication

```python
# Lazy-load content
Div(
    SkeletonList(),
    hx_get="/api/tasks/recent",
    hx_trigger="load",
    hx_swap="innerHTML",
)

# Form submission without page reload
Form(
    Input(name="title", placeholder="Quick add..."),
    Button("Add", type="submit"),
    hx_post="/api/tasks",
    hx_target="#task-list",
    hx_swap="afterbegin",
)

# Delete with confirmation
Button(
    "Delete",
    cls=ButtonT.destructive,
    hx_delete=f"/api/tasks?uid={task.uid}",
    hx_confirm="Are you sure?",
    hx_target=f"#task-{task.uid}",
    hx_swap="outerHTML",
)
```

### Alpine.js — Client-Side State

```python
# Toggle visibility
Div(
    Button("Show Details", **{"@click": "open = !open"}),
    Div(
        P("Hidden content"),
        **{"x-show": "open", "x-transition": ""},
    ),
    **{"x-data": "{ open: false }"},
)

# Filter a rendered list client-side, no round trip
Div(
    Select(
        Option("All", value="all"),
        Option("Overdue", value="overdue"),
        Option("High priority", value="high_priority"),
        **{"x-model": "filterPreset"},
    ),
    *[
        Div(
            task.title,
            # matchesFilter(status, isOverdue, isHighPriority, isThisWeek).
            # json.dumps() — NOT an f-string: Python's True renders as "True",
            # which Alpine evaluates as an undefined identifier, not a boolean.
            **{
                "x-show": "matchesFilter("
                f"{json.dumps(task.status.value)}, "
                f"{json.dumps(task.uid in overdue_uids)}, false, false)"
            },
        )
        for task in tasks
    ],
    **{"x-data": "domainFilter()"},  # Component defined in /static/js/skuel.js
)
```

Named Alpine components live in a `/static/js/` bundle — `skuel.js` for the 22
shared ones, or a page-local bundle for the 4 single-surface ones.

### Alpine.js Component Registry

**Rule:** every `Alpine.data()` definition belongs in a `/static/js/` bundle — never inline in a Python template. Which bundle depends on reach: `skuel.js` for anything more than one page uses; a page-local bundle (see [the page-local inventory](../architecture/ALPINE_JS_ARCHITECTURE.md#available-components)) when exactly one surface needs it, so single-page behaviour stays off every other page's critical path.

One-off state that lives and dies with a single element does not need a registered component at all — an inline `x-data="{ open: false }"` object is the right call there.

#### Tier 1 — Commonly Needed

<!-- alpine-registry:begin -->

| Component | Usage | What it does |
|-----------|-------|-------------|
| `collapsible` | `x-data="collapsible(true)"` | Expand/collapse one section. `expanded` + `toggle()`. The smallest useful component. |
| `collapsibleSidebar` | `x-data="collapsibleSidebar('profile')"` | Sidebar collapse/expand with localStorage persistence. Pass a `storageKey` to remember state; instances sharing a key share an `Alpine.store`. |
| `searchFilters` | `x-data="searchFilters()"` | Search input + filter dropdowns with debounced HTMX requests. |
| `domainFilter` | `x-data="domainFilter()"` | Client-side sort + filter presets over an already-rendered list. `sortBy`, `filterPreset`, `matchesFilter(...)`, `toggleShowAll()`. |
| `formValidator` | `x-data="formValidator()"` | Client-side validation with per-field error display. Validates on blur and submit. |
| `chartVis` | `x-data="chartVis('/api/x.json', 'bar')"` | Chart.js chart from a JSON endpoint. Models the load explicitly: `loading`, `error`, `chart`. |
| `toastManager` | `x-data="toastManager"` | Toast notification stack. Triggered by `X-Toast-Message`/`X-Toast-Type` HTMX response headers or a `$dispatch('toast', { message, type })` event. Methods: `show(message, type, duration)`, `dismiss(id)`, auto-dismiss. |

<!-- alpine-registry:end -->

**Modals are not in this table.** Use the `AlpineModal` FastHTML wrapper
(`ui/patterns/modal.py`) — it renders the backdrop, transitions and click-out
for you and takes plain Alpine expressions. The modal's *state* is whatever
component wraps it, often an inline `{ isOpen: false }`.

**Button loading state is not in this table either.** It is HTMX-native: point
`hx_indicator` at an element carrying the `htmx-indicator` class. Reach for
Alpine only when you need to disable or relabel the control as well, and then an
inline `x-data="{ busy: false }"` driven by `x-on:htmx:before-request` is enough.

```python
# Example: confirm modal via the shared AlpineModal wrapper
from ui.patterns.modal import AlpineModal

Div(
    Button("Delete…", **{"@click": "isOpen = true"}),
    AlpineModal(
        H3("Delete?"),
        P("This cannot be undone."),
        Div(
            Button("Cancel", cls=ButtonT.ghost, **{"@click": "isOpen = false"}),
            Button("Delete", cls=ButtonT.destructive, hx_delete="/api/items/123"),
            cls="flex gap-2 justify-end mt-4",
        ),
        show="isOpen",
        close="isOpen = false",
        max_width="max-w-lg",
    ),
    **{"x-data": "{ isOpen: false }"},
)
```

`AlpineModal` owns the backdrop, the `x-transition`, the `x-cloak` and the
click-out-to-close — pass `show`/`close` as Alpine expressions and it wires the
rest. When the modal needs behaviour beyond a boolean (lazy-loading its body,
for instance), back it with a registry component and pass `close="close()"`;
`insightDetailModal(uid)` is the worked example in `skuel.js`.

#### Tier 2 — Domain-Specific

These are purpose-built for specific features. Check `skuel.js` for their full API before using.

<!-- alpine-registry:begin -->

| Component | Domain |
|-----------|--------|
| `calendarLegend` | Calendar views — legend swatches double as type filters |
| `hierarchyTree` | Goal/KU hierarchy tree views |
| `relationshipGraph` | Vis.js lateral relationship graphs |
| `exploreGraph`, `exploreSearch` | Explore sidebar — graph + tag/text search |
| `entityPicker` | Searchable cross-domain UID picker (pairs with `EntityPicker`) |
| `bulkInsightManager`, `insightDetailModal`, `insightFiltersDebounced` | Insight cards |
| `profileFocusHandler` | Profile hub focus navigation |
| `revisionForm` | Revision feedback points |
| `submit`, `batchTranscribe`, `userFolderTranscribe` | Submission + transcription surfaces |
| `offlineIndicator` | PWA offline banner |

<!-- alpine-registry:end -->

Tier 1 and Tier 2 together are the complete **shared** registry — the 22
components in `skuel.js`. Both tables are machine-checked by
`tests/unit/docs/test_alpine_docs_registry.py`; a component deleted from
`skuel.js` fails the build until these rows follow.

Four more components live in page-local bundles rather than `skuel.js`, loaded
only by their own routes, for 26 in total. They are enumerated once — in
[ALPINE_JS_ARCHITECTURE.md § Available Components](../architecture/ALPINE_JS_ARCHITECTURE.md#available-components),
which is machine-checked — so this guide does not repeat the list. Add to
`skuel.js` when more than one page needs the component; otherwise keep it
page-local.

Calendar note: the calendar's Alpine component was renamed from calendarPage to
`calendarLegend` in #621, when the legend became the type filter. Its old sibling
calendarModal was deleted in `327f26623`; calendar modals now use the shared
`AlpineModal` wrapper.

---

## Building a Complete Page

Here is the anatomy of a typical SKUEL page route:

```python
# adapters/inbound/example_ui.py

from fasthtml.common import Div
from adapters.inbound.fasthtml_types import Request

from adapters.inbound.auth import require_authenticated_user
from ui.components import Button, ButtonT
from ui.primitives import ButtonLink
from ui.layout import Grid, Stack
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.card_generator import CardGenerator
from ui.patterns.empty_state import EmptyState
from ui.patterns.error_banner import render_error_banner
from ui.patterns.page_header import PageHeader
from ui.patterns.section_header import SectionHeader
from ui.patterns.stats_grid import StatsGrid
from ui.tokens import Spacing


def create_example_routes(app, rt, services):
    """Register example UI routes."""

    @rt("/example")
    async def example_page(request: Request):
        user_uid = require_authenticated_user(request)
        result = await services.example.get_all(user_uid)

        if result.is_error:
            return BasePage(
                render_error_banner("Unable to load data", result.error.message),
                title="Example", request=request, active_page="example",
            )

        entities = result.value or []
        if not entities:
            return BasePage(
                EmptyState("No items yet", description="Create your first item.",
                           action_text="Create Item", action_href="/example?view=create"),
                title="Example", request=request, active_page="example",
            )

        stats = [
            {"label": "Total", "value": len(entities)},
            {"label": "Active", "value": sum(1 for e in entities if e.status == "active")},
        ]
        content = Stack(
            PageHeader("Example", subtitle="Your items",
                       actions=Button("New Item", cls=ButtonT.primary)),
            StatsGrid(stats),
            SectionHeader("All Items"),
            Grid(*[CardGenerator.from_dataclass(
                    {"title": e.title, "description": e.description},
                    display_fields=["description"],
                    show_labels=False,
                    title_href=f"/example/detail?uid={e.uid}",
                 ) for e in entities], cols=3),
            gap=6,
        )

        return BasePage(
            content, title="Example", page_type=PageType.STANDARD,
            request=request, active_page="example",
        )
```

### The pattern in five steps

1. **Authenticate** — `require_authenticated_user(request)` or `@require_admin`
2. **Load data** — Call service, get `Result[T]`
3. **Handle errors** — Check `result.is_error`, show `render_error_banner()`
4. **Build content** — Compose components: `PageHeader` + `StatsGrid` + `Grid(CardGenerator...)` + etc.
5. **Wrap in BasePage** — Set title, page type, active page for navbar highlighting

---

## Common Gotchas

**1. `BasePage()`** — BasePage is async. If you forget `await`, the page renders as `<coroutine object BasePage at 0x...>`. Every `BasePage(...)` call must be `BasePage(...)`.

**2. Don't collect `@rt()` routes into lists.** The `@rt()` decorator registers the route immediately with FastHTML. If you also append the function to a `routes = []` list and register that list, the route gets double-registered. Just use `@rt()` and let it handle registration.

**3. `FlexItem` is required for text truncation in flex layouts.** CSS flex items default to `min-width: auto`, which prevents text from shrinking below its content width. Wrapping in `FlexItem(..., grow=True)` adds `min-w-0` + `overflow-hidden` so `TruncatedText` and `line-clamp` actually work.

**4. HTMX screen reader announcements use path-based detection.** The live region in BasePage announces CRUD operations to screen readers by detecting `/create`, `/update`, `/delete` in the request path. If your route doesn't include these substrings, the announcement won't fire.

**5. FormGenerator handles label+input pairing automatically.** For custom form layouts where you need direct control over field placement, use the primitives from `ui/forms/` (`Input`, `Select`, `LabelInput`, `LabelSelect`, `LabelTextArea`) directly instead of `FormGenerator.render()`.

---

## CSS Architecture

| File | What it does | When to edit |
|------|-------------|--------------|
| `static/css/output.css` | **Compiled Tailwind — the single production CSS asset** (ADR-071). Loaded by `build_head()`. No MonsterUI, no browser-JIT compiler. | Never by hand — regenerated by `./dev css-build` |
| `static/css/input.css` | Tailwind entry point (`@tailwind` directives) **+ SKUEL-owned semantic CSS variables** (`--background`, `--primary`, `--card`, …) | Editing theme color values or adding `@layer` rules |
| `static/css/main.css` | SKUEL-specific styles (HTMX states, animations, safe areas, button/input visibility overrides) | Adding new HTMX transitions, animations, or component visibility enhancements |
| `static/css/hierarchy.css` | TreeView, accordion | Adding new hierarchy components |
| `static/css/calendar.css` | Calendar grid styling | Calendar features only |

**Rule:** Prefer the `ui/components/` wrappers (`Button`, `Card`, `Badge`) and Tailwind utilities (`flex`, `gap-4`, `text-sm`) over custom CSS. Only add to `main.css` for things Tailwind cannot express (animations, HTMX states, CSS custom properties).

**CSS variable ownership:** SKUEL owns its semantic CSS variables in `input.css` (the shadcn/ui token pattern), mapped to Tailwind colors in the same file's `@theme inline` block (Tailwind v4 CSS-first config — there is no `tailwind.config.js`). DaisyUI — which previously generated these — is removed.

**Global border radius:** `radii="sm"` (2px/4px) — configured in both `ui/theme.py` and `ui/layouts/base_page.py`. Keeps corners crisp and visible. **Do not change** without updating both files.

**Theme compatibility:** When adding new styles, always use the semantic token classes (e.g., `bg-background`, `text-foreground`, `text-muted-foreground`) so they adapt to theme switching — never raw `text-gray-*` or bespoke hex.

**Rebuilding CSS:** After changing Tailwind classes or `input.css`, regenerate `output.css` (a **required build step** — missing classes are invisible at Python-edit time; the `@source inline(...)` directives in `input.css` cover runtime-composed class strings like `f"gap-{n}"`):

```bash
./dev css-build            # one-time build  (wraps: npm run css:build)
./dev css                  # watch mode during development
./dev css-prod             # minified for production
```

---

## Domain-Specific UI

All six Activity Domains share one directory, `ui/activities/`, with a
`{domain}_views.py` + `{domain}_form.py` pair per domain plus shared pieces:

```
ui/activities/tasks_views.py …    — list/detail view components (one pair per domain)
ui/activities/tasks_form.py …     — create/edit form components
ui/activities/filter_bar.py       — shared list filter bar
ui/activities/_shared.py          — cross-domain view helpers
ui/activities/nav.py              — Activity sidebar (render_activity_sidebar_page)
ui/activities/hub.py              — Activities content embedded in /profile
```

These compose the same core components (`PageHeader`, `StatsGrid`, badges, etc.)
with domain-specific data, and every domain page wraps in
`render_activity_sidebar_page()`. The calendar (Week/Month views) is a
cross-cutting surface with its own `ui/calendar/` module and `/cal/` routes —
it is not part of the per-domain pair pattern.

---

## Accessibility

BasePage includes WCAG 2.1 Level AA features automatically:

- **Skip link** — "Skip to main content" for keyboard users
- **Live region** — `aria-live="polite"` for screen reader announcements
- **Viewport safe areas** — `viewport-fit=cover` for notched devices
- **Semantic HTML** — `<nav>`, `<main>`, `<header>`, `<footer>`
- **ARIA attributes** — Form inputs include `aria-invalid`, `aria-describedby`
- **Focus management** — Keyboard navigation for sidebar, modals, dropdowns
- **Mobile menu** — `aria-expanded` binding on hamburger button

When building new components:

- Use semantic elements (`H2`, `Nav`, `Section`) not generic `Div` for landmarks
- Add `aria-label` to icon-only buttons: `Button(Icon("x"), cls=ButtonT.ghost, **{"aria-label": "Close"})` (the `IconButton` helper is deleted)
- Use `role="alert"` for error messages (already built into `Input(error_text=...)`)
- Test keyboard navigation — Tab, Enter, Escape should work

---

## Key Files Quick Reference

| Purpose | File |
|---------|------|
| Buttons, cards, icon, tables, form set, tabs, accordion | `ui/components/` (import from `ui.components`) |
| `ButtonLink` + shared primitives | `ui/primitives.py` |
| Forms (`Input`, `LabelInput`, `Textarea`, …) | `ui/forms/` |
| Badges, alerts, progress | `ui/feedback.py` |
| Layout (flex, grid) | `ui/layout.py` |
| Typography | `PageHeader`/`SectionHeader` patterns + raw FastHTML `H4`/`P`/`Span` (`ui/text.py` deleted) |
| Modals | `AlpineModal` (`ui/patterns/modal.py`) or inline Alpine `x-show` + Tailwind |
| Navbar | `ui/layouts/navbar.py` (internal to `BasePage`) |
| Tables, dividers | `ui/data.py` |
| Design tokens | `ui/tokens.py` |
| Theme + headers | `ui/theme.py` |
| Enum presentation bridge | `ui/enum_helpers.py` |
| Page wrapper | `ui/layouts/base_page.py` |
| Navbar | `ui/layouts/navbar.py` |
| Sidebar pages | `ui/patterns/sidebar.py` |
| Entity cards | `ui/patterns/entity_card.py` |
| Form generation | `ui/patterns/form_generator.py` |
| Skeleton loaders | `ui/patterns/skeleton.py` |
| Error display | `ui/patterns/error_banner.py` |
| Activity view tabs | `ui/patterns/activity_views_base.py` |
| Alpine.js components | `static/js/skuel.js` |
| Component catalog | `docs/ui/COMPONENT_CATALOG.md` |

---

## See Also

- `/docs/ui/COMPONENT_CATALOG.md` — Complete component catalog with all parameters
- `/docs/patterns/UI_COMPONENT_PATTERNS.md` — Architectural patterns and decisions
- `/docs/patterns/FASTHTML_ROUTE_REGISTRATION.md` — Route wiring conventions
- `/docs/patterns/FORM_GENERATOR_GUIDE.md` — FormGenerator deep dive
- `/docs/patterns/HIERARCHY_COMPONENTS_GUIDE.md` — TreeView and hierarchy UI
