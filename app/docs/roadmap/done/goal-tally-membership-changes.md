---
title: "Goal Tally Membership Changes Don't Recompute"
updated: 2026-10-08
status: "done — closed by the Activity links arc PR 4: every door that changes a goal's contributions publishes GoalContributionsChanged, the tally's one trigger, and ./dev reconcile-goal-tallies repairs a lost one"
registered: "2026-09-23 (Codex finding on #1408, round 3)"
trigger: "a report of a goal whose stored tally disagrees with its linked tasks, OR the next change to how goal progress is triggered"
check: "a TASK_BASED goal's stored tally (current_value/target_value) equals its live CONTRIBUTES_TO_GOAL tally after each of: linking a task or event, unlinking one, deleting one, and editing completion_updates_goal — with no contribution changing status"
---

# Goal Tally Membership Changes Don't Recompute

**Closed by the [Activity links arc](activity-links-arc.md), PR 4** (§ PR 4 — "Contributes").
A goal's tally is its owner's tasks and events that `CONTRIBUTES_TO_GOAL` the goal, and it has one
trigger: `GoalContributionsChanged` (`goal_uids`, `contributor_uids`), whose one subscriber,
`GoalsProgressService.handle_goal_contributions_changed`, recomputes each goal named and each goal a
named contributor contributes to, under the goal's lock
(`GoalsBackend.recompute_progress_from_contributions`). Every door that changes the tally publishes
it:

- a status write that moves a task or event between done, not done and out (the task and event
  status chokepoints, bulk completion, the missed-habit-event writer, the vault ingest door);
- task and event create with goals; the task update's goal list (a full replace) and a change to
  `completion_updates_goal`; the task and event link doors and their unlink service methods;
- task and event delete, with the goal uids captured before the edge goes;
- the vault: a `connections.contributes_to_goal` target added or retracted, a file deleted, a
  content-vault Edge file; and a PathStep engagement's spawn, discard and abandon.

The trigger is best-effort, so `./dev reconcile-goal-tallies`
(`GoalsProgressService.reconcile_goal_tallies`) recomputes every TASK_BASED goal whose stored tally
disagrees with its contributions. A goal whose last contribution leaves is written 0 / 0, 0%. The
dashboard's tally figures are now `total_contributions` / `completed_contributions`
(`GoalsBackend.get_contribution_tally`). The record below is the case as registered.

## What happens

A TASK_BASED goal's progress is recomputed from its linked-task tally under the goal's lock
(`GoalsBackend.recompute_progress_from_linked_tasks`,
[goal-progress-recompute-lost-update.md](goal-progress-recompute-lost-update.md)). The
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

The progress dashboard (`get_goal_progress_dashboard`, `GET /api/goals/insights`) reads the live
tally for its task figures (`GoalsBackend.get_linked_task_tally`) and the stored figure for
`progress.percentage`, so inside that window one payload shows both: `completed_tasks` 0 of
`total_tasks` 1 beside a `percentage` of 50.

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
