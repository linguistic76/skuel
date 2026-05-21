# Intelligence Backlog

Deferred intelligence gaps. Each item has a clear trigger condition and implementation guide.

> **History note (2026-05-11):** This backlog was originally framed around extending an ISP-protocol adoption (the 11 "awareness slices" of UserContext). Those protocols were retired in commit `a82faaba` — `UserContext` is now the single source of truth. The remaining backlog items below are real intelligence gaps that survived the consolidation.

---

## 2A: Placeholder activity service params in `_create_learning_services()`

**File:** `services_bootstrap/_learning_services.py`
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
- Fetch LearningPath → PathStep sequence (via LP backend)
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
| `core/services/goals/goaps_intelligence_service.py` | `get_goal_momentum_metrics()` |
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

<!-- "Broader Protocol Adoption" section removed 2026-05-11 — the awareness-slice
     protocols were retired in commit a82faaba in favor of UserContext as the
     single source of truth. There is no protocol-narrowing work to schedule. -->

