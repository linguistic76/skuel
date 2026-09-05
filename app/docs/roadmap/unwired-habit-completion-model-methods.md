---
title: "Unwired HabitCompletion Model Methods — Wrong the Day They're Wired"
updated: 2026-09-05
status: "staged"
registered: 2026-08-24
trigger: "a consumer wants one of the four, or the next Habits model touch"
check: "git grep -n \"is_streak_eligible\\|was_completed_today\" -- core/services/ adapters/ ui/ — empty until wired"
---

# Unwired `HabitCompletion` Model Methods — Wrong the Day They're Wired

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

Four methods on `core/models/habit/completion.py` have ZERO production consumers —
`was_completed_today`, `days_since_completion`, `is_streak_eligible`,
`contributes_to_consistency`. `git grep` finds only `tests/unit/models/test_habit_completion.py`
(the `days_since_completion` hit in `habit_event_handler_service.py` is an unrelated same-named
parameter). Under the future-completion ruling (2026-08-23) each would be wrong the day anyone
wires it: `days_since_completion` returns a NEGATIVE for a future completion;
`is_streak_eligible`'s recency gate (`days_since_completion() > 1`) never fires for a future
completion (negative days), so it OVER-accepts — the completion passes straight to the
quality/duplicate-day checks; `was_completed_today` is false for it; `contributes_to_consistency("weekly")`'s
`week_start <= d <= today` excludes a future day inside the current week.

⚠️ **Wiring caveat:** a never-called method's edge cases were never tested — wiring one CHANGES
its meaning from staged prose to live rule. Wiring is a semantics decision (what a
not-yet-happened completion means for that reader), not a hookup; audit each against the ruling
first. `./dev bloat` does not cover model methods — this section is the visibility.

**Trigger:** a consumer wants one of these, or the next Habits model touch (then: wire
corrected, or delete — never-wired → ask, per the docs-hold-vision discriminator).
**Named cost:** dormant wrong logic that looks ready-made.
