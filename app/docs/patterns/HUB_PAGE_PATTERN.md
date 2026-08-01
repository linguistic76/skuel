---
title: "Pattern: Hub Page (MOC) Implementation"
updated: 2026-04-07
status: current
category: patterns
tags: [ui, navigation, moc, hub, cards]
related: [docs/design-principles/HUB_PAGES.md, docs/patterns/UI_COMPONENT_PATTERNS.md]
related_skills: [ui-orchestrator]
---

# Hub Page (MOC) Pattern

> Implementation guide for hub pages — entry points that organize navigation and surface live state.

For the *design rationale* (why hub pages exist), see `/docs/design-principles/HUB_PAGES.md`.
This document covers *how to build one*.

## Architecture

**`/submissions`**, **`/gradebook`**, and **`/library`** are sidebar-free MOC root pages — a 2×2 grid of icon-badge cards, each linking to a section's sidebar sub-pages. The former unified `HomeHub(active_tab=...)` tabbed hub (`ui/home_hub.py`) is retired; these three routes are now independent `BasePage(STANDARD)` pages.

**Profile** (`/profile`) is the **personal overview hub** — four tabs (Activities / Curriculum / Submissions / Reports, `?tab=` selected, default `activities`). Activities, Curriculum, and Reports show HTMX lazy-loaded preview blocks (`ACTIVITY_BLOCKS` / `LIBRARY_BLOCKS` / `GRADEBOOK_BLOCKS`); Submissions is a simple 4-button link panel (Sync first) mirroring the `/submissions` sidebar (`SubmissionsTabPanel`, `ui/workbench/hub.py`). The old intermediate hubs (`/curriculum`, `/study`) are shelved — they redirect 301 to `/profile`.

Activity Domain child pages (`/tasks`, `/goals`, etc.) use `SidebarPage` with the shared Activity sidebar, which links back to `/profile`.

**Domain hub pages** are rich functional pages that Profile links to:

| Route | Purpose | Status |
|-------|---------|--------|
| `/ku` | Knowledge browsing (ORGANIZES-driven) | Active |
| `/path-steps` | Enrolled + available path steps | Active |
| `/exercises` | Practice linked to PathSteps and Kus | Active |
| `/submissions` | Full submission list + browse | Active |
| `/entry-reports` | Teacher and AI feedback on submissions | Active |
| `/activity-reports` | Activity progress reports | Active |

Domain hubs are NOT simple card grids — they have real capabilities (forms, entity lists, actions).

## Shared Components

**Location:** `ui/patterns/hub.py`

These components are used by domain hub pages (e.g., KU index). Profile no longer uses them — it has its own live content sections.

### HubCardData

```python
@dataclass(frozen=True)
class HubCardData:
    icon: str
    name: str
    href: str
    description: str
    badge: str | int | None = None  # Optional count/label pill
```

### HubCard

```python
def HubCard(card: HubCardData) -> A:
    """Single hub card — icon + title + description + optional badge, wrapped in <A>."""
```

Renders a clickable card with icon, title, description, and optional badge pill. Badge renders only when not `None` and not `0`.

### HubSection

```python
def HubSection(title: str | None, cards: list[HubCardData], cols: int = 2) -> Div:
    """Section header + responsive card grid."""
```

- `title=None` renders grid without section header (for flat grids)
- `cols`: 2 (default), 3, or 4

### HubContainer + HubContainerGrid

```python
def HubContainer(card: HubCardData) -> A:
    """Hub container — a substantial navigational block for hub pages."""

def HubContainerGrid(cards: list[HubCardData], cols: int = 2) -> Div:
    """Responsive grid of hub containers."""
```

Bigger than `HubCard` — more padding, larger icon, full description paragraph, and arrow affordance. Reuses `HubCardData`.

### MocCard

```python
def MocCard(title: str, description: str, href: str, icon: str, icon_bg: str = "bg-muted") -> A:
    """MOC root-page card — icon tile + title + description, wrapped in <A>."""
```

Icon-tile card used by the MOC hub roots (`/library`, `/submissions`, `/gradebook`) to link their sub-pages. Takes plain args instead of `HubCardData` (needs `icon_bg`, no badge).

