---
title: "Tasks+ / One-Chrome Follow-ons — Explore's Phone Form, the Doorless Census, the Tabs Widget, Three Small Rulings"
updated: 2026-09-19
status: "deferred"
registered: 2026-09-19
trigger: "Mike schedules each — every item needs a product ruling or a 1440 snapshot first; none is a hub dependency"
check: "the code sites named under each item still exist in the stated shape; the chrome gate (scripts/chrome_gate.py) is GREEN before any of them ships"
---

# Tasks+ / One-Chrome Follow-ons

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

What the Tasks+ / one-chrome arc ([`done/tasks-plus-one-chrome.md`](done/tasks-plus-one-chrome.md), #1373–#1378)
deliberately left outside itself. Each item was priced in the review (§4 D5, D7, D8; §5 item 7) and ruled *after
the arc, its own PR*. None blocks anything; each waits on a ruling or a first snapshot. The arc's constraints hold for
all of them: one `SidebarPage` for every sidebar, the improvement lands in the shared component, every chrome PR runs
`scripts/chrome_gate.py` before and after and bumps `CACHE_VERSION` when `static/` changes.

## 1. Explore's phone form + the MOC-roots ruling (D5)

The Explore sidebar (graph hero + Learning/Saved/Completed lists) is desktop-only `extra_sidebar_sections`; below
`lg` it does not exist and `/explore/library` — the Library door's landing — has no section nav at all. Two names,
two keys, one section: the navbar "Library" lands on the public catalog (`/explore/library`, key `explore`), the
sidebar "Library" is the personal MOC root (`/library`, key `library`), and PR 4 keys the Library door on both
(`IconNavItem.page_keys = {"explore", "library"}`) so it lights on its own landing.
**Rule:** accept the absence, give Explore a phone form through `SidebarPage(extra_mobile_sections=…)` (the parameter
exists; Explore passes nothing to it), or fold Explore into the Library section — and whether `/library` and
`/submissions` stay MOC roots. **Where:** `ui/explore/nav.py`, `ui/patterns/sidebar.py`, `ui/layouts/nav_config.py`.

## 2. The doorless-surfaces census (D8)

Ten surfaces have no door in the chrome or any sidebar: `/groups`, `/lifepath`, `/insights`, `/self-checkin`,
`/journals` (discussions), `/search`, `/pathways`, `/activity-review`, `/analytics`, plus the caller-less
`ProfileHubData` / `UserStatsAggregator.get_profile_hub_data` stack (`core/services/user_stats_types.py`,
`core/services/user/user_stats_aggregator.py`, reached only through `_context_planning_mixin.py`, which nothing
routes to). Each needs a product ruling: staged (give it a door — a sidebar row or a section) or abandoned (delete
per One Path Forward). Not a hub dependency; the `/profile` retirement created none of these.

## 3. `ui/enum_helpers.py` census

24 of its 32 wrappers have no production caller (`core/`, `adapters/`, `ui/`, `scripts/`; several are exercised only
by their own tests). PR 5 orphaned three more and ruled a token deletion worthless — the module wants one census PR:
keep what a route or view calls, delete the rest with their tests.

## 4. `ui/patterns/tabs.py` <!-- planned --> — extract the one correct tabs widget

Two live same-page switchers are tabs widgets and neither is right: the teaching student-detail page's rows
(`alpine_section_renderer` / `alpine_mobile_section_renderer`, `ui/patterns/sidebar.py`) render `role="tab"` with
`@click` and no keyboard path; `/groups` (`ui/groups/hub.py`) has a roving-tabindex widget whose tab bar is an inline
`display:flex; width:100%` with no overflow rule — bounded at `MAX_STUDENT_GROUPS = 4`, so it does not overflow
today. **Build:** one WAI-ARIA tab bar in `ui/patterns/tabs.py` <!-- planned --> — buttons, `aria-controls`, roving tabindex, arrow
keys, `overflow-x-auto` + `shrink-0` — adopted by BOTH consumers. Mike sees the 1440 snapshot first.

## 5. `SidebarItem.group` + desktop dividers

The Tasks+ sidebar is eleven flat rows. A `group` field on `SidebarItem` with dividers on the desktop sidebar
(By time · By kind · Journal / GradeBook) gives the loop's structure cheaply without re-cutting the chrome — the
review's answer to D6 (re-cut into loop phases: ruled NOT now; the reason for reversing calendar-arc ruling 6 is
unrecorded and is the constraint any re-cut must satisfy).

## 6. Rename Submissions › Journal to "Transcribe" (D7)

`/submissions/journal` persists no `UserEntry` (ADR-073) — it transcribes and compiles. "Journal" currently names
three things (this page, the Tasks+ Journal row = today's periodic note, `/journals` discussions). Recommended YES
in the review; a rename of the `SidebarItem` label + page title, own S PR.

## 7. PWA first-run

`AuthPage` renders no manifest, service-worker registration or offline banner, so the app is not installable before
login and a standalone launch on an expired session lands on chrome-less login. Needs a real device after the
DigitalOcean unpark to measure; the fix is `AuthPage` carrying `pwa_headers()`.
