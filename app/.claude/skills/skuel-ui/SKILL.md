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

`BasePage` is the single entry point for all pages. It automatically includes HTMX, Alpine.js, MonsterUI (FrankenUI + Tailwind), Vis.js, SKUEL's JS/CSS, modal container, and ARIA live regions.

```python
from ui.layouts.base_page import BasePage

return BasePage(
    content,                    # Your page content (FastHTML components)
    title="Tasks",              # Browser tab title
    request=request,            # Auto-detects auth state, user name, admin role
    active_page="tasks",        # Highlights navbar item
)
```

**Never build custom HTML structure** — no bare `Html(Head(...), Body(...))`. Two layout functions exist:
- `BasePage()` — authenticated pages (navbar + chrome)
- `AuthPage()` — unauthenticated pages (login, register — no navbar, no chrome)

Both load CSS through `build_head()`. Never construct a `Head(...)` manually or hand-assemble `<link>` tags.

```python
# Authenticated pages (90%+ of the app):
from ui.layouts.base_page import BasePage
return BasePage(content, title="Tasks", request=request, active_page="tasks")

# Unauthenticated pages (login, register, landing):
from ui.layouts.base_page import AuthPage
return AuthPage(login_content, title="Sign In")
```

Auth pages use the same SKUEL component wrappers (`LabelInput`, `Button`, `Card`) — no raw HTML strings, no `NotStr`.

### Page Types

| Type | Use Case | Sidebar | Container |
|------|----------|---------|-----------|
| **STANDARD** (default) | 90% of pages — forms, lists, detail pages | None | `max-w-6xl` centered |
| **HUB** | Admin dashboard with fixed sidebar | Fixed left (256px) | Flexible. Admin home hub at `/` uses STANDARD with `HubSection` cards. |
| **CUSTOM** | Collapsible sidebar with persistence | Custom via `SidebarPage()` | Flexible |

**Notable STANDARD pages:**

| Route | Page | Type | Notes |
|-------|------|------|-------|
| `/tasks` | Tasks list + detail | `STANDARD` | HTMX status toggle, filtering, connection badges |
| `/goals` | Goals list + detail | `STANDARD` | Progress bars, milestones, gravity-well connections |
| `/habits` | Habits list + detail | `STANDARD` | Streaks, atomic habits (cue/routine/reward), identity |
| `/events` | Events list + detail | `STANDARD` | Scheduling, location, recurrence, milestones |
| `/choices` | Choices list + detail | `STANDARD` | Options list, decision framework, outcome/satisfaction |
| `/principles` | Principles list + detail | `STANDARD` | Strength badge, alignment, gravity-well connections |
| `/submissions` | Submissions hub | `STANDARD` | `HomeHub(active_tab='submissions')` — same tabbed interface as `/home` |

```python
from ui.layouts.page_types import PageType

# STANDARD (implicit default)
BasePage(content, title="Tasks", request=request)

# CUSTOM — full-width, page manages its own layout (used by SidebarPage)
BasePage(content, page_type=PageType.CUSTOM, title="Activities", request=request)
```

**Decision tree:**
```
Need a sidebar?
├─ NO → PageType.STANDARD
└─ YES → SidebarPage() (uses PageType.CUSTOM internally)
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
Spacing.PAGE        # "p-4 sm:p-6 lg:p-8"  — page-level padding
Spacing.SECTION     # "space-y-8"           — between sections
Spacing.CONTENT     # "space-y-4"           — between items

# Cards
Card.BASE           # "bg-base-100 border border-base-200 rounded-lg"
Card.INTERACTIVE    # BASE + "hover:shadow-md transition-shadow"
Card.PADDING        # "p-6"
```

### PageHeader and SectionHeader

**Always use `PageHeader()` for page headers** — never raw `H1()` with ad-hoc classes. PageHeader ensures consistent typography (`text-2xl font-bold text-foreground`), spacing (`mb-8`), and subtitle/actions layout. **Always use `SectionHeader()` for section headers outside cards** — never raw `H2()` with ad-hoc classes. SectionHeader ensures consistent typography (`text-xl font-semibold text-foreground`), spacing (`mb-6`), and optional action layout. Skip only for: error headings inside Cards, modal titles, sub-section headings within Cards, or genuinely custom layouts.

```python
from ui.patterns import PageHeader, SectionHeader

# Page header with subtitle and action button
PageHeader(
    "Tasks",
    subtitle="Manage your daily work",
    actions=Button("Create Task", variant=ButtonT.primary,
                   **{"hx-get": "/tasks/create-modal", "hx-target": "#modal"}),
)

# Section header with action link
SectionHeader(
    "Recent Tasks",
    action=A("View All", href="/tasks/all", cls="text-primary hover:underline"),
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
Components (/ui/buttons.py, /ui/cards.py, /ui/forms/, /ui/feedback.py, /ui/layout.py, /ui/text.py, … — MonsterUI wrappers)
```

Each layer has a single responsibility: components handle styling, patterns handle domain semantics, layouts handle page structure.

### Decision: Where Does a New Component Go?

