---
title: UI Component Patterns
updated: '2026-04-05'
category: patterns
related_skills:
  - accessibility-guide
  - ui-css
  - ui-browser
  - skuel-ui
related_docs: []
---
# UI Component Patterns

*Last updated: 2026-02-01*

**Core Principle:** "BasePage for consistency, custom layouts for special cases"

## Quick Start

**Core Skills:** [@skuel-ui](../../.claude/skills/skuel-ui/SKILL.md), [@ui-css](../../.claude/skills/ui-css/SKILL.md), [@ui-browser](../../.claude/skills/ui-browser/SKILL.md)

**Advanced Skills:** [@accessibility-guide](../../.claude/skills/accessibility-guide/SKILL.md)

For hands-on implementation:
1. Invoke `@skuel-ui` for BasePage patterns, page types, navigation, sidebars, and forms
2. Invoke `@ui-css` for Tailwind + `ui.components` styling
3. Invoke `@ui-browser` for HTMX server communication and Alpine.js client-side state
4. Invoke `@accessibility-guide` for WCAG 2.1 Level AA compliance
5. Continue below for complete component architecture

**Related Documentation:**
- [/ui/activities/sidebar.py](/ui/activities/sidebar.py) - Activities sidebar items
- [/ui/study/layout.py](/ui/study/layout.py) - Study sidebar example

---

## Overview

SKUEL uses a layered UI component architecture built on its own pure-Tailwind + Alpine.js component layer (`ui.components`, ADR-071). This document explains the component system and how to use it.

**Key Files:**
- `/ui/` - SKUEL UI design system (components, patterns, layouts, tokens)
- `/ui/layouts/base_page.py` - Unified page wrapper
- `/ui/layouts/page_types.py` - Page type definitions (HUB vs STANDARD)
- `/ui/tokens.py` - Spacing, container, and styling tokens
- `/core/utils/palette.py` - Centralized hex color constants (SemanticColor, RelationshipColor, EventTypeColor, FrequencyColor, CalendarFallback) — `ui/palette.py` re-exports for backward compat
- `/ui/feedback.py`, `/ui/layout.py` — pure Tailwind wrappers; `ButtonLink` in `ui/primitives.py` (also pure Tailwind)
- `/ui/forms/` — pure Tailwind wrappers; `ui/buttons.py` + `ui/cards.py` deleted PR E — `Button`/`ButtonT`/`Card*` now in `ui.components`
- `/ui/navigation.py`, `/ui/data.py` — pure Tailwind wrappers
- `/ui/components/` - **SKUEL-owned Tailwind component layer (ADR-071, complete).** Pure Tailwind + Alpine.js, no UIkit/MonsterUI/DaisyUI. `ui/theme.py` is also pure Tailwind (loads compiled `output.css`).

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

**Evolution (2026-03-13):** `/study` is the student workspace hub landing page. Sub-pages are top-level routes (`/submit`, `/submissions`, `/entry-reports`, `/activity-reports`, `/submit-activity-report`) sharing a 5-item Study sidebar. `/study` landing shows vertically-stacked workspace cards. Old `/submissions/*` and `/learn/*` UI paths redirect 301 to the new top-level routes.

**Evolution (2026-03-17a):** Navbar gains **C** (Curriculum) icon between A and S. All three icons (A, C, S) now have hover dropdown menus. `/curriculum` landing shows 4-card grid. Curriculum sub-pages (`/lessons`, `/path-steps`, `/learning-paths`, `/exercises`) share a 4-item Curriculum sidebar. Exercises moved from Study sidebar to Curriculum sidebar.

**Evolution (2026-03-17b):** **A** icon removed from navbar. Activity links moved to avatar hover dropdown (`_avatar_dropdown()`). Navbar now: C, S + avatar (hover → Activities) + logout. `/profile` stripped of sidebar — uses `BasePage` directly. Journals card on `/activities` replaced with lightweight link. Sidebar badges loaded async via `GET /api/sidebar/badges` (HTMX OOB swap with `CountBadge` + `HealthIndicator`).

**Evolution (2026-03-17c):** **⚛️** (Knowledge) icon added as first navbar item, linking to `/ku`. Emoji icons use `text-base` styling (vs `font-semibold text-sm` for letter icons). `/ku` page redesigned from SEL-category grouped sections to flat Ku listing with bookmarks + latest sidebar. Sidebar powered by `UserRelationshipService.get_pinned_entities()` for bookmarks. Navbar order: SKUEL logo → ⚛️ → C → S → avatar → logout → search → bell.

**Evolution (2026-02-09):** All 5 sidebars (Profile, KU, Reports, Journals, Askesis) unified into single Tailwind + Alpine.js component (`SidebarPage`). Custom CSS/JS files (`profile_sidebar.css`, `profile_sidebar.js`) deleted. Mobile uses horizontal tabs (SKUEL `TabContainer`) instead of drawer/overlay.

**Evolution (2026-03-29):** `/profile` evolved from card grid to **live actionable hub**. Data sourced from `UserContext.build_rich()`. See `ui/profile/hub.py`.

**Evolution (2026-04-03a):** `/profile` Activity Domains changed from Alpine.js tabbed view (one domain visible at a time) to all 6 domains visible as scrollable blocks. Each block has a colored domain header (icon + clickable title + "View all" link) and 3 priority-sorted cards HTMX lazy-loaded from `/api/profile/{slug}/preview`.

**Evolution (2026-04-03b):** Activity Domains extracted from `/profile` into dedicated `/activities` hub with `SidebarPage` sidebar. The old horizontal `ActivityDomainNav` band replaced by collapsible Activity sidebar shared across `/activities`, `/tasks`, `/goals`, `/habits`, `/events`, `/choices`, `/principles`. Avatar dropdown simplified to Profile + Sign out. Activity icon added to navbar `ICON_NAV_ITEMS`. `/profile` retains Focus/Velocity, link to `/activities`, Nous placeholder, and Settings.

**Evolution (2026-04-04b):** Activity Domains content merged back into `/profile` — `ActivityHubView()` rendered inline (6 HTMX-loaded domain blocks). Avatar dropdown gains 6 Activity Domain links (Tasks, Goals, Habits, Events, Choices, Principles) between Search and Sign out. `ACTIVITY_DROPDOWN_ITEMS` re-populated for mobile menu. Activity icon removed from navbar `ICON_NAV_ITEMS`; `/activities` route removed entirely (no redirect).

