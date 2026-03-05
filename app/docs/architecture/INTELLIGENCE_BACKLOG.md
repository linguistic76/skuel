# Intelligence Backlog

Deferred intelligence gaps identified during the Context Awareness Protocol adoption (2026-03-05).
Each item has a clear trigger condition and implementation guide.

---

## 2A: Placeholder activity service params in `_create_learning_services()`

**File:** `services_bootstrap.py` lines 601–604
**Params:** `_tasks_service`, `_habits_service`, `_goals_service`, `_events_service`

**Purpose when implemented:** Cross-wire learning services with activity domain facades so that:
- KU detail pages can surface "Tasks that apply this knowledge" (`APPLIES_KNOWLEDGE` traversal)
- `LpService` can generate tasks from a learning path (`create_tasks_from_learning_path`)
- `get_next_learning_task()` can query tasks linked to knowledge units the user is ready to learn

**Prerequisite:** Item 2B (`create_tasks_from_learning_path`) must be implemented first.

**Trigger:** When implementing adaptive learning path features.

---

## 2B: Stub methods in `tasks_scheduling_service.py`

**File:** `core/services/tasks/tasks_scheduling_service.py`

### `create_tasks_from_learning_path(learning_path_uid, _user_context)` (~line 302)

Currently returns `Result.ok([])`. Real implementation needs:
- Fetch LearningPath → LearningStep sequence (via LP backend)
- For each step: check user's `mastered_knowledge_uids`, prerequisite readiness
- Create a Task per unmastered step, linked via `APPLIES_KNOWLEDGE`
- Respect `user_context.available_minutes_daily` for capacity

### `get_next_learning_task(user_context)` (~line 307)

Currently returns `Result.ok(None)`. Real implementation needs:
- Call `user_context.get_ready_to_learn()` to get ready KU UIDs
- Query Tasks that `APPLIES_KNOWLEDGE` to those UIDs, filter to incomplete/unblocked
- Rank by readiness score + task priority
- Return top candidate

**Trigger:** When enabling "Learn from path" feature on LP detail page.

---

## 2C: `_period_days` placeholder in 4 intelligence services

All 4 services accept `_period_days: int = 30` but do not apply any date filtering.

| File | Method |
|------|--------|
| `core/services/habits/habits_intelligence_service.py` | `get_habits_strength_metrics()` |
| `core/services/goals/goals_intelligence_service.py` | `get_goal_momentum_metrics()` |
| `core/services/choices/choices_intelligence_service.py` | `get_decision_velocity()` |
| `core/services/principles/principles_intelligence_service.py` | `get_principle_alignment_trends()` |

**What real implementation needs for each:**
- Build date range: `today - _period_days → today`
- Filter completion events/relationships within window
- Compute windowed metrics (streak, rate, trend/velocity)
- Return time-stamped trend direction

All 4 follow the same pattern and should be implemented together.

**Trigger:** When analytics dashboards need time-window filtering controls.

---

## 2D: `analytics_life_path_service.get_life_path_trajectory()` (~line 452)

**File:** `core/services/analytics/analytics_life_path_service.py`

Currently returns a stub dict with `"direction": "unknown"`. Real implementation needs:
- Query historical `SERVES_LIFE_PATH` relationship metadata (timestamps, scores)
- Pull alignment snapshots from 7 days ago and 30 days ago
- Compute slope: improving / stable / declining
- Return structured trajectory with per-dimension history

**Trigger:** When LifePath detail page implements the trajectory/progress view.

---

## 2E: `_include_predictions` in `habits_service.py` (~line 831)

**File:** `core/services/habits_service.py`

Currently ignored. Would enable AI-predicted completion likelihood for at-risk habits.

**Requires:** `HabitsAIService` (already wired) — uses habit streak patterns + LLM to generate
probability scores.

**Trigger:** When AI tier features are surfaced in the Habits UI.

---

## Broader Protocol Adoption (future)

The planning mixins (adopted 2026-03-05) cover the highest-leverage adoption. The remaining
~40 files and ~60 method signatures can be narrowed incrementally. Priority order:

1. Askesis services (`user_state_analyzer.py`, `action_recommendation_engine.py`) — use `CrossDomainAwareness` / `FullAwareness`
2. Domain intelligence services (tasks, goals, habits, choices, principles, events) — per-domain narrowing
3. Domain planning/progress services — same pattern as mixins
4. Domain scheduling and learning services

All follow the same zero-risk pattern: add `TYPE_CHECKING` import, narrow the type annotation,
no body changes.

**See:** `core/ports/context_awareness_protocols.py` for protocol definitions.
