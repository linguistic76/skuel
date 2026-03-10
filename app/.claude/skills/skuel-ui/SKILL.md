---
name: skuel-ui
description: Expert guide for building UI in SKUEL — covers page architecture, component composition, navigation, sidebar pages, and forms. Self-contained with inline CSS and interactivity guidance. Use when building any SKUEL page or feature, creating forms, navigation, components, layouts, or sidebars. Triggers for: "build a page", "create a form", "navigation", "component", "layout", "sidebar", "BasePage", "TaskCard", "PageHeader", or any SKUEL-specific UI work.
allowed-tools: Read, Grep, Glob
---

# SKUEL UI: Pages · Components · Navigation · Forms

## Core Philosophy

> "BasePage for consistency, compose small components, validate early, one sidebar pattern."

**Four principles:**
1. Every page uses `BasePage` — it provides HTML, navbar, auth, ARIA, modals, and all vendor libraries
2. Components are composed from three layers: Primitives → Patterns → Layouts
3. Forms validate at three tiers: HTML5 hints → early Python validation → Pydantic
4. Navigation uses the `SidebarPage` component — no custom CSS, Alpine manages state

---

## 1. Page Architecture

### BasePage — The Foundation

`BasePage` is the single entry point for all pages. It automatically includes HTMX, Alpine.js, DaisyUI, Tailwind, Vis.js, SKUEL's JS/CSS, modal container, and ARIA live regions.

```python
from ui.layouts.base_page import BasePage

return BasePage(
    content,                    # Your page content (FastHTML components)
    title="Tasks",              # Browser tab title
    request=request,            # Auto-detects auth state, user name, admin role
    active_page="tasks",        # Highlights navbar item
)
```

**Never build custom HTML structure** — no bare `Html(Head(...), Body(...))`. Always use `BasePage`. If a custom layout genuinely cannot use `BasePage`, use `build_head()` for the `<head>` — never construct it manually.

```python
# For custom layouts that can't use BasePage (e.g., ActivityLayout):
from ui.layouts.base_page import build_head
Html(build_head("Title", extra_css=["/static/css/calendar.css"]), Body(...))
```

### Page Types

| Type | Use Case | Sidebar | Container |
|------|----------|---------|-----------|
| **STANDARD** (default) | 90% of pages — forms, lists, detail pages | None | `max-w-6xl` centered |
| **HUB** | Admin dashboard with fixed sidebar | Fixed left (256px) | Flexible |
| **CUSTOM** | Collapsible sidebar with persistence | Custom via `SidebarPage()` | Flexible |

```python
from ui.layouts.page_types import PageType

# STANDARD (implicit default)
BasePage(content, title="Tasks", request=request)

# HUB with fixed sidebar
BasePage(
    content,
    page_type=PageType.HUB,
    sidebar=sidebar_html,
    title="Admin",
    request=request,
)

# CUSTOM — use SidebarPage() instead (see Sidebar Pages section)
```

**Decision tree:**
```
Need a sidebar?
├─ NO → PageType.STANDARD
├─ YES, fixed/static? → PageType.HUB
└─ YES, collapsible + state persistence? → SidebarPage()
```

### Design Tokens

Use tokens from `/ui/tokens.py` for consistent spacing — never hardcode:

```python
from ui.tokens import Container, Spacing, Card

# Containers
Container.STANDARD  # "max-w-6xl mx-auto"   — standard pages
Container.NARROW    # "max-w-4xl mx-auto"   — narrow content
Container.WIDE      # "max-w-7xl mx-auto"   — wide dashboards

# Spacing
Spacing.PAGE        # "p-6 lg:p-8"          — page-level padding
Spacing.SECTION     # "space-y-8"           — between sections
Spacing.CONTENT     # "space-y-4"           — between items

# Cards
Card.BASE           # "bg-base-100 border border-base-200 rounded-lg"
Card.INTERACTIVE    # BASE + "hover:shadow-md transition-shadow"
Card.PADDING        # "p-6"
```

### PageHeader and SectionHeader

