# Placeholder Parameter Index

*Technical debt register for accepted-but-unimplemented features: parameters whose bodies ignore
them (usually, but not always, underscore-prefixed) and the hardcoded values that stand in for
computation that has not been written yet.*
*Last updated: 2026-07-28*

> ⚠ **Most coordinates outside Groups E2, F, H, I2 and J are stale — a repair sweep is outstanding.**
> Rows in those five groups were re-verified against the tree on 2026-07-28. Elsewhere, expect a
> wrong line number, a wrong path, or a symbol that has moved or been deleted — and note that some
> rows' *descriptions* are wrong too, independently of their coordinates. **Treat any other row as a
> lead, not a citation: read the code before relying on it.** Some rows need repointing and some
> need deleting; that judgement is the sweep's, per row.

## Convention

Parameters prefixed with `_` in SKUEL method signatures indicate accepted-but-unimplemented features.
The method compiles and the signature is stable; the body ignores the parameter.

```python
async def analyze_habit_performance(
    self, user_uid: UserUID,
    _period_days: int = 30  # Placeholder - not yet implemented
) -> Result[dict[str, Any]]:
```

This is distinct from Python's `_` throwaway variable. The underscore prefix here communicates:
"this parameter belongs to the interface but the implementation is deferred."

---

## Group A — Period-Based Analytics Filtering

⚠ **Three, not four.** `GoalsIntelligenceService` no longer belongs here — it reads a
non-underscore `period_days` and filters on it (`core/services/goals/goals_intelligence_service.py:162`).
Its row below is stale, along with the other coordinates in this table; see the banner. The
remaining three services accept `_period_days` and perform no date filtering, and should be
implemented together when time-window analytics is scheduled.

| Service | File | Line | Parameter | Notes |
|---------|------|------|-----------|-------|
| GoalsIntelligenceService | `core/services/goals/goaps_intelligence_service.py` | 202 | `_period_days: int = 30` | `analyze_goal_performance()` |
| HabitsIntelligenceService | `core/services/habits/habits_intelligence_service.py` | 171 | `_period_days: int = 30` | `analyze_habit_performance()` |
| ChoicesIntelligenceService | `core/services/choices/choices_intelligence_service.py` | 169 | `_period_days: int = 30` | `analyze_choice_patterns()` |
| PrinciplesIntelligenceService | `core/services/principles/principles_intelligence_service.py` | 173 | `_period_days: int = 30` | `analyze_principle_alignment()` |

**What full implementation requires:** Each service's query must filter nodes to those
created/updated within the given period window. The `_period_days` parameter maps directly
to a Cypher `WHERE n.created_at >= datetime() - duration({days: $period_days})` clause.

---

## Group B — Habits Service Prediction Parameters

| Service | File | Line | Parameter | Notes |
|---------|------|------|-----------|-------|
| HabitsService | `core/services/habits_service.py` | 798 | `_period: int = 30` | `get_habit_analytics()` — period filtering |
| HabitsService | `core/services/habits_service.py` | 799 | `_include_predictions: bool = False` | `get_habit_analytics()` — AI streak/trend predictions |

**What full implementation requires:**
- `_period`: Same date-window filtering as Group A.
- `_include_predictions`: Calls an AI service to forecast habit continuity. Depends on embedding
  similarity or completion pattern analysis. Should remain `False` by default (expensive).

---

## Group C — Askesis Bootstrap Entity Services (Phase 2.5)

AskesisService is bootstrapped without domain service dependencies. When entity extraction
is implemented, these four attributes must be wired in `services_bootstrap.py`.

| Location | Lines | Placeholder | Deferred To |
|----------|-------|-------------|-------------|
| `services_bootstrap.py` | 575–579, 1316–1319 | `_tasks_service`, `_habits_service`, `_goals_service`, `_events_service` | Phase 2.5 |

**What full implementation requires:** Pass the four activity domain services into AskesisService
so it can extract entity references from conversation context (e.g., "my goal to run 5k" resolves
to a Goal UID). Requires entity extraction logic in AskesisService itself.

---

## Group D — Neo4j Adapter Stubs

These are declared on the adapter but have no body beyond a docstring.

| File | Line | Method | Parameter | Notes |
|------|------|--------|-----------|-------|
| `adapters/persistence/neo4j_adapter.py` | 186 | `bootstrap_indexes()` | `_force: bool = False` | Force-recreate indexes even if they exist |

**What full implementation requires:**
- `_force`: Index idempotency check. Currently `bootstrap_indexes()` runs unconditionally. Adding
  `_force=False` would skip creation if indexes already exist.

---

## Group E — AI Computation Placeholders (Hardcoded Values)

