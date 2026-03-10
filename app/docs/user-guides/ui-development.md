# UI Development Guide

**Last Updated:** 2026-03-10

How to build user interfaces in SKUEL. Covers the component system, page architecture, patterns, and conventions.

---

## Architecture Overview

SKUEL renders server-side HTML with FastHTML. The browser gets complete HTML documents — no client-side framework builds pages. Interactivity comes from two lightweight layers:

| Layer | Tool | Role |
|-------|------|------|
| HTML generation | FastHTML (Python) | Build HTML elements as function calls |
| Semantic styling | DaisyUI 5 + Tailwind CSS | Component classes (`btn`, `card`, `badge`) + utilities |
| Server communication | HTMX | Partial page updates, form submissions, lazy loading |
| Client-side state | Alpine.js | Toggles, modals, filters, dropdowns |

Every page is a Python function that returns HTML. There is no JSX, no template language, no build step for UI code.

---

## Component Layers

```
Layouts   → BasePage, SidebarPage, DashboardLayout
              ↓ compose
Patterns  → PageHeader, EntityCard, StatsGrid, EmptyState, FormGenerator
              ↓ compose
Components → Button, Card, Badge, Input, Select, Alert, Modal, Row, Stack
```

**Components** (`ui/buttons.py`, `ui/cards.py`, etc.) wrap DaisyUI classes into Python functions with typed parameters. They handle styling.

**Patterns** (`ui/patterns/`) compose multiple components into domain-agnostic building blocks. They handle structure.

**Layouts** (`ui/layouts/`) wrap entire pages with consistent chrome (navbar, sidebar, head tags). They handle page-level concerns.

### Where to put new UI code

```
Is it domain-agnostic styling (button, card, input)?
├─ YES → ui/buttons.py, ui/cards.py, ui/forms.py, etc.
Is it reusable across multiple domains?
├─ YES → ui/patterns/
Is it domain-specific but reusable within that domain?
├─ YES → ui/{domain}/views.py
Is it one-off UI for a single route?
├─ YES → Inline in the route file (adapters/inbound/*_ui.py)
```

---

## Component Reference

### Buttons (`ui/buttons.py`)

```python
from ui.buttons import Button, ButtonLink, IconButton, ButtonT
from ui.layout import Size

# Primary action
Button("Save", variant=ButtonT.primary)

# With size
Button("Delete", variant=ButtonT.error, size=Size.sm)

# Loading state
Button("Saving...", variant=ButtonT.primary, loading=True, disabled=True)

# Navigation (renders <a> styled as button)
ButtonLink("View Details", href="/tasks/123")
ButtonLink("Back", href="/tasks", variant=ButtonT.ghost, size=Size.sm)

# Icon button
IconButton("X", variant=ButtonT.ghost, label="Close")

# HTMX action
Button("Archive", variant=ButtonT.warning, hx_post="/api/tasks/archive", hx_target="#task-list")
```

**ButtonT variants:** `primary`, `secondary`, `accent`, `neutral`, `ghost`, `link`, `info`, `success`, `warning`, `error`, `outline`

**Size options:** `Size.xs`, `Size.sm`, `Size.md`, `Size.lg`, `Size.xl`

### Cards (`ui/cards.py`)

```python
from ui.cards import Card, CardBody, CardTitle, CardActions, CardLink, CardT

# Standard card
Card(
    CardBody(
        CardTitle("Task Details"),
        P("Complete the quarterly report by Friday"),
    )
)

# Bordered variant
Card(
    CardBody(
        CardTitle("Habits"),
        P("Track your daily habits"),
        CardActions(
            Button("Add Habit", variant=ButtonT.primary, size=Size.sm),
        ),
    ),
    variant=CardT.bordered,
)

# Clickable card (navigates on click)
CardLink(
    CardBody(
        CardTitle("Morning Routine"),
        P("5 habits tracked"),
    ),
    href="/habits/morning-routine",
)
```

### Forms (`ui/forms.py`)

```python
from ui.forms import Input, Select, Textarea, FormControl, Label, Checkbox, InputT
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

# Wrapped in a form
Form(
    FormControl(
        Label("Title"),
        Input(name="title", placeholder="Task title", required=True),
    ),
    FormControl(
        Label("Description"),
        Textarea(name="description", placeholder="Details..."),
    ),
    Button("Create Task", type="submit"),
    method="post",
    action="/api/tasks",
)
```

