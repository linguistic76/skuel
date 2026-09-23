---
title: "Goal Progress Is One-Way — Reopens Never Recompute"
updated: 2026-09-23
status: "registered — next in the goal-link arc (PR 1b)"
registered: "2026-09-23 (Codex P1 on #1407)"
trigger: "scheduled: goal-link arc PR 1b, immediately after #1407"
check: "reopening a goal's only completed task, through update_task AND through the vault door, leaves the goal at its recomputed tally (0/1, 0%) and no longer COMPLETED"
---

# Goal Progress Is One-Way — Reopens Never Recompute

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

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
[done/goal-progress-reads-an-unwritten-edge.md](done/goal-progress-reads-an-unwritten-edge.md).

## Shape of the fix

The recompute counts graph state already (tally, average streak), so it can run on any trigger.
Two open questions:

1. **Trigger.** Subscribing `TaskReopened` covers the API door but not the vault door. A
   state-driven reconciliation covers both, the way the vault bridge's outbound writes follow a
   state predicate rather than a transition event.
2. **Un-achieving.** When a COMPLETED goal's recomputed progress drops below 100%, does the goal
   reopen? If so, `achieved_date` is cleared through the ADR-087 guard, the mirror of
   `_achievement_write`. This is a product ruling. Clearing it is consistent with a derived
   measurement; keeping it treats achievement as a historical fact.

This shares the handlers with
[goal-progress-recompute-lost-update.md](goal-progress-recompute-lost-update.md). Fix both in one
PR, because an atomic recompute is the natural place for a reopen trigger to land.
