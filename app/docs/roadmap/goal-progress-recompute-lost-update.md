---
title: "Goal Progress Recompute — Lost Update Under Concurrent Completions"
updated: 2026-09-23
status: "registered — next in the goal-link arc (PR 1b)"
registered: "2026-09-23 (Codex P1 on #1407)"
trigger: "scheduled: goal-link arc PR 1b, immediately after #1407"
check: "the linked-activity count and the goal write happen in ONE guarded statement (or are serialized per goal), for both _update_goal_from_task_completion and _update_goal_from_habit_completion; a test races two completions of a goal's last two tasks and asserts 2/2 and 100%"
---

# Goal Progress Recompute — Lost Update Under Concurrent Completions

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

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
([done/goal-progress-reads-an-unwritten-edge.md](done/goal-progress-reads-an-unwritten-edge.md)).
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