**InputT variants:** `bordered` (default), `ghost`, `primary`, `secondary`, `accent`, `info`, `success`, `warning`, `error`

### Feedback (`ui/feedback.py`)

```python
from ui.feedback import Alert, AlertT, Badge, BadgeT, StatusBadge, PriorityBadge
from ui.feedback import Loading, LoadingT, Progress, ProgressT

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

# Loading spinners
Loading(size=Size.lg)
Loading(variant=LoadingT.dots, size=Size.sm)

# Progress bars
Progress(value=75, variant=ProgressT.success)
Progress()  # indeterminate
```

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
# It adds min-w-0 + overflow-hidden so text can actually shrink
Row(
    FlexItem(TruncatedText(long_title), grow=True),   # shrinks properly
    Badge("Due Today", variant=BadgeT.warning),        # stays fixed
)

# Responsive grid
Grid(
    *[EntityCard(...) for e in entities],
    cols=3,        # 1 col mobile, 2 tablet, 3 desktop
    gap=4,
)

# Centered container
Container(
    page_content,
    size="6xl",    # max-w-6xl
)

# Space-between layout (common for headers)
DivFullySpaced(
    H2("Recent Tasks"),
    ButtonLink("View All", href="/tasks", variant=ButtonT.ghost),
)
```

### Typography (`ui/text.py`)

```python
from ui.text import PageTitle, SectionTitle, CardTitle, Subtitle
from ui.text import BodyText, SmallText, Caption, TruncatedText

PageTitle("Dashboard", subtitle="Welcome back, Mike")   # h1 + optional subtitle
SectionTitle("Active Goals")                             # h2
CardTitle("Morning Routine", truncate=True)              # h3, truncates by default
Subtitle("Weekly Summary")                               # h4

BodyText("Task details go here")                         # <p>
BodyText("Secondary info", muted=True)                   # <p> with muted color
SmallText("Last updated 2 hours ago")                    # <span> small + muted
Caption("PRIORITY")                                      # uppercase label

TruncatedText("Very long text that overflows...", lines=2)  # line-clamp
```

### Modals (`ui/modals.py`)

```python
from ui.modals import Modal, ModalBox, ModalAction, ModalBackdrop

Modal(
    "confirm-delete",                          # id — required
    ModalBox(
        H3("Delete Task?"),
        P("This action cannot be undone."),
        ModalAction(
            Button("Cancel", variant=ButtonT.ghost,
                   onclick="document.getElementById('confirm-delete').close()"),
            Button("Delete", variant=ButtonT.error, hx_delete="/api/tasks/123"),
        ),
    ),
    ModalBackdrop(),
)

# Open with: document.getElementById('confirm-delete').showModal()
# Or Alpine.js: @click="$refs.confirmModal.showModal()"
```

### Navigation (`ui/navigation.py`)

```python
from ui.navigation import Menu, MenuItem, Dropdown, DropdownTrigger, DropdownContent, Tabs, Tab

# Dropdown menu
Dropdown(
    DropdownTrigger(Button("Options", variant=ButtonT.ghost)),
    DropdownContent(
        Menu(
            MenuItem(A("Edit", href="/edit")),
            MenuItem(A("Delete", href="/delete"), cls="text-error"),
        ),
    ),
    end=True,   # align right
)

# Tabs
Tabs(
    Tab("List", active=True, hx_get="/tasks?view=list", hx_target="#content"),
    Tab("Calendar", hx_get="/tasks?view=calendar", hx_target="#content"),
    Tab("Analytics", hx_get="/tasks?view=analytics", hx_target="#content"),
    boxed=True,
)
```

### Data Display (`ui/data.py`)

```python
from ui.data import Table, Stats, Stat, StatTitle, StatValue, StatDesc, Tooltip, Divider

# Table
Table(
    Thead(Tr(Th("Name"), Th("Status"), Th("Due"))),
    Tbody(
        Tr(Td("Fix bug"), Td(StatusBadge("active")), Td("Mar 15")),
        Tr(Td("Write docs"), Td(StatusBadge("pending")), Td("Mar 20")),
    ),
    zebra=True,
)

