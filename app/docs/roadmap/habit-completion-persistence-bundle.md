---
title: "Habit-Completion Persistence Bundle — Orphans, UID Collisions, Non-Atomic Day Uniqueness"
updated: 2026-09-05
status: "ruling needed (defect 3)"
registered: 2026-08-28
trigger: "lived habit-completion use, or the next touch of the completion write path"
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
   (`calendar_service.py:1219-1224`) reads that day's completions and returns the existing one; two
   concurrent requests (two tabs) both pass the read and each create a node and increment the
   stats. The habits-surface door (`/api/habits/track` → `record_completion`) has **no** day guard
   at all. The `(habit_uid, day)` invariant has to live in persistence — the same redesign as
   defect 2 (a day-keyed uid + uniqueness constraint + upsert-on-create makes the double-tap a
   database-level no-op — **for the whole statement, not just the node**: the habit patch and every
   completion side effect must sit on the `ON CREATE` path, and the match path returns the
   already-recorded completion without incrementing or publishing anything; a `MERGE` that no-ops
   the node and still patches the counters double-counts the exact double-tap this exists to
   stop). ⚠ **Ruling needed first:** is one completion per habit-day the contract?
   Only the calendar door enforces it today; `record_completion` never said; and the streak readers
   are NOT evidence either way — `_completed_days_window` deliberately collapses rows to a set of
   days, so several completions on one day stay valid records that contribute one streak day.
   The ruling is a product decision, not an inference from the code. A multi-per-day habit would
   want a different key.
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
5. **The streak backfill wants a DISTINCT-day query.** `_completed_days_window` (`:372-390`)
   fetches raw rows (`limit=max(1000, days*2)`) and dedupes to days in Python; ≥3 same-day
   duplicates sustained across a >1000-row window starve it and `best_streak` under-reports;
   `current_streak` is protected by the `max(run, habit.current_streak)` guard only down to the
   *cached* value — a backfill that extends the current run at its oldest end under the same
   starvation reads N instead of N+1. Both directions are conservative (never over-report); the
   repair's test must cover both. Fix: a backend operation
   returning **distinct `date(completed_at)`** in a range, for the streak reads only. It is NOT the
   `find_by` row's replacement — those three reads (`get_completions_for_habit`,
   `get_today_completions`, `export_completion_history`) need whole `HabitCompletion` records and
   deliberately keep same-day duplicates. What the two share is the **normalized range
   predicate** (`date(left(toString(x), 10))` on both sides): two operations, one predicate, one
   PR.
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
`/api/context/habit/complete` — carrying `success_rate` into the shared operation, **derived and
persisted inside the same locked statement** (or derived at read time), never as post-commit
work: a recalculation that runs after the node commits recreates defect 4's stranded window and
lets concurrent completions overwrite each other's rate; the same holds for untrack's inverse —
or deletes the door; a ruling taken at build time, not a default.
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

**Not covered by the three Habit rows above, deliberately:** *Habit Streak Counters* is the HABIT
node's counters (read-then-write; what `current_streak` means); *Unwired `HabitCompletion` Model
Methods* is dormant model code; *`find_by` Datetime String-Binding* is the read-side range
predicate. This bundle is the completion node's **identity and lifecycle** and the atomicity
between the two backends. The overlaps are fix-sharing, not scope-sharing: a single-statement
lock-derived create+patch (4) closes the streak lost-update too; the DISTINCT-day operation (5)
rides the same normalized range predicate as the `find_by` row's fix.

**Trigger:** lived habit-completion use — live graph 2026-08-28: **0 `HabitCompletion` nodes**
across 5 habits, and the node-less door's footprint is zero too (`sum(h.total_completions)` 0, no
`last_completed`, `max(current_streak)` 0); the machinery has never been exercised outside #915's
swept acceptance run. ⚠ The node count alone cannot see the `/api/context` door — a habit tally
above the node count is that door's signature (`get_habit_analytics` already counts nodes only),
so the check reads both. Or
the next touch of the completion write path (`record_completion` / `_record_completion_no_event` /
`record_habit_occurrence` / `untrack_habit` / `complete_habit_with_quality`). Defect 5 is built in
the `find_by` row's PR (same predicate, distinct operations) but has its own trigger: duplicate
volume — ≥3 same-day rows sustained across a >1000-row window — which defect 3's `(habit_uid, day)`
invariant makes impossible once it lands; one natively-typed row fires the `find_by` row and says
nothing about this one. Defect 3's ruling is
Mike's, taken at build time, not in passing.
**Named cost:** orphaned completion rows after a habit delete (invisible to habit reads, counted
by user aggregates); a same-second double-tap on either door — or one bulk request naming a
habit twice — mints nodes sharing one uid; a two-tab double-complete double-counts stats; a transient stats-write failure
leaves totals permanently stale behind a "success"; a dup-heavy history under-reports
`best_streak`; an untrack answers `removed: true` having removed nothing; a tracked or calendar
completion advances no goal progress, invalidates no context cache, and reports no broken streak
(no `HabitCompleted`, no `HabitStreakBroken`).
Today every one of these costs nothing, because nothing has been written.
