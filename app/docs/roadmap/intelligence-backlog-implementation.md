# Intelligence Backlog: Implementation Guide

Five deferred intelligence gaps identified during the Context Awareness Protocol adoption
(2026-03-05). Each item has a concrete starting point, the exact files to touch, and the
data model and query patterns already in place.

**Source of truth for what to build:** `/docs/architecture/INTELLIGENCE_BACKLOG.md`
**This file:** How to start building each item.

---

## Item 2A — Cross-wire learning services with activity facades

**What it unlocks:** KU detail pages that surface related tasks; LP pages that can
generate a task plan for a user; `get_next_learning_task()` returning real results.

**Current state:**
`services_bootstrap.py` lines 601–604 accept `_tasks_service`, `_habits_service`,
`_goals_service`, `_events_service` but discard them. They are passed in at lines 1414–1417.

**Starting point — `_create_learning_services()` in `services_bootstrap.py`:**

The four facade services are already wired into `activity_services` at bootstrap time and
already passed as arguments — they just hit dead-end underscore params. To activate:

1. Remove the underscore prefix from the four params (`_tasks_service` → `tasks_service`).
2. Store them on the returned dict or pass them directly into the service constructors
   that need them (`LpService`, `KuService`).
3. Each receiving service constructor needs a matching `tasks_service` kwarg.

**Where the cross-wiring is consumed:**
- `LpService` — `create_tasks_from_learning_path()` (see Item 2B) needs `tasks_service`
  to call `tasks_service.create_task()`.
- `KuService` (or `KuIntelligenceService`) — a future `get_applying_tasks(ku_uid, user_uid)`
  method queries `APPLIES_KNOWLEDGE` edges from the task side.

**Prerequisite:** Item 2B must be implemented before activating this wiring, otherwise
`create_tasks_from_learning_path()` would have the service but still return `[]`.

---

## Item 2B — Implement stub methods in `tasks_scheduling_service.py`

**File:** `core/services/tasks/tasks_scheduling_service.py`

Two adjacent stub methods at lines 283 and 307. Implement them together — they share
the same dependency pattern.

---

### `create_tasks_from_learning_path(learning_path_uid, _user_context)`

**Current body:** logs a debug message and returns `Result.ok([])`.

**What the implementation needs to do:**

1. **Fetch the LP sequence.** Use `LpService` (or `LpBackend` directly) to get the
   ordered learning steps. The LP backend already has `get_paths_containing_ku()` and
   `get_ku_mastery_progress()` — use `LpBackend` to get the step sequence:
   ```cypher
   MATCH (lp:LearningPath {uid: $uid})-[:CONTAINS_STEP {order: order}]->(ls:LearningStep)
         -[:TEACHES]->(ku:Entity)
   RETURN ku.uid, ku.title, ls.order
   ORDER BY ls.order
   ```

2. **Filter by mastery.** Check `_user_context.mastered_knowledge_uids` (already populated
   on `UserContext`). Skip KUs the user has already mastered.

3. **Check prerequisite readiness.** Use `_user_context.prerequisites_needed` — skip KUs
   whose prerequisites are not yet in `_user_context.prerequisites_completed`.

4. **Create one Task per unmastered, ready step.** Call `self.backend.create()` with a
   `TaskCreateRequest`-style dict. Link the task to the KU via `APPLIES_KNOWLEDGE`
   (use `TasksBackend.link_task_to_knowledge(task_uid, ku_uid)` — already exists on
   `TasksBackend` in `domain_backends.py`).

5. **Respect capacity.** If `_user_context.available_minutes_daily` is set, cap the
   number of tasks created to fit within that budget (each task has an estimated duration
   field). Drop the underscore prefix once implemented.

**Rename:** `_user_context` → `user_context` once the param is used.

---

### `get_next_learning_task(user_context)`

**Current body:** calls `user_context.get_ready_to_learn()` (real method on `UserContext`,
returns a list of KU UIDs) but then short-circuits to `Result.ok(None)`.

`get_ready_to_learn()` is already implemented at `unified_user_context.py:633`. It checks
`next_recommended_knowledge` against `prerequisites_needed` and `prerequisites_completed`.

**Implementation steps:**

1. Call `ready_knowledge = user_context.get_ready_to_learn()` (already in the body).

2. If `ready_knowledge` is empty, return `Result.ok(None)` (already there).

