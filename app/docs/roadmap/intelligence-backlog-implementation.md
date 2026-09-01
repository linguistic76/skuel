---
updated: 2026-08-21
---

# Intelligence Backlog: Implementation Guide

Four deferred intelligence gaps. Each item has a concrete starting point, the exact files
to touch, and the data model and query patterns already in place. (Item 2C was retired on
2026-07-29 — see its section below.)

> The framing here originally referenced a "Context Awareness Protocol adoption" effort that
> was retired in commit `a82faaba` (2026-05-11). The intelligence gaps below are real and
> survived the consolidation; only the surrounding protocol-narrowing scaffolding is gone.
> See `/docs/architecture/UNIFIED_USER_ARCHITECTURE.md` for the current contract.

**Source of truth for what to build:** `/docs/architecture/INTELLIGENCE_BACKLOG.md`
**This file:** How to start building each item.

---

## Item 2A — Connect task generation to curriculum data

**What it unlocks:** KU detail pages that surface related tasks; LP pages that can
generate a task plan for a user; `get_next_learning_task()` returning real results.

⚠⚠ **The wiring design is UNDECIDED, and this file deliberately no longer prescribes one.** Three
successive review rounds each broke a different prescriptive version of these steps — the ownership
claim, then the dependency direction, then a blanket assertion that no composition-root wiring was
needed. Prescriptive prose about unbuilt code does not converge. Everything below is only what has
been **verified against the tree**; design the wiring when the work is actually scheduled.

**Verified facts**

| Fact | Coordinate |
|---|---|
| Both consumers are on `TasksLearningService` — neither is on `LpService` or `KuService` | `tasks_learning_service.py:138` (`create_tasks_from_learning_path`), `:115` (`get_next_learning_task`) |
| It already creates tasks, so it does **not** need a `tasks_service` injected | `self.backend.create_task` — `tasks_learning_service.py:64` |
| Its constructor receives only a tasks backend, event bus and relationship service | `tasks_learning_service.py:50–58` |
| The ordered-step reader it needs lives on the curriculum side | `LpService.get_path_steps(path_uid)` — `lp_service.py:249` → `lp_core_service.py:261` |
| Activity services are built **before** learning services, so a curriculum reader cannot simply be constructor-injected into the task service | `compose.py:532` (activity) vs `:709` (learning) |
| `LearningAlignmentBridge` cannot supply the path — its methods take an `LpPosition` from the caller rather than fetching it | `core/services/infrastructure/learning_alignment_bridge.py` |
| The KU-detail-page reverse lookup **already exists — do not build a new one.** Both surfaces return bare **UIDs**, not hydrated models, so the only genuinely missing work is hydration + presentation | `PsService.find_tasks_applying_knowledge(ku_uid, user_uid, status_filter)` → `ps_service.py:505` → `ps_application_discovery_service.py:161` (**user-scoped**, `Result[list[str]]`); and `KuOperations.get_applying_task_uids(ku_uid)` → `curriculum_protocols.py:431` → `curriculum_backends.py:289` (**not** user-scoped) |
| `_create_learning_services()` takes no activity services; its four placeholder params were deleted 2026-07-29 | `_learning_services.py`, call site `compose.py:709` |

**The two methods are not one problem.** `create_tasks_from_learning_path()` needs curriculum data
it currently has no route to, and the construction order above means that route has to be arranged
deliberately rather than passed at construction. Note also that moving the LearningPath traversal
onto `TasksBackend` would cross the domain-backend boundary (`CLAUDE.md` § 100% Dynamic Backend
Pattern). `get_next_learning_task()` is different: it already has its context input via
`user_context.get_ready_to_learn()` (121), and what it still needs is an `APPLIES_KNOWLEDGE` query
on the **task** side.

Note `services_bootstrap` is a **package, not a module** — there is no `services_bootstrap.py`. If
a design does end up threading services through the composition root, the working shape to copy is
`create_askesis_service()` (`_intelligence_hub.py:201`) → `core/services/askesis_factory.py:63–66`.

**Prerequisite:** Item 2B must be implemented before any of this pays off, otherwise
`create_tasks_from_learning_path()` would have its inputs and still return `[]`.

---

## Item 2B — Implement stub methods in `tasks_learning_service.py`

**File:** `core/services/tasks/tasks_learning_service.py` — both methods live here, not in
`tasks_scheduling_service.py` (which still exists, but no longer holds them).

Two stub methods, at lines 138 (`create_tasks_from_learning_path`) and 115
(`get_next_learning_task`), separated by `suggest_learning_aligned_tasks` (130). Implement them
together — they share the same dependency pattern.

---

### `create_tasks_from_learning_path(learning_path_uid, _user_context)`

**Current body:** logs a debug message and returns `Result.ok([])`.

**What the implementation needs to do:**

1. **Fetch the LP sequence.** Use `LpService` (or `LpBackend` directly) to get the
   ordered path steps. The LP backend already has `get_paths_containing_ku()` and
   `get_ku_mastery_progress()` — use `LpBackend` to get the step sequence:
   ```cypher
   MATCH (lp:LearningPath {uid: $uid})-[r:HAS_STEP]->(ps:PathStep)
         -[:USES_KU]->(ku:Entity)
   RETURN ku.uid, ku.title, r.sequence
   ORDER BY r.sequence
   ```

2. **Filter by mastery.** Check `_user_context.mastered_knowledge_uids` (already populated
   on `UserContext`). Skip KUs the user has already mastered.

3. **Check prerequisite readiness.** Use `_user_context.prerequisites_needed` — skip KUs
   whose prerequisites are not yet in `_user_context.prerequisites_completed`.