```
Is it domain-agnostic styling (button, card, input)?
├─ YES → /ui/buttons.py, /ui/cards.py, /ui/forms/, etc. (Component — pick the right module)
Is it reusable across multiple domains?
├─ YES → /ui/patterns/ (Pattern)
Is it domain-specific but reusable within domain?
├─ YES → /ui/{domain}/ (e.g. ui/teaching/forms.py, ui/activities/_shared.py)
Is it one-off UI for a single route?
├─ Non-trivial (forms, multi-section panels, display helpers with FT trees)
│  └─ YES → /ui/{domain}/ as a render_*() function — routes must NOT inline Form/Input/Label/Textarea
└─ Trivial (single Div wrapper, layout glue, 1-2 token classes)
   └─ YES → Inline in route handler
```

**Route thinning signal:** If a `*_ui.py` file imports `Form`, `Input`, `Label`, or `Textarea` from fasthtml, HTML construction is leaking into routing. Extract those blocks to a `render_*` function in the domain's `ui/` package.

**Canonical example:** `ui/teaching/forms.py` — holds `render_feedback_submission_form()`, `render_revision_request_form()`, `render_submission_metadata()`. `teaching_ui.py` calls them; it imports none of the form primitives itself.

**Adopted domains (Phase 1):** `ui/lifepath/` (vision form, alignment dashboard), `ui/askesis/` (welcome, chat, settings — dissolved `AskesisUI` class), `ui/activity_review/` (snapshot + feedback forms), `ui/analytics/` (dashboard, 7 domain metrics renderers — dissolved `AnalyticsUIComponents` class), `ui/ingestion/` (ingestion dashboard cards + JS), `ui/system/` (landing page, admin hub, 404 page), `ui/exercises/` (editor, cards, detail), `ui/explore/` (cards, filters).

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
                Button("Edit", variant=ButtonT.ghost, size=Size.sm,
                       **{"hx-get": f"/tasks/{task.uid}/edit", "hx-target": "#modal"}),
                Button("Complete", variant=ButtonT.success, size=Size.sm,
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
from ui.patterns import PageHeader, SectionHeader, EmptyState, StatsGrid, StatCard
from ui.patterns.stats_grid import StatItem
from ui.patterns import ProgressMetric, SettingToggle

# Empty state — primary list view with CTA
EmptyState(
    title="No tasks found",
    description="Create one to get started!",
    action_text="Create task",
    action_href="/activities/tasks?view=create",
)

# Empty state — secondary section (no CTA)
EmptyState(title="No feedback yet")

# Empty state — with icon
EmptyState(title="No habits for today!", icon="🎉")

# Stats grid — uses StatItem frozen dataclass (not dicts)
StatsGrid([
    StatItem(label="Total", value="42", trend="+5"),
    StatItem(label="Completed", value="18"),
    StatItem(label="Overdue", value="3", trend="-2"),
])

# CardGenerator — THE single card component for all SKUEL UI contexts
from ui.patterns.card_generator import CardGenerator
from ui.feedback import StatusBadge, PriorityBadge

# Detail card from dataclass
CardGenerator.from_dataclass(
    entity,
    display_fields=["description", "model", "status"],
    show_labels=False,                              # list card style (no Label wrappers)
    header_badges=["status"],                       # badges beside title (string = introspect)
    title_href=f"/detail/{entity.uid}",             # linked title
    field_renderers={"model": render_model_badge},  # custom per-field
    actions=Div(Button("Edit"), Button("Delete"), cls="flex gap-2"),
)

# Activity domain list card (dict with pre-rendered badges)
CardGenerator.from_dataclass(
    {"title": goal.title, "description": goal.description or ""},
    display_fields=["description"],
    header_badges=[StatusBadge("in_progress"), PriorityBadge("high")],
    show_labels=False,
    metadata=["Due: Dec 15", "Project: Q4"],
    actions=Div(ButtonLink("View", href="/tasks/123", variant=ButtonT.ghost)),
)

# Teaching row card (subtitle + badges + extra)
CardGenerator.from_dataclass(
    {"title": "Essay Draft"},
    display_fields=[],
    subtitle="by Student Name",
    header_badges=[Badge("3 pending", variant=BadgeT.warning)],
    show_labels=False,
    actions=ButtonLink("View", href="/path", variant=ButtonT.primary, size=Size.sm),
    extra=feedback_toggle,
    card_attrs={"cls": "bg-background shadow-sm mb-2"},
)

# StatusBadge — delegates to EntityStatus.get_badge_class() for all 14 statuses
from ui.feedback import StatusBadge
StatusBadge("active")       # EntityStatus-driven green badge
StatusBadge("in_progress")  # EntityStatus-driven yellow badge

# Single stat with semantic color
StatCard(label="Completion Rate", value="85%", color="success")

# Progress bar with auto color thresholds
ProgressMetric("Data Quality", 0.88)  # green ≥80%, yellow ≥60%, red <60%
```

### EmptyState Usage Rules

- **Primary list views** (main entity list): `EmptyState(title="...", description="...", action_text="Create ...", action_href="/...")`
- **Secondary sections** (detail panel subsections, sidebar items): `EmptyState(title="...")` — no CTA
- **Tiny inline indicators** (sidebar `<li>`, analytics cards): Leave as `P()` — `EmptyState` with `py-12` is too heavy
- **Never hand-roll** `Div(P("No ..."))` for empty states — always use `EmptyState()`. Supports `**kwargs` pass-through for `id`, `cls` overrides, etc.

### StatsGrid Usage Rules

- **Never hand-roll** stat grids with raw `Div()` + grid + Tailwind — always use `StatsGrid()`/`StatItem()`.
- Use `StatItem` frozen dataclass (not dicts) for type-safe data passing: `label`, `value`, `change`, `trend`, `color`.
- `StatsGrid(stats, cols=4)` — responsive grid container. `StatCard()` for individual cards outside a grid.
- Adopted across ~16 files (insights, pathways, analytics, finance, admin, profile).

### SectionHeader Usage Rules

- **Never use raw `H2()`** for section headers outside cards — always use `SectionHeader()`.
- `SectionHeader(title)` — wraps in `Div(H2(...), cls="mb-6")`. Pass `action=` for a right-aligned link/button. Pass `cls=` for extra classes (e.g., `cls="mt-8"`).
- **Card-internal titles** (`H2` inside `Card()`) are a different semantic role — those stay as raw `H2()`.
- Adopted across ~7 files (groups, insights, exercises, analytics, admin, ingestion, curriculum adaptive).

### AlpineModal Usage Rules

- **Never hand-roll** modals with raw `Div()` + `fixed inset-0` + manual onclick handlers — always use `AlpineModal()`.
- Standardizes backdrop, click-outside-to-close, `x-cloak`, and transitions.
- For **HTMX-inserted modals** (server returns HTML fragment), use the auto-open pattern: `Div(AlpineModal(..., show="open", close="open = false; $nextTick(() => ...)"), x_data="{ open: true }", id="...")`.
- Adopted across ~5 files (calendar, sharing, insights).

### Typed Page Contexts

Route→UI contracts use per-domain TypedDicts from `ui/page_contexts.py`:

```python
from ui.page_contexts import TasksPageContext, GoalsPageContext  # etc.

# Build in route, pass to view
page_ctx: TasksPageContext = {
    "entities": tasks,
    "filters": filters.to_dict(),
    "projects": projects,
    "assignees": assignees,
}
view_content = TasksViewComponents.render_list_view(ctx=page_ctx)
```

Each domain has a standalone TypedDict with typed entities (`list[Task]`, `list[Goal]`, etc.) and `total=True` for required fields (`entities`, `filters`, `stats`). Optional fields use `NotRequired` (`projects`, `assignees`, `categories`, `view`). `ctx` is the only parameter to `render_list_view`.

### Composition Strategies

```python
# Strategy 1: Function composition (preferred)
def GoalCard(goal: Goal, show_actions: bool = True) -> Any:
    return Card(CardBody(
        H4(goal.title),
        Badge(goal.status.value, variant=BadgeT.success),
        CardActions(Button("Update", ...)) if show_actions else None,
    ))

# Strategy 2: Static class for grouped domain components
class TasksViewComponents:
    @staticmethod
    def render_list(tasks: list[Task]) -> Any:
        return Grid(*[TaskCard(t) for t in tasks], cls="grid-cols-1 gap-4")

# Strategy 3: Configuration-driven (use when N domains share one layout)
# Real example: DomainRouteConfig in adapters/inbound — six Activity Domain routes share config.
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
            PageHeader("Tasks", actions=Button("New Task", variant=ButtonT.primary)),
            content,
            cls=f"{Spacing.PAGE} {Container.STANDARD}",
        ),
        title="Tasks",
        request=request,
        active_page="tasks",
    )
