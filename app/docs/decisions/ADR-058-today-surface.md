---
title: "ADR-058: Today as the Post-Login Landing Surface"
updated: 2026-09-21
status: current
category: decisions
tags: [adr, decisions, ui, landing, today, lifepath]
related: [ADR-050, ADR-055]
---

# ADR-058: Today as the Post-Login Landing Surface

**Status:** Accepted (amended 2026-09-12, 2026-09-19, 2026-09-21)

**Date:** 2026-04-23

**Decision Type:** Pattern/Practice

---

## Amendment (2026-09-21 — `/home` is gone)

The hub this ADR demoted no longer exists: `/home` was folded into the
`/profile` tabs on 2026-05-11 (`1cb65580d`, no redirect) and `/profile` was
retired by the Tasks+ arc (#1377, no route, no redirect) — a request for either
is a 404. Alternative 3 below, rejected here, happened in two later decisions.
`adapters/inbound/home_routes.py` keeps its name and registers only the two
shared navbar fragments (`GET /api/navbar/notification-badge`,
`GET /api/personal-header`). The Decision's "regression guard" clause and every
other line below that names the old hub are the record of the decision as
made and carry the `historical` marker.

---

## Amendment (2026-09-19 — Tasks+ arc PR 4, one navbar, one rule)

Two clauses of the Decision below are superseded. The rule that replaces
them — one navigation, one rule — lives in `ui/layouts/nav_config.py` and is
pinned by `tests/unit/ui/test_navbar.py`: the global chrome (bottom nav
below `sm`, centre links at `sm+`, both from `ICON_NAV_ITEMS`) carries
exactly ONE door per SECTION, lit for the whole section by a section key;
a section's pages are its sidebar's rows, lit by slug. The same chrome
renders for every role — the admin navbar fork is gone.

- **"admins continue to `/`" — retired.** ``/today`` is the landing for
  EVERY authenticated role: ``/`` is a 303 to it, the login, registration and
  reset redirects go there, and the PWA ``start_url`` (``/``) resolves to it.
  The admin hub that ``/`` served is deleted with the admin navbar fork: an
  admin sees the one chrome, with Admin and Teaching as role-gated section
  doors (centre links at lg+, rows on ``/settings`` below).
- **"primary icon nav item ... icon `sun` and `page_key="today"`" —
  retired.** The global chrome carries one door per SECTION, lit by a section
  key. Today is a PAGE of the Tasks+ section: the ``ICON_NAV_ITEMS`` door is
  **"Tasks+"** (→ ``/today``, ``page_keys={"activity"}``, icon ``activity``),
  first among the centre links and the bottom-nav tabs, lit on every page
  under the activity sidebar; the Today row of that sidebar is the page-level
  light. The two lights on ``/today`` (door + row) are the one sanctioned
  overlap — two levels of one navigation.

Everything else in the 2026-09-12 amendment stands; where it names Today as
"the mobile bottom-nav item", read "the Tasks+ door's landing".

---

## Amendment (2026-09-12 — day-view arc D.1)

The landing decision stands: ``/today`` is the post-login surface. The
*surface itself* was rebuilt as a server-rendered **day view**
(``ui/today/page.py``, [`calendar-priority-lens-arc.md`](../roadmap/done/calendar-priority-lens-arc.md)
§ D.1), and the handoff this ADR adopted is archived at
[`today-surface-handoff.md`](../roadmap/done/today-surface-handoff.md). What
changed:

- **Rendering.** Per-domain sections — Overdue (live day only), Tasks, Events,
  Habits, Milestones, Choices — rendered through the domain list cards and the
  calendar's chips, nav cluster and kind legend (one filter component and one
  storage key across Today/Weekly/Monthly). No page-local JavaScript:
  ``static/js/today.js``, ``static/css/today.css``, ``ui/today/drawer.py``, the <!-- historical -->
  ``window.SEED`` block and the six view TypedDicts are gone; ``TodayPageContext``
  carries domain models.
- **Interaction.** Quick-add (C6) and a server-rendered Defer 1d/1w control
  (C7, ``source=day|triage``, reloads the day via ``HX-Redirect``) stay as Today
  routes. Completing a task is the card's status toggle through the one
  completion door (``POST /api/tasks/{uid}/status``); completing a habit is
  the chip's modal through the calendar's per-day door, whose
  ``calendar-refresh`` the habits container listens for (re-fetching
  ``GET /today/{date}/habits``, the same shape the page rendered). The drawer, star/pin
  (``PINNED_TODAY`` edge — detached by
  ``scripts/migrations/detach_pinned_today_2026_09.cypher``), LifePath wake,
  keyboard map, drag-to-defer and optimistic UI are retired.
- **Navigation claim corrected.** The brand link goes to ``/explore``; Today is
  the mobile bottom-nav item, the activity sidebar's first row and the
  post-login redirect — not the brand link.