# DaisyUI Stats
Stats(
    Stat(
        StatTitle("Total Tasks"),
        StatValue("142"),
        StatDesc("21% increase from last month"),
    ),
    Stat(
        StatTitle("Completion Rate"),
        StatValue("87%"),
        StatDesc("Above target"),
    ),
)

# Tooltip
Tooltip(Button("Hover me"), tip="This is helpful info", position="bottom")
```

---

## Page Architecture

### BasePage — The Universal Wrapper

Every page goes through `BasePage`. It provides the complete HTML document: `<head>` tags, navbar, layout structure, accessibility features, and script loading.

```python
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType

# Standard page (centered content, no sidebar)
await BasePage(
    content=my_content,
    title="Tasks",
    page_type=PageType.STANDARD,
    request=request,
    active_page="tasks",
)

# Hub page (with sidebar)
await BasePage(
    content=my_content,
    title="Profile",
    page_type=PageType.HUB,
    sidebar=my_sidebar,
    request=request,
    active_page="profile",
)
```

**BasePage is async** because it reads the request to determine auth state for the navbar. Always `await` it.

**`active_page`** highlights the correct navbar link. Values: `"tasks"`, `"goals"`, `"habits"`, `"events"`, `"choices"`, `"principles"`, `"profile"`, `"admin"`, `"insights"`, etc.

### Page Types

| Type | Sidebar | Container | Use Case |
|------|---------|-----------|----------|
| `STANDARD` | None | `max-w-6xl mx-auto` | Most pages |
| `HUB` | Left, `w-64` | `flex-1 min-w-0` | Profile, Admin Dashboard |
| `CUSTOM` | None | Full width | Pages that manage their own layout |

### SidebarPage — Pages with Navigation Sidebar

```python
from ui.patterns.sidebar import SidebarPage, SidebarItem

items = [
    SidebarItem(label="Overview", href="/profile", slug="overview", icon="O"),
    SidebarItem(label="Tasks", href="/profile/tasks", slug="tasks", icon="T"),
    SidebarItem(label="Goals", href="/profile/goals", slug="goals", icon="G"),
    SidebarItem(label="Settings", href="/profile/settings", slug="settings", icon="S"),
]

await SidebarPage(
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
        Button("New Task", variant=ButtonT.primary),
        ButtonLink("Import", href="/tasks/import", variant=ButtonT.ghost),
    ),
)
```

### EntityCard — Universal Entity Display

The standard way to show any domain entity in a list or grid.

```python
from ui.patterns.entity_card import EntityCard, CardConfig, CardVariant

# Default — full layout with description, metadata, actions
EntityCard(
    title="Complete quarterly report",
    description="Summarize Q1 results and present to stakeholders",
    status="active",
    priority="high",
    metadata=["Due: Mar 15", "Project: Finance"],
    actions=Button("View", variant=ButtonT.ghost, size=Size.sm),
    href="/tasks/task_quarterly_abc",
)

# Compact — title and badges only, for dense lists
EntityCard(
    title="Daily standup",
    status="active",
    config=CardConfig.compact(),
)

# Highlighted — emphasized with border and background
EntityCard(
    title="Urgent: Server migration",
    status="blocked",
    priority="critical",
    config=CardConfig.highlighted(),
)
```

### StatsGrid — Dashboard Metrics

```python
from ui.patterns.stats_grid import StatsGrid

