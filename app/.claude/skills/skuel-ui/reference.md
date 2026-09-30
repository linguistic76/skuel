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
├─ YES → /ui/components/ first (Button, Alert, Icon, form set, Table, Divider, Accordion, Card family, layout helpers); /ui/primitives.py for ButtonLink, dropdown_menu, icon_tile, SelectableOptionRow, UploadDropzone; /ui/forms/ for form wrappers
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

**Canonical example:** `ui/teaching/forms.py` — holds `render_review_actions()` (the one action rule) over `render_feedback_submission_form()`, `render_revision_request_form()` and `render_waiting_actions()`, plus `render_submission_metadata()`. `ui/teaching/detail.py`'s `render_review_body()` composes them; the review routes build no form themselves.

**Adopted domains (Phase 1):** `ui/lifepath/` (vision form, alignment dashboard), `ui/askesis/` (welcome, chat, settings — dissolved `AskesisUI` class), `ui/activity_review/` (snapshot + feedback forms), `ui/analytics/` (dashboard, 7 domain metrics renderers — dissolved `AnalyticsUIComponents` class), `ui/ingestion/` (ingestion dashboard cards + JS), `ui/system/` (landing page, 404 page), `ui/exercises/` (editor, cards, detail), `ui/explore/` (cards, filters).

### Component API Design

```python
# ✅ GOOD: Accept domain object, boolean flags, cls extensibility
def TaskCard(
    task: Task,
    show_actions: bool = True,
    show_description: bool = True,
    cls: str = "",
) -> FT:
    card_id = f"task-{safe_id(task.uid)}"
    return Card(
        CardBody(
            H4(task.title, cls="font-semibold"),
            P(task.description, cls="text-sm text-muted-foreground") if show_description else None,
            CardFooter(   # CardFooter is the action area
                ButtonLink("Edit", href=f"/tasks/edit?uid={task.uid}", cls=ButtonT.ghost, size="sm"),
                # POST /api/tasks/{uid}/status answers the updated card, so the card swaps itself
                Button("Complete", cls=ButtonT.primary, size="sm",
                       hx_post=f"/api/tasks/{task.uid}/status", hx_vals='{"status": "completed"}',
                       hx_target=f"#{card_id}", hx_swap="outerHTML"),
                cls="justify-end gap-2",
            ) if show_actions else None,
        ),
        cls=("hover:shadow-md transition-shadow", cls),
        id=card_id,
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
from ui.patterns import PageHeader, SectionHeader, EmptyState, StatsGrid, StatCard, IconStat
from ui.patterns.stats_grid import StatItem
from ui.patterns import SettingToggle
from ui.feedback import Progress, ProgressT

# Empty state — primary list view with CTA
EmptyState(
    title="No tasks found",
    description="Create one to get started!",
    action_text="Create task",
    action_href="/tasks/create",
)

# Empty state — secondary section (no CTA)
EmptyState(title="No feedback yet")

# Empty state — with icon
EmptyState(title="No habits for today!", icon="🎉")

# Stats grid — uses StatItem frozen dataclass (not dicts)
# `change` is the text shown ("+5"); `trend` colors it: "up" | "down" | "neutral"
StatsGrid([
    StatItem(label="Total", value="42", change="+5", trend="up"),
    StatItem(label="Completed", value="18"),
    StatItem(label="Overdue", value="3", change="-2", trend="down"),
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

`ui/page_contexts.py` holds route→UI TypedDicts. The page shape is `TodayPageContext`: the
Today route builds it, and `TodayPage(ctx)` (`ui/today/page.py`) renders it. The other two,
`RelatedConceptChip` and `NextStepRelatedGroup`, are the rows of the Explore
related-concepts fragments. The Activity lists have no page context — they are rendered by
`activity_ui_factory.py` through `ActivityUIConfig.list_component`.

### Composition Strategies

```python
# Strategy 1: Function composition (preferred)
def GoalCard(goal: Goal, show_actions: bool = True) -> FT:
    return Card(CardBody(
        H4(goal.title),
        StatusBadge(goal.status.value),
        CardFooter(ButtonLink("Open", href=f"/goals/detail?uid={goal.uid}", cls=ButtonT.ghost, size="sm"),
                   cls="justify-end") if show_actions else None,
    ))