### HubDomainBlock + HubDomainBlockList (HTMX preview blocks)

```python
@dataclass(frozen=True)
class HubBlockData:
    label: str
    slug: str
    icon: str               # Lucide icon name (rendered via Icon)
    color: str              # hex color for header
    href: str               # "View all" link
    preview_url: str | None = None  # HTMX endpoint; None = OOB-populated by a combined endpoint

def HubDomainBlock(block: HubBlockData) -> Div:
    """Colored header + HTMX lazy-loaded preview area.

    When preview_url is set, the panel self-loads via hx-trigger="intersect once" —
    the fetch fires the first time the panel becomes visible, so blocks inside
    hidden tab containers defer until their tab is shown.
    When preview_url is None, the panel renders as a passive OOB target (id set, no HTMX
    attrs) — a combined endpoint will swap its content in via hx-swap-oob.
    """

def HubDomainBlockList(blocks: list[HubBlockData]) -> Div:
    """Vertical stack of domain blocks."""
```

Used by hub pages (`/groups`, `/activities`, `/teaching/students/{uid}`). Each block renders a colored header (icon + title + "View all" link) and an HTMX placeholder that loads preview cards when the block becomes visible. The Teaching root hub (`/teaching`) uses static `HubContainerGrid`; the nested student hub uses `HubDomainBlockList` with a mix of self-loading blocks and OOB-populated blocks (see pattern below).

### HubAccordionBlock + HubAccordionBlockList (collapsible variant)

```python
def HubAccordionBlock(block: HubBlockData, open: bool = False) -> FT:
    """Collapsible domain block — native <details>/<summary>."""

def HubAccordionBlockList(blocks: list[HubBlockData], open_first: bool = True) -> Div:
    """Vertical stack of accordion blocks; the first starts open by default."""
```