These are not underscore parameters but are explicitly marked in comments — `# Placeholder` in the
table below, `# FUTURE-IMPL-00N:` in the E2 subsection. They are hardcoded values that should
eventually be computed from graph data.

| File | Line | Value | Should Become |
|------|------|-------|---------------|
| `core/services/choices/choices_intelligence_service.py` | 1087 | `avg_confidence = 0.7` | Mean of `choice.confidence` across recent choices |
| `core/services/choices/choices_intelligence_service.py` | 1088 | `avg_satisfaction = 0.75` | Derived from outcome tracking |
| `core/services/choices/choices_intelligence_service.py` | 1258 | `"avg_quality_score": 0.7` | Same as above |
| `core/services/goals/goaps_intelligence_service.py` | 533 | `"learning_progress_rate": 0.5` | KU completion rate for goal-linked curriculum |
| `core/services/cross_domain_analytics_service.py` | 661–665 | `average_mood`, `mood_trend`, `most_common_themes`, `longest_streak` | Computed from Journal/Submission sentiment analysis |

**What full implementation requires:** Each value needs a dedicated graph query or NLP pipeline.
`mood_trend` and `most_common_themes` specifically require text processing on Journal content.
`longest_streak` requires date-sequence analysis on completion history.

### E2 — Goal-achievement recommendations (`FUTURE-IMPL-*`)

`GoalEventHandlerService._generate_recommendations()` (line 441) fires when a goal is achieved and
returns up to four "what next" suggestions — one per strategy. It accepts `user_uid` and never
reads it.

That unread parameter and the markers below are **co-symptoms of the same deferral, not cause and
effect** — all four markers sit inside helper methods (489–564), none of which receives `user_uid`,
so implementing them would not by itself make `_generate_recommendations()` read it.

The output is **not** user-invariant, and the deferral is narrower than it looks: `_get_goal_context`
already scopes its graph read to the owning user (`get_achievement_context(goal_uid, user_uid)`), and
three of the four strategies interpolate that user's own entity titles into `description` and emit
their uids in `related_*`. Only `_recommend_domain_progression` is genuinely table-driven. What is
deferred is the *shaping* of the advice — which strategies fire, and with what confidence — not the
data it quotes. Note the fourth strategy, `_recommend_principle_alignment()` (566), is built the same
way but carries no marker.

| Marker | File | Line | Placeholder | Should Become |
|--------|------|------|-------------|---------------|
| `FUTURE-IMPL-001` | `core/services/goals/goal_event_handler_service.py` | 491 | `domain_progressions` — a hardcoded 4×3 domain/goal-type string table (lines 492–513) with a generic fallback; `"confidence": 0.85` (523) | Progression suggested from the user's own goal graph rather than a literal table |
| `FUTURE-IMPL-002` | `core/services/goals/goal_event_handler_service.py` | 531 | Canned `title`; `"confidence": 0.80` (542). The `description` is *not* canned — it interpolates the user's real Ku titles (536→540) | Confidence derived from actual mastery signal on the referenced Kus |
| `FUTURE-IMPL-004` | `core/services/goals/goal_event_handler_service.py` | 545 | Bare marker on the last line inside the returned dict — no value attached | **Intent not recoverable.** It cited `DEFERRED_IMPLEMENTATIONS.md`, a register that never existed in this repo (no commit ever added it), so no description of the reserved field survives anywhere. The surrounding dict is otherwise complete. Delete the marker or re-specify it — do not guess. |
| `FUTURE-IMPL-006` | `core/services/goals/goal_event_handler_service.py` | 550 | Canned `title`; `"confidence": 0.75` (561). The `description` interpolates the user's real habit titles (555→559) | Confidence derived from real streak/consistency data on the linked habits |

**What full implementation requires:** the hardcoded confidences become computed scores, and
`_recommend_domain_progression`'s literal table gives way to progression drawn from the user's own
goal graph. Of the four markers, only `FUTURE-IMPL-001` plausibly needs `user_uid` threaded through
— 002 and 006 want confidence computed from Kus and habits that `goal_context` already carries with
their uids, so they can be satisfied by widening the existing query. Until one of them lands,
`user_uid` stays in the signature as the deferred hook.

---

## Group F — Goal Task Generation Stubs

| File | Line | Method | Parameter |
|------|------|--------|-----------|
| `core/services/goal_task_generator.py` | 439 | `_generate_urgent_tasks()` | `_user_context: UserContext` |

**What full implementation requires:** `_generate_urgent_tasks()` is **not** a stub — it is live
(called at line 245) and emits a task for the goal's first incomplete milestone. But `_user_context`
is not the only thing deferred in it:

- **Urgency is not computed at all.** `priority=Priority.CRITICAL` (450) and
  `due_date=today + 3 days` (451) are hardcoded literals that ignore even `Milestone.target_date`,
  and they bypass the class's own `_calculate_priority()` (464, used at 279). The at-risk *gate*
  lives in the caller (243, `goal.days_remaining() < 30`), not here.