```

### ActivityFilterBar (Config-Driven Filter Bar)

All 6 Activity Domain list views use a shared config-driven filter bar (`/ui/activities/filter_bar.py`). Each domain defines a `FilterBarConfig` with its filter dropdowns, sort options, and HTMX targets. Route files call `ActivityFilterBar(config, current_values)` directly.

**Implementation note:** Uses plain `<select class="uk-select">` instead of MonsterUI's `LabelSelect` (`<uk-select>` web component) for reliability — the custom element can fail to initialize. `LabelSelect` is still used in regular forms.

```python
from ui.activities.filter_bar import ActivityFilterBar, FilterBarConfig, FilterSelect

# Domain config defined in *_views.py (e.g. tasks_views.py)
TASK_FILTER_CONFIG = FilterBarConfig(
    fragment_url="/tasks/list-fragment",
    list_target_id="task-list",
    filters=[
        FilterSelect(name="status", label="Status",
                     options=[("Active", "active"), ("Completed", "completed"), ("All", "all")],
                     default="active"),
        FilterSelect(name="priority", label="Priority",
                     options=[("All", "all"), ("Critical", "critical"), ("High", "high")],
                     default="all"),
    ],
    sort_options=[("Priority", "priority"), ("Due Date", "due_date"), ("Title", "title")],
    sort_default="priority",
)

# Called in route files (e.g. tasks_ui.py)
ActivityFilterBar(TASK_FILTER_CONFIG, {"status": status_filter, "priority": priority_filter, "sort_by": sort_by})
```

**Config constants per domain:** `TASK_FILTER_CONFIG`, `GOAL_FILTER_CONFIG`, `HABIT_FILTER_CONFIG`, `EVENT_FILTER_CONFIG`, `CHOICE_FILTER_CONFIG`, `PRINCIPLE_FILTER_CONFIG`.

**Activity Domain routes pattern:** `GET /{domain}` (page), `GET /{domain}/list-fragment` (HTMX filtered list), `GET /{domain}/detail` (detail view). Routes are manual `@rt()` handlers in each `_ui.py` file.

See: `/docs/patterns/ROUTE_FACTORIES.md`

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
    NavItem("Profile Hub", "/profile", "profile"),
    NavItem("Search", "/search", "search"),
    NavItem("Calendar", "/calendar", "calendar"),
)
```

