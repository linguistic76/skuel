---
title: "Mixed Goals Get No Event-Driven Progress"
updated: 2026-09-23
status: "registered"
registered: "2026-09-23 (Codex finding on #1407)"
trigger: "a MIXED goal in real use, or the next touch of GoalsProgressService's completion handlers"
check: "one ruling (what a MIXED goal's four components read from) then one PR: both completion handlers recompute a MIXED goal through ProgressCalculator.calculate_combined_progress from graph state, never from the stored percentage"
---

# Mixed Goals Get No Event-Driven Progress

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

## What is true now

`GoalsProgressService.handle_task_completed` recomputes TASK_BASED goals only, and
`handle_habit_completed` recomputes HABIT_BASED goals only. A `MIXED` goal is not written by
either handler, so its `progress_percentage` moves only when someone edits it.

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

- **Task share:** `count_linked_tasks` already provides it.
- **Habit component:** `calculate_habit_contribution` takes per-habit streaks
  (`habit_streaks: dict[str, int]`). The handler has an average, and treats it as streak ÷
  `target_value`, where `target_value` is a desired streak length. These are different
  measures. **This is the ruling:** which one a MIXED goal's habit half means.
- **Knowledge completion:** the goal's `REQUIRES_KNOWLEDGE` Kus that the learner has mastered.
  That needs a learner-state read the handlers do not have today.
- **Milestone completion:** `current_value / target_value`. Here `target_value` is contested by
  the habit half: the task handler's tally-ownership comment
  (`_update_goal_from_task_completion`) explains why a MIXED goal's `target_value` must not be
  overwritten.

## Live exposure

On 2026-09-23 AuraDB held 3 goals, all `percentage`-measured. No MIXED goal exists.