**Evolution (2026-07-05):** Activity Domains return to `/profile` as a dedicated **Activities** tab (the May tab rework had dropped them, orphaning `ActivityHubView`). `ui/activities/hub.py` now holds `ACTIVITY_BLOCKS` + the preview renderer; the tab uses `HubAccordionBlockList` (#518 pattern). `ActivityHubView`, the `/profile` overview constellation (`OverviewView`, `/api/profile/intelligence-section`, `/api/profile/charts/*`), and `SkeletonIntelligence` deleted — Askesis is the intelligence UI. Alignment radar chart re-homed to `/lifepath/alignment`.

**Evolution (2026-03-30):** Tasks and Goals have active read-focused UI views at `/tasks` and `/goals` with HTMX interactions, filtering, and knowledge connections. Tasks icon (check-square) added to navbar between Knowledge and Submissions. Habits, Events, Choices, and Principles read-focused UIs are planned. Navbar order: SKUEL logo → ⚛️ (Knowledge) → Tasks → ⇄ (Submissions) → avatar → logout.

**Evolution (2026-04-03):** Admin accounts redirect to `/` after login instead of `/admin`. The `/` route renders an admin home hub with two cards (Admin → `/admin`, Teaching → `/teaching`). SKUEL logo in navbar left section links to `/`. "Admin Dashboard" and "Teaching" text links removed from navbar center. Admin navbar: SKUEL logo (left) → empty center → avatar + logout with icon (right). Mobile menu has explicit Admin + Teaching + Sign out links.

**Evolution (2026-04-04):** Explore sidebar evolved from text-only "My Learning" sidebar to **graph-centered sidebar**. Hero: `ExploreGraphView` (`ui/explore/graph.py`) — interactive Vis.js force-directed graph with hub mode (learning universe) and entity mode (lateral relationships). Filter tabs (All/Learning/Saved) control both graph node highlighting and list visibility. Sidebar widened to `w-96` (384px) via new `sidebar_width` param on `SidebarPage`. Alpine component: `exploreGraph` in `skuel.js`. API: `GET /api/explore/graph`. Graph expands to full-screen JS overlay on `document.body` (creates a second Vis.js network to escape sidebar `overflow:hidden` + `transform`).

**Evolution (2026-04-05):** Learning loop UI fully wired: EntryReport detail page at `/entry-reports/detail?uid=` (outcome badge, processor badge, assessment score bar); RevisedExercise student pages at `/revised-exercises` and `/revised-exercises/detail?uid=` (GradeBook sidebar); GradeBook expanded from 4 to 5 items (+ Revisions) and 5 hub blocks. Teaching revision form enhanced with structured `FeedbackCategory` feedback points (Alpine.js dynamic list). `AlpineModal` component standardized in `ui/patterns/modal.py` — adopted in calendar, sharing, and insights modals. Raw DaisyUI `Select` classes replaced with SKUEL `ui.forms.Select` wrapper in relationship_graph, profile, and calendar.

**Evolution (2026-04-06a):** Post-login redirect changed from `/profile` to `/home` — a new post-login landing hub with 6 navigational cards (Tasks+, Explore, Library, Submissions, GradeBook, Settings) using `HubContainerGrid`. Hub view in `ui/home_hub.py`, route in `adapters/inbound/home_routes.py`.

**Evolution (2026-04-06b):** Navbar Hub access changed from right-side hamburger dropdown to a **Hub icon** (home) as the furthest-left icon link. Right section simplified to Search + notification bell only. `_hub_dropdown()` removed from `navbar.py`.

**Evolution (2026-04-06c):** Avatar dropdown removed from navbar left section — Tasks+ icon already links to `/profile`, making it redundant. Sign-out icon added to navbar right section (Search + bell + Sign out). Focus+Velocity header extracted from `/profile` to shared `personal_header()` in `ui/patterns/personal_header.py` and added to top of `/home`. Nous placeholder removed from `/profile`. `/home` route now fetches `UserContext` via `get_rich_unified_context()`.

**Evolution (2026-06-24):** Profile avatar button removed from navbar right section. Askesis flame icon (`Icon("flame")`) added linking to `/askesis`, placed between Search and notification bell. Right section is now: Search + Askesis (flame) + bell + Sign out. Brand "SKUEL" link (→ `/profile`) is the entry point to the profile hub.

**Evolution (2026-06-28):** Profile avatar button (`_profile_button`) re-wired into navbar right section, placed between notification bell and Sign out. Brand "SKUEL" link updated from `/profile` → `/explore` (the ZPD-surfaced reading focal point — primary landing destination after login). `Explore` removed from `ICON_NAV_ITEMS`; the brand link is now the sole entry point. Right section is now: Search + Askesis (flame) + bell + Profile avatar + Sign out.

**Evolution (2026-07-17):** Tasks+ removed from `ICON_NAV_ITEMS` (activity domains are reached via the Profile hub); Journals (`/journals`, `Icon("book-open")`) takes its slot. Calendar icon button (`_calendar_button`, `Icon("calendar")` → `/events/calendar`) added to the navbar right section after Search; calendar pages now pass `active_page="calendar"` (was `"tasks"`). Right section is now: Search + Calendar + Askesis (flame) + Shared-inbox + bell + Profile avatar + Sign out.

**Evolution (2026-04-06d):** Performance pass — `personal_header()` on `/tasks` was blocking the page render with the 1034-line MEGA_QUERY just for 3 fields. Replaced with `personal_header_placeholder()` — an HTMX div that lazy-loads via `GET /api/personal-header` (registered in `home_routes.py`) after the page renders. Use `personal_header_placeholder()` on any page that doesn't already have `UserContext` loaded; use `personal_header(context)` only when the full context is already in scope (e.g. `/home`). Explore page and sidebar queries parallelized with `asyncio.gather`. `RequestTimingMiddleware` added — logs all requests with duration; `SLOW` at WARNING for >100ms.

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

All sidebar pages (Activity Domains, Explore, GradeBook, Library, Teaching, Submissions) use a single `SidebarPage()` component from `ui/patterns/sidebar.py`.

**Key Features:**
- One component for all 6 sidebar pages
- Desktop: Fixed sidebar (default 256px, configurable via `sidebar_width` param — Explore uses `w-96`/384px for graph) with smooth collapse to 48px edge
- Mobile: Horizontal tabs (SKUEL `TabContainer`, no drawer/overlay)
- Alpine.js `collapsibleSidebar` + `Alpine.store()` for shared reactive state
- localStorage persistence of collapsed state
- Screen reader announcements on toggle

**Core API:**
```python
from ui.patterns.sidebar import SidebarItem, SidebarPage

items = [
    SidebarItem("Submit", "/submit", "submit", icon="📤"),
    SidebarItem("History", "/submissions/history", "history", icon="📝"),
    SidebarItem("Entry Reports", "/entry-reports", "entry-reports", icon="📋"),
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

**See:** `@skuel-ui` for complete implementation guide

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
- `/core/services/user/domain_health.py` - `DomainStatus` class (canonical — 8 `calculate_*_status()` methods)
- `/ui/profile/domain_stats_config.py` - Configuration and extractor functions (imports `DomainStatus` from core)
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

Adopted across all 6 Activity Domain dashboards, Study hub, Curriculum hub, Admin dashboard, Analytics, Calendar, LifePath, Timeline, Finance (all 6 sections), Pathways (4 pages), Askesis (3 pages), Form Submissions, Submissions, User Profile, and Preferences. Every `SidebarPage` content area starts with a `PageHeader`. `SectionHeader` adopted across ~7 files (~10 usages) — groups, insights, exercises, analytics, admin, ingestion, curriculum adaptive. Never use raw `H2()` for section headers outside cards.

```python
from ui.patterns import PageHeader, SectionHeader

# Page header with optional subtitle and actions
PageHeader("Tasks", subtitle="Manage your daily tasks")
PageHeader("Goals", subtitle="Track and achieve your goals")

# Section header with optional action link
SectionHeader("Recent Tasks")
SectionHeader("Active Goals", action=ButtonLink("View All", href="/goals", cls=ButtonT.ghost, size="xs"))
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

## Import Pattern (SKUEL Components)

> **ADR-071 complete.** All UI is SKUEL-owned pure Tailwind + Alpine.js — import from
> `ui.components` (which re-exports the wrapper modules below). `from monsterui.franken import ...`
> no longer works. See `/docs/decisions/ADR-071-skuel-tailwind-component-layer.md`.

```python
# Pure HTML elements from FastHTML
from fasthtml.common import H1, H2, H3, P, A, Form, Li, Ul

# ui.components — the unified import surface (Button/ButtonT, Card family, and more)
from ui.components import Button, ButtonT, Card, CardBody, CardTitle
from ui.primitives import ButtonLink
from ui.enum_helpers import get_submission_status_badge_class
from ui.feedback import Alert, AlertT, Badge, BadgeT, Loading, Progress, ProgressT, RadialProgress
from ui.forms import Checkbox, Input, LabelCheckbox, LabelInput, LabelSelect, LabelTextArea, Radio, Range, Select, Textarea, Toggle
from ui.layout import Container, DivCentered, DivFullySpaced, DivHStacked, DivVStacked, Grid, Size
from ui.patterns.modal import AlpineModal  # Standardized Alpine.js modal wrapper
from ui.navigation import Dropdown, DropdownContent, DropdownTrigger, Menu, MenuItem, Navbar, NavbarCenter, NavbarEnd, NavbarStart, Tabs
from ui.data import Divider, DividerSplit, DividerT, Table, TableFromDicts, TableFromLists, TableT
# Standard FastHTML elements — always from fasthtml.common
from fasthtml.common import Div, Option, Span, Tbody, Td, Th, Thead, Tr

# Theme for app initialization
from ui.theme import skuel_headers, Theme
```

---

## Theme Headers

All SKUEL pages use `skuel_headers()` for consistent styling:

```python
from fasthtml.common import fast_app
from ui.theme import skuel_headers, Theme

# Default (light theme)
app, rt = fast_app(hdrs=skuel_headers())

# With custom theme
app, rt = fast_app(hdrs=skuel_headers(theme=Theme.dark))

# With PWA support
from ui.theme import pwa_headers
app, rt = fast_app(hdrs=(*skuel_headers(), *pwa_headers()))
```

**What `skuel_headers()` includes:**
- Meta viewport tags
- Compiled Tailwind CSS — `static/css/output.css` (built by `./dev css-build`)
- HTMX 1.9.10
- Alpine.js 3.14.8 (self-hosted)
- SKUEL custom CSS/JS

Icons are server-rendered inline SVG via `Icon()` (`ui/components/icon.py`) — no lucide
runtime is loaded; there is no `data-lucide` / `createIcons()` client scan.

### `build_head()` — Canonical `<head>` for Full Documents

Pages that return complete `Html()` documents (rather than partial HTMX fragments) use `build_head()` from `base_page.py`. This is the **single source of truth** for all `<head>` content — `BasePage` and `AuthPage` both delegate to it. Never construct a `Head(...)` manually. Never hand-assemble `<link>` tags in raw HTML strings.

`build_head()` loads the compiled Tailwind stylesheet (`static/css/output.css`) plus self-hosted HTMX, Alpine.js, and Lucide — no CDN dependency, no browser JIT.

```python
# Pass extra_css / extra_scripts to BasePage — they are forwarded to build_head()
return await BasePage(
    content,
    title="Timeline",
    page_type=PageType.CUSTOM,
    request=request,
    extra_css=["/static/vendor/vis-timeline/vis-timeline-graph2d.min.css", "/static/css/timeline.css"],
    extra_scripts=["/static/vendor/vis-timeline/vis-timeline-graph2d.min.js"],
)
# extra_scripts are injected before skuel.js so Alpine components can reference page-specific libs
```

### `AuthPage()` — Unauthenticated Pages

Login, registration, and landing pages use `AuthPage()` instead of `BasePage()`. It loads the full SKUEL CSS stack (compiled Tailwind `output.css`) via `build_head()` but renders no navbar, no modals, no toasts, no PWA components.

```python
from ui.layouts.base_page import AuthPage

# Login page route handler
return AuthPage(
    login_form_content,  # FT component tree
    title="Sign In",
)
```

Auth page content uses the same SKUEL component wrappers as the rest of the app (`LabelInput`, `Button`, `Card`, `Checkbox`). This ensures consistent styling — no parallel CSS classes, no raw HTML strings.

---

## Type-Safe Variants

SKUEL uses Python enums for type-safe component variants:

### Buttons

`ButtonT` is a `StrEnum` of Tailwind class strings. Style via **`cls=`** (not `variant=`);
geometry via the **`size=`** string kwarg. The enum is slim — `default`, `primary`,
`secondary`, `ghost`, `destructive`, `link` (no `error`/`success`/`warning`/`accent`/`outline`).

```python
# Primary action — cls=, not variant=
Button("Submit", cls=ButtonT.primary)

# Secondary/Ghost
Button("Cancel", cls=ButtonT.ghost)
Button("Back", cls=ButtonT.secondary)

# Destructive (was ButtonT.error)
Button("Delete", cls=ButtonT.destructive)

# With size (string: "xs" | "sm" | "md" | "lg" | "xl")
Button("Small", cls=ButtonT.primary, size="sm")
Button("Large", cls=ButtonT.primary, size="lg")

# Bordered/outline style is the default variant
Button("Outline", cls=ButtonT.default)

# With HTMX
Button("Load More", cls=ButtonT.ghost, hx_get="/items?page=2", hx_target="#list")
```

> For status-colored success/warning/error UI, use **badges/alerts** (`ui.feedback`), which
> keep `variant=` and the full color enum (see [Badges](#badges) / [Alerts](#alerts)) — the
> button and feedback enums are deliberately different.

### Alerts

```python
Alert("Operation successful!", variant=AlertT.success)
Alert("Warning: Check your input", variant=AlertT.warning)
Alert("Error occurred", variant=AlertT.error)
Alert("Info message", variant=AlertT.info)
```

### Badges

Three badge components in `ui/feedback`:

```python
from ui.feedback import Badge, BadgeT, StatusBadge, PriorityBadge

# StatusBadge — for any EntityStatus value (delegates to EntityStatus.get_badge_class())
StatusBadge("active")              # canonical green
StatusBadge("submitted")           # canonical yellow
StatusBadge("revision_requested")  # canonical yellow

# PriorityBadge — for priority values
PriorityBadge("high")    # error variant
PriorityBadge("medium")  # warning variant

# Badge — for everything else (category labels, entity types, counts)
Badge("Active", variant=BadgeT.success)
Badge("Pending", variant=BadgeT.warning)
Badge("5", variant=BadgeT.primary, size=Size.sm)
Badge("Ku", variant=BadgeT.accent, size=Size.sm)  # entity type pill
Badge("Path Step", variant=None, cls="bg-teal-100 text-teal-800 border-teal-200", size=Size.sm)
```

### Progress

```python
Progress(value=75, variant=ProgressT.primary)
Progress(value=100, variant=ProgressT.success)
RadialProgress(75, cls="text-success")   # color via cls; variant= is reserved/unused
```

---

## Card Pattern

**Always wrap card content in `CardBody`:**

```python
Card(
    CardBody(
        H2("Title"),
        P("Description"),
        Button("Action", cls=ButtonT.primary)
    ),
    cls="hover:shadow-lg"  # Additional classes optional
)
```

### Card with Actions

`CardActions` is deleted — use `CardFooter` (add `justify-end` for right-aligned actions):

```python
Card(
    CardBody(
        CardTitle("Task Name"),
        P("Task description here", cls="text-muted-foreground"),
        CardFooter(
            Button("Edit", cls=ButtonT.ghost, size="sm"),
            Button("Complete", cls=ButtonT.primary, size="sm"),
            cls="justify-end gap-2",
        ),
    )
)
```

### Card Styling

`Card` has **no `variant=`** (`CardT` is deleted). The base is a bordered, rounded surface;
adjust emphasis with Tailwind classes via `cls=`:

```python
# Default card (base bordered surface)
Card(CardBody(...))

# Emphasis / muted / danger — semantic-token border + background via cls
Card(CardBody(...), cls="border-primary")
Card(CardBody(...), cls="bg-muted")
Card(CardBody(...), cls="border-destructive")

# Hover effect (lift + shadow on hover)
Card(CardBody(...), cls="hover:shadow-md transition-shadow")
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
    Button("Sign In", cls=ButtonT.primary, type="submit"),
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

`Input` has no `size=` parameter — adjust geometry with Tailwind classes via `cls=`:

```python
Input(cls="h-8 text-sm")  # Smaller input
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
    Button("Add New", cls=ButtonT.primary),
)

# Centered content
DivCentered(
    Loading(size=Size.lg),
    cls="h-screen"
)
```

### Grid Layout

```python
# Responsive grid (1 col mobile, 2 on sm, 3 on lg+)
Grid(
    Card(CardHeader(CardTitle("Card 1")), CardBody(P("Content"))),
    Card(CardHeader(CardTitle("Card 2")), CardBody(P("Content"))),
    Card(CardHeader(CardTitle("Card 3")), CardBody(P("Content"))),
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

## Modal Pattern — AlpineModal

Use `AlpineModal` from `ui/patterns/modal.py` for all Alpine.js-controlled modals. It standardizes backdrop overlay, click-outside-to-close, transitions, and accessibility (`x-cloak`).

```python
from ui.patterns.modal import AlpineModal

# Simple modal controlled by Alpine.js boolean
AlpineModal(
    H3("Confirm Delete"),
    P("Are you sure you want to delete this item?"),
    Div(
        Button("Cancel", cls=ButtonT.ghost,
               **{"@click": "showConfirm = false"}),
        Button("Delete", cls=ButtonT.destructive,
               hx_delete="/api/items/123",
               hx_target="#item-list"),
        cls="flex gap-2 justify-end mt-4",
    ),
    show="showConfirm",
    close="showConfirm = false",
    max_width="max-w-lg",
)

# Scrollable modal with custom id
AlpineModal(
    *detail_content,
    show="isOpen",
    close="close()",
    max_width="max-w-2xl",
    scrollable=True,
    id="detail-modal",
)

# Open modal
Button("Delete",
       **{"@click": "showConfirm = true"},
       cls=ButtonT.destructive)
```

**Parameters:**
- `show` — Alpine.js expression for visibility (e.g. `"isOpen"`, `"shareModal"`)
- `close` — Alpine.js expression to close (e.g. `"close()"`, `"shareModal = false"`)
- `max_width` — Tailwind max-width class (default: `"max-w-md"`)
- `scrollable` — Whether content scrolls at 80vh (default: `False`)
- `id` — Optional DOM id

**Adopted in:** calendar components, sharing modal, insight card modal.

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
        Button("Logout", cls=ButtonT.ghost, size="sm")
    )
)
```

### Tabs

`Tabs()` delegates to `ui.components.nav.TabContainer` — each argument is a `(label, content)` tuple:

```python
Tabs(
    ("All", task_list_panel),
    ("Active", active_panel),
    ("Completed", completed_panel),
    active_tab=0,
)
```

### Dropdown

```python
Dropdown(
    DropdownTrigger(Button("Options", cls=ButtonT.ghost)),
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
            "Actions": Button("Edit", cls=ButtonT.ghost, size="xs"),
        },
        {
            "Name": "Task 2",
            "Status": Badge("Pending", variant=BadgeT.warning),
            "Actions": Button("Edit", cls=ButtonT.ghost, size="xs"),
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
# CSS-only spinner — no variant param; use size to control dimensions
Loading()              # md (default)
Loading(size=Size.sm)
Loading(size=Size.lg)

# HTMX loading indicator
Button("Save",
       cls=ButtonT.primary,
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
            CardFooter(
                Button("Edit", cls=ButtonT.ghost, size="sm",
                       hx_get=f"/tasks/{task.uid}/edit", hx_target="#modal"),
                Button("Complete", cls=ButtonT.primary, size="sm",
                       hx_post=f"/api/tasks/{task.uid}/complete", hx_target="#task-list"),
                cls="justify-end gap-2",
            ),
        ),
        cls=f"border-l-4 {_priority_border(task.priority)}"
    )
```

### Empty State

**Location:** `/ui/patterns/empty_state.py`

Adopted across ~75 usages in ~38 files (Activity Domains, Curriculum, Study, Admin, Finance, Teaching, Explore, Search, Notifications, Insights, Profile, etc.). No hand-rolled empty states remain.

```python
from ui.patterns.empty_state import EmptyState

# Primary list view — full CTA
EmptyState(
    title="No tasks found",
    description="Create one to get started!",
    action_text="Create task",
    action_href="/tasks",
)

# Secondary section — title only
EmptyState(title="No feedback yet")

# With icon
EmptyState(title="No habits for today!", icon="🎉")
```

**Usage rules:** Primary list views get full CTA. Secondary sections get title only. Tiny inline indicators (sidebar `<li>`, analytics cards) stay as `P()` — `EmptyState` with `py-12` is too heavy for compact contexts.

### Learning Loop Fragments (PathStep Detail)

**Location:** `ui/learning_loop/` — shared exercise status helpers + PathStep submission/feedback renderers.

The `/learning-loop/ps/{ps_uid}/*` fragment routes remain wired in `learning_loop_routes.py` (`create_learning_loop_fragment_routes`) but are not surfaced on the PS detail page since the 2026-06-24 reading-first redesign. Renderers in `ui/learning_loop/`:

- `exercise_status.py` — `render_exercise_list()`, status pills (`_STATUS_PILL`), action links with `from_ps` context. Shared with Library exercises tab (`/library/exercises`).
- `submissions_section.py` — `render_ps_submissions()` — submission rows with status badges.
- `feedback_section.py` — `render_ps_feedback()` — feedback rows with outcome badges, filters to submissions with reports.

---

## Common Anti-Patterns

### Don't Use Raw `H1()`/`H2()` for Page Headers

Page and section headers must use `PageHeader()` — not raw `H1()`/`H2()` with ad-hoc Tailwind classes. This ensures consistent typography (`text-2xl font-bold text-foreground`), spacing (`mb-8`), and subtitle/actions layout across all pages.

```python
# BAD: Hand-rolled header with inconsistent styling
H1("Pathways Dashboard", cls="text-3xl font-bold text-primary")
P("Track your learning journey", cls="text-lg text-muted-foreground mt-2")

# GOOD: PageHeader with consistent styling
PageHeader("Pathways Dashboard", subtitle="Track your learning journey")

# GOOD: PageHeader with right-aligned actions
PageHeader("Invoices", actions=Span(f"{count} total", cls="text-sm text-muted-foreground"))
```

**Skip PageHeader for:** error page headings inside Cards (use `CardHeader(CardTitle(...))`), modal titles, sub-section headings within CardBody, and genuinely custom layouts with badges/progress indicators below the title.

### Use Semantic Card Structure — Never Raw H2/H3 Inside Card()

Card titles must use `CardHeader(CardTitle(...))` — never raw `H2()` or `H3()` directly inside `Card()`:

```python
# CORRECT — semantic SKUEL card structure
Card(
    CardHeader(CardTitle("Learning Overview")),
    CardBody(content),
)

# WRONG — bypasses CardHeader/CardTitle styling
Card(
    H2("Learning Overview", cls="text-xl font-semibold mb-4"),
    content,
    cls="bg-background shadow-sm p-6",
)
```

Import from `ui.components`: `Card, CardBody, CardHeader, CardTitle` (M5 ✅). Base padding and background are built into the component classes — add layout-only classes like `mb-6` to `Card()`.

**Adoption status:** All card titles across ~12 files use semantic `CardHeader(CardTitle(...))`. Zero raw H2/H3 inside Card.

### Don't Use Raw `A()` for Action CTAs

Action links (Submit, View Report, Download, View all) must use `ButtonLink()` — not raw `A()` with ad-hoc Tailwind. Raw `A()` is reserved for entity title links, breadcrumbs, sidebar navigation, and inline contextual text links (e.g. links inside a paragraph sentence).

**Data-sourced hrefs must pass `safe_external_url()`** (`ui/primitives.py`): any URL that originates from stored data (e.g. Resource `source_url` from vault descriptors) is scheme-allowlisted to http/https before reaching an `href` — a `javascript:`/`data:` value renders as plain text instead of a link (stored-XSS class, Kody #502). Hardcoded route paths don't need it.

**Adoption status:** Used across ~45 files. No raw `A()` action CTAs remain.

```python
# BAD: Ad-hoc styled text link for a CTA
A("Submit →", href="/submit", cls="text-xs text-primary hover:underline")

# GOOD: ButtonLink with semantic style (cls=) + geometry (size=)
ButtonLink("Submit →", href="/submit", cls=ButtonT.primary, size="sm")
```

**ButtonLink style/size convention:**

| Action Type | `cls` | `size` | Examples |
|---|---|---|---|
| Primary CTA | `ButtonT.primary` | `"sm"` | Submit, Start Ingestion |
| View/Navigate | `ButtonT.ghost` | `"sm"` | View Report, Download, Back |
| "View all" section links | `ButtonT.ghost` | `"xs"` | View all →, See all |

### Don't Use Raw `Span()` for Status Badges

All status/category pill badges must use `Badge()`, `StatusBadge()`, or `PriorityBadge()` from `ui/feedback` — not raw `Span()` with hand-rolled Tailwind color classes. This ensures consistent sizing (`inline-flex items-center rounded-full border font-medium`), spacing, and color semantics. No hand-rolled `Span()` badges remain — all use `Badge()`/`StatusBadge()`/`PriorityBadge()` (including finance health tier, explore type pills, teaching status).

```python
# BAD: Hand-rolled badge with duplicated CSS
Span("Submitted", cls="bg-blue-100 text-blue-800 border border-blue-200 text-xs font-medium px-2 py-0.5 rounded-full")

# GOOD: StatusBadge for EntityStatus values (canonical colors from EntityStatus.get_badge_class())
StatusBadge("submitted")

# BAD: Custom color dict mapping statuses to Tailwind classes
_STATUS_COLORS = {"active": "bg-green-100 ...", "blocked": "bg-red-100 ..."}
Span(label, cls=_STATUS_COLORS[status])

# GOOD: Badge with variant for non-EntityStatus categories
Badge("Feedback Available", variant=BadgeT.success, size=Size.sm)
Badge("Revision Requested", variant=None, cls="bg-amber-100 text-amber-800 border-amber-200", size=Size.sm)
```

**Badge selection convention:**

| What you're displaying | Component | Example |
|---|---|---|
| EntityStatus value (active, submitted, completed, ...) | `StatusBadge(status)` | `StatusBadge("active")` |
| Priority value (high, medium, low, ...) | `PriorityBadge(priority)` | `PriorityBadge("high")` |
| Priority on an Activity card (inline-editable) | `PriorityBadgeDropdown(...)` from `ui/activities/_shared` | `PriorityBadgeDropdown(task.uid, "high", domain="tasks", singular="task")` |
| Category/type label with a BadgeT color match | `Badge(label, variant=BadgeT.xxx)` | `Badge("Ku", variant=BadgeT.accent)` |
| Category/type label with a custom color | `Badge(label, variant=None, cls="...")` | `Badge("Path Step", variant=None, cls="bg-teal-100 ...")` |

### Don't Hand-Roll Stat Grids

Statistics grids must use `StatsGrid()`/`StatItem()` from `ui/patterns/stats_grid.py` — not raw `Div()` + grid + Tailwind stat layouts. This ensures consistent card styling, trend indicators, and responsive column behavior.

```python
# BAD: Hand-rolled stat grid with duplicated layout
Div(
    Div(P("Total"), P("42", cls="text-2xl font-bold"), cls="bg-background p-4 rounded-lg"),
    Div(P("Active"), P("18", cls="text-2xl font-bold"), cls="bg-background p-4 rounded-lg"),
    cls="grid grid-cols-3 gap-4",
)

# GOOD: StatsGrid with StatItem frozen dataclass
StatsGrid([
    StatItem(label="Total", value="42"),
    StatItem(label="Active", value="18", trend="up"),
], cols=2)
```

**Adoption status:** Used across ~16 files (insights, pathways, analytics, finance, admin, profile). No hand-rolled stat grids remain.

### Don't Hand-Roll Modals

All Alpine.js-controlled modals must use `AlpineModal()` from `ui/patterns/modal.py` — not raw `Div()` with manual backdrop, `fixed inset-0`, and onclick handlers. `AlpineModal` standardizes backdrop overlay, click-outside-to-close, `x-cloak`, and transitions.

```python
# BAD: Hand-rolled modal with manual DOM removal
Div(
    Div(
        Div(*content, cls="bg-background rounded-lg p-6 max-w-md"),
        cls="fixed inset-0 flex items-center justify-center bg-black bg-opacity-50 z-50",
        onclick="if(event.target === this) document.getElementById('my-modal').remove()",
    ),
    id="my-modal",
)

# GOOD: AlpineModal with Alpine.js state
AlpineModal(
    *content,
    show="isOpen",
    close="isOpen = false",
    max_width="max-w-md",
)
```

**For HTMX-inserted modals** (server returns modal HTML), use the auto-open pattern:

```python
Div(
    AlpineModal(*content, show="open",
        close="open = false; $nextTick(() => document.getElementById('my-modal')?.remove())",
        max_width="max-w-2xl", scrollable=True),
    x_data="{ open: true }",
    id="my-modal",
)
```

**Adoption status:** Used across ~5 files (calendar, sharing, insights). No hand-rolled modals remain.

### Don't Hand-Roll Raw Utility Classes on Wrappers

```python
# BAD: Redundant - the Button component already encodes its own Tailwind classes
Button("Click", cls="bg-blue-600 text-white px-4 py-2 rounded")

# GOOD: Use the variant enum
Button("Click", cls=ButtonT.primary)
```

### Import Components from `ui.components`

```python
# GOOD: Import from SKUEL's pure-Tailwind component layer (ADR-071)
from ui.components import Button, ButtonT, Card, CardBody
from ui.primitives import ButtonLink  # A() wrapper for button-styled nav links

# BAD: monsterui no longer exists — this import fails
# from monsterui.franken import Button, ButtonT
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
# GOOD: Extra classes via cls parameter (Button merges style + extras into one cls)
Button("Full Width", cls=f"{ButtonT.primary} w-full")
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
- `/adapters/inbound/teaching_ui.py` - Hub page pattern: `/teaching` hub (BasePage) → child pages with teaching sidebar (`ui/teaching/nav.py`) + nested student hub at `/teaching/students/{uid}` (BasePage, HTMX preview blocks) → student submissions with Alpine section sidebar. All HTML construction delegated to `ui/teaching/` — routes only do auth + service call + delegation.
- `/adapters/inbound/study_ui.py` - HTMX fragments with error banners
- `/adapters/inbound/ku_ui.py` - Error state vs empty state
- `/adapters/inbound/admin_dashboard_ui.py` - Per-section partial failure banners via `tuple[data, bool]` helpers
- `/adapters/inbound/insights_ui.py` - Error state with pagination

### Activity Domain Detail Page Pattern

*Harmonized: 2026-02-07 | Updated: 2026-04-07 (route thinning rule)*

All 6 Activity Domain detail pages (`/{domain}/{uid}`) follow this pattern: **route handles auth + service call + layout assembly; non-trivial HTML is delegated to `ui/{domain}/` components**.

**Required elements:**
1. `require_authenticated_user(request)` for user_uid
2. `service.get_for_user(uid, user_uid)` for ownership-verified fetch
3. BasePage-wrapped error card on failure (not bare `Div` or `Response`)
4. HTML construction: trivial layout glue (a `Div` wrapper, `Container`/`Spacing` tokens) may remain inline; non-trivial blocks (forms, multi-section panels, display helpers) **must** go in `ui/{domain}/` — route files must not import `Form`, `Input`, `Label`, `Textarea` to build them inline
5. `Container.STANDARD` + `Spacing.PAGE` tokens on outer content Div
6. `EntityRelationshipsSection(entity_uid=..., entity_type=...)` for lateral relationships
7. `BasePage(content=content, title=..., page_type=PageType.STANDARD, request=request, active_page="{domain}")`

**Route thinning rule (2026-04-07):** A route file importing `Form`, `Input`, `Label`, or `Textarea` directly is a signal that HTML construction is leaking into routing. Extract those blocks to a `render_*` function in the domain's `ui/` package.

**Business logic extraction rule (2026-04-07; updated 2026-05-26 for ADR-044):** Raw Cypher queries, domain filtering/sorting, and workflow bucketing must not live in route or UI view files. Cross-domain connection fetching runs below the hexagonal boundary in `ConnectionFetchBackend` (`adapters/persistence/neo4j/connection_fetch_backend.py`), behind the `ConnectionFetchOperations` port — UI factories receive the port as `ActivityUIConfig.backend` and call `config.backend.fetch_entity_connections(config.connection_config, uids)`; `core/utils/connection_configs.py` holds only the pure-data `ConnectionConfig` constants. Entity filtering uses `filter_{domain}()` from `core/utils/entity_filters.py`. Domain predicate methods (`is_overdue()`, `is_keystone`, `is_upcoming()`, `is_today()`, `is_deadline_past()`) live on domain models, not as UI helpers.

**Teaching UI as canonical example:** `ui/teaching/forms.py` holds `render_feedback_submission_form()`, `render_revision_request_form()`, `render_submission_metadata()`, `render_form_responses_section()`. `teaching_ui.py` and `teaching_forms_ui.py` call these functions — they contain no inline `Form`/`Input`/`Label` construction. Dict→dataclass converters live in `ui/teaching/types.py`; submission bucketing lives in `TeacherOrchestrator.get_bucketed_student_submissions()`.

**Exercises UI as second example:** `ui/exercises/editor.py` holds `render_exercise_editor()` (the Form/Input/Label/Textarea-heavy component), `ui/exercises/detail.py` holds `render_exercise_view()` and `render_exercise_student_detail()`, `ui/exercises/cards.py` holds `render_exercises_list()` and `render_exercise_card()`. `exercises_ui.py` is ~180 lines — pure auth + service call + delegation.

**Explore UI:** `ui/explore/cards.py` holds `render_explore_card()` and `render_explore_search_panel()`. `ui/explore/filters.py` holds `filter_items()` and sort helpers. Sidebar data aggregation moved to `ExploreOrchestrator.get_sidebar_data()`. `render_explore_sidebar_page()` accepts pre-fetched `sidebar_data: dict[str, Any] | None` instead of raw services.

**LifePath UI:** `ui/lifepath/` — `dashboard.py` (dashboard content + daily focus), `vision.py` (vision form + recommendations page), `alignment.py` (5-dimension alignment dashboard), `nav.py` (sidebar items + page wrapper). `lifepath_ui.py` is ~175 lines — pure auth + service call + delegation.

**Askesis UI:** `ui/askesis/` — `welcome.py` (centered welcome + chat form), `chat.py` (message bubbles), `settings.py` (settings form), `nav.py` (sidebar items + page wrapper). Dissolved `AskesisUI` class. `askesis_ui.py` is ~168 lines.

**Activity Review UI:** `ui/activity_review/` — `cards.py` (queue items + snapshot domain cards), `forms.py` (snapshot form + feedback form with Script sync), `types.py` (domain choices config), `nav.py` (sidebar). `activity_review_ui.py` is ~266 lines.

**Analytics UI:** `ui/analytics/` — `dashboard.py` (dashboard + period fields + result rendering), `domain_metrics.py` (7 per-domain metric renderers), `life_path.py` (alignment dashboard), `life_summary.py` (weekly cross-layer summary). Dissolved `AnalyticsUIComponents` class. `analytics_ui.py` is ~167 lines.

**Ingestion UI:** `ui/ingestion/` — `dashboard.py` (form groups, ingestion cards, results display + JS handlers). `ingestion_ui.py` is ~59 lines — pure admin auth + delegation.

**System UI:** `ui/system/` — `landing.py` (login landing page with hero + form), `admin_hub.py` (admin home hub cards), `error_pages.py` (404 page). `system_ui.py` is ~73 lines — pure auth checks + delegation.

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

**Shared metadata helper:** All 6 detail views use `MetadataField(label, *value)` from `ui/activities/_shared.py` for label+value pairs in metadata grids, schedule sections, philosophical context, etc. Accepts variadic children for complex values (stars + score, lists, links).

```python
from ui.activities._shared import MetadataField
# Simple
MetadataField("Due Date", Span(str(task.due_date), cls=due_cls))
# Complex (multiple children)
MetadataField("Satisfaction",
    Span(stars, cls="text-yellow-600", style="font-size: 1.2rem;"),
    Span(f" {score}/5", cls="text-muted-foreground text-sm"),
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


**Insights** (`insights_ui.py`): Module-level `filter_insights()` and `build_filter_query_string()` helpers DRY the filtering logic shared between `insights_dashboard` and `load_more_insights` routes.

**Pattern:** Routes should only do: authenticate → parse → call service → handle error → render. Data assembly, computation, and reshaping belong in service methods. Entity filtering/sorting lives in `core/utils/entity_filters.py`, not in UI view files. Cross-domain connection fetching lives below the boundary in `ConnectionFetchBackend` (behind the `ConnectionFetchOperations` port), not in route files — `core/utils/connection_configs.py` holds only the pure-data configs.

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

Field-level constraints (`min_length`, `max_length`, required) live on the request model. Cross-field rules use `@model_validator`. Route handlers catch `PydanticValidationError` and render a user-friendly error banner — no 500s reach the user.

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

Pydantic errors surface as banners — route handlers catch validation errors:

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

### Cross-Domain Consistency Tests

`tests/unit/ui/test_cross_domain_consistency.py` verifies that all 6 activity domain views and 4 hub pages use shared components consistently. No DB, no mocks — renders components and checks output.

| Test Class | What It Catches |
|------------|----------------|
| `TestImportConsistency` | Dropped import of PageHeader, EmptyState, StatsGrid, or EntityRelationshipsSection |
| `TestEmptyStateConsistency` | `*List([])` replaced with bare `Div("No items")` instead of `EmptyState(...)` |
| `TestStatsBarConsistency` | `*StatsBar([])` using custom layout instead of `StatsGrid` |
| `TestDetailViewConsistency` | Detail view missing PageHeader or EntityRelationshipsSection |
| `TestHubPageConsistency` | Hub page (Activity, GradeBook, Library, Student) missing PageHeader |

```bash
uv run pytest tests/unit/ui/test_cross_domain_consistency.py -v
```

### Benefits

1. **Testability**: Pure functions testable without database/async
2. **Readability**: Clear separation of I/O vs computation
3. **Maintainability**: Single Responsibility Principle enforced
4. **UX**: Clear validation messages via Pydantic — caught by route handlers and rendered as error banners
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

## Shared Components

All live in `/ui/patterns/` or `/ui/feedback.py`.

| Component | Purpose | Notes |
|-----------|---------|-------|
| `PageHeader` | Page title + subtitle + actions | Adopted across all 6 Activity Domain dashboards, Study, Curriculum, Admin, Analytics, Calendar, LifePath, Finance, Pathways, Askesis, Form Submissions, Submissions, Profile, Preferences. **Never use raw `H1()`/`H2()` for page headers.** |
| `SectionHeader` | Section titles | ~8 files. **Never use raw `H2()` for section headers outside cards.** |
| `CardHeader` / `CardTitle` | Semantic card titles from `ui/cards` | **Never use raw `H2()`/`H3()` directly inside `Card()`.** Canonical pattern: `Card(CardHeader(CardTitle("…")), CardBody(content))`. |
| `EmptyState` | Empty-list placeholder | ~75 usages across ~38 files. **Never hand-roll `Div(P("No …"))` for empty states.** |
| `CardGenerator` | THE single card component | Detail cards, list cards, teaching rows, insight cards. Supports subtitle, metadata, extra, header_badges with FT pass-through. |
| `StatsGrid` / `StatItem` | Statistics grids | ~16 files. **Never hand-roll `Div()` + grid + Tailwind stat layouts.** |
| `ButtonLink` | Action CTAs | ~45 files. **Never use raw `A()` for action links.** `ButtonT.primary` for CTAs, `ButtonT.ghost` for navigation. |
| `StatusBadge` / `Badge` / `PriorityBadge` | All badges | From `ui/feedback`. **Never raw `Span()` with hand-rolled Tailwind.** `StatusBadge` for `EntityStatus` values, `Badge` for category/type pills, `PriorityBadge` for priorities. |
| `render_error_banner` / `render_inline_error` | Accessible error states | Adopted across 25+ route files. |
| `AlpineModal` | Standardized Alpine.js modal wrapper | ~5 files. **Never hand-roll modals with raw `Div()` + `fixed inset-0` + onclick handlers.** Provides backdrop, transitions, click-outside-to-close. |

---

## Page Contexts

Per-domain TypedDicts in `/ui/page_contexts.py` define route → UI contracts with typed entities (`list[Task]`, etc.) and `total=True` for required fields. `render_list_view(ctx)` is the only signature — no dual-path. **NOT in `core/ports/`** — page contexts are UI concerns.

---

## Key UI Files

**Layout & navigation:**
- `/ui/home_hub.py` — Home hub
- `/ui/layouts/base_page.py`, `/ui/layouts/navbar.py`
- `/ui/patterns/sidebar.py`, `/ui/patterns/modal.py` (AlpineModal)
- `/ui/patterns/` — `PageHeader`, `form_generator`, `card_generator`, etc.

**Explore:**
- `/ui/explore/reading_plan.py` — reading-column view for `/explore` (server-rendered; Alpine: greeting/save/disclosure/keyboard)
- `/static/js/explore-reading.js` — `exploreReading` Alpine factory
- `/ui/explore/nav.py` — graph-centered sidebar (used by `/explore/library`; KU and PS detail pages use `BasePage(CUSTOM)` with no sidebar)
- `/ui/explore/graph.py` — `ExploreGraphView` Vis.js component
- `/ui/explore/cards.py` — card rendering + search panel (library catalog)
- `/ui/explore/filters.py` — filter/sort helpers
- `/ui/explore/ku_detail.py`, `/ui/explore/ps_detail.py` — extracted from `explore_ui.py`

**Exercises & learning loop:**
- `/ui/exercises/cards.py`, `/ui/exercises/editor.py`, `/ui/exercises/detail.py`
- `/ui/learning_loop/` — exercise status pills, PS submissions/feedback renderers (shared with Library)

**Teaching:**
- `/ui/teaching/nav.py`, `/ui/teaching/student_hub.py`, `/ui/teaching/types.py`

**Domain-specific UI packages (extracted from their `*_ui.py` modules):**
- `/ui/lifepath/` (dashboard, vision form, alignment)
- `/ui/askesis/` (welcome, chat, settings)
- `/ui/activity_review/` (cards, forms, nav)
- `/ui/analytics/` (dashboard, domain_metrics, life_path, life_summary)
- `/ui/ingestion/` (ingestion dashboard)
- `/ui/system/` (landing page, admin hub, 404)
- `/ui/journals/` (cards, components, forms)
- `/ui/insights/` (components, filters, insight_card)
- `/ui/pathways/` (components)
- `/ui/notifications/` (cards)
- `/ui/calendar/` (components, converters)
- `/ui/finance/` (components, invoice_views, layout, section_views, types)
- `/ui/vault/` (sync_fragments — vault sync/preview buttons, privacy wall, consent form, stats/preview/error fragments; routes stay in `vault_routes.py`)

**Workbench:**
- `/ui/workbench/hub.py` — `SubmissionsTabPanel` (Submissions tab on `/profile`: 4 link buttons mirroring the sidebar)
- `/ui/workbench/nav.py` — Submissions sidebar

**Shared:**
- `/ui/primitives.py` — `icon_tile`, `section_label`, `primary_btn`, `card_row`, `SelectableOptionRow`, `dropdown_menu`, `dropdown_separator`, `UploadDropzone`, `SelectedFileCard`: low-level building blocks from the /submit and Askesis UX redesigns; use these instead of duplicating class strings. `SelectableOptionRow` consolidates the icon+title+subtitle+checkmark pattern (active: `bg-blue-50`, hover: `hover:bg-slate-100` live here only). `dropdown_menu`/`dropdown_separator` are the canonical Alpine dropdown shell. `UploadDropzone`/`SelectedFileCard` are the canonical drag-drop empty/filled file-upload states.
- `/ui/page_contexts.py`, `/ui/tokens.py` (spacing/layout)
- `/core/utils/palette.py` (centralized hex colors; `ui/palette.py` re-exports)
- `/core/services/visualization_service.py` (pure Chart.js/Vis.js/Gantt formatter — no domain deps; `ui/visualization/` re-exports)
- `/core/services/analytics/visualization_aggregation_service.py` (data fetching + aggregation for visualization endpoints — delegates formatting to `VisualizationService`)
- `/adapters/inbound/activity_ui_factory.py` — `ActivityUIConfig` + shared 5-route factory for all 6 Activity Domains (each `{domain}_ui.py` is ~50 lines delegating here)

---

## See Also

- `/.claude/skills/ui-css/SKILL.md` - Tailwind + `ui.components` component reference
- `/.claude/skills/fasthtml/SKILL.md` - FastHTML framework guide
- `/.claude/skills/ui-browser/SKILL.md` - HTMX + Alpine.js for UI state
- `/docs/patterns/ERROR_HANDLING.md` - Result[T] error handling
- `/docs/migrations/ACTIVITY_UI_ERROR_HANDLING_REFACTORING_2026-01-24.md` - P0 security fixes
- `/docs/migrations/ACTIVITY_UI_CODE_QUALITY_IMPROVEMENTS_2026-01-24.md` - Pure helpers & validation
- `/docs/architecture/UX_MIGRATION_PLAN.md` - Migration history
