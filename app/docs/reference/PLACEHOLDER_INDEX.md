# Placeholder Parameter Index

*Technical debt register for accepted-but-unimplemented features: parameters whose bodies ignore
them (usually, but not always, underscore-prefixed) and the hardcoded values that stand in for
computation that has not been written yet.*
*Last updated: 2026-07-29*

Every coordinate below was re-verified against the tree on 2026-07-28 (`77c4d959b`). Each row names
a file, a line, and a symbol that should be on it, so the set is re-checkable mechanically.

⚠ **That verification does not survive later PRs, and nothing re-runs it.** Group E's four choices
rows were six lines stale by the time anyone read them again — #859 inserted a helper above them and
shifted the block — so treat the stamp above as "verified once", not "currently true". Group E's
choices rows were re-derived in #862, and **Group A's were re-derived against `1f0d396ce` on
2026-07-29** — #862 shifted the choices method down 7 lines, staling that row the same way. Every
other group still carries the `77c4d959b` stamp.

**When a coordinate misses, grep the symbol, not the path.** Whether the file exists is the wrong
staleness test: the previous revision's rows failed three different ways, and only one of them was
a simple line drift.

- A path that never existed in any branch — `goaps_intelligence_service.py`, a typo for
  `goals_intelligence_service.py`, on three rows.
- Files that still existed with the symbol moved out of them — `habits_service.py` and
  `principles_intelligence_service.py`, whose methods went to `_enrichment_mixin.py` and
  `_core_intelligence_mixin.py`.
- Files whose cited code had been deleted outright — `cross_domain_analytics_service.py`,
  `events_intelligence_service.py`.

## Convention

Parameters prefixed with `_` in SKUEL method signatures indicate accepted-but-unimplemented features.
The method compiles and the signature is stable; the body ignores the parameter.

```python
async def get_performance_analytics(
    self, user_uid: UserUID,
    _period_days: int = 30  # Placeholder - not yet implemented
) -> Result[dict[str, Any]]:
```

This is distinct from Python's `_` throwaway variable. The underscore prefix here communicates:
"this parameter belongs to the interface but the implementation is deferred."

---

## Group A — Period-Based Analytics Filtering

| Service | File | Line | Parameter | Method |
|---------|------|------|-----------|--------|
| HabitsIntelligenceService | `core/services/habits/habits_intelligence_service.py` | 112 | `_period_days: int = 30` | `get_performance_analytics()` (111) |
| ChoicesIntelligenceService | `core/services/choices/choices_intelligence_service.py` | 111 | `_period_days: int = 30` | `get_performance_analytics()` (110) |
| PrinciplesIntelligenceService | `core/services/principles/_core_intelligence_mixin.py` | 55 | `_period_days: int = 30` | `get_performance_analytics()` (54), mixed into `principles_intelligence_service.py:44` |

⚠ **These three are live, and the placeholder is user-visible.** All six Activity Domains register
`GET /api/{domain}/analytics` (`create_activity_domain_route_config` sets
`intelligence=IntelligenceRouteConfig()`, `domain_route_factory.py:340`). The handler reads
`period_days` off the query string and passes it through
(`intelligence_route_factory.py:286`, `290`). Each of the three services then echoes it back as
`"period_days"` in the response body (habits 173, choices 149, principles 99) while computing over
everything `find_by(user_uid=...)` returns. The response therefore *claims* a window it did not
apply — this is a wrong answer, not just a missing feature.

**Goals is already implemented and is not listed here:** `GoalsIntelligenceService` takes a
non-underscore `period_days` and filters on it at `goals_intelligence_service.py:176–182`.

✅ **Goals is now the worked reference for this group.** It previously used
`find_by(updated_at__gte=cutoff.isoformat())` — a bare `>=` against a string bound, which
silently dropped every re-ingested goal — and was fixed to route through `find_by_date_range`.
Copy that call shape. Three things it had to get right beyond naming the helper:

- **Pass a `date`, not a `datetime`.** The helper's coercion is day-granular
  (`date(left(toString(n.field), 10))`), so a `datetime` bound is the wrong shape for it.
- **Set `limit` explicitly.** `find_by_date_range` defaults to `limit=100`, and every metric in
  these responses is a count or a mean over the returned set — the default page size is the
  same silent-under-return class as the bug being fixed.
