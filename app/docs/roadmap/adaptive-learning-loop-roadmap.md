# Adaptive Learning Loop Roadmap

**Created:** 2026-03-09
**Related:** ADR-048, `core/constants.py::LearningLoop`
**Status:** Phase 1 complete (Tasks + Habits), roadmap for remaining work

### Design Decisions (2026-03-09)

- **Choices:** Low volume early on — defer choice outcome learning until usage data accumulates. Prioritize higher-volume domains (Goals, Events) first.
- **Mastery decay:** Exponential decay with review-triggered resets (spaced repetition model). Not linear.
- **Cross-domain correlations (Tier 3):** Build infrastructure now so it's ready when user volume arrives. No active users generating 30+ days of multi-domain data yet.

---

## What Exists Today

Two domains have `learn_from_completion()` wired to the event bus:

| Domain | What It Learns | Persistence | Cold-Start Threshold |
|--------|---------------|-------------|---------------------|
| **Tasks** | Duration calibration (EMA of estimated/actual ratio) | User node: `task_duration_ratio`, `task_completion_count` | 5 samples |
| **Habits** | Completion hour histogram + on-time rate (EMA) | Habit node: `completion_hours_json`, `learned_preferred_hour`, `learned_on_time_rate` | 7 samples |

Both are fire-and-forget via EventBus subscriptions in `services_bootstrap.py`. Learning failures never block user actions.

---

## What Data Already Exists But Is Unused

This is the key insight: **SKUEL already collects significant outcome data that nothing reads back.** The adaptive learning loop is primarily about *closing the feedback loop on data we already have*, not collecting new data.

### Activity Domains — Unclosed Loops

| Domain | Data Already Collected | What Could Be Learned |
|--------|----------------------|----------------------|
| **Goals** | `GoalAchieved` event with `actual_duration_days`, `planned_duration_days`, `completed_ahead_of_schedule`, `related_task_count`, `related_habit_count` | Goal duration calibration (same EMA pattern as Tasks). Which habit/task combinations correlate with faster goal completion. |
| **Events** | `CalendarEventCompleted` event, scheduling data, completion times | Scheduling accuracy — does the user consistently run over? Preferred event duration by type. |
| **Choices** | `ChoiceMade` with `selected_option` + `confidence`, `ChoiceOutcomeRecorded` with `outcome_quality` (0.0–1.0) + `lessons_learned` | Decision quality calibration — does high confidence correlate with good outcomes? Pattern recognition across choice categories. |
| **Principles** | Alignment scores, behavioral tracking, principle strength assessments | Which principles the user actually lives vs. aspirational ones. Correlation between principle engagement and activity outcomes. |

### Curriculum — Unclosed Loops

| Data | Where It Lives | What Could Be Learned |
|------|---------------|----------------------|
| Mastery scores | `(User)-[:MASTERED {mastery_score, confidence}]->(Ku)` | Mastery decay over time (spaced repetition scheduling). Which KUs need review. |
| View counts + time spent | `(User)-[:VIEWED {view_count, time_spent_seconds}]->(Ku)` | Learning efficiency — how much time does this user need per KU? Diminishing returns detection. |
| Submission history | Submission → Exercise → Article chain | Which exercises are effective teachers. Which articles need rework (high submission failure rate). |
| LP step completion | `LearningStepCompleted` events, `KnowledgeMastered` events | Optimal step ordering. Prerequisite satisfaction rates. Path completion prediction. |
| ZPD computation | `zpd_backend.py` — current zone, proximal zone, blocking gaps | ZPD already identifies *what* to learn next. Missing: feeding completion outcomes back to refine ZPD boundary estimates. |

### Cross-Domain — Unclosed Loops

| Pattern | Data Available | What Could Be Learned |
|---------|---------------|----------------------|
| Knowledge application | `(Task)-[:APPLIES_KNOWLEDGE]->(Ku)`, same for Habits, Journals | Which KUs the user actually applies (substance). Knowledge that stays theoretical vs. lived. |
| Goal-knowledge alignment | `(Goal)-[:REQUIRES_KNOWLEDGE]->(Ku)` + mastery data | Progress toward goals measured by knowledge acquisition. |
| Activity-curriculum bridge | All 6 activity domains + mastery relationships | Does completing certain habits accelerate KU mastery? Do tasks that apply knowledge improve retention? |

---

## Roadmap: Tiers of Work

### Tier 1 — Close Existing Loops (Data → Learning)

