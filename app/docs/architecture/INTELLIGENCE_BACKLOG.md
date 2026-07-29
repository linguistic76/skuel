# Intelligence Backlog

Deferred intelligence gaps. Each item has a clear trigger condition and implementation guide.

> **History note (2026-05-11):** This backlog was originally framed around extending an ISP-protocol adoption (the 11 "awareness slices" of UserContext). Those protocols were retired in commit `a82faaba` — `UserContext` is now the single source of truth. The remaining backlog items below are real intelligence gaps that survived the consolidation.

---

## 2A: Connect task generation to curriculum data

**Consumers:** `core/services/tasks/tasks_learning_service.py`
**Possible wiring point:** `services_bootstrap/_learning_services.py` (call site: `compose.py:709`)

**Purpose when implemented:**
- KU detail pages can surface "Tasks that apply this knowledge" — the `APPLIES_KNOWLEDGE`
  traversal for this **already exists** (see below); only hydration/presentation is missing
- `create_tasks_from_learning_path()` can turn a LearningPath into a task plan
- `get_next_learning_task()` can return tasks linked to knowledge the user is ready to learn

⚠⚠ **The dependency runs tasks → curriculum, not curriculum → tasks — and the framing of this item
is itself unresolved.** An earlier revision described injecting the activity facades into
`LpService` / `KuService`. That is backwards for both named consumers:

| Claim | Reality |
|---|---|
| `LpService` owns `create_tasks_from_learning_path()` | It does not. Both that method (138) and `get_next_learning_task()` (115) are on **`TasksLearningService`** — neither curriculum facade has either |
| It needs a `tasks_service` injected to create tasks | It already creates them, via `self.backend.create_task` (`tasks_learning_service.py:64`) |
| `LearningAlignmentBridge` can supply the path | It cannot. Its methods take an `LpPosition` handed in *by the caller*; it does not fetch the LearningPath → PathStep → Ku sequence |

What `TasksLearningService` actually lacks is a route to **read** that curriculum sequence. The
reader exists — `LpService.get_path_steps(path_uid)` (`lp_service.py:249` →
`lp_core_service.py:261`) — but reaching it needs deliberate arrangement, because activity services
are constructed **before** learning services (`compose.py:532` vs `:709`), so it cannot simply be
passed to the task service's constructor. Moving the traversal onto `TasksBackend` instead is not
the escape hatch: that crosses the domain-backend boundary (`CLAUDE.md` § 100% Dynamic Backend
Pattern).

⚠ **The three bullets are not one problem, and the wiring design is undecided.** Only
`create_tasks_from_learning_path()` needs the curriculum route above. `get_next_learning_task()`
already has its context input (121) and needs an `APPLIES_KNOWLEDGE` query on the *task* side. And
the KU-detail-page read is **already implemented — do not build a second one**: use
`PsService.find_tasks_applying_knowledge(ku_uid, user_uid, status_filter)` (`ps_service.py:505` →
`ps_application_discovery_service.py:161`, user-scoped) or the unscoped
`KuOperations.get_applying_task_uids()` (`curriculum_backends.py:289`). Both hand back bare UIDs,
so what is actually missing there is hydration and presentation, not a query.
See `docs/roadmap/intelligence-backlog-implementation.md § Item 2A` for the verified-facts table —
that file deliberately prescribes no wiring steps, because three review rounds each broke a
different prescriptive version.

⚠ **There is no partial wiring left to activate.** This item was previously anchored on four unread
placeholder params on `_create_learning_services()` — `_tasks_service`, `_habits_service`,
`_goals_service`, `_events_service` — which the composition root fed with live activity facades.
They were **deleted on 2026-07-29** as dead code: nothing read them, and they had been stranded
since Askesis creation moved out of that function in January 2026. There is no underscore prefix
left to remove.

**If the settled direction does need services threaded through the composition root**, the shape to
copy is `create_askesis_service()` (`services_bootstrap/_intelligence_hub.py:201`), which passes
`activity_services` through to `core/services/askesis_factory.py:63–66` as required,
non-underscore `AskesisDeps` fields.

**Prerequisite:** Item 2B (`create_tasks_from_learning_path`) must be implemented first.

**Trigger:** When implementing adaptive learning path features.

---

## 2B: Stub methods in `tasks_learning_service.py`

**File:** `core/services/tasks/tasks_learning_service.py` — both methods live here, not in
`tasks_scheduling_service.py` (which still exists, but no longer holds them). Fronted by
`TasksService` at `core/services/tasks_service.py:693` and `:698`.

### `create_tasks_from_learning_path(learning_path_uid, _user_context)` (line 138)

Logs a debug line and returns `Result.ok([])`; the docstring marks it "stub — pending
implementation". Real implementation needs:
- Fetch LearningPath → PathStep sequence (via LP backend)
- For each step: check user's `mastered_knowledge_uids`, prerequisite readiness
- Create a Task per unmastered step, linked via `APPLIES_KNOWLEDGE`
- Respect `user_context.available_minutes_daily` for capacity

### `get_next_learning_task(user_context)` (line 115)

Returns `Result.ok(None)` on every path. **It already calls `user_context.get_ready_to_learn()`**
(line 121) and early-returns when that comes back empty — so the remaining work starts at the
query, not the context read. Real implementation needs:
- Query Tasks that `APPLIES_KNOWLEDGE` to those ready KU UIDs, filter to incomplete/unblocked
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