- **One task only** — the `break` at 460 defers multi-milestone generation.
- `_user_context` is unread, so no cross-goal signal (competing deadlines, capacity) reaches the
  decision.

Implementing `_user_context` alone would still leave every urgent task at a constant CRITICAL
priority and a constant today+3 due date.

(The two `adaptive_lp_recommendations_service.py` stubs formerly listed here were deleted with
the unwired adaptive_lp shell in the 2026-06 curriculum dead-code campaign.)

---

## Group G — Events Intelligence Private Methods

| File | Lines | Method | Parameter |
|------|-------|--------|-----------|
| `core/services/events/events_intelligence_service.py` | 507 | `_analyze_goal_support()` | `_context: GraphContext` |
| `core/services/events/events_intelligence_service.py` | 540 | `_analyze_habit_impact()` | `_context: GraphContext` |

**What full implementation requires:** Both methods receive a `GraphContext` that contains the
surrounding graph neighborhood. Once the graph context query is enriched to include goal and
habit nodes, these private methods can traverse the context rather than issuing new queries.

---

## Group H — Askesis Private Methods

Four Askesis private methods accept an underscore-prefixed parameter their bodies never read.

| File | Line | Method | Parameter | Called at |
|------|------|--------|-----------|-----------|
| `core/services/askesis/action_recommendation_engine.py` | 451 | `_recommend_foundation_building()` | `_user_context: UserContext` | 167, in `get_next_best_action()` |
| `core/services/askesis/action_recommendation_engine.py` | 472 | `_calculate_habit_risk_days()` | `_user_context: UserContext` | 361, in `predict_future_state()` |
| `core/services/askesis/user_state_analyzer.py` | 343 | `_generate_insights()` | `_focus_areas: list[str] \| None` | 116, in `analyze_user_state()` |
| `core/services/askesis/context_retriever.py` | 966 | `_analyze_blocked_knowledge_prerequisites()` | `_knowledge_units: list[Any]` | 424 |

Three of the four carry the identical `(unused - for future use)` docstring marker (lines 480, 353
and 980); `_recommend_foundation_building` has no Args block to hold one.

⚠ Before implementing any of these, establish whether the enclosing method can actually **run**.
Each chain terminates at an `AskesisService` facade method, and whether a route reaches those was
not established here — "it has a caller" is the weak question.

---

## Group I — Infrastructure / Miscellaneous

| File | Line | Method | Parameter | Notes |
|------|------|--------|-----------|-------|
| `core/models/entity.py` | 176 | `can_view()` | `_viewer_uid`, `_shared_user_uids` | Returns `visibility == PUBLIC`; both args unread because owner/sharing logic lives in the `UserOwnedEntity` override. **Not** an always-True stub |
| `core/models/entity.py` | 233 | `substance_score()` | `_force_recalculate: bool` | Force-refresh flag; recalculation not implemented |
| ~~`adapters/persistence/neo4j/user_backend.py`~~ | ~~952~~ | ~~`get_user_context()`~~ | ~~`_user_uid: str`~~ | **Removed** (March 2026) — was never a backend operation; use `UserService.get_user_context()` |
| `adapters/persistence/neo4j/_relationship_crud_mixin.py` | 744 | (inline comment) | `_props` | Property validation not yet implemented |
| `core/services/calendar_optimization_service.py` | 318 | `_get_user_energy_profile()` | `_user_uid: str` | Returns demo/static pattern; real profile query deferred |
| `core/services/schema_change_detector.py` | 537 | `_update_optimizations()` | `_report: SchemaChangeReport` | Clears optimization caches; full re-optimization from the report deferred |
| `core/services/goals/goaps_intelligence_service.py` | 1270 | `_determine_trend()` | `_lookback_days: int` | Trend direction ignores lookback window |
| `core/services/user/lp_intelligence/learning_recommendation_engine.py` | 217 | (inline comment) | `recommended_ku_uids = []` | Returns empty list; real recommendation logic deferred |

### I2 — Progress event handlers (`FUTURE-IMPL-*`)

| Marker | File | Line | Placeholder | Notes |
|--------|------|------|-------------|-------|
| `FUTURE-IMPL-008` | `core/services/goals/goals_progress_service.py` | 1129 | `current_streak: int` (1131) on `_update_goal_from_habit_completion()` (1130) | ⚠ **One of the two deferred *parameters* in this register that are NOT underscore-prefixed** (the other is `user_uid` on `_generate_recommendations()`, Group E2). The handler recomputes progress from `avg_streak` across *all* habits linked to the goal, so the completing habit's own streak is discarded. Deferred: per-habit weighting. |
| `FUTURE-IMPL-009` | `core/services/lp/lp_progress_service.py` | 171 | `old_progress_percentage` synthesised as `((mastered_kus - 1) / total_kus) * 100` (205); `average_mastery_score=1.0` (239) | No `UserLpProgress` entity exists, so prior progress is inferred by assuming exactly one KU was just mastered, and `LearningPathCompleted` reports perfect mastery unconditionally. |

