---
title: "HabitMissed — Publisher-less Chain"
updated: 2026-09-05
status: "staged (ruled keep-staged)"
registered: 2026-08-28
ruled: 2026-08-28
trigger: "a lived want for difficulty insights, or the streak-semantics ruling — they share the day model"
check: "git grep -n \"HabitMissed(\" outside core/events/ empty; MATCH (i:Insight {insight_type: 'difficulty_pattern'}) RETURN count(i) → 0"
---

# `HabitMissed` — Publisher-less Chain

*Case file for the [deferred-work.md](deferred-work.md) entry of the same name; move to `done/` when nothing in it remains open.*

`HabitMissed` (`core/events/habit_events.py:131`) is subscribed
(`services_bootstrap/_event_wiring.py:532` → `HabitEventHandlerService.handle_habit_missed`,
`core/services/habits/habit_event_handler_service.py:447`) and has **no publisher in any
commit** — `git log -S'HabitMissed('` finds only the initial commit's usage fiction, deleted in
#1173. The handler is real: structured miss/difficulty logging, and at ≥3 consecutive misses a
persisted `InsightType.DIFFICULTY_PATTERN` through `InsightStore` — a live store (11 `:Insight`
nodes on 2026-08-28: 8 `completion_pattern`, 3 `learning_progress`, **0 `difficulty_pattern`**).

**Ruling 2026-08-28 (Mike):** the three same-shaped PLANNED entries were ruled in one sitting —
`SchemaChangeDetector.add_change_handler` and `UserContext.get_recommended_next_action`
DELETED 2026-08-29 (the PR after #1179 — with `SchemaChangeEvent`, whose only reader was the
fan-out); this chain KEPT staged. It differs from the two: its consumer is a persisted insight in
a store other events already feed, not a fan-out with no reader.

**What the publisher must be:** a detector that finds occurrence days with no completion. Tier
does not constrain its shape: CORE's guarantee is **AI-scoped** ("no AI background workers" —
`GRACEFUL_DEGRADATION_ARCHITECTURE.md` § Why This Matters; the hourly `ProgressReportWorker` IS a
CORE-tier Analog worker, and `done/reopen-vault-surface.md` records "CORE runs no background
workers" as a falsified premise). So a **scheduled Analog detector** on the `ProgressReportWorker`
pattern, a **read-time** scan (compute misses since the last observation when the habit list or
`/today` loads, publish, record the watermark) and a **one-shot** (`./dev habit-miss-scan`, like
telemetry retention) are all legitimate; the constraints are no LLM, no API cost, and the day
model. Its day maths must honour the future-completion ruling (a future completion is not a
miss) and the `current_streak` semantics question in § Habit Streak Counters — the same "what
does a day mean" ruling. Do not build the detector before that ruling.
**Trigger:** a lived want for difficulty insights, or the streak-semantics ruling (they share the
day model — rule it once).
**Check:** `git grep -n "HabitMissed(" -- core/ adapters/ scripts/ services_bootstrap/ ui/ ':!core/events/'`
— empty until a publisher exists in either accepted shape (`scripts/` covers the one-shot;
`core/events/` is excluded because it holds the class definition; the subscriber in
`_event_wiring.py` is the deliberate staging);
`MATCH (i:Insight {insight_type: 'difficulty_pattern'}) RETURN count(i)` → 0.
**Named cost while staged:** `./dev bloat` carries it as PLANNED; the difficulty assessment is
code that has never run outside its unit tests.
