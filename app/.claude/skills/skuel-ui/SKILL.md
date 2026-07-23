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

## Component Layer Migration (ADR-071)

`ui/components/` is SKUEL's owned component layer — thin FT functions encoding Tailwind class strings, no UIkit.

**Why:** FrankenUI shipped UIkit JS that directly conflicted with Alpine.js (two competing DOM state machines). ADR-071 replaced MonsterUI with SKUEL-owned components so the interactivity model is coherent: Alpine.js + HTMX, nothing else.

**Current state (ADR-071 complete — M1–M11 all done):** Import everything from `ui.components`:
- `Button`, `ButtonT` — style via `cls=ButtonT.primary`, geometry via `size="sm"` kwarg
- `Alert`, `AlertT`, `Loading`, `Progress`
- `Icon` (Lucide, server-rendered inline SVG — no lucide runtime), full form set, table set, `Divider`, `TabContainer`, `Accordion`, layout helpers
- Card family (`Card`, `CardBody`, `CardHeader`, `CardTitle`, `CardFooter`)

`build_head()` / `skuel_headers()` load `output.css` (pre-compiled Tailwind CLI) + Lucide + HTMX + Alpine. UIkit/FrankenUI/MonsterUI/DaisyUI are gone — no `monsterui`/`daisyui` dependency, no vendor files, no browser JIT.

> ⚠️ **Two enum conventions — don't conflate them.** `ui.components.Button`/`ButtonT` take
> style via **`cls=`** and `ButtonT` is **slim** (`default`/`primary`/`secondary`/`ghost`/
> `destructive`/`link` — map `error`→`destructive`, no `success`/`warning`/`accent`). The
> `ui.feedback` components (`Badge`/`Alert`/`Progress`/`RadialProgress`) keep **`variant=`**
> with the **full** color enum (`BadgeT`/`AlertT`/`ProgressT` expose `success`/`warning`/
> `error`/`accent`/…). So: `Button(cls=ButtonT.destructive)` but `Badge(variant=BadgeT.error)`.

---

## Design Direction (Aesthetic Intent)

> "Commit to a direction before coding. Intent through tokens — never ad-hoc hex or fonts."

The component stack is: FastHTML + Tailwind CLI + `ui/components/` + Alpine.js + HTMX (ADR-071 complete — MonsterUI/FrankenUI/DaisyUI removed). Express aesthetic intent *through existing components and tokens*, never by fighting the stack with raw HTML, CDN fonts, or bespoke CSS.

**Pre-coding pass — commit to four dimensions before writing FT:**
1. **Purpose** — what problem, who uses it (mirror the route's `*PageContext`).
2. **Constraints** — stack is fixed: `BasePage`/`AuthPage` → `build_head()`, server-rendered, accessible (see `accessibility-guide`).
3. **Differentiation** — the one thing a user remembers; earned by deliberate hierarchy/density, not novelty CSS.
4. **Tone** — pick a committed direction (refined-minimal ↔ dense-utilitarian) and hold it across the page.

**Express intent through the stack:**
- **Typography = hierarchy via components.** `PageHeader`/`SectionHeader` carry the type scale — never raw `H1()`/`H2()` with ad-hoc classes. Wholesale font swaps are out of scope; a distinctive display font, if ever wanted, must be vendored through `build_head()` — never a CDN `<link>`, never `NotStr`.
- **Color = semantic tokens.** Dominant-color-plus-sharp-accent via component variants (`ButtonT.primary`, `BadgeT.accent`) and semantic tokens (`text-base-content/70`) / `/core/utils/palette.py` constants — never raw `text-gray-600` or bespoke hex. See `ui-css`.
- **Motion = Alpine/HTMX seams.** Reserve motion for high-impact moments — the shell-first reveal (`content_loading_placeholder` + HTMX swap) and Alpine `x-transition` — not scattered JS micro-animations. See `ui-browser`.
- **Composition = design tokens.** Deliberate negative space OR controlled density via `Container.*`, `Spacing.*`, `Card.*` (`/ui/tokens.py`) — never magic widths.

**Avoid AI-slop:** no purple-gradient-on-white clichés, no cookie-cutter layout lacking context-specific character; raw `H1()` → `PageHeader`, bespoke hex/font → semantic tokens / vendored fonts, scattered micro-animations → high-impact seams.

---

## 1. Page Architecture

### BasePage — The Foundation

`BasePage` is the single entry point for all pages. It automatically includes HTMX, Alpine.js, the compiled Tailwind CSS (`output.css` via `skuel_headers()`), Lucide, Vis.js, SKUEL's JS/CSS, modal container, and ARIA live regions.

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
| `/submissions` | Submissions MOC root | `STANDARD` | Sidebar-free card hub linking to Sync, Exercise, Journal, History, Knowledge |

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
    actions=Button("Create Task", cls=ButtonT.primary,
                   **{"hx-get": "/tasks/create-modal", "hx-target": "#modal"}),
)

