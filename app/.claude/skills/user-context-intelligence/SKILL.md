---
name: user-context-intelligence
description: Expert guide for SKUEL's central cross-domain intelligence hub. Use when implementing daily planning, life path alignment, learning recommendations, schedule-aware recommendations, or when working with UserContextIntelligence, UserContextIntelligenceFactory, RichUserContext, or the hub's nine methods.
allowed-tools: Read, Grep, Glob
---

# UserContextIntelligence: Central Cross-Domain Intelligence Hub

> "THE CORE VALUE PROPOSITION: What should I work on next?"

`UserContextIntelligence` binds one user's `RichUserContext` to the domain services and answers
cross-domain questions from the two together. It lives in `core/services/user/intelligence/`.

It is **not** a `BaseAnalyticsService` subclass (there is no `BaseIntelligenceService` in the
tree). It is a class composed from seven mixins (ADR-021), constructed per request by a factory
that holds the services.

```
UserContextIntelligence = RichUserContext (one user's state, already read)
                        + domain services (fresh reads, made at call time)
```

---

## The Class

```python
class UserContextIntelligence(
    LearningIntelligenceMixin,      # Methods 1-4
    LifePathIntelligenceMixin,      # Method 7
    SynergyIntelligenceMixin,       # Method 6
    ScheduleIntelligenceMixin,      # Method 8
    TemporalMomentumMixin,          # compute_momentum_signals() — feeds method 5
    DailyPlanningMixin,             # Method 5 — the flagship
    PerceptionIntelligenceMixin,    # Method 9
):
    ...
```

Every mixin inherits `IntelligenceMixinBase` (`_base.py`), the one place the shared attribute
surface (`self.context`, `self.tasks`, …) is declared. A new service on the class is one
annotation there, one parameter on `UserContextIntelligence.__init__`, and one entry in the
factory's `_required_services` dict.

## The Nine Methods

| # | Method | Mixin | Returns | Reads |
|---|--------|-------|---------|-------|
| 1 | `get_optimal_next_path_steps(max_steps=5, consider_goals=True, consider_capacity=True)` | Learning | `Result[list[PathStep]]` | `zpd_service`, `vector_search`, `ps`, `tasks`, context |
| 2 | `get_learning_path_critical_path()` | Learning | `Result[list[str]]` | context only |
| 3 | `get_knowledge_application_opportunities(ku_uid)` | Learning | `Result[dict[str, list[str]]]` | `tasks`, context |
| 4 | `get_unblocking_priority_order()` | Learning | `Result[list[tuple[str, int]]]` | context only |
| 5 | **`get_ready_to_work_on_today(prioritize_life_path=True, respect_capacity=True)`** | DailyPlanning | `Result[DailyWorkPlan]` | six Activity facades, `ps`, `exercises`, `vector_search`, `filtered_providers`, context |
| 6 | `get_cross_domain_synergies(min_synergy_score=0.3, include_types=None)` | Synergy | `Result[list[CrossDomainSynergy]]` | context only |
| 7 | `calculate_life_path_alignment()` | LifePath | `Result[LifePathAlignment]` | context only |
| 8 | `get_schedule_aware_recommendations(max_recommendations=5, time_horizon_hours=8, respect_energy=True)` | Schedule | `list[ScheduleAwareRecommendation]` — **a bare list, not a `Result`** | context only |
| 9 | `get_cross_domain_perception_analysis()` | Perception | `Result[dict[str, Any]]` | `goals` / `habits` / `principles` backends, context |

The flags on method 1 are not guarantees: which of its four sources answers decides whether
`consider_capacity` filters or only scores, and whether `consider_goals` is read at all — see
[MIXIN_ARCHITECTURE.md](MIXIN_ARCHITECTURE.md).

Method 8 is the one method that does not return `Result[T]`: it is a fail-soft read that
degrades to fewer recommendations, and `AskesisService.get_schedule_aware_recommendations` wraps
the list into a `Result`.

`PathStep` here is `core.models.context_types.PathStep` — a frozen recommendation record keyed
by `ku_uid`. It shares its name with the curriculum entity
`core.models.pathways.path_step.PathStep`; import the one you mean by module.

### Who calls them

