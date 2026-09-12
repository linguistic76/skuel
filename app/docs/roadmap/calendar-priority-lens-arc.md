---
title: "Calendar Priority-Lens Arc — Rulings & Contract"
updated: 2026-09-12
status: "active"
registered: 2026-09-11
ruled: 2026-09-11
---

# Calendar Priority-Lens Arc — Rulings & Contract

**Status:** ACTIVE 2026-09-11 (founder rulings taken the same day against a full code read + live-graph
census). Five sub-arcs, A→E, each a short PR chain run in a fresh context against this document.
PR 0 (#1312) Codex review, eight rounds, all findings accepted and folded in (round 8: a
calendar-period report counts from persisted HISTORY — `HabitCompletion` rows, `progress_history`,
`alignment_history` — never from a latest-only stamp that a later transition overwrites; its
period-end denominator is an approximation with a named false positive; round 7: the rich
query's touched predicates gate nothing today — E.2 moves them onto the row; a calendar period's
denominator is open AT PERIOD END; `find_by_period` is owner-scoped; round 6: the task
completion rate's denominator is in-period — completed in period + open now — never the whole
inventory; the week legend lists Milestone; a task both overdue and scheduled today renders once, in
Overdue; D1 regenerates the graph contract when it deletes `PINNED_TODAY` and clears the persisted
edges; round 5: A.2 posts
url-encoded form bodies and a real submit button — shipped that way on #1314; the rich query admits
choices by `decided_at`; A2 merged before A1c, so A1c is the next PR and the goal/principle
counters read zero until it lands; the B1 cutoff is stop-old-app → migrate → start-B1; closed-period
finalisation bypasses the cooldown and comparisons skip superseded same-period reports; round 4: the goal
and principle stamps the counters read are written by no producer — A.1c stamps them; E.2 keeps
no upper bound on `updated_at`, the mapper's canonical stamps are the bound; the Reports door reads
the newest OWNED report; a partial report is finalised once its period closes): the report's events are
bounded to the window in A.1 (not E.2); the backfill (B2) runs before the enum deletion (B1); E.2's
data cutoff is `min(now, period_end)`; A.1's headline counters are in-period transitions, never
inventory — tasks by `completion_date`, events attended only when COMPLETED; the day view covers every
*dated* domain (Choices included, Principles are dateless) and binds the calendar's legend controller
with Choice added to the filter CSS; the legendless month view binds no legend controller, so a kind
hidden on the week can never blank it.
**Related:** [`done/calendar-act-from-arc.md`](done/calendar-act-from-arc.md) (C1–C7),
[`done/calendar-periodic-notes-arc.md`](done/calendar-periodic-notes-arc.md) (R1–R5, E1–E4, S1–S4),
[`done/habit-rhythm-arc.md`](done/habit-rhythm-arc.md) (M1–M7),
[ADR-045](../decisions/ADR-045-priority-confidence-customization-dials.md),
[ADR-058](../decisions/ADR-058-today-surface.md),
[ADR-069](../decisions/ADR-069-extract-activities-pipeline-and-entry-report.md) Decision 3,
[ADR-087](../decisions/ADR-087-status-guarded-conditional-writes.md),
[`weekly-goals-choices-chips.md`](weekly-goals-choices-chips.md) (the deferred half of ruling 3),
[`goal-progress-reads-an-unwritten-edge.md`](goal-progress-reads-an-unwritten-edge.md) (compounding
defect, separate case file).

---

## Intent

The calendar grew to display too much. The founder's ruling: the calendar shows *time-bound
commitments filtered by priority*; the Activity Domains as a whole are understood through
**Activity Reports**, not through calendar chips or sidebar counts. Concretely:

- **Monthly** = Events at priority ≥ medium. Nothing else.
- **Weekly** = Events ≥ medium, Habits ≥ medium, Tasks = high. (Goals + Choices deferred — see below.)
- **Daily** (`/today`) = a simple server-rendered view of every *dated* Activity Domain *for that
  day* — tasks, events, habits, goal milestones, choices — task-list first, sharing its card stack
  with `/tasks`. Principles carry no date; they are read through the report. The Day spine goes.
- **Priority** has exactly three levels: low / medium / high.
- The sidebar's domain rows with counts leave the calendar/Today pages; a **Reports** door replaces them.

## Founder rulings (2026-09-11 — do not re-litigate)