```python
from ui.patterns import PageHeader, SectionHeader

# Page header with subtitle and action button
PageHeader(
    "Tasks",
    subtitle="Manage your daily work",
    actions=Button("Create Task", cls="btn btn-primary",
                   **{"hx-get": "/tasks/create-modal", "hx-target": "#modal"}),
)

# Section header with action link
SectionHeader(
    "Recent Tasks",
    action=A("View All", href="/tasks/all", cls="link link-primary"),
)
```

### Complete Page Example

```python
@rt("/tasks")
async def get_tasks(request: Request):
    user_uid = require_authenticated_user(request)
    tasks_result = await tasks_service.list_for_user(user_uid)
    if tasks_result.is_error:
        return render_error_banner(str(tasks_result.error))

    content = Div(
        PageHeader("Tasks", subtitle="Manage your daily work"),
        TasksList(tasks_result.value),
        cls=f"{Spacing.PAGE} {Container.STANDARD}",
    )

    return BasePage(content, title="Tasks", request=request, active_page="tasks")
```

---

## 2. Component Composition

### Three-Layer Model

```
Layouts  (/ui/layouts/, /ui/{domain}/layout.py)
    ↓ compose
Patterns (/ui/patterns/, /ui/{domain}/views.py)
    ↓ compose
Components (/ui/buttons.py, /ui/cards.py, /ui/forms.py, /ui/feedback.py, /ui/layout.py, /ui/text.py, … — DaisyUI wrappers)
```

Each layer has a single responsibility: components handle styling, patterns handle domain semantics, layouts handle page structure.

### Decision: Where Does a New Component Go?

```
Is it domain-agnostic styling (button, card, input)?
├─ YES → /ui/buttons.py, /ui/cards.py, /ui/forms.py, etc. (Component — pick the right module)
Is it reusable across multiple domains?
├─ YES → /ui/patterns/ (Pattern)
Is it domain-specific but reusable within domain?
├─ YES → /ui/{domain}/views.py (Domain Pattern)
Is it one-off UI for a single route?
└─ YES → Inline in route handler (no separate component)
```

### Component API Design

```python
# ✅ GOOD: Accept domain object, boolean flags, cls extensibility
def TaskCard(
    task: Task,
    show_actions: bool = True,
    show_description: bool = True,
    cls: str = "",
) -> Any:
    return Card(
        CardBody(
            H4(task.title, cls="font-semibold"),
            P(task.description, cls="text-sm text-base-content/70") if show_description else None,
            CardActions(
                Button("Edit", cls="btn btn-ghost btn-sm",
                       **{"hx-get": f"/tasks/{task.uid}/edit", "hx-target": "#modal"}),
                Button("Complete", cls="btn btn-success btn-sm",
                       **{"hx-post": f"/api/tasks/{task.uid}/complete"}),
            ) if show_actions else None,
        ),
        cls=f"{Card.INTERACTIVE} {cls}".strip(),
    )

# ❌ BAD: Many required primitive params, no defaults
def TaskCard(title: str, desc: str, stat: str, prio: str, uid: str): ...
```

**Principles:**
1. Accept domain objects (`task: Task`) not primitive strings
2. Boolean flags for optional sections (`show_actions: bool = True`)
3. Sensible defaults — most common use works with minimal params
4. `cls: str = ""` for extensibility
5. Type hints on all parameters

### Common Patterns Library

```python
from ui.patterns import PageHeader, SectionHeader, EmptyState, StatsGrid

# Empty state with optional action
EmptyState(
    "No tasks found.",
    icon="✅",
    action=Button("Create Task", cls="btn btn-primary"),
)

# Stats grid
StatsGrid([
    {"label": "Total", "value": "42", "icon": "✅", "trend": "+5"},
    {"label": "Completed", "value": "18", "icon": "🎉"},
    {"label": "Overdue", "value": "3", "icon": "⚠️", "trend": "-2"},
])
```

### Composition Strategies