| Method | Production caller |
|--------|-------------------|
| 5 | `/api/context/next-action` → `UserContextService.get_next_action` → `UserService.get_daily_work_plan` → `factory.create(context).get_ready_to_work_on_today()` |
| 1–8 | `AskesisService` wraps each one — the `AskesisOperations` protocol (`core/ports/askesis_protocols.py`). Method 5's wrapper is `get_daily_work_plan`; the other seven carry the hub method's own name. No route calls any of the eight wrappers — the Askesis API registers one route, `/api/askesis/ask`. |
| 9 | None, and no Askesis wrapper. Registered in `PLANNED_METHODS` (`scripts/detect_bloat.py`) as built and waiting on a perception-insights panel. |

So method 5 has two call paths into the hub — `UserService.get_daily_work_plan` and
`AskesisService.get_daily_work_plan` — and the first is the one a request reaches today. A
change to a hub method's signature updates its Askesis wrapper and the protocol with it. Treat
methods 1–4 and 6–9 as a library surface: read the method before building on a claim about what
it returns.

---

## Rich Context Is Required

`factory.create()` and every mixin take a `RichUserContext` — the `UserContext` subclass that
narrows the seven `RICH_ONLY_FIELDS` from `X | None` to `X` and pins `is_rich_context=True`.
mypy rejects a standard context at the call site.

| Read | Returns | Depth |
|------|---------|-------|
| `UserService.get_rich_unified_context(user_uid)` | `Result[RichUserContext]` | Rich — cached 5 minutes, built on a miss |
| `UserContextBuilder.build_rich(user_uid, min_confidence=0.7, window="30d")` | `Result[RichUserContext]` | Rich — always builds |
| `UserService.get_user_context(user_uid)` | `Result[UserContext]` | **Standard** — not accepted by the factory |
| `UserContextBuilder.build(user_uid)` | `Result[UserContext]` | Standard |
| `UserService.peek_cached_context(user_uid)` | `RichUserContext \| None` | Cache hit only — never builds |

```python
context_result = await user_service.get_rich_unified_context(user_uid)
if context_result.is_error:
    return Result.fail(context_result)

intelligence = factory.create(context_result.value)
plan_result = await intelligence.get_ready_to_work_on_today()
```

Two mechanisms guard the rich-only fields, and they stack:

1. **Compile time** — type the parameter `RichUserContext`.
2. **Read path** — read a rich-only field through its accessor (`context.get_habits_by_goal()`,
   or `context.habits_by_goal_or_empty()` where either depth is tolerated). The strict accessors
   go through `UserContext._as_rich(operation)`, which raises `RichContextRequiredError` on a
   standard context. SKUEL018 forbids a direct `.habits_by_goal` read outside the accessor files.

**There is no universal runtime guard.** `factory.create()` does not check the depth, and no
method checks it on entry. A standard context handed over by an unchecked caller gets as far as
the first strict accessor the call happens to reach, and that depends on the method, its
arguments and the data. Where an accessor is reached it raises `RichContextRequiredError` — an
exception, not a `Result.fail`.

Measured on a standard `UserContext` with a few fields set:

| Call | Outcome |
|------|---------|
| Method 5 | Returns a plan — it calls no strict accessor. The plan is built from the standard fields (`daily_habits`, `available_minutes_daily`) and whatever the services return for a context with no `entities_rich`. |
| Method 6, default `include_types` | Raises at `get_habits_by_goal()` |
| Method 6, `include_types` limited to `knowledge_task`, `principle_goal`, `goal_learning` or `engagement_completion` | Returns `Result.ok([])` |
| Method 7, with a life path, active tasks and learning goals | Raises at `get_tasks_for_goal()` |
| Method 8 | Raises at `get_blocked_tasks()` |
| Methods 2 and 4 | Return a `Result` |

So a wrong-depth context can produce a plausible answer instead of an error. The type is the
guard.

`entities_rich` is not one of the seven: read it directly (`context.entities_rich.get("tasks", [])`).
At standard depth it is an empty dict.

`is_rich(ctx)` (`unified_user_context.py`) is the `TypeGuard` for code that holds a plain
`UserContext` and wants to narrow when it happens to be rich.

