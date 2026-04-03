---
title: "Pattern: Hub Page (MOC) Implementation"
updated: 2026-04-03
status: current
category: patterns
tags: [ui, navigation, moc, hub, cards]
related: [docs/design-principles/HUB_PAGES.md, docs/patterns/UI_COMPONENT_PATTERNS.md]
---

# Hub Page (MOC) Pattern

> Implementation guide for hub pages — entry points that organize navigation and surface live state.

For the *design rationale* (why hub pages exist), see `/docs/design-principles/HUB_PAGES.md`.
This document covers *how to build one*.

## Architecture

**Profile is the personal overview hub** (`/profile`). It shows Focus/Velocity indicators, a link card to `/activities`, the Nous community feed placeholder, and Settings. The old intermediate hubs (`/curriculum`, `/study`) are shelved — they redirect 301 to `/profile`.

**Activity Domains hub** (`/activities`) shows all 6 Activity Domains as HTMX lazy-loaded preview blocks. No sidebar — uses `BasePage(STANDARD)`. Child pages (`/tasks`, `/goals`, etc.) use `SidebarPage` with the shared Activity sidebar.

**Domain hub pages** are rich functional pages that Profile links to:

| Route | Purpose | Status |
|-------|---------|--------|
| `/ku` | Knowledge browsing (ORGANIZES-driven) | Active |
| `/lessons` | Enrolled + available lessons | Active |
| `/exercises` | Practice linked to lessons and Kus | Active |
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
    icon: str        # Feather icon name (UkIcon)
    color: str       # hex color for header
    href: str        # "View all" link
    preview_url: str # HTMX endpoint

def HubDomainBlock(block: HubBlockData) -> Div:
    """Colored header + HTMX lazy-loaded preview area."""

def HubDomainBlockList(blocks: list[HubBlockData]) -> Div:
    """Vertical stack of domain blocks."""
```

Used by hub pages (`/activities`, `/gradebook`, `/library`, `/teaching/students/{uid}`). Each block renders a colored header (icon + title + "View all" link) and an HTMX placeholder that loads preview cards on page load. The Teaching root hub (`/teaching`) uses static `HubContainerGrid`; the nested student hub uses `HubDomainBlockList` with per-student preview endpoints.

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
        _personal_header(context),          # Focus + Velocity indicators
        _activity_link(),                   # Link card to /activities
        _nous_section(),                    # Community feed (placeholder)
        _settings_link(),
    )
```

## Usage: HTMX Hub Pages (Activity, GradeBook, Library)

All three hub pages use the same shared pattern — `HubDomainBlockList` with `HubBlockData` config:

```python
# ui/activities/activity_hub.py
_ACTIVITY_BLOCKS = [
    HubBlockData("Tasks", "tasks", "check-square", "#3B82F6", "/tasks", "/api/profile/tasks/preview"),
    # ... 5 more Activity Domains
]

def ActivityHubView() -> Div:
    return Div(PageHeader(...), HubDomainBlockList(_ACTIVITY_BLOCKS))
```

Each block loads 3 preview cards via HTMX from its `preview_url`. Preview endpoints return `HubPreviewGrid(cards)` or `HubPreviewEmpty(domain)`.

**Preview endpoints:**
- Activity: `/api/profile/{slug}/preview` (6 domains, in `user_profile_ui.py`)
- Library: `/api/library/{section}/preview` (4 sections, in `library_ui.py`)
- GradeBook: `/api/gradebook/{section}/preview` (4 sections, split across `submissions_ui.py`, `exercise_reports_ui.py`, `activity_reports_ui.py`)
- Student hub: `/api/teaching/students/{uid}/{section}/preview` (4 sections: pending, revision, completed, ku — in `teaching_ui.py`)

## Usage: Graph-Driven Hub Page

Any route handler can render ORGANIZES data as a card grid:

```python
children_result = await lesson_service.get_organized_children(moc_uid)
cards = hub_cards_from_organizers(children_result.value)
section = HubSection("Contents", cards)
```

**Flow:** Navbar icon → hub page (`BasePage(STANDARD)`, no sidebar) → click "View all" or preview card → child page (`SidebarPage`). Sidebar title links back to hub.

**Files:** `ui/gradebook/hub.py`, `ui/library/hub.py`, `ui/activities/activity_hub.py`, `ui/teaching/hub.py` (hub views), `ui/gradebook/nav.py`, `ui/library/nav.py`, `ui/activities/nav.py`, `ui/teaching/nav.py` (sidebar nav for children). Teaching also has a nested student hub: `ui/teaching/student_hub.py`.

## Shelved Hubs

| Old Route | Old File | Shelved To | Replaced By |
|-----------|----------|------------|-------------|
| `/curriculum` | `ui/curriculum/landing.py` | `_shelved/curriculum_landing/` | `/profile` (301 redirect) |
| `/study` | `ui/study/dashboard.py` | `_shelved/study_dashboard/` | `/profile` (301 redirect) |

## File Locations

| Concern | File |
|---------|------|
| Shared components | `ui/patterns/hub.py` |
| Profile hub | `ui/profile/hub.py` |
| Profile routes | `adapters/inbound/user_profile_ui.py` |
| Activity hub view | `ui/activities/activity_hub.py` |
| Activity hub route | `adapters/inbound/activity_hub_routes.py` |
| Activity sidebar | `ui/activities/nav.py` |
| GradeBook hub view | `ui/gradebook/hub.py` |
| GradeBook sidebar | `ui/gradebook/nav.py` |
| Library hub view | `ui/library/hub.py` |
| Library sidebar | `ui/library/nav.py` |
| Teaching hub view | `ui/teaching/hub.py` |
| Teaching sidebar | `ui/teaching/nav.py` |
| Student hub view | `ui/teaching/student_hub.py` |
| Design rationale | `docs/design-principles/HUB_PAGES.md` |
| Base page wrapper | `ui/layouts/base_page.py` |

## See Also

- `/docs/design-principles/HUB_PAGES.md` — why hub pages exist
- `/docs/patterns/UI_COMPONENT_PATTERNS.md` — broader UI patterns
- `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` — MOC as graph pattern