```python
# Strategy 1: Function composition (preferred)
def GoalCard(goal: Goal, show_actions: bool = True) -> Any:
    return Card(CardBody(
        H4(goal.title),
        Badge(goal.status.value, cls="badge badge-success"),
        CardActions(Button("Update", ...)) if show_actions else None,
    ))

# Strategy 2: Static class for grouped domain components
class TasksViewComponents:
    @staticmethod
    def render_list(tasks: list[Task]) -> Any:
        return Grid(*[TaskCard(t) for t in tasks], cls="grid-cols-1 gap-4")

# Strategy 3: Configuration-driven (use when N domains share one layout)
# Real example: ActivityDomainViewConfig in ui/profile/activity_views.py
# Six Activity Domain views share one layout — only data-extraction varies per domain.
# Mirrors DomainConfig at the service layer.

@dataclass(frozen=True)
class ActivityDomainViewConfig:
    domain: str
    title: str
    icon: str
    section_title: str
    href_prefix: str
    view_all_text: str
    empty_message: str
    intelligence_card_title: str
    show_filter_controls: bool
    item_limit: int
    stats_fn: Callable[[UserContext], StatsResult]        # domain-specific extraction
    items_fn: Callable[[UserContext], list[dict[str, Any]]]
    recommendations_fn: Callable[[UserContext], list[Recommendation]]

# Single layout implementation — config drives all decisions
def ActivityDomainView(config: ActivityDomainViewConfig, context: UserContext) -> Div: ...

# Six thin public wrappers with unchanged signatures
def TasksView(context: UserContext, focus_uid: str | None = None) -> Div:
    return ActivityDomainView(TASKS_CONFIG, context, focus_uid)
```

**When to use Strategy 3:** When three or more domain components share the same layout but differ only in data extraction. Use a frozen dataclass (not a dict) so the config is type-safe and immutable.

### Domain Page Layout

```python
# Domain-specific page layout wrapper
def create_tasks_page(content: Any, request: Request | None = None) -> Any:
    return BasePage(
        Div(
            PageHeader("Tasks", actions=Button("New Task", cls="btn btn-primary")),
            content,
            cls=f"{Spacing.PAGE} {Container.STANDARD}",
        ),
        title="Tasks",
        request=request,
        active_page="tasks",
    )
```

---

## 3. Navigation

### NavItem Configuration

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class NavItem:
    label: str
    href: str
    page_key: str         # Matches active_page parameter for highlighting
    requires_auth: bool = True
    requires_admin: bool = False

MAIN_NAV_ITEMS: tuple[NavItem, ...] = (
    NavItem("Profile Hub", "/profile/hub", "profile/hub"),
    NavItem("Search", "/search", "search"),
    NavItem("Calendar", "/calendar", "calendar"),
)
```

### Profile Dropdown (Avatar Menu)

Activity Domains (Tasks, Goals, Habits, Choices, Principles, Events) live in the navbar avatar dropdown, not the main nav. See `/ui/layouts/nav_config.py` for `PROFILE_DROPDOWN_ITEMS`.

```python
# Rendering pattern (from navbar.py)
def _profile_dropdown(current_user: str) -> Div:
    return Div(
        Button(
            Div(current_user[0].upper(), cls="size-8 rounded-full bg-primary flex items-center justify-center"),
            cls="btn btn-ghost btn-circle",
            **{"@click": "toggleProfile()", "data-profile-trigger": "true"},
        ),
        Div(
            A("Your profile", href="/profile", cls="block px-4 py-2"),
            *profile_dropdown_links,
            id="profile-dropdown",
            cls="absolute right-0 z-50 mt-2 w-48 rounded-lg bg-base-100 shadow-lg",
            **{"x-show": "profileMenuOpen", "x-transition": "", "x-cloak": ""},
        ),
        cls="relative",
    )
```

### Mobile Navigation

The navbar Alpine component (`navbar()` in `skuel.js`) handles both mobile hamburger and profile dropdown:

```python
Nav(
    # ... nav content ...
    **{"x-data": "navbar()"},
    cls="navbar bg-white border-b border-gray-200 sticky top-0 z-50",
)

# Mobile menu button
Button(
    Span(_hamburger_icon(), **{"x-show": "!mobileMenuOpen"}),
    Span(_close_icon(), **{"x-show": "mobileMenuOpen", "x-cloak": ""}),
    cls="btn btn-ghost btn-square sm:hidden",
    **{"@click": "toggleMobile()"},
)

