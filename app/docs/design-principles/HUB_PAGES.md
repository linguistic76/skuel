---
title: "Design Principle: Hub Pages"
updated: 2026-03-29
status: current
category: design-principles
tags: [design, principles, ui, navigation, moc, hub]
related: [docs/domains/moc.md, docs/architecture/CURRICULUM_GROUPING_PATTERNS.md]
---

# Hub Pages

> Pages are navigation. A well-designed page with curated links replaces persistent chrome.

## Statement

SKUEL organizes user navigation through **hub pages** — standalone pages that provide access to related sections through their content, not through sidebar menus or persistent navigation chrome. A hub page is something you read. It shows you where you are and where you can go. The page itself is the map.

This principle descends from the MOC (Map of Content) concept. A MOC is any entity that organizes other entities via relationships. A hub page is the UI expression of this idea — a page that organizes access to other pages through intentional, curated links.

## Why This Matters

Sidebar menus are generic infrastructure. They present the same list of links regardless of context. A hub page is contextual — it shows counts, status, and descriptions that help the user decide where to go next. The content *is* the navigation.

Sidebars also add persistent visual weight and responsive complexity (desktop sidebar vs. mobile tabs). Hub pages are just pages — they work the same on every screen size with standard HTML.

SKUEL values standards-compliant, non-cutting-edge UI. Hub pages are the oldest pattern on the web: a page with links. No JavaScript state management for sidebar toggle. No responsive breakpoint switching between sidebar and tabs. Just HTML.

## In Practice

**Profile is THE main hub.** The old `/curriculum` and `/study` hubs are shelved — they redirect 301 to `/profile`.

| Page | Hub Pattern | What It Organizes |
|------|-------------|-------------------|
| `/profile` | Grouped card sections with badges | Knowledge, Practice, Reports — links to all domain pages |

### Profile as THE Hub

Profile is the top-level entry point for the user's world. Cards are grouped into sections (Knowledge, Practice, Reports) with context-driven badges showing live counts from UserContext:

- **Knowledge** — `/ku` (bookmarked count), `/lessons`
- **Practice** — `/exercises` (assigned count), `/submit` (unsubmitted count), `/submissions`
- **Reports** — `/exercise-reports` (pending feedback count), `/activity-reports`

### Domain Hub Pages (Future)

The pages that Profile links to will become rich functional hubs:

- **Lessons hub** — enrolled lessons, available lessons, enrolled LPs/LSs
- **Submissions hub** — submit an ExerciseSubmission + list submitted work
- **Reports hub** — ExerciseReports list + RevisedExercise UI
- **KU hub** — ORGANIZES-driven knowledge navigation

Each is more than a card grid — they have real capabilities (forms, entity lists, actions).

## Relationship to MOC

MOC (Map of Content) is an emergent graph identity — any entity with ORGANIZES relationships. Hub pages are the UI analog: any page that organizes access to other pages through its content. The two ideas reinforce each other:

- **Graph layer:** An entity with ORGANIZES relationships is a MOC
- **UI layer:** A page with curated links to sub-sections is a hub page

Hub pages do not require ORGANIZES relationships in the graph. They can be purely UI-driven (like `/curriculum`). But when a page's links are derived from graph relationships, the two patterns converge.

## Coexistence with Sidebars

Hub pages and sidebars serve different roles and can coexist:

- **Hub page:** Entry point. Helps the user choose a direction. Used at the top of a section.
- **Sidebar:** Within-section navigation. Helps the user move between items in a section they've already entered.

The curriculum section demonstrates this: `/curriculum` is a hub (no sidebar), `/lessons` uses a sidebar (within-section navigation). The principle is not "delete all sidebars" — it is "use hub pages as entry points instead of relying on sidebars for top-level navigation."

## Maturity and Immature Code

Hub pages provide a natural home for features at different maturity levels. A hub can link to a well-built section and a rough prototype equally. The link text and description communicate maturity:

- "Reports — Exercise and activity reports" (mature)
- "Nous — Emerging" (immature, exploratory)

This allows raw, immature code to exist alongside mature code without architectural conflict. The hub page itself is just links — it doesn't need the linked sections to be complete.

## Enforcement

- **Profile is THE main hub** — all top-level navigation flows through `/profile`
- **New domain pages** should be rich functional hubs, not card-grid-only pages
- **BasePage (STANDARD)** is the correct page type for hub pages — no custom layout needed
- **Shared components** (`HubCard`, `HubSection`, `HubCardData`) in `ui/patterns/hub.py`

## See Also

- `/docs/domains/moc.md` — MOC as emergent identity
- `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` — LS Path vs MOC Path
- `/docs/patterns/HUB_PAGE_PATTERN.md` — implementation pattern and shared components
- `/ui/patterns/hub.py` — shared hub card components
- `/ui/profile/hub.py` — reference implementation (THE main hub)
