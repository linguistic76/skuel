# Calendar Act-From Arc — Design & Choices

**Status:** CONFIRMED 2026-08-02 (founder ruling: "I want the calendar to be a place that
I act from") — scoped 2026-08-02 after live-graph verification + full code-path read
(routes → service → query builder → components). This document is the arc's source of
truth; each PR runs in a fresh context against it. **PRs 1–5 shipped 2026-08-02
(#913–#917). C6 ruled at its own elicitation later that day — see C6 and PR table row 6.**
**Related:** `core/services/calendar_service.py`, `adapters/inbound/calendar_ui.py`,
`ui/calendar/components.py`, `scripts/detect_bloat.py` (`_CALENDAR_EDIT_SURFACE` PLANNED
tier), the #623 all-chips-visible ruling, the Monday-start ISO-rail ruling (PERMANENT).

---

## Intent

The calendar today is a read-only projection — and a partially wrong one. This arc makes
it truthful (everything that should render, renders, consistently across views) and then
makes it **actable**: completing habits per-day, rescheduling tasks/events — un-staging
the three PLANNED calendar-edit methods (`quick_create`, `reschedule_item`,
`record_habit_occurrence`) that have waited since the 2026-07-12 redesign for exactly
this decision. (Outcome: two were wired in PRs 3–4; `quick_create` was superseded by
the C6 ruling and is deleted, not wired — see C6.)

## Founder ruling (2026-08-02 elicitation)

**The calendar is a surface to act from**, not just a temporal overview. This settles
the arc's center of gravity: the habit-completion loop (PR 3) is the heart; truthful
display (PRs 1–2) is its prerequisite; reschedule (PR 4) and truthful legend + dead-code
removal (PR 5) complete it. Quick-add (PR 6) was elicit-before-build; RULED 2026-08-02
at elicitation #2 — the settled design is in C6. No further elicitation gates remain.

## Verified ground truth (2026-08-02, live dev graph + code read)

- **Live corpus (user_linguistic76):** 3 active habits, all `recurrence_pattern="daily"`
  (`habit_8036b07d`, `habit_3696b8a1`, `habit_e1f401b7`); 89 tasks — 16 with `due_date`
  (June 16–Jul 11, ALL completed), 4 with `scheduled_date` (Jul 6/15, completed, and
  **scheduled-only** — no due_date); 5 events all Jul 1–4; 2 goals, neither with a
  `target_date`. Two further habits + 2 tasks + 1 event belong to `user_admin`
  (ownership scoping verified working).
- **Defect 1 — month edges are data-blind:** `/cal/month/{y}/{m}/content` fetches
  strictly the 1st→last of month (`calendar_ui.py:204-211`) but `create_month_grid`
  renders lead-in/tail cells from the Monday on/before the 1st. Those cells get day
  numbers, never data — visibly inconsistent with the week view of the same days.
  `_fetch_habits`'s "keeps month and week consistent" fix (`calendar_service.py:443-461`)
  is undercut at month edges by the route's fetch window.
- **Defect 2 — scheduled-only tasks can never render:** tasks fetch with
  `date_field="due_date"` only (`tasks_service.py:271` DomainConfig →
  `build_user_activity_query`), yet `_task_to_calendar_item`
  (`calendar_service.py:483-520`) explicitly renders `scheduled_date`-first as
  TASK_WORK. A task with `scheduled_date` and no `due_date` (4 exist live) is never
  fetched. Only invisible today because those 4 are completed.
- **Defect 3 — habit action loop unreachable:** `_opens_detail_modal`
  (`components.py:254-262`) makes habit chips display-only (a synthesized occurrence
  can't tell the modal its day), so the habit item-details modal, its "Mark Complete"
  button, and `POST /cal/habit/{uid}/complete` are unreachable; grep confirms no other
  caller. `_create_occurrence` hardcodes `CompletionStatus.PENDING` — completed days
  render identically to missed ones.
- **Defect 4 — parallel dead converters:** `ui/calendar/converters.py` is imported ONLY
  by `tests/unit/ui/test_calendar_converters.py`. Its recurrence logic contradicts the
  live service (weekly → Monday, monthly → 1st; service anchors to habit inception,
  correct). Superseded, not staged → delete per One Path Forward.
- **Defect 5 — legend advertises Milestone; nothing emits it:**
  `CalendarItemType.MILESTONE` has color/label/icon but no producer in the calendar
  pipeline. Goals are the natural source and `goals_service` already configures
  `date_field="target_date"` — `get_user_items_in_range` works unmodified.
- **Staged plumbing verified real (no phantoms):** `CalendarService.record_habit_occurrence`
  → `habits_service.track_habit` (`_CompletionMixin`, takes `TrackHabitRequest` with
  `completion_date`) → per-date completion. `reschedule_item` mutates via typed
  ADR-066 intents, preserves event duration. `get_completions_for_habit(habit_uid,
  start_date, end_date)` exists for per-range completion state (3 habits live — N-queries
  acceptable; bulk later if habit count grows). All three edit methods registered in
  `PLANNED_METHODS` under `_CALENDAR_EDIT_SURFACE` — un-register as each is wired.
- **Query-builder seam:** `build_user_activity_query`
  (`domain_queries.py:963`) validates identifiers and applies the #766 temporal idiom
  (`left(toString(n.field), 10)` before `date()`) — the OR-of-two-date-fields extension
  (PR 2) must reuse that idiom for BOTH fields.
- **Composition:** `CalendarService(tasks, events, habits)` built at
  `services_bootstrap/compose.py:815` — PR 5 adds `goals_service` here.
- **Stale docstring:** `calendar_routes.py:8` claims calendar_api.py wires
  "quick-create, item details, reschedule" — only GET item-details exists. Becomes true
  again as PRs 3–4 wire actions; fix the docstring in whichever PR lands the claim.
- **Data observation (NOT this arc):** duplicate live tasks ("Visa 4 India" ×2,
  "move furniture" ×2, "DrJoffe" ×2) — likely double ingestion; separate care session.

## Choices

**C1 — Month view fetches the full visible grid.** Chosen: the month content route
computes `grid_start` (Monday on/before the 1st) and `grid_end` (Sunday of the last
rendered week) and fetches THAT range; lead-in/tail cells become fully data-bearing
(Google-calendar convention; the founder-observed inconsistency dies). ⚠️ Gotcha:
`create_month_grid` currently derives "the month" from `calendar_data.start_date` — with
a widened fetch range that inference breaks. Pass the focus month explicitly
(`create_month_grid(calendar_data, year, month)`) and derive in/out-of-month tone from
it, not from `start_date`. *Rejected:* rendering out-of-month cells deliberately blank
(hides real data; contradicts the week view); fetching per-cell (N+1).

**C2 — Tasks fetch matches EITHER date field.** Chosen: extend
`build_user_activity_query` with OR-of-multiple-date-fields (e.g. `date_field:
str | list[str]`, OR semantics, each field through the #766 idiom, `validate_identifier`
on every field), thread through `user_activity_range_raw` →
`get_user_items_in_range_base`; Tasks' calendar fetch asks for
`["due_date", "scheduled_date"]`. Placement/type stay as-is in
`_task_to_calendar_item` (scheduled → 9am work chip; due-only → all-day deadline).
*Rejected:* two fetches + Python dedupe in CalendarService (two round-trips, dedupe
code, and the builder extension is small); changing Tasks' DomainConfig `date_field`
globally (would silently alter every other range consumer — calendar-only concern).

**C3 — Habit chips know their day; the completion loop closes.** The arc's heart.
Chosen:
- `_items_by_date` expansion stamps each habit chip with its occurrence date; chips
  become interactive again (`_opens_detail_modal` returns True for habits), fetching
  `/cal/item-details/{item_id}?date=YYYY-MM-DD` (query param per FastHTML convention).
- The modal shows THAT day (title, streak, that-day status) and "Mark Complete" posts
  the date to `POST /cal/habit/{habit_uid}/complete` (form field `on_date`), which now
  calls `calendar_service.record_habit_occurrence` (un-staging it) instead of
  today-only `record_completion`. Guard: no future-date completions (server-side; the
  button is disabled/absent on future chips).
- `_generate_habit_occurrences` gains real state: completions per habit fetched via
  `get_completions_for_habit(habit, view_start, view_end)`; occurrence status =
  COMPLETED when a completion exists that day, else PENDING. Completed chips render
  visually distinct (✓ / dimmed via a `data-` attribute + calendar.css); the modal's
  Mark Complete becomes "Completed ✓" state for already-done days.
- Un-register `record_habit_occurrence` from `PLANNED_METHODS`.
*Rejected:* per-chip inline checkbox without a modal (loses the streak/details surface
already built; can be a later refinement); reconstructing the day server-side from
"today" (the exact bug that made chips display-only).

**C4 — Reschedule from the item modal.** Chosen: task/event item-details modal gains a
date (+ time, events) input posting to a new `POST /cal/item/{item_id}/reschedule`
(CSRF-protected, form-encoded) → `calendar_service.reschedule_item` (un-staging it;
ownership already enforced in-service, not-found on non-owner). Response swaps the
calendar content fragment so the chip visibly moves. Un-register from `PLANNED_METHODS`.
*Rejected:* drag-and-drop (real JS scope; the modal path proves the loop first —
drag-drop can layer on later WITHOUT contract changes since the endpoint is the same);
rescheduling habits (habits recur, they don't reschedule).

**C5 — Truthful legend: goals become Milestones; dead converters die.** Chosen:
`CalendarService` gains `goals_service: GoalsOperations` (compose.py:815) +
`_fetch_goals` (existing `get_user_items_in_range`, `target_date` config) +
`_goal_to_calendar_item` emitting `CalendarItemType.MILESTONE` (all-day, 🎯, #9333ea) —
every legend entry now has a producer. ⚠️ Gotcha (Codex, #911): `_opens_detail_modal`
admits every non-habit type, so milestone chips are clickable the moment they exist —
but `get_item` parses only `task-`/`event-`/`habit-` prefixes, so a click would open
"Calendar item not found". C5 therefore ALSO adds owner-scoped `goal-` handling to
`CalendarService.get_item` (same not-found-on-non-owner pattern as the other three) and
a "View Goal" action (`/goals` detail link) in the modal. Delete `ui/calendar/converters.py` +
`tests/unit/ui/test_calendar_converters.py` (superseded → delete, per the
deletion-campaign protocol; the service's occurrence generator is the one path).
*Rejected:* dropping Milestone from the legend (goals-on-calendar gives the act-from
surface forward pull for free); porting any converter logic first (verified drifted and
wrong).

**C6 — Day-click acts: the day lens is the entry point; `quick_create` dies superseded.**
RULED 2026-08-02 (founder elicitation #2; supersedes the staged-elicit-first text that
stood here). The entry-point tension resolved by re-routing the click, not by adding a
new affordance to the grid:
- **Day-cell click → `/today/{date}`** (the existing day lens from the Today↔Calendar
  arc) — month grid cells AND week-view day cards, keeping the `closest()` guard so
  chips/links stay independently clickable. Past days navigate too (reviewing a past
  day is legitimate; the lens is always meaningful).
- **Daily-note doors:** the per-cell date-number link to `/journals/daily/{date}` STAYS
  (the always-nearby door). The Month AND Week toolbars gain a **"Daily note"** button
  (today's note) beside their period-note button — completing the Daily/Weekly/Monthly
  family. This pre-resolves the calendar side of periodic-notes S2 (visible note-doors).
- **Quick-add is TASKS ONLY and lives on the day lens**, not in a calendar modal: an
  add-a-task affordance on `/today/{date}` creating with `scheduled_date` = viewed day
  and **no `due_date`** (work-chip semantics — founder: "it's I'll work on it that
  day"). The affordance is absent on past-day lenses AND the POST refuses past dates
  server-side. Events keep the Create-an-Event page; the day lens may carry a
  date-prefilled "Create event for this day" link.
- ⚠️ **Day-lens membership must widen with it** (Codex, #918): the lens currently
  selects tasks by `due_date == view_date` ONLY (`ui/today/orchestrator.py:254-256`) —
  a scheduled-only quick-add would vanish from the very lens that created it on
  refresh. PR 6 widens the lens's day membership to `scheduled_date` OR `due_date`
  (mirroring the calendar's C2 semantics). The triage bar stays due-based — it speaks
  deadline language, not work-plan language.
- ⚠️ **Defer moves the date that put the task on THIS day's lens** (Codex, #918
  rounds 2–3): the current handler always shifts `due_date`, inventing one from today
  when absent (`adapters/inbound/today_routes.py:170-175`) — under the widened
  membership a deferred scheduled-only task would reappear on its work date carrying a
  phantom deadline. And a fixed "always move the work date" rule fails the both-dates
  case: such a task is a member of TWO lens days, and deferring it from its due-day
  lens must move the deadline, not the work date, or it bounces back on refresh.
  Therefore: the defer POST carries the lens's `view_date`; the handler moves the
  field(s) equal to `view_date` (both, when both match that day). When NO field equals
  `view_date` — the triage case: an overdue task surfaces on today's lens regardless
  of its dates (`ui/today/orchestrator.py:259-268`) — defer moves `due_date` (triage
  speaks deadline language; this subsumes the due-only fallback and covers overdue
  both-dates tasks, Codex round 4). Date-ordering invariant preserved: a defer that
  would push `scheduled_date` past `due_date` is refused with the same
  work-date-past-deadline message family as C4's reschedule guards. The lens client
  currently hides the card and toasts success BEFORE the POST with no error callback
  (`static/js/today.js:234-244`, Codex round 5) — PR 6 adds refusal handling: on a
  non-2xx defer response the card is restored and the refusal message shown; the
  rejection path is verified through the UI (headless Chrome), not just at the route.
- **`quick_create` is DELETED as superseded, not wired:** it was designed for a
  calendar-owned modal world — multi-type, and it stamps BOTH `scheduled_date` and
  `due_date` (contradicting the ruling). Creation belongs to the Today surface through
  `TasksService`, like the lens's existing complete/defer/star actions. Un-register it
  from `PLANNED_METHODS` in the same PR — `_CALENDAR_EDIT_SURFACE` empties.
*Rejected:* a calendar quick-add modal (duplicates existing forms; the day lens IS the
acting surface); hover "+" chips (grid noise); toolbar-only daily-note access (past
days' notes would lose their calendar door); inline event creation on the lens
(duplicates Create-an-Event; tasks are the daily-lived quick capture).

## Non-goals (this arc)

Drag-and-drop rescheduling (C4 modal path first); week-view hourly time grid (agenda
cards stay); a "show completed items" toggle; external calendar sync; habit recurrence
semantics changes; the duplicate-task data cleanup (separate care session); nav badge
counts anywhere (standing ruling); pagination.

## Standing conventions that bind every PR here

Monday-start + ISO-week rail are PERMANENT (never re-propose). All chips render — no
truncation (#623); legend filters are the only hiding mechanism. Every new Cypher goes
through the query builders with parameterized values (CYP003) and `RelationshipName`/
`NeoLabel` members (SKUEL030); date comparisons use the #766 `left(toString(…),10)`
idiom. Query params over path params for new GET routes; POST mutations CSRF-protected.
`Result[T]` internally, `require_found` at boundaries. Habit chips/modal must keep
working when a habit has string `created_at` (native/string temporal split —
`_habit_inception_date` already tolerates both; don't regress it). Un-staged methods
leave `PLANNED_METHODS` in the same PR that wires them (SKUEL026-adjacent hygiene:
a PLANNED entry for a wired method is registry rot).

## PR plan (contract)

Each PR: fresh context; branch from **updated** main (`git pull --ff-only` first);
`./dev format` + `./dev quality` + targeted tests; runtime verification with headless
Chrome against the live dev app (month + week views, real Alpine, screenshot) plus a
live-graph spot check; commit → PR → Codex review → consideration note → merge
(standing authorization). This doc ships with PR 0 (docs-only — summon Codex explicitly;
the gate auto-passes docs PRs without a verdict).

| PR | Scope | Acceptance (live case) |
|----|-------|------------------------|
| 1 | C1 — month grid fetches full visible range; focus month passed explicitly | August 2026 month view shows the 3 daily habit chips on Jul 27–31 and Sep 1–6 cells; those cells agree with the week views of the same days |
| 2 | C2 — OR-of-date-fields in query builder; tasks fetch by due OR scheduled | A live pending task with `scheduled_date` in the view range and NO `due_date` renders as a work chip; a due-only task still renders as a deadline chip; non-calendar range consumers unchanged (`./dev quality` + targeted tests) |
| 3 | C3 — day-aware habit chips, real completion state, per-day Mark Complete | Clicking "Meditate" on yesterday's cell opens a modal for THAT day; Mark Complete records a completion dated yesterday (verified in graph); the chip turns completed; today's chip completed via /habits also renders completed; future chips offer no completion |
| 4 | C4 — modal reschedule for tasks/events | Rescheduling a live scheduled task from its modal moves the chip to the new date (graph verified); an event keeps its duration; non-owner UIDs get not-found |
| 5 | C5 — goals as Milestones (incl. `goal-` in `get_item` + modal); delete dead converters; docstring truth | Setting a `target_date` on live goal "Focus on Van" renders a purple Milestone chip on that day; clicking it opens a working details modal with a View Goal link (non-owner → not-found); `ui/calendar/converters.py` + its test are gone; `calendar_routes.py` docstring matches reality |
| 6 | C6 — day-click → day lens; day-lens task quick-add (+ lens membership widened to due OR scheduled); Daily-note toolbar buttons; delete `quick_create` | Clicking Aug 20 in month AND week views opens `/today/2026-08-20`; adding a task there creates it with `scheduled_date=2026-08-20`, no `due_date`; the task appears on that day's lens immediately AND after a refresh (lens selects due OR scheduled), and renders as a work chip on the calendar; deferring that task from its Today card moves `scheduled_date` (no invented `due_date`) and it leaves that day's lens and calendar cell for the deferred day; a both-dates task deferred from its due-day lens moves the deadline instead (view-date-driven); an OVERDUE both-dates task deferred from its triage card moves the deadline (no-field-matches fallback); a defer that would push the work date past the deadline is refused AND the card visibly returns with the refusal message (client rollback verified in the UI); a past day's lens offers no add and a forged past-date POST is refused; date numbers still link to daily notes; both toolbars show a Daily note button opening today's note; `quick_create` gone from `CalendarService` AND `PLANNED_METHODS` (`_CALENDAR_EDIT_SURFACE` empty); `./dev bloat` clean |

PR 1 → 2 → 3 is the dependency spine (truthful grid → truthful items → actions on
them); PRs 4 and 5 are independent of each other and can land in either order after 3.
PR 6 runs last (ruled after 1–5 shipped; it re-routes the day-cell click and touches
the toolbar both earlier PRs shaped).
