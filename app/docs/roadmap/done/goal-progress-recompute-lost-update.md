---
title: "Goal Progress Recompute — Lost Update Under Concurrent Completions"
updated: 2026-09-23
status: done
registered: "2026-09-23 (Codex P1 on #1407)"
ruled: "2026-09-23 (Mike): completion_updates_goal is WIRED, default true — not deleted"
---

# Goal Progress Recompute — Lost Update Under Concurrent Completions

*Fixed 2026-09-23 in the goal-link arc's PR 1b, with
[goal-progress-one-way.md](goal-progress-one-way.md). Registered as a
[deferred-work.md](../deferred-work.md) entry; the defect as found is kept below, followed by
[what shipped](#what-shipped).*

## The race

`GoalsProgressService._update_goal_from_task_completion` works in three steps:

1. It reads the goal.
2. It reads the linked-task tally (`count_linked_tasks`).
3. It computes the new percentage and writes it through `update_with_status_guard`.

The node lock is taken only in step 3. So two completions landing together can interleave:

| Handler A (1st of 2 tasks) | Handler B (2nd of 2 tasks) |
|---|---|
| counts 1/2 | |
| | counts 2/2, writes 100%, goal → COMPLETED |
| writes 50%, `current_value=1`, `target_value=2` | |

The guard conditions only the *achievement* patch (ADR-087), not the progress fields, so the goal
ends COMPLETED at 50% and "1/2 tasks". `_update_goal_from_habit_completion` has the same shape
with `count_linked_habits_avg_streak`.

## Why it is live now

Until #1407 these readers matched an edge nothing writes, so neither recompute ever ran
([goal-progress-reads-an-unwritten-edge.md](goal-progress-reads-an-unwritten-edge.md)).
Sequential completions are correct as of #1407. Only concurrent ones race.

## Shape of the fix

ADR-087's rule is that a verdict is decided by the write, never before it. So the tally belongs
inside the guarded statement: count the linked activities after taking the goal's write lock, and
derive progress, tally and the achievement condition from that count. The alternative is to
serialize recomputes per goal. Race the statement, not the service: a service-level `gather` race
hides a missing lock, because each call does enough work to stagger itself.

## Also for this PR: `completion_updates_goal`

`Task.completion_updates_goal` (and the task-template field) is documented as "completion updates
goal progress", but **no code reads it**. Only `goal_task_generator` sets it (to True). Its
default is False, and neither the goal picker nor the create door sets it. Honoring it as-is would
drop every ordinary goal-linked task from the tally (Codex raised this on #1407, where it was
declined for that reason). The tally statement this PR rewrites is where it would be read, so rule
on it here. Either delete it, since the `FULFILLS_GOAL` link already says the task counts, or
wire it with a default that matches how links are actually made.

## What shipped

**The tally is counted under the goal's lock.** `_CrudMixin._recompute_with_status_guard` runs
one explicit transaction. It takes the goal's write-lock (the `_sg_lock` sentinel
`update_with_status_guard` uses), runs the domain's tally read, and hands the locked goal and the
tally to a pure planner. It then writes the planner's `(updates, guard)` with the same guarded
statement `update_with_status_guard` runs, which also removes the sentinel. A planner that returns
`None` rolls the transaction back. `GoalsBackend.recompute_progress_from_linked_tasks` and
`…_habits` wrap it and replace `count_linked_tasks` and `count_linked_habits_avg_streak`, which
are deleted. The two handlers' planners (`_plan_task_progress`, `_plan_habit_progress`) are
module-level pure functions.

A second recompute of the same goal blocks at the lock until the first commits, then counts what
the first wrote over. The planner's goal is the one read under the lock, so `old_progress`, the
tally-staleness check and the `progress_history` append are exact too. The history append was a
read-modify-write that could lose an entry the same way.

**Raced at the statement, not the service.** `test_task_goal_event_flow.py::TestTaskGoalRecomputeUnderTheGoalLock`
holds the goal's write-lock in a raw transaction that also completes the second task. It then runs
the first task's handler, commits the holder, and asserts 2/2, 100% and COMPLETED. On `main` it
failed with `(1.0, 2.0)`: the handler counted 1 of 2 before the lock and wrote it after. The
primitive's own contract (declined plan rolls back, no sentinel lingers, the guard reads the locked
prior, not-found) is pinned in `test_status_guarded_update.py::TestRecomputeWithStatusGuard`.

**`completion_updates_goal` is wired, default true** (ruled by Mike, 2026-09-23). The task tally
counts `FULFILLS_GOAL` tasks with `coalesce(task.completion_updates_goal, true)`, so a link counts
unless its task opts out. The default flipped to `True` on `Task`, `TaskDTO`, `TaskTemplate`,
`TaskTemplateDTO` and `TaskTemplateCreateRequest`. The generator's now-redundant `= True` is gone,
and `ACTIVITY_TEMPLATE_AUTHORING.md` documents the opt-out. The DTO persists every field, so tasks
created in the app store an explicit `false` that the new default cannot reach.
`scripts/migrations/completion_updates_goal_default_true_2026_09.cypher` rewrites those. On AuraDB
(read-only count, 2026-09-23) that is 75 tasks, none of them linked to a goal yet. No door ever set
the flag to false on purpose.