### What `build_rich()` reads

One concurrent round-trip under a single `asyncio.gather`:

- **The MEGA-QUERY** — six plan-cached statements, one per read family
  (`RICH_CONTEXT_STATEMENTS` in `adapters/persistence/neo4j/user_context_queries.py`: tasks &
  goals, habits & events, principles & choices, knowledge, curriculum, learner state), run by
  `execute_mega_query` and merged by top-level key.
- **Five reads beside it** — current path steps, PS engagements, groups,
  `SUBMISSION_STATS_QUERY`, `ENTRY_KNOWLEDGE_APPLIED_QUERY`.

A failed MEGA-QUERY, submission-stats or applied-knowledge read fails the build. A failed
path-step, engagement or group read does not: the fields stay at their defaults
(`active_ps_engagements` stays `None`).

**A new read is a new `RICH_CONTEXT_STATEMENTS` entry, never a section appended to an existing
statement.** The server serves a statement from its plan cache only up to a size; past it every
execution re-plans. `tests/integration/test_user_context_plan_cache.py` derives its
parametrization from the registry.

`window` is a report-period token — a trailing window (`"7d"`, `"14d"`, `"30d"`, `"90d"`) or a
calendar period (`"2026-W37"`, `"2026-09"`), resolved by `core/utils/report_periods.py`. Open
entities are always admitted; completed ones from the period's start on. An unknown token is a
validation failure, never a substituted default.

The ZPD capstone runs last: when the builder has a `zpd_service` (FULL tier),
`context.zpd_assessment` is set from `assess_zone(user_uid, context=context)`. It stays `None`
at CORE tier and when the assessment read fails.

No Cypher lives in `core/` (SKUEL021): `UserContextBuilder(query_executor, user_service=None)`
takes a `UserContextQueryOperations` executor built at the composition root. `build()` and
`build_rich()` resolve the user through `user_service` and fail without it;
`zpd_service` and `ps_engagement_service` are attributes set after construction.

---

## Services on the Instance

`UserContextIntelligence.__init__` requires eleven services and raises `ValueError` naming any
that is `None`.

| Attribute | Wired value | Called by |
|-----------|-------------|-----------|
| `tasks` | `TasksService` facade | DailyPlanning, Learning |
| `goals` | `GoalsService` facade | DailyPlanning, Perception |
| `habits` | `HabitsService` facade | DailyPlanning, Perception |
| `events` | `EventsService` facade | DailyPlanning |
| `choices` | `ChoicesService` facade | DailyPlanning |
| `principles` | `PrinciplesService` facade | DailyPlanning, Perception |
| `ps` | `PsService` facade | DailyPlanning, Learning |
| `exercises` | `ExerciseService` facade | DailyPlanning |
| `lp` | `LpService.relationships` (`UnifiedRelationshipService`) | no mixin |
| `report` | `ReportRelationshipService` | no mixin |
| `calendar` | `CalendarService` | no mixin |

`lp`, `report` and `calendar` are required at construction and stored, and no mixin method reads
them. Schedule-aware recommendations and life-path alignment are computed from context fields.
Do not document a method as "using the calendar service" because the attribute exists.

The Activity facades are passed whole — **not** `.relationships`. The planning methods the
mixins call (`get_actionable_tasks_for_user`, `get_at_risk_habits_for_user`, …) are facade
methods.

### Optional

| Attribute | Value | When `None` / empty |
|-----------|-------|---------------------|
| `zpd_service` | `ZPDOperations` | CORE tier. Method 1 goes straight to the activity-based ranking. |
| `vector_search` | `Neo4jVectorSearchService` | CORE tier. Methods 1 and 5 skip the semantic step. |
| `filtered_providers` | `dict[str, FilteredContextProvider]` | Empty dict: method 5 adds no domain-health warnings. |

The factory itself is built in both tiers — `compose_services` refuses to finish without
`services.context_intelligence` and `user_service.intelligence_factory`. The daily plan is an
Analog-layer read.

See [FACTORY_PATTERN.md](FACTORY_PATTERN.md) for the constructor, the bootstrap wiring and the
provider dict.

---

## The Flagship: `get_ready_to_work_on_today()`

