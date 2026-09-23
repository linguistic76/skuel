---
title: "Goal Tally Membership Changes Don't Recompute"
updated: 2026-09-23
status: "registered"
registered: "2026-09-23 (Codex finding on #1408, round 3)"
trigger: "a report of a goal whose stored tally disagrees with its linked tasks, OR the next change to how goal progress is triggered"
check: "a TASK_BASED goal's stored tally (current_value/target_value) equals its live FULFILLS_GOAL tally after each of: linking a task, unlinking one, deleting one, and editing completion_updates_goal — with no linked task changing status"
---

# Goal Tally Membership Changes Don't Recompute

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

## What happens

A TASK_BASED goal's progress is recomputed from its linked-task tally under the goal's lock
(`GoalsBackend.recompute_progress_from_linked_tasks`,
[done/goal-progress-recompute-lost-update.md](done/goal-progress-recompute-lost-update.md)). The
recompute runs only when a linked task changes status: on `TaskCompleted` and on `TaskReopened`.
Four changes alter the tally without a status transition, and none of them recomputes it:

- a task is **linked** to the goal (create or update with `fulfills_goal_uid`, or a vault
  `connections.fulfills_goal:` edge);
- a task is **unlinked**;
- a linked task is **deleted**;
- a linked task's **`completion_updates_goal`** changes. The tally reads it since #1408. On a Task
  the flag is reachable only through a vault task file; the app requests don't carry it.

Example: a goal at 1 of 2 (50%) whose completed task opts out keeps reading 50%. The live tally is
0 of 1.

## Why it is not worse

The recompute is state-derived, so the goal converges at the next completion or reopen of any
task still linked to it. The drift is also bounded: the stored figure is wrong only between a
membership change and the next status change.

## Shape of the fix

A trigger for membership changes, not a second recompute. Each door that changes membership has
to reach the goal. That is the edge writers (task create/update, the vault edge pass, deletion),
and the ingest door's property write for the flag. Two candidates:

1. Recompute the affected goals directly after the write. That makes the task service and the
   ingest door depend on goal progress.
2. Publish one event for "the tally of goal X may have changed", with goal progress as its
   subscriber. That needs a new event, and a census of every writer of `FULFILLS_GOAL` and of the
   flag.

Deletion needs the goal uids captured before the node goes.
