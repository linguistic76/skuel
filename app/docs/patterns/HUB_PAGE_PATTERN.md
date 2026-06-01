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

**Home** (`/home`) is the **post-login landing hub** — a three-tab interface (Submissions / GradeBook / Library) with HTMX-loaded domain blocks per tab and a Settings footer. `/submissions`, `/gradebook`, and `/library` render the same `HomeHub(active_tab=...)` with the matching tab pre-selected. Hub view in `ui/home_hub.py`.

**Profile** (`/profile`) is the **personal overview hub** — Focus/Velocity indicators, Activity Domains (6 HTMX lazy-loaded preview blocks inline), the Nous community feed placeholder, and Settings. The old intermediate hubs (`/curriculum`, `/study`) are shelved — they redirect 301 to `/profile`.

Activity Domain child pages (`/tasks`, `/goals`, etc.) use `SidebarPage` with the shared Activity sidebar, which links back to `/profile`.

**Domain hub pages** are rich functional pages that Profile links to:

| Route | Purpose | Status |
|-------|---------|--------|
| `/ku` | Knowledge browsing (ORGANIZES-driven) | Active |
| `/path-steps` | Enrolled + available path steps | Active |
| `/exercises` | Practice linked to PathSteps and Kus | Active |
| `/submissions` | Full submission list + browse | Active |
| `/exercise-reports` | Teacher and AI feedback on submissions | Active |
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

### HubDomainBlock + HubDomainBlockList (HTMX preview blocks)

```python
@dataclass(frozen=True)
class HubBlockData:
    label: str
    slug: str
    icon: str               # Feather icon name (UkIcon)
    color: str              # hex color for header
    href: str               # "View all" link
    preview_url: str | None = None  # HTMX endpoint; None = OOB-populated by a combined endpoint

def HubDomainBlock(block: HubBlockData) -> Div:
    """Colored header + HTMX lazy-loaded preview area.

    When preview_url is set, the panel self-loads on page render via hx-trigger="load".
    When preview_url is None, the panel renders as a passive OOB target (id set, no HTMX
    attrs) — a combined endpoint will swap its content in via hx-swap-oob.
    """

def HubDomainBlockList(blocks: list[HubBlockData]) -> Div:
    """Vertical stack of domain blocks."""
```

Used by hub pages (`/profile`, `/gradebook`, `/library`, `/teaching/students/{uid}`). Each block renders a colored header (icon + title + "View all" link) and an HTMX placeholder that loads preview cards on page load. The Teaching root hub (`/teaching`) uses static `HubContainerGrid`; the nested student hub uses `HubDomainBlockList` with a mix of self-loading blocks and OOB-populated blocks (see pattern below).

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

2. **StudentHub submission blocks** (`teaching_ui.py`) — `GET /api/teaching/students/{uid}/submissions/preview` returns 3 bucket previews (pending, revision, completed) as OOB swaps. One DB call, three panels populated. Bucketing logic lives in `TeacherOrchestrator.get_bucketed_student_submissions()`.

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
def HubPreviewCard(title: str, href: str, badge: FT | None = None) -> A:
    """Compact preview card — title + optional badge."""

def HubPreviewGrid(cards: list[A]) -> Div:
    """3-column grid of preview cards."""

def HubPreviewEmpty(domain: str) -> Div:
    """Empty state for a preview block."""
```

Returned by HTMX preview endpoints to populate `HubDomainBlock` areas.

### Graph-Driven Bridges

```python
def hub_cards_from_organizers(
    children: list[OrganizerResult],
    href_template: str = "/ku/read?uid={uid}",
    default_icon: str = "📖",
    default_description: str = "",
) -> list[HubCardData]:

def hub_cards_from_root_organizers(
    roots: list[RootOrganizerResult],
    href_template: str = "/ku/read?uid={uid}",
    default_icon: str = "📖",
    default_description: str = "",
) -> list[HubCardData]:
```

Convert ORGANIZES query results into `HubCardData` for rendering. `RootOrganizerResult.child_count` maps to badge.

## Usage: Profile Hub (Personal Overview)

Profile renders personal state from `UserContext`:

```python
def ProfileHubView(context: UserContext) -> Div:
    return Div(
        personal_header(context),           # Focus + Velocity (shared component)
        ActivityHubView(),                  # 6 Activity Domain preview blocks (inline)
    )
