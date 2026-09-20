---
title: "Design Principle: Sections, Chrome and Hub Pages"
updated: 2026-09-19
status: current
category: design-principles
tags: [design, principles, ui, navigation, moc, hub, chrome]
related: [docs/domains/moc.md, docs/architecture/CURRICULUM_GROUPING_PATTERNS.md, docs/patterns/HUB_PAGE_PATTERN.md, docs/roadmap/done/tasks-plus-one-chrome.md]
---

# Sections, Chrome and Hub Pages

> A section is navigated by its chrome. A hub page earns its place only when it carries what the section nav cannot.

## Statement

SKUEL's navigation has two levels, and one rule binds them (`ui/layouts/nav_config.py`):

- **The global chrome carries one door per SECTION**, lit for the whole section by a section key. Below `sm` the
  doors are the bottom nav; from `sm` they are the navbar's centre links — both rendered from the same
  `ICON_NAV_ITEMS` spec, identical for every authenticated role. Role-gated doors (Teaching, Admin) join the centre
  links at `lg` and are rows on `/settings` below it.
- **A section's PAGES are its sidebar's rows**, lit by slug. At `lg+` the rows are a collapsible sidebar; below `lg`
  they are the **section nav** — a horizontally scrolling `nav/ul/li/a[aria-current]` list above the content
  (`ui/patterns/sidebar.py`). The same `SidebarItem` list produces both.

A door's href is the section's landing. The landing may or may not be a sidebar row: Tasks+ lands on `/today`, which
IS its first row (the door lights as the section and the Today row lights as the page — two levels of one
navigation, not a duplicate); Library and Submissions land on pages outside their sidebars (`/explore/library`, the
`/submissions` MOC root); PathSteps has no sidebar. What the rule forbids is a URL at both levels anywhere else: a
door's href may appear in a sidebar only as that sidebar's first row, and no other row may be a door.
`tests/unit/ui/test_navbar.py` pins exactly that over every `*_SIDEBAR_ITEMS`.

**Tasks+ IS a section.** Its sidebar (`ui/activities/nav.py`) is the one list — Today, Weekly, Monthly, the six
Activity Domains, Journal, GradeBook — on every page under it, and the Tasks+ door (→ `/today`) is lit on all of
them. It has no hub page: the section nav already shows the siblings, and `/today` is the cross-domain glance.

## Why This Matters

The section nav is the smallest chrome that still shows a page's siblings and works without JavaScript. It is the
same links at every width, so nothing has to be learned twice; below `lg` the current link is centred in the row
before first paint (a parse-time script), and with JS off the row is a plain scrolling list. A drawer or hamburger
would hide the siblings behind a tap; a `<select>` would navigate on input; a hub page would cost a click on the way
to every page. SKUEL values standards-compliant, non-cutting-edge UI: a `<nav>` of `<a>` links, marked
`aria-current="page"`, is the oldest pattern on the web.

The chrome is also where cost is decided. A sidebar's badge loader (`/api/sidebar/badges`, a `RichUserContext`
build) is opt-in (`SidebarPage(badges=True)` — Tasks+ only) and fires only once the desktop sidebar is on screen
(`hx-trigger="intersect once"`), so a phone never pays for badges it cannot see.

## When a Hub Page Earns Its Place

A hub page is a page whose content IS the navigation — a MOC (Map of Content) in UI form. It is justified when it
carries something the section nav cannot: a description of each destination before the user commits, a card grid
of the section's sub-pages for a first-time visitor, live previews that decide *where to go next*, or the organised
children of a graph entity. It is NOT justified as a second door to pages the chrome already reaches, and it never
replaces the section nav — the nav is what shows the siblings once the user is inside.

| Page | Hub form | What it carries that the nav cannot |
|------|----------|-------------------------------------|
| `/submissions` | MOC root — sidebar-free `BasePage(STANDARD)`, five `MocCard`s | A described entry into the five Submissions doors (Sync first — the primary personal-data path) |
| `/library` | MOC root — four `MocCard`s | A described entry into the four Library lists |
| `/groups` | `HubDomainBlock` per group, HTMX-loaded "Recent Shares" | Peer work shared with each group the student belongs to |
| `/teaching/students/{uid}` | Nested hub — `HubDomainBlockList` (Needs Review, Revision Requested, Completed, KU Progress) | One student's live state, four buckets from one orchestrator read (OOB swaps) |
| `/gradebook/{uid}` | A "Map of Content" `HubSection` when the entry has `ORGANIZES` children | An entry's organised children, linked per entity type |