Slots are filled in this order. `estimated_time` accumulates as it goes; with
`respect_capacity=True` a slot marked *capacity-checked* skips an item that would push the total
past `context.available_minutes_daily`.

| Slot | Source | Takes | Minutes each | Capacity-checked |
|------|--------|-------|--------------|------------------|
| 1 At-risk habits | `habits.get_at_risk_habits_for_user(context)` | first 3 | 15 | no |
| 2 Today's events | `events.get_upcoming_events_for_user(context)` | all returned (`limit` defaults to 5) | 30 | no |
| 2.3 Pending revisions | `exercises.get_pending_revisions_for_user(context)` | all returned (the service's `limit` defaults to 3) | `est_time_minutes` | yes |
| 2.5 Unsubmitted exercises | `exercises.get_actionable_exercises_for_user(context)` | all returned (same default) | `est_time_minutes` | yes |
| 3 Tasks | `tasks.get_actionable_tasks_for_user(context, limit=5)` | 2 overdue + 3 others | 30 | yes |
| 4 Daily habits | `context.daily_habits` not already in slot 1 | first 3 | 15 | yes |
| 5 Learning | see below | up to 3 | `estimated_time_to_mastery`, default 30 | yes |
| 6 Goals | `goals.get_advancing_goals_for_user(context, limit=2)` | all returned | 0 | no |
| 7 Decisions | `choices.get_pending_decisions_for_user(context)` | 2 with `priority_score >= 0.7` | 0 | no |
| 8 Principles | `principles.get_aligned_principles_for_user(context)` | first 3 | 0 | no |

A slot whose service read fails or returns nothing contributes nothing — the plan is still
returned `Result.ok`. The method has no failing branch of its own.

**Slot 5 (learning)** runs only when `respect_capacity` is off or the plan so far is under 70% of
the available minutes, and takes the first branch that applies:

1. `context.zpd_assessment` is present and non-empty → its top three recommended actions, keeping
   those whose `action_type == "learn"`.
2. `vector_search` is wired → `learning_aware_search(...)`, three results; an empty or failed
   search falls to branch 3.
3. `ps.get_ready_to_learn_for_user(context, limit=3)`.

Only branch 3 fills `contextual_knowledge`; branches 1 and 2 add UIDs to `learning` alone.

**Exercises** come from `ExerciseService`, which reads `context.unsubmitted_exercises` /
`context.pending_revised_exercises` and joins prerequisite mastery, so each `ContextualExercise`
carries `blocking_kus` and `readiness_score`.

### Warnings

Appended to `plan.warnings` in this order:

1. Revisions: the count of `context.pending_revised_exercises`; revisions blocked by unmastered
   prerequisites.
2. Exercises: overdue count; blocked count.
3. Tasks: overdue count.
4. `workload_utilization > 0.9`; no learning scheduled while `context.learning_goals` is set.
5. Domain health — only when `filtered_providers` is non-empty (§ Domain-health warnings).
6. Momentum — `TemporalMomentumMixin`: domains with nothing in `entities_rich`, and habit
   consistency under 0.4. Consistency is 0.0 when there are no habit items to average, so the
   low-consistency warning also reaches a user who tracks no habits.

### Domain-health warnings

`_query_domain_stats(domain)` calls
`filtered_providers[domain].get_filtered_context(user_uid=..., status_filter="all")` and returns
the `stats` dict, or `None` when the domain has no provider or the read failed. `None` means
"unavailable", never "zero" — a warning whose stats are `None` is skipped.

Each facade computes `stats` over what its read returns, and that read is `find_by` with its
default `limit=100`. For a user with more than 100 entities in a domain, `total` stops at 100
and every other count is a count within those 100.

Only the six Activity keys are read:

| Domain | Key read | Warns when |
|--------|----------|------------|
| tasks | `active` | `> 30` |
| goals | `active` | `== 0` |
| habits | `total` | `== 0` |
| events | `today` | `>= 5` |
| choices | `pending` | `>= 5` |
| principles | `total`, `core` | `total > 0` and `core == 0` |
| goals + habits | `active`, `active` | goals `>= 10` and habits `== 0` |
| tasks + goals | `active`, `active` | tasks `> 20` and goals `== 0` |

The stats come from `core/utils/activity_stats.py`. `compute_choice_stats` counts the statuses
`"pending"` and `"decided"`; a Choice's statuses are `draft` / `active` / `completed` /
`archived`, so `pending` is 0 for every user and **the choices warning does not fire**. Do not
build on it.

### Plan metadata

- `workload_utilization = min(1.0, estimated_time / max(available_minutes, 1))`.
- `fits_capacity = workload_utilization <= 1.0` — with the clamp above, this is `True` on every
  plan. Read `workload_utilization` or `estimated_time_minutes`, not `fits_capacity`.
- `priorities` and `rationale` are built from the assembled plan, then set with
  `dataclasses.replace`.
- **PS-engagement buckets (ADR-059)** — when `context.active_ps_engagements` is non-empty,
  `engaged_ps_groups` holds one `EngagedPsGroup` per engagement (its spawned UIDs intersected
  with the plan's per-domain lists) and `available_to_start` holds path steps in
  `active_path_steps_rich` the user has not engaged.

`Priority` (the enum) is not read by `daily_planning.py`. The per-domain planning methods
produce each item's `priority_score`.

---

## Return Types

All five are `@dataclass(frozen=True)` in `core/models/context_types.py`, re-exported from
`core.services.user.intelligence`. Their sequence fields are tuples. One field is a mapping:
`PathStep.application_opportunities` is a `dict[str, tuple[str, ...]]`, so a `PathStep` is
frozen but not deeply immutable, and not hashable — do not put one in a set or use it as a
dict key.

| Type | Key fields |
|------|------------|
| `DailyWorkPlan` | per-domain UID tuples (`learning`, `tasks`, `habits`, `events`, `goals`, `choices`, `principles`, `exercises`), `contextual_*` tuples, `engaged_ps_groups`, `available_to_start`, `estimated_time_minutes`, `workload_utilization`, `rationale`, `priorities`, `warnings` |
| `PathStep` | `ku_uid`, `title`, `rationale`, `prerequisites_met`, `aligns_with_goals`, `unlocks_count`, `priority_score`, `application_opportunities` |
| `LifePathAlignment` | `overall_score`, `alignment_level`, five dimension scores, `strengths`, `gaps`, `recommendations` |
| `CrossDomainSynergy` | `source_uid`, `source_domain`, `target_uids`, `synergy_type`, `synergy_score` |
| `ScheduleAwareRecommendation` | `uid`, `recommendation_type`, `suggested_time_slot`, `schedule_fit_score`, `overall_score` |

Full field lists: [QUICK_REFERENCE.md](QUICK_REFERENCE.md).

`ContextualTask` and `ContextualGoal` each carry a `learning_requirements` payload, built by
`build_learning_requirements` (`core/services/infrastructure/prerequisite_checker.py`) from the
same mastery split that drives readiness; it is `None` when the entity requires no knowledge. See
[PREREQUISITE_CHECKER_PATTERN.md](/docs/patterns/PREREQUISITE_CHECKER_PATTERN.md).

---

## Analytics Tier, Not AI

No mixin calls an LLM. At CORE tier every method is graph reads plus Python. At FULL tier two
optional inputs join, and each has a fallback:

- `zpd_service` — ranking for method 1; `context.zpd_assessment` for slot 5.
- `vector_search` — the semantic step in methods 1 and 5, which embeds the query text through
  the embeddings service.

LLM features live in the per-domain `*AIService` classes (`BaseAIService`), set on each facade's
`.ai` slot at FULL tier. See [base-ai-service](../base-ai-service/SKILL.md).

---

## Anti-Patterns

### Passing a standard context

```python
# WRONG - get_user_context() builds the standard depth; mypy rejects the create() call
context_result = await user_service.get_user_context(user_uid)
intelligence = factory.create(context_result.value)

# CORRECT
context_result = await user_service.get_rich_unified_context(user_uid)
if context_result.is_error:
    return Result.fail(context_result)
intelligence = factory.create(context_result.value)
```

### Constructing without the factory

```python
# WRONG - duplicates the bootstrap wiring
intelligence = UserContextIntelligence(context=context, tasks=services.tasks, ...)

# CORRECT
intelligence = services.context_intelligence.create(context)
```

### Holding an instance across requests

An instance is bound to one context snapshot. Build the context (or take the cached one) and
call `factory.create()` per request; the context cache, not the instance, is what is reused.

### Reading `.value` without checking

```python
# WRONG
plan = (await intelligence.get_ready_to_work_on_today()).value

# CORRECT
result = await intelligence.get_ready_to_work_on_today()
if result.is_error:
    return Result.fail(result)
plan = result.value
```

### Re-querying what the context holds

A method that takes a context does not fetch the user's tasks or goals again. Take
`RichUserContext` as the parameter and read `context.entities_rich[...]`, the UID lists, or an
accessor. If a method needs one field, take that field as a primitive — do not introduce a
narrower "awareness" protocol over `UserContext`.

---

## Key Source Files

| File | Purpose |
|------|---------|
| `core/services/user/intelligence/core.py` | `UserContextIntelligence` |
| `core/services/user/intelligence/factory.py` | `UserContextIntelligenceFactory` |
| `core/services/user/intelligence/_base.py` | `IntelligenceMixinBase` — shared attribute surface |
| `core/services/user/intelligence/daily_planning.py` | Method 5 + domain-health warnings + ADR-059 bucketing |
| `core/services/user/intelligence/learning_intelligence.py` | Methods 1–4 |
| `core/services/user/intelligence/life_path_intelligence.py` | Method 7 |
| `core/services/user/intelligence/synergy_intelligence.py` | Method 6 |
| `core/services/user/intelligence/schedule_intelligence.py` | Method 8 |
| `core/services/user/intelligence/perception_intelligence.py` | Method 9 |
| `core/services/user/intelligence/temporal_momentum.py` | Momentum signals |
| `core/models/context_types.py` | Return types and the `Contextual*` items |
| `core/services/user/unified_user_context.py` | `UserContext`, `RichUserContext`, `is_rich` |
| `core/services/user/user_context_builder.py` | `build()` / `build_rich()` |
| `core/services/user/_context_planning_mixin.py` | `UserService.get_rich_unified_context`, `get_daily_work_plan` |
| `services_bootstrap/_intelligence_hub.py` | Factory, ZPD and Askesis wiring |
| `core/ports/filtered_context_protocols.py` | `FilteredContextProvider` |

## Deep Dive Resources

- [UNIFIED_USER_ARCHITECTURE.md](/docs/architecture/UNIFIED_USER_ARCHITECTURE.md) — `User`, `UserContext`, the builder, the MEGA-QUERY
- [USER_CONTEXT_INTELLIGENCE.md](/docs/intelligence/USER_CONTEXT_INTELLIGENCE.md) — the hub's own doc
- [ADR-021](/docs/decisions/ADR-021-user-context-intelligence-modularization.md) — mixin decomposition
- [ADR-030-usercontext-file-consolidation.md](/docs/decisions/ADR-030-usercontext-file-consolidation.md) — the canonical `UserContext` location
- [ADR-030-dual-track-assessment-pattern.md](/docs/decisions/ADR-030-dual-track-assessment-pattern.md) — the check-ins method 9 reads

## Related Skills

- **[base-analytics-service](../base-analytics-service/SKILL.md)** — per-domain analytics services (`BaseAnalyticsService`)
- **[zpd](../zpd/SKILL.md)** — the assessment behind `zpd_service` and `context.zpd_assessment`
- **[activity-domains](../activity-domains/SKILL.md)** — the six facades and `get_filtered_context()`
- **[learning-loop](../learning-loop/SKILL.md)** — where the exercise and revision slots come from
- **[result-pattern](../result-pattern/SKILL.md)** — `Result[T]`

## See Also

- [QUICK_REFERENCE.md](QUICK_REFERENCE.md) — imports, signatures, return-type fields, context fields
- [MIXIN_ARCHITECTURE.md](MIXIN_ARCHITECTURE.md) — what each mixin computes
- [FACTORY_PATTERN.md](FACTORY_PATTERN.md) — factory, bootstrap wiring, testing
- [PATTERNS.md](PATTERNS.md) — the three rules in one place
