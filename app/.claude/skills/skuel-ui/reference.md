# skuel-ui Reference: Components, Navigation, Sidebars, Forms, CSS & Interactivity

> On-demand reference for the [`skuel-ui`](SKILL.md) skill. SKILL.md holds the philosophy, page architecture (§1), anti-patterns (§8), testing checklist (§9), and Key Files (§10); this file holds the detailed building blocks — §2 Component Composition, §3 Navigation, §4 Sidebar Pages, §5 Form Patterns, §6 Inline CSS Reference, and §7 Inline Interactivity Reference.

---

## 2. Component Composition

### Three-Layer Model

```
Layouts  (/ui/layouts/, /ui/{domain}/layout.py)
    ↓ compose
Patterns (/ui/patterns/, /ui/{domain}/views.py)
    ↓ compose
Components (/ui/components/ — SKUEL-owned Tailwind layer; /ui/primitives.py, /ui/forms/, /ui/feedback.py, /ui/layout.py, … — pure Tailwind wrappers, ADR-071 complete)
```

Each layer has a single responsibility: components handle styling, patterns handle domain semantics, layouts handle page structure.

### Decision: Where Does a New Component Go?

```
Is it domain-agnostic styling (button, card, input)?
├─ YES → /ui/components/ first (Button, Alert, Icon, form set, Table, Divider, Accordion, TabContainer, Card family, layout helpers); /ui/primitives.py for ButtonLink, dropdown_menu, icon_tile, SelectableOptionRow, UploadDropzone; /ui/forms/ for form wrappers
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
            CardFooter(   # CardActions is deleted — CardFooter is the action area
                Button("Edit", cls=ButtonT.ghost, size="sm",
                       **{"hx-get": f"/tasks/{task.uid}/edit", "hx-target": "#modal"}),
                Button("Complete", cls=ButtonT.primary, size="sm",
                       **{"hx-post": f"/api/tasks/{task.uid}/complete"}),
                cls="justify-end gap-2",
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
from ui.patterns import PageHeader, SectionHeader, EmptyState, StatsGrid, StatCard, IconStat, StatTile
from ui.patterns.stats_grid import StatItem
from ui.patterns import SettingToggle
from ui.feedback import Progress, ProgressT

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
    actions=Div(ButtonLink("View", href="/tasks/123", cls=ButtonT.ghost)),
)

# Teaching row card (subtitle + badges + extra)
CardGenerator.from_dataclass(
    {"title": "Essay Draft"},
    display_fields=[],
    subtitle="by Student Name",
    header_badges=[Badge("3 pending", variant=BadgeT.warning)],
    show_labels=False,
    actions=ButtonLink("View", href="/path", cls=ButtonT.primary, size="sm"),
    extra=feedback_toggle,
    card_attrs={"cls": "bg-background shadow-sm mb-2"},
)

# StatusBadge — delegates to EntityStatus.get_badge_class() for all 14 statuses
from ui.feedback import StatusBadge
StatusBadge("active")       # EntityStatus-driven green badge
StatusBadge("in_progress")  # EntityStatus-driven yellow badge

# Single stat with semantic color (Card-wrapped label/value)
StatCard(label="Completion Rate", value="85%", color="success")

# Compact icon-led stat tile (centered, no Card — for dashboards/previews)
IconStat("Successful", 42, "✅", "text-success")

# Compact value-over-label stat tile (centered, no icon, no Card)
StatTile("Active", 42)

# Progress bar — pick the variant for the color you want
Progress(value=88, variant=ProgressT.success)  # success/warning/error/primary/...
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
        CardFooter(Button("Update", ...), cls="justify-end") if show_actions else None,
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
            PageHeader("Tasks", actions=Button("New Task", cls=ButtonT.primary)),
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

**Implementation note:** Uses SKUEL's `Select` from `ui.components`. Both `Select` and `LabelSelect` render a native `<select>` (pure Tailwind) so HTMX `FormData` serialization works — there is no web-component wrapper to hide the native element from form submission.

```python
from ui.activities.filter_bar import ActivityFilterBar, FILTER_CONFIGS