### Admin Navbar

Admin users see a different navbar than regular users:
- **Left:** SKUEL logo text link → `/` (admin home hub)
- **Center:** Empty (no text nav links)
- **Right:** Admin avatar (→ `/`) + Sign out (icon+text)
- **Mobile:** Hamburger menu with Admin (`/admin`) + Teaching (`/teaching`) + Sign out links

The admin home hub at `/` shows two `HubCard`s (Admin + Teaching). Regular users redirect to `/home` (post-login landing — three-tab interface: Submissions / GradeBook / Library, with HTMX-loaded domain blocks per tab; Settings footer). `/submissions`, `/gradebook`, `/library` render the same `HomeHub(active_tab=...)` with the matching tab pre-selected. Icon links are hidden for admins.

### Navbar Icon Links (Regular Users)

The navbar left section has 4 icon links (in order):

| Position | Icon | Route | `page_key` | Description |
|----------|------|-------|------------|-------------|
| 1st | `home` | `/home` | `"home"` | Hub (furthest left, auth only) |
| 2nd | `check-square` | `/profile` | `"profile"` | Tasks+ (auth only) |
| 3rd | `compass` | `/explore` | `"explore"` | Explore hub (public) |
| 4th | `book-open` | `/library` | `"library"` | Library hub (public) |

Right section: Search icon (`/search`) + notification bell + Sign out icon (`/logout`).

`/reports` redirects 301 → `/library`.

See `/ui/layouts/nav_config.py` for `ICON_NAV_ITEMS` and `IconNavItem`. All current icons use `has_dropdown=False` — direct links only. The Hub icon is separated from `icon_links` in `create_navbar()` so it renders furthest left.

Icon dropdowns are rendered via `_DROPDOWN_ITEMS_MAP` in `navbar.py`. Items without `has_dropdown` render as direct links via `_icon_nav_link()`. Emoji letters (multi-char) get `text-base` styling instead of `font-semibold text-sm`.

### Mobile Navigation

The navbar Alpine component (`navbar()` in `skuel.js`) handles the mobile hamburger menu. On mobile, activity domains (from avatar dropdown) and icon nav items are expanded into individual links. All current icon nav items are direct links (no dropdowns):

```python
# Mobile: activity domains first, then icon nav items, then Sign out
for di in ACTIVITY_DROPDOWN_ITEMS:
    mobile_icon_links.append(...)
for item in ICON_NAV_ITEMS:  # Hub, Tasks+, Explore, Library
    if item.has_dropdown:
        for di in _DROPDOWN_ITEMS_MAP.get(item.page_key, ()):
            mobile_icon_links.append(...)
    else:
        mobile_icon_links.append(...)  # All 4 current items take this path
if is_authenticated:
    mobile_icon_links.append(Sign out link)
```

**Navbar accessibility requirements:**

| Element | Required Attribute |
|---------|--------------------|
| `<nav>` | `aria-label="Main navigation"` |
| Icon buttons | `<span class="sr-only">Description</span>` |
| Dropdowns | `aria-haspopup="true"` on trigger |

---

## 4. Sidebar Pages

Use `SidebarPage()` for pages with collapsible, persistent sidebar navigation. Four sidebar groups exist:

- **Activity Domains** — `render_activity_sidebar_page()` from `ui/activities/nav.py` — 7 items (profile link + 6 domains). Used on `/tasks`, `/goals`, `/habits`, `/events`, `/choices`, `/principles`. Activity Domains content is embedded inline in `/profile`.
- **Explore** — `render_explore_sidebar_page()` from `ui/explore/nav.py` — graph-centered sidebar (wider `w-96`/384px via `sidebar_width` param, no nav items, uses `extra_sidebar_sections`). **Signature:** `render_explore_sidebar_page(content, sidebar_data: dict[str, Any] | None, request, ...)` — route handlers call `orchestrator.get_sidebar_data(user_uid)` first, then pass the pre-fetched dict. Hero: `ExploreGraphView` (`ui/explore/graph.py`) — interactive Vis.js force-directed graph. Hub mode (`/explore`): user's learning universe with "You" center node + studying Kus + in-progress PSes; fetched from `GET /api/explore/graph`. Entity mode (`/explore/ku/{uid}`, `/explore/ps/{uid}`): centers on current entity with lateral relationships. Filter tabs (All/Learning/Saved) control both graph node highlighting and list section visibility. Three supporting sections below graph: Learning, Saved, Completed. Alpine component: `exploreGraph(mode, entity_uid, entity_type)` in `skuel.js`. Graph expands to full-screen JS overlay on `document.body` (Escape/backdrop click to close) — creates a second Vis.js network to escape sidebar `overflow:hidden` + `transform`. Node colors: violet for Ku, teal for PS, blue for "You". Detail pages pass `current_entity_type` for graph centering. Unauthenticated: shows graph + "Sign in to track your learning". **PathStep detail** (`/explore/ps/{uid}`) is the **learning loop anchor** — authenticated users see three HTMX-loaded sections (Exercises with status pills, My Submissions, Feedback) served by `/learning-loop/ps/{ps_uid}/*` fragment endpoints; unauthenticated users see simple exercise links. **Supporting modules:** `ui/explore/cards.py` (card rendering + search panel), `ui/explore/filters.py` (client-side filter/sort helpers).
- **GradeBook** — `render_gradebook_sidebar_page()` from `ui/gradebook/nav.py` — 3 items (Exercise Reports, Activity Reports, Revisions). Used on child pages: `/exercise-reports`, `/activity-reports`, `/submit-activity-report`, `/activity-reports/detail`, `/revised-exercises`, `/revised-exercises/detail`. The hub at `/gradebook` renders `HomeHub(active_tab='gradebook')` — same tabbed interface as `/home`, GradeBook tab pre-selected. Block definitions in `ui/gradebook/hub.py` (`GRADEBOOK_BLOCKS`).
- **Library** — `render_library_sidebar_page()` from `ui/library/nav.py` — 4 items (Exercises, Resources, Ku, Path Steps). Used on child pages: `/library/exercises`, `/library/resources`, `/library/ku`, `/library/path-steps`. The hub at `/library` renders `HomeHub(active_tab='library')` — Library tab pre-selected. Block definitions in `ui/library/hub.py` (`LIBRARY_BLOCKS`).