The orchestrator's ``ui/`` placement rationale below still holds and is why
SKUEL032 cites this ADR. Everything after this section describes the surface
as adopted in April 2026; where it conflicts with the amendment, the amendment
is current.

---

## Context

Until this ADR, authenticated users landed on `/home` — a "Home Hub" that <!-- historical -->
presented Submissions, GradeBook, and Library as equal top-level cards. The
hub answered "what can I do in SKUEL?" but not "what am I doing *today*?"
The user's life commitments (LifePaths), their overdue work, and their
time-anchored rituals were all buried one click deeper.

SKUEL's mental model is LifePath-first: every Activity hangs off a LifePath,
and every Activity Report rolls up into one. A landing page that ignores
LifePaths contradicts that model. Users repeatedly asked "where do I start
each morning?" — the hub was never a satisfying answer.

A dedicated design handoff (now archived at
`docs/roadmap/done/today-surface-handoff.md`) re-delivered the surface in SKUEL's actual
stack (FastHTML + HTMX + Alpine + MonsterUI) with production tokens. The
handoff targets: a Triage bar for overdue/blocked items, one ribbon per
LifePath (with a dormant variant), a Day spine of time-anchored rituals,
and a task detail drawer — all driven by keyboard, with drag-to-defer and
optimistic UI.

---

## Decision

**Adopt `/today` as the post-login landing page.**
**Demote `/home` from the primary entry point to a directly-addressable hub <!-- historical -->
that survives only as a regression guard.** *Superseded 2026-05-11 / #1377:
`/home` is gone — see the 2026-09-21 amendment.*

Implementation:
- Post-sign-in and post-registration redirects target `/today` for
  non-admin users (admins continue to `/`). *Superseded 2026-09-19: every
  role lands on `/today`.*
- Navbar brand link (`SKUEL`) and primary icon nav item point to
  `/today` with icon `sun` and `page_key="today"`. *Superseded 2026-09-12
  (brand → `/explore`) and 2026-09-19 (the door is "Tasks+", keyed by
  section).*
- `/home` still resolves (no 404s, no broken bookmarks) but nothing <!-- historical -->
  routes users to it automatically. *Superseded 2026-05-11 / #1377: `/home`
  is gone.*
- Home Hub's filter axes (Submissions / GradeBook / Library) are demoted
  to sidebar options reachable from Today, not peers of it.

**Live spec (at adoption):** the design handoff, now archived at
[`today-surface-handoff.md`](../roadmap/done/today-surface-handoff.md) — see
the amendment above for the surface as built today.

---

## Alternatives Considered

### Alternative 1: Keep `/home` as landing, add Today as a sibling <!-- historical -->
**Why rejected:** Peer navigation implies equal weight. Today answers the
central question (what am I doing now?) while Home Hub is a directory of
other surfaces. Treating them as peers recreates the confusion this ADR
is meant to resolve. Per "Consolidation Over Parallel Systems" the
codebase should have one canonical landing, not two.

### Alternative 2: Three-variant Today (Ribbon / Constellation / Command)
**Description:** The first design exploration proposed three alternate
surfaces so the user could pick the mental model that fit them.

**Why rejected:** Violates "One Path Forward." Three surfaces means three
maintenance burdens, three sets of keyboard interactions to keep in sync,
and a user-facing choice that adds cognitive load on first login.
Ribbon is the strongest of the three (LifePath-first, direct
manipulation) and ships as the single Today surface. Constellation and
Command are preserved in git history only.

### Alternative 3: Retire `/home` entirely in this ADR <!-- historical -->
**Why rejected:** Retiring a landing page is a behavioral change with
unknown downstream impact (bookmarks, docs, screenshots, user habit).
This ADR narrowly scopes the landing *redirect* change so it can be
validated on its own; full retirement is a separate decision once
usage data shows `/home` traffic has fallen off. <!-- historical -->

---

## Consequences

### Positive
- Landing page answers the LifePath-first question the rest of the app
  is built around — mental model is visible from the first screen.
- Triage bar surfaces blocked/overdue items that were previously
  two clicks deep, shortening the feedback loop.
- Keyboard-first navigation (j/k/Enter/x/d) makes Today competitive with
  a task manager without requiring mouse precision.
- `prefers-reduced-motion` is honored end-to-end; drag interactions are
  disabled automatically for users who opt out.

### Negative
- Users with `/home` bookmarks keep landing there on direct navigation <!-- historical -->
  and will not see Today until they click the brand link. Acceptable
  short-term cost; revisited when `/home` retirement is proposed. <!-- historical -->
- Today's interactivity (drag-to-defer, optimistic updates) concentrates
  more production JavaScript in `static/js/today.js` than prior pages <!-- historical -->
  carried. Kept verbatim from the handoff mock to minimize drift; an
  `<template x-for>` conversion is a possible follow-up if the
  innerHTML-rendered row approach blocks a future a11y audit.