- **Keep `user_uid` in `additional_filters`.** The helper matches on the label first, so
  dropping the owner filter leaks other users' rows into one user's analytics.

⚠ **A field-name guard cannot catch this defect.** The generic check #859 relied on for Choices —
"every filtered key must be a real model field" — passes against the bad goals call, because
`updated_at` *is* a real `Goal` field. A dropped predicate over-returns and is caught by field-name
membership; an emitted predicate that evaluates to null under-returns and is not. The tree-wide
guard for the whole family is `tests/unit/services/goals/test_goals_analytics_window.py`
(`TestNoBareComparisonOnMixedTimestamps`), which fails if any of the three services below is
implemented with a bare comparison on either timestamp.

**What full implementation requires:** each service must bound its fetch to the period window.

⚠ **Not by writing Cypher.** The previous revision of this row prescribed a
`WHERE n.created_at >= datetime() - duration({days: $period_days})` clause. All three sites are in
`core/`, where **SKUEL021 forbids raw Cypher** (`lint_skuel.py:17`, ADR-044) — and all three
currently author none. That remedy would not lint.

The in-architecture move is `find_by_date_range`, which coerces the stored value
(`date(left(toString(n.field), 10))`) before comparing — declared on `EntitySearchOperations`
(`base_protocols.py:583`).

```python
cutoff = date.today() - timedelta(days=period_days)   # a date: the coercion is day-granular
result = await self.backend.find_by_date_range(
    start_date=cutoff, end_date=None,                 # "last N days" has a lower bound only
    date_field="updated_at",                          # or "created_at"
    additional_filters={"user_uid": user_uid},        # owner scoping is not optional
    limit=QueryLimit.MAXIMUM,                         # the default 100 truncates silently
)
```

Live as written in `goals_intelligence_service.py:176–182`.

⚠ **Not `find_by(<field>__gte=...)`, for either key.** Both timestamp fields are
**mixed-representation**, so a bare `>=` against a string bound evaluates to null on the
temporally-stored rows and silently drops them — the protocol docstring says so explicitly
(`base_protocols.py:591–596`):

| Field | ISO string written by | Native `datetime()` written by |
|---|---|---|
| `created_at` | `_crud_mixin` create path | `BulkUpsertBackend` `ON CREATE` (`bulk_upsert_backend.py:122`) |
| `updated_at` | `_crud_mixin.py:437` | `BulkUpsertBackend` `ON MATCH` (`bulk_upsert_backend.py:125`) |

Habit, Choice, Principle **and** Goal all carry an `EntityIngestionConfig`
(`core/services/ingestion/config.py:269–309`), so every one of them can be re-ingested from the
vault and pick up the native-datetime shape. This is not a rare edge: it is the shape of any
entity whose last write came from a vault sync.

Whether the window keys off `created_at` or `updated_at` remains a semantic decision — but it no
longer changes which helper to use.

**This group is the register for the `_period_days` deferral; add coordinates here, not elsewhere.**
Three other copies existed as of 2026-07-29 and are now redirect stubs or links:
`docs/architecture/INTELLIGENCE_BACKLOG.md` § 2C, `docs/roadmap/intelligence-backlog-implementation.md`
§ Item 2C, and `docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md` § "Placeholder Convention".

Two of them survived repeated doc sweeps for the same structural reason: **a claim that resolves to
nothing never looks stale.** § 2C named four methods that had never existed in any branch;
INTELLIGENCE_SERVICES_INDEX said "4 services" and counted Goals, which has been implemented
throughout. Neither error is visible to a link checker, and neither reads as obviously wrong.

---

## Group B — Habits Service Prediction Parameters

| Service | File | Line | Parameter | Method |
|---------|------|------|-----------|--------|
| HabitsService | `core/services/habits/_enrichment_mixin.py` | 42 | `_period: str = "month"` | `get_habit_analytics()` (39) |
| HabitsService | `core/services/habits/_enrichment_mixin.py` | 43 | `_include_predictions: bool = False` | `get_habit_analytics()` (39) |