`/profile` is a **personal overview hub** using `BasePage` directly — Focus/Velocity, Activity Domains (6 HTMX blocks inline via `ActivityHubView()`), Nous placeholder, Settings. See `ui/profile/hub.py`.

### SidebarItem

```python
from ui.patterns.sidebar import SidebarItem

SidebarItem(
    label="Submit",              # Display text
    href="/submit",              # Navigation URL
    slug="submit",               # For active state matching
    icon="📤",                   # Optional emoji
    description="",              # Optional subtitle (renders two-line item)
    badge_text="",               # Optional badge (e.g., count)
    badge_cls="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium bg-muted text-muted-foreground",
    hx_attrs={},                 # Optional HTMX attributes
)
```

### SidebarPage (Primary API)

```python
# Preferred: use the domain-specific helper (handles items, title, storage_key)
from ui.gradebook.nav import render_gradebook_sidebar_page

return await render_gradebook_sidebar_page(
    content=my_content, active="submissions", request=request
)

# Submissions sidebar (Upload, Submit, History):
from ui.workbench.nav import render_submissions_sidebar_page

return await render_submissions_sidebar_page(
    content=my_content, active="upload", request=request
)

# Or use SidebarPage directly for custom sidebars:
from ui.patterns.sidebar import SidebarItem, SidebarPage

items = [
    SidebarItem("Exercise Reports", "/exercise-reports", "exercise-reports", icon="clipboard-check"),
    SidebarItem("Activity Reports", "/activity-reports", "activity-reports", icon="bar-chart-2"),
    SidebarItem("Revisions", "/revised-exercises", "revised-exercises", icon="refresh-cw"),
]

return await SidebarPage(
    content=my_content,
    items=items,
    active="submissions",               # Active item slug
    title="GradeBook",                  # Sidebar heading
    storage_key="gradebook-sidebar",    # localStorage key for collapse state
    request=request,
    active_page="gradebook",            # Navbar active item
    # Optional:
    subtitle="",                        # Sidebar subtitle
    extra_sidebar_sections=[],          # Additional content below nav items
    extra_mobile_sections=[],           # Below mobile tabs
    item_renderer=None,                 # Custom render function
    title_href="",                      # Link on sidebar title
    title_icon="",                      # Lucide icon name replacing text title (e.g. "graduation-cap")
)
```

### Layout Behavior

**Desktop (lg: 1024px+):** Fixed left sidebar (256px) with collapse toggle → collapses to 48px edge.

**Mobile:** Hidden sidebar; horizontal `tabs tabs-bordered` replace it. No drawer, no hamburger overlay.

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

**Pattern 5 — Alpine section renderer (instant switching, no page navigation):**

Use when sidebar items should control Alpine `x-show` sections instead of navigating to different URLs. All content loads on initial render; switching is instant. Used by Teaching student submissions page (`/teaching/students/{uid}/submissions`).

```python
from ui.patterns.sidebar import alpine_section_renderer, alpine_mobile_section_renderer

items = [
    SidebarItem("Needs Review", href="", slug="pending", icon="📥", badge_text="3"),
    SidebarItem("Completed", href="", slug="completed", icon="✅"),
]

# Content panels use x-show keyed to the same state variable
content = Div(
    Div(pending_list, **{"x-show": "section === 'pending'"}),
    Div(completed_list, **{"x-show": "section === 'completed'"}),
)

return await SidebarPage(
    content=content, items=items, active="pending",
    title="Student Name", storage_key="student-detail-sidebar",
    request=request,
    item_renderer=alpine_section_renderer("section"),
    mobile_item_renderer=alpine_mobile_section_renderer("section"),
    alpine_state="{ section: 'pending' }",           # shared x-data on wrapper
    title_prefix=A(UkIcon("arrow-left"), href="/back"),  # back arrow in sidebar header
)
```

Key: `alpine_state` places `x-data` on the parent wrapper so both sidebar and content share the `section` variable. Alpine's hierarchical scoping means `collapsibleSidebar` on child elements doesn't conflict.

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

