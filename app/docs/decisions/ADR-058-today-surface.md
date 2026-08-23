---
title: "ADR-058: Today as the Post-Login Landing Surface"
updated: 2026-04-23
status: current
category: decisions
tags: [adr, decisions, ui, landing, today, lifepath]
related: [ADR-050, ADR-055]
---

# ADR-058: Today as the Post-Login Landing Surface

**Status:** Accepted

**Date:** 2026-04-23

**Decision Type:** Pattern/Practice

---

## Context

Until this ADR, authenticated users landed on `/home` — a "Home Hub" that
presented Submissions, GradeBook, and Library as equal top-level cards. The
hub answered "what can I do in SKUEL?" but not "what am I doing *today*?"
The user's life commitments (LifePaths), their overdue work, and their
time-anchored rituals were all buried one click deeper.

SKUEL's mental model is LifePath-first: every Activity hangs off a LifePath,
and every Activity Report rolls up into one. A landing page that ignores
LifePaths contradicts that model. Users repeatedly asked "where do I start
each morning?" — the hub was never a satisfying answer.

A dedicated design handoff (now archived at
`docs/design-handoff/today/`) re-delivered the surface in SKUEL's actual
stack (FastHTML + HTMX + Alpine + MonsterUI) with production tokens. The
handoff targets: a Triage bar for overdue/blocked items, one ribbon per
LifePath (with a dormant variant), a Day spine of time-anchored rituals,
and a task detail drawer — all driven by keyboard, with drag-to-defer and
optimistic UI.

---

## Decision

**Adopt `/today` as the post-login landing page. Demote `/home` from the
primary entry point to a directly-addressable hub that survives only as a
regression guard.**

Implementation:
- Post-sign-in and post-registration redirects target `/today` for
  non-admin users (admins continue to `/`).
- Navbar brand link (`SKUEL`) and primary icon nav item point to
  `/today` with icon `sun` and `page_key="today"`.
- `/home` still resolves (no 404s, no broken bookmarks) but nothing
  routes users to it automatically.
- Home Hub's filter axes (Submissions / GradeBook / Library) are demoted
  to sidebar options reachable from Today, not peers of it.

**Live spec:** [`docs/design-handoff/today/today.md`](../design-handoff/today/today.md)
remains the source of truth for the surface's data shape, endpoints,
keymap, and accessibility requirements. `today.html` in the same folder
is the self-contained reference mock.

---

## Alternatives Considered

### Alternative 1: Keep `/home` as landing, add Today as a sibling
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

### Alternative 3: Retire `/home` entirely in this ADR
**Why rejected:** Retiring a landing page is a behavioral change with
unknown downstream impact (bookmarks, docs, screenshots, user habit).
This ADR narrowly scopes the landing *redirect* change so it can be
validated on its own; full retirement is a separate decision once
usage data shows `/home` traffic has fallen off.

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
- Users with `/home` bookmarks keep landing there on direct navigation
  and will not see Today until they click the brand link. Acceptable
  short-term cost; revisited when `/home` retirement is proposed.
- Today's interactivity (drag-to-defer, optimistic updates) concentrates
  more production JavaScript in `static/js/today.js` than prior pages
  carried. Kept verbatim from the handoff mock to minimize drift; an
  `<template x-for>` conversion is a possible follow-up if the
  innerHTML-rendered row approach blocks a future a11y audit.

### Risks & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Users disoriented by landing change | Low | Low | Brand link and icon nav both advertise `/today`; `/home` still resolves for muscle memory |
| Today assembly latency across 6 facade fetches | Medium | Medium | Orchestrator wraps the six independent reads (tasks / goals / principles / habits / events / LifePath designation) in a single `asyncio.gather`, so TTFB is bounded by the slowest facade, not the sum. Principle-edge fan-out is also gathered inside `_first_principle_map`. If p95 regresses once production traffic lands, the remaining optimization is folding Today's reads into `build_rich()` / MEGA-QUERY. |
| Drag-to-defer accidentally triggered on touch | Low | Low | Handoff spec defines a 70px threshold; `prefers-reduced-motion` disables drag entirely |

---

## Implementation Details

### Files
- `adapters/inbound/today_routes.py` — 8 endpoints (page + dated day-lens + drawer + 5 mutations)
- `adapters/inbound/auth_ui.py` — redirect targets `/today` for non-admins
- `adapters/inbound/home_routes.py` — `/home` retained as regression guard
- `ui/today/page.py`, `ui/today/drawer.py` — FastHTML translation of the handoff
- `ui/today/orchestrator.py` — `TodayOrchestrator.build_context()` assembles the view shape. Lives under `ui/` (not `core/services/`) because the output is a page context, not a service-layer contract; putting it in `core/` would invert the `core → ui` import direction.
- `ui/layouts/navbar.py`, `ui/layouts/nav_config.py` — brand + icon nav point at Today
- `static/js/today.js` — Alpine `today` factory, shipped verbatim from the mock
- `static/css/today.css`, `static/css/input.css` — task-row / defer-backdrop styles + strength tokens
- `ui/page_contexts.py` — `TodayPageContext`, `TodayStats`, `LifePathRibbonView`, `TriageItemView`, `RitualView`, `KindMeta`, `TaskView`, `GoalView`, `PrincipleView` TypedDicts (page contexts are UI concerns; not in `core/ports/`)

### Endpoints (see `today.md` §5 for full signatures)
- `GET  /today` — full page via `BasePage(active_page="today")` (the live current day)
- `GET  /today/{date_str}` — day lens for an arbitrary date (Prev/Now/Next navigation, parallel to Week/Month); unparseable dates degrade to today
- `GET  /today/tasks/{id}/drawer` — detail drawer fragment
- `POST /today/tasks/{id}/complete` — optimistic complete, 204
- `POST /today/tasks/quick-add` — create a task scheduled on the viewed day (`title` + `view_date`); `scheduled_date` only, no `due_date` (a work chip, not a deadline); past days refused 400; success replies `HX-Redirect` back to the day's lens (C6 of the calendar act-from arc; creation replaced the deleted `CalendarService.quick_create`)
- `POST /today/tasks/{id}/defer` — accepts `span=1d|1w` + `source=ribbon|triage` + `view_date`; moves the field(s) the card spoke for to `view_date + span`, guarded by the shared lens-membership predicate (`ui/today/membership.py`, C7 of the calendar act-from arc), 204
- `POST /today/tasks/{id}/star` — toggle priority pin, 204
- `POST /today/lifepaths/{id}/wake` — clear dormant flag, returns ribbon fragment

One mutation Today does NOT own: the flash toast's **Undo** reopens a
just-completed task through the shared status chokepoint
`POST /api/tasks/{id}/status`, posting the status the card carried before the
complete (`TaskView.status`). Reusing the live, CSRF-protected,
ownership-checked route keeps Undo a real reopen — the chokepoint also clears
`completion_date` — instead of a local un-hide over a graph that stays
completed. No Today-specific endpoint was added for it.

Every task-scoped route enforces ownership via `verify_entity_ownership`
(the API-style helper from `route_factories.route_helpers` — returns an
error `Result` for HTMX fragments/204s; the UI-style `require_owned_entity`
would be wrong here since these endpoints return fragments, not full pages).

---

## References
- [`docs/design-handoff/today/today.md`](../design-handoff/today/today.md) — live spec
- [`docs/design-handoff/today/today.html`](../design-handoff/today/today.html) — reference mock
- ADR-050: PWA as Mobile Strategy — establishes the open-web-standards lens Today inherits
- ADR-055: Architectural Lenses — Today sits in the cross-cutting "view" layer, not a subsystem