**No new data collection. Wire existing outcome data into `learn_from_*()` methods.**

Each item follows the proven pattern: add method to `*IntelligenceService`, subscribe to existing event, persist EMA/histogram to existing Neo4j node.

1. **Goals duration calibration** — `GoalsIntelligenceService.learn_from_achievement()` subscribed to `GoalAchieved`. Same EMA pattern as Tasks. Store `goal_duration_ratio`, `goal_completion_count` on User node. High-volume domain, direct parallel to Task learning.

2. **Events scheduling calibration** — `EventsIntelligenceService.learn_from_completion()` subscribed to `CalendarEventCompleted`. Learn whether user's events run long/short. Store `event_duration_ratio` on User node. High-volume domain.

3. **Habits streak/break learning** — Already partially implemented (`handle_habit_streak_broken`, `handle_habit_missed` persist data). Missing: feeding `learned_recovery_difficulty` and `learned_difficulty_level` back into scheduling recommendations.

4. **Principles engagement decay** — Track which principles the user actively references vs. which go dormant. No event needed — can be computed from relationship timestamps during analytics queries.

5. **Choices decision quality** *(deferred — low volume early on)* — `ChoicesIntelligenceService.learn_from_outcome()` subscribed to `ChoiceOutcomeRecorded`. Correlate `confidence` with `outcome_quality`. Store `choice_calibration_score` on User node. Rich signal but needs sufficient choice volume to be meaningful.

**Prerequisites:** None. All events and data exist. Pure service-layer additions.

### Tier 2 — Mastery Feedback Loop (Curriculum Learning)

**Make mastery scores dynamic instead of write-once.**

1. **Mastery decay model (exponential + review reset)** — `UserKnowledgeMastery` has `retention_score` but nothing degrades it over time. Implement exponential decay: `retention = e^(-λt)` where `t` is time since last review and `λ` is the decay constant. Each successful review resets the clock and *decreases* `λ` (longer retention after repeated reviews — the core spaced repetition insight). Constants for `LearningLoop`: `MASTERY_DECAY_LAMBDA_INITIAL`, `MASTERY_DECAY_LAMBDA_MIN`, `MASTERY_DECAY_REVIEW_FACTOR`.

2. **Submission-driven mastery updates** — When a submission receives feedback, update the mastery score on the related KU. Good feedback → mastery increases. Revision needed → mastery decreases. Wire: `SubmissionReport` creation → mastery adjustment.

3. **Exercise effectiveness tracking** — Aggregate submission outcomes per Exercise. Exercises where students consistently struggle → flag for curriculum review. Store `exercise_success_rate` on Exercise node.

4. **LP progress prediction** — Use per-step completion times to predict total path duration. `LpIntelligenceService` already has `find_learning_sequence()` — enhance with learned time-per-step estimates.

5. **ZPD boundary refinement** — ZPD currently uses structural adjacency (graph relationships). Enhance: weight proximal zone items by user's demonstrated learning velocity in similar KU categories.

**Prerequisites:** Tier 1 patterns proven. Mastery decay requires choosing a decay function (exponential is standard in spaced repetition literature).

### Tier 3 — Cross-Domain Correlation (Pattern Discovery)

**Learn which combinations of activities produce the best outcomes.**

1. **Knowledge substance validation** — `knowledge_substance_philosophy.md` defines weights (Habits 0.10, Journals 0.07, etc.) but these are static. Track actual correlation: when a user applies a KU through a Habit, does their mastery score hold better? Adjust substance weights per-user based on evidence.

2. **Goal-habit correlation** — `GoalAchieved` events include `related_habit_count`. Over time, learn which habit types accelerate goal completion. Store correlation coefficients.

3. **Temporal productivity patterns** — Tasks already have completion timestamps. Habits have hour histograms. Aggregate across all domains: when is this user most effective? Store `productive_hours_profile` on User node.

4. **Domain interference detection** — Does high task load in a given week correlate with habit streak breaks? Does heavy curriculum engagement correlate with goal progress or goal neglect? Requires looking at weekly activity windows.