# Strategy 2: Configuration-driven (use when N domains share one layout)
# Live example: ActivityUIConfig (adapters/inbound/activity_ui_factory.py). Each of the six
# Activity *_ui.py files builds one config, and create_activity_ui_routes() generates the
# page shell, content fragment, list fragment, detail shell and detail content from it.
config = ActivityUIConfig(
    domain_name="tasks",
    ...,                                  # service callables, filter config, labels
    list_component=TaskList,              # (entities, connections_map) -> FT
    detail_component=TaskDetailView,      # (entity, connections) -> FT
    get_owned=tasks_service.verify_ownership,
)
create_activity_ui_routes(app, rt, config)
```

**When to use Strategy 2:** When three or more domain surfaces share the same layout but differ in data and components. Use a frozen dataclass (not a dict) so the config is type-safe and immutable. Grouping renderers as `@staticmethod`s on a class is the retired shape: the analytics and Askesis `*UI` classes were dissolved into module functions.

### Section Page Wrappers

A page in a sidebar section goes through that section's helper, which supplies the items,
title, storage key and the chrome's section key:

```python
from ui.activities.nav import render_activity_sidebar_page

return render_activity_sidebar_page(
    Div(PageHeader("New Task"), TaskCreateForm(), cls="space-y-6"),
    active="tasks",       # the Tasks+ row to light
    request=request,
)
```

The other section helpers: `render_submissions_sidebar_page` (`ui/workbench/nav.py`),
`render_library_sidebar_page` (`ui/library/nav.py`), `lifepath_sidebar_page`
(`ui/lifepath/nav.py`), `render_explore_sidebar_page` (`ui/explore/nav.py`).

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

**Activity Domain routes pattern:** `create_activity_ui_routes()` generates five routes per domain: `/{domain}` (shell), `/{domain}/content` (filter bar + list + stats), `/{domain}/list-fragment` (the filtered list, with `HX-Push-Url`), `/{domain}/detail` (detail shell) and `/{domain}/detail/content`. Each `{domain}_ui.py` adds its own create/edit routes beside them.

See: `/docs/patterns/ROUTE_FACTORIES.md`

---

## 3. Navigation

### Nav Configuration (`ui/layouts/nav_config.py`)

Two frozen dataclasses drive the global chrome — ONE navbar and ONE bottom nav for every role; there is no admin fork:

- `IconNavItem` (label, href, page_keys, icon, requires_auth) — `ICON_NAV_ITEMS` is the section-door spec, rendered as **desktop centre text links** (sm+) AND **phone bottom-nav icon tabs** (<sm) from the same list (`_visible_icon_items()` in `navbar.py`; the only gate is `requires_auth`, so every authenticated role sees the same four). `page_keys` is a SET of section keys the door lights for.
- `NavItem` (label, href, page_key, requires_admin, requires_teacher) — `MAIN_NAV_ITEMS` holds the role-gated doors (Teaching, Admin), rendered as **centre links at lg+** (`hidden lg:block` — at 640 the four section doors plus the icon cluster fill the bar, so Teaching + Admin do not fit in any font) AND **`lg:hidden` rows on `/settings`** (`role_nav_rows()`), filtered by the one predicate `NavItem.visible_to()`.

**The rule:** the global chrome carries exactly ONE door per SECTION, lit for the whole section by a section key (`active_page`); the section's own pages are the sidebar's rows, lit by slug. A door's href is the section's landing, which may be a sidebar row (Tasks+ → `/today`, its first row) or not (Library → `/explore/library`, Submissions → the `/submissions` MOC root, PathSteps → no sidebar). A door's href may appear in a sidebar ONLY as that sidebar's first row, and no other row is ever a door — the one sanctioned overlap (pinned by `tests/unit/ui/test_navbar.py`).

Current `ICON_NAV_ITEMS` (in order):

| Label | Icon | Route | `page_keys` | Notes |
|-------|------|-------|-------------|-------|
| Tasks+ | `activity` | `/today` | `{"activity"}` | Every page under the activity sidebar (`render_activity_sidebar_page`) passes `"activity"` — Today, the calendar views, the six domains, the periodic notes, the GradeBook |
| Library | `globe` | `/explore/library` | `{"explore", "library"}` | Public (`requires_auth=False`); two keys because its landing lights `explore` while `/library/*` lights `library` (D5 in the Tasks+ brief) |
| PathSteps | `map` | `/path-steps` | `{"path-steps"}` | Public (`requires_auth=False`) |
| Submissions | `upload` | `/submissions` | `{"submissions"}` | The submissions MOC; every sub-page passes the same `active_page`, so the link stays lit across the section |

### The Navbar (every role)

- **Left:** SKUEL brand text link → `/explore` (authed) or `/` (anon)
- **Centre (sm+):** text links from `ICON_NAV_ITEMS`; at lg+ `MAIN_NAV_ITEMS` joins them (Teaching for teachers and admins, Admin for admins); the lit link carries `aria-current="page"`
- **Right (icon buttons):** Askesis flame (`/askesis`) → Shared-inbox (`/profile/shared`) → notification bell (HTMX lazy-loaded badge from `/api/navbar/notification-badge`) → avatar (`/settings`, `page_key="settings"`) → Sign out (`/logout`, desktop only — the phone reaches it from `signout_row()` on `/settings`, so exactly one door exists at every width)
- **Phone (<sm):** the slim top bar (brand + the four right icons) + the fixed bottom nav via `create_bottom_nav()` — the `ICON_NAV_ITEMS` tabs (four for every authenticated role; the two `requires_auth=False` doors for an anonymous visitor), `sm:hidden`, `min-h-16` + `safe-area-inset-bottom`. Sign out (`sm:hidden`) and Admin/Teaching (`lg:hidden`) are rows on `/settings` (`ui/settings/page.py`), rendered first and outside any HTMX fragment or `x-cloak` — each row is hidden exactly where its top-bar counterpart appears.
- **Landing:** `/` → 303 `/today` for every authenticated role (ADR-058, amended); the login/register/reset redirects go there too. There is no admin hub.

Every navbar item is a direct link — the navbar carries no dropdown and no hamburger. The periodic notes are reached from the Tasks+ sidebar's Journal row (today's note) and, inside a periodic note, the **period rail** (`ui/journals/chat_page.py`): one row per period kind, each opening that period's note and stepping to its neighbours; every door derives its URLs, labels and icons from `ui/journals/period_links.py`.

`/submissions` and `/library` are sidebar-free MOC root pages (icon-badge `MocCard` grids — five and four cards); `/gradebook` is a Tasks+ page (the received-feedback exchange lines, GradeBook row lit). There is no `/profile` hub, no `/home`, and no admin home: `GET /profile` is a 404 and `/` is a 303 to `/today`. A hub page earns its place only when it carries what the section nav cannot — `/docs/design-principles/HUB_PAGES.md`.

**Navbar accessibility requirements:**

| Element | Required Attribute |
|---------|--------------------|
| `<nav>` | `aria-label="Main navigation"` (top) / `aria-label="Primary navigation"` (bottom) |
| Icon buttons | `<span class="sr-only">Description</span>` |
| Active links | `aria-current="page"` |

---

## 4. Sidebar Pages

Use `SidebarPage()` for pages with collapsible, persistent sidebar navigation. The sidebar groups:

- **Tasks+** — `render_activity_sidebar_page()` from `ui/activities/nav.py` — `ACTIVITY_SIDEBAR_ITEMS` (Today, Weekly, Monthly, Tasks, Goals, Habits, Events, Principles, Choices, Journal, GradeBook) on `/tasks`, `/goals`, `/habits`, `/events`, `/choices`, `/principles`, the calendar month/week pages, `/today`, the periodic notes (`/journals/{uid}`; `content_max_width="max-w-none"` on the calendar and the notes) and the GradeBook surfaces (`/gradebook`, `/gradebook/{uid}`, the report/revision detail pages, `/submit-activity-report` — `active="gradebook"`; `title` names the tab) — one list, and every one of those pages lights the Tasks+ door in the chrome (`active_page="activity"`, passed by the helper — callers never set it). This is the ONE sidebar that opts into the badge loader (`SidebarPage(badges=True)`): `GET /api/sidebar/badges` fires once the desktop sidebar is on screen (`hx-trigger="intersect once"` — never below `lg`, where the sidebar is `display:none`) and OOB-swaps exactly `ACTIVITY_SIDEBAR_ITEMS ∩ DOMAIN_STATS_CONFIG` (the six domain rows); every other sidebar renders no slots and makes no request. Each calendar view shows its declared membership (`VIEW_SPECS`: month = events; week = events, habits, goal milestones and high-priority tasks, with the kind legend as filter).
- **Explore** — `render_explore_sidebar_page()` from `ui/explore/nav.py` — graph-centered sidebar (`w-96`/384px via `sidebar_width`, no nav items, uses `extra_sidebar_sections`). **Its one caller is `/explore/library`** (the catalog). `/explore` itself is the reading column (`ui/explore/reading_plan.py`), and the Ku/PS reading pages (`/explore/ku/{uid}`, `/explore/ps/{uid}`) are `BasePage(CUSTOM)` with no sidebar. **Signature:** `render_explore_sidebar_page(content, sidebar_data, request, page_title="Explore", current_uid="", current_entity_type="")` (`sidebar_data` is `None` for an anonymous visitor) — the route calls `orchestrator.get_sidebar_data(user_uid)` first, then passes the pre-fetched dict. Hero: `ExploreGraphView` (`ui/explore/graph.py`), a Vis.js force-directed graph in hub mode (the "You" node + studying Kus + in-progress PSes, from `GET /api/explore/graph`). Entity mode exists (`current_uid` + `current_entity_type`) but the one caller never passes them. Below the graph: Learning, Saved and Completed lists. Alpine component: `exploreGraph(mode, entity_uid, entity_type)` in `skuel.js`. Unauthenticated: graph + "Sign in to track your learning". The graph also has its own full page, `/explore/graph`. **PathStep detail** (`/explore/ps/{uid}`) is the **learning loop anchor**: for a signed-in user it HTMX-loads two sections, Exercises (`/learning-loop/ps/{ps_uid}/exercises`, with status pills) and Submissions & Feedback (`/learning-loop/ps/{ps_uid}/submissions-and-feedback`). **Supporting module:** `ui/explore/cards.py` (card rendering + search panel); catalog filtering and sorting are server-side via `SearchRouter.faceted_search` (`adapters/inbound/explore_ui.py`).
- **Submissions** — `render_submissions_sidebar_page()` from `ui/workbench/nav.py` — 5 items: Sync (`/submissions/sync`), Submit (`/submissions/submit`), Journal (`/submissions/journal`), History (`/submissions/history`), Knowledge (`/submissions/knowledge` — knowledge notes with removable grounded-Ku chips). Root `/submissions` is a sidebar-free MOC page with 5 cards.
- **GradeBook** — no sidebar of its own. `/gradebook` is THE received-feedback page (3→1 collapse, arc 2 C1): per-exercise exchange lines with status/source filter chips (`ui/gradebook/summary.py`, HTMX fragment `/gradebook/lines`) + conditional Activity-reports and Other-feedback groups; it and its detail pages (`/entry-reports/detail`, `/activity-reports/detail`, `/revised-exercises/detail`, `/gradebook/{uid}`) render under the Activity sidebar via `render_activity_sidebar_page(..., active="gradebook", title=GRADEBOOK_TITLE)` (error-only pages via `render_activity_sidebar_error`). The header's "Request activity report" action opens `/submit-activity-report`.
- **Library** — `render_library_sidebar_page()` from `ui/library/nav.py` — 4 items (Exercises, Resources, Ku, Path Steps). Used on child pages: `/library/exercises`, `/library/resources`, `/library/ku`, `/library/path-steps`. Root `/library` is a sidebar-free MOC page with 4 cards; `title_href="/library"`.
- **Teaching** — `ui/teaching/nav.py` — Students (`/teaching/students`, the section landing — there is no `/teaching` hub), Groups, Review Queue, Forms. **Admin** — `ui/admin/layout.py` (`ADMIN_SIDEBAR_ITEMS`).

### SidebarItem

```python
from ui.patterns.sidebar import SidebarItem

SidebarItem(
    label="Submit",              # Display text
    href="/submissions/submit",  # Navigation URL
    slug="submit",               # For active state matching
    icon="send",                 # Lucide name from ui/components/_icon_data.py (an emoji renders help-circle)
    description="",              # Optional subtitle (renders two-line item)
    badge_text="",               # Optional badge text (rendered via feedback.Badge, neutral)
    hx_attrs={},                 # Optional HTMX attributes
)
```

### SidebarPage (Primary API)

```python
# Preferred: use the domain-specific helper (handles items, title, storage_key)
from ui.activities.nav import render_activity_sidebar_page

return render_activity_sidebar_page(
    content=my_content, active="gradebook", request=request, title="GradeBook"
)

# Submissions sidebar (Sync, Submit, Journal, History, Knowledge):
from ui.workbench.nav import render_submissions_sidebar_page

return render_submissions_sidebar_page(
    content=my_content, active="submit", request=request
)

# Or use SidebarPage directly for custom sidebars:
from ui.patterns.sidebar import SidebarItem, SidebarPage

items = [
    SidebarItem("Exercises", "/library/exercises", "exercises", icon="book-open"),
    SidebarItem("Resources", "/library/resources", "resources", icon="bookmark"),
]

return SidebarPage(
    content=my_content,
    items=items,
    active="exercises",                 # Active item slug
    title="Library",                    # Sidebar heading
    storage_key="library-sidebar",      # localStorage key for collapse state
    request=request,
    active_page="library",              # Navbar active item
    # Optional:
    subtitle="",                        # Sidebar subtitle
    extra_sidebar_sections=[],          # Additional content below nav items
    extra_mobile_sections=[],           # Below the section nav
    item_renderer=None,                 # Custom render function
    title_href="",                      # Link on sidebar title
    title_icon="",                      # Lucide icon name replacing text title (e.g. "graduation-cap")
    content_max_width="max-w-6xl",      # Content column cap; "max-w-none" for fluid pages (calendar grids)
)
```

### Layout Behavior

**Desktop (lg: 1024px+):** Fixed left sidebar (256px) with collapse toggle → collapses to 48px edge. Content reflows into the freed space (collapse applies `lg:!ml-12` — the `!` is required because the static `lg:ml-64` can't be removed by Alpine's `:class` and wins on CSS order otherwise). Content is centered and capped at `content_max_width` (default `max-w-6xl`); pass `"max-w-none"` for pages that should fill the viewport — the calendar month/week grids do this.

**Below lg:** Hidden sidebar; the **section nav** replaces it — `<nav aria-label="{title}"><ul role="list">` of `shrink-0` `<li><a>` page links in a horizontally scrolling row, the current page marked `aria-current="page"` server-side (never `role="tab"`/`aria-selected`: the links navigate between pages). A parse-time inline script after the row centres the current link (`scrollLeft`, never `scrollIntoView`) and stamps `data-overflow`/`data-at-end` on the `<nav>`; `.section-nav` in `input.css` draws a right-edge fade from those attributes beside the native scrollbar. No items → no row (Explore). The row stays rather than a drawer or hamburger because every sibling stays visible and it works without JS.

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
return SidebarPage(content=content, items=ITEMS, active="overview", title="Reports",
                         storage_key="reports-sidebar", request=request)
```

**Pattern 2 — Extra sections (HTMX-loaded content):**
```python
extra_section = Div(
    H4("Section Title", cls="text-sm font-semibold opacity-60 px-3 mt-2"),
    Div(id="extra-list", **{"hx-get": "/your/fragment/route", "hx-trigger": "load"}),
)
return SidebarPage(..., extra_sidebar_sections=[extra_section])
```

**Pattern 3 — Custom item renderer (custom layout):**
```python
def _item_renderer(item: SidebarItem, is_active: bool) -> FT:
    active_cls = "bg-accent font-semibold" if is_active else ""
    return Li(A(
        Icon(item.icon, size=18, cls="shrink-0") if item.icon else "",
        Span(item.label, cls="flex-1"),
        Badge(item.badge_text, variant=BadgeT.neutral) if item.badge_text else "",
        href=item.href,
        cls=f"flex items-center gap-2 rounded-lg px-3 py-2.5 min-h-[44px] hover:bg-accent {active_cls}",
        **({"aria_current": "page"} if is_active else {}),
    ))

return SidebarPage(..., item_renderer=_item_renderer)
```
A renderer that navigates between pages keeps `aria-current="page"` on the current link — the default renderer's contract, and what the chrome gate measures.

**Pattern 4 — Description items (two-line layout, no custom renderer needed):**
```python
SidebarItem("Overview", "/askesis", "overview", icon="house", description="Your life context dashboard")
```
`icon` is a lucide name from `ui/components/_icon_data.py`; an unregistered name (an emoji, a typo) renders the `help-circle` fallback.

**Pattern 5 — Alpine section renderer (instant switching, no page navigation):**

Use when sidebar items should control Alpine `x-show` sections instead of navigating to different URLs. All content loads on initial render; switching is instant. Used by the Teaching student submissions page (`/teaching/students/{uid}/submissions`). Because these rows switch sections on the SAME page they render `role="tab"` inside a `<div role="tablist">` — the default below-`lg` row is a `<nav>` list of page links marked `aria-current`, and the two must not be mixed (a nav list owning `role="tab"` children is an invalid tabs hierarchy).

```python
from ui.patterns.sidebar import alpine_section_renderer, alpine_mobile_section_renderer

items = [
    SidebarItem("Needs Review", href="", slug="pending", icon="inbox", badge_text="3"),
    SidebarItem("Completed", href="", slug="completed", icon="check-circle"),
]

# Content panels use x-show keyed to the same state variable
content = Div(
    Div(pending_list, **{"x-show": "section === 'pending'"}),
    Div(completed_list, **{"x-show": "section === 'completed'"}),
)

return SidebarPage(
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
// static/js/skuel.js (abridged): collapsibleSidebar reads from Alpine.store(storageKey)
// Both sidebar and content reference the same store key → they stay in sync
Alpine.data('collapsibleSidebar', function(storageKey, defaultCollapsed) {
    return {
        get collapsed() { var store = Alpine.store(storageKey); return store ? store.collapsed : false; },
        init: function() {
            // First instance registers the store; localStorage is read only at >= 1024px
            if (!Alpine.store(storageKey)) { /* ... */ Alpine.store(storageKey, { collapsed: initial }); }
        },
        toggle: function() {
            var store = Alpine.store(storageKey);
            store.collapsed = !store.collapsed;
            localStorage.setItem(storageKey + '-collapsed', store.collapsed.toString());
            window.SKUEL.announce('Sidebar ' + (store.collapsed ? 'collapsed' : 'expanded'));
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

### Two-Tier Validation

| Tier | Technology | Error Type | When |
|------|------------|-----------|------|
| **Client hints** | HTML5 `required`, `maxlength`, `min`/`max` | Browser native | Always (FormGenerator adds these from Pydantic constraints) |
| **Schema validation** | Pydantic request model via `parse_form_body` | `Result[T]` failure → banner (400 on an API route) | Every form; cross-field rules are `@model_validator`s on the model |

There is no hand-written validator between the two: a `validate_*_form_data()` function
duplicates the model's constraints, and the two drift.

### Manual Form Structure

For forms that need full custom control beyond FormGenerator's capabilities:

```python
from fasthtml.common import FT, Form, Option

from ui.components import Button, ButtonT, LabelInput, LabelSelect, LabelTextArea

def create_task_form() -> FT:
    return Form(
        LabelInput("Title *", type="text", name="title",
                   placeholder="What needs to be done?",
                   required=True, maxlength=200),
        LabelTextArea("Description", name="description", rows=4),
        LabelSelect(
            Option("Select...", value="", selected=True),
            Option("High", value="high"),
            Option("Medium", value="medium"),
            Option("Low", value="low"),
            label="Priority",
            name="priority",
        ),
        Button("Create Task", cls=(ButtonT.primary, "w-full mt-4"), type="submit"),
        method="post",
        action="/tasks/create",   # answers a 303 to the new task, or the page with a banner
        cls="space-y-4",
    )
```

`Priority` has three levels (`high`, `medium`, `low`). A plain `method="post"` form gets its
CSRF token from `skuel.js`, which adds the hidden `csrf_token` input on submit.

### Handling the Submit (the live pattern)

From `adapters/inbound/tasks_ui.py`: the model validates, and the route renders the model's
message.

```python
@rt("/tasks/create", methods=["POST"])
@csrf_protected
async def task_create_submit(request: Request) -> FT | RedirectResponse:
    user_uid = require_authenticated_user(request)

    parsed = await parse_form_body(request, TaskCreateRequest)
    if parsed.is_error:
        content = Div(
            PageHeader("New Task"),
            render_error_banner(parsed.expect_error().display_message),
            TaskCreateForm(),
            cls="space-y-6",
        )
        return render_activity_sidebar_page(content, active="tasks", request=request)

    result = await tasks_service.core.create_task(parsed.value, user_uid)
    if result.is_error:
        ...  # same page, the service's message in the banner
    return RedirectResponse(f"/tasks/detail?uid={result.value.uid}", status_code=303)
```

### Modal Forms — AlpineModal

Use `AlpineModal` from `ui/patterns/modal.py` for all Alpine.js-controlled modals. It standardizes backdrop, click-outside-to-close, transitions, and `x-cloak`.

A modal the page already holds is driven by a flag in an enclosing `x-data`:

```python
from ui.components import Button, ButtonT
from ui.patterns.modal import AlpineModal

Div(
    Button("Share", cls=ButtonT.primary, **{"@click": "showShare = true"}),
    AlpineModal(
        H3("Share", cls="font-bold text-lg"),
        share_form,
        Button("Cancel", cls=ButtonT.ghost, **{"@click": "showShare = false"}),
        show="showShare",
        close="showShare = false",
        max_width="max-w-lg",
    ),
    x_data="{ showShare: false }",
)
```

A modal the **server returns** (swapped into `#modal`) carries its own state and opens on
arrival. Its flag lives in the fragment, because nothing outside it can hold one:

```python
Div(
    AlpineModal(*content, show="open",
                close="open = false; $nextTick(() => document.getElementById('my-modal')?.remove())",
                max_width="max-w-2xl", scrollable=True),
    x_data="{ open: true }",
    id="my-modal",
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
    method="post",
    action=create_url,
    **{"x-data": "{ taskType: 'once' }"},
)
```

### Date/Time Inputs

```python
# "Today" and the wall clock are the user's zone's (core.utils.zone_context), never the host's
from core.utils.timestamp_helpers import today_in, wall_clock_in
from core.utils.zone_context import current_zone

# Date with min constraint
Input(type="date", name="due_date", min=today_in(current_zone()).isoformat())

# Time with 15-minute increments
Input(type="time", name="start_time", value="09:00", step="900")

# Datetime-local
Input(type="datetime-local", name="event_start",
      value=wall_clock_in(current_zone()).strftime("%Y-%m-%dT%H:%M"))

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
# ✅ theme-aware semantic tokens (switch under .dark)
"text-foreground"           # Primary text
"text-muted-foreground"     # Secondary text
"bg-background"             # Page / card surface
"bg-muted"                  # Subtle surface (hover states, active items)
"border-border"             # Borders, dividers
# text-error / bg-success / bg-base-200 / text-base-content also compile, as fixed hex that
# stays the same in dark mode (ADR-071 compat); there is no bg-base-100 — see ui-css

# ❌ Tailwind palette (breaks theming)
"text-gray-900"  "bg-white"  "text-gray-600"
```

**SKUEL component imports (pure Tailwind, ADR-071):**

```python
from ui.components import Button, ButtonT, Card, CardBody, CardHeader, CardTitle
from ui.primitives import ButtonLink, SelectableOptionRow, icon_tile, section_label, primary_btn, card_row
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
ButtonLink("Submit →", href="/submissions/submit", cls=ButtonT.primary, size="sm")
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
    P("Task complete", cls="text-sm font-semibold"),
)

# Selectable option row: icon tile + title + subtitle + checkmark (active/hover state lives here)
# Used in dropdowns and option lists where one option is selected at a time (journal
# mode, the Submit page's "Ask for feedback?", etc.)
SelectableOptionRow(
    icon="sparkles", tile_bg="bg-violet-50", icon_cls="text-violet-700",
    title="AI", subtitle="Graded against the exercise.",
    selected_expr="feedback === 'ai'", click_handler="selectFeedback('ai')",
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
# Submit via HTMX, append the returned row, reset only on success
Form(
    ...,
    hx_post=add_url,              # a route that answers the new row's HTML
    hx_target="#task-list",
    hx_swap="beforeend",
    **{"hx-on::after-request": "if (event.detail.successful) this.reset()"},
)

# Load content on page load
Div(id="stats", **{"hx-get": "/api/stats", "hx-trigger": "load"})

# Search with debounce
Input(name="q", **{
    "hx-get": "/search",
    "hx-trigger": "input changed delay:300ms",
    "hx-target": "#results",
})

# Delete with confirmation — the CRUD delete door is POST /api/{domain}/delete?uid=
# and answers JSON, so swap "delete" (remove the card) rather than swapping the body in
Button("Delete", cls=ButtonT.destructive, size="sm",
       hx_post=f"/api/exercises/delete?uid={exercise.uid}",
       hx_confirm="Are you sure you want to delete this exercise?",
       hx_target=f"#{exercise_card_id(exercise.uid)}",
       hx_swap="delete")
```

### Alpine in SKUEL Forms

```python
# Loading state — on the FORM, because htmx fires htmx:afterRequest on the element that
# issued the request (the form) and it bubbles UP, never down to the button. A button that
# listens for it itself stays disabled forever (measured, htmx 1.9.10 + Alpine 3.14.8).
Form(
    ...,
    Button("Save", cls=ButtonT.primary, type="submit", **{":disabled": "loading"}),
    hx_post=save_url,
    **{"x-data": "{ loading: false }", "@submit": "loading = true",
       "@htmx:after-request": "loading = false"},
)

# Conditional field visibility
Div(
    LabelSelect(..., label="Pattern", name="recurrence"),
    **{"x-show": "type === 'recurring'", "x-transition": ""},
)

# Reference centralized components (always prefer over inline x-data)
Div(content, **{"x-data": "toastManager()"})
Div(content, **{"x-data": "collapsible(false)"})
```