# Mobile menu panel
Div(
    *[_nav_link(item, active_page, mobile=True) for item in nav_items],
    cls="sm:hidden",
    **{"x-show": "mobileMenuOpen", "x-transition": "", "x-cloak": ""},
)
```

**Navbar accessibility requirements:**

| Element | Required Attribute |
|---------|--------------------|
| `<nav>` | `aria-label="Main navigation"` |
| Icon buttons | `<span class="sr-only">Description</span>` |
| Dropdowns | `aria-haspopup="true"` on trigger |

---

## 4. Sidebar Pages

Use `SidebarPage()` for pages with collapsible, persistent sidebar navigation (Profile, KU, Submissions, Journals, Askesis).

### SidebarItem

```python
from ui.patterns.sidebar import SidebarItem

SidebarItem(
    label="Submit",              # Display text
    href="/submissions/submit",  # Navigation URL
    slug="submit",               # For active state matching
    icon="📤",                   # Optional emoji
    description="",              # Optional subtitle (renders two-line item)
    badge_text="",               # Optional badge (e.g., count)
    badge_cls="badge badge-sm badge-ghost",
    hx_attrs={},                 # Optional HTMX attributes
)
```

### SidebarPage (Primary API)

```python
from ui.patterns.sidebar import SidebarItem, SidebarPage

items = [
    SidebarItem("Submit", "/submissions/submit", "submit", icon="📤"),
    SidebarItem("Browse", "/submissions/browse", "browse", icon="📂"),
    SidebarItem("Projects", "/submissions/projects", "projects", icon="📋"),
]

return await SidebarPage(
    content=my_content,
    items=items,
    active="submit",                    # Active item slug
    title="Reports",                    # Sidebar heading
    storage_key="reports-sidebar",      # localStorage key for collapse state
    request=request,
    active_page="reports",              # Navbar active item
    # Optional:
    subtitle="",                        # Sidebar subtitle
    extra_sidebar_sections=[],          # Additional content below nav items
    extra_mobile_sections=[],           # Below mobile tabs
    item_renderer=None,                 # Custom render function
    title_href="",                      # Link on sidebar title
)
```

### Layout Behavior

**Desktop (lg: 1024px+):** Fixed left sidebar (256px) with collapse toggle → collapses to 48px edge.

**Mobile:** Hidden sidebar; DaisyUI horizontal `tabs tabs-bordered` replace it. No drawer, no hamburger overlay.

```
Desktop:              Mobile:
┌──────┬──────────┐  ┌────────────────────┐
│ Side │ Content  │  │[Tab1][Tab2][Tab3]  │
│ bar  │          │  ├────────────────────┤
│ ←    │          │  │ Content            │
└──────┴──────────┘  └────────────────────┘
```

### Sidebar Patterns

**Pattern 1 — Basic (flat list):**
```python
return await SidebarPage(content=content, items=ITEMS, active="overview", title="Reports",
                         storage_key="reports-sidebar", request=request)
```

**Pattern 2 — Extra sections (HTMX-loaded content):**
```python
moc_section = Div(
    H4("Maps of Content", cls="text-sm font-semibold opacity-60 px-3 mt-2"),
    Div(id="moc-list", **{"hx-get": "/api/ku/moc-list", "hx-trigger": "load"}),
)
return await SidebarPage(..., extra_sidebar_sections=[moc_section])
```

**Pattern 3 — Custom item renderer (badges, custom layout):**
```python
def _profile_item_renderer(item: SidebarItem, is_active: bool) -> Any:
    active_cls = "bg-base-200 font-semibold" if is_active else ""
    return Li(A(
        Span(item.icon, cls="text-lg"),
        Span(item.label, cls="flex-1"),
        Span(item.badge_text, cls=item.badge_cls) if item.badge_text else "",
        href=item.href,
        cls=f"flex items-center gap-2 rounded-lg px-3 py-2 hover:bg-base-200 {active_cls}",
    ))