| # | Ruling | Decision |
|---|--------|----------|
| 1 | Priority collapse mechanics | **Delete `Priority.CRITICAL` outright + one-shot graph backfill** `critical → high` (authorised, see ruling 8). No input-only alias — aliasing would launder data and hide the count. DSL `@priority(1,2)` → HIGH, `3` → MEDIUM, `4,5` → LOW. Obsidian 🔺 ⏫ → HIGH, 🔼 → MEDIUM, none → MEDIUM, 🔽 ⏬ → LOW (aligned with Obsidian's own names). |
| 2 | Month rule | **A definition, not a preference** — server-side per-view membership. "ONLY" is a contract. |
| 3 | Goals + Choices on weekly | **Deferred** to its own ruling — case file [`weekly-goals-choices-chips.md`](weekly-goals-choices-chips.md). It contradicts M4, R2 and S1 outright, so it is recorded, not silently overridden. |
| 4 | Day view keeps | **Overdue: must keep.** Defer control: keep, as a server-rendered control on the existing route (C7's guard + predicate intact). Keyboard j/k and drag: drop with the Alpine bundle. *(Defer/keyboard were "not sure" — this is the orchestrator's recommendation, adopted unless the founder objects.)* |
| 5 | Completion door | **The status door is the one door** — `TasksCoreService.update_task`, the ADR-087 chokepoint. The "cascade door" is the explicit-complete path whose four extra steps are `logger.debug("Would …")` stubs and whose one real step moves behind the event bus. Founder deferred to best practice; see Arc D.0. |
| 6 | Sidebar | **Slimmer variant on calendar/Today pages only** (Today / Weekly / Monthly / Journal / Reports). Domain pages keep their rows and badges. |
| 7 | Report schedule producer | **Retire** (arc E's last PR) — it is a second period vocabulary (trailing windows + weekday cadence), not the automation half of find-or-generate; nothing consumes an unrequested report; zero tests; empty table since it was built. Amends ADR-069 Decision 3 rows 6–8. |
| 8 | Graph backfill | **Authorised** — the census measured exactly **7 Task nodes** with `priority = 'critical'` (no other label, no odd spellings). Lateral relationships carry `r.priority` too and are rewritten in the same migration. |
| 9 | Week report token | **ISO `2026-W37`** (the journals' period-key grammar); months `2026-09`. |
| 10 | `CalendarItem.priority` | CalendarItem is the projection of a Task/Event/Habit/Goal onto the calendar. It keeps **one** priority field, typed as the `Priority` enum (arc C filters on it); the int copy and `metadata["priority"]` are deleted as duplication. |

## Verified ground truth (2026-09-11 — code read + live graph)

**Live census (AuraDB, read-only):** priority by type — task: 65 medium / 4 high / **7 critical**;
event: 6 medium; goal: 2 medium / 1 high; habit: 2 medium / 1 high (+3 NULL); choice: 8 medium / 1 high
/ 1 low; principle: 2 medium / 1 high. No non-Activity label carries priority. **Goal nodes: 3 total,
0 carry `progress`, 2 carry `progress_percentage`.**

**Calendar.** One shell (`calendar_ui.py::_calendar_shell`) and one fetch
(`CalendarService.get_calendar_view`) serve month and week; `view_type` is stored on `CalendarData` and
read by nothing. The legend's hide state is one browser key (`skuel-calendar-hidden-types`) with no
view segment. Events and habits hardcode `priority=1` in their converters (calendar_service.py:795,
:874); tasks/goals carry the real value; **no UI code reads `CalendarItem.priority`** — its only reader
is the consumer-less JSON route `GET /api/v2/calendar/items/{id}`. Write-only `CalendarItem` fields:
`icon`, `priority` (int), `project_uid`, `related_uids` (never written), every `metadata` key except
`status`; `CalendarData.metadata` and `.view`; the `CalendarFilter` dataclass (zero constructors).
Server-side scoping has in-service precedent: `include_completed=False` and `get_planning_items`
(excludes habits). Legend tests pinning the four-kind layout: `test_legend_groups_four_kinds_by_activity_pair`,
`test_legend_swatches_read_as_controls`; `test_get_calendar_view_includes_milestones` asserts a
Milestone on MONTH.

**Priority.** 14 non-test files reference `Priority.CRITICAL`; 10 in-enum maps + ~15 outside maps/ladders
hand-enumerate four keys (census in the arc-prep findings: `constants.py` PRIORITY_LEVEL,
`entity_filters.PRIORITY_ORDER`, `ui/activities/_shared.PRIORITY_ORDER` (dead duplicate),
`profile_orchestrator`, `goals_scheduling_service` (DEFAULT_MAX_CRITICAL_GOALS — the only HARD cap),
`ui/feedback.py`, `ui/search/components.py`, `filter_bar.py`, `skuel.js:594` (lateral edge width),
`curriculum_backends.py:1095` CASE, `dsl_mappings.py`, `obsidian_tasks_adapter.py`, `goal_task_generator.py`,
`ui/today/orchestrator.py`). `get_calendar_color` has zero readers. CSS tokens are already three-level.
ADR-045's justification (a CRITICAL override in `daily_planning.py`) does not exist in code. `priority`
is absent from `ENUM_FIELD_TYPES`, so the vault door neither canonicalises nor refuses it. Lateral
relationships persist `r.priority` (`lateral_route_factory.py:118` → `SET r += $properties`).

**Today.** `ui/today/page.py` 961 + `static/js/today.js` 412 + `ui/today/orchestrator.py` 604 lines; every
section but quick-add is an Alpine template over `window.SEED`; the Day spine is a 06:00–22:00 hour axis
(the shape M5 ruled against). Two task-row renderers (Alpine `_task_row` vs `TaskCard`) and two
completion doors. `TaskCard`/`HabitCard`/`EventCard` all fit `ActivityList`'s `card_fn(item, connections)`
contract; `ActivityList` needs only an empty-state override and a list id. `HabitCard`'s toggle sets
habit STATUS — a day view needs the per-day door `POST /cal/habit/{uid}/complete`. `PlanningPanel`
cannot render a day by design. ADR-058 is stale on the brand link (`/explore`, not `/today`) and
contradicts itself on whether `today.md` is archived or the live spec.

**Completion doors (ruling 5 evidence).** `complete_task_with_cascade` (tasks_progress_service.py:198)
does the SAME ADR-087 guarded write as `update_task` (:340 vs tasks_core_service.py:926-933), then runs
five steps of which four are `logger.debug("Would …")` stubs (:665, :674, :679, :733) and one is real —
`_trigger_task` (:681-728), a guarded `SCHEDULED` write over `TRIGGERS_ON_COMPLETION` dependents (a
registered edge with **no runtime writer**; 0 edges measured 2026-08-23). `update_task` is a superset on
the event side (TaskUpdated + transition-gated TaskCompleted + TaskReopened + embedding refresh); the
cascade publishes only TaskCompleted and is the only publisher that can set `is_repeat=True`. Every
TaskCompleted subscriber fires from both doors because `publish_async` awaits all handlers
(event_bus.py:180) — "fire-and-forget" in SKUEL means error-isolated, not un-awaited. Live callers of
`complete_task`: `today_routes.py:157` and `user_context_service.py:527` (behind
`POST /api/context/task/complete`, zero UI consumers, unwired fields). `record_task_completion` is a
fourth publisher with zero production callers.

**Activity Reports.** Composed and its worker started in BOTH tiers (compose.py:1505-1521 sits outside
every `tier.ai_enabled` gate). **No user can produce a report today:** the request form posts to
`POST /api/reports/progress/generate`, whose handler was shelved in `503bbdfc4` (2026-04-15) and later
retired; the annotate POST is dead the same way; the schedule producer is PLANNED READY since 2026-06-12
so the hourly worker polls an empty table. Period vocabulary is trailing windows only (`7d|14d|30d|90d`,
pinned in `constants.py:692-696`, the form, the Pydantic pattern, `build_rich(window=)`); the MEGA-QUERY
computes `$window_end` (user_context_queries.py:1571-1579) but **no predicate references it**. Eight
reads in `_completions_from_context` use keys the MEGA-QUERY never emits (rename table in Arc A). The
MEGA-QUERY reads `goal.progress` at :153, :164, :180, :1323 — a property no node carries — so
`context.goal_progress` is a constant 0.0 for every consumer. Zero tests seed a non-empty
`entities_rich` row. Cooldown 60 min per user, fail-open. No `.md` download.

**Sidebar.** `ACTIVITY_SIDEBAR_ITEMS` is one list shared by 44 callers; the "11/74" + dot are OOB-swapped by
`GET /api/sidebar/badges`, which `ui/patterns/sidebar.py:375-377` fires on EVERY SidebarPage load and
which builds the RICH UserContext (5-min cache); badge placeholders render only for listed items, so on
a calendar sidebar the build is wasted. `events_ui.py` passes `active="events"` for a slug the list no
longer has.

## Amendments by letter (the standing rulings this arc changes)

| Ruling | Was | Now |
|---|---|---|
| **#623 convention** ("All chips render; legend filters are the only hiding mechanism") | every kind renders; client CSS is the only filter | **The server renders each view's DECLARED membership (kind × priority). Within that membership, all chips render and legend filters remain the only client-side hiding.** Toggle-reversibility — #623's rationale — survives: nothing the legend can hide is missing from the DOM. |
| **C3** (per-day habit tick on month AND week) | month + week | week (habits ≥ medium) + the day lens. The month view carries no habits. |
| **C5** ("every legend entry has a producer") | one four-kind legend | the legend is **per-view**: month has none (one kind, nothing to toggle); week shows Event / Habit / Task / Milestone — every kind the WEEK spec renders. |
| **S1 / habit-rhythm non-goal** ("four-kind legend ships as-is; no new filter vocabulary") | frozen | superseded by the per-view legend above. Priority is NOT a legend control — it is view membership (ruling 2). |
| **M4 / R2** (Goals, Choices, Principles are not weekly filters / chips) | binding | **unchanged** — deferred half in [`weekly-goals-choices-chips.md`](weekly-goals-choices-chips.md). Goals still reach the grid as Milestones (C5) — on the WEEK view only, ≥ medium. |
| **ADR-045** (four levels, CRITICAL "surfaces to top of daily plan") | LOW/MEDIUM/HIGH/CRITICAL | LOW/MEDIUM/HIGH. The cited override never existed; the amendment de-fictions it. |
| **ADR-058** (Ribbon, Day spine, drawer, keymap, drag-to-defer) | the Ribbon design | `/today` stays the landing page and the day lens (C6); the spine, ribbon, drawer, star, keymap and Alpine bundle are deleted; the surface is server-rendered from the `/tasks` card stack. |
| **C7** (defer contract) | `source=ribbon\|triage` | substance unchanged (view-date-anchored, membership-guarded, no Undo); `source=ribbon` → `source=day`; the "(source, uid) keyed client state" and "one transport per control" clauses are moot without Alpine. |
| **ADR-069 Decision 3 rows 6–8** (schedule producer PLANNED — "deleting them strands a running loop") | keep | the loop retires WITH its producer (row 10's all-or-nothing rule applied symmetrically). Arc E's find-or-generate door is the one period-report path. |
| **`docs/domains/tasks.md` "five doors, one contract"** | five | **one door** (`update_task`) — Arc D.0. |

Unchanged and binding: C1, C2, C4, C6 (day-cell click → `/today/{date}`; tasks-only quick-add; past
days refused), R1, R3–R5, E1–E4, M1–M3, M5–M7, Monday-start + ISO-week rail (PERMANENT), ADR-085 read
enforcement, ADR-087 status-guarded writes.

## Choices

### Arc A — Activity Reports true and reachable (first; independent)

**A.1 — the mapper reads the keys the MEGA-QUERY emits.** `entities_rich` rows are
`{entity: properties(n), graph_context: {...}}`. Rename table (wrong → right, `progress_report_generator.py`
line → `user_context_queries.py` line):

| Domain | Reads today | Must read | Consequence today |
|---|---|---|---|
| tasks | `graph_ctx["goal_refs"]` (:774, :786) | `graph_ctx["goal_context"]` — a SINGLE dict or null (:153) | `goal_alignments` always empty |
| tasks | `graph_ctx["ku_refs"]` (:777, :789; details key mislabelled `reports`) | `graph_ctx["applied_knowledge"]` list of {uid,title} (:152); details key → `kus` | `knowledge_applications` always empty |
| goals | `entity["progress"]` (:804) | `entity["progress_percentage"]` 0–100 (properties(goal) :192) | avg progress 0.0, "progress: —" |
| habits | `entity["streak"]` (:819) | `entity["current_streak"]` (:360) | avg streak 0 → "Habit streaks are low" fires for everyone |
| events | `graph_ctx["is_milestone"]` (:835) | `entity["is_milestone_event"]` (event.py:140) | milestones always 0 |
| choices | `graph_ctx["principle_refs"]` (:851) | `graph_ctx["guiding_principles"]` (:682) | "No choices linked to principles" fires for everyone |
| principles | `entity["alignment"]` (:867) | `entity["current_alignment"]` (principle.py:124) | aligned / needs-attention always 0 |
| principles | `entity["category"]` (:869) | `entity["principle_category"]` | cosmetic |

Same PR: `habits_completed` counts habits whose NODE status is COMPLETED (a retired habit) — derive
"≥1 completion in window" from `entity["last_completed"] >= window_start` instead (no query change).
**Events are bounded to `[window_start, window_end]` by `event_date` in the mapper** — the rich query
selects every event from `window_start` onward with no upper bound, so without this cut a scheduled
future event is reported as already attended (Codex P1 on PR 0; the query-level bound for explicit
periods is E.2's, and must not touch the live context's forward-looking event rows, which
`events_habit_integration_service` and `principles_planning_service` consume). **Every headline
counter is an in-period transition read off the entity's own stamp, never the row count** (Codex P1,
rounds 2–3): `tasks_completed` = status COMPLETED with `completion_date` in period (the rich query
selects completed tasks by `updated_at`, so an old completion re-edited in the window must not count),
and its ratio's denominator is in-period too — `tasks_total` = completed in period + open — "open" meaning open NOW for a trailing window and
open AT PERIOD END for a calendar period (created no later than `period_end`, not completed or
otherwise terminal by it; Codex P1, round 7) — never
the whole touched inventory, which would print a falsely low rate and a "reduce scope"
recommendation for anyone with old open tasks (Codex P1, round 6);
`goals_progressed` = `last_progress_update` in period, `habits_completed` = `last_completed` in period
(both bounds), `events_attended` = in-window events whose status is COMPLETED (attendance is the
completed state — `EventsProgressService.get_attendance_rate` — so a cancelled or merely passed event
is inventory, not attendance), `choices_made` = `decided_at` in period, `principles_reviewed` =
`last_review_date` in period; the `*_details` lists remain the context's inventory and the markdown
names them "in play".

**A.1c — the stamps those counters read must be WRITTEN (Codex P1, round 4).** A2 (#1314) merged before
A1c, so until A1c lands a generated report reads zero goals progressed and zero principles reviewed
(Codex P1, round 5) — A1c is the next PR in line. It also widens the rich query's choice selection to
admit a choice by `decided_at >= window_start` (today a choice created before the window, decided in
it and completed before generation is dropped by the draft/active-or-created-in-window predicate at
`user_context_queries.py:579`, so `choices_made` undercounts the very transition it promises). No goal progress
writer persists `last_progress_update` (`GoalsProgressService` updates `progress_percentage` and
relies on the generic `updated_at`), and no principle flow persists `last_review_date`
(`record_principle_reflection` only publishes; `_store_user_assessment` appends `alignment_history`;
the field is absent from `PrincipleUpdateIntent`). A mapper test that seeds the field passes while
production counts zero. A.1c (own PR, after A1): every progress-writing path stamps
`last_progress_update`, every reflection/assessment path stamps `last_review_date` (and the intent
carries it), with integration tests that drive the WRITER and assert the report counter — never a
seeded row. The admin snapshot (`ActivityReportService.create_snapshot`) reads the same
five wrong keys and is fixed in the same PR.
Tests: a NEW `TestCompletionsFromContext` seeding rows in the real shape and asserting non-zero
deltas against the current all-zero result (the standing "assert an output DELTA" rule); the `kus`
fixture at :289 becomes the mapper's real output.

**A.1b — `goal.progress` → `progress_percentage` in the MEGA-QUERY** (:153, :164, :180, :1323), dividing by
100.0 in Cypher so the 0–1 consumers of `context.goal_progress` (`user_stats_types.py:250-258, :336`,
`unified_user_context.py:662`, `schedule_intelligence.py:376`, `life_path_intelligence.py:212-214`) stay
correct; `goals_core_service.py:807` `getattr(goal, "progress", 0.0)` → `goal.calculate_progress()`.
Integration test: a goal written with `progress_percentage=40.0` yields `context.goal_progress[uid] == 0.4`
(today 0.0). The compounding `SUPPORTS_GOAL`-direction defect stays in its own case file.

**A.2 — restore the two dead producers** inside `create_activity_reports_ui_routes`:
`POST /api/reports/progress/generate` and `POST /api/activity-reports/annotate` (the annotation GET has
no consumer and is not restored), under today's conventions: `@rt(path, methods=["POST"])` →
`@csrf_protected` → `@boundary_handler`, **`parse_form_body`** + `Result.fail(parsed)` — HTMX sends
the enclosing form's fields url-encoded, and the forms' former `hx-headers`/`hx-vals` JSON attempt
never produced a JSON body (Codex P1, round 5; shipped this way on #1314). The notes form's "Save
Notes" is a real submit `Button`, not an anchor. Both handlers return `Result[FT]` fragments the two
LIVE forms target (`#generate-status` with a link to the detail page and an out-of-band refresh of
`#progress-list`; `#annotation-status`). The generator reaches the factory as a kwarg from the container
(`services.progress_report_generator`) the way `batch_transcription` is wired at
`user_entry_routes.py:64-80`. The shelved list/schedule/privacy routes are NOT restored (list is
`/reports/progress-list`; schedule retires in E; privacy stays PLANNED). Reference:
`git show 503bbdfc4^:app/adapters/inbound/progress_report_api.py:93-118, :341-383`.

**A.3 — `.md` download:** `GET /activity-reports/md?uid=` owner-scoped through
`orchestrator.get_activity_report(uid, user_uid)` (never bare `get`), rendered by a new
`adapters/outbound/activity_report_renderer.py` mirroring `exercise_renderer.py`
(`Response(media_type="text/markdown; charset=utf-8", Content-Disposition attachment)`, 404 text/plain
on refusal); a Download button on the detail page.

**A.4 — de-fiction:** `REPORT_ARCHITECTURE.md:481-488` route table (eight routes that do not exist),
`ReportSource.AUTOMATIC` docstring ("scheduled" → programmatic fallback), the learning-loop skill's
`create_scheduled` mention.

*Rejected:* restoring the routes as JSON-returning (the live forms swap innerHTML — raw JSON would
render as text); a second period vocabulary for the admin activity-review path (open question, see
below).

### Arc B — Priority → three levels (before C)

- Delete `Priority.CRITICAL`; shrink the 10 in-enum maps; delete `get_calendar_color` (zero readers) and
  `ui/activities/_shared.PRIORITY_ORDER` (dead duplicate of `core/utils/entity_filters.PRIORITY_ORDER`);
  collapse the ~15 outside maps; re-base every `Priority.CRITICAL` member reference to HIGH.
- Semantics with no three-level analogue: `TaskPriorityChanged.escalated_to_urgent` (`== 4`) → **delete the
  field** (constant False otherwise); `DEFAULT_MAX_CRITICAL_GOALS` hard cap → **delete** (HIGH keeps its
  advisory rule); keystone habit maintenance events → HIGH (the keystone distinction lives on the habit,
  not the event's priority). `task_knowledge_analyzer.py:524/:618` string compares → HIGH.
- DSL: `map_dsl_priority_to_enum` 1,2 → HIGH, 3 → MEDIUM, 4,5 → LOW; `DSL_SPECIFICATION.md:255` example.
  Obsidian `_PRIORITY_BY_EMOJI`: 🔺→1, ⏫→1 (both HIGH), 🔼→3 (MEDIUM), 🔽→4, ⏬→5; add the missing int→enum
  test. (Live periodic notes carry 14 emoji lines + 6 `@priority(1)` lines that resolve to HIGH with no
  file edits.)
- Register `"priority": Priority` in `ENUM_FIELD_TYPES` so an authored `critical` is canonicalised/refused at
  the vault door (otherwise the vault can rewrite it after the backfill).
- Backfill: one label-anchored idempotent `.cypher` migration modelled on
  `scripts/migrations/lowercase_event_type_2026_08.cypher`, rewriting BOTH `n.priority` (7 Task nodes) and
  `r.priority` on lateral relationships, with a verify query. Run against Aura (authorised) **twice**: before
  B1 merges and as B1 deploys — **stop the old app, run the migration, start B1** (Codex P1, round 5):
  the second run is the write cutoff, and nothing writes between it and the new code serving, so no
  row the old enum accepted can meet the new one.
  **Ordering (Codex P1 on PR 0): the backfill runs against Aura BEFORE B1 merges.** `Priority(task.priority)`
  is constructed directly in `_task_to_calendar_item` and the Today orchestrator, so a deleted member
  with seven persisted `critical` rows would raise on every calendar/Today read in between. `'high'` is
  valid under both vocabularies, so running the backfill first is safe; B1 then registers `priority` in
  `ENUM_FIELD_TYPES` so the vault cannot reintroduce the value.
- Docs: ADR-045 amendment (delete the fictional daily-planning override), `PRIORITY_CONFIDENCE_ARCHITECTURE.md`,
  `ENUM_ARCHITECTURE.md`, `calendar_models.py:149` comment, `ui/today/orchestrator.py:81` (`Priority.NONE`
  does not exist).
- *Out of scope:* other vocabularies that spell `critical` — `DomainStatus`/domain_health, `InsightImpact`,
  `ErrorSeverity`, `HabitEssentiality`, the search `_URGENCY_OPTIONS` facet, Askesis free-string action
  priority.

### Arc C — Calendar lens: server-side per-view membership (after B)

- Replace `CalendarFilter` with a frozen **`ViewSpec`** keyed by `CalendarView`:
  `MONTH = {EVENT ≥ MEDIUM}`; `WEEK = {EVENT ≥ MEDIUM, HABIT ≥ MEDIUM, TASK = HIGH, MILESTONE ≥ MEDIUM}`.
  `get_calendar_view` derives it from `view_type` (its first real consumer; no route/protocol change),
  skips `_fetch_habits` and the per-habit completion reads when HABIT is out, and filters by
  `Priority.from_value(entity.priority)` — **NULL priority reads as MEDIUM** (the request-model default,
  so an unstated habit is shown, not hidden).
- `CalendarItem.priority` becomes `Priority | None` (the enum); delete the int, `metadata["priority"]`,
  `icon`, `project_uid`, `related_uids`, the non-status metadata keys (replace `metadata["status"]` with a
  typed field), `CalendarData.metadata`/`.view`, `CalendarItemType.get_icon`; fix `_event_to_calendar_item`'s
  `category="PERSONAL"` (uppercase against the lowercase `EventType` vocabulary); retype
  `create_item_details_modal(item: CalendarItem)`. **Delete `GET /api/v2/calendar/items/{id}`** (no runtime
  consumer; the sole reader of the write-only fields; 9 tests go with it).
- Legend per view (`create_calendar_legend(view)`): MONTH renders none **and binds no `calendarLegend`
  controller** — a kind hidden on the week is stored in the shared key, and a controller on the
  legendless month would apply `cal-hide-event` with nothing there to lift it, blanking the view (Codex
  P2, round 3); WEEK renders Event / Habit / Task / Milestone with click-to-hide + spotlight intact (CSS
  mechanism unchanged; the single storage key stays). Rewrite the two legend tests; flip the milestones
  test to WEEK; add a test that the month shell carries no `x-data="calendarLegend"`.
- `get_planning_items` (weekly/monthly-note panel) stays unfiltered — it is the planning-against surface
  (R4/E2), a different job. `period_panel` is untouched.
- Docs: components.py:112 names `_wrap_calendar_page` as the legend binding site (it is `_calendar_shell`);
  `service_protocols.py:79` falsely lists `visualization_api.py` as a calendar consumer; `ROUTE_MAP.md:85`
  says calendar views are navbar-only (they carry the activity sidebar).
- *Rejected:* client-side priority filtering with per-view defaults (a preference is not a definition —
  ruling 2; and month would still fetch/expand every habit); a `CalendarView.DAY` member (Today does not
  consume `CalendarService`'s view; see Arc D).

### Arc D — Daily view: server-rendered, day-scoped, all domains

**D.0 — one completion door (prerequisite PR; can land any time).**
- `TasksCoreService.update_task` is THE door. `_trigger_task` (+ `_TERMINAL_STATUS_VALUES`, now
  `EntityStatus.terminal_values()`) moves into `TaskEventHandlerService` as **its own `TaskCompleted`
  subscriber** (`handle_dependent_scheduling`, its own exception boundary — Codex P2, round 10: a step inside
  `handle_task_completed` would exit through that handler's single boundary when an optional
  intelligence step raises first, leaving dependents unscheduled behind a reported-successful
  completion; the bus runs subscribers in isolation). Its `refuse_if_prior_in` terminal guard makes it
  idempotent — no `is_repeat` gate; its 5 tests move with it. **What the door gives up** (Codex P1 on
  #1320): the retired cascade re-ran on a repeat click, an accidental manual replay for a subscriber that
  failed transiently; a re-post through `update_task` publishes nothing, so a lost subscriber run is
  lost until the outbox in [`ingest-transition-obligation-durability.md`](ingest-transition-obligation-durability.md)
  — whose scope now includes the app door — exists. Recorded there, not patched here.
- Delete: `complete_task_with_cascade` + the four stubs + the four cascade-only context helpers,
  `_OrchestrationMixin.complete_task_with_cascade`, `TasksService.complete_task`, `TasksOperations.complete_task`
  (a facade method declared on the BACKEND protocol that no adapter satisfies — the dual-layer-lie shape),
  `record_task_completion` (+ facade delegation; zero callers), `POST /api/context/task/complete` +
  `UserContextService.complete_task_with_context` + its request models (zero consumers; unwired fields).
- `POST /today/tasks/{uid}/complete` is repointed to `tasks.update_task(uid, TaskUpdateIntent(status=COMPLETED))`
  in D.0 (behaviour-preserving) and deleted with today.js in D.1.
- Retire `TaskCompleted.is_repeat` in the same PR (no publisher can set it True once the cascade is gone):
  the field, its five subscriber gates, `tests/unit/test_task_completed_is_repeat.py`.
- Rewrite `tests/integration/test_task_completion_doors_three_click.py` so all three clicks go through
  `update_task` (keep the stamp invariant + the race test; "a re-post publishes nothing" is already pinned).
- Prose: `TaskCompleted` docstring, `completion_stamp.py:34-36`, `tasks_core_service.py:872-878`,
  `docs/domains/tasks.md:277-285` ("five doors" → one), SERVICE_TOPOLOGY, SUB_SERVICE_CATALOG,
  BASESERVICE_METHOD_INDEX, BASESERVICE_QUICK_START, FASTHTML_TYPE_HINTS_GUIDE, activity-domains skill.
- `TasksProgressService` after the deletions is ~150 lines — fold into `TasksCoreService` only if the
  SERVICE_DECOMPOSITION_RULE floor says so; a deliberate later decision, not this PR.

**D.1 — the day view.** Keep `GET /today` and `/today/{date}` (all link-ins, auth redirects and C6 survive).
Render server-side: `PageHeader` + `calendar_nav_cluster` + the existing quick-add (C6) + **Overdue** on the
live day only (`is_triage_member`) + **Tasks** = `ActivityList`/`TaskCard` over `is_ribbon_member(t, view_date)` minus the tasks already
shown in Overdue — a task both overdue and scheduled today renders once, in Overdue, because `TaskCard`
derives its DOM id and HTMX target from the task uid alone and two copies would swap only one (Codex
P2, round 6)
+ **Events** for the day (`EventCard`) + **Habits** due that day as the calendar's day-stamped chips with the
per-day complete door (`POST /cal/habit/{uid}/complete`, C3) + **Milestones** (goal `target_date == day`) as
read-only rows + **Choices** whose `decision_deadline` or `decided_at` falls on the day, as read-only rows
linking to the choice (Codex P2, round 2 — the only other dated domain; Principles are dateless and are
not a day-view section). The page binds the calendar's legend controller — `x_data="calendarLegend"` +
`:class="filterClasses()"` on the day shell and `create_calendar_legend(view)` with the day's swatch set
(Task / Event / Habit / Milestone / Choice) — and wraps each section in a `data-item-type` container, so
the existing CSS filter (one shared component, one storage key) gives the day view its per-domain
toggle. `static/css/calendar.css` gains `choice` in both the `.cal-hide-*` and `.cal-spot-*` selector
groups (Codex P2, round 3 — a swatch whose kind has no selector toggles its pressed state and hides
nothing). `ActivityList` gains `empty_state` and `list_id`
parameters. Defer: a server-rendered "Defer 1d / 1w" control posting the existing route
(`source=day|triage`). Delete: today.js, today.css, `drawer.py`, spine/ribbon/drawer/star/wake/keyboard
sections, `PINNED_TODAY` edge + backend methods + protocol entries (regenerate `GRAPH_CONTRACT.yaml` in the same
PR — its drift test byte-compares the artifact against the enums — and ship a one-shot statement that
detaches the persisted `PINNED_TODAY` edges; Codex P2, round 6), the six seed TypedDicts, the
`docs/design-handoff/today/` pair (archive to `docs/roadmap/done/`), service-worker `CACHE_VERSION` bump,
`ALPINE_JS_ARCHITECTURE.md` registry row. Orchestrator slims to ~120 lines returning per-domain lists;
`membership.py` stays. Amend ADR-058 (keep the `ui/` placement rationale SKUEL032 cites; fix the brand-link
claim). Ride-alongs: the deferred `0m` duration fix (its trigger is "next touch of /today"); C7's
lens-status question (dated CANCELLED/FAILED tasks: **render** — the lens shows the day's truth).
**Implemented (D1 PR):** the legend takes a swatch set — ``create_kind_legend(DAY_KINDS)`` beside
``create_calendar_legend(view)`` — because the day is not a ``CalendarView`` (no floors: every
priority renders); ``CalendarItemType.CHOICE`` exists for the legend and the ``data-item-type``
filter only (choices render as rows, never chips); habits come from a new
``CalendarService.habit_items_for_day`` (the modal's own day stamp); the defer route's success
is 204 + ``HX-Redirect`` to the day; the handoff pair is archived at
``docs/roadmap/done/today-surface-handoff.md`` (the mock deleted); ``PINNED_TODAY`` edges are
detached by ``scripts/migrations/detach_pinned_today_2026_09.cypher``.

### Arc E — Sidebar + report doors (after A and C)

- **E.1 sidebar variant:** `render_activity_sidebar_page(items=...)` with `CALENDAR_SIDEBAR_ITEMS`
  (Today / Weekly / Monthly / Journal / Reports → `/activity-reports/latest`); a `badges: bool` gate on
  `SidebarPage` so calendar/Today pages do not fire `/api/sidebar/badges`; fix the `events` slug drift.
  `GET /activity-reports/latest` redirects to the newest report the user OWNS — a new owner-scoped
  backend read (`user_uid = subject`), not `get_history`, which is subject-scoped and returns
  admin-authored HUMAN reports the owner-scoped detail then refuses (Codex P2, round 4) — or to
  `/submit-activity-report` when none.
  **Implemented (E1 PR):** `CALENDAR_SIDEBAR_ITEMS` + `items=` on `render_activity_sidebar_page`, which
  sets `badges=False` on `SidebarPage`/`SidebarNav` (the loader attributes are simply not rendered);
  `events_ui.py` highlights `monthly` (the month is the events lens); `ActivityReportBackend.get_latest_for_owner`
  → `ActivityReportService.get_latest_for_owner` → `UserEntryOrchestrator.get_latest_activity_report`
  → `GET /activity-reports/latest`.
- **E.2 calendar-aligned periods** — lands as two PRs: **E.2a** (this bullet minus the history writers:
  tokens, data cutoff, row predicates, doors, per-period cooldown, distinct comparison, period-end
  denominator, `HabitCompletion`-row habit counts, limitations in metadata) and **E.2b** (the history
  writers and the history-based `goals_progressed` / `principles_reviewed` for closed periods, which
  E.2a records as a limitation until then). Tokens `2026-09` / `2026-W37` beside the trailing windows; the generator
  derives (start, end) via `week_bounds`/month bounds, keeps `period_end` as the report's metadata, and
  passes **`min(now, period_end)` as the DATA cutoff** — the mapper's `window_end` (Codex P1 on PR 0: a
  September report generated on the 11th must not count events scheduled for the 20th). **The rich
  query gets NO upper bound on its `updated_at` "touched" predicates** (Codex P1, round 4): a task
  completed inside the period but edited after it must still reach the mapper, whose canonical stamps
  (`completion_date`, `last_completed`, `decided_at`, `last_review_date`, `last_progress_update`,
  `event_date`) are the one bound; **A calendar-period report counts transitions from persisted history, not from the node's latest
  stamp** (Codex P1, round 8): `last_completed`, `last_progress_update` and `last_review_date` are
  overwritten by every later completion, progress write or review, so a September report generated
  in October would count zero for a habit done in both months. E.2 reads `habits_completed` from
  `HabitCompletion` rows dated in the period, `goals_progressed` from `progress_history` entries in
  it, `principles_reviewed` from `alignment_history` assessments dated in it (`completion_date` on
  a task and `decided_at` on a choice are single stamps and stay as they are); a trailing window
  ending now keeps the latest-stamp reads, which coincide with history for it.
  **The period-end denominator is an approximation with a named false positive** (Codex P1, round
  8): "open at period end" = created no later than `period_end` and either non-terminal now or
  terminal with its terminal stamp (`completion_date`, else `updated_at`) after `period_end`. A
  task terminal before the period and merely edited after it is counted as open — SKUEL persists no
  status-transition history, and E.2 records that limit in the report's metadata rather than
  promising a precision it cannot keep; the final report generated at first open after the period
  closes is as close to the period-end state as the data allows.
  `build_rich(window_start=)` selects touched-since-start — **and E.2 makes that selection real**: the
  touched predicates at `user_context_queries.py:112` (tasks) and `:170` (goals) sit on the
  neighbourhood `OPTIONAL MATCH`, so today they null the matched subtask/contributing task and keep
  the carried row, which is still collected; an untouched closed task reaches `entities_rich`
  regardless (Codex P1, round 7). E.2 applies the activity predicate to the row itself (a `WITH …
  WHERE` before the neighbourhood match) and pins it with an integration test that an untouched
  closed task is absent from `entities_rich` for the period.
  Stop defaulting unknown tokens (generator 7d vs builder 30d);
  `ActivityReportBackend.find_by_period(user_uid, subject_uid, time_period)` — scoped to the requesting
  OWNER like the detail read, never subject-only (an admin-authored HUMAN report can share the subject
  and the period token; Codex P2, round 7); `GET /activity-reports/for?kind=monthly|weekly&date=…`
  = find-or-generate → detail; toolbar pill "Report for September" / "Report for W37" via `period_link`;
  cooldown keyed per (user, period). Partial-period semantics: the first click generates a partial report
  (its data cutoff stored as `metadata["data_cutoff"]`) and later clicks re-open it while the period is
  still open; **once the period has closed, a report whose data cutoff precedes `period_end` is
  stale — `find_by_period` treats it as absent and the door generates the final report, superseding
  it** (Codex P2, round 4). That finalisation bypasses the per-(user, period) cooldown — a partial
  generated in the period's last hour must not block its own final snapshot — and
  `_collect_comparison` selects the preceding DISTINCT period, never a superseded same-period row
  (Codex P2s, round 5); a "Regenerate" action on the detail page is the explicit refresh.
  **The door splits** (Codex P2, round 10): `GET /activity-reports/for` is a *lookup* — it redirects to
  the period's reusable report or renders the pill's "Generate" state — and the generation transition
  (LLM call, persisted `ActivityReport`, cooldown consumption) is a CSRF-protected
  `POST /activity-reports/for`, so a prefetch or speculative navigation can never mint a report.
  **History has no writer yet** (Codex P1s, round 9): no production path appends `Goal.progress_history`
  (`update_goal_progress` writes the figure and, with notes, `metadata["progress_notes"]`; A1c stamps
  `last_progress_update`), and `record_principle_reflection` publishes events and stamps
  `last_review_date` while `alignment_history` is appended only by the self-assessment flow. Before
  `goals_progressed` / `principles_reviewed` read history for a closed period, E.2 makes every
  progress-writing path (`update_goal_progress`, `GoalsCoreService.update_goal` on a
  `progress_percentage` change, `complete_goal`) append `{date, progress_percentage}` to
  `progress_history`, and reflections persist a dated occurrence (an `alignment_history` entry with
  `kind: reflection` and no score); until then a calendar-period report keeps the trailing-stamp read and
  records the limitation in its metadata, like the period-end denominator.
- **E.3 retire the schedule producer** (ruling 7): worker, `ProgressScheduleService`, `core/models/report_schedule/`,
  `ReportScheduleBackend`, both protocols, `ScheduleType`, both request models, `NeoLabel.REPORT_SCHEDULE`,
  `RelationshipName.HAS_SCHEDULE`, `MIN_AUTO_REPORT_INTERVAL_HOURS`, compose/container/bootstrap wiring, the
  PLANNED entry + 3 registrations, `stale_names.py` entries, `PrivacySummary.report_schedule`, 16 model
  tests, the fixture in `test_timestamp_field_coercion_residual.py`; regenerate `GRAPH_CONTRACT.yaml`;
  amend ADR-069 D3 rows 6–8 (and row 9's schedule clause); repoint the five "hourly ProgressReportWorker
  is the CORE Analog worker" citations (CLAUDE.md, GRACEFUL_DEGRADATION_ARCHITECTURE, DO_MIGRATION_GUIDE,
  neo4j-cypher-patterns skill, habitmissed case file) to the 5-min graph-health poller. **The cleanup
  rule is a repo-wide grep for every retired name** (`ProgressScheduleService`, `ReportSchedule*`,
  `ScheduleType`, `REPORT_SCHEDULE`, `HAS_SCHEDULE`, `MIN_AUTO_REPORT_INTERVAL_HOURS`,
  `ProgressReportWorker`), not the citation list above — Codex (P2, round 10) named five more
  authoritative docs still presenting the scheduler as live: `REPORT_ARCHITECTURE.md`,
  `ENTITY_TYPE_ARCHITECTURE.md`, `PROTOCOL_REFERENCE.md`, `constants_usage_guide.md`,
  `ANY_USAGE_POLICY.md`.

## Non-goals (this arc)

Goals/Choices chips on the weekly view (deferred — own case file). Habits in the weekly-note panel
(separate deferred item). The `SUPPORTS_GOAL`-direction defect (own case file). Drag-and-drop or keyboard
navigation on the day view. A `CalendarView.DAY` member. External calendar sync. Finance as a seventh
domain. Re-litigating Monday-start / ISO rail or any C/R/E/M ruling not named in the amendments table.

## Open questions (answer in the PR that first touches them)

- Admin activity review (`ActivityReviewRequest.time_period` default `7d`): move to calendar tokens with
  E.2, or does the trailing-window vocabulary survive for the admin snapshot only?
- `habits_completed`: derive from `last_completed` (A.1, undercounts multi-completion weeks) vs add a
  `HabitCompletion` count to the MEGA-QUERY (accurate; touches the 1200-line query) — A.1 takes the
  cheap path and records the choice.
- Month legend: none, or a single Event swatch for spotlight only? C takes **none**.

## Standing conventions that bind every PR here

Fresh context per PR; branch from **updated** `main` (`git pull --ff-only` first); `./dev format` +
`./dev quality` + targeted tests; runtime verification with headless Chrome against the live dev app
for every UI PR (month + week + day views, real Alpine, 375px too); live-graph spot check where data
changes; commit → PR → Codex review → consideration note → merge (standing authorisation; docs-only PRs
summon Codex explicitly). Monday-start + ISO rail PERMANENT. Every new Cypher through the query builders
with parameterised values; `RelationshipName`/`NeoLabel` members only. Un-staged or deleted subjects leave
`PLANNED_METHODS` in the same PR. No personal vault content in the repo. Present-tense docstrings; the
history lives here and in the `done/` docs.

## PR plan (contract)

| PR | Scope | Acceptance (live case) |
|----|-------|------------------------|
| 0 | This doc + the deferred case file + MOC entry (docs-only; summon Codex explicitly) | Doc reflects rulings 1–10 and the amendments table; `./dev docs-links` clean |
| A1 | A.1 + A.1b — mapper rename table; events bounded to the window and attended only when COMPLETED; in-period counters for tasks (by `completion_date`), goals, habits, choices and principles from the entities' own stamps; the admin snapshot's five identical reads; MEGA-QUERY `progress_percentage/100.0`; `goals_core_service` abandon-progress | New mapper tests assert non-zero deltas for all eight keys, exclude a future event and an after-window habit completion, and count only in-period goal/choice/principle transitions; a goal with `progress_percentage=40` yields `goal_progress==0.4` in an integration test; `./dev quality` 0 errors |
| A1c | A.1c — goal progress writers stamp `last_progress_update`; principle reflection/assessment writers stamp `last_review_date` (intent carries it) | Integration tests drive `GoalsProgressService`'s progress door and the principle assessment door, then assert `goals_progressed == 1` / `principles_reviewed == 1` through the mapper — no seeded stamp |
| A2 | A.2 + A.3 + A.4 — restore generate/annotate/annotation routes as HTMX fragments; `.md` download; de-fiction | Clicking "Generate" on `/submit-activity-report` produces a report and links to its detail (headless Chrome); annotate saves; `/activity-reports/md?uid=` downloads owned reports and 404s foreign ones; no doc names a route that does not exist |
| B2 | Backfill migration committed AND run against Aura + verify — **lands before B1** | `MATCH (n) WHERE n.priority='critical' RETURN count(n)` = 0 and the same for relationships, run against Aura after the migration |
| B1 | Priority collapse — enum, maps, DSL/Obsidian remap, `ENUM_FIELD_TYPES`, docs | `Priority` has three members; `./dev quality` 0 errors; `@priority(1)` and ⏫ both create HIGH tasks; 🔼 creates MEDIUM; **the B2 migration is re-run as B1 deploys — stop the old app, migrate, start B1** (the write cutoff — until then the old enum still accepts `critical` on every activity write; Codex P1 on #1315 and round 5) and its verify returns no `critical` row |
| C1 | ViewSpec + converter priority + CalendarItem/CalendarData/CalendarFilter cleanup + delete `/api/v2/calendar/items` + per-view legend | Month view shows only events ≥ medium (live: 6 medium events, 0 habit chips); week view shows the 3 medium/high habits + high tasks + events; a low-priority habit is absent from week; legend on month is absent and the month shell binds no legend controller (hiding Event on the week leaves the month intact); on week the legend has four swatches; `./dev quality` 0 errors |
| D0 | One completion door (see D.0) | All three clicks in the three-click integration test go through `update_task`; `TRIGGERS_ON_COMPLETION` dependents still schedule (handler test); `is_repeat` gone; `/today` complete still works |
| D1 | The day view (see D.1) + ADR-058 amendment | `/today` renders overdue + tasks (TaskCard) + events + habits + milestones + the day's choices with no page-local JS bundle; the legend's Habits swatch hides the habits section and the Choice swatch hides the choices section (the calendar's `calendarLegend` controller bound on the day shell; `choice` in calendar.css); completing a task from the day view goes through `/api/tasks/{uid}/status`; quick-add still creates `scheduled_date`-only tasks; the calendar's day-cell click lands on the new view; 375px verified |
| E1 | Sidebar variant + `/activity-reports/latest` | Calendar/Today pages show Today/Weekly/Monthly/Journal/Reports and issue no `/api/sidebar/badges` request; `/tasks` unchanged |
| E2a | Calendar-aligned periods + find-or-generate doors | "Report for September" on the month toolbar opens a report whose window is Sep 1–30; a task completed Oct 1 is excluded while a task completed Sep 20 and edited Oct 3 is counted; clicking again re-opens the same report while September is open; the first click after Sep 30 on a partial report generates the final one |
| E2b | History writers + history-based counters | every progress write appends to `progress_history` and a reflection persists a dated occurrence; a closed period's `goals_progressed` / `principles_reviewed` count from history and the limitation note leaves the metadata |
| E3 | Retire the schedule producer | `./dev bloat --check` clean with the entry removed; `GRAPH_CONTRACT.yaml` regenerated; no worker starts at bootstrap |

Order: 0 → A1 → A2 → A1c → B2 → B1 → C1 → D0 → D1 → E1 → E2a → E2b → E3. A and D0 are independent of the rest and
may land earlier; B1 requires B2 (backfill run first); C requires B; D1 requires D0; E2a requires A2; E2b requires E2a;
E3 requires E2a.
