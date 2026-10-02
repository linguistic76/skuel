---
title: "Habit-Completion Persistence Bundle — Orphans, UID Collisions, Non-Atomic Day Uniqueness"
updated: 2026-10-02
status: "ruled — build waits on the trigger"
registered: 2026-08-28
trigger: "lived habit-completion use, or the next touch of the completion write path"
ruled: "2026-09-23 (Mike): one completion per habit per day is the contract (defect 3, option a); defect 5 is moot once that invariant lands with its historical dedupe"
check: "MATCH (hc:HabitCompletion) RETURN count(hc) AND the Habit tally (sum total_completions, max last_completed); SHOW CONSTRAINTS lists none on the label"
---

# Habit-Completion Persistence Bundle — Orphans, UID Collisions, Non-Atomic Day Uniqueness

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

Codex's "future care session" on #915 (calendar act-from arc PR 3 —
[`done/calendar-act-from-arc.md`](done/calendar-act-from-arc.md)): five findings accepted as real
and deferred there because each belongs to the `HabitCompletion` **persistence layer**
(`core/services/habits/habits_completion_service.py` + the plain
`UniversalNeo4jBackend[HabitCompletion]` in `services_bootstrap/_backends.py`), not to the
calendar surface that PR was building. Until this section they lived only in that PR's body and
two consideration notes. Re-verified against the code and the live graph 2026-08-28; a sixth
(untrack) surfaced in this section's own review (#1172).