```

`personal_header(context)` requires a `UserContext` already in scope (use on `/profile` and the HTMX fragment endpoint). For pages that load `UserContext` only for the header, use `personal_header_placeholder()` instead — it renders an HTMX div that lazy-loads via `GET /api/personal-header` without blocking the page render. Both are defined in `ui/patterns/personal_header.py`; the endpoint is registered in `adapters/inbound/home_routes.py`.

## Usage: HTMX Hub Pages (Activity, GradeBook, Library, Submissions)

All hub pages use `HubDomainBlockList` with `HubBlockData` config. Each block loads content via HTMX from its `preview_url`. Preview endpoints typically return `HubPreviewGrid(cards)` or `HubPreviewEmpty(domain)` for data blocks, or an embedded action widget (e.g. a form) for action-first blocks like the Submissions upload block.

### Activity hub (inline in `/profile`)

```python
# ui/activities/activity_hub.py
_ACTIVITY_BLOCKS = [
    HubBlockData("Tasks", "tasks", "check-square", "#3B82F6", "/tasks", "/api/profile/tasks/preview"),
    # ... 5 more Activity Domains
]

def ActivityHubView() -> Div:
    return Div(PageHeader(...), HubDomainBlockList(_ACTIVITY_BLOCKS))
```

### Unified tabbed hub (`/home`, `/submissions`, `/gradebook`, `/library`)

`HomeHub(active_tab)` in `ui/home_hub.py` renders all three tab panels using the `*_BLOCKS` constants:

```python
# *_BLOCKS constants (no hub functions — just data):
# ui/workbench/hub.py  → SUBMISSIONS_BLOCKS (2 blocks)
# ui/gradebook/hub.py  → GRADEBOOK_BLOCKS (3 blocks)
# ui/library/hub.py    → LIBRARY_BLOCKS (5 blocks)

def HomeHub(active_tab: str = "submissions") -> Div:
    """x-data initializes with active_tab; all three panels rendered, x-show controls visibility."""
```

**Preview endpoints:**
- Activity: `/api/profile/{slug}/preview` (6 domains, in `user_profile_ui.py`)
- Library: `/api/library/{section}/preview` (4 sections, in `library_ui.py`, wired via `library_routes.py`)
- GradeBook: `/api/gradebook/{section}/preview` (3 sections, split across `user_entry_ui.py`, `exercise_reports_ui.py`, `activity_reports_ui.py`)
- Submissions: `/api/submissions/{section}/preview` (2 sections: upload, submit — in `user_entry_ui.py`); history preview served via `/api/submissions/history/preview` (rendered in Library tab)
- Student hub: `/api/teaching/students/{uid}/submissions/preview` (OOB — 3 buckets in one call) + `/api/teaching/students/{uid}/ku/preview` (independent — in `teaching_ui.py`)

## Usage: Graph-Driven Hub Page

Any route handler can render ORGANIZES data as a card grid:

```python
children_result = await ku_service.get_organized_children(moc_uid)
cards = hub_cards_from_organizers(children_result.value)
section = HubSection("Contents", cards)
```

**Flow:** Navbar icon → hub page (`BasePage(STANDARD)`, no sidebar) → click "View all" or preview card → child page (`SidebarPage`). Sidebar title links back to hub. Activity Domains are embedded inline in `/profile` via `ActivityHubView()`.

**Files:** `ui/home_hub.py` (unified tabbed hub — `HomeHub(active_tab)`), `ui/gradebook/hub.py` (`GRADEBOOK_BLOCKS`), `ui/library/hub.py` (`LIBRARY_BLOCKS`), `ui/workbench/hub.py` (`SUBMISSIONS_BLOCKS`), `ui/activities/activity_hub.py` (used inline in `/profile`), `ui/teaching/hub.py` (hub views), `ui/gradebook/nav.py`, `ui/library/nav.py`, `ui/workbench/nav.py`, `ui/activities/nav.py`, `ui/teaching/nav.py` (sidebar nav for children). Teaching also has a nested student hub: `ui/teaching/student_hub.py`.

## Retired Hubs

| Old Route | Replaced By |
|-----------|-------------|
| `/curriculum` | `/profile` (301 redirect) |
| `/study` | `/profile` (301 redirect) |
| `/activities` | — (no redirect, route deleted; content lives in `/profile`) |

## File Locations

| Concern | File |
|---------|------|
| Shared components | `ui/patterns/hub.py` |
| Profile hub | `ui/profile/hub.py` |
| Profile routes | `adapters/inbound/user_profile_ui.py` |
| Activity hub view | `ui/activities/activity_hub.py` (embedded in `/profile`) |
| Activity hub redirect | — (removed; `/activities` route no longer exists) |
| Activity sidebar | `ui/activities/nav.py` |
| Unified tabbed hub | `ui/home_hub.py` (`HomeHub(active_tab)`) |
| GradeBook block definitions | `ui/gradebook/hub.py` (`GRADEBOOK_BLOCKS`) |
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
