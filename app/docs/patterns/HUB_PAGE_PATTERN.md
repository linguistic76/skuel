---
title: "Pattern: Hub Page (MOC) Implementation"
updated: 2026-03-29
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

**Profile is THE main hub** (`/profile`). It is a **live actionable hub** — not a card grid. It surfaces the user's active learning state (Kus, lessons, exercises with Submit buttons, report summaries) directly on the page, sourced from `UserContext.build_rich()`. The old intermediate hubs (`/curriculum`, `/study`) are shelved — they redirect 301 to `/profile`.

**Domain hub pages** are rich functional pages that Profile links to:

| Route | Purpose | Status |
|-------|---------|--------|
| `/ku` | Knowledge browsing (ORGANIZES-driven) | Active |
| `/lessons` | Enrolled + available lessons | Active |
| `/exercises` | Practice linked to lessons and Kus | Active |
| `/submissions` | Full submission list + browse | Active |
| `/exercise-reports` | Teacher and AI feedback on submissions | Active |
| `/activity-reports` | Activity progress reports | Active |

Domain hubs are NOT simple card grids — they have real capabilities (forms, entity lists, actions). `/profile` Submissions section uses Alpine.js tabs + HTMX lazy-loaded fragments.

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

## Usage: Profile Hub (Live Actionable)

Profile renders live content sections from `UserContext`, not card grids:

```python
def ProfileHubView(context: UserContext) -> Div:
    return Div(
        _personal_header(context),          # Focus + Velocity indicators
        _knowledge_section(context),        # Bookmarked + recent Kus (mastery %, namespace)
        _lessons_section(context),          # Lessons being studied (via IN_PROGRESS relationship)
        _exercises_section(context),        # Assigned exercises with Submit buttons
        _reports_section(),                 # HTMX lazy-loaded report summaries
        _nous_section(),                    # Community feed (placeholder)
        _settings_link(),
    )
```

**Data sources (all from `UserContext.build_rich()`):**
- Knowledge: `ku_bookmarked_uids` + `recently_viewed_ku_uids` → lookup in `knowledge_units_rich`
- Lessons: `current_lessons` (list of `CurrentLessonItem` with uid + title)
- Exercises: `unsubmitted_exercises` + `pending_revised_exercises` (from UserContext)
- Reports: HTMX endpoints `/api/profile/reports/exercise-summary` and `/api/profile/reports/activity-summary`

## Usage: Graph-Driven Hub Page

Any route handler can render ORGANIZES data as a card grid:

```python
children_result = await lesson_service.get_organized_children(moc_uid)
cards = hub_cards_from_organizers(children_result.value)
section = HubSection("Contents", cards)
```

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
| Design rationale | `docs/design-principles/HUB_PAGES.md` |
| Base page wrapper | `ui/layouts/base_page.py` |

## See Also

- `/docs/design-principles/HUB_PAGES.md` — why hub pages exist
- `/docs/patterns/UI_COMPONENT_PATTERNS.md` — broader UI patterns
- `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` — MOC as graph pattern