The MOC roots are defined in `adapters/inbound/user_entry_ui.py` (`submissions_moc`) and
`adapters/inbound/library_ui.py` (`library_moc`); their child pages use `SidebarPage` and link back to the root via
the sidebar's `title_href`. `/gradebook` is not a hub: it is the one received-feedback page (per-exercise exchange
lines, `ui/gradebook/summary.py`), a Tasks+ page with the GradeBook row lit. Teaching has no hub either —
`/teaching/students` is its landing and the sidebar (`ui/teaching/nav.py`) carries Groups, Review Queue and Forms.

**Retired without a hub replacement:** the `/profile` personal-overview hub (its four tabs live where their content
lives — Tasks+, `/library`, `/submissions`, `/gradebook`; `/profile/shared`, the shared-with-me inbox, keeps its
URL) and the admin home hub at `/` (`/` is a 303 to `/today` for every role). The cross-domain top-3 previews died
with the hub; if that glance is ever missed, its home is a `/today` section, not a revived hub. The record is
`docs/roadmap/done/tasks-plus-one-chrome.md`.

## Library Sub-Page Data Pattern

Library sub-pages show **user-specific filtered content**, not full listings (`core/orchestrator/library_orchestrator.py`):

- **Ku** (`/library/ku`) — only the user's bookmarked (PINNED) Ku, fetched by UID from
  `UserRelationshipService.get_pinned_entities()`.
- **Path Steps** (`/library/path-steps`) — only enrolled (IN_PROGRESS) steps, fetched by UID from
  `PsMasteryService.get_in_progress_step_uids()`.
- **Exercises** (`/library/exercises`) — two sources merged by `ExerciseService.get_student_exercises_with_status()`:
  assigned (via group) + personal (linked to IN_PROGRESS PathSteps).
- **Resources** (`/library/resources`) — all `Resource` entities (admin-curated, shared).

**Key principle:** fetch only what the user needs by UID, not all entities with arbitrary limits.

## Relationship to MOC

MOC (Map of Content) is an emergent graph identity — any entity with ORGANIZES relationships. A hub page is the UI
analog: a page that organizes access to other pages through its content.

- **Graph layer:** an entity with ORGANIZES relationships is a MOC
- **UI layer:** a page with curated links to sub-sections is a hub page

A hub page does not need ORGANIZES relationships behind it (`/library` is purely UI-driven); when a page's links ARE
derived from the graph (`hub_cards_from_organizers` on `/gradebook/{uid}`), the two patterns converge.

## Maturity and Immature Code

A hub page can link to a well-built section and a rough prototype equally; the card text communicates maturity
("Reports — exercise and activity reports" vs "Coming soon"). Raw code can sit beside mature code without
architectural conflict — the hub is content, and does not need its destinations complete.

## Enforcement

- **Landing is `/today` for every authenticated role** — login, `/`, and the PWA `start_url` all resolve there;
  the account page is `/settings` (avatar at every width).
- **One door per section in the chrome; pages are sidebar rows.** A new section is a new `IconNavItem` (or a
  role-gated `NavItem`) plus a `*_SIDEBAR_ITEMS` list — never a second door to an existing page. The
  anti-duplication test fails otherwise.
- **A new hub page must name what it carries that the section nav cannot** (the table above); a card grid that
  merely repeats the sidebar is deleted.
- **`BasePage(STANDARD)`** is the page type for a hub page — no custom layout needed.
- **Shared components** (`MocCard`, `HubCard`, `HubSection`, `HubDomainBlock`, `HubBlockData`) live in
  `ui/patterns/hub.py`.

## See Also

- `/docs/domains/moc.md` — MOC as emergent identity
- `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` — PS Path vs MOC Path
- `/docs/patterns/HUB_PAGE_PATTERN.md` — implementation pattern and shared components
- `/docs/roadmap/done/tasks-plus-one-chrome.md` — the arc record: measurements, rulings overturned, the chrome gate
- `/ui/layouts/nav_config.py` — the chrome's one spec; `/ui/patterns/sidebar.py` — the sidebar + section nav