# Section header with action link
SectionHeader(
    "Recent Tasks",
    action=A("View All", href="/tasks/all", cls="text-primary hover:underline"),
)
```

### Shell-First Page Loading — The Standard Pattern

All SKUEL pages that need DB data use the **shell-first pattern**: the route handler returns page chrome immediately (zero DB calls), while a `hx_trigger="load"` div fires a `*/content` fragment endpoint that does the work.

```python
from ui.patterns.loading import content_loading_placeholder
```

`content_loading_placeholder` renders an `animate-pulse` skeleton shimmer while the fragment loads — four bars at varying widths give a content-shape cue. `loading_text` is `sr-only` (screen readers only).

```python
# ✅ CORRECT: shell returns immediately, content fills in via HTMX
@rt("/tasks")
def tasks_page(request: Request) -> Any:
    require_authenticated_user(request)
    content = Div(
        PageHeader("Tasks", subtitle="Manage your daily work"),
        content_loading_placeholder("/tasks/content", "tasks-content"),
    )
    return BasePage(content, title="Tasks", request=request, active_page="tasks")

@rt("/tasks/content")
async def tasks_content_fragment(request: Request) -> Any:
    user_uid = require_authenticated_user(request)
    result = await tasks_service.get_user_tasks(user_uid)
    if result.is_error:
        return Div(
            render_error_banner(result.expect_error().display_message),
            id="tasks-content",
        )
    return Div(TasksList(result.value), id="tasks-content")
```

**Detail pages** (UID from query param) — validate the UID in the shell (cheap), pass it to the fragment:

```python
@rt("/tasks/detail")
def task_detail_page(request: Request) -> Any:
    require_authenticated_user(request)
    uid = request.query_params.get("uid", "")
    if not uid:
        return render_activity_sidebar_page(
            Div(render_error_banner("Missing task UID")), active="tasks", request=request
        )
    content = Div(
        content_loading_placeholder(f"/tasks/detail/content?uid={uid}", "task-detail-content"),
    )
    return render_activity_sidebar_page(content, active="tasks", request=request)

@rt("/tasks/detail/content")
async def task_detail_content_fragment(request: Request) -> Any:
    user_uid = require_authenticated_user(request)
    uid = request.query_params.get("uid", "")
    task_result = await tasks_service.get_task(uid)
    if task_result.is_error or task_result.value.user_uid != user_uid:
        return Div(render_error_banner("Task not found"), id="task-detail-content")
    task = task_result.value
    # connection_fetch_backend implements the ConnectionFetchOperations port (below the boundary, ADR-044)
    connections_map = await connection_fetch_backend.fetch_entity_connections(config, [task.uid])
    return TaskDetailView(task, connections_map.get(task.uid, []))
