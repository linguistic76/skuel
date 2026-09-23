---
title: "Goal Progress Is One-Way — Reopens Never Recompute"
updated: 2026-09-23
status: done
registered: "2026-09-23 (Codex P1 on #1407)"
ruled: "2026-09-23 (Mike): YES — a COMPLETED goal whose recomputed progress drops below 100% is UN-ACHIEVED (status leaves COMPLETED, achieved_date cleared through the ADR-087 guard)"
---

# Goal Progress Is One-Way — Reopens Never Recompute

*Fixed 2026-09-23 in the goal-link arc's PR 1b, with
[goal-progress-recompute-lost-update.md](goal-progress-recompute-lost-update.md). Registered as a
[deferred-work.md](../deferred-work.md) entry; the defect as found is kept below, followed by
[what shipped](#what-shipped).*

## What happens

Goal progress is recomputed only on `TaskCompleted` and `HabitCompleted`. When a completion is
undone, nothing recomputes it:

- **API/UI reopen.** `update_task` publishes `TaskReopened` on a transition out of completed, but
  the event has **no subscriber anywhere**.
- **Vault reopen.** The ingest door's `status_transitions.py` builds completion events only. By
  design it publishes no reopen event, and it clears the stamp by state instead.

So completing a goal's only linked task writes 100%, `1/1`, and COMPLETED. Reopening that task
through either door leaves all three in place for good.

## Why it is live now

Before #1407 no completion moved a goal, so there was nothing for a reopen to undo. See
[goal-progress-reads-an-unwritten-edge.md](goal-progress-reads-an-unwritten-edge.md).

## Shape of the fix

The recompute counts graph state already (tally, average streak), so it can run on any trigger.
Two open questions:

1. **Trigger.** Subscribing `TaskReopened` covers the API door but not the vault door. A
   state-driven reconciliation covers both, the way the vault bridge's outbound writes follow a
   state predicate rather than a transition event.
2. **Un-achieving — RULED (Mike, 2026-09-23): yes.** A COMPLETED goal whose recomputed progress
   drops below 100% is un-achieved. Its status leaves COMPLETED and `achieved_date` is cleared
   through the ADR-087 guard, the mirror of `_achievement_write`. Progress a recompute derives
   from the graph is a measurement, and achievement follows the measurement.

This shares the handlers with
[goal-progress-recompute-lost-update.md](goal-progress-recompute-lost-update.md). Fix both in one
PR, because an atomic recompute is the natural place for a reopen trigger to land.

## What shipped

**Both reopen doors publish `TaskReopened`, and goal progress subscribes to it.** `update_task`
already published it. The vault ingest door now does too:
`classify_ingest_status_transitions` reports `reopened_uids` (prior `completed`, resulting status
not), and `_apply_status_transitions` publishes `TaskReopened` for each one from the persisted
owner (`build_reopen_events`, `_publish_reopens`). `GoalsProgressService.handle_task_reopened` is
wired in `_event_wiring.py` and runs the same recompute as `handle_task_completed`.

**Why an event and not a sweep.** The recompute is state-based: it reads the tally under the goal's
lock ([goal-progress-recompute-lost-update.md](goal-progress-recompute-lost-update.md)). The
event is only its trigger, so a lost or repeated `TaskReopened` leaves the goal correct at its
next recompute. A separate state reconciliation would need a trigger of its own. The census of
doors that can take a task out of `completed` found two. `update_task` is the chokepoint, and the
Obsidian inbound line reconciliation writes through it. The vault ingest door is the other. Every
other task status writer (`unblock_task_if_ready`, dependent scheduling, bulk complete) refuses a
terminal prior or only completes.

**Un-achieve, as ruled.** `_recompute_status_write` adds a `patch_if_prior_in(COMPLETED, {status:
active, achieved_date: null})` when the figure drops from ≥100 to <100. It is the mirror of the
achievement patch, which fires on a rise from <100 to ≥100. The trigger is the crossing, not the
level, so a goal completed by hand at 40% is not un-achieved when a recompute moves it to 60%. It
applies to both tally recomputes, so a HABIT_BASED goal whose average streak falls back below its
target is un-achieved on the next habit completion.

**Tests fail on main first.** `test_goal_progress_cascade.py` runs on the composed app. It completes
a goal's only task and then reopens it through `update_task`, and again through the vault door
(`ingest_file` of the task file, completed and then `in_progress`). Both assert 0/1, 0%, ACTIVE and
no `achieved_date`. On `main`, both read `(1.0, 1.0)`.

`TaskReopened`'s docstring, `docs/domains/tasks.md` and ADR-070 said the event was "deliberately
unsubscribed". That 2026-08-24 ruling was about analytics and the vault write-back, and it still
holds for both. The docs now name the event's two subscribers: goal progress, and context
invalidation. The vault door's reopen publishes no `TaskUpdated`, so without the second an Obsidian
reopen would leave a cached context showing the task as completed (Codex, #1408).