return await SidebarPage(..., item_renderer=_profile_item_renderer)
```

**Pattern 4 — Description items (two-line layout, no custom renderer needed):**
```python
SidebarItem("Overview", "/askesis", "overview", icon="🏠", description="Your life context dashboard")
```

### Alpine Shared Store (Key Detail)

Both sidebar and content area must use the same `Alpine.store()` — without it, collapse state goes out of sync:

```javascript
// Correct: collapsibleSidebar() reads from Alpine.store(storageKey)
// Both sidebar and content reference same store key → stay in sync
Alpine.data('collapsibleSidebar', function(storageKey) {
    return {
        get collapsed() { return Alpine.store(storageKey)?.collapsed ?? false; },
        toggle() {
            var store = Alpine.store(storageKey);
            store.collapsed = !store.collapsed;
            localStorage.setItem(storageKey + '-collapsed', store.collapsed.toString());
        }
    };
});
```

---

## 5. Form Patterns

### FormGenerator (Preferred)

Use `FormGenerator` for all standard forms. It introspects Pydantic request models and generates DaisyUI-styled forms with correct types, constraints, labels, and Alpine.js validation.

```python
from ui.patterns.form_generator import FormGenerator

# Basic — all fields from model
FormGenerator.from_model(TaskCreateRequest, action="/api/tasks")

# With sections (use for Activity Domain create forms)
FormGenerator.from_model(
    GoalCreateRequest,
    action="/api/goals",
    sections={
        "Basic Information": ["title", "description", "why_important"],
        "Classification": ["goal_type", "domain", "priority"],
        "Timeline": ["start_date", "target_date"],
    },
    help_texts={"why_important": "What makes this goal meaningful?"},
    form_attrs={"hx_post": "/api/goals", "hx_target": "#goals-container"},
)

# Edit form from existing entity
FormGenerator.from_instance(
    TaskUpdateRequest, existing_task,
    action=f"/tasks/edit-save?uid={task.uid}",
    submit_label="Save Changes",
)

# Fragment mode — embed in article content (no <form> tag, no submit button)
exercise_fields = FormGenerator.from_model(
    ExerciseSubmissionRequest,
    include_fields=["response", "confidence_level"],
    as_fragment=True,
)
```

**Full guide:** See `/docs/patterns/FORM_GENERATOR_GUIDE.md`

### Three-Tier Validation

| Tier | Technology | Error Type | When |
|------|------------|-----------|------|
| **Client hints** | HTML5 `required`, `maxlength`, `min`/`max` | Browser native | Always (FormGenerator adds these from Pydantic constraints) |
| **Early validation** | Pure Python function | `Result[None]` with clear message | Before Pydantic, custom rules |
| **Schema validation** | Pydantic request model | 422 Unprocessable Entity | Type safety |

### Manual Form Structure (DaisyUI)

For forms that need full custom control beyond FormGenerator's capabilities:

```python
from ui.buttons import Button, ButtonT
from ui.forms import FormControl, Input, Label, LabelText, Select, Textarea

def create_task_form(action_url: str = "/tasks/quick-add") -> Any:
    return Form(
        FormControl(
            Label(LabelText("Title *")),
            Input(type="text", name="title", placeholder="What needs to be done?",
                  required=True, maxlength=200),
        ),
        FormControl(
            Label(LabelText("Description")),
            Textarea(name="description", rows=4),
        ),
        FormControl(
            Label(LabelText("Priority")),
            Select(
                Option("Select...", value="", selected=True),
                Option("Critical", value="critical"),
                Option("High", value="high"),
                Option("Medium", value="medium"),
                Option("Low", value="low"),
                name="priority",
            ),
        ),
        Button("Create Task", variant=ButtonT.primary, type="submit", cls="w-full mt-4"),
        hx_post=action_url,
        hx_target="#task-list",
        hx_swap="beforeend",
        hx_on="htmx:afterRequest: this.reset()",
        cls="space-y-4",
    )
```

### Early Validation Pattern

```python
def validate_task_form_data(form_data: dict[str, Any]) -> Result[None]:
    """Pure function: validate before service call. User-facing error messages."""
    title = form_data.get("title", "").strip()
    if not title:
        return Errors.validation("Task title is required")
    if len(title) > 200:
        return Errors.validation("Title must be 200 characters or less")

    due_str = form_data.get("due_date", "")
    if due_str:
        try:
            date.fromisoformat(due_str)
        except ValueError:
            return Errors.validation("Invalid date format")

    return Result.ok(None)