# All 6 domain configs centralised in FILTER_CONFIGS dict in filter_bar.py
# Access via FILTER_CONFIGS["tasks"], FILTER_CONFIGS["goals"], etc.
ActivityFilterBar(FILTER_CONFIGS["tasks"], {"status": status_filter, "priority": priority_filter, "sort_by": sort_by})
```

**Config dict:** `FILTER_CONFIGS: dict[str, FilterBarConfig]` in `ui/activities/filter_bar.py` — keys are domain slugs (`"tasks"`, `"goals"`, `"habits"`, `"events"`, `"choices"`, `"principles"`).

**Live category options:** `with_user_categories(config, categories)` (same file) rebuilds the Category dropdown from `service.search.list_user_categories(user_uid)` — Goals/Habits/Principles wire it via `ActivityUIConfig.list_categories`; the dropdown is dropped at 0-1 categories and falls back to the static config on fetch failure.

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

The admin home hub at `/` shows two `HubCard`s (Admin + Teaching). Regular users redirect to `/home`. Icon links are hidden for admins. `/submissions`, `/gradebook`, and `/library` are sidebar-free MOC root pages (2×2 icon-badge card grids), not tabbed hubs — `HomeHub` is retired.

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

The navbar handles the mobile hamburger menu with inline Alpine state (`x-data="{ mobileMenuOpen: false }"` in `ui/layouts/navbar.py` — simple enough that no `skuel.js` component is registered). On mobile, activity domains (from avatar dropdown) and icon nav items are expanded into individual links. All current icon nav items are direct links (no dropdowns):

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

- **Activity Domains** — `render_activity_sidebar_page()` from `ui/activities/nav.py` — 8 items (Today, Tasks, Events/Calendar, Goals, Habits, Principles, Choices, Journal). Used on `/tasks`, `/goals`, `/habits`, `/events/*` (calendar views), `/choices`, `/principles`, `/journals`. "Events" sidebar link → `/events/calendar` (redirects to current month); calendar month/week/day pages all render inside this sidebar. Activity Domains content is embedded inline in `/profile`.
- **Explore** — `render_explore_sidebar_page()` from `ui/explore/nav.py` — graph-centered sidebar (wider `w-96`/384px via `sidebar_width` param, no nav items, uses `extra_sidebar_sections`). **Signature:** `render_explore_sidebar_page(content, sidebar_data: dict[str, Any] | None, request, ...)` — route handlers call `orchestrator.get_sidebar_data(user_uid)` first, then pass the pre-fetched dict. Hero: `ExploreGraphView` (`ui/explore/graph.py`) — interactive Vis.js force-directed graph. Hub mode (`/explore`): user's learning universe with "You" center node + studying Kus + in-progress PSes; fetched from `GET /api/explore/graph`. Entity mode (`/explore/ku/{uid}`, `/explore/ps/{uid}`): centers on current entity with lateral relationships. Filter tabs (All/Learning/Saved) control both graph node highlighting and list section visibility. Three supporting sections below graph: Learning, Saved, Completed. Alpine component: `exploreGraph(mode, entity_uid, entity_type)` in `skuel.js`. Graph expands to full-screen JS overlay on `document.body` (Escape/backdrop click to close) — creates a second Vis.js network to escape sidebar `overflow:hidden` + `transform`. Node colors: violet for Ku, teal for PS, blue for "You". Detail pages pass `current_entity_type` for graph centering. Unauthenticated: shows graph + "Sign in to track your learning". **PathStep detail** (`/explore/ps/{uid}`) is the **learning loop anchor** — authenticated users see three HTMX-loaded sections (Exercises with status pills, My Submissions, Feedback) served by `/learning-loop/ps/{ps_uid}/*` fragment endpoints; unauthenticated users see simple exercise links. **Supporting modules:** `ui/explore/cards.py` (card rendering + search panel), `ui/explore/filters.py` (client-side filter/sort helpers).
- **Submissions** — `render_submissions_sidebar_page()` from `ui/workbench/nav.py` — 5 items: Exercise (`/submissions/exercise`), Journal (`/submissions/journal`), Sync (`/submissions/sync`), History (`/submissions/history`), Knowledge (`/submissions/knowledge` — knowledge notes with removable grounded-Ku chips). Root `/submissions` is a sidebar-free MOC page with 5 cards. `/submit` → 302 → `/submissions/exercise`; `/settings/vault` → 301 → `/submissions/sync`.
- **GradeBook** — `render_gradebook_sidebar_page()` from `ui/gradebook/nav.py` — 3 items (Entry Reports, Activity Reports, Revisions). Used on child pages: `/entry-reports`, `/activity-reports`, `/submit-activity-report`, `/activity-reports/detail`, `/revised-exercises`, `/revised-exercises/detail`. Root `/gradebook` is a sidebar-free MOC page with 3 cards; `title_href="/gradebook"`. Block definitions in `ui/gradebook/hub.py` (`GRADEBOOK_BLOCKS`) still serve HTMX preview endpoints.
- **Library** — `render_library_sidebar_page()` from `ui/library/nav.py` — 4 items (Exercises, Resources, Ku, Path Steps). Used on child pages: `/library/exercises`, `/library/resources`, `/library/ku`, `/library/path-steps`. Root `/library` is a sidebar-free MOC page with 4 cards; `title_href="/library"`. Block definitions in `ui/library/hub.py` (`LIBRARY_BLOCKS`) still serve HTMX preview endpoints.

`/profile` is a **4-tab personal hub** using `BasePage` directly — Curriculum / Activities / Submissions / Reports tabs mirroring the loop (study / live it / submit / grade); accordion blocks with HTMX lazy-loaded previews. See `ui/profile/hub.py`.

### SidebarItem

```python
from ui.patterns.sidebar import SidebarItem

SidebarItem(
    label="Submit",              # Display text
    href="/submit",              # Navigation URL
    slug="submit",               # For active state matching
    icon="📤",                   # Optional emoji
    description="",              # Optional subtitle (renders two-line item)
    badge_text="",               # Optional badge text (rendered via feedback.Badge, neutral)
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

# Submissions sidebar (Exercise, Journals, History, Obsidian Sync):
from ui.workbench.nav import render_submissions_sidebar_page

return await render_submissions_sidebar_page(
    content=my_content, active="upload", request=request
)

# Or use SidebarPage directly for custom sidebars:
from ui.patterns.sidebar import SidebarItem, SidebarPage

items = [
    SidebarItem("Entry Reports", "/entry-reports", "entry-reports", icon="clipboard-check"),
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
    content_max_width="max-w-6xl",      # Content column cap; "max-w-none" for fluid pages (calendar grids)
)
```

### Layout Behavior

**Desktop (lg: 1024px+):** Fixed left sidebar (256px) with collapse toggle → collapses to 48px edge. Content reflows into the freed space (collapse applies `lg:!ml-12` — the `!` is required because the static `lg:ml-64` can't be removed by Alpine's `:class` and wins on CSS order otherwise). Content is centered and capped at `content_max_width` (default `max-w-6xl`); pass `"max-w-none"` for pages that should fill the viewport — the calendar month/week grids do this.

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
extra_section = Div(
    H4("Section Title", cls="text-sm font-semibold opacity-60 px-3 mt-2"),
    Div(id="extra-list", **{"hx-get": "/your/fragment/route", "hx-trigger": "load"}),
)
return await SidebarPage(..., extra_sidebar_sections=[extra_section])
```

**Pattern 3 — Custom item renderer (badges, custom layout):**
```python
def _profile_item_renderer(item: SidebarItem, is_active: bool) -> Any:
    active_cls = "bg-base-200 font-semibold" if is_active else ""
    return Li(A(
        Span(item.icon, cls="text-lg"),
        Span(item.label, cls="flex-1"),
        Badge(item.badge_text, variant=BadgeT.neutral) if item.badge_text else "",
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
    title_prefix=A(Icon("arrow-left"), href="/back"),  # back arrow in sidebar header
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

Use `FormGenerator` for all standard forms. It introspects Pydantic request models and generates SKUEL-styled forms (pure Tailwind `ui.components`) with correct types, constraints, labels, and Alpine.js validation.

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
    UserEntryRequest,
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
from ui.components import Button, ButtonT, LabelInput, LabelTextArea, LabelSelect

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
        Button("Create Task", cls=(ButtonT.primary, "w-full mt-4"), type="submit"),
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
from ui.components import Button, ButtonT

@rt("/tasks/create-modal")
async def task_create_modal(request):
    """Return modal HTML for HTMX swap into #modal."""
    return AlpineModal(
        H3("Create Task", cls="font-bold text-lg"),
        create_task_form(action_url="/tasks/quick-add"),
        Button("Cancel", cls=ButtonT.ghost,
               **{"@click": "showModal = false"}),
        show="showModal",
        close="showModal = false",
        max_width="max-w-lg",
    )

# Trigger button
Button("New Task", cls=ButtonT.primary,
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
            Button("Add", cls=ButtonT.primary, type="submit"),
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
    Button("Create", cls=ButtonT.primary, type="submit"),
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

Use SKUEL semantic tokens, not the raw Tailwind palette:

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

**SKUEL component imports (pure Tailwind, ADR-071):**

```python
from ui.components import Button, ButtonT, Card, CardBody, CardHeader, CardTitle
from ui.primitives import ButtonLink, icon_tile, section_label, primary_btn, card_row
from ui.feedback import Alert, AlertT, Badge, BadgeT, Loading
from ui.forms import LabelInput, LabelTextArea, LabelSelect, LabelCheckbox, Input, Select, Textarea, Checkbox
from ui.patterns.modal import AlpineModal  # Standardized Alpine.js modal wrapper
from ui.components import Table, TableFromDicts, TableFromLists, TableT, Divider, DividerSplit, DividerT

# Buttons — cls= for style variant, size= for geometry (never mix size tokens in cls tuple)
Button("Primary", cls=ButtonT.primary)
Button("Ghost Small", cls=ButtonT.ghost, size="sm")
Button("Delete", cls=ButtonT.destructive, size="sm")

# ButtonLink — use for ALL action CTAs (not raw A() with ad-hoc Tailwind)
# Raw A() is reserved for: entity title links, breadcrumbs, sidebar nav, inline text links
# Convention: primary CTA → ButtonT.primary, size="sm"
#             view/navigate → ButtonT.ghost, size="sm"
#             "view all" section links → ButtonT.ghost, size="xs"
ButtonLink("Submit →", href="/submit", cls=ButtonT.primary, size="sm")
ButtonLink("View Report →", href="/reports/1", cls=ButtonT.ghost, size="sm")
ButtonLink("View all →", href="/tasks", cls=ButtonT.ghost, size="xs")

# SKUEL Primitives (ui/primitives.py) — unified design language building blocks

# Rounded semantic icon tile: md=34×34 (default), lg=42×42
icon_tile("check-circle", bg_cls="bg-blue-50", icon_cls="text-blue-600")
icon_tile("star", bg_cls="bg-amber-50", icon_cls="text-amber-600", size="lg")

# Uppercase section divider label (CONNECTS, DETAILS, etc.)
section_label("Connects")

# Dark bg-foreground action button with leading icon — form submits, primary CTAs
primary_btn("Submit", icon="send", type="submit")
primary_btn("Generate", icon="sparkles", cls="w-full")

# Flex row with gap-[13px] — standard icon-tile + text content layout
card_row(
    icon_tile("check", "bg-green-50", "text-green-600"),
    P("Task complete", cls="text-[14px] font-semibold"),
)

# Selectable option row: icon tile + title + subtitle + checkmark (active/hover state lives here)
# Used in dropdowns where one option is selected at a time (journal mode, submit dest, etc.)
SelectableOptionRow(
    icon="sparkles", tile_bg="bg-violet-50", icon_cls="text-violet-700",
    title="AI Feedback", subtitle="An AI reads and responds to your entry",
    selected_expr="dest === 'ai'", click_handler="selectDest('ai')",
)
# disabled=True → opacity-70, no checkmark; title_extra → badge alongside title
# subtitle_cls → override for monospace filenames (default: muted description text)

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

# Cards — new standard container (border-border, rounded-[12px], bg-card)
Div(cls="border border-border rounded-[12px] bg-card p-[22px] hover:shadow-sm transition-shadow")
# Or use Card from ui.components:
Card(CardBody(...))

# Loading (CSS-only spinner — no variant param)
Loading(size=Size.sm)
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
Button("Delete", cls=ButtonT.destructive, size="sm", **{
    "hx-delete": f"/api/tasks/{uid}",
    "hx-confirm": "Delete this task?",
    "hx-target": "closest .task-card",
    "hx-swap": "outerHTML swap:300ms",
})
```

### Alpine in SKUEL Forms

```python
# Loading button state
Button("Save", cls=ButtonT.primary,
       **{"@click": "loading = true", ":disabled": "loading",
          "x-data": "{ loading: false }"},
       **{"@htmx:after-request": "loading = false"})

# Conditional field visibility
Div(
    LabelSelect(..., label="Pattern", name="recurrence"),
    **{"x-show": "type === 'recurring'", "x-transition": ""},
)

# Reference centralized components (always prefer over inline x-data)
Div(content, **{"x-data": "toastManager()"})
Div(content, **{"x-data": "collapsible(false)"})
```