⚠ **Unlike Group A, nothing calls this.** `get_habit_analytics()` has no call site anywhere in the
tree — the one lexical near-match, `cross_domain_analytics_service.py:504`, calls the *backend*
method of the same name (`cross_domain_backend.py:435`), which takes `user_uid` and neither of these
parameters. Five of its `_EnrichmentMixin` siblings are registered in the bloat detector's PLANNED
tier (`scripts/detect_bloat.py:512–520`); `get_habit_analytics` itself is not registered anywhere.

**What full implementation requires:**
- `_period`: **not** Group A's filter. It is a period *name* (`"month"`), not a day count, so the
  `_period_days` day-window clause is not a drop-in — either convert at the boundary or retype.
- `_include_predictions`: Calls an AI service to forecast habit continuity. Depends on embedding
  similarity or completion pattern analysis. Should remain `False` by default (expensive).
- Before either: establish a consumer, or delete the method. It is unreached surface today.

---

## Group D — Neo4j Adapter Stubs

These are declared on the adapter but have no body beyond a docstring.

| File | Line | Method | Parameter | Notes |
|------|------|--------|-----------|-------|
| `adapters/persistence/neo4j_adapter.py` | 209 | `bootstrap_indexes()` | `_force: bool = False` | Docstring (217): "Reserved for future use" |

**Intent not recoverable.** The obvious reading — "skip creation when the indexes already exist" —
is already the behaviour: every constraint and index statement in the method body carries
`IF NOT EXISTS` (verified across 209–345; no bare `CREATE`), so the server no-ops on a second run.
Nothing in the tree states what `_force` was reserved to switch. Delete the parameter or
re-specify it — do not guess, and do not implement the docstring's literal reading, which the DDL
already provides.

---

## Group E — AI Computation Placeholders (Hardcoded Values)

These are not underscore parameters but are explicitly marked in comments — `# Placeholder` in the
table below, `# FUTURE-IMPL-00N:` in the E2 subsection.

The blocking prerequisite recorded here in #857 — that the three choices rows were *unreachable* —
was **wrong on its mechanism, and the rows were never unreachable**. Corrected and fixed in #859;
kept below because the correction is the reusable part.

| Claim made in #857 | What the code actually did |
|---|---|
| `find_by(date__gte=…, date__lte=…)` emits a predicate on `n.date` | It does not. `build_search_query` checks the key against the model's dataclass fields first (`crud_queries.py:107–109`) and **skips** any it does not recognise, with a warning |
| Neo4j returns nothing, so the methods exit through `if not choices:` | The opposite. Both predicates were dropped and the query degraded to `WHERE n.user_uid = $user_uid` — **every choice the user ever made**, unbounded by time and silently capped at `find_by`'s default `limit=100` |
| The placeholders never execute | They executed for any user with ≥1 choice. `days` was the inert part: `days=7` and `days=365` returned the same set, while `choices_per_week` kept dividing by the *requested* window |

The general lesson is the one worth keeping: **`validate_field_name` is not the only gate on a filter
key.** It is a regex + length cap (`validation_helpers.py:59–61`) and it does pass `date__gte`, but a
second, model-aware gate downstream is what actually decided the behaviour. Tracing to the first gate
and stopping produced a confident, backwards diagnosis — a dropped predicate over-returns, it does
not silent-zero.