StatsGrid([
    {"label": "Active", "value": 42, "change": "+5 this week", "trend": "up"},
    {"label": "Completed", "value": 98, "trend": "neutral"},
    {"label": "Overdue", "value": 3, "change": "+1", "trend": "down"},
    {"label": "Total", "value": 143},
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
from ui.patterns.error_banner import render_error_banner, render_inline_error

# Full error banner (for page-level errors)
render_error_banner(
    "Unable to load tasks",
    technical_details="Database connection timeout",
    severity="error",
)

# Inline error (for form fields or sections)
render_inline_error("This field is required")
```

### Skeleton Loaders

```python
from ui.patterns.skeleton import SkeletonCard, SkeletonList, SkeletonStats, SkeletonTable

# Use with HTMX lazy loading
Div(
    SkeletonList(count=5),
    hx_get="/api/tasks",
    hx_trigger="load",
    hx_swap="innerHTML",
)
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

## Badge Classes (`ui/badge_classes.py`)

When you need raw DaisyUI class strings (for inline styling without component wrappers), use the centralized mappings:

```python
from ui.badge_classes import (
    status_badge_class,
    priority_badge_class,
    priority_border_class,
    submission_status_badge_class,
)

cls = status_badge_class("active")       # "badge-success"
cls = priority_badge_class("critical")   # "badge-error"
cls = priority_border_class("high")      # "border-l-4 border-warning"
```

This is the single source of truth for all status/priority color mappings. Don't hardcode badge classes elsewhere.

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
    variant=ButtonT.error,
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

# Filter list
Div(
    Input(
        placeholder="Search...",
        **{"x-model": "search", "@input.debounce.300ms": "filterResults()"},
    ),
    **{"x-data": "taskFilter()"},  # Component defined in /static/js/skuel.js
)
```

All Alpine.js `x-data` component definitions live in `/static/js/skuel.js`.

---

## Building a Complete Page

Here is the anatomy of a typical SKUEL page route:

```python
# adapters/inbound/example_ui.py

from fasthtml.common import Div
from starlette.requests import Request

from adapters.inbound.auth import require_authenticated_user
from ui.buttons import Button, ButtonLink, ButtonT
from ui.layout import Grid, Stack, Size
from ui.layouts.base_page import BasePage
from ui.layouts.page_types import PageType
from ui.patterns.entity_card import EntityCard, CardConfig
from ui.patterns.empty_state import EmptyState
from ui.patterns.error_banner import render_error_banner
from ui.patterns.page_header import PageHeader
from ui.patterns.stats_grid import StatsGrid
from ui.text import SectionTitle
from ui.tokens import Spacing


def create_example_routes(app, rt, services):
    """Register example UI routes."""

    @rt("/example")
    async def example_page(request: Request):
        user_uid = require_authenticated_user(request)

        # 1. Load data
        result = await services.example.get_all(user_uid)

        # 2. Handle errors
        if result.is_error:
            return await BasePage(
                render_error_banner("Unable to load data", result.error.message),
                title="Example",
                request=request,
                active_page="example",
            )

        entities = result.value or []

        # 3. Build empty state if needed
        if not entities:
            return await BasePage(
                EmptyState(
                    "No items yet",
                    description="Create your first item to get started.",
                    action_text="Create Item",
                    action_href="/example?view=create",
                ),
                title="Example",
                request=request,
                active_page="example",
            )

        # 4. Build page content
        stats = [
            {"label": "Total", "value": len(entities)},
            {"label": "Active", "value": sum(1 for e in entities if e.status == "active")},
        ]

        content = Stack(
            PageHeader(
                "Example",
                subtitle="Your items",
                actions=Button("New Item", variant=ButtonT.primary),
            ),
            StatsGrid(stats),
            SectionTitle("All Items"),
            Grid(
                *[EntityCard(
                    title=e.title,
                    description=e.description,
                    status=e.status,
                    priority=e.priority,
                    href=f"/example/detail?uid={e.uid}",
                    config=CardConfig.default(),
                ) for e in entities],
                cols=3,
            ),
            gap=6,
        )

        # 5. Wrap in BasePage
        return await BasePage(
            content,
            title="Example",
            page_type=PageType.STANDARD,
            request=request,
            active_page="example",
        )
```

### The pattern in five steps

1. **Authenticate** — `require_authenticated_user(request)` or `@require_admin`
2. **Load data** — Call service, get `Result[T]`
3. **Handle errors** — Check `result.is_error`, show `render_error_banner()`
4. **Build content** — Compose components: `PageHeader` + `StatsGrid` + `Grid(EntityCard...)` + etc.
5. **Wrap in BasePage** — Set title, page type, active page for navbar highlighting

---

## CSS Architecture

| File | What it does | When to edit |
|------|-------------|--------------|
| `static/css/output.css` | Compiled Tailwind + DaisyUI | Never — regenerated by `npx tailwindcss` |
| `static/css/main.css` | SKUEL-specific styles (HTMX states, animations, safe areas) | Adding new HTMX transitions or animations |
| `static/css/hierarchy.css` | TreeView, accordion, breadcrumbs | Adding new hierarchy components |
| `static/css/calendar.css` | Calendar grid styling | Calendar features only |
| `static/css/input.css` | Tailwind `@tailwind` directives | Never — this is the Tailwind entry point |

**Rule:** Prefer DaisyUI component classes (`btn`, `card`, `badge`) and Tailwind utilities (`flex`, `gap-4`, `text-sm`) over custom CSS. Only add to `main.css` for things Tailwind/DaisyUI cannot express (animations, HTMX states, CSS custom properties).

---

## Domain-Specific UI

Each Activity Domain has a `ui/{domain}/` directory with domain-specific components:

```
ui/tasks/     — TodoistTaskComponents, TasksViewComponents, layout
ui/goals/     — GoalHierarchyView, views
ui/habits/    — HabitStreakDisplay, views
ui/events/    — EventCalendarView, views
ui/choices/   — ChoiceComparisonView, views
ui/principles/ — PrincipleStrengthView, views
```

These compose the same core components (EntityCard, StatsGrid, etc.) with domain-specific data. The pattern:

```python
# ui/tasks/views.py
class TasksViewComponents:
    @staticmethod
    def render_list(tasks, filters, stats):
        return Stack(
            PageHeader("Tasks", actions=...),
            StatsGrid(stats),
            Grid(*[EntityCard(...) for t in tasks], cols=2),
        )

    @staticmethod
    def render_create(form_data=None):
        return FormGenerator.render(TaskCreateRequest, ...)

    @staticmethod
    def render_detail(task):
        return Card(CardBody(...))
```

---

## Activity Views Base Pattern

All six Activity Domains (Tasks, Goals, Habits, Events, Choices, Principles) share a three-view tab interface:

```python
from ui.patterns.activity_views_base import ActivityViewTabs

tabs = ActivityViewTabs.render("goals", "list", [
    ("list", "List", "List"),         # (id, desktop_label, mobile_label)
    ("create", "Create", "+"),
    ("calendar", "Calendar", "Cal"),
])
```

This renders DaisyUI tabs with HTMX for dynamic content switching.

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
- Add `aria-label` to icon-only buttons via `IconButton(icon, label="Close")`
- Use `role="alert"` for error messages (already built into `Input(error_text=...)`)
- Test keyboard navigation — Tab, Enter, Escape should work

---

## Key Files Quick Reference

| Purpose | File |
|---------|------|
| Buttons | `ui/buttons.py` |
| Cards | `ui/cards.py` |
| Forms | `ui/forms.py` |
| Badges, alerts, progress | `ui/feedback.py` |
| Layout (flex, grid) | `ui/layout.py` |
| Typography | `ui/text.py` |
| Modals | `ui/modals.py` |
| Nav components | `ui/navigation.py` |
| Tables, stats, tooltips | `ui/data.py` |
| Design tokens | `ui/tokens.py` |
| Theme + headers | `ui/theme.py` |
| Badge class mappings | `ui/badge_classes.py` |
| Enum-to-color helpers | `ui/enum_helpers.py` |
| Page wrapper | `ui/layouts/base_page.py` |
| Navbar | `ui/layouts/navbar.py` |
| Sidebar pages | `ui/patterns/sidebar.py` |
| Entity cards | `ui/patterns/entity_card.py` |
| Form generation | `ui/patterns/form_generator.py` |
| Skeleton loaders | `ui/patterns/skeleton.py` |
| Error display | `ui/patterns/error_banner.py` |
| Activity view tabs | `ui/patterns/activity_views_base.py` |
| Component catalog | `docs/ui/COMPONENT_CATALOG.md` |

---

## See Also

- `/docs/ui/COMPONENT_CATALOG.md` — Complete component catalog with all parameters
- `/docs/patterns/UI_COMPONENT_PATTERNS.md` — Architectural patterns and decisions
- `/docs/patterns/FASTHTML_ROUTE_REGISTRATION.md` — Route wiring conventions
- `/docs/patterns/FORM_GENERATOR_GUIDE.md` — FormGenerator deep dive
- `/docs/patterns/HIERARCHY_COMPONENTS_GUIDE.md` — TreeView and hierarchy UI