@rt("/tasks/quick-add", methods=["POST"])
async def create_task(request):
    user_uid = require_authenticated_user(request)
    form_dict = dict(await request.form())

    # Step 1: Early validation
    validation = validate_task_form_data(form_dict)
    if validation.is_error:
        return render_error_banner(f"Validation error: {validation.error}")

    # Step 2: Service call
    result = await tasks_service.create_task(form_dict, user_uid)
    if result.is_error:
        return render_error_banner(str(result.error))

    return TaskCard(result.value)
```

### Modal Forms

```python
@rt("/tasks/create-modal")
async def task_create_modal(request):
    """Return modal HTML for HTMX swap into #modal."""
    return Dialog(
        Div(
            H3("Create Task", cls="font-bold text-lg"),
            create_task_form(action_url="/tasks/quick-add"),
            Div(
                Button("Cancel", cls="btn btn-ghost",
                       **{"onclick": "document.getElementById('modal-dialog').close()"}),
                cls="modal-action",
            ),
            cls="modal-box",
        ),
        id="modal-dialog",
        cls="modal modal-open",
    )

# Trigger button (renders modal into global #modal container)
Button("New Task", cls="btn btn-primary",
       **{"hx-get": "/tasks/create-modal", "hx-target": "#modal"})
```

### Quick-Add Pattern (Minimal Fields)

```python
def render_quick_add_form() -> Any:
    """Single-field rapid entry form."""
    return Form(
        Div(
            Input(type="text", name="title", placeholder="Add a task...",
                  required=True, cls="input input-bordered flex-1"),
            Button("Add", cls="btn btn-primary", type="submit"),
            cls="flex gap-2",
        ),
        hx_post="/tasks/quick-add",
        hx_target="#task-list",
        hx_swap="beforeend",
        hx_on="htmx:afterRequest: this.reset()",
    )
```

### Conditional Fields (Alpine)

```python
Form(
    FormControl(
        Label(LabelText("Task Type")),
        Select(Option("One-time", value="once"), Option("Recurring", value="recurring"),
               name="task_type", cls="select select-bordered w-full",
               **{"x-model": "taskType"}),
    ),
    Div(
        FormControl(
            Label(LabelText("Recurrence Pattern")),
            Select(Option("Daily"), Option("Weekly"), Option("Monthly"),
                   name="recurrence_pattern", cls="select select-bordered w-full"),
        ),
        **{"x-show": "taskType === 'recurring'", "x-transition": ""},
    ),
    Button("Create", cls="btn btn-primary", type="submit"),
    hx_post="/tasks/create",
    **{"x-data": "{ taskType: 'once' }"},
)
```

### Date/Time Inputs

```python
# Date with min constraint
Input(type="date", name="due_date", min=str(date.today()), cls="input input-bordered w-full")

# Time with 15-minute increments
Input(type="time", name="start_time", value="09:00", step="900", cls="input input-bordered w-full")

# Datetime-local
Input(type="datetime-local", name="event_start",
      value=datetime.now().strftime("%Y-%m-%dT%H:%M"), cls="input input-bordered w-full")

# Two-column date row
Div(
    FormControl(Label(LabelText("Start")), Input(type="date", name="start_date", ...)),
    FormControl(Label(LabelText("End")), Input(type="date", name="end_date", ...)),
    cls="grid grid-cols-2 gap-4",
)
```

---

## 6. Inline CSS Reference (SKUEL Essentials)

Use DaisyUI semantic tokens, not Tailwind palette:

```python
# ✅ DaisyUI tokens (respect active theme)
"text-base-content"         # Primary text
"text-base-content/70"      # Secondary text
"bg-base-100"               # Page background
"bg-base-200"               # Subtle surface (hover states, active items)
"border-base-200"           # Subtle borders

# ❌ Tailwind palette (breaks theming)
"text-gray-900"  "bg-white"  "text-gray-600"
```

**Key DaisyUI classes for SKUEL:**

```html
<!-- Buttons -->
<button class="btn btn-primary">Primary</button>
<button class="btn btn-ghost btn-sm">Ghost Small</button>
<button class="btn btn-outline btn-error">Delete</button>

