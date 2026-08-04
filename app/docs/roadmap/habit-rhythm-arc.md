# Habit Rhythm Arc — Markwhen Resolution & the Time-of-Day Vocabulary

**Status:** ✅ COMPLETE (2026-08-04) — shipped as **#927** (PR 1, S1), **#933**
(PR 2, S2) and **#934** (PR 3, S3). Contract settled in the S5 Markwhen
exploration (the door `calendar-periodic-notes-arc.md` E4 deliberately left
open). Rulings M1–M7 below are founder-settled — do not re-litigate.
**Related:** `docs/roadmap/calendar-periodic-notes-arc.md` (E4, R5),
`docs/roadmap/calendar-act-from-arc.md` (C3 per-day habit completion;
hourly-grid non-goal), `core/models/habit/habit.py` (scheduling fields),
`core/models/enums/scheduling_enums.py` (`TimeOfDay`),
`core/services/calendar_service.py` (`_habit_to_calendar_item`),
`core/services/habits/habits_scheduling_service.py`,
`core/services/habit_event_scheduler.py`, `ui/calendar/components.py`
(week-view ordering). The deletion target — `ui/timeline/`,
`adapters/inbound/timeline_routes.py`, the timeline endpoints in
`adapters/inbound/visualization_api.py`, `static/vendor/vis-timeline/` — no
longer exists as of #934.

---

## Why this arc exists

The periodic-notes arc deferred one question (E4): should SKUEL read or render
the Markwhen timeline machinery in the founder's daily template? This arc is
that conversation, run artifact-first. The artifact read showed the machinery
was never a workflow: the three Templater export scripts were never written,
zero `.mw` files were ever produced, no renderer exists on either side
(Obsidian has no Markwhen plugin; the app's Markwhen viewer was replaced by a
Vis.js page in January 2026 that no navigation links to), and the founder
confirmed the authored blocks were "experimental testing, not much thought."

What the exploration surfaced instead is the real desire underneath: plan
habits forward, see the habitual week visually as the **rhythm of the day**,
and flip planned→completed with a tick. Every piece of that lands on entity
data plus the existing calendar — not on a timeline file format. Markwhen was
only ever needed while the *note* was the data carrier; with habitual time as
*entity* data, no timeline notation needs to exist anywhere.

## Founder rulings (settled 2026-08-03 — do not re-litigate)

- **M1 — One vocabulary of habitual truth.** Habitual time lives as data on
  the Habit entity — never as parallel note-text structure. "We want to avoid
  confusion here and unite with one language."
- **M2 — Markwhen retires.** E4's open door resolves as retirement, not
  adoption. No markwhen parsing, no markwhen rendering, no `.mw` export —
  on either side. (The vault-side template scaffolding is the founder's to
  clean; see Vault-side notes.)
- **M3 — Fuzzy blocks, not exact times.** "I do not need accurate start and
  end times for habits. I need blocks of space + time … it is more about
  duration than time and checking whether it was completed or not." Habit time
  = `TimeOfDay` slot + `duration_minutes`, and nothing finer. Slots only was
  ruled explicitly over slots-plus-optional-clock-time.