3. For the non-empty case — query Tasks linked to any ready KU via `APPLIES_KNOWLEDGE`:
   ```cypher
   MATCH (u:User {uid: $user_uid})-[:OWNS]->(t:Entity:Task)
   MATCH (t)-[:APPLIES_KNOWLEDGE]->(ku:Entity)
   WHERE ku.uid IN $ready_knowledge_uids
     AND t.status NOT IN ['completed', 'failed', 'cancelled', 'archived']
   RETURN t, ku.uid as knowledge_uid
   ORDER BY t.priority DESC
   LIMIT 1
   ```
   Use `self.backend.execute_query()` for this raw Cypher (it's a cross-domain query).

4. Deserialize the result with `self._context_to_domain_model()` and return as
   `Result.ok(task_model)`.

5. If no linked tasks exist, return `Result.ok(None)` — the caller in
   `UserContextIntelligence` handles the None case.

---

## Item 2C — Activate `_period_days` filtering in 4 intelligence services

**Pattern:** Identical in all four services. Implement together.

| File | Method | Line |
|------|--------|------|
| `core/services/habits/habits_intelligence_service.py` | `get_performance_analytics()` | 142 |
| `core/services/goals/goals_intelligence_service.py` | `get_performance_analytics()` | 173 |
| `core/services/choices/choices_intelligence_service.py` | `get_decision_velocity()` | 138 |
| `core/services/principles/principles_intelligence_service.py` | `get_principle_alignment_trends()` | 145 |

**Current state:** Each method fetches ALL entities via `backend.find_by(user_uid=user_uid)`
and computes aggregate metrics. The `_period_days` param is passed through to the response
dict but never used for filtering.

**What changes:**

1. **Rename the param.** Drop the underscore: `_period_days` → `period_days`. This is the
   signal that the param is now in use (per CLAUDE.md naming conventions).

2. **Compute the cutoff date** at the start of each method:
   ```python
   from datetime import date, timedelta
   cutoff = date.today() - timedelta(days=period_days)
   ```

3. **Filter the fetch.** The backends support `created_at__gte` filter syntax via
   `UniversalNeo4jBackend.find_by()`. Replace:
   ```python
   # before
   await self.backend.find_by(user_uid=user_uid)
   ```
   with:
   ```python
   # after
   await self.backend.find_by(user_uid=user_uid, updated_at__gte=cutoff)
   ```
   For habits, `updated_at` reflects the last check-in. For goals, filter on
   `updated_at` for activity (or `target_date__gte` to include currently active goals).

4. **Windowed trend metrics.** For `get_decision_velocity()` (choices) and
   `get_principle_alignment_trends()` (principles), the windowed metric is:
   `count_completed / period_days` — decisions resolved per day, principles acted on per day.
   These services currently count totals; divide by `period_days` to get velocity.

5. **Add trend direction.** Compare the windowed rate against a 90-day baseline:
   - Fetch a 90-day window count separately
   - `rate_30d = count_30d / 30`
   - `rate_90d = count_90d / 90`
   - `direction = "improving" if rate_30d > rate_90d * 1.1 else "declining" if rate_30d < rate_90d * 0.9 else "stable"`

**Testing pattern:** Each of these services already has unit tests in `tests/unit/`. The
test pattern is to mock `self.backend.find_by` — just extend the mock to also handle the
`updated_at__gte` kwarg and return a filtered list.

---

## Item 2D — Implement `_calculate_alignment_trends()` in `analytics_life_path_service.py`

**File:** `core/services/analytics/analytics_life_path_service.py`

**Method:** `_calculate_alignment_trends(user_uid, life_path_uid)` at line 417.

**Current body:** Returns a hardcoded dict with `"direction": "unknown"` and two `None`
snapshot fields.

**What it needs:**

The method is private and called from `calculate_life_path_alignment()`. The alignment
score is already computed by the parent method — what's missing is the historical comparison.

**Where the historical data lives:**

SKUEL does not yet persist alignment snapshots as nodes. The approach that works without
adding new node types is to query the `SERVES_LIFE_PATH` relationship metadata —
specifically the `created_at` and `score` properties that are set when
`UnifiedRelationshipService.link_to_life_path()` is called.

**Implementation steps:**

1. **Query time-windowed SERVES_LIFE_PATH scores:**
   ```cypher
   MATCH (e:Entity)-[r:SERVES_LIFE_PATH]->(lp:LearningPath {uid: $life_path_uid})
   MATCH (u:User {uid: $user_uid})-[:OWNS]->(e)
   RETURN r.score as score, r.created_at as created_at
   ORDER BY r.created_at DESC
   ```
   Use `self.backend.execute_query()` (or the driver directly if needed).

2. **Bin by time window.** Partition results into `7d`, `30d`, and `90d` buckets:
   ```python
   from datetime import datetime, timedelta
   now = datetime.now()
   scores_7d = [r["score"] for r in records if r["created_at"] >= now - timedelta(days=7)]
   scores_30d = [r["score"] for r in records if r["created_at"] >= now - timedelta(days=30)]
   ```

3. **Compute averages** and trend direction:
   ```python
   avg_7d = sum(scores_7d) / len(scores_7d) if scores_7d else None
   avg_30d = sum(scores_30d) / len(scores_30d) if scores_30d else None
   direction = "improving" if avg_7d and avg_30d and avg_7d > avg_30d * 1.05 \
               else "declining" if avg_7d and avg_30d and avg_7d < avg_30d * 0.95 \
               else "stable"
   ```

4. **Return the real dict** replacing the stub:
   ```python
   return {
       "user_uid": user_uid,
       "life_path_uid": life_path_uid,
       "7_days_ago": round(avg_7d, 2) if avg_7d else None,
       "30_days_ago": round(avg_30d, 2) if avg_30d else None,
       "direction": direction,
   }
   ```

**Note on data availability:** `SERVES_LIFE_PATH` relationships are created when entities
are linked. If a user has no linked entities yet, `scores_7d` and `scores_30d` will be
empty — the method should return `"direction": "unknown"` in that case, same as now.
The implementation is defensive by default.

---

## Item 2E — Activate `_include_predictions` in `habits_service.py`

**File:** `core/services/habits_service.py`

**Method:** `get_habit_analytics(habit_uid, _period, _include_predictions)` at line 818.

**Current state:** Both params are ignored. The method delegates entirely to
`self.intelligence.analyze_habit_performance(habit_uid)`.

**What changes when `_include_predictions=True`:**

The prediction source is `HabitsAIService`, already wired as `self.ai` (line 334).
`HabitsAIService` extends `BaseAIService` — it has LLM access.

**Implementation steps:**

1. **Drop the underscores:** `_period` → `period`, `_include_predictions` → `include_predictions`.

2. **Get the base analytics** from the existing delegation (unchanged):
   ```python
   base_result = await self.intelligence.analyze_habit_performance(habit_uid)
   if base_result.is_error or not include_predictions:
       return base_result
   ```

3. **Generate predictions via `HabitsAIService`.** This requires adding a method to
   `HabitsAIService` — something like `predict_completion_likelihood(habit, analytics)`:
   - Input: the `Habit` model + the analytics dict from step 2
   - LLM prompt: streak history, success rate, days since last check-in, user pattern
   - Output: `{"likelihood": 0.0-1.0, "risk_factors": [...], "recommendation": "..."}`
   - Use the `PROMPT_REGISTRY` (see `@prompt-templates` skill) — add a template key
     `habits.completion_prediction`.

4. **Guard on `self.ai`** (it's `None` in CORE tier):
   ```python
   if self.ai is None:
       return base_result  # Graceful — no AI in CORE tier
   prediction_result = await self.ai.predict_completion_likelihood(habit, base_result.value)
   ```

5. **Merge** predictions into the analytics dict and return.

**Note:** `period` param can be activated independently of `include_predictions` —
it feeds through to `self.intelligence.analyze_habit_performance()` once that service
supports time-windowing (Item 2C for habits covers the analytics layer; this item covers
the habit-specific analytics route at the facade level).

---

## Implementation order recommendation

```
2C (period_days filtering)      — self-contained, no dependencies, 4 services in parallel
    ↓
2D (alignment trends)           — self-contained, uses existing graph data
    ↓
2B (task stub methods)          — depends on LpBackend step queries (already exist)
    ↓
2A (cross-wire bootstrap)       — activates 2B's implementations end-to-end
    ↓
2E (include_predictions)        — requires HabitsAIService method addition (FULL tier only)
```

Items 2C and 2D have zero dependencies and can be started immediately.
Item 2E is FULL-tier only and blocked on having enough habit data to make predictions meaningful.