### Risks & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Users disoriented by landing change | Low | Low | Brand link and icon nav both advertise `/today`; `/home` still resolves for muscle memory | <!-- historical -->
| Today assembly latency across 6 facade fetches | Medium | Medium | Orchestrator wraps the six independent reads (tasks / goals / principles / habits / events / LifePath designation) in a single `asyncio.gather`, so TTFB is bounded by the slowest facade, not the sum. Principle-edge fan-out is also gathered inside `_first_principle_map`. If p95 regresses once production traffic lands, the remaining optimization is folding Today's reads into `build_rich()` / MEGA-QUERY. |
| Drag-to-defer accidentally triggered on touch | Low | Low | Handoff spec defines a 70px threshold; `prefers-reduced-motion` disables drag entirely |

---

## Implementation Details

### Files
- `adapters/inbound/today_routes.py` — 5 endpoints (page, dated day-lens, the day's habits fragment, quick-add, defer)
- `adapters/inbound/auth_ui.py` — redirect targets `/today` for non-admins
- `adapters/inbound/home_routes.py` — the two shared navbar fragments (`GET /api/navbar/notification-badge`, `GET /api/personal-header`); no `/home` hub is registered
- `ui/today/page.py` — FastHTML translation of the handoff (now the server-rendered day view — see the amendment)
- `ui/today/drawer.py` — FastHTML translation of the handoff's detail drawer <!-- historical -->
- `ui/today/orchestrator.py` — `TodayOrchestrator.build_context()` assembles the view shape. Lives under `ui/` (not `core/services/`) because the output is a page context, not a service-layer contract; putting it in `core/` would invert the `core → ui` import direction.
- `ui/layouts/navbar.py`, `ui/layouts/nav_config.py` — brand + icon nav point at Today
- `static/js/today.js` — Alpine `today` factory, shipped verbatim from the mock <!-- historical -->
- `static/css/today.css` — task-row / defer-backdrop styles <!-- historical -->
- `static/css/input.css` — strength tokens
- `ui/page_contexts.py` — `TodayPageContext`, `TodayStats`, `LifePathRibbonView`, `TriageItemView`, `RitualView`, `KindMeta`, `TaskView`, `GoalView`, `PrincipleView` TypedDicts (page contexts are UI concerns; not in `core/ports/`)

### Endpoints (live signatures in `adapters/inbound/today_routes.py`; the adopted spec's §5 is in the archived handoff)
- `GET  /today` — full page through `render_activity_sidebar_page(active="today")` (the live current day)
- `GET  /today/{date_str}` — day lens for an arbitrary date (Prev/Now/Next navigation, parallel to Week/Month); unparseable dates degrade to today
- `GET  /today/{date_str}/habits` — the day's habit chips, re-fetched on `calendar-refresh`
- `GET  /today/tasks/{id}/drawer` — detail drawer fragment <!-- historical -->
- `POST /today/tasks/{id}/complete` — optimistic complete, 204 <!-- historical -->
- `POST /today/tasks/quick-add` — create a task scheduled on the viewed day (`title` + `view_date`); `scheduled_date` only, no `due_date` (a work chip, not a deadline); past days refused 400; success replies `HX-Redirect` back to the day's lens (C6 of the calendar act-from arc; creation replaced the deleted `CalendarService.quick_create`)
- `POST /today/tasks/{id}/defer` — accepts `span=1d|1w` + `source=day|triage` + `view_date`; moves the field(s) the card spoke for to `view_date + span`, guarded by the shared lens-membership predicate (`ui/today/membership.py`, C7 of the calendar act-from arc), 204
- `POST /today/tasks/{id}/star` — toggle priority pin, 204 <!-- historical -->
- `POST /today/lifepaths/{id}/wake` — clear dormant flag, returns ribbon fragment <!-- historical -->

Completion is not a Today route: the day's `TaskCard` posts its status
toggle to the shared, CSRF-protected, ownership-checked chokepoint
`POST /api/tasks/{uid}/status` — the one completion door every surface uses,
which also clears `completion_date` on a reopen.

The task-scoped route (`defer`) enforces ownership via `verify_entity_ownership`
(the API-style helper from `route_factories.route_helpers` — returns an
error `Result`, answered as a 404; the UI-style `require_owned_entity`
would be wrong here since the endpoint answers a 204, not a full page).

---

## References
- [`today-surface-handoff.md`](../roadmap/done/today-surface-handoff.md) — the adopted handoff, archived (its mock lives in git history)
- ADR-050: PWA as Mobile Strategy — establishes the open-web-standards lens Today inherits
- ADR-055: Architectural Lenses — Today sits in the cross-cutting "view" layer, not a subsystem