<!-- Status badges -->
<span class="badge badge-success">Active</span>
<span class="badge badge-warning badge-sm">Pending</span>
<span class="badge badge-error">Blocked</span>
<span class="badge badge-ghost">Default</span>

<!-- Alerts / Error banners -->
<div class="alert alert-error"><span>⚠️</span><span>Error message</span></div>
<div class="alert alert-success"><span>Task created!</span></div>

<!-- Cards (using tokens) -->
<div class="bg-base-100 border border-base-200 rounded-lg p-6 hover:shadow-md transition-shadow">

<!-- Loading -->
<span class="loading loading-spinner loading-sm"></span>
```

**Responsive layout:**
```python
# Mobile: stack; Desktop: side-by-side
Div(cls="flex flex-col lg:flex-row gap-4")

# Responsive grid
Div(cls="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6")

# Hide/show at breakpoints
Div(cls="hidden lg:block")   # Desktop only
Div(cls="lg:hidden")         # Mobile only
```

---

## 7. Inline Interactivity Reference (SKUEL Essentials)

### HTMX in Forms

```python
# Submit form, append result to list
Form(
    ...,
    hx_post="/tasks/quick-add",
    hx_target="#task-list",
    hx_swap="beforeend",
    hx_on="htmx:afterRequest: this.reset()",
)

# Load content on page load
Div(id="stats", **{"hx-get": "/api/stats", "hx-trigger": "load"})

# Search with debounce
Input(name="q", **{
    "hx-get": "/search",
    "hx-trigger": "input changed delay:300ms",
    "hx-target": "#results",
})

# Delete with confirmation
Button("Delete", cls="btn btn-error btn-sm", **{
    "hx-delete": f"/api/tasks/{uid}",
    "hx-confirm": "Delete this task?",
    "hx-target": "closest .task-card",
    "hx-swap": "outerHTML swap:300ms",
})
```

### Alpine in SKUEL Forms

```python
# Loading button state
Button("Save", cls="btn btn-primary",
       **{"@click": "loading = true", ":disabled": "loading",
          "x-data": "{ loading: false }"},
       **{"@htmx:after-request": "loading = false"})

# Conditional field visibility
Div(
    FormControl(...),
    **{"x-show": "type === 'recurring'", "x-transition": ""},
)

# Reference centralized components (always prefer over inline x-data)
Div(content, **{"x-data": "loadingButton()"})
Div(content, **{"x-data": "collapsible(false)"})
```

---

## 8. Common Mistakes & Anti-Patterns

```python
# ❌ Custom HTML structure — misses navbar, ARIA, auth, vendor libs
Html(Head(Title("Page")), Body(content))
# ✅ Always use BasePage
BasePage(content, title="Page", request=request)

# ❌ Manual auth parameters
BasePage(content, user_display_name="John", is_authenticated=True)
# ✅ Pass request for auto-detection
BasePage(content, request=request)

# ❌ PageType.HUB for collapsible sidebar
BasePage(content, page_type=PageType.HUB, ...)
# ✅ SidebarPage() for collapsible + state persistence
await SidebarPage(content=content, items=items, ...)

# ❌ Magic container widths
Div(cls="max-w-6xl mx-auto p-6 lg:p-8")
# ✅ Design tokens
Div(cls=f"{Container.STANDARD} {Spacing.PAGE}")

# ❌ DaisyUI drawer for sidebar (conflicts with BasePage padding)
Div(cls="drawer lg:drawer-open", ...)
# ✅ SidebarPage() (Tailwind + Alpine, no conflicts)

# ❌ Duplicate x-data for shared sidebar state
sidebar = Div(**{"x-data": "{ collapsed: false }"})
content = Div(**{"x-data": "{ collapsed: false }"})  # Different instance!
# ✅ SidebarPage() handles Alpine.store() automatically

# ❌ Skipping early validation
result = TaskCreateRequest(**form_data)  # Generic 422 on error
# ✅ Early validation with clear messages
validation = validate_task_form_data(form_dict)
if validation.is_error: return render_error_banner(...)

# ❌ Input without FormControl wrapper (accessibility issue)
Label("Email"), Input(name="email")
# ✅ Wrap in FormControl
FormControl(Label(LabelText("Email")), Input(name="email", ...))

