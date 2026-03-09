# ADR-048: Adaptive Learning Loop Architecture

**Status:** Proposed
**Date:** 2026-03-09
**Deciders:** Mike

**Decision Type:** Architecture

**Related ADRs:**
- Related to: ADR-043 (Intelligence Tier Toggle)
- Related to: ADR-047 (Entity Types Replace Domain Categories)

---

## Context

SKUEL records outcomes extensively but never reads them back to improve recommendations:

- **Mastery scores** are written to `HAS_MASTERY` relationships but never update recommendation weights
- **Choice outcomes** are stored but never analyzed for decision-making patterns
- **Activity reports** are generated but don't improve future task/habit recommendations
- **Intelligence services** produce static recommendations based on current state, not learned patterns

### Prior Art: Deleted Intelligence Models

Five `*_intelligence.py` model files (~3,900 lines) attempted to solve this with frozen dataclasses containing algorithms like `learn_from_conversation()`, `predict_completion_probability()`, and domain coordination scoring. These were architecturally wrong:

1. **Frozen dataclasses can't learn** — immutable state means no adaptation
2. **No persistence** — learning state vanished on restart
3. **No data source** — algorithms had no connection to actual outcome data
4. **No event integration** — nothing triggered learning updates

The files were deleted (this ADR documents the replacement architecture), but key concepts worth preserving:

- **Outcome-weighted recommendations:** Weight suggestions by historical success rates
- **Temporal pattern analysis:** When is the user most productive for each activity type?
- **Domain coordination:** Which domain combinations work well together?
- **Multi-factor prediction:** Estimate completion probability from context (energy, time, load)

---

## Decision

Learning from outcomes will be implemented as **service-layer methods with Neo4j persistence**, not as model-layer frozen dataclasses.

### Architecture

```
Outcome Event (e.g., task.completed)
    |
    v
EventBus subscriber
    |
    v
*IntelligenceService.learn_from_outcome()
    |
    v
Neo4j property updates (on existing nodes/relationships)
    |
    v
Next recommendation query reads updated weights
```

### Key Design Decisions

1. **Learning state lives in Neo4j** — as properties on existing nodes and relationships, not as separate frozen dataclasses. Examples:
   - `(user)-[:HAS_MASTERY {weight, success_count, last_updated}]->(ku)` — existing relationship, new properties
   - `(:User {preferred_task_time, avg_completion_rate})` — existing node, new properties
   - `(:Task {predicted_duration_minutes})` — calibrated over time from actuals

2. **`*IntelligenceService` classes gain `learn_from_outcome()` methods** — extending the existing `BaseAnalyticsService` subclasses. No new service layer. Examples:
   - `TasksIntelligenceService.learn_from_completion(task_uid, actual_duration, energy_level)`
   - `HabitsIntelligenceService.learn_from_streak(habit_uid, streak_length, break_reason)`
   - `AskesisIntelligenceService.learn_from_conversation(session_uid, satisfaction_score)`

3. **Event bus integration** — outcome events (already defined in `core/events/`) trigger learning updates asynchronously:
   ```python
   @subscribe(TaskCompleted)
   async def on_task_completed(event: TaskCompleted):
       await intelligence.learn_from_completion(event.task_uid, event.actual_duration)
   ```

4. **Cold-start defaults** — when no learning data exists, services use sensible defaults from `core/constants.py`. Learning data only overrides defaults once enough samples exist (configurable threshold).

### Design Constraints

- **Must work at `INTELLIGENCE_TIER=core`** — all learning uses graph queries and Python math, no LLM calls
- **Learning updates are async** — they never block the user action that triggered them
- **Existing data sources first** — mastery relationships, choice outcomes, activity reports, habit completions are all already in Neo4j
- **No new node types** — learning state attaches to existing nodes/relationships as properties

---

## Consequences

### Positive

- Learning state survives restarts (persisted in Neo4j)
- Recommendations improve with usage (feedback loop closes)
- No new infrastructure — uses existing event bus, existing services, existing Neo4j nodes
- Works at `INTELLIGENCE_TIER=core` ($0, no API keys)

### Negative

- Learning algorithms are spread across multiple `*IntelligenceService` classes (mitigated: each service owns its domain's learning)
- Neo4j property updates add write load (mitigated: async, batched where possible)
- Cold-start period where recommendations are no better than today

### Neutral

- Intelligence model files (`*_intelligence.py`) are deleted — their speculative algorithms are replaced by data-driven implementations as each domain's learning is built out

---

## Implementation Plan

Incremental, one domain at a time:

1. **Tasks** — learn completion time calibration from `task.completed` events
2. **Habits** — learn optimal scheduling from streak/break patterns
3. **Askesis** — learn conversation style preferences from session feedback
4. **Cross-domain** — learn domain coordination patterns from concurrent activity outcomes

Each domain follows the same pattern: add `learn_from_*()` to existing `*IntelligenceService`, subscribe to existing events, store weights on existing Neo4j nodes.