- **M4 — The habitual week is SEEN on the calendar week view via the Habits
  legend filter.** The founder's working filter set is Tasks / Events / Habits.
  Goals, Choices, Principles do not apply as weekly-calendar filters — a Goal
  or Choice reaches the grid only by being marked as an Event or Task. The
  Milestone kind ships as-is (#922); nothing here re-opens E1.
- **M5 — Visual = the rhythm of the day as an ordered sequence**, not
  time-proportional blocks on an hour axis. The hourly grid stays a non-goal
  (consistent with the act-from arc).
- **M6 — The backward look is the same picture.** Planned and completed are
  one display; the per-day completion tick (shipped in act-from C3) is what
  flips a habit chip from planned to completed. No separate review surface.
- **M7 — `/timelines` is deleted.** One Path Forward: the page is linked from
  nowhere, fed by fabricated times, and superseded by the weekly calendar as
  the ruled surface.

R5 note: because the rhythm renders from *entities*, the R5 line ("note
contents never render on the grid") is untouched — the tension the exploration
named dissolves rather than needing a new ruling.

## Verified ground truth (2026-08-03 artifact + code read)

- **The toolchain never ran.** Daily/weekly/monthly templates reference three
  Templater scripts (`mw_to_tasks_and_export` and week/month variants); none
  exists in the Templater user-script folder. Zero `.mw` files on disk; no
  `public/mw/` or `static/mw/` directories; every generated `MW_*` section in
  every specimen is empty. Exactly one daily note (2026-06-16) ever carried a
  bespoke markwhen block; the recurring "habit anchors" in it were the
  template's own unedited example lines.
- **No renderer exists anywhere.** The Obsidian vault has no Markwhen plugin
  (blocks render as plain code). The app replaced its Markwhen viewer with
  Vis.js Timeline in January 2026 (`ui/timeline/components.py`); the resulting
  `/timelines` page was registered but linked from no navigation — an orphaned
  surface fed by `get_calendar_view`. Deleted in PR 3 (#934).
- **Habit times were fabricated end to end** (FIXED in PR 2).
  `_habit_to_calendar_item` set `start_time=now` — the moment of the query —
  with a hardcoded 30-minute duration, ignoring the habit's own
  `preferred_time` and `duration_minutes`. It now derives the block from both.
- **`preferred_time` is a three-interpretation string.**
  `habit_event_scheduler.py` parses it as `"%H:%M"` clock time;
  `habits_scheduling_service.py` compares slot words ("morning"/"evening");
  and `ui/today/orchestrator.py` gates habits into Today's rituals and
  day-spine via `_parse_hhmm(h.preferred_time)` (a habit whose value doesn't
  parse as `HH:MM` is silently excluded — slot values would drop habits from
  Today entirely; Codex finding on this PR, code-verified). Live data holds
  `"evening"`, `"anytime"`, `"medium"` (a priority word — polluted), and
  null. The one-vocabulary defect M1 targets.
- **The fuzzy vocabulary already exists.** `TimeOfDay`
  (`core/models/enums/scheduling_enums.py:58`) defines EARLY_MORNING (5–7),
  MORNING (7–12), AFTERNOON (12–17), EVENING (17–21), NIGHT (21–24),
  LATE_NIGHT (0–5), ANYTIME — each with an hour range and a representative
  hour. M3's ruling maps onto it with no new enum.
- **The rhythm ordering already existed — but habit expansion bypassed it**
  (FIXED in PR 2). Both grids sort a day's chips chronologically by item start
  time. However, `_items_by_date` expanded each habit occurrence as an
  `all_day=True` chip re-stamped to midnight — so truthful times on the base
  item alone would still have clustered every habit at day start (Codex finding
  on PR 1, code-verified). PR 2 re-dates each occurrence through
  `habit_block_on`, one re-dating truth shared with the day-aware
  item-details stamp.
- **The tick already exists.** Act-from C3 shipped per-day habit completion on
  calendar chips — M6's mechanism is live.
- **Habit is file-ingestible** (`EntityType.HABIT` ingestion config), so
  markdown authoring of habit time = frontmatter on the habit's vault file
  (plus the app's habit form) — no new notation.
- **Live specimen of the split vocabulary:** `Meditate` and `Prep tomorrow`
  exist as Habit entities (daily, 15m, `preferred_time` null) *and* as
  markwhen anchors (07:00/20m, 21:30/10m) — same habitual truths, neither
  representation complete.
- **Vault-side defect (founder's side):** the current monthly template still
  carries the markwhen block and lacks `type: user_entry`/`pipeline`
  frontmatter, so monthly notes would not ingest (the Monthly folder is
  empty, so this has never bitten).

## What PR 1 found that this doc did not say (2026-08-03)

Recorded per the arc's standing rule that a PR updates this doc when its fresh
read contradicts or extends the ground truth.

- **The `"medium"` pollution has a live code writer**, not a stray hand-edit:
  `activity_domain_converters.py` set `preferred_time=activity.energy_states[0]`
  — an `@energy()` word into a time field. The upstream door is the LLM DSL
  bridge (`EXTRACT_ACTIVITIES`), and `@energy` values are unvalidated, so the
  migration alone would have been re-polluted on the next extraction. PR 1
  derives the slot from `@when()`'s hour instead; energy still reaches the habit
  as a tag. Live census: 5 Habit nodes, 0 HabitTemplate nodes, values
  `evening` / `anytime` / `medium` / null×2 — **no `HH:MM` value has ever been
  stored**, so the migration had nothing to preserve.
- **The `%H:%M` parse was unreachable.** `HabitEventScheduler._determine_strategy`
  only returns `FIXED_TIME` when the config's `default_strategy` is set to it,
  and the sole constructor uses the default (`OPTIMAL_TIME`). Fixing the parse in
  place would have been vacuous, so PR 1 also makes a declared slot *select*
  `FIXED_TIME`, outranking the keystone/category/tag heuristics — otherwise M1's
  vocabulary never reaches scheduling at all.
- **`_parse_hhmm` served nothing else.** Its docstring claimed it also handled
  `reminder_time`; it had exactly two callers, both `preferred_time`. Deleted
  outright, not split.
- **HabitTemplate had to move too.** `_spawn_orchestrator._copy_through` copies
  template fields into the instance **verbatim by name**, so a `str` template
  field would have written a raw string into the typed instance field with
  nothing to catch it. `HabitTemplate` / DTO / requests are retyped in PR 1.
- **`Habit.reminder_time` stays a string.** It is the habit's genuine clock-time
  field, with its own request/intent/set-clear stack. `preferred_time` is the
  slot; `reminder_time` is the clock. That split is the answer to "why is one
  time field an enum and the other not?".
- **`get_habits_by_time_of_day` never existed.** Documented in `docs/domains/habits.md`
  and `docs/reference/SEARCH_SERVICE_METHODS.md` since the initial commit, with
  zero implementations in any commit (`git log --all -S`). Both rows deleted.
- **`GRAPH_CONTRACT.yaml` does not carry scalar node properties**, so this change
  produces no contract drift and needs no regeneration.

## What PR 2 found that this doc did not say (2026-08-03)

Recorded per the arc's standing rule that a PR updates this doc when its fresh
read contradicts or extends the ground truth.

- **The chip must speak the SLOT WORD, not the representative hour.** S2 as
  written stops at deriving `start_time` from the slot; it does not say what the
  chip *prints*. Printing the derived hour re-fabricates exactly what this arc
  exists to end: `TimeOfDay.get_default_hour()` maps **MORNING and ANYTIME both
  to 9**, so "9:00 AM" would tell a founder who chose *anytime* that he
  committed to nine o'clock, and the clock string is strictly *less* informative
  than the slot word. The hour is not invertible, so the slot itself now rides
  on `CalendarItem.time_of_day` and the chip reads `Morning · 20m`. New:
  `TimeOfDay.get_label()`.
- **Null is unstated, not "Anytime".** ANYTIME's hour *places* an unstated
  habit; it must not *name* it. `time_of_day` is passed through unresolved and a
  slotless habit's chip reads `15m` alone — otherwise the calendar would assert
  a preference the user never expressed and contradict the two surfaces that
  already read null as unstated (`ui/activities/habits_views.py` renders no
  Preferred-Time row; `ui/today/orchestrator.py` drops the habit from the ritual
  spine). **2 of the 5 live habits carry no `preferred_time` property at all**,
  so this is the ordinary path.
- **`duration_minutes = 0` exists in the graph and is not API-creatable.**
  `habit.pause-and-name` stores `0`, while `HabitCreateRequest` declares
  `ge=1` — so a test built from the request model cannot reach it. A
  non-positive duration counts as unstated (a zero-length block is not a
  block). Not closed by PR 2: the same habit still renders **0m** on
  `/today` (`ui/today/orchestrator.py`, `int(h.duration_minutes or 0)`) and
  proposes **15** in `habits_scheduling_service`.
- **The month chip cannot carry the duration inline.** A month day column is
  pinned at ~93px (the grid is `min-w-[700px]` over 7 columns and pans rather
  than shrinking). Measured in headless Chrome at 375px, an inline duration tag
  cut the habit title box from 47.1px to **5.0px** — the habit's NAME vanished,
  and with it the C3 completion ✓, which `calendar.css` renders inside
  `.calendar-item-title::after`. The block rides in the month chip's tooltip;
  the week chip has its own line for it.
- **The within-day sort needed a HABIT-ONLY tiebreak.** Slots collide by design
  and nothing upstream orders habits — their fetch issues no `ORDER BY` — so
  three live habits at 09:00 would reshuffle between renders, with month and
  week (separate requests) able to disagree. Widening the tiebreak to *all*
  kinds silently re-sorted tasks: `_task_to_calendar_item` stamps **every**
  scheduled task 09:00 and every due-only task midnight, so they all tie and
  would have flipped from query order to alphabetical with milestones wedged
  between due tasks. `_item_order`'s secondary key is habits only.
- **`_stamp_habit_occurrence`'s times had no reader before this PR.** The modal
  always took the occurrence-day branch, so the stamp's `all_day`/times were
  inert. They are load-bearing now: the modal states the day *and* the block.
- **A scheduled Task can never be "an afternoon task."**
  `_task_to_calendar_item` stamps every scheduled task 09:00 (only a due date
  gives midnight). The PR 2 acceptance's before-an-afternoon-item case was
  therefore verified against an **Event** — the one kind carrying a real clock
  time — plus an evening habit below it.
- **The non-positive-duration guard is load-bearing for a boundary PR 2 does
  not own.** `visualization_service._calendar_item_to_visjs` flips
  `type="range"` → `"point"` with `end: null` when `end_time == start_time`.
  PR 3 deletes that consumer; don't delete the guard with it. *(Honoured in
  #934 — the consumer went, the guard in `calendar_service.py` stayed.)*
- **Pre-existing fragility, observed not fixed:** an entity whose Neo4j time is
  *zoned* (`time()` rather than `localtime()`) makes `datetime.combine` produce
  a tz-aware datetime, and the grid's chronological sort then raises
  `TypeError: can't compare offset-naive and offset-aware datetimes` for the
  whole week. Not reachable through the app's write path (services pass Python
  `time` objects, stored as `LocalTime`); surfaced by seeding a verification
  probe with `time('14:00')`.

## What PR 3 found that this doc did not say (2026-08-04)

Recorded per the arc's standing rule that a PR updates this doc when its fresh
read contradicts or extends the ground truth.

- **`./dev bloat` was structurally incapable of catching this deletion's
  orphans.** Its scope is events / service-methods / prompt-templates ONLY, so
  `ui/patterns/skeleton.py` was never in view: `SkeletonTimeline` going to zero
  consumers would have reported clean forever. S3's instruction to grep each
  shared piece by hand was the only working instrument. The same census also
  showed `SkeletonSidebarItem`, `SkeletonSidebar` and `SkeletonDomainView`
  already at **zero** consumers — pre-existing, not caused here, left alone.
  A clean bloat run is not evidence a component library has no dead entries.
- **`vis-network` and `vis-timeline` look like one family and are not.**
  `static/vendor/vis-network/` was hand-downloaded in `617e0641b` (v9.1.9) and
  appears in neither `package.json` nor `copy-vendor-libs.js`, while
  `vis-timeline` was an npm dependency copied by that script. They also never
  co-load, so the shared `window.vis` global is not contended. Dropping the npm
  package could not reach the lateral-relationship or explore graphs — but the
  shared prefix makes "delete vis-*" look far more dangerous than it was, and
  a name-based judgement would have got this backwards in either direction.
- **Deleting a read path can orphan an injected dependency, and nothing
  reports it.** `calendar_service` was passed into
  `VisualizationAggregationService` for `get_timeline_data` alone. Once that
  method went, the constructor parameter had zero readers — invisible to MyPy,
  to ruff, and to the bloat detector alike (constructor params are not in any
  detector's scope). Removed here, with `compose.py` and the Gantt integration
  fixture updated. When deleting a service method, check what its dependencies
  were injected *for*.
- **The Gantt half of this surface is orphaned too — and the docs claimed a
  component that never existed.** `frappe-gantt` is vendored but loaded by no
  page, and `/api/visualizations/gantt/*` has no UI consumer, so it is the same
  shape M7 ruled on for `/timelines`. The `chartjs` skill and
  `ui-development.md` both documented a `ganttVis()` Alpine component;
  `git`-wide there is no such registration. The false claim is corrected here.
  **Whether the Gantt surface follows `/timelines` is a founder ruling, not
  this PR's** — M7 names `/timelines` and nothing else.
- **`DOMAIN_ROUTE_CONFIG_PATTERN.md`'s route inventory was already wrong.** It
  claimed 38 files, listed 36 numbered entries (with duplicate and skipped
  numbers), against 29 modules actually declaring a `DomainRouteConfig`. Only
  the timeline entry and its section count were corrected; the re-audit is a
  separate job.

### Time vocabularies deliberately left alone (DECLINE list)

Seven independent hour→slot bucketings exist, no two agreeing. PR 1 unifies the
ones in the **habit** domain (`habits_scheduling_service`'s 12/17 split and
`HabitCompletion.completion_time_of_day`'s 5/12/17/21 split, both now
`TimeOfDay.from_hour`). The rest are out of scope and are **not** oversights:

- `Reflection.reflection_time_of_day` (5/12/17/21) — Principles domain.
- `event_event_handler_service` (6/12/17/21) — a log line, never persisted.
- `schedule_intelligence` (5/12/17/21) — user-context intelligence.
- `ContextualRecommendation.suggested_time_slot` — **cannot** be unified: it
  mixes slots with `"now"` / `"later"`.
- `EnergyProfile.chronotype` (`morning`/`evening`/`neutral`) — a person-type,
  not a time of day.
- `SchedulingStrategy.MORNING/EVENING` + `EventSchedulingConfig`'s
  `morning_start_hour` / `evening_start_hour`, and habit **tags** sniffed for
  `"morning"` / `"evening"` — scheduler heuristics, now outranked by a declared
  slot but not deleted.
- `ContextualHabitCompletionRequest.environmental_factors["time_of_day"]` — a
  free-form `dict[str, Any]` on a live route, unconstrained by design.
- `EventSchedulingConfig.default_duration_minutes` (PR 2's decline) — the same
  30 the calendar now reads from `HabitBlock.DEFAULT_DURATION_MINUTES`, left on
  its own literal. This list already fences the scheduler's knobs off, and at
  least five habit-duration defaults exist (15 in `habits_scheduling_service`
  and the DSL converters, a hardcoded 30 inside `habit_event_scheduler`'s
  routine builder that bypasses the config field anyway, and the Today
  orchestrator's `or 0`). Unifying them is a *scheduling* question, not a
  rendering one.
- `properties(habit)` in the UserContext MEGA-QUERY splats the raw stored
  string into `entities_rich["habits"]` with no coercion. No consumer reads the
  key today; a future one must not assume it is a `TimeOfDay`.

## Scope

- **S1 — One time vocabulary (PR 1).** `Habit.preferred_time` becomes
  `TimeOfDay | None` (field name retained — it reads truthfully; retype, don't
  rename). Migrate live values (`"evening"`→EVENING, `"anytime"`→ANYTIME,
  `"medium"`→null). Unify the consumers: the `%H:%M` parse path in
  `habit_event_scheduler` derives from the slot's representative hour; slot
  comparisons in `habits_scheduling_service` become enum comparisons; the
  Today orchestrator's `_parse_hhmm` gates (rituals filter + day-spine,
  `ui/today/orchestrator.py`) derive from the slot's representative hour
  instead of rejecting non-`HH:MM` values. Expose slot + `duration_minutes`
  in the habit create/edit form and verify both flow through vault
  frontmatter ingestion. The PR's fresh read maps the full consumer set (the
  events-side habit-integration readers included).
- **S2 — Truthful habit chips (PR 2).** `_habit_to_calendar_item` (and the
  occurrence generator's times) derive `start_time` from the habit's
  `TimeOfDay` representative hour and `end_time` from real
  `duration_minutes`, with ANYTIME/unset falling back to a stable default.
  The truthful times must survive occurrence expansion: `_items_by_date`
  re-stamped expanded habit chips to midnight/`all_day=True` — the expansion
  combines each occurrence date with the habit's representative time instead,
  and the day-aware item-details stamp keeps working. Chips surface the
  duration (e.g. "20m") — inline on the week chip (`Morning · 20m`), in the
  tooltip on the month chip, which has no room for it (see "What PR 2 found").
  Week-view day columns then order habits into the day's rhythm among tasks
  and events via the existing sort. **Shipped as #933.**
- **S3 — Delete `/timelines` (PR 3).** **Shipped as #934.** Remove the page, `timeline_routes.py`,
  the timeline endpoints and service methods
  (`get_timeline_data`/`get_tasks_timeline_data`, `format_for_visjs`/
  `format_tasks_for_visjs`, `VisTimelineConfig`), the `timelineVis` Alpine
  component, `static/css/timeline.css`, and `static/vendor/vis-timeline/`.
  The PR maps the exact blast radius before deleting (e.g. `SkeletonTimeline`
  and any shared helpers survive if other surfaces use them) and runs
  `./dev bloat` after.
- **Vault-side (no repo PR).** Offered to the founder, his vault, his call:
  fix the monthly template's ingestion frontmatter and strip the retired
  markwhen scaffolding from the monthly template. No personal vault content
  enters this repo either way.

## Non-goals

- A markwhen parser, renderer, or `.mw` export path — retired (M2), not
  deferred.
- Exact clock times on habits (M3 — slots only).
- A time-proportional hourly grid, day or week (M5; act-from non-goal stands).
- Habit rows in the weekly-note panel — A5's *visual* half now lives on the
  calendar week view (M4); the panel's backward-review half remains its own
  follow-up, gated on lived use.
- New legend kinds or filter vocabulary — the four-kind legend (#922) ships
  as-is; M4 is satisfied by the existing Habits filter.
- Re-litigating R1–R5, E1–E4, Monday-start/ISO rail, or any act-from choice.
- Entity creation from timeline-ish note text (E3's parse contract is
  untouched — checkbox lines + explicit `@context()` markers remain the only
  parse shapes).

## Standing conventions that bind every PR here

Fresh context per PR; branch from **updated** main (`git pull --ff-only`
first); `./dev format` + `./dev quality` + targeted tests; runtime
verification in headless Chrome against the live dev app (real Alpine,
screenshot, assert after 2 rAFs with
`--run-all-compositor-stages-before-draw`) plus a live-graph spot check where
data changes; commit → PR → Codex review → consideration note → merge
(standing authorization). All chips render — legend filters are the only
hiding mechanism. Vault sync stays human-initiated (ADR-070 D9). No personal
vault content in this public repo — specimen shapes only.

## PR plan (contract)

| PR | Scope | Acceptance (live case) |
|----|-------|------------------------|
| 0 | This doc (docs-only; summon Codex explicitly — the gate auto-passes docs PRs without a verdict) | Doc reflects M1–M7 + the E4 resolution; PR table matches the rulings |
| 1 ✅ #927 | S1 — `preferred_time: TimeOfDay \| None`; live-value migration; consumer unification (scheduler, scheduling service, Today orchestrator); form + frontmatter authoring | Live graph shows no non-enum `preferred_time` values after migration (the `"medium"` pollution is gone); setting "Meditate" to `morning` + 20m via the habit form persists both; a habit vault file with `preferred_time: evening` frontmatter ingests to `TimeOfDay.EVENING`; a slot-valued habit still appears in Today's rituals/day-spine (the `_parse_hhmm` gate no longer drops it); `./dev quality` green with all three former string interpretations gone |
| 2 ✅ | S2 — truthful habit chip times + visible duration, preserved through occurrence expansion | MET. Live week view, Thu 2026-08-06 (a NON-today day): `Meditate` renders `Morning · 20m` above a 2:00 PM event and an `Evening · 45m` habit, with nothing earlier than its own slot; a slotless habit renders `15m` at the ANYTIME fallback position; the C3 tick flips the chip (`data-completed`, `::after` = `" ✓"`, opacity 0.55) in week AND month; the `?date=` modal opens on `Monday, August 3, 2026 · Evening · 45m` and Mark Complete OOB-swaps. Headless Chrome at 1280px and 375px. **The chip states the SLOT WORD, not the derived hour** — see "What PR 2 found" |
| 3 ✅ #934 | S3 — delete `/timelines` and its feeding surface | MET. `/timelines`, `/api/visualizations/timeline`, `/api/visualizations/tasks-timeline`, `static/css/timeline.css` and both `static/vendor/vis-timeline/` assets all return **404** on the live app; timeline endpoints gone from `visualization_api.py`; `./dev quality` green (MyPy + Pyright + dead-code gate + npm audit) with 8092 unit tests passing; `./dev bloat` unchanged at 120 planned, no new findings; week AND month calendar grids render clean in headless Chrome at 1280px and 375px with PR 2's habit chips intact (`Meditate ✓` / `Morning · 20m` above a 2:00 PM event above `Prep tomorrow` / `Evening · 45m`). **`./dev bloat` could not have caught this PR's orphans** — see "What PR 3 found" |

Order run: 1 → 2 → 3 (2 depended on 1's truthful fields; 3 was independent).
Any PR that discovers a contract-breaking surprise updates THIS doc in the same
PR.

## Closure (2026-08-04)

All three PRs merged; M1–M7 are discharged. Habitual time is `TimeOfDay` +
`duration_minutes` on the Habit entity (M1, M3), the habitual week is seen on
the calendar week view through the Habits legend filter (M4), the rhythm renders
as an ordered sequence rather than an hour axis (M5), planned and completed are
one picture via the act-from C3 tick (M6), Markwhen is retired on the app side
(M2), and `/timelines` is gone (M7).

Left open by design, each gated on lived use rather than on work:

- **Vault-side cleanup** is the founder's — the monthly template still carries
  the retired markwhen block and lacks `type: user_entry`/`pipeline`
  frontmatter. No repo PR; no personal vault content enters this repo.
- **Habit rows in the weekly-note panel** (A5's backward-review half) remain a
  follow-up, per Non-goals.
- **The orphaned Gantt surface** (`/api/visualizations/gantt/*` + the vendored
  `frappe-gantt`, loaded by no page) is the same shape M7 ruled on, but M7 names
  `/timelines` only. It needs its own founder ruling — see "What PR 3 found".
- **The non-positive-duration follow-ups PR 2 named** are still open: the same
  habit renders `0m` on `/today` and proposes `15` in
  `habits_scheduling_service`.
