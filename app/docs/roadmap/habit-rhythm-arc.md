# Habit Rhythm Arc — Markwhen Resolution & the Time-of-Day Vocabulary

**Status:** 📋 STAGED (2026-08-03) — contract settled in the S5 Markwhen
exploration (the door `calendar-periodic-notes-arc.md` E4 deliberately left
open). Rulings M1–M7 below are founder-settled — do not re-litigate.
Implementation starts on the founder's go signal; PRs then run per the standard
multi-PR arc workflow (fresh context each).
**Related:** `docs/roadmap/calendar-periodic-notes-arc.md` (E4, R5),
`docs/roadmap/calendar-act-from-arc.md` (C3 per-day habit completion;
hourly-grid non-goal), `core/models/habit/habit.py` (scheduling fields),
`core/models/enums/scheduling_enums.py` (`TimeOfDay`),
`core/services/calendar_service.py` (`_habit_to_calendar_item`),
`core/services/habits/habits_scheduling_service.py`,
`core/services/habit_event_scheduler.py`, `ui/calendar/components.py`
(week-view ordering), and the deletion target: `ui/timeline/`,
`adapters/inbound/timeline_routes.py`, the timeline endpoints in
`adapters/inbound/visualization_api.py`, `static/vendor/vis-timeline/`.

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
  `/timelines` page is registered but linked from no navigation — an orphaned
  surface fed by `get_calendar_view`.
- **Habit times are fabricated end to end.** `_habit_to_calendar_item`
  (`core/services/calendar_service.py:846`) sets `start_time=now` — the moment
  of the query — with a hardcoded 30-minute duration, ignoring the habit's own
  `preferred_time` and `duration_minutes`.
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
- **The rhythm ordering already exists — but habit expansion bypasses it.**
  The week view sorts a day's chips chronologically by item start time
  (`ui/calendar/components.py:248`). However, `_items_by_date` expands each
  habit occurrence as an `all_day=True` chip re-stamped to midnight
  (`components.py:281-287`) — so truthful times on the base item alone would
  still cluster every habit at day start (Codex finding on this PR,
  code-verified). PR 2 must carry the representative times through occurrence
  expansion (and the day-aware item-details stamp) for the existing sort to
  produce the rhythm.
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
  currently re-stamps expanded habit chips to midnight/`all_day=True`
  (`components.py:281-287`) — the expansion combines each occurrence date
  with the habit's representative time instead, and the day-aware
  item-details stamp keeps working. Chips surface the duration (e.g. "20m").
  Week-view day columns then order habits into the day's rhythm among tasks
  and events via the existing sort.
- **S3 — Delete `/timelines` (PR 3).** Remove the page, `timeline_routes.py`,
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
| 1 | S1 — `preferred_time: TimeOfDay \| None`; live-value migration; consumer unification (scheduler, scheduling service, Today orchestrator); form + frontmatter authoring | Live graph shows no non-enum `preferred_time` values after migration (the `"medium"` pollution is gone); setting "Meditate" to `morning` + 20m via the habit form persists both; a habit vault file with `preferred_time: evening` frontmatter ingests to `TimeOfDay.EVENING`; a slot-valued habit still appears in Today's rituals/day-spine (the `_parse_hhmm` gate no longer drops it); `./dev quality` green with all three former string interpretations gone |
| 2 | S2 — truthful habit chip times + visible duration, preserved through occurrence expansion | In a live week view, "Meditate" (morning, 20m) renders before an afternoon task and after nothing earlier, with "20m" on the chip — verified on a NON-today day (proving expansion carries the time, not just the base item); an ANYTIME habit still renders (stable fallback position); the C3 completion tick still flips the chip and the day-aware modal still opens with its `?date=`; headless-Chrome verified in week AND month views |
| 3 | S3 — delete `/timelines` and its feeding surface | `/timelines` returns 404; timeline endpoints removed from `visualization_api.py`; no dangling imports (`./dev quality` green); `static/vendor/vis-timeline/` gone; `./dev bloat` reports no new dead code; calendar views unaffected in headless Chrome |

Suggested order 1 → 2 (2 depends on 1's truthful fields); PR 3 is independent
and may run any time. Any PR that discovers a contract-breaking surprise
updates THIS doc in the same PR.
