# Placeholder Parameter Index

*Technical debt register for underscore-prefixed placeholder parameters.*
*Last updated: 2026-07-21*

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

The four intelligence services accept `_period_days` but perform no date filtering.
All four should be implemented together when time-window analytics is scheduled.

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

These are not underscore parameters but are explicitly marked `# Placeholder` in comments.
They are hardcoded scalars that should eventually be computed from graph data.

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

---

## Group F — Goal Task Generation Stubs

| File | Line | Method | Parameter |
|------|------|--------|-----------|
| `core/services/goals/goal_task_generator.py` | 424 | `_generate_urgent_tasks()` | `_user_context: UserContext` |

**What full implementation requires:**
- `_generate_urgent_tasks`: Must read `user_context.at_risk_goals` and generate concrete tasks.

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

## Group I — Infrastructure / Miscellaneous

| File | Line | Method | Parameter | Notes |
|------|------|--------|-----------|-------|
| `core/models/entity.py` | 185 | `can_view()` | `_viewer_uid`, `_shared_user_uids` | Visibility check stub — always returns True |
| `core/models/entity.py` | 233 | `substance_score()` | `_force_recalculate: bool` | Force-refresh flag; recalculation not implemented |
| ~~`adapters/persistence/neo4j/user_backend.py`~~ | ~~952~~ | ~~`get_user_context()`~~ | ~~`_user_uid: str`~~ | **Removed** (March 2026) — was never a backend operation; use `UserService.get_user_context()` |
| `adapters/persistence/neo4j/_relationship_crud_mixin.py` | 744 | (inline comment) | `_props` | Property validation not yet implemented |
| `core/services/calendar_optimization_service.py` | 318 | `_get_user_energy_profile()` | `_user_uid: str` | Returns demo/static pattern; real profile query deferred |
| `core/services/schema_change_detector.py` | 537 | `_update_optimizations()` | `_report: SchemaChangeReport` | Clears optimization caches; full re-optimization from the report deferred |
| `core/services/goals/goaps_intelligence_service.py` | 1270 | `_determine_trend()` | `_lookback_days: int` | Trend direction ignores lookback window |
| `core/services/user/lp_intelligence/learning_recommendation_engine.py` | 217 | (inline comment) | `recommended_ku_uids = []` | Returns empty list; real recommendation logic deferred |

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
| High | A — Period Analytics | Four services; uniform pattern; one Cypher change per service |
| High | B — Habits Predictions | Directly affects user-facing analytics |
| High | F — LP Recommendations | Core Askesis intelligence depends on gap scoring |
| High | I — `entity.can_view()` | Visibility checking always returns True — security gap |
| Medium | C — Askesis Bootstrap | Phase 2.5 dependency; requires entity extraction logic |
| Medium | E — Hardcoded Scalars | Affects intelligence accuracy; requires graph queries |
| Medium | G — Events Intelligence | Depends on GraphContext enrichment work |
| Low | D — Neo4j Adapter Stubs | Developer tooling; not user-facing |
| Low | H — Askesis Private Methods | Internal heuristics refinement |
| Low | I — misc infrastructure | Calendar energy profile, schema optimizer, conflict detection |
| Low | J — UI Views | UX enhancement; not correctness issues |
| Low | K — Conversation System | Depends on Messaging system design |

---

## Related Documentation

- `CLAUDE.md` — "Parameter Naming" section defines the convention
- `docs/patterns/ERROR_HANDLING.md` — Result[T] pattern used in all service methods above
- `docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md` — Intelligence service architecture
- `docs/architecture/UNIFIED_USER_ARCHITECTURE.md` — UserContext and period-based analytics context
