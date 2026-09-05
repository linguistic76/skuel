---
title: "Habit Streak Counters — Lost-Update Race + Future-Day Credit"
updated: 2026-09-05
status: "ruling needed"
registered: 2026-08-24
trigger: "next substantive touch of the streak write path, or a lived wrong-streak report"
check: "ruling on what current_streak MEANS; the lost update is the read-then-write in both streak writers"
---

# Habit Streak Counters — Lost-Update Race + Future-Day Credit

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

Two named defects in the same write family, deliberately scoped OUT of the conditional-write arc
(numeric counters, not status transitions — a different bug class):

1. **Lost update.** Both streak writers are read-then-write: the inline CALCULATE STREAK block
   in `habits_progress_service.py` (`complete_habit_with_quality`) and `_calculate_new_streak`
   in `habits_completion_service.py` read `current_streak`/`last_completed`, compute in Python,
   and write back (`total_completions` rides the same shape). Two concurrent completions can
   drop an increment.
2. **Future-day credit — ruling needed on semantics.** Completing a FUTURE habit occurrence is
   legitimate by ruling (2026-08-23): the write doors carry no upper bound and must not gain
   one. But both writers advance `last_completed` to the completed day and increment on
   `days_since == 1`, so completing tomorrow, then the day after — in one sitting — grows
   `current_streak` without bound and freezes the inflation into `best_streak` permanently (for
   a daily habit with no recurrence end, every future day is an occurrence day). Not a
   mechanical fix: it is a question of what `current_streak` MEANS. Candidate: consecutive
   completed days ending at *today*, with future completions stored and shown but not advancing
   the streak until their day arrives. The provenance-bearing
   `HabitStreakBroken`/`HabitStreakMilestone` events publish whatever number the writer
   computed, so milestones inherit the inflation.

**Trigger:** next substantive touch of the streak write path, or a lived wrong-streak report.
**Named cost:** inflated or lost streaks and milestones; `best_streak` never heals.
