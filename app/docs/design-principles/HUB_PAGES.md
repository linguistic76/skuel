---
title: "Design Principle: Hub Pages"
updated: 2026-04-07
status: current
category: design-principles
tags: [design, principles, ui, navigation, moc, hub]
related: [docs/domains/moc.md, docs/architecture/CURRICULUM_GROUPING_PATTERNS.md]
---

# Hub Pages

> Pages are navigation. A well-designed page with curated content replaces persistent chrome.

## Statement

SKUEL organizes user navigation through **hub pages** — standalone pages that provide access to related sections through their content, not through sidebar menus or persistent navigation chrome. A hub page is something you read. It shows you where you are and where you can go. The page itself is the map.

This principle descends from the MOC (Map of Content) concept. A MOC is any entity that organizes other entities via relationships. A hub page is the UI expression of this idea — a page that organizes access to other pages through intentional, curated links.

## Why This Matters

Sidebar menus are generic infrastructure. They present the same list of links regardless of context. A hub page is contextual — it shows counts, status, and descriptions that help the user decide where to go next. The content *is* the navigation.

Sidebars also add persistent visual weight and responsive complexity (desktop sidebar vs. mobile tabs). Hub pages are just pages — they work the same on every screen size with standard HTML.

SKUEL values standards-compliant, non-cutting-edge UI. Hub pages are the oldest pattern on the web: a page with links. No JavaScript state management for sidebar toggle. No responsive breakpoint switching between sidebar and tabs. Just HTML.

## In Practice

### Top-Level Navigation Structure

The navbar provides five entry points. Three share a unified tabbed hub, one is a static container hub, and one is a personal overview:

| Page | Hub Pattern | What It Organizes |
|------|-------------|-------------------|
| `/home` | Tabbed hub (default: Submissions tab) | Submissions blocks, GradeBook blocks, Library blocks |
| `/submissions` | Tabbed hub (Submissions tab active) | Same as `/home` — Submissions tab pre-selected |
| `/gradebook` | Tabbed hub (GradeBook tab active) | Same as `/home` — GradeBook tab pre-selected |
| `/library` | Tabbed hub (Library tab active) | Same as `/home` — Library tab pre-selected |
| `/teaching` | Container hub | Students, Groups, Review Queue, Forms (TEACHER role) |
| `/profile` | Personal overview | Focus/Velocity, Activity Domains (6 HTMX blocks) |

### Unified Tabbed Hub (`/home`, `/submissions`, `/gradebook`, `/library`)

All four pages render `HomeHub(active_tab=...)` from `ui/home_hub.py`. The Alpine.js `x-data` initializes with the correct tab pre-selected. Clicking a different tab switches instantly (client-side, no page reload).

Each tab shows a `HubDomainBlockList` populated by a `*_BLOCKS` constant:
- **Submissions tab** — `SUBMISSIONS_BLOCKS` from `ui/workbench/hub.py`: Upload Activity Data, Submit Exercise
- **GradeBook tab** — `GRADEBOOK_BLOCKS` from `ui/gradebook/hub.py`: Exercise Reports, Activity Reports, Revisions
- **Library tab** — `LIBRARY_BLOCKS` from `ui/library/hub.py`: Exercises, Submission History, Resources, Ku, Path Steps

Visiting any of the four URLs lands you on the same interface with the appropriate tab highlighted. Child pages use `SidebarPage` for within-section navigation.

### Static Container Hub (Teaching)

**Teaching** (`/teaching`) — 4 containers: Students (`/teaching/students`), Groups (`/teaching/groups`), Review Queue (`/teaching/queue`), Forms (`/teaching/forms`). Hub view in `ui/teaching/hub.py`, sidebar nav in `ui/teaching/nav.py`. Individual students have a **nested hub** at `/teaching/students/{uid}` — 4 HTMX-loaded preview blocks (Needs Review, Revision Requested, Completed, KU Progress) showing actual submission/KU data inline, linking to `/teaching/students/{uid}/submissions?tab=...`. Preview endpoints: `/api/teaching/students/{uid}/{section}/preview`.

**Components:** `HubContainerGrid` and `HubContainer` in `ui/patterns/hub.py` — bigger than `HubCard`, with more padding, full description, and arrow affordance.

### Inline Hub Content

- **Activity Domains** — embedded directly in `/profile` as 6 HTMX lazy-loaded preview blocks. Activity sidebar (shared across `/tasks`, `/goals`, etc.) links back to `/profile`.

### Library Data Pattern

Library tabs show **user-specific filtered content**, not full listings:

- **Ku tab** (`/library/ku`) — Only the user's bookmarked (PINNED) Ku, fetched via `backend.get_many()` with pinned UIDs from `UserRelationshipService.get_pinned_entities()`.
- **Path Steps tab** (`/library/path-steps`) — Only enrolled (IN_PROGRESS) steps, fetched via `backend.get_many()` with enrolled UIDs from `PsMasteryService.get_in_progress_step_uids()`.
- **Exercises tab** (`/library/exercises`) — Exercises from two sources merged by `ExerciseService.get_student_exercises_with_status()`: assigned (via group) + personal (linked to IN_PROGRESS PathSteps).
- **Resources tab** (`/library/resources`) — All `Resource` entities (admin-curated, shared).

**Key principle:** Fetch only what the user needs by UID, not all entities with arbitrary limits.

## Relationship to MOC

MOC (Map of Content) is an emergent graph identity — any entity with ORGANIZES relationships. Hub pages are the UI analog: any page that organizes access to other pages through its content. The two ideas reinforce each other:

- **Graph layer:** An entity with ORGANIZES relationships is a MOC
- **UI layer:** A page with curated links to sub-sections is a hub page

Hub pages do not require ORGANIZES relationships in the graph. They can be purely UI-driven. But when a page's links are derived from graph relationships, the two patterns converge.

## Coexistence with Sidebars

Hub pages and sidebars serve different roles and can coexist:

- **Hub page:** Entry point. Helps the user choose a direction. Used at the top of a section.
- **Sidebar:** Within-section navigation. Helps the user move between items in a section they've already entered.

The KU section demonstrates this: `/ku` uses a sidebar (bookmarks + latest in sidebar, listing in main area). The principle is not "delete all sidebars" — it is "use hub pages as entry points instead of relying on sidebars for top-level navigation."

## Maturity and Immature Code

Hub pages provide a natural home for features at different maturity levels. A hub can link to a well-built section and a rough prototype equally. The link text and description communicate maturity:

- "Reports — Exercise and activity reports" (mature)
- "Nous — Coming Soon" (immature, exploratory)

This allows raw, immature code to exist alongside mature code without architectural conflict. The hub page itself is just content — it doesn't need the linked sections to be complete.

## Enforcement

- **Home is the post-login entry point** (`/home`) — users land here after login with 6 navigational cards
- **Profile is the personal overview hub** — users navigate to `/profile` for activity domains and personal statistics
- **New domain pages** should be rich functional hubs, not card-grid-only pages
- **BasePage (STANDARD)** is the correct page type for hub pages — no custom layout needed
- **Shared components** (`HubCard`, `HubSection`, `HubCardData`) in `ui/patterns/hub.py` — used by domain hubs, not Profile

## See Also

- `/docs/domains/moc.md` — MOC as emergent identity
- `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` — PS Path vs MOC Path
- `/docs/patterns/HUB_PAGE_PATTERN.md` — implementation pattern and shared components
- `/ui/patterns/hub.py` — shared hub card components
- `/ui/profile/hub.py` — reference implementation (THE main hub)