Same `HubBlockData` config as `HubDomainBlock`, rendered as a native `<details>` element: the whole summary row toggles (chevron rotates via `group-open:rotate-90`, pure CSS), the label is a plain Span, and "View all →" is the sole navigation (`@click.stop` so it doesn't toggle). Because the preview panel uses `hx-trigger="intersect once"`, a closed accordion never fetches — content inside a closed `<details>` has no layout box, so the IntersectionObserver only fires once the section is open AND its tab visible. Used by the `/profile` Curriculum and Reports tabs.

**Decision guide — flat vs accordion:**

| Situation | Use |
|-----------|-----|
| Few blocks, all previews should be visible immediately | `HubDomainBlockList` |
| Many sections where headers alone orient the user; open on demand | `HubAccordionBlockList` |
| Blocks populated by a combined OOB endpoint (e.g. teaching student hub) | `HubDomainBlockList` — the OOB response would populate closed panels invisibly and skew the one-combined-fetch economics |

---

## Pattern: OOB Swaps for Shared-Data Hub Blocks

**Rule: When multiple hub blocks load from the same data source, use one combined endpoint with HTMX OOB swaps — not N independent endpoints.**

### The Problem It Solves

The naive implementation of a hub with N blocks fires N independent HTMX requests on page load. When those blocks all need the same underlying data (e.g., all three submission-status buckets come from one `get_student_submissions()` DB query), you end up with N identical round-trips:

```
Page load →
  GET /api/.../pending/preview   → DB query A
  GET /api/.../revision/preview  → DB query A  (duplicate!)
  GET /api/.../completed/preview → DB query A  (duplicate!)
```

With OOB swaps, this collapses to one:

```
Page load →
  GET /api/.../submissions/preview → DB query A → 3 OOB fragments returned
```

### How HTMX OOB Swaps Work

HTMX normally puts a server response into the element that made the request (the "main swap target"). Out-of-band (OOB) swaps are additional elements in the same response that get routed to *different* DOM elements by matching their `id`.

HTMX's rule: any element in the response that has `hx-swap-oob="true"` is pulled out and swapped into the element on the page that has the same `id`. The main swap target can be `hx-swap="none"` — meaning the request itself has no primary target at all, its only purpose is to deliver OOB fragments.

```html
<!-- Page has 3 passive target divs (no hx-* attrs, just IDs): -->
<div id="hub-panel-pending">Loading...</div>
<div id="hub-panel-revision">Loading...</div>
<div id="hub-panel-completed">Loading...</div>

<!-- One hidden trigger fires on load, main swap is "none": -->
<div hx-get="/api/students/{uid}/submissions/preview"
     hx-trigger="load"
     hx-swap="none">
</div>

<!-- Server response contains 3 OOB fragments: -->
<div id="hub-panel-pending"  hx-swap-oob="true">...pending cards...</div>
<div id="hub-panel-revision" hx-swap-oob="true">...revision cards...</div>
<div id="hub-panel-completed" hx-swap-oob="true">...completed cards...</div>
```

HTMX matches each response fragment to its page target by `id` and swaps them in. The trigger div itself swaps nothing (`hx-swap="none"`).

### SKUEL Implementation

**Two established examples:**

1. **Sidebar badges** (`user_profile_ui.py:363`) — `GET /api/sidebar/badges` returns 9 badge spans (activity + curriculum domains) as OOB swaps. The sidebar renders each badge placeholder with its `id`; a single hidden trigger on the sidebar fires once on load.

2. **StudentHub submission blocks** (`teaching_ui.py`) — `GET /api/teaching/students/{uid}/submissions/preview` returns 3 bucket previews (pending, revision, completed) as OOB swaps. One orchestrator fetch, three panels populated. Bucketing logic lives in `TeacherOrchestrator.get_bucketed_student_submissions()` — Needs Review AND Revision Requested are each the student-scoped review queue (default statuses vs `revision_requested` — one collapse rule, two surfaces), never raw status reads; anything both queues omit is history.

**Combined endpoint pattern (FastHTML):**

```python
@rt("/api/teaching/students/{uid}/submissions/preview")
@require_role(UserRole.TEACHER, get_user_service)
async def student_submissions_preview(request, uid, current_user=None):
    """OOB fragment: all 3 submission bucket previews in one DB round-trip."""
    user_uid = require_authenticated_user(request)
    # Orchestrator returns bucketed raw dicts; route converts to SubmissionRow view models
    pending, revision, completed, _ = await _get_bucketed_submissions(user_uid, uid)

    def _make_fragment(slug, rows, empty_label):
        content = HubPreviewGrid([...]) if rows else HubPreviewEmpty(empty_label)
        return Div(content, id=f"hub-panel-{slug}", hx_swap_oob="true")

    return Div(
        _make_fragment("pending",  pending,   "submissions needing review"),
        _make_fragment("revision", revision,  "revision requests"),
        _make_fragment("completed", completed, "completed submissions"),
    )
```

**Hub component wiring (FastHTML):**

```python
def StudentHub(student_name, student_uid):
    base_api = f"/api/teaching/students/{student_uid}"

    blocks = [
        HubBlockData(..., slug="pending",   preview_url=None),  # OOB target
        HubBlockData(..., slug="revision",  preview_url=None),  # OOB target
        HubBlockData(..., slug="completed", preview_url=None),  # OOB target
        HubBlockData(..., slug="ku", preview_url=f"{base_api}/ku/preview"),  # independent
    ]

    # Hidden div fires combined endpoint; hx_swap="none" because all updates are OOB
    oob_trigger = Div(
        hx_get=f"{base_api}/submissions/preview",
        hx_trigger="load",
        hx_swap="none",
    )

    return Div(oob_trigger, HubDomainBlockList(blocks))
```

**Key implementation notes:**
- Set `preview_url=None` on blocks that will be OOB-populated — `HubDomainBlock` renders them without HTMX attrs (just `id`), making them passive targets.
- Independent blocks (different data source, like KU progress) keep their own `preview_url` and self-load normally. Mix both patterns on the same hub freely.
- The combined endpoint returns `Div(*fragments)` — the outer `Div` is the main swap target (swapped into the trigger div, immediately discarded since `hx_swap="none"`); only the inner OOB fragments matter.
- Each OOB fragment needs `id=f"hub-panel-{slug}"` matching the IDs rendered by `HubDomainBlock`.

### Decision Guide: Independent loads vs OOB

| Situation | Use |
|-----------|-----|
| Each block has a different service/DB call | Independent `preview_url` on each block |
| 2+ blocks share the same DB query | OOB combined endpoint, `preview_url=None` on shared blocks |
| Mix of shared + independent | OOB trigger for the shared group + `preview_url` on independent blocks |

**See also:** `ui-browser` skill → "HTMX: Out-of-Band (OOB) Swaps" for the HTMX mechanics.

### HubPreviewCard + HubPreviewGrid + HubPreviewEmpty

```python
def HubPreviewCard(
    title: str, href: str, badge: FT | None = None, description: str | None = None
) -> A:
    """Compact preview card — entity title first, optional description snippet
    (line-clamp-2) and badge in a meta row below."""

def HubPreviewGrid(cards: list[A]) -> Div:
    """3-column grid of preview cards."""

def HubPreviewEmpty(domain: str) -> Div:
    """Empty state for a preview block."""
```

Returned by HTMX preview endpoints to populate `HubDomainBlock`/`HubAccordionBlock` areas. The entity title is the card's headline — don't lead with a badge that repeats the section header; reserve `badge` for genuinely informative status (submission state, media type, revision number).

### Graph-Driven Bridges

```python
def hub_cards_from_organizers(
    children: list[OrganizerResult],
    href_template: str = "/ku/{uid}",
    default_icon: str = "📖",
    default_description: str = "",
    href_for: Callable[[OrganizerResult], str] | None = None,
) -> list[HubCardData]:

def hub_cards_from_root_organizers(
    roots: list[RootOrganizerResult],
    href_template: str = "/ku/{uid}",
    default_icon: str = "📖",
    default_description: str = "",
) -> list[HubCardData]:
```

Convert ORGANIZES query results into `HubCardData` for rendering. `RootOrganizerResult.child_count` maps to badge. `href_for` overrides `href_template` when children span entity types (`OrganizerResult.entity_type` + `entity_detail_href()` from `ui/patterns/entity_links.py` resolve the per-type detail URL).

## Usage: Profile Hub (Personal Overview)

Profile renders via `ProfileHubView(active_tab)` — no UserContext on the critical path. The route only calls `require_authenticated_user(request)` for auth, then renders the tab layout directly.

`personal_header(context)` (Focus + Velocity) lives in `ui/patterns/personal_header.py` and is used on `/home` and the HTMX fragment endpoint (`GET /api/personal-header`). For pages that don't already have `UserContext` loaded, use `personal_header_placeholder()` — an HTMX div that lazy-loads without blocking the page render. The endpoint is registered in `adapters/inbound/home_routes.py`.

## Usage: HTMX Hub Pages (Activity, GradeBook, Library, Submissions)

All hub pages use `HubDomainBlockList` with `HubBlockData` config. Each block loads content via HTMX from its `preview_url`. Preview endpoints typically return `HubPreviewGrid(cards)` or `HubPreviewEmpty(domain)` for data blocks, or an embedded action widget (e.g. a form) for action-first blocks like the Submissions upload block.

### Activities tab (on `/profile`)

```python
# ui/activities/hub.py
ACTIVITY_BLOCKS = [
    HubBlockData("Tasks", "tasks", "check-square", "#3B82F6", "/tasks", "/api/profile/tasks/preview"),
    # ... 5 more Activity Domains
]

# ui/profile/hub.py renders it as an accordion tab panel:
_panel("activities", HubAccordionBlockList(ACTIVITY_BLOCKS))
```

### MOC root pages (`/submissions`, `/gradebook`, `/library`)

Each is a `BasePage(STANDARD)` with a `grid grid-cols-1 sm:grid-cols-2` of `MocCard()` components (shared, in `ui/patterns/hub.py`). No sidebar, no Alpine state. Routes in:

- `adapters/inbound/user_entry_ui.py` — `submissions_moc` and `gradebook_moc`
- `adapters/inbound/library_ui.py` — `library_moc`

**HTMX preview endpoints** (still used by profile and teaching hubs):
- Activity: `/api/profile/{slug}/preview` (6 domains, in `user_profile_ui.py`)
- Library: `/api/library/{section}/preview` (4 sections, in `library_ui.py`, wired via `library_routes.py`)
- GradeBook: `/api/gradebook/{section}/preview` (3 sections, split across `entry_reports_ui.py`, `activity_reports_ui.py`, `revised_exercises_ui.py`)
- Submissions: `/api/submissions/{section}/preview` (3 sections in `user_entry_ui.py`)
- Student hub: `/api/teaching/students/{uid}/submissions/preview` (OOB) + `/api/teaching/students/{uid}/ku/preview` (in `teaching_ui.py`)

## Usage: Graph-Driven Hub Page

Any route handler can render ORGANIZES data as a card grid:

```python
children_result = await ku_service.get_organized_children(moc_uid)
cards = hub_cards_from_organizers(children_result.value)
section = HubSection("Contents", cards)
```

Live consumer: `/gradebook/{uid}` (`submission_detail` in `user_entry_ui.py`) renders an owned user entry's ORGANIZES children as a "Map of Content" `HubSection` — children span entity types, so it passes `href_for` backed by `entity_detail_href()`.

**Flow:** Navbar icon → hub page (`BasePage(STANDARD)`, no sidebar) → click "View all" or preview card → child page (`SidebarPage`). Sidebar title links back to hub. Activity Domains live on the `/profile` Activities tab (accordion blocks, `ACTIVITY_BLOCKS`).

**Files:** `ui/gradebook/hub.py` (`GRADEBOOK_BLOCKS`), `ui/library/hub.py` (`LIBRARY_BLOCKS`), `ui/workbench/hub.py` (`SubmissionsTabPanel`), `ui/activities/hub.py` (`ACTIVITY_BLOCKS`, Activities tab on `/profile`), `ui/teaching/hub.py` (hub views), `ui/gradebook/nav.py`, `ui/library/nav.py`, `ui/workbench/nav.py`, `ui/activities/nav.py`, `ui/teaching/nav.py` (sidebar nav for children). Teaching also has a nested student hub: `ui/teaching/student_hub.py`.

## Retired Hubs

| Old Route | Replaced By |
|-----------|-------------|
| `/curriculum` | `/profile` (301 redirect) |
| `/study` | `/profile` (301 redirect) |
| `/activities` | — (no redirect, route deleted; content lives on the `/profile` Activities tab) |
| `HomeHub(active_tab=...)` | Three independent MOC root pages (`/submissions`, `/gradebook`, `/library`) |

## File Locations

| Concern | File |
|---------|------|
| Shared components | `ui/patterns/hub.py` |
| Profile hub | `ui/profile/hub.py` |
| Profile routes | `adapters/inbound/user_profile_ui.py` |
| Activity blocks + preview renderer | `ui/activities/hub.py` (Activities tab on `/profile`) |
| Activity hub redirect | — (removed; `/activities` route no longer exists) |
| Activity sidebar | `ui/activities/nav.py` |
| MOC root pages | `adapters/inbound/user_entry_ui.py` (`submissions_moc`, `gradebook_moc`), `adapters/inbound/library_ui.py` (`library_moc`) |
| GradeBook block definitions | `ui/gradebook/hub.py` (`GRADEBOOK_BLOCKS`, used by HTMX previews) |
| GradeBook sidebar | `ui/gradebook/nav.py` |
| Library block definitions | `ui/library/hub.py` (`LIBRARY_BLOCKS`) |
| Library sidebar | `ui/library/nav.py` |
| Submissions block definitions | `ui/workbench/hub.py` (`SUBMISSIONS_BLOCKS`) |
| Submissions sidebar | `ui/workbench/nav.py` |
| Submissions routes | `adapters/inbound/user_entry_ui.py` |
| Teaching hub view | `ui/teaching/hub.py` |
| Teaching sidebar | `ui/teaching/nav.py` |
| Student hub view | `ui/teaching/student_hub.py` |
| Design rationale | `docs/design-principles/HUB_PAGES.md` |
| Base page wrapper | `ui/layouts/base_page.py` |

## See Also

- `/docs/design-principles/HUB_PAGES.md` — why hub pages exist
- `/docs/patterns/UI_COMPONENT_PATTERNS.md` — broader UI patterns
- `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` — MOC as graph pattern