The fix (#859) routes all three period methods through
`_AnalyticsMixin._find_choices_in_window` (`_analytics_mixin.py:194`), which windows on `created_at`
via `find_by_date_range`. Two constraints are recorded in that helper's docstring and pinned by
tests: `decided_at` would have silent-zeroed (its only writer, `ChoicesCoreService.make_decision`,
has no route), and `created_at` has two storage shapes, so only the coercing
`find_by_date_range` path matches both.

⚠ **The four rows do not share a remedy — check where the data lives before writing a query.** Two
need no query at all, one cannot be recovered by any query until persistence is defined, and only
the fourth is a genuine graph read.

| File | Line | Value | Should Become |
|------|------|-------|---------------|
| `core/services/choices/_analytics_mixin.py` | 430 | `avg_confidence = 0.7` | **Blocked — nothing to average.** `Choice` has no `confidence` field, and neither do `ChoiceDTO` nor the `Entity` base. Decision confidence is carried at the boundary only: `ChoiceDecisionRequest.confidence` (`core/models/choice/choice_request.py:149`) and the decision event (`core/events/choice_events.py:103`). Persisting it is the prerequisite, not a query. Note the boundary model itself is unreachable — no route constructs a `ChoiceDecisionRequest` |
| `core/services/choices/_analytics_mixin.py` | 431 | `avg_satisfaction = 0.75` | **No query needed.** `get_decision_patterns()` already holds the `Choice` objects — it iterates them at 421–422. Mean of the non-null `Choice.satisfaction_score` (`choice.py:81`, 1–5 scale, nullable), rescaled |
| `core/services/choices/_analytics_mixin.py` | 604 | `"avg_quality_score": 0.7` | **No query needed.** `get_domain_decision_patterns()` holds `domain_choice_list` in the loop that emits this. Mean of `Choice.get_decision_quality_score()` (`choice.py:129`) |
| `core/services/goals/_analytics_mixin.py` | 211 | `"learning_progress_rate": 0.5` | KU completion rate for goal-linked curriculum — **this one is a real graph read** |

Rows 430/431 sit in `get_decision_patterns()` beside a computed ratio
(`principle_alignment_score`, 432); row 604 sits in `get_domain_decision_patterns()` beside a real
`percentage`. In both cases a caller cannot tell which fields of the returned dict were computed and
which are constants — and since #859 both dicts are actually built and returned, so the constants
now reach callers.

⚠ **`principle_alignment_score` was described here as "a genuinely computed ratio" while it was
computing 0.0 for every input** — a reminder that "there is arithmetic on this line" is not evidence
that the arithmetic has an input. `principle_aligned_count` and `goal_oriented_count` read
`aligned_principles` / `related_goals` off each `Choice` via `getattr(..., None)`; **neither has ever
been a `Choice` or `ChoiceDTO` field** — both live as graph edges — so the `None` default pinned both
sums, both percentages, the alignment score and the `strategic_vs_tactical` band at 0 / "tactical".
Same family as the filter bug this section used to describe: a name that does not exist on the model,
degrading silently instead of erroring.

**Fixed (#862).** Both counts now come from a batched relationship read
(`_AnalyticsMixin._fetch_alignment_links`, 258): one `UNWIND` query per edge type over the whole
window, `principles` (`INFORMED_BY_PRINCIPLE`) and `goals` (`AFFECTS_GOAL`). The same read also
retired the hardcoded `most_common_principle` (`None  # Would need aggregation`) — it is now a
`Counter` over the principle UIDs already fetched, so it costs no extra query, and it returns a
**UID, not a title**. Pinned by `tests/integration/test_choices_alignment_metrics.py`, where six of
seven assertions are RED against the old code.

Alignment is the **union of both principle directions** — `INFORMED_BY_PRINCIPLE` outgoing and
`GUIDES_CHOICE` incoming — matching what `CHOICES_INTELLIGENCE.md` and `path_aware_types` already
mean by a choice's principles. ⚠ **I first shipped the outgoing direction alone, on a published
claim that `GUIDES_CHOICE` "has no writer anywhere in the tree".** That claim was false, and the way
it was reached is the reusable part: I grepped for the *edge name* and for its Choice-side method key.
The writer names neither. `PrinciplesService.create_principle_link` takes a user-supplied
`link_type` and resolves the edge through `_GravityMixin._LINK_TYPE_MAP` (`"choice"` →
`guided_choices`), reachable at `POST /api/principles/links`. **A generic, registry-driven writer is
invisible to a name grep** — to rule out a writer, search the *dispatch table*, not the identifier.

A failed relationship read propagates as an error `Result` rather than degrading to 0.0, and
`ChoicesIntelligenceService` now declares `_require_relationships = True` (as habits and goals
intelligence already did), so the service cannot be constructed without the sub-service that reads
these edges. A 0% alignment that is really a missing dependency is the defect this row describes.

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

`GoalTaskGenerator` has three private generators that accept the caller's real `UserContext` and
read none of it — `_user_context` occurs exactly three times in the file, once per signature.

| File | Line | Method | Parameter | Called at |
|------|------|--------|-----------|-----------|
| `core/services/goal_task_generator.py` | 258 | `_generate_milestone_tasks()` | `_user_context: UserContext` | 131, in `generate_tasks_for_goal()` (96) |
| `core/services/goal_task_generator.py` | 411 | `_generate_checkin_tasks()` | `_user_context: UserContext` | 143, in `generate_tasks_for_goal()` (96) |
| `core/services/goal_task_generator.py` | 439 | `_generate_urgent_tasks()` | `_user_context: UserContext` | 245, in `generate_next_critical_tasks()` (223) |

**What full implementation requires:** `_generate_urgent_tasks()` is **not** a stub — it is live
and emits a task for the goal's first incomplete milestone. But `_user_context`
is not the only thing deferred in it:

- **Urgency is not computed at all.** `priority=Priority.CRITICAL` (450) and
  `due_date=today + 3 days` (451) are hardcoded literals that ignore even `Milestone.target_date`,
  and they bypass the class's own `_calculate_priority()` (464, used at 279). The at-risk *gate*
  lives in the caller (243, `goal.days_remaining() < 30`), not here.
- `_user_context` is unread, so no cross-goal signal (competing deadlines, capacity) reaches the
  decision.

The `break` at 460 (`# Only one urgent task`) is **not** deferred work — it is the selection
contract. `generate_next_critical_tasks()` (223) pools tasks across every at-risk goal and then
applies a global `critical_tasks[:limit]` (250), so emitting every milestone would let one goal
crowd the others out. Leave it alone unless that contract is being changed deliberately.

Implementing `_user_context` alone would still leave every urgent task at a constant CRITICAL
priority and a constant today+3 due date.

(The two `adaptive_lp_recommendations_service.py` stubs formerly listed here were deleted with
the unwired adaptive_lp shell in the 2026-06 curriculum dead-code campaign.)

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
| `adapters/persistence/neo4j/_relationship_crud_mixin.py` | 910 | (inline comment) | `_props` | Property validation not yet implemented |
| `core/services/calendar_optimization_service.py` | 143 | `_get_user_energy_profile()` | `_user_uid: UserUID` | Returns a static demo profile — the docstring says "for demo"; real profile query deferred |
| `core/services/schema_change_detector.py` | 537 | `_update_optimizations()` | `_report: SchemaChangeReport` | Clears two optimization caches unconditionally; full re-optimization *from the report* deferred |
| `core/services/goals/_predictive_mixin.py` | 401 | `_calculate_consistency_factor()` | `_lookback_days: int` | Caller passes a real window (135) |
| `core/services/goals/_predictive_mixin.py` | 449 | `_calculate_momentum_factor()` | `_lookback_days: int` | Caller passes a real window (137) |
| `core/services/goals/_predictive_mixin.py` | 676 | `_determine_trend()` | `_lookback_days: int` | Caller passes a real window (167) |
| `core/services/lp_intelligence/learning_recommendation_engine.py` | 216 | (inline comment) | `recommended_ku_uids = []` | Returns empty list; real recommendation logic deferred |

The three `_predictive_mixin` rows are one deferral, not three: `predict_goal_success()` (97) accepts
`lookback_days: int = 30` (100) and threads it into all three helpers, every one of which discards
it — so no consistency, momentum or trend output responds to the window the caller asked for. The
parameter is not wholly dead: its one live consumer is `_determine_confidence_level()` (536), called
at 149, which receives it positionally as `data_points` (537) and buckets it at 543–548.

### I2 — Progress event handlers (`FUTURE-IMPL-*`)

| Marker | File | Line | Placeholder | Notes |
|--------|------|------|-------------|-------|
| `FUTURE-IMPL-008` | `core/services/goals/goals_progress_service.py` | 1129 | `current_streak: int` (1131) on `_update_goal_from_habit_completion()` (1130) | ⚠ **One of the two deferred *parameters* in this register that are NOT underscore-prefixed** (the other is `user_uid` on `_generate_recommendations()`, Group E2). ⚠ **Intent unknown — do not assume a remedy.** The value is not lost: the completing habit's streak is persisted (`habits_progress_service.py:242`) *before* the event is published, and `count_linked_habits_avg_streak` averages the persisted `current_streak` of every linked habit, so it is already counted. The parameter is redundant as it stands, and the handler receives no `habit_uid` with which to single that habit out. |
| `FUTURE-IMPL-009` | `core/services/lp/lp_progress_service.py` | 171 | `old_progress_percentage` synthesised as `((mastered_kus - 1) / total_kus) * 100` (205); `average_mastery_score=1.0` (239) | Nothing reads persisted LP progress, so prior progress is inferred by assuming exactly one KU was just mastered; and whenever the completion branch fires, `LearningPathCompleted` reports mastery of exactly 1.0. |

**What full implementation requires:**
- `FUTURE-IMPL-008`: **decide, don't implement.** The averaged progress already includes the
  completing habit, so there is no missing input to restore — establish whether a per-habit
  emphasis was ever intended (which would need a `habit_uid` this handler is not given), and if
  not, delete the parameter rather than invent a use for it.
- `FUTURE-IMPL-009`: a persisted record of prior LP progress and its start date. **Read the live
  relationship state** — enrollment lifecycle is on `ENROLLED_IN` (`r.status`, written by
  `UserBackend.enroll_in_learning_path` / `complete_learning_path`), and per-KU progression is the
  `VIEWED → IN_PROGRESS → MASTERED` edge chain, where mastery is the **edge's existence**, not a
  score. Two placeholders resolve from it: the inferred `old_progress_percentage`, and the
  hardcoded `average_mastery_score`.

  ⚠ **Two dead ends to avoid here.** Do not add the `UserLpProgress` entity that
  `lp_progress_service.py:204` names in passing. And do not reach for `UserProgress`
  (`core/models/progress/user_progress.py`) either, despite it being a generic dataclass with a
  wired `UniversalNeo4jBackend[UserProgress]`: **no code writes a `:UserProgress` node**, and
  ADR-002 records that this vocabulary "was never built" — a reader against it silently returned
  zero from the day it shipped. Being instantiated is not the same as being written; check for a
  writer that can actually run before building on a model.

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
| `ui/profile/curriculum_views.py` | 18 | `PathStepsDomainView()` | `_context`, `_focus_uid` | Renders a fixed empty state; **neither** parameter is read |
| `ui/admin/views.py` | 526 | `render_user_reports_list()` | `_user_uid` | `@staticmethod` on `AdminUIComponents` (38); UID passed but not used in query |

⚠ **Like Group B, neither function has a caller** — the only occurrence of each name in the Python
tree is its own definition. `curriculum_views.py` goes further: **nothing imports the module**, its
three other functions (`LearningPathsDomainView` 43, `_learning_paths_list` 84,
`_ready_to_learn_list` 144) are unreached too, and `ui/profile/__init__.py` does not export it.

**But the docs still register it as live**, which cuts the other way and must be weighed:
`ui/profile/README.md:29` lists it in the package's module table as "KU, LS, LP profile views", and
the `skuel-ui` skill repeats the entry (`.claude/skills/skuel-ui/SKILL.md:494`, as "KU, PS, LP").
`ui/profile/_shared.py:3` also describes itself as "consumed by curriculum_views.py". None of that
makes the module runtime-reachable, but it is evidence of intent, and whichever way the question is
settled those three references have to move with it. Note the README entry still says **LS**,
predating the LearningStep→PathStep rename — the register it belongs to is itself stale.

Settle whether that module is abandoned or staged before implementing either parameter — `CLAUDE.md`
§ One Path Forward deletes the first and registers the second. Do not read `./dev bloat` as having
settled it: `ui` is in its `FIRST_PARTY_ROOTS` (`scripts/detect_bloat.py:65`), yet it reports none of
these functions, so their absence from its PLANNED tables is not evidence either way.

---

## Implementation Priority

| Priority | Group | Reason |
|----------|-------|--------|
| High | A — Period Analytics | Live on `GET /api/{choices,habits,principles}/analytics`; the response echoes a `period_days` it did not apply. Uniform pattern; one date-window filter per service, via `find_by_date_range` — **not** the bare `find_by(<field>__gte=...)` goals uses, which drops re-ingested rows (see the group) |
| High | E — Hardcoded Scalars | The three choices rows are **unreachable** — both enclosing methods filter on a `Choice.date` property that does not exist, so they return empty. Repointing that filter comes before any of the aggregations; `learning_progress_rate` is independent and needs a graph query |
| Medium | E2 — Goal-achievement recommendations | Confidences hardcoded and one strategy table-driven; `user_uid` accepted but unread |
| Medium | I2 — Progress event handlers | `FUTURE-IMPL-009` needs persisted LP state — read the live `ENROLLED_IN` / `MASTERED` edges; `UserProgress` and `UserLpProgress` are both dead ends |
| Low | B — Habits Predictions | No caller in the tree — `get_habit_analytics()` is unreached facade surface. Establish a consumer or delete it before implementing either parameter |
| Low | D — Neo4j Adapter Stubs | Developer tooling; not user-facing, and `_force`'s intent is not recoverable |
| Low | F — Goal Task Generation | Tasks are already generated; priority/due-date hardcoded and cross-goal context unread in all three generators |
| Low | H — Askesis Private Methods | Internal heuristics refinement |
| Low | I — misc infrastructure | Calendar energy profile, schema optimizer, predictive lookback window (3 sites), `_props` validation, LP recommendation stub |
| Low | J — UI Views | UX enhancement; not correctness issues |

Every row above resolves to a heading in this document (`## Group X`, or `### X2` for the
`FUTURE-IMPL` subsections) — keep it that way when editing. A row with no section is how this
table rotted last time.

---

## Removed rows

Deletions are recorded here so they are not re-added from memory. **Group letters are identifiers,
not a sequence** — the gaps at C and G are deliberate; do not re-letter, because `§ E2` and `§ I2`
are cited by name from six `FUTURE-IMPL-*` comments in the code.

| Removed | When | Why |
|---------|------|-----|
| **Group G — Events Intelligence Private Methods** (2 rows + its priority row) | 2026-07-28 | `_analyze_goal_support` and `_analyze_habit_impact` do not exist anywhere in the tree |
| **Group A — GoalsIntelligenceService row** | 2026-07-28 | `analyze_goal_performance` is gone tree-wide; the surviving `get_performance_analytics` takes a non-underscore `period_days` and filters on it. Implemented, not deferred |
| **Group E — `cross_domain_analytics_service.py` mood/streak row** | 2026-07-28 | `JournalMoodAnalysis` + `get_mood_analysis` were removed in SKUEL030 tranche 3 (`7f9fc3c1c`, #737); the file records this at lines 56–60 and is now 580 lines long, short of the cited 661–665 |
| **Group I — `Entity.can_view()` and `Entity.substance_score()`** (both rows + their shared priority row) | 2026-07-28 | **Implemented, not deferred — and structurally identical.** Each is a base method whose parameters are unread because the base has nothing to do, with the behaviour fully implemented on a subclass override taking the same parameters *without* underscores: `UserOwnedEntity.can_view(viewer_uid, shared_user_uids)` (`user_owned_entity.py:72`, owner + shared logic at 81–87) and `Curriculum.substance_score(force_recalculate)` (`curriculum.py:267`, cache bypass at 280–287). An ordinary polymorphic signature is not accepted-but-unimplemented work, and listing it here invites a future sweep to "implement" a base that is intentionally inert |
| **Group I — `user_backend.get_user_context()` row** | 2026-07-28 | Had been struck through since the method's removal in `1373cc419` (2026-03-18). It was never a backend operation and no longer resolves; `UserService.get_user_context()` (`core/services/user_service.py:193`) is the live path |
| **Group C — Askesis Bootstrap Entity Services** (whole section + its priority row) | 2026-07-29 | **Carried out, not dropped.** The section's own remedy was "delete the four parameters and the four call-site arguments"; that deletion landed, so the group has no coordinates left to register. `_create_learning_services()` no longer declares `_tasks_service` / `_habits_service` / `_goals_service` / `_events_service`, and `compose.py` no longer passes the four activity services into them. Entity extraction is unaffected — it never ran through these parameters, and stays wired via `create_askesis_service()` → `askesis_factory.py` → `EntityExtractor` |
| **Priority row "K — Conversation System"** | 2026-07-28 (#856) | Its section (added 2026-02-25 in `5ce618ee1`) was deleted on 2026-06-19 by `69be520ca` (#338), which wired Neo4j conversation persistence and removed the `InMemoryConversationRepo` it documented. The groundwork was **built, not deferred** |

---

## Related Documentation

- `CLAUDE.md` — "Naming Conventions" § Parameters defines the underscore convention
- `docs/patterns/ERROR_HANDLING.md` — Result[T] pattern used in all service methods above
- `docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md` — Intelligence service architecture
- `docs/architecture/UNIFIED_USER_ARCHITECTURE.md` — UserContext and period-based analytics context