# ❌ GET for mutations
Form(hx_get="/tasks/create")
# ✅ POST for all mutations
Form(hx_post="/tasks/create")

# ❌ Tailwind palette over DaisyUI tokens
P("text", cls="text-gray-600")
# ✅ Semantic DaisyUI tokens
P("text", cls="text-base-content/70")
```

---

## 9. Testing Checklist

When building a new SKUEL page or feature, verify:

**Page structure:**
- [ ] Uses `BasePage` (not custom HTML)
- [ ] Passes `request` parameter (auto auth detection)
- [ ] Includes `active_page` (navbar highlighting)
- [ ] Uses `Container.STANDARD` and `Spacing.PAGE` design tokens

**Navigation:**
- [ ] `<nav>` has `aria-label`
- [ ] Icon buttons have `<span class="sr-only">` text
- [ ] Active page highlighted in navbar

**Sidebar (if applicable):**
- [ ] `SidebarPage()` used (not DaisyUI drawer)
- [ ] `storage_key` is unique per page
- [ ] Desktop collapse works; state persists on reload
- [ ] Mobile shows horizontal tabs (not drawer)

**Forms:**
- [ ] All inputs in `FormControl` + `Label` wrapper
- [ ] Required fields have `required=True` and asterisk in label
- [ ] Early validation function with clear messages
- [ ] POST (not GET) for all mutations
- [ ] Form resets after successful submit (`hx_on="htmx:afterRequest: this.reset()"`)
- [ ] Date constraints set (e.g., `min=str(date.today())`)

**Responsiveness:**
- [ ] Content works at 320px (mobile)
- [ ] No horizontal scroll
- [ ] Sidebar hidden on mobile
- [ ] Navbar collapses to hamburger

**Accessibility:**
- [ ] Keyboard navigation works (Tab, Enter, Escape)
- [ ] Dynamic updates announced (`aria-live="polite"`)
- [ ] Focus management after HTMX swaps

---

## 10. Key Files

| File | Purpose |
|------|---------|
| `/ui/layouts/base_page.py` | `BasePage` + `build_head()` — foundation for all pages |
| `/ui/layouts/page_types.py` | `PageType` enum and config |
| `/ui/layouts/navbar.py` | Navbar with profile dropdown |
| `/ui/layouts/nav_config.py` | `PROFILE_DROPDOWN_ITEMS`, `MAIN_NAV_ITEMS` |
| `/ui/patterns/sidebar.py` | `SidebarItem`, `SidebarNav`, `SidebarPage` |
| `/ui/patterns/__init__.py` | `PageHeader`, `SectionHeader`, `EmptyState`, `StatsGrid`, `FormGenerator` |
| `/ui/patterns/form_generator.py` | `FormGenerator` — dynamic form generation from Pydantic models |
| `/ui/tokens.py` | `Container`, `Spacing`, `Card` design tokens |
| `ui/buttons.py`, `ui/cards.py`, `ui/forms.py`, `ui/modals.py`, `ui/feedback.py`, `ui/layout.py`, `ui/navigation.py`, `ui/data.py` | FastHTML DaisyUI wrappers — 8 focused modules (March 2026) |
| `/static/js/skuel.js` | All Alpine.data() components |
| `/ui/profile/_shared.py` | 5 shared profile primitives (`DomainFilterControls`, `DomainSummaryCard`, `DomainIntelligenceCard`, `_item_list`) |
| `/ui/profile/activity_views.py` | `ActivityDomainViewConfig` + `ActivityDomainView` + 6 public wrappers (Tasks/Goals/Habits/Events/Choices/Principles) |
| `/ui/profile/curriculum_views.py` | KU, LS, LP profile views |
| `/ui/profile/overview.py` | `OverviewView` + all intelligence helper functions |
| `/docs/patterns/UI_COMPONENT_PATTERNS.md` | Complete patterns documentation |

## See Also

- `ui-css` — Deep reference for DaisyUI components and Tailwind utilities
- `ui-browser` — Deep reference for HTMX patterns and Alpine.js directives
- `fasthtml` — FastHTML route patterns and FT component system
- `chartjs` — Chart.js analytics visualization
- `vis-network` — Vis.js graph visualization
