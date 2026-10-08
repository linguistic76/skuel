---
title: "Mixed Goals Get No Event-Driven Progress"
updated: 2026-10-08
status: "registered"
registered: "2026-09-23 (Codex finding on #1407)"
trigger: "a MIXED goal in real use, or the founder's ruling on the habit half (the handler touch fired 2026-10-06 with the Activity links arc PR 4; MIXED stayed out)"
check: "one ruling (what a MIXED goal's four components read from) then one PR: both progress handlers (contributions and habit completion) recompute a MIXED goal through ProgressCalculator.calculate_combined_progress from graph state, never from the stored percentage"
---

# Mixed Goals Get No Event-Driven Progress

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

## What is true now

`GoalsProgressService.handle_goal_contributions_changed` recomputes TASK_BASED goals only (from
their contributing tasks and events), and `handle_habit_completed` recomputes HABIT_BASED goals
only. A `MIXED` goal is not written by either handler, so its `progress_percentage` moves only
when someone edits it.

**The trigger's second half fired on 2026-10-06** — the Activity links arc's PR 4 rewrote the
task half: one event, `GoalContributionsChanged`, replaced the task completion and reopen
subscriptions, and the tally counts contributing tasks and events. MIXED stayed out by the
founder's ruling for that PR (only TASK_BASED goals have a contribution tally;
[activity-links-arc.md § PR 4](done/activity-links-arc.md#pr-4--contributes)): this case file waits on
its own ruling, below.

## Why MIXED was taken out

Until #1407 the handlers' goal readers matched an edge nothing writes (see
[done/goal-progress-reads-an-unwritten-edge.md](done/goal-progress-reads-an-unwritten-edge.md)),
so no branch of either handler had ever run. Each handler had a MIXED branch that blended one
component into the stored figure:

```
new = old * 0.7 + task_share * 30      # task handler
new = old * 0.7 + streak_share * 30    # habit handler
```

`old` is the previous output of this same formula, so each result feeds the next. Two linked
tasks completed in turn read 15%, then 40.5%. A redelivered event raises the figure again, and
enough completions push a goal past 100% and mark it achieved. Codex caught this on #1407: fixing
the readers would have made the formula run for the first time. The branches were deleted
rather than shipped. That changed no live behavior, because MIXED goals had never moved.

## What a real fix needs

A canonical MIXED calculation already exists: `ProgressCalculator.calculate_combined_progress`
(`core/services/infrastructure/progress_calculator.py`). It weights task 0.3, habit 0.3,
knowledge 0.2 and milestone 0.2, and computes every component from scratch. It is used only by
`calculate_goal_progress_with_context`, which returns a breakdown and persists nothing.

A handler that uses it must supply all four components from graph state:

- **Task share:** the contribution tally (`ContributionTally`, read under the goal's lock by `recompute_progress_from_contributions`) already provides it — tasks and events alike.
- **Habit component:** `calculate_habit_contribution` takes per-habit streaks
  (`habit_streaks: dict[str, int]`). The handler has an average, and treats it as streak ÷
  `target_value`, where `target_value` is a desired streak length. These are different
  measures. **This is the ruling:** which one a MIXED goal's habit half means.
- **Knowledge completion:** the goal's `REQUIRES_KNOWLEDGE` Kus that the learner has mastered.
  That needs a learner-state read the handlers do not have today.
- **Milestone completion:** `current_value / target_value`. Here `target_value` is contested by
  the habit half: the contribution planner's tally-ownership comment
  (`_plan_contribution_progress`) explains why a MIXED goal's `target_value` must not be
  overwritten.

## Live exposure

On 2026-09-23 AuraDB held 3 goals, all `percentage`-measured. No MIXED goal exists.