**What full implementation requires:**
- `FUTURE-IMPL-008`: weight the completing habit's `current_streak` against the goal's other
  linked habits instead of collapsing to a flat average.
- `FUTURE-IMPL-009`: a persisted `UserLpProgress` entity holding prior progress and `start_date`.
  Two further placeholders resolve with it — the inferred `old_progress_percentage`, and the
  hardcoded `average_mastery_score` (which should average real per-KU mastery scores).

> **Why `FUTURE-IMPL-008` has a named ruff entry — and why that entry is documentation, not
> mechanism.** SKUEL defers a parameter by underscore-prefixing it, and ruff's `ARG` rules already
> skip underscore-prefixed arguments, so a placeholder recorded here normally needs no suppression
> at all. `current_streak` is not underscore-prefixed, so it *is* a genuine ARG002 violation — which
> is why `"core/services/goals/goals_progress_service.py" = ["ARG002"]` survived the #855
> per-file-ignores sweep. But that key is not what silences it: broader keys already cover the file
> (`"core/services/*_service.py"` and `"core/services/*/[!_]*.py"` both match, because ruff's `*`
> crosses `/`). The named entry is documentation of the one live violation, not the mechanism.
> Prefer underscore-prefixing over adding a suppression, and never read a named per-file entry as
> proof that it is load-bearing — measure with the table cleared.

---

## Group J — UI Placeholder Views

These are FastHTML component functions that accept parameters that are not yet rendered.

| File | Line | Function | Parameter | Notes |
|------|------|----------|-----------|-------|
| `ui/profile/curriculum_views.py` | 18 | `PathStepsDomainView()` | `_focus_uid` | Focus-on-UID not yet implemented |
| `ui/admin/views.py` | 526 | `render_user_reports_list()` | `_user_uid` | UID passed but not used in query |

---

## Implementation Priority

| Priority | Group | Reason |
|----------|-------|--------|
| High | A — Period Analytics | Three services remain (choices, habits, principles); goals already filters — see `goals_intelligence_service.py:162`. Uniform pattern; one date-window filter per service |
| High | B — Habits Predictions | Directly affects user-facing analytics |
| Low | I — `entity.can_view()` | Base check is correct (`visibility == PUBLIC`); ownership/sharing handled by the `UserOwnedEntity` override. Previously ranked High on a "always returns True" reading that the code does not support |
| Medium | C — Askesis Bootstrap | Phase 2.5 dependency; requires entity extraction logic |
| Medium | E — Hardcoded Scalars | Affects intelligence accuracy; requires graph queries |
| Medium | E2 — Goal-achievement recommendations | Confidences hardcoded and one strategy table-driven; `user_uid` accepted but unread |
| Medium | G — Events Intelligence | Depends on GraphContext enrichment work |
| Medium | I2 — Progress event handlers | `FUTURE-IMPL-009` blocks on a `UserLpProgress` entity that does not exist |
| Low | D — Neo4j Adapter Stubs | Developer tooling; not user-facing |
| Low | F — Goal Task Generation | Tasks are already generated; priority/due-date hardcoded and cross-goal context unread |
| Low | H — Askesis Private Methods | Internal heuristics refinement |
| Low | I — misc infrastructure | Calendar energy profile, schema optimizer, trend lookback |
| Low | J — UI Views | UX enhancement; not correctness issues |

Every row above resolves to a heading in this document (`## Group X`, or `### X2` for the
`FUTURE-IMPL` subsections) — keep it that way when editing. A row with no section is how this
table rotted last time.

A former "K — Conversation System" row was dropped on 2026-07-28. Its section
(`## Group K — Messaging / Conversation System Groundwork`, added 2026-02-25 in `5ce618ee1`) was
deleted on 2026-06-19 by `69be520ca` (#338), which wired Neo4j conversation persistence and removed
the `InMemoryConversationRepo` the section documented — but left the priority-table row behind. The
groundwork it tracked was **built, not deferred**, so there is nothing left to record here.

---

## Related Documentation

- `CLAUDE.md` — "Parameter Naming" section defines the convention
- `docs/patterns/ERROR_HANDLING.md` — Result[T] pattern used in all service methods above
- `docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md` — Intelligence service architecture
- `docs/architecture/UNIFIED_USER_ARCHITECTURE.md` — UserContext and period-based analytics context