```

**Path-param routes** (`/explore/ku/{uid}`) — embed the param in the fragment URL. KU uses `BasePage(CUSTOM)` (reading-first column, no sidebar) and pre-loads its Alpine factory before the fragment arrives:

```python
@rt("/explore/ku/{uid}")
def explore_ku_detail(request: Request, uid: str) -> Any:
    content = Div(
        Script(src="/static/js/ku-reading.js"),  # Alpine factory before HTMX fragment
        content_loading_placeholder(f"/explore/ku/{uid}/content", "ku-detail-content"),
    )
    return BasePage(content, title="Read", page_type=PageType.CUSTOM, request=request, active_page="explore")

@rt("/explore/ku/{uid}/content")
async def explore_ku_content_fragment(request: Request, uid: str) -> Any:
    ku_result = await orchestrator.get_ku(uid)
    if ku_result.is_error:
        return Div(render_error_banner(f"Not found: {uid}"), id="ku-detail-content")
    return build_ku_content(ku_result.value, ...)
```

**Fragment naming conventions:**
- List pages: `*/content` (replaces the whole content area)
- Detail pages: `*/detail/content?uid=` (replaces detail content area)
- Path-param pages: `*/{uid}/content` (replaces content area for that entity)

**Rule:** Every route that calls a service before rendering belongs in a `*/content` fragment, not the shell. The shell only does: auth check, UID extraction, error for missing UID, and **forwarding page-URL state into the fragment URL**.

**Query-param trap:** the page URL and the fragment request are two separate HTTP requests — filter params in the page URL (`/tasks?status=completed`) are silently dropped unless the shell whitelist-forwards them into the placeholder URL. And when a fragment applies user-chosen filters, answer with an `HX-Push-Url` header pointing at the canonical *page* URL so the view is bookmarkable. Both halves implemented in `adapters/inbound/activity_ui_factory.py`; full recipe in `docs/patterns/SHELL_FIRST_PAGE_PATTERN.md` § The Query-Param Trap.

**See also:** `docs/patterns/SHELL_FIRST_PAGE_PATTERN.md`

### Skeleton Components — When to Use Each

`content_loading_placeholder` is for shell-first page sections (full content areas). For inline HTMX containers and Alpine loading states, use the skeleton components directly:

```python
from ui.patterns.skeleton import SkeletonList, SkeletonLines, SkeletonTimeline
```

| Component | When to use |
|-----------|-------------|
| `content_loading_placeholder` | Shell-first page sections — replaces entire content area on load |
| `SkeletonList(count=3)` | Hub panels, HTMX containers that load a list of cards |
| `SkeletonLines(count=3)` | Expand-on-click panels, tree nodes, small inline lists |
| `SkeletonTimeline()` | Vis.js Timeline loading state — fills `h-[70vh]` with Gantt rows |

**Rule:** Never use `P("Loading...")` or `Span("Loading...")` as a loading placeholder anywhere in UI code.

---

## Component, Navigation, Sidebar, Form, CSS & Interactivity Reference

The detailed building blocks live in **[reference.md](reference.md)**:

- **§2 Component Composition** — component signature conventions, empty states, StatsGrid, CardGenerator, badges, view contexts, the three composition strategies, FILTER_CONFIGS.
- **§3 Navigation** — navbar structure, mobile ordering, nav items.
- **§4 Sidebar Pages** — SidebarPage, domain sidebar helpers, collapsible state, tabbed sidebars.
- **§5 Form Patterns** — model-driven forms, sections, edit/fragment modes, modal forms, date/time inputs.
- **§6 Inline CSS Reference** — semantic tokens, buttons, badges, alerts, cards, responsive layout.
- **§7 Inline Interactivity Reference** — HTMX + Alpine recipes (submit-append, lazy load, debounced search, confirm-delete, loading state, conditional fields).

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
SidebarPage(content=content, items=items, ...)

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

# ❌ Old ui.buttons import (deleted in PR E)
from ui.buttons import Button, ButtonT, ButtonLink, IconButton
# ❌ monsterui.franken import — removed (ADR-071), no longer works
from monsterui.franken import Button, ButtonT
# ✅ Button/ButtonT — use ui.components
from ui.components import Button, ButtonT
# ✅ ButtonLink — from ui.primitives
from ui.primitives import ButtonLink
# ✅ Card family — use ui.components
from ui.components import Card, CardBody, CardHeader, CardTitle

# ❌ Old tuple cls+size pattern
Button("Edit", cls=(ButtonT.ghost, ButtonT.sm))
ButtonLink("View →", href="/tasks", cls=(ButtonT.ghost, ButtonT.xs))
# ✅ New: style via cls=, geometry via size= kwarg
Button("Edit", cls=ButtonT.ghost, size="sm")
ButtonLink("View →", href="/tasks", cls=ButtonT.ghost, size="xs")

# ❌ Tailwind palette over semantic tokens
P("text", cls="text-gray-600")
# ✅ Semantic tokens
P("text", cls="text-base-content/70")

# ❌ Raw H1/H2 for hierarchy — ad-hoc type scale, no committed direction
H1("Tasks", cls="text-3xl font-bold")
# ✅ PageHeader/SectionHeader carry the type scale (design intent)
PageHeader("Tasks", subtitle="Manage your daily work")

# ❌ Bespoke hex or hand-linked/CDN font — use semantic tokens; vendor fonts via build_head()
Span("New", style="color:#7c3aed")
# ✅ Semantic variant/token; fonts vendored via build_head()
Badge("New", variant=BadgeT.accent)
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

**Design intent:**
- [ ] Committed tone held across the page (not generic/cookie-cutter)
- [ ] Hierarchy via `PageHeader`/`SectionHeader` (no raw `H1()`/`H2()`)
- [ ] Color via semantic tokens / `palette.py` (no bespoke hex, no `text-gray-*`)
- [ ] Motion only at high-impact seams (`content_loading_placeholder`, `x-transition`)

---

## 10. Key Files

| File | Purpose |
|------|---------|
| `/ui/layouts/base_page.py` | `BasePage` + `build_head()` — foundation for all pages |
| `/ui/layouts/page_types.py` | `PageType` enum and config |
| `/ui/layouts/navbar.py` | Navbar — admin: SKUEL logo + avatar + Sign out; regular: center links from `ICON_NAV_ITEMS` (Library, PathSteps; Today on mobile bottom nav) + right icon cluster (Search, Calendar, Askesis, Shared-inbox, bell, Profile avatar, Sign out) |
| `/ui/layouts/nav_config.py` | `ICON_NAV_ITEMS`, `ACTIVITY_DROPDOWN_ITEMS`, `MAIN_NAV_ITEMS` |
| `/ui/patterns/sidebar.py` | `SidebarItem`, `SidebarNav`, `SidebarPage` |
| `/ui/curriculum/` | Curriculum sidebar, layout, landing page |
| `/ui/patterns/__init__.py` | `PageHeader`, `SectionHeader`, `EmptyState`, `CardGenerator`, `StatCard`, `IconStat`, `StatTile`, `StatsGrid`, `FormGenerator`, `SettingToggle` |
| `/ui/page_contexts.py` | Per-domain TypedDicts (`TasksPageContext`, `GoalsPageContext`, etc.) for route→UI contracts |
| `/ui/patterns/form_generator.py` | `FormGenerator` — dynamic form generation from Pydantic models |
| `/ui/tokens.py` | `Container`, `Spacing`, `Card` design tokens |
| `/core/utils/palette.py` | `SemanticColor`, `RelationshipColor`, `EventTypeColor`, `FrequencyColor`, `CalendarFallback` — centralized hex color constants (`ui/palette.py` re-exports) |
| `/ui/primitives.py` | Shared design primitives: `icon_tile()`, `section_label()`, `primary_btn()`, `card_row()`, `ButtonLink`, `SelectableOptionRow()`, `dropdown_menu()`, `dropdown_separator()`, `UploadDropzone()`, `SelectedFileCard()`. Source of truth for the unified design language tokens (container, selection, typography). `SelectableOptionRow` is the canonical option-row with icon+title+subtitle+checkmark — active/hover state strings live here only. `dropdown_menu`/`dropdown_separator` are the canonical Alpine dropdown shell. `UploadDropzone`/`SelectedFileCard` are the canonical drag-drop empty/filled file-upload states. |
| `ui/feedback.py`, `ui/layout.py`, `ui/navigation.py`, `ui/data.py`, `ui/theme.py` | Pure Tailwind wrappers (ADR-071 complete). `ui/buttons.py`, `ui/cards.py`, `ui/text.py` deleted (PR E). `ButtonLink` from `ui/primitives.py`. |
| `ui/components/` | **SKUEL-owned Tailwind component layer (ADR-071 complete).** Import from here: `Button`/`ButtonT`, `Alert`/`AlertT`/`Loading`/`Progress`, `Icon` (Lucide), full form set (`Input`, `Label`, `LabelInput`, `LabelTextArea`, `LabelSelect`, `LabelCheckbox`, `Select`, `TextArea`, `Switch`, `Radio`, `Range` — bare `Checkbox` is exported from `ui.forms` only), `Table`/`TableFromLists`/`TableFromDicts`/`TableT`, `Divider`, `DivFullySpaced`/`DivCentered`/`Center`, `TabContainer`, `Accordion`/`AccordionItem`, `Card`/`CardBody`/`CardHeader`/`CardTitle`/`CardFooter`. |
| `/static/js/skuel.js` | All Alpine.data() components |
| `/ui/profile/hub.py` | `ProfileHubView` — 4-tab hub (Activities / Curriculum / Submissions / Reports, default Activities); Activities/Curriculum/Reports render `HubAccordionBlockList` (native `<details>` accordions, lazy `intersect once` previews) |
| `/ui/activities/nav.py` | Activity sidebar config (`ACTIVITY_SIDEBAR_ITEMS`) + `render_activity_sidebar_page()` helper |
| `/ui/gradebook/nav.py` | GradeBook sidebar config (`GRADEBOOK_SIDEBAR_ITEMS`) + `render_gradebook_sidebar_page()` helper |
| `/ui/workbench/hub.py` | `SubmissionsTabPanel` — Submissions tab on `/profile` (4 link buttons mirroring the sidebar) |
| `/ui/workbench/nav.py` | Submissions sidebar config (`SUBMISSIONS_SIDEBAR_ITEMS`) + `render_submissions_sidebar_page()` helper |
| `/adapters/inbound/user_entry_ui.py` | `submissions_moc` (MOC root), `gradebook_moc` (MOC root), submission history endpoints, knowledge-notes grounding page (`/submissions/knowledge`), journal submit/browse/download |
| `/adapters/inbound/settings_routes.py` | Settings page (extracted from Workbench) — `/settings` + `/settings/save` |
| `/ui/library/nav.py` | Library sidebar config (`LIBRARY_SIDEBAR_ITEMS`) + `render_library_sidebar_page()` helper |
| `/ui/activities/hub.py` | `ACTIVITY_BLOCKS` + `render_domain_card_preview` — Activities tab on `/profile` (accordion blocks, HTMX lazy-loaded from `/api/profile/{slug}/preview`) |
| `/adapters/inbound/library_routes.py` | Library hub orchestrator — wires `library_ui.py` with its 6 service dependencies (extracted from `learning_loop_routes.py`) |
| `/adapters/inbound/library_ui.py` | `library_moc` (MOC root at `/library`) + sidebar sub-pages: `/library/exercises` (status-aware), `/library/resources`, `/library/ku` (PINNED only), `/library/path-steps` (IN_PROGRESS only). Exercise status helpers in `ui/learning_loop/exercise_status.py` |
| `/adapters/inbound/explore_ui.py` | Reading-first `/explore` surface + `/explore/library` catalog + `/explore/read/{uid}` alias + API routes. PS/Ku detail pages and learning loop fragments are in `learning_loop_routes.py`. |
| `/adapters/inbound/user_entry_routes.py` | UserEntry hub orchestrator (`create_user_entry_routes`) — wires user_entry_ui, entry_reports_ui, activity_reports_ui, revised_exercises_ui sub-factories |
| `/ui/learning_loop/` | Shared learning loop renderers: `exercise_status.py` (status pills, action links, exercise list), `submissions_section.py` (PS submissions), `feedback_section.py` (PS feedback) |
| `/core/services/resource_service.py` | `ResourceService` — `list_all()` for `Resource` entities (books, talks, films) |
| `/ui/activities/filter_bar.py` | Config-driven `ActivityFilterBar` component (`FilterBarConfig`, `FilterSelect`) — shared across all 6 Activity Domains |
| `/ui/activities/_shared.py` | Shared Activity Domain UI utilities (`MetadataField`, `safe_id`, `CONNECTION_ICONS`, `ConnectionBadges`, `ConnectionSummary`). Connection dicts use `connected_uid`/`connected_type` keys. |
| `/core/utils/connection_configs.py` | Pure-data `ConnectionConfig` + 6 per-domain constants. The batch connection Cypher lives below the boundary in `ConnectionFetchBackend` (behind `ConnectionFetchOperations`, ADR-044); UI factories receive the port as `ActivityUIConfig.backend` |
| `/core/utils/entity_filters.py` | `filter_tasks/goals/habits/events/choices/principles()` — business filtering/sorting logic extracted from UI views |
| `/adapters/inbound/activity_ui_factory.py` | `ActivityUIConfig` dataclass + `create_activity_ui_routes()` — shared factory generating 5 routes per Activity Domain (page shell, content fragment, list-fragment, detail shell, detail content). Each `{domain}_ui.py` is ~50 lines creating an `ActivityUIConfig` and delegating here |
| `/ui/journals/` | Journal UI rendering: `cards.py`, `components.py`, `forms.py` — used by `user_entry_ui.py` |
| `/ui/insights/` | Insight UI rendering: `components.py`, `filters.py`, `insight_card.py` — extracted from `insights_ui.py` |
| `/ui/pathways/` | Pathways UI rendering: `components.py` — extracted from `pathways_ui.py` |
| `/ui/notifications/` | Notification UI rendering: `cards.py` — extracted from `notifications_routes.py` |
| `/ui/calendar/` | Calendar UI rendering: `components.py`, `converters.py` — extracted from `calendar_ui.py` |
| `/ui/finance/` | Finance UI rendering: `components.py`, `invoice_views.py`, `layout.py`, `section_views.py`, `types.py` — extracted from `finance_ui.py` |
| `/ui/explore/ku_detail.py` | Ku detail page rendering — extracted from `explore_ui.py` |
| `/ui/explore/ps_detail.py` | PathStep detail page rendering — extracted from `explore_ui.py` |
| `/ui/profile/_shared.py` | Shared profile primitives (`DomainSummaryCard`, `DomainIntelligenceCard`, `DomainFilterControls`, `_item_list`) |
| `/ui/profile/curriculum_views.py` | KU, PS, LP profile views |
| `/docs/patterns/UI_COMPONENT_PATTERNS.md` | Complete patterns documentation |
| `/tests/unit/ui/test_cross_domain_consistency.py` | Cross-domain consistency tests — verifies PageHeader, EmptyState, StatsGrid, EntityRelationshipsSection used across all 6 activity domains + 4 hub pages |

## See Also

- `ui-css` — CSS layer, Tailwind utilities, and component styling reference
- `ui-browser` — Deep reference for HTMX patterns and Alpine.js directives
- `fasthtml` — FastHTML route patterns and FT component system
- `chartjs` — Chart.js analytics visualization
- `vis-network` — Vis.js graph visualization
