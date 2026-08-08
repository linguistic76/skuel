# Gantt Visualization Surface — Staged, Not Abandoned

**Status:** 🅿️ STAGED (founder ruling 2026-08-04). The Frappe Gantt surface is
**deliberately kept** for future development. It is NOT a deletion candidate and
does NOT follow `/timelines` (deleted in #934). Founder: *"this is an area I am
keen on, it has not developed yet, I got started but have not done anything with
it. I want to incorporate in the future… I just know I want to be able to use its
power for visuals."*

**Related:** `adapters/inbound/visualization_api.py` (the two live endpoints),
`core/services/analytics/visualization_aggregation_service.py` (fetch),
`core/services/visualization_service.py` (format),
`core/ports/query_types.py` (`GanttConfig` wire type),
`scripts/copy-vendor-libs.js` (vendor pipeline),
`docs/roadmap/done/habit-rhythm-arc.md` (M7 / #934 — the sibling surface that WAS deleted),
`docs/roadmap/done/js-dependency-surface.md` (the JS dependency record ADR-067 defers to).

---

## Why this document exists

The Gantt surface had no home. `/api/visualizations/gantt/*` is live and
route-registered, its service chain is maintained and bug-fixed, and yet nothing
in the tree recorded that it exists, why it is unwired, or what it would take to
use it. That absence is what made it look like a deletion candidate during the
habit-rhythm arc — twice, on false premises (see *Corrections* below).

This doc is the record. **One Path Forward deletes the abandoned, never the
staged** — this surface is now explicitly the latter.

## Founder ruling (2026-08-04 — do not re-litigate)

- **G1 — The Gantt surface is STAGED.** It is kept, not deleted. Any future
  audit that finds `/api/visualizations/gantt/*` without a UI consumer should
  read this document and stop, not open a deletion PR.
- ~~**G2 — Target `frappe-gantt` 0.6.1, not 1.2.2.**~~ **REVISED 2026-08-05 — now
  target 1.2.2.** The "deliberate, separately-scoped, never opportunistic" half of
  the ruling stands and was honoured: the bump landed as its own PR (#949) with all
  three breaks handled, not as a routine dependency update. Only the *target* changed.
  1.x also gains native milestone rendering, which 0.6.1 cannot do at all (a
  milestone is `start == end`, i.e. a zero-width rectangle).
- **G3 — Do NOT register any Gantt symbol in the bloat detector's PLANNED
  tiers.** Empirically tested: the methods are reachable from a registered HTTP
  route, so `detect_bloat.py` never reports them, and a PLANNED entry is
  immediately reported as a *stale marking* — strictly worse than no entry. This
  doc is the completion backlog instead.

## Verified history — built, shelved, then swept

The surface was **fully wired once**, and lost its front half as collateral
damage. It was never an abandoned half-idea.

| When | Commit | What happened |
|------|--------|---------------|
| 2026-01-25 | `15e148778` | Initial commit. `ganttVis` Alpine component live at `static/js/skuel.js:749`, mounted via `x-data` on a Goals visualization page; `frappe-gantt` vendor assets committed under `static/vendor/frappe-gantt/`. |
| 2026-03-28 | `327f26623` | Activity-Domain shelving. Vendor assets **moved** (`R100`, byte-identical blobs) into `app/_shelved/activity_ui/`; `ganttVis` deleted from `skuel.js` along with 11 other Alpine components. Frappe Gantt vendor is named explicitly in the commit message — deliberate at this step. |
| 2026-03-30 | `ed8cbeadf` | `_shelved/` retired (93 files, ~22k lines). The Gantt assets died here as part of the sweep, **not individually named** — collateral. |
| 2026-06 | #201 | Two genuine phantom-method bugs in the aggregation layer fixed, with real-Neo4j integration guards. |
| 2026-07 | #846/#847/#848 | Goal progress reader fixed (the 0%-bar bug). **Not motivated by a Gantt consumer** — incidental fallout from a shared-reader audit. |
| 2026-08-04 | #934 | `/timelines` deleted. Gantt deliberately spared pending this ruling. |

**Nobody ever decided to drop the Gantt.** It rode along with the Activity
Domain CRUD UI shelving.

## What is verified true today

Everything below was verified by reading code, executing the formatter, or
querying the live dev graph — not inferred from filenames.

### The backend is live, correct, and tested

- Two registered endpoints: `GET /api/visualizations/gantt/tasks` and
  `GET /api/visualizations/gantt/goal/{goal_uid}` (`visualization_api.py`).
- Both are auth-gated (verified 401).
- **The goal endpoint is NOT an IDOR.** It ownership-scopes via
  `goals_service.get_for_user(goal_uid, user_uid)` and returns a 404
  byte-identical to a nonexistent UID. Its task fan-out was hardened against
  cross-user leakage in `f56fabfe5`.
- Two real-Neo4j integration guards pass (`tests/integration/test_gantt_aggregation_roundtrip.py`).
- The dangling-dependency guard in the dependency wiring is correct and deliberate.

### The wire contract matches the library exactly

> **Superseded 2026-08-05 by the bump to 1.2.2 (#949).** The findings below were
> verified against 0.6.1 and are kept as the historical record of *why* the surface
> was judged sound; three of them are no longer descriptions of `main`. Current
> state is in the § "0.6.1 → 1.2.2 delta" section, which #949 acted on.

Verified against the real `frappe-gantt` 0.6.1 source, not documentation:

- All **7 task keys** SKUEL emits (`id`, `name`, `start`, `end`, `progress`,
  `dependencies`, `custom_class`) match 0.6.1's expected task object, including
  the 0–100 progress scale. *(Still true in 1.2.2 — the key names did not change;
  what changed is that `custom_class` must now be a single whitespace-free token,
  pinned by a test since #949.)*
- All **5 option keys** in the emitted `options` dict match 0.6.1's defaults
  key-for-key. *(No longer: 1.2.2 dropped `popup_trigger` and `custom_popup_html`,
  so #949 emits 3.)*
- The dist bundle exposes a plain global `Gantt` — the same integration shape as
  Chart.js's global `Chart`. *(Still true — the UMD build 1.2.2 ships does the same.)*
- ~~`scripts/copy-vendor-libs.js`'s declared source paths are **correct** for
  0.6.1. The vendor pipeline is not broken.~~ *(No longer: the `.min.*` files it
  named vanish in 0.9.0. Repointed at the UMD build in #949.)*
- ~~The deleted vendor blobs are byte-identical to what npm 0.6.1 ships, so
  recovery is `npm install && npm run vendor:copy` with zero code changes.~~
  *(Recovery still works, but against 1.2.2's `.umd.js`/`.css`.)*
- `npm audit` is clean — no security pressure to upgrade. *(Still true at 1.2.2.)*

### What is absent (expected, not defective)

No vendor asset on disk, no `ganttVis` component, no UI route
(`VISUALIZATION_CONFIG` sets `ui_factory=None`), no nav entry, no CSS. This is
the staged state.

## Defects to fix before the surface is demoed

These are **real correctness bugs in live, route-reachable code** — they produce
a *wrong* chart, not merely an unrendered one. Ordered by severity.

| # | Defect | Location | Fix |
|---|--------|----------|-----|
| D1 | **Zero-length task bars.** A task with `due_date` and no `scheduled_date` — the ordinary SKUEL shape — makes start == end. Renders as an invisible sliver. | `visualization_service.py:428-429` | Copy the guard from its own sibling at `:314` (`if task.due_date and task.due_date > start_date`). |
| D2 | **Inverted bars (end before start).** `scheduled_date > due_date` (an overdue task rescheduled forward) yields a negative-duration bar. | `visualization_service.py:428-429` | Same one-line guard as D1. |
| D3 | **Ingested tasks are invisible to the goal Gantt.** `get_tasks_for_goal` reads the node *property* `fulfills_goal_uid`; the ingestion door writes only the `FULFILLS_GOAL` *edge*. Two writers disagree; the reader sees one. Live graph: 2 `FULFILLS_GOAL` edges, 0 nodes with the property. | `tasks_search_service.py:84` | Read the edge, or dual-read. **The integration test cannot catch this** — its fixture uses the property-writing API path. |
| D4 | **Empty task list returns an ERROR, not an empty chart.** First UI load would show an error toast. | `visualization_service.py:304-305` | Return an empty `GanttConfig` instead of `Result.fail`. |
| D5 | **Progress is a constant 50%** for every ACTIVE task. The branch computing a real number is unreachable on the normal lifecycle (`actual_minutes` is only stamped at completion, which the COMPLETED branch catches first). | `visualization_service.py:471-476` | Return 0 for ACTIVE-without-evidence, or write `actual_minutes` on a real progress path. A fallback may *place* a bar; it must not *name* a value. |
| D6 | **`priority-None` CSS class.** The `getattr(task, "priority", Priority.MEDIUM)` default is unreachable (the field is always declared), so an unset priority stringifies to `None`. Bites vault-ingested tasks specifically. | `visualization_service.py:545` | `or Priority.MEDIUM` instead of the getattr default. Same dead-default class as the #846 defect. |
| D7 | **Duration arithmetic can only ever yield a 1-day bar.** `// (8 * 60)` floors to 0 or 1 for every API-reachable `duration_minutes` (capped at 480). A 5-minute and an 8-hour task render identically. | `visualization_service.py:317` | Scale in hours, or drop the pretence and document 1 day as the unit. |
| D8 | **The milestone branch is a phantom API.** It calls `.get()` on `milestones: list[dict]`, but `Goal.milestones` is `tuple[Milestone, ...]` — a frozen dataclass — and all four field names differ (`id`/`uid`, `name`/`title`, `date`/`target_date`, `completed`/`is_completed`). Passing the real data raises `AttributeError`. Also unreachable: `get_goal_gantt_data` never passes milestones. | `visualization_service.py:443-455` | Reconcile to the `Milestone` dataclass. High value — the data already exists and is populated. |
| D9 | **Milestone ids collide** and interpolate user text into the id space (`id=ms.get("id", f"ms_{ms.get('name','milestone')}")`). Two unnamed milestones get the same id. | `visualization_service.py:448` | Fix with D8, same branch. |
| D10 | **Fetch/render date disagreement.** The fetch window keys on `due_date` only; the formatter prefers `scheduled_date`. In the live graph the two populations are strictly disjoint, so 4 scheduled-only tasks can never enter the chart. | `visualization_aggregation_service.py:213-218` | `date_field=["due_date","scheduled_date"]` — the builder already supports OR semantics and the calendar already uses it that way. |

Also noted, not defects: both readers cap at 100 rows ordered by `created_at DESC`
(an arbitrary truncation for a timeline), and the dependency loop is N+1 against
the graph.

## Data readiness — the surface would render nothing today

Live dev-graph census (positive control confirmed — the same query returns 16
rows for a Jun–Jul window):

- **91 Tasks**, of which **85 are completed** and **71 have no date at all**.
- **0 tasks** fall inside the Gantt's `[today-7, today+60]` window. The latest
  `due_date` in the entire graph is 2026-07-11; the window opens 2026-07-28.
- **0 `DEPENDS_ON` edges** exist anywhere — no dependency arrow can ever render.
- **0 of 3 Goals** have a `target_date` — every goal bar would be a synthetic
  90-day default.

**Implication:** fixing the code is necessary but not sufficient. Forward-dated
task data has to exist before a Gantt shows anything worth looking at. D4 is what
turns "empty" from an error into an honest empty state.

## Ordered path to a rendering Gantt

Each step names the live pattern to copy. Nine artifacts.

| # | Step | File | Pattern to follow |
|---|------|------|-------------------|
| 1 | `npm install` | — | `node_modules/` is currently **empty** — this blocks `vendor:copy` *and* the whole JS test suite. |
| 2 | Restore vendor asset | `static/vendor/frappe-gantt/` | `npm run vendor:copy` — correct for **1.2.2** since #949 (`frappe-gantt.umd.js` + `.css`; the `.min.*` paths this once used no longer exist upstream). ⚠ It `mkdir`s the dest **before** checking the source, so the directory looks plausible even when the copy failed — read the exit code, not the directory. |
| 3 | Fix D1–D10 | `visualization_service.py`, `visualization_aggregation_service.py` | The guard at `:314` is the in-file precedent for D1/D2. |
| 4 | Revive `ganttVis` | `static/js/skuel.js` | Recoverable verbatim: `git show 4fb1ea37e:app/static/js/skuel.js \| sed -n '1224,1315p'`. ⚠ Written against the 0.6 option API — matches G2. |
| 5 | Register in smoke test | `scripts/smoke_test.py` `_REGISTRY_COMPONENTS` | **Mandatory** — `_assert_registry_in_sync()` fails otherwise. ⚠ The fixture never loads frappe-gantt, so `ganttVis` must not touch the `Gantt` global at `init()`. |
| 6 | UI route | `adapters/inbound/` | `VISUALIZATION_CONFIG` currently sets `ui_factory=None`. |
| 7 | Page/component | `ui/` | **Chart.js is the correct precedent** — opt-in per-page via `extra_scripts`. ⚠ **Not** vis-network: that is hand-committed and loaded unconditionally in `build_head()` on every page. |
| 8 | Nav entry | navigation config | Otherwise reachable only by typing the URL — exactly how `/timelines` became orphaned. |
| 9 | CSS | `static/css/` | `_get_gantt_class` emits classes (`completed`, `in-progress`, `blocked`, `priority-*`, `milestone-bar`) that have **zero rules** anywhere — in the repo or in frappe-gantt's own stylesheet. |

**Library constraints to respect:** frappe-gantt's constructor mutates the DOM
around its wrapper and has **no `destroy()`** — re-init leaks, so an HTMX-swapped
fragment must be swap-aware. Its stylesheet is hardcoded light-theme hex with no
CSS variables.

**Useful artifact:** the #934 deletion diff (`d5308df74`) is a verified, complete
*inverse checklist* of everything a visualization surface touches in this
codebase.

## The 0.6.1 → 1.2.2 delta (recorded for a future decision — **TAKEN in #949**)

All three were handled in **#949**; each entry records what broke and how it was
resolved, so the analysis stays checkable rather than becoming folklore.

1. **Dist filenames change.** ⚠ **This lands in 0.9.0, not 1.x** — corrected
   2026-08-05 against `npm pack`, having originally been recorded as a 1.x change.
   0.9.0 and 1.2.2 both ship `frappe-gantt.umd.js` / `.es.js` / `.css` with no
   `.min.*`. `copy-vendor-libs.js` resolved `.min.js`/`.min.css` by exact filename,
   so #943 (which took 0.6.1 → 0.9.0) broke `npm run vendor:copy` on `main` until
   #949 repointed it at the UMD build. The error is loud — "Source not found",
   `exit 1` — but the destination directory is created *before* the source check,
   so the directory itself looks plausible afterwards.
2. **`custom_class` becomes single-valued.** `src/bar.js` applies it with
   `classList.add()`, which raises `InvalidCharacterError` on a token containing
   whitespace — the chart dies rather than degrading. `_get_gantt_class` emitted
   `"in-progress priority-high"`. #949 returns exactly one token: status first,
   priority as the fallback so a task with no distinguishing status still carries
   information. The value had **no test in either direction** — switching from two
   classes to one broke nothing — so #949 added a parametrised value pin over the
   whole status × priority grid, RED-proved at 12 of 20 cases failing against the
   old behaviour.
3. **Two emitted option keys were renamed/removed:** `popup_trigger` and
   `custom_popup_html` are absent from 1.2.2's `DEFAULT_OPTIONS`; popups are a
   `popup` callback, which cannot be expressed in a JSON payload. #949 stopped
   emitting them rather than advertise a contract the library no longer honours.
   `view_mode`, `date_format` and `language` all survive.

**Argument in favour of eventually bumping:** 1.x supports milestones natively.
0.6.1 has no diamond mark — it draws one rectangle per task sized by the date
delta, so a milestone (start == end) is a zero-width rectangle and would be
invisible without custom CSS (see D8/D9).

⚠ ~~`^0.6.1` is a caret range on a `0.x` major, so it resolves `>=0.6.1 <0.7.0` —
no routine `npm install`/`ci`/`update` can reach 1.x. The bump requires a
deliberate hand edit. There is no ambush risk.~~

**FALSIFIED 2026-08-05 — and worth keeping as a worked example.** The semver
reasoning was correct; the threat model was not. It enumerated the tools that
*resolve within* a declared range (`npm install`/`ci`/`update`) and concluded
safety — but a dependency bot does not resolve within the range, it **rewrites
the range**. Renovate's npm manager was enabled on 2026-08-05 (#941) and its
first JS PR, #943, proposed `^0.6.1 → ^0.9.0` and was merged, carrying the
dist-filename break above onto `main`. Filed as "js minor/patch", correctly:
semver says `0.6 → 0.9` *is* a minor. On a `0.x` package the minor position is
where breaking changes live, so "minor" and "safe to merge routinely" are not the
same claim.

The generalisation: *"no routine command can reach X"* is only as strong as the
enumeration of routine commands, and that enumeration silently went stale the
moment a new actor gained write access to the manifest.

**The options dict is unpinned by tests**, so these version-coupled option names
are invisible to CI. Pinning them is cheap insurance before any bump.

## Corrections this document supersedes

Two claims published to `main` in #934 (`d5308df74`) were false and are corrected
here and in `habit-rhythm-arc.md`:

1. ❌ *"the docs claimed a component that never existed"* — **false.** `ganttVis`
   existed from `15e148778` to `327f26623`. The docs were describing real code
   that was deleted out from under them.
2. ❌ *"`frappe-gantt` is vendored but loaded by no page"* — **false.** It is not
   vendored: the assets left in `ed8cbeadf`, and the npm package is not installed.

The reasoning that put the Gantt in a deletion frame rested on premise (1). With
it corrected, the surface reads as an interrupted feature, not vapour.