Use `FormGenerator` for all standard forms. It introspects Pydantic request models and generates MonsterUI-styled forms with correct types, constraints, labels, and Alpine.js validation.

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

### Manual Form Structure

For forms that need full custom control beyond FormGenerator's capabilities:

```python
from ui.buttons import Button, ButtonT
from ui.forms import LabelInput, LabelTextArea, LabelSelect

def create_task_form(action_url: str = "/tasks/quick-add") -> Any:
    return Form(
        LabelInput("Title *", type="text", name="title",
                   placeholder="What needs to be done?",
                   required=True, maxlength=200),
        LabelTextArea("Description", name="description", rows=4),
        LabelSelect(
            Option("Select...", value="", selected=True),
            Option("Critical", value="critical"),
            Option("High", value="high"),
            Option("Medium", value="medium"),
            Option("Low", value="low"),
            label="Priority",
            name="priority",
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
    title = safe_form_string(form_data.get("title"))
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

### Modal Forms — AlpineModal

Use `AlpineModal` from `ui/patterns/modal.py` for all Alpine.js-controlled modals. It standardizes backdrop, click-outside-to-close, transitions, and `x-cloak`.

```python
from ui.patterns.modal import AlpineModal
from ui.buttons import Button, ButtonT

@rt("/tasks/create-modal")
async def task_create_modal(request):
    """Return modal HTML for HTMX swap into #modal."""
    return AlpineModal(
        H3("Create Task", cls="font-bold text-lg"),
        create_task_form(action_url="/tasks/quick-add"),
        Button("Cancel", variant=ButtonT.ghost,
               **{"@click": "showModal = false"}),
        show="showModal",
        close="showModal = false",
        max_width="max-w-lg",
    )

# Trigger button
Button("New Task", variant=ButtonT.primary,
       **{"@click": "showModal = true"})
