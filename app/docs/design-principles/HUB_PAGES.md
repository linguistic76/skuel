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

| Page | Hub Pattern | What It Organizes |
|------|-------------|-------------------|
| `/curriculum` | 4-card grid, no sidebar | Lessons, Learning Steps, Learning Paths, Exercises |
| `/profile` (target) | Section cards with counts and links | Kus, Lessons, Submissions, Reports, Nous |
| `/study` (target) | Section cards linking to student workflows | Submit, Submissions, Reports |

### Existing Example: `/curriculum`

The curriculum landing page is a hub. Four cards, each with an icon, title, description, and link. A stats grid shows counts. No sidebar. The sub-pages (`/lessons`, `/learning-steps`, etc.) use a sidebar for within-section navigation — but the entry point is a hub.

### Target Example: `/profile`

The profile page becomes a hub for the user's world:

- **Knowledge** — link to `/ku`, with count of bookmarked KUs
- **Lessons** — link to curriculum the user is engaged with
- **Submit** — link to submission interface, with pending count
- **Reports** — exercise reports and activity reports
- **Nous** — emerging section (identity, intelligence, self-knowledge)

Each section is a card or link group in the page content. No sidebar required.

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

- **New top-level sections** should have a hub page as their entry point
- **Profile redesign** will remove the sidebar and use hub pattern
- **Code review** should prefer hub pages over adding more sidebar items for top-level navigation
- **BasePage (STANDARD)** is the correct page type for hub pages — no custom layout needed

## See Also

- `/docs/domains/moc.md` — MOC as emergent identity
- `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` — LS Path vs MOC Path
- `/ui/curriculum/landing.py` — reference implementation of hub pattern