4. **Create one Task per unmastered, ready step.** Call `self.backend.create()` with a
   `TaskCreateRequest`-style dict. Link the task to the KU via `APPLIES_KNOWLEDGE`
   (use `tasks_service.link_task_to_knowledge(task_uid, ku_uid)` — facade delegates
   to `UnifiedRelationshipService`).

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
   Add this as a named method on the domain backend (e.g., `GoalsBackend.find_task_for_knowledge()`). Domain-specific Cypher belongs on the backend, not inline in the service.

4. Deserialize the result with `self._context_to_domain_model()` and return as
   `Result.ok(task_model)`.

5. If no linked tasks exist, return `Result.ok(None)` — the caller in
   `UserContextIntelligence` handles the None case.

---

## Item 2C — Activate `_period_days` filtering — retired, see PLACEHOLDER_INDEX Group A

**Retired 2026-07-29.** This item duplicated `/docs/reference/PLACEHOLDER_INDEX.md`
§ "Group A — Period-Based Analytics Filtering", which is the live register and carries verified
coordinates for the three remaining services.

The five-step recipe that stood here is **not** carried over, because none of it survived
verification against the tree:

- **Its table was wrong in every row.** `get_decision_velocity()` and
  `get_principle_alignment_trends()` have never existed in any branch — the real method is
  `get_performance_analytics()` on both services. `goals/goaps_intelligence_service.py` is a typo
  for `goals_intelligence_service.py`. All four line numbers had drifted. Goals no longer belongs
  in the list at all: it takes a non-underscore `period_days` and already filters on it.
- **Its step-3 remedy is unproven as written.** It passed a bare `date` object to
  `find_by(updated_at__gte=...)`. So did the goals implementation it was measured against, in the
  other direction — `cutoff.isoformat()` off a timezone-aware `datetime` — and that turned out to
  be the defect, not the model (fixed; see below). It also offered
  `created_at` as the alternative key without the caveat that goes with it: PR #859 **measured**
  that `created_at` has two storage shapes — ISO string for most entities, zoned `datetime` for a
  minority — and that a naive `find_by(created_at__gte=...)` silently drops the datetime-stored
  rows. Only `find_by_date_range` coerces both before comparing. Whoever implements Group A on
  `created_at` needs that helper, not a `__gte` kwarg.
- **Its steps 4–5 prescribed metrics with no input.** The velocity figure
  (`count_completed / period_days`) and the 90-day trend baseline were specified for two methods
  that count no completion events: choices computes a `decided/total` ratio
  (`choices_intelligence_service.py:110`) and principles counts by strength and `is_active`
  (`_core_intelligence_mixin.py:54`). "Principles acted on per day" has no source in the method
  it named.

Group A's remedy is `find_by_date_range` — for **both** candidate keys, not just `created_at`.
`updated_at` is mixed-representation too: `_crud_mixin.py:437` writes an ISO string while
`BulkUpsertBackend` writes a native `datetime()` on re-ingest
(`bulk_upsert_backend.py:125`), and all four activity domains are vault-ingestible. A bare
`find_by(<field>__gte=...)` evaluates to null on the temporally-stored rows and drops them.

**The goals call now IS the model to copy** — it used exactly that bare `__gte` and has been
repointed at `find_by_date_range` (`goals_intelligence_service.py:176–182`), with a day-granular
`date` bound, an explicit `limit`, and owner scoping retained. Group A in
`docs/reference/PLACEHOLDER_INDEX.md` carries the full call shape and the three non-obvious
constraints; `tests/unit/services/goals/test_goals_analytics_window.py` fails tree-wide if any
remaining service is implemented with a bare comparison on either timestamp.

Either way, **not** a Cypher `WHERE` clause, which SKUEL021 forbids in `core/`.

---

## Item 2D — RETIRED 2026-08-21 (target method deleted)

`_calculate_alignment_trends()` was deleted from `analytics_life_path_service.py` by
`2d8c31d03` (#1034, "score Life Path alignment PER-LEARNER") — the stub this item existed
to fill no longer exists, so there is nothing to implement. The historical-trend idea
(time-windowed `SERVES_LIFE_PATH` score comparison) is preserved in git history at this
doc's pre-2026-08-21 revision if per-learner alignment ever wants a trend axis; that would
be a new design against the post-#1034 shape, not a revival of the deleted method.

---

## Item 2E — Activate `_include_predictions` in `habits_service.py`

**File:** `core/services/habits/_enrichment_mixin.py` *(moved here in the HabitsService
mixin decomposition — coordinates re-verified 2026-08-21)*

**Method:** `get_habit_analytics(habit_uid, _period, _include_predictions)` at line 39.

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
supports time-windowing (the analytics-layer window is registered in
`/docs/reference/PLACEHOLDER_INDEX.md` § Group A; this item covers the habit-specific analytics
route at the facade level).

---

## Implementation order recommendation

```
2B (task stub methods)          — depends on LpBackend step queries (already exist)
    ↓
2A (cross-wire bootstrap)       — activates 2B's implementations end-to-end
    ↓
2E (include_predictions)        — requires HabitsAIService method addition (FULL tier only)
```

(2D was retired 2026-08-21 — its target method was deleted by #1034.)
Item 2E is FULL-tier only and blocked on having enough habit data to make predictions meaningful.

The `period_days` filtering formerly sequenced here as 2C is tracked in
`/docs/reference/PLACEHOLDER_INDEX.md` § Group A — also zero-dependency, also startable
immediately, and covering three services rather than four.