```

### Quick-Add Pattern (Minimal Fields)

```python
def render_quick_add_form() -> Any:
    """Single-field rapid entry form."""
    return Form(
        Div(
            Input(type="text", name="title", placeholder="Add a task...",
                  required=True, cls="flex-1"),
            Button("Add", variant=ButtonT.primary, type="submit"),
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
    LabelSelect(
        Option("One-time", value="once"), Option("Recurring", value="recurring"),
        label="Task Type",
        name="task_type",
        **{"x-model": "taskType"},
    ),
    Div(
        LabelSelect(
            Option("Daily"), Option("Weekly"), Option("Monthly"),
            label="Recurrence Pattern",
            name="recurrence_pattern",
        ),
        **{"x-show": "taskType === 'recurring'", "x-transition": ""},
    ),
    Button("Create", variant=ButtonT.primary, type="submit"),
    hx_post="/tasks/create",
    **{"x-data": "{ taskType: 'once' }"},
)
```

### Date/Time Inputs

```python
# Date with min constraint
Input(type="date", name="due_date", min=str(date.today()))

# Time with 15-minute increments
Input(type="time", name="start_time", value="09:00", step="900")

# Datetime-local
Input(type="datetime-local", name="event_start",
      value=datetime.now().strftime("%Y-%m-%dT%H:%M"))

# Two-column date row
Div(
    LabelInput("Start", type="date", name="start_date"),
    LabelInput("End", type="date", name="end_date"),
    cls="grid grid-cols-2 gap-4",
)
```

---

## 6. Inline CSS Reference (SKUEL Essentials)

Use MonsterUI semantic tokens, not Tailwind palette:

```python
# ✅ semantic tokens (respect active theme)
"text-base-content"         # Primary text
"text-base-content/70"      # Secondary text
"bg-base-100"               # Page background
"bg-base-200"               # Subtle surface (hover states, active items)
"border-base-200"           # Subtle borders

# ❌ Tailwind palette (breaks theming)
"text-gray-900"  "bg-white"  "text-gray-600"
```

**MonsterUI wrapper components for SKUEL:**

```python
from ui.buttons import Button, ButtonT, ButtonLink, IconButton
from ui.feedback import Alert, AlertT, Badge, BadgeT, Loading, LoadingT
from ui.forms import LabelInput, LabelTextArea, LabelSelect, LabelCheckbox, Input, Select, Textarea, Checkbox
from ui.patterns.modal import AlpineModal  # Standardized Alpine.js modal wrapper
from ui.layout import Size
from ui.data import Table, TableFromDicts, TableFromLists, TableT, Divider, DividerSplit, DividerT

# Buttons
Button("Primary", variant=ButtonT.primary)
Button("Ghost Small", variant=ButtonT.ghost, size=Size.sm)
Button("Delete", variant=ButtonT.outline_error)

# ButtonLink — use for ALL action CTAs (not raw A() with ad-hoc Tailwind)
# Raw A() is reserved for: entity title links, breadcrumbs, sidebar nav, inline text links
# Convention: primary CTA → ButtonT.primary + Size.sm
#             view/navigate → ButtonT.ghost + Size.sm
#             "view all" section links → ButtonT.ghost + Size.xs
ButtonLink("Submit →", href="/submit", variant=ButtonT.primary, size=Size.sm)
ButtonLink("View Report →", href="/reports/1", variant=ButtonT.ghost, size=Size.sm)
ButtonLink("View all →", href="/tasks", variant=ButtonT.ghost, size=Size.xs)

# StatusBadge — for any EntityStatus value (delegates to EntityStatus.get_badge_class())
from ui.feedback import StatusBadge, PriorityBadge
StatusBadge("active")       # canonical green
StatusBadge("submitted")    # canonical yellow
PriorityBadge("high")       # error variant

# Badge — for non-EntityStatus categories (type pills, counts, custom labels)
Badge("Active", variant=BadgeT.success)
Badge("Pending", variant=BadgeT.warning, size=Size.sm)
Badge("Ku", variant=BadgeT.accent, size=Size.sm)  # entity type pill
Badge("Path Step", variant=None, cls="bg-teal-100 text-teal-800 border-teal-200", size=Size.sm)

# Alerts / Error banners
Alert("Error message", variant=AlertT.error)
Alert("Task created!", variant=AlertT.success)

# Cards (using tokens)
Div(cls="bg-base-100 border border-base-200 rounded-lg p-6 hover:shadow-md transition-shadow")

# Loading
Loading(variant=LoadingT.spinner, size=Size.sm)
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
Button("Delete", variant=ButtonT.error, size=Size.sm, **{
    "hx-delete": f"/api/tasks/{uid}",
    "hx-confirm": "Delete this task?",
    "hx-target": "closest .task-card",
    "hx-swap": "outerHTML swap:300ms",
})
```

### Alpine in SKUEL Forms

```python
# Loading button state
Button("Save", variant=ButtonT.primary,
       **{"@click": "loading = true", ":disabled": "loading",
          "x-data": "{ loading: false }"},
       **{"@htmx:after-request": "loading = false"})

# Conditional field visibility
Div(
    LabelSelect(..., label="Pattern", name="recurrence"),
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

# ❌ Manual sidebar layout with CUSTOM
BasePage(content, page_type=PageType.CUSTOM, sidebar=Div(...))
# ✅ SidebarPage() for sidebar with collapsible + state persistence
await SidebarPage(content=content, items=items, ...)

# ❌ Magic container widths
Div(cls="max-w-6xl mx-auto p-4 sm:p-6 lg:p-8")
# ✅ Design tokens
Div(cls=f"{Container.STANDARD} {Spacing.PAGE}")

# ❌ Raw drawer HTML for sidebar (conflicts with BasePage padding)
Div(cls="drawer lg:drawer-open", ...)
# ✅ SidebarPage() (Tailwind + Alpine, no conflicts)

# ❌ Duplicate x-data for shared sidebar state
sidebar = Div(**{"x-data": "{ collapsed: false }"})
content = Div(**{"x-data": "{ collapsed: false }"})  # Different instance!
# ✅ SidebarPage() handles Alpine.store() automatically

# ❌ Hand-rolled badge with duplicated CSS classes
Span("Submitted", cls="bg-blue-100 text-blue-800 border border-blue-200 text-xs font-medium px-2 py-0.5 rounded-full")
# ✅ StatusBadge for EntityStatus values
StatusBadge("submitted")
# ✅ Badge for non-EntityStatus categories
Badge("Ku", variant=BadgeT.accent, size=Size.sm)

# ❌ Skipping early validation
result = TaskCreateRequest(**form_data)  # Generic 422 on error
# ✅ Early validation with clear messages
validation = validate_task_form_data(form_dict)
if validation.is_error: return render_error_banner(...)

# ❌ Separate Label + Input without wrapper (accessibility issue)
Label("Email"), Input(name="email")
# ✅ Use LabelInput (handles label, ARIA help_text/error_text)
LabelInput("Email", name="email", type="email")

# ❌ GET for mutations
Form(hx_get="/tasks/create")
# ✅ POST for all mutations
Form(hx_post="/tasks/create")

# ❌ Tailwind palette over semantic tokens
P("text", cls="text-gray-600")
# ✅ Semantic tokens
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
- [ ] `SidebarPage()` used (not raw drawer HTML)
- [ ] `storage_key` is unique per page
- [ ] Desktop collapse works; state persists on reload
- [ ] Mobile shows horizontal tabs (not drawer)

**Forms:**
- [ ] All inputs use `LabelInput`, `LabelTextArea`, `LabelSelect`, or `LabelCheckbox`
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
| `/ui/layouts/navbar.py` | Navbar — admin: SKUEL logo + avatar + Sign out; regular: 6 icon links (Hub, Tasks+, Explore, Library, Submissions, GradeBook) + avatar dropdown (Profile/6 Activity links/Sign out) |
| `/ui/layouts/nav_config.py` | `ICON_NAV_ITEMS`, `*_DROPDOWN_ITEMS`, `MAIN_NAV_ITEMS` |
| `/ui/patterns/sidebar.py` | `SidebarItem`, `SidebarNav`, `SidebarPage` |
| `/ui/curriculum/` | Curriculum sidebar, layout, landing page |
| `/ui/patterns/__init__.py` | `PageHeader`, `SectionHeader`, `EmptyState`, `CardGenerator`, `StatCard`, `StatsGrid`, `FormGenerator`, `ProgressMetric`, `SettingToggle` |
| `/ui/page_contexts.py` | Per-domain TypedDicts (`TasksPageContext`, `GoalsPageContext`, etc.) for route→UI contracts |
| `/ui/patterns/form_generator.py` | `FormGenerator` — dynamic form generation from Pydantic models |
| `/ui/tokens.py` | `Container`, `Spacing`, `Card` design tokens |
| `/core/utils/palette.py` | `SemanticColor`, `RelationshipColor`, `EventTypeColor`, `FrequencyColor`, `CalendarFallback` — centralized hex color constants (`ui/palette.py` re-exports) |
| `ui/buttons.py`, `ui/cards.py`, `ui/forms/`, `ui/feedback.py`, `ui/layout.py`, `ui/navigation.py`, `ui/data.py` | FastHTML MonsterUI wrappers — 7 focused modules (March 2026) |
| `/static/js/skuel.js` | All Alpine.data() components |
| `/ui/profile/hub.py` | `ProfileHubView` — personal overview: Focus/Velocity, Activity Domains (inline), Nous, Settings |
| `/ui/activities/nav.py` | Activity sidebar config (`ACTIVITY_SIDEBAR_ITEMS`) + `render_activity_sidebar_page()` helper |
| `/ui/gradebook/nav.py` | GradeBook sidebar config (`GRADEBOOK_SIDEBAR_ITEMS`) + `render_gradebook_sidebar_page()` helper |
| `/ui/workbench/hub.py` | `SUBMISSIONS_BLOCKS` — block definitions for Submissions tab in `HomeHub` |
| `/ui/workbench/nav.py` | Submissions sidebar config (`SUBMISSIONS_SIDEBAR_ITEMS`) + `render_submissions_sidebar_page()` helper |
| `/adapters/inbound/submissions_hub_routes.py` | Submissions hub page + HTMX preview endpoints + history |
| `/adapters/inbound/settings_routes.py` | Settings page (extracted from Workbench) — `/settings` + `/settings/save` |
| `/ui/library/nav.py` | Library sidebar config (`LIBRARY_SIDEBAR_ITEMS`) + `render_library_sidebar_page()` helper |
| `/ui/activities/activity_hub.py` | `ActivityHubView` — 6 Activity Domain preview blocks (embedded in `/profile`, HTMX lazy-loaded from `/api/profile/{slug}/preview`) |
| `/adapters/inbound/library_routes.py` | Library hub orchestrator — wires `library_ui.py` with its 6 service dependencies (extracted from `learning_loop_routes.py`) |
| `/adapters/inbound/library_ui.py` | `/library` sidebar pages + dual-purpose routes: `/library/exercises` (status-aware, uses `ExerciseStatusRow`), `/library/resources`, `/library/ku` (PINNED only, fetched via `backend.get_many()` by pinned UIDs), `/library/path-steps` (IN_PROGRESS only, fetched via `backend.get_many()` by enrolled UIDs). Exercise status helpers extracted to `ui/learning_loop/exercise_status.py` |
| `/adapters/inbound/explore_ui.py` | Explore hub + PS detail page + 2 PathStep learning loop HTMX fragments (`/learning-loop/ps/{ps_uid}/exercises`, `/learning-loop/ps/{ps_uid}/submissions-and-feedback`) wired in `create_explore_ui_routes` |
| `/adapters/inbound/submissions_routes.py` | Submissions hub orchestrator (`create_submissions_ui_orchestrator`) — wires submissions_ui, exercise_reports_ui, activity_reports_ui, revised_exercises_ui sub-factories |
| `/ui/learning_loop/` | Shared learning loop renderers: `exercise_status.py` (status pills, action links, exercise list), `submissions_section.py` (PS submissions), `feedback_section.py` (PS feedback) |
| `/core/services/resource_service.py` | `ResourceService` — `list_all()` for `Resource` entities (books, talks, films) |
| `/ui/activities/filter_bar.py` | Config-driven `ActivityFilterBar` component (`FilterBarConfig`, `FilterSelect`) — shared across all 6 Activity Domains |
| `/ui/activities/_shared.py` | Shared Activity Domain UI utilities (`MetadataField`, `safe_id`, `CONNECTION_ICONS`, `ConnectionBadges`, `ConnectionSummary`). Connection dicts use `connected_uid`/`connected_type` keys. |
| `/core/utils/connection_fetcher.py` | Unified `fetch_entity_connections()` — batch cross-domain connection query with per-domain `ConnectionConfig` constants |
| `/core/utils/entity_filters.py` | `filter_tasks/goals/habits/events/choices/principles()` — business filtering/sorting logic extracted from UI views |
| `/ui/profile/_shared.py` | Shared profile primitives (`DomainSummaryCard`, `DomainIntelligenceCard`, `DomainFilterControls`, `_item_list`) |
| `/ui/profile/curriculum_views.py` | KU, PS, LP profile views |
| `/ui/profile/overview.py` | `OverviewView` + all intelligence helper functions |
| `/docs/patterns/UI_COMPONENT_PATTERNS.md` | Complete patterns documentation |
| `/tests/unit/ui/test_cross_domain_consistency.py` | Cross-domain consistency tests — verifies PageHeader, EmptyState, StatsGrid, EntityRelationshipsSection used across all 6 activity domains + 4 hub pages |

## See Also

- `ui-css` — Deep reference for MonsterUI components and Tailwind utilities
- `ui-browser` — Deep reference for HTMX patterns and Alpine.js directives
- `fasthtml` — FastHTML route patterns and FT component system
- `chartjs` — Chart.js analytics visualization
- `vis-network` — Vis.js graph visualization
