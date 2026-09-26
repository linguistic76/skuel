---
title: "Pattern: Hub Page (MOC) Implementation"
updated: 2026-09-22
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

## Related Skills

For implementation guidance, see:
- [@ui-orchestrator](../../.claude/skills/ui-orchestrator/SKILL.md)

## Architecture

Sections are navigated by the chrome — one door per section in the navbar/bottom nav, the section's pages as sidebar rows (`SidebarPage`, a collapsible sidebar at `lg+` and the scrolling section nav below). A hub page is built only where it carries what that nav cannot (the design principle's table). Four live hub forms:

| Route | Hub form | Built from |
|-------|----------|-----------|
| `/submissions` | MOC root — sidebar-free `BasePage(STANDARD)`, five `MocCard`s (Sync, Exercise, Journal, History, Knowledge) | `adapters/inbound/user_entry_ui.py` (`submissions_moc`) |
| `/library` | MOC root — four `MocCard`s (Exercises, Resources, Ku, Path Steps) | `adapters/inbound/library_ui.py` (`library_moc`) |
| `/groups` | one `HubDomainBlock` per group, each HTMX-loading a "Recent Shares" preview (the Shared page's reader, `get_shared_with_me(via=group_uid)`) | `ui/groups/hub.py`, `adapters/inbound/groups_hub_routes.py` |
| `/teaching/students/{uid}` | nested student hub — `HubDomainBlockList`, three OOB-populated buckets + one self-loading block | `ui/teaching/student_hub.py`, `adapters/inbound/teaching_ui.py` |

Plus one graph-driven section: `/gradebook/{uid}` renders an entry's `ORGANIZES` children as a "Map of Content" `HubSection`.

Tasks+ has no hub — its sidebar (`ui/activities/nav.py`) is the one list on every page under it, and the Tasks+ door (→ `/today`) is lit on all of them. `/gradebook` is a Tasks+ page (the received-feedback exchange lines, GradeBook row lit), not a hub. Teaching has no root hub (`/teaching/students` is its landing).

## Shared Components

**Location:** `ui/patterns/hub.py`

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

### MocCard

```python
def MocCard(title: str, description: str, href: str, icon: str, icon_bg: str = "bg-muted") -> A:
    """MOC root-page card — icon tile + title + description, wrapped in <A>."""
```

Icon-tile card used by the MOC roots (`/library`, `/submissions`) to link their sub-pages. Takes plain args instead of `HubCardData` (needs `icon_bg`, no badge).

### HubDomainBlock + HubDomainBlockList (HTMX preview blocks)

```python
@dataclass(frozen=True)
class HubBlockData:
    label: str
    slug: str
    icon: str               # Lucide icon name (rendered via Icon)
    color: str              # hex color for header
    href: str               # Header label link (primary action)
    preview_url: str | None = None  # HTMX endpoint; None = OOB-populated by a combined endpoint
    view_all_href: str | None = None  # Override for "View all →"; falls back to href

def HubDomainBlock(block: HubBlockData) -> Div:
    """A single domain block: colored header + HTMX lazy-loaded preview area."""

def HubDomainBlockList(blocks: list[HubBlockData]) -> Div:
    """Vertical stack of domain blocks."""
```

Each block renders a colored header (icon + title + "View all →") and a preview panel. When `preview_url` is set the panel self-loads with `hx-trigger="intersect once"` — the fetch fires the first time the panel gains a layout box in the viewport, so a block inside a hidden container defers until revealed. When `preview_url` is `None` the panel is a passive OOB target (`id` set, no HTMX attributes) that a combined endpoint fills via `hx-swap-oob` (pattern below). Consumers: `/groups` (one block per group) and the nested student hub `/teaching/students/{uid}` (three OOB buckets + one self-loading block).

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
<div hx-get="/api/teaching/students/{uid}/submissions/preview"
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

1. **Sidebar badges** (`adapters/inbound/sidebar_badges_ui.py`) — `GET /api/sidebar/badges` returns one badge span per Tasks+ domain row (`ACTIVITY_SIDEBAR_ITEMS ∩ DOMAIN_STATS_CONFIG`, six today) as OOB swaps. Only the Tasks+ sidebar (`SidebarPage(badges=True)`) renders the `sidebar-badge-{slug}` slots and carries the trigger, which fires once the desktop sidebar is on screen (`intersect once`) — a phone, where the sidebar is `display:none`, makes no request.

2. **StudentHub submission blocks** (`teaching_ui.py`) — `GET /api/teaching/students/{uid}/submissions/preview` returns 3 bucket previews (pending, revision, completed) as OOB swaps. One orchestrator fetch, three panels populated. Bucketing logic lives in `TeacherOrchestrator.get_bucketed_student_submissions()` — Needs Review AND Revision Requested are each the student-scoped review queue (default statuses vs `revision_requested` — one collapse rule, two surfaces), never raw status reads; anything both queues omit is history.

**Combined endpoint pattern (FastHTML):**

```python
@rt("/api/teaching/students/{uid}/submissions/preview")
@require_role(UserRole.TEACHER, get_user_service)
async def student_submissions_preview(request: Request, uid: str, current_user: Any = None):
    """OOB fragment: all 3 submission bucket previews in one DB round-trip."""
    user_uid = UserUID(current_user.uid)  # the decorator authenticated and fetched the caller
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

Returned by HTMX preview endpoints to populate `HubDomainBlock` panels. The entity title is the card's headline — don't lead with a badge that repeats the section header; reserve `badge` for genuinely informative status (submission state, media type, revision number).

### Graph-Driven Bridges

```python
def hub_cards_from_organizers(
    children: list[OrganizerResult],
    href_template: str = "/explore/ku/{uid}",
    default_icon: str = "📖",
    default_description: str = "",
    href_for: Callable[[OrganizerResult], str] | None = None,
) -> list[HubCardData]:
```

Converts ORGANIZES query results into `HubCardData` for rendering, sorted by `order`. `href_for` overrides `href_template` when children span entity types (`OrganizerResult.entity_type` + `entity_detail_href()` from `ui/patterns/entity_links.py` resolve the per-type detail URL).

## Usage: MOC Root Pages (`/submissions`, `/library`)

Each is a `BasePage(STANDARD)` with a `grid grid-cols-1 sm:grid-cols-2` of `MocCard()` components. No sidebar, no Alpine state. Routes:

- `adapters/inbound/user_entry_ui.py` — `submissions_moc`
- `adapters/inbound/library_ui.py` — `library_moc`

The child pages render under the section's `SidebarPage` (`ui/workbench/nav.py`, `ui/library/nav.py`), whose `title_href` links back to the root.

## Usage: HTMX Hub Pages (`/groups`, the student hub)

Blocks are `HubBlockData` configs rendered by `HubDomainBlock`; each loads its content via HTMX from `preview_url` (or is filled by a combined OOB endpoint). Preview endpoints return `HubPreviewGrid(cards)` or `HubPreviewEmpty(domain)`.

**HTMX preview endpoints:**
- Groups: `/api/groups/{group_uid}/shared/preview` (`groups_hub_routes.py`)
- Student hub: `/api/teaching/students/{uid}/submissions/preview` (OOB, three buckets) + `/api/teaching/students/{uid}/ku/preview` (`teaching_ui.py`)

`personal_header(context)` (Focus + Velocity, `ui/patterns/personal_header.py`) is not a hub component: pages that lack a loaded `UserContext` use `personal_header_placeholder()`, an HTMX div that lazy-loads from `GET /api/personal-header` (`adapters/inbound/home_routes.py`) without blocking the page render.

## Usage: Graph-Driven Hub Page

`hub_cards_from_organizers` renders any `OrganizerResult` list as a card grid.
The fetch is per-subject, and only two subject types have a service reader:
PathStep (`PsService.get_organized_children`) and UserEntry (via the
orchestrator below). Every other entity type — Ku included — can carry
vault-authored ORGANIZES edges with no dedicated reader above the backend:

```python
children_result = await orchestrator.get_entry_organized_children(entry_uid)
if children_result.is_error:
    # A failed fetch must not masquerade as "not a MOC" — surface it.
    return render_inline_error(children_result.expect_error().message)
section = HubSection("Contents", hub_cards_from_organizers(children_result.value))
```

Live consumer: `/gradebook/{uid}` (`submission_detail` in `user_entry_ui.py`) renders an owned user entry's ORGANIZES children as a "Map of Content" `HubSection` — children span entity types, so it passes `href_for` backed by `entity_detail_href()`.

**Flow:** section door in the chrome → the section's landing (a MOC root for Library and Submissions; `/today` for Tasks+) → a child page under the section's `SidebarPage`. The sidebar's `title_href` links back to the root. The former hub pages are gone with no redirects — no `/profile`, no `/home`, no `/curriculum`, no `/study`, no `/activities` (the record is `docs/roadmap/done/tasks-plus-one-chrome.md`).

## File Locations

| Concern | File |
|---------|------|
| Shared components | `ui/patterns/hub.py` |
| Chrome spec (section doors, role doors) | `ui/layouts/nav_config.py`; rendered by `ui/layouts/navbar.py` |
| Sidebar + section nav | `ui/patterns/sidebar.py` |
| Tasks+ sidebar | `ui/activities/nav.py` (`ACTIVITY_SIDEBAR_ITEMS`, `render_activity_sidebar_page`) |
| Sidebar badges endpoint | `adapters/inbound/sidebar_badges_ui.py` (`/api/sidebar/badges`); extractors in `ui/activities/domain_stats_config.py` |
| MOC root pages | `adapters/inbound/user_entry_ui.py` (`submissions_moc`), `adapters/inbound/library_ui.py` (`library_moc`) |
| Library sidebar | `ui/library/nav.py` |
| Submissions sidebar | `ui/workbench/nav.py` |
| Groups hub | `ui/groups/hub.py`, `adapters/inbound/groups_hub_routes.py` |
| Teaching sidebar | `ui/teaching/nav.py` (no root hub — `/teaching/students` is the landing) |
| Student hub view | `ui/teaching/student_hub.py` |
| Shared-with-me inbox | `ui/profile/shared_view.py`, `adapters/inbound/user_profile_ui.py` (`/profile/shared` — the one `/profile/*` route) |
| Design rationale | `docs/design-principles/HUB_PAGES.md` |
| Base page wrapper | `ui/layouts/base_page.py` |

## See Also

- `/docs/design-principles/HUB_PAGES.md` — why hub pages exist
- `/docs/patterns/UI_COMPONENT_PATTERNS.md` — broader UI patterns
- `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` — MOC as graph pattern
- `/docs/roadmap/done/tasks-plus-one-chrome.md` — the arc that retired the `/profile` hub and made the chrome one navigation