5. **Recommendation feedback loop** — `LearningRecommendation` model already has `user_action` (accepted/dismissed/deferred) and `success_outcome` fields. Nothing populates them. Wire: when a recommendation is shown and the user acts (or doesn't), record it. Over time, weight future recommendations by historical acceptance.

**Prerequisites:** Sufficient data volume across domains. Tiers 1–2 providing ongoing learning state updates. Cross-domain queries may need performance attention (multi-domain CALL{} subqueries).

### Tier 4 — Intelligent Defaults & Predictions

**Use learned patterns to make proactive suggestions.**

1. **Task duration prediction** — Replace static `duration_minutes` with `predicted_duration_minutes` based on user's calibrated ratio + task category patterns. (Partially done — Task learning already writes `predicted_duration_minutes`, but nothing in the UI consumes it.)

2. **Habit scheduling optimization** — Use `learned_preferred_hour` to suggest optimal scheduling when creating new habits. Surface "you complete habits most reliably at 7am" in the UI.

3. **Goal timeline forecasting** — Use `goal_duration_ratio` to adjust deadline estimates. "Based on your history, this goal will likely take 1.4x your estimate."

4. **Learning path time estimates** — Personalized LP duration based on user's `learning_velocity_by_domain` and per-step time history.

5. **Daily planning intelligence** — `UserContextIntelligence.get_ready_to_work_on_today()` already exists. Enhance with learned patterns: prioritize tasks at times the user has historically been productive, suggest habits during preferred hours, recommend KUs in the user's current ZPD.

**Prerequisites:** Tiers 1–3 providing stable learned parameters. UI work to surface predictions (not in scope of this roadmap — see `skuel-ui` skill).

---

## Data Gaps — What We Don't Collect Yet

These are genuinely missing signals. Each would require new data capture, not just wiring existing data.

| Gap | Why It Matters | Collection Method | Priority |
|-----|---------------|-------------------|----------|
| **Energy/capacity level** | "Took 2 hours" means different things at 8am vs midnight | Optional field on completion events, or inferred from time-of-day patterns | Low — can approximate from temporal patterns |
| **Explicit recommendation feedback** | "Was this helpful?" closes the loop fastest | UI affordance on recommendations (thumbs up/down) | Medium — high signal but requires UI |
| **Context switching cost** | Rapid domain switching may degrade performance | Computed from event timestamps (time between completions in different domains) | Low — can be derived from existing timestamps |
| **Difficulty self-assessment** | User perception vs. system estimation | Optional rating after completion | Low — `ChoiceMade.confidence` is the closest existing analogue |

**Philosophy:** Prefer deriving insights from behavioral data (what the user *does*) over asking for self-reports (what the user *says*). Self-reports are noisy. Behavioral data is ground truth.

---

## Infrastructure Requirements

None of this requires new infrastructure. The pattern is proven:

```
Existing Event → IntelligenceService.learn_from_*() → Neo4j property update → Next query reads it
```

What may need attention as volume grows:

| Concern | When It Matters | Mitigation |
|---------|----------------|------------|
| **Write amplification** | Every completion triggers N property updates | Already async/fire-and-forget. Batch if N > 3. |
| **Cold-start UX** | New users see no benefit until thresholds met | LearningLoop.MIN_SAMPLES_* constants. Show "learning..." indicator. |
| **Query complexity** | Cross-domain correlations (Tier 3) add CALL{} blocks | UserContext MEGA-QUERY already handles 6 domains. Profile before optimizing. |
| **Constants tuning** | EMA alpha, decay rates, thresholds | All in `core/constants.py::LearningLoop`. Adjustable without code changes. Add new constants per tier. |

---

## Sequencing Guidance

**Tier 1 first, fully.** It follows a pattern already proven twice (Tasks, Habits). Each domain is independent — can be done in any order. Finishing all 4 remaining Activity domains gives the system a complete behavioral profile.

**Tier 2 after Tier 1** because mastery feedback loops benefit from having Activity domain learning in place (knowing *how* the user works improves *what* curriculum to recommend).

**Tier 3 requires data volume.** Cross-domain correlations are meaningless with < 30 days of multi-domain activity. Build Tiers 1–2, let data accumulate, then mine it.

**Tier 4 is the payoff** — but only works when the underlying learning is stable and accurate. Premature predictions based on noisy early data erode trust.

---

## What This Is Not

This roadmap is about **closing feedback loops on data we already collect**. It is not about:

- Adding new features or UI surfaces
- Building ML models or requiring external AI services
- Creating new entity types or Neo4j node labels
- Changing the event bus architecture
- Adding LLM-powered analysis (all learning is `INTELLIGENCE_TIER=core` compatible)

The adaptive learning loop makes the existing system *smarter over time* by reading its own output.