1. **A habit delete orphans its completions.** Both production delete doors are `DETACH DELETE`:
   the API route (`CRUDRouteFactory`'s `delete`, wired for every Activity Domain by
   `create_activity_domain_route_config`) calls `delete_for_user(uid, user_uid, cascade=True)`,
   which goes straight to `backend.delete(cascade=True)`; the vault reconciler
   (`IngestionTracker._execute_deletion_plan` → `IngestionBackend.delete_entities_with_metadata`,
   `DETACH DELETE` leaf-first) has no non-cascading variant at all. (`HabitsCoreService.delete` defaults
   to `cascade=False` and no production caller passes `True` — irrelevant, because neither door
   goes through it, and a plain `DELETE` could not succeed anyway: every habit carries its `:OWNS`
   edge.) A completion is tied
   to its habit by the `habit_uid` *property* only — its one edge is
   `(User)-[:OWNS]->(:HabitCompletion)` (`_create_node`, per the model's field docstring). But the
   edge is not the point: `DETACH DELETE` removes the habit and its relationships and never touches
   a neighbouring node, so an edge would not help either. **Requirement:** both delete doors
   explicitly `MATCH` and delete the habit's `HabitCompletion` nodes in the same deletion statement
   (the habit-specific backend delete and `delete_entities_with_metadata`'s Habit shape) — a
   bundle closed without that still orphans. Today the rows stay: unreachable from any habit read, still counted by every
   user-scoped `OWNS` aggregate (`activity_backends.py:413` high-quality count,
   `cross_domain_backend.py`'s consistency window). Both writers orphan identically; #915's own
   acceptance run swept its residue by hand.
2. **The completion uid is second-granularity and unconstrained.**
   `hc.{user_uid}.{habit_uid}.{int(now.timestamp())}` (`record_completion`, `:133`); the bulk door
   keys on the request's `completed_at` (`:265`), which defaults to `datetime.now()` per request
   and which its one production caller (`habits_api.py`, the bulk route) never passes — so bulk
   collides on the same second exactly as the single door does — and deterministically in one case
   reachable today: `BulkCompleteHabitsRequest.habit_uids` (`min_length=1`, no uniqueness check)
   accepts the same habit twice and the loop shares one `now`, so `["habit.x", "habit.x"]` mints
   one uid twice and increments the habit twice. The repair rejects a duplicated list at the
   boundary. Nothing enforces uniqueness:
   the model declares no `field(metadata={"index": ...})`; of the five startup sync routines in
   `services_bootstrap/compose.py` (`sync_auth_indexes` / `sync_vector_indexes` /
   `sync_domain_indexes` / `sync_fulltext_indexes` / `sync_conversation_indexes`) none names the
   label, and the `:Entity` uid uniqueness constraint `sync_domain_indexes` creates cannot reach it
   because its backend is built without `base_label=NeoLabel.ENTITY`; live AuraDB
   `SHOW CONSTRAINTS` (2026-08-28) lists 7 constraints, **none on `HabitCompletion`** (no index
   either). The eventual constraint belongs in `sync_domain_indexes`, alongside the per-label uid
   indexes it already owns — **behind a preflight**: Neo4j refuses to create a uniqueness
   constraint over a label that already violates it, and this work is triggered by lived use, i.e.
   after today's writers may have minted duplicates; a dedupe/migration (or an explicit
   duplicate-count preflight that fails the repair, not the boot) has to run before the constraint
   is enabled, or the repaired build cannot bootstrap. #915 live-verified three same-second
   writes → three nodes sharing one uid. The `hc.` spelling is registered nowhere else (no prefix validation knows it);
   the ratified separator grammar spells generated UIDs with `_` — settle the spelling when the key
   is redesigned, not before.
3. **Day idempotency is a read-before-write guard, not an invariant.** `record_habit_occurrence`
   (`core/services/calendar_service.py:1188-1193`) reads that day's completions and returns the existing one; two
   concurrent requests (two tabs) both pass the read and each create a node and increment the
   stats. The habits-surface door (`/api/habits/track` → `record_completion`) has **no** day guard
   at all. The `(habit_uid, day)` invariant has to live in persistence — the same redesign as
   defect 2 (a day-keyed uid + uniqueness constraint + upsert-on-create makes the double-tap a
   database-level no-op — **for the whole statement, not just the node**: the habit patch and every
   completion side effect must sit on the `ON CREATE` path, and the match path returns the
   already-recorded completion without incrementing or publishing anything; a `MERGE` that no-ops
   the node and still patches the counters double-counts the exact double-tap this exists to
   stop). **Ruled (Mike, 2026-09-23): one completion per habit per day is the contract.**
   Every frequency the model can express is counted in days (`RecurrencePattern` stops at
   `DAILY`; the only count field is `target_days_per_week`), and so are the denominators the
   row-counting readers divide by (`success_rate`, `get_completion_stats`, the completed-today
   count). Those readers are correct once the invariant holds. Today a same-day duplicate
   inflates them. So the build is the day-keyed uid, the uniqueness constraint behind its
   preflight, and create-if-absent described above. Defect 2's uid and defect 4's single
   statement are the same statement.
4. **A transient stats-write failure strands the node behind a later "success".** Write order is
   compute → `completions_backend.create` → `habits_backend.update` (`:162`). If the update fails
   after the create landed, the node exists with `total_completions` / streaks / `last_completed`
   stale, and a calendar retry is intercepted by defect 3's existing-day return — reported success,
   no repair (the `record_completion` docstring names this "the residual window"). The bulk door
   is worse: `_record_completion_no_event` (`:311`) **discards** the stats update's `Result`, so
   `/api/habits/bulk-complete` counts the completion and publishes `HabitCompletionBulk` on the
   spot even when the stats write failed — no retry is even attempted. And the bulk loop appends
   only `is_ok` results and always returns `Result.ok`, so `/api/habits/bulk-complete` answers 201
   on partial failure: atomicity alone does not close this writer — per-item failures must
   propagate or be reported. ⚠ The one-line
   "propagate the error" is NOT the fix there: the node is already stored, so propagating drops an
   existing completion from the response and the event — the same strand in a different coat.
   Only the atomicity work below closes either writer. Fix shapes: one
   Cypher statement that creates the node and patches the habit — the primary shape. It closes the
   streak lost-update race above **only if the statement derives the counters from the node's
   state after taking the write lock** (ADR-087's shape: lock, read prior, patch in the same
   statement); a Python-computed absolute `N+1` serialized twice is still `N+1`. Derivation is an
   alternative only if it covers
   **every** field the patch writes — `total_completions`, `current_streak`, `best_streak`,
   `last_completed`, `identity_votes_cast` — plus the milestone events keyed off them; deriving the
   tally alone (the direction `cross_domain_backend.py`'s consistency window took because the bulk
   door's nodes are invisible to the tally) heals one field of five and leaves the rest of this
   defect open.
5. **Moot once defect 3's invariant lands (ruled 2026-09-23).** With one completion per habit
   per day enforced, the window holds at most one row per day, and `limit=max(1000, days*2)` can
   never starve it. Nothing is built for it separately. That holds only if the landing
   **re-keys and dedupes the existing rows to `(habit_uid, day)`** as well as keying new writes.
   The constraint's preflight has to collapse historical same-day duplicates, not merely count
   them. It also has to leave the cached counters (`total_completions`, `identity_votes_cast`)
   consistent with the deduplicated history, because later writes build on them. No single
   mechanical rule does that. Subtracting once per removed row undercounts wherever defect 4's
   lost update or stranded node already dropped the increment. Recomputing from nodes erases the
   node-less `/api/context` door's contribution. So the reconciliation is decided together with
   the historical baseline below, at build time. Until then, today's doors can still write
   duplicates. The analysis below is kept because it applies again if the contract
   ever changes. `_completed_days_window` fetches raw rows (`limit=max(1000, days*2)`), newest
   first, and dedupes to days in Python. The cap drops the OLDEST rows, so it starves only when
   the window holds more than `max(1000, 2 × window days)` rows, which means averaging over two a
   day across a window of at least a year. Then `best_streak` under-reports;
   `current_streak` is protected by the `max(run, habit.current_streak)` guard only down to the
   *cached* value — a backfill that extends the current run at its oldest end under the same
   starvation reads N instead of N+1. Both directions are conservative (never over-report); the
   repair's test must cover both. Fix: a backend operation
   returning **distinct `date(completed_at)`** in a range, for the streak reads only. It does not
   replace the three whole-record reads (`get_completions_for_habit`, `get_today_completions`,
   `export_completion_history`), which need whole `HabitCompletion` records, deliberately keep
   same-day duplicates, and go through `find_by_date_range`
   ([done](done/find-by-datetime-string-binding.md)). It reuses that read's **normalized range
   predicate** (the days' bounds in the current zone, `stored_day_bounds`), and a day it returns
   is the one the completion falls on in that zone.
6. **Untrack cannot delete, says it did, and would not recompute if it could.** `untrack_habit`
   (`_completion_mixin.py:88`, `POST /api/habits/untrack`) deletes each of the day's completions
   with `completions_backend.delete(uid)` — default `cascade=False`, the plain `DELETE` the mixin
   documents as "will fail if entity has any relationships" — and every completion has carried its
   `(User)-[:OWNS]->` edge since #1100, so the delete has been refused on every call since then;
   the loop **discards** each `Result`, so the route answers `{"removed": true}` regardless. No
   test covers the door. Had it deleted, nothing recomputes `total_completions` / `current_streak`
   / `best_streak` / `last_completed` / `identity_votes_cast` / `success_rate` (an untrack inside
   the trailing consistency window changes its numerator) — cached stats diverge from the node set
   exactly as in defect 4, in the other direction. Requirement: one atomic
   delete-and-recompute (the inverse of defect 4's create-and-patch, the same single-statement
   shape), `cascade=True`, errors propagated — **and an inverse event with explicit subscriber
   semantics** (name it at build time; a new `core/events` module must be imported in
   `core/events/__init__.py`): the user-context cache must invalidate, linked-goal progress that
   `GoalsProgressService.handle_habit_completed` advanced must recompute, and once the shared
   writer emits `HabitCompleted` its analytics / timing-learning subscribers must be told the
   completion is gone, or every one of them keeps the removed completion. Two node writes are not
   the whole inverse. Found by Codex on #1172, not on #915.

⚠ **A third writer creates no node at all.** `POST /api/context/habit/complete` →
`UserContextService.complete_habit_with_context` →
`HabitsProgressService.complete_habit_with_quality` increments `total_completions`, advances
`current_streak` / `best_streak` / `last_completed` via `backend.update_habit`, is the ONLY
completion path that recalculates and persists **`success_rate`** (the consistency value habit
enrichment, AI, pattern and scheduling readers consume — `record_completion` never touches it),
and publishes `HabitCompleted` — without ever creating a `HabitCompletion`. Every node-derived
shape above
(derived stats, untrack's recompute, the `(habit_uid, day)` invariant) would erase or bypass that
door's contribution. The redesign migrates it onto the completion-node path — **one shared,
lock-derived persistence operation behind all four production doors**: `/api/habits/track`
(`record_completion`), the calendar (`record_habit_occurrence` → the same), `/api/habits/bulk-complete`
(`_record_completion_no_event`, with explicit bulk response/event semantics — today it has UID
collisions, discarded update failures, partial success and non-canonical events of its own), and
`/api/context/habit/complete` — or deletes the door; a ruling taken at build time, not a default.
The rate is no longer the shared operation's to persist: it is **derived at read time** (ruled
2026-10-01, see *A rate derived at read time* below), so the migrated door's only obligation to
it is to leave a node behind — a rate persisted after the node commits would recreate defect 4's
stranded window and let concurrent completions overwrite each other's value.
A redesign that leaves bulk on its own helper closes the bundle with a defective path still
open. **And routing future calls is not enough:** every contextual completion made before the
migration exists only in `Habit.total_completions`, the streak fields and already-published
events — a node-derived `success_rate` or untrack recompute would erase that history, and the
tally-vs-node trigger below only *detects* the condition. The bundle carries a historical
baseline/reconciliation step before any node-derived write is enabled (seed the pre-migration
tally as a baseline, or backfill it as nodes — a ruling), unless it lands before the first
contextual completion. (Its own
read-then-write streak block is already the *Habit Streak Counters* row's first item.)

⚠ **And the event asymmetry runs the other way.** That node-less door is today the ONLY
publisher of `HabitCompleted` (`habits_progress_service.py:298` — the only `HabitCompleted(`
left in the tree since the `core/events/habit_events.py` usage-example fiction, which cited a
`log_completion` that never existed, was deleted 2026-08-28). `record_completion` publishes
`HabitStreakMilestone` only, so the two
node-writing doors (`/api/habits/track`, calendar) reach none of the four wired subscribers —
`GoalsProgressService.handle_habit_completed` (goal progress),
`CrossDomainAnalyticsService.handle_habit_completed`,
`HabitEventHandlerService.handle_habit_completed`, and `MetricsEventHandler._on_habit_completed`
(the Prometheus `entities_completed{entity_type="habit"}` counter — completion telemetry is blind
to them too) — nor the user-context cache invalidation keyed on it. The same holds for `HabitStreakBroken`: `_calculate_new_streak` resets the streak after a
gap, but `record_completion` publishes only `HabitStreakMilestone` (`_check_streak_milestones`), so
the wired `HabitEventHandlerService` subscription never hears a tracked or calendar break —
`complete_habit_with_quality` (`:309`) is again the only real publisher — the second
constructor was in that same deleted example block. A live gap on the node doors now, not only
a consolidation
hazard: the shared committed writer must carry the canonical `HabitCompleted` and
`HabitStreakBroken` and the contextual side effects with it, or the merge silently disconnects
goal progress and streak recovery from every completion. **With explicit completion-time
semantics:** `BaseEvent.occurred_at` defaults to `datetime.now()`, and two subscribers read it
directly — `CrossDomainAnalyticsService.handle_habit_completed` persists it,
`HabitEventHandlerService.handle_habit_completed` learns the completion hour from it — so a
canonical event published as-is stamps a backfilled or future occurrence as completed *now* and
trains scheduling on the request hour (and setting `occurred_at` to the date-only midnight trains
an artificial hour instead). The shared writer's event carries the occurrence's own
`completed_at`, and a date-only backfill is excluded from the **whole timing sample** — not the
hour histogram alone: `HabitCompleted.completed_on_time` defaults to `True` and the same handler
feeds it into `learned_on_time_rate`, so an unknown-time completion left on the default is
counted as known-on-time and inflates the EMA and its sample count — defined, not defaulted.
And a **future-dated** completion (legitimate by the 2026-08-23 ruling — see the *Habit Streak
Counters* row) is stored but must not feed behaviour that has not happened yet into downstream
state: published as-is, `CrossDomainAnalyticsService.handle_habit_completed` would pass the
future timestamp into `_upsert_counter_analytics` (a permanently future `first_completion_at`)
and the handler would learn its hour and on-time sample. Its side effects are deferred or
excluded until its occurrence day arrives — the same decision as that row's `current_streak`
semantics, taken once.

⚠ **A rate derived at read time — pulled forward out of this bundle (HA-1, ruled 2026-10-01).**
A rate over "the last thirty days" changes when a day passes with no completion, so a value
persisted at completion time cannot stay true — a habit kept daily and then dropped would hold
1.0 forever. Mike ruled (A1) that the rate is derived when it is read, and that the derivation is
not this bundle's work: it shipped ahead of it. What it is now:

- **One definition.** `core/models/habit/adherence.py` — `habit_adherence(recurrence_pattern,
  target_days_per_week, completed_on, *, created_on, today)`: the habit's completions in the
  trailing `HabitConsistencyWindow` over what its frequency expects there, at most 1.0 —
  lifted out of `HabitsProgressService._calculate_consistency_from_completions`, which now calls
  it. Two rulings (Mike, 2026-10-02) shape `expected`: the span is cut short at the habit's
  creation day (a 3-day-old daily habit kept 3/3 reads 1.0, not 0.1), and every
  `RecurrencePattern` expects what the span holds of its own cadence (`expected_completions`:
  daily every day; weekdays / weekends the days of their kind on the calendar; weekly, biweekly,
  monthly the whole periods; custom its weekly target scaled). Quarterly, yearly and one-time
  habits — and a habit with nothing due yet in its span — have **no rate** (`None`): they are left
  out of every average and never at risk, rather than read as 0.0. Both sides of the ratio are
  counted over the one span: `completed_on` holds the day of each completion, and a completion
  backfilled to before the habit existed is outside it (Codex r2 on #1488 — counting the window
  but measuring from creation let three pre-creation backfills read a new habit as 1.0).
- **One read.** `adapters/persistence/neo4j/query/cypher/habit_fragments.py` — the window
  predicate (`datetime()` on both operands, `[start, end)` from `stored_day_bounds`, so a
  future-stamped completion is outside) and the per-habit completions (the `completed_at` stamps of
  completions the habit's OWNER owns that name the habit — stamps, not a count, so the creation-day
  cut is made in the user's zone by `completion_days`). Composed by `CrossDomainBackend.get_habit_analytics` (per user),
  `HabitsBackend.get_habit_window_completions` (per habit, on `HabitsOperations`), and both
  user-context statements. `HabitsService.get_adherence_rates(habits)` composes the per-habit
  completions with `habit_adherence` for any caller holding Habit models.
- **The readers the stale `completion_rate` name used to blind.** `HABIT_ADHERENCE_QUERY` (its own
  `RICH_CONTEXT_STATEMENTS` entry) and `CONSOLIDATED_QUERY` project each active habit's window
  completions; the populator derives `UserContext.habit_completion_rates` from it, so the at-risk
  classification (active habits only: no streak, or under half), `HabitsStats.consistency_rate`,
  the overall completion blend (`core/services/user_stats_types.py`) and `ContextualHabit`'s
  fallback rate are true together. `TemporalMomentumMixin` reads the derived rates (`None` for a
  user with no habit that has a rate); `AnalyticsMetricsService.calculate_habit_metrics` reads
  `HabitsService.get_adherence_rates`. A completion through `complete_habit_with_quality` on a
  habit with no rate stores the field's default (0.0) rather than leaving an earlier rate standing. Nothing reads a `completion_rate` property off a Habit node any
  longer, and no fixture writes one.
- **Not yet:** the stored `Habit.success_rate` and its ~25 readers (goal prediction, dual-track,
  scheduling, planning, intelligence, AI, the habit detail page) still read the field
  `complete_habit_with_quality` persists — HA-2 hydrates it at the Habit read chokepoints from the
  same count and retires the stored field and its writer.

**B1 — the node-less door is left exactly as it is, and is invisible to the rate.** Only a
`:HabitCompletion` node counts, so a completion made through `POST /api/context/habit/complete`
(`complete_habit_with_quality`) counts for nothing in the derived rate until this bundle migrates
that door onto the shared node-writing operation (which it already requires). The door has no UI
caller.

**The bundle keeps every write-side defect, and its trigger.** No write path was touched by the
derivation. The derived rate counts nodes, so the defects above now reach it: a same-day
double-tap or a same-second uid collision (defects 2 and 4) adds a node and inflates the day's
count until the `(habit_uid, day)` invariant lands — bounded by the clamp at 1.0 — and an
orphaned completion (defect 1) still counts toward a user's per-user consistency, though not
toward any habit's rate (its habit is gone).

**Not covered by the three Habit rows above, deliberately:** *Habit Streak Counters* is the HABIT
node's counters (read-then-write; what `current_streak` means); *Unwired `HabitCompletion` Model
Methods* is dormant model code; the read-side range predicate is `find_by_date_range`
([done](done/find-by-datetime-string-binding.md)). This bundle is the completion node's **identity and lifecycle** and the atomicity
between the two backends. The overlaps are fix-sharing, not scope-sharing: a single-statement
lock-derived create+patch (4) closes the streak lost-update too; the DISTINCT-day operation (5)
rides `find_by_date_range`'s normalized range predicate.

**Trigger:** lived habit-completion use — live graph 2026-08-28: **0 `HabitCompletion` nodes**
across 5 habits, and the node-less door's footprint is zero too (`sum(h.total_completions)` 0, no
`last_completed`, `max(current_streak)` 0); the machinery has never been exercised outside #915's
swept acceptance run. Re-read 2026-10-02 (HA-1, read-only): **1 node** across 6 habits (all
daily), `completed_at` an ISO string (`2026-09-04T07:00:00`), owned by its habit's owner, and
`sum(h.total_completions)` 1 — tally equals node count, so no `/api/context` completion; no Habit
carries a non-zero `success_rate`, none carries `completion_rate`. ⚠ The node count alone cannot see the `/api/context` door — a habit tally
above the node count is that door's signature (`get_habit_analytics` already counts nodes only),
so the check reads both. Or
the next touch of the completion write path (`record_completion` / `_record_completion_no_event` /
`record_habit_occurrence` / `untrack_habit` / `complete_habit_with_quality`). Defect 3's ruling
is taken (one completion per habit per day), so defect 5 has no trigger of its own left. It
closes when defect 3 lands with its historical dedupe.
**Named cost:** orphaned completion rows after a habit delete (invisible to habit reads, counted
by user aggregates); a same-second double-tap on either door — or one bulk request naming a
habit twice — mints nodes sharing one uid; a two-tab double-complete double-counts stats; a transient stats-write failure
leaves totals permanently stale behind a "success"; a dup-heavy history under-reports
`best_streak`; an untrack answers `removed: true` having removed nothing; a tracked or calendar
completion advances no goal progress, invalidates no context cache, and reports no broken streak
(no `HabitCompleted`, no `HabitStreakBroken`).
Today every one of these costs next to nothing: one completion has been written.
