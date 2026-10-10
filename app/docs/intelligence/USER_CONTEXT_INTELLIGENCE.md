---
related_skills:
- user-context-intelligence
updated: 2026-10-10
---
# UserContextIntelligence — the Hub Methods

## Related Skills

For implementation guidance, see:
- [@user-context-intelligence](../../.claude/skills/user-context-intelligence/SKILL.md) — the
  method contracts, the flagship's slot order, the context fields each mixin reads

## What it is

**The hub methods** are the nine questions `UserContextIntelligence` answers for one user from
their `RichUserContext` plus the domain services. **Askesis** is the pedagogical companion that
asks them; its wrappers are its door onto them, not a separate capability (the ruling and its
date: [askesis-intelligence-doors.md](../roadmap/askesis-intelligence-doors.md)).

**Location:** `core/services/user/intelligence/` (package)
**Not a `BaseAnalyticsService`:** a class composed from seven mixins (ADR-021), constructed per
request by a factory that holds the services. It owns no backend; it synthesizes across domains
from one user's context and fresh reads made at call time.

```
UserContextIntelligence = RichUserContext (one user's state, already read)
                        + the eleven domain services (fresh reads, made at call time)
```

Domain intelligence services (`TasksIntelligenceService`, …) analyse single domains.
`UserContextIntelligence` synthesizes across all of them. It runs in both tiers: the factory is
built in CORE and FULL alike, and `compose_services` refuses to finish without it. Only the two
optional services (`zpd_service`, `vector_search`) are FULL-tier.

---

## The nine methods and their doors

| # | Method | Mixin | Question | Door today |
|---|--------|-------|----------|------------|
| 1 | `get_optimal_next_path_steps()` | Learning | What should I learn next? | Insights card `learn-next` |
| 2 | `get_learning_path_critical_path()` | Learning | Fastest route to my life path? | none — staged (`_HUB_CRITICAL_PATH`) |
| 3 | `get_knowledge_application_opportunities(ku_uid)` | Learning | Where can I apply this? | Ku page, "Where you can apply this" (`GET /explore/ku/{uid}/apply`) |
| 4 | `get_unblocking_priority_order()` | Learning | What unlocks the most? | Insights card `unblock-first` |
| 5 | **`get_ready_to_work_on_today()`** | DailyPlanning | **The daily plan** | `/api/context/next-action` → `UserContextService.get_next_action` → `UserService.get_daily_work_plan` |
| 6 | `get_cross_domain_synergies()` | Synergy | What helps many things at once? | Insights card `synergies` |
| 7 | `calculate_life_path_alignment()` | LifePath | Am I living toward my life path? | Insights card `alignment` |
| 8 | `get_schedule_aware_recommendations()` | Schedule | What fits right now? | Insights card `right-now` |
| 9 | `get_cross_domain_perception_analysis()` | Perception | How do my self-ratings compare with the record? | Insights card `perception` |

**The first door — the Insights cards.** `GET /insights/hub/{question}`
(`adapters/inbound/insights_ui.py`) builds the hub from the caller's cached rich context
(`UserService.get_rich_unified_context`) and answers the `HubQuestion` the segment names, as an
HTMX fragment the `/insights` "Your intelligence" section mounts (`ui/insights/hub_cards.py`).
A failed read renders the question's error card (200), never a 500. Method 3's door is the same
shape on the Ku reading page (`learning_loop_routes.py`).

**The second door — Askesis, staged.** `AskesisService` wraps methods 1–8 (method 5's wrapper is
`get_daily_work_plan`; the other seven carry the hub method's name) as members of
`AskesisOperations`. No route calls a wrapper; they become live when the Askesis conversation
reaches a hub method by tool-selection. Registered `PLANNED` / `DELAYED` in
`scripts/detect_bloat.py` (`_ASKESIS_HUB_DOOR`).

**Method 2 waits on something else.** The critical path reads the context only (the life path's
unmastered knowledge in prerequisite order); the walk through the LP structure it was imagined
for waits on the two LP backend methods ruled *build, not now*
([lp-backend-recommendation-methods.md](../roadmap/lp-backend-recommendation-methods.md)). The
`lp` dependency is held for that walk and read by no method yet.

Every hub method returns `Result[T]`. The record types (`PathStep`, `DailyWorkPlan`,
`CrossDomainSynergy`, `LifePathAlignment`, `ScheduleAwareRecommendation`) are frozen dataclasses
in `core/models/context_types.py` with tuple sequence fields; method 9 returns the
`PerceptionAnalysis` TypedDict (`core/ports/query_types.py`). Signatures and fields:
[QUICK_REFERENCE.md](../../.claude/skills/user-context-intelligence/QUICK_REFERENCE.md).

---

## The eleven required services

"SKUEL runs at full capacity or not at all": `UserContextIntelligence.__init__` and the factory
both raise `ValueError` naming any required service that is `None`. A twelfth service touches
five sites, all of which the `ValueError` guards read: the factory's `_required_services` dict
and its `__init__` parameter; `UserContextIntelligence.__init__`'s parameter, its `required`
mapping and its `self.<service>` assignment; the annotation on `IntelligenceMixinBase`
(`_base.py`), which is what a mixin reads; and the argument in
`services_bootstrap/_intelligence_hub.py`. Miss the assignment or the annotation and the
constructors validate while the method raises `AttributeError`.

| Group | Parameter | Wired value (`services_bootstrap/_intelligence_hub.py`) | Read by |
|-------|-----------|------------------------------------------------------|---------|
| Activity (6) | `tasks`, `goals`, `habits`, `events`, `choices`, `principles` | the **facades** (`TasksService`, …) — not `.relationships`; the planning methods (`get_actionable_tasks_for_user`, …) are facade methods | methods 1, 5, 9 |
| Curriculum (3) | `ps` | `PsService` facade | methods 1, 5 |
| | `lp` | `LpService.relationships` (`UnifiedRelationshipService`) | no method yet (held for method 2's LP walk) |
| | `exercises` | `ExerciseService` facade | method 5 (revisions, unsubmitted exercises) |
| Processing (1) | `report` | `ReportRelationshipService` | method 5 — `get_pending_submissions(pipelines=Pipeline.awaiting_report())`, the plan's `awaiting_report` slot |
| Temporal (1) | `calendar` | `CalendarService` | method 8 — `event_items_in_range` for the horizon's committed minutes |

Optional: `zpd_service` (`ZPDOperations`, FULL tier — method 1's first candidate source),
`vector_search_service` (FULL tier — methods 1 and 5's semantic step), `filtered_providers`
(the nine facades that implement `FilteredContextProvider`: the six Activity facades, `ps`,
`learning_paths`, `exercises` — read by method 5's domain-health warnings, Activity keys only).

---

## Rich context is required

`factory.create()` and every mixin take a `RichUserContext` — the `UserContext` subclass that
narrows the seven `RICH_ONLY_FIELDS` from `X | None` to `X` and pins `is_rich_context=True`.
mypy rejects a standard context at the call site.

| Read | Depth |
|------|-------|
| `UserService.get_rich_unified_context(user_uid)` | Rich — cached 5 minutes, built on a miss; **the read the HTTP and HTMX doors make** (an Askesis wrapper makes no read — it takes the `RichUserContext` its caller hands it) |
| `UserContextBuilder.build_rich(user_uid, window="30d")` | Rich — always builds |
| `UserService.get_user_context(user_uid)` / `UserContextBuilder.build(user_uid)` | Standard — not accepted by the factory |

The `/api/context/*` view methods (`UserContextService`: dashboard, summary, at-risk habits,
adaptive path, create-tasks-from-goal) build the rich context too; only
`complete_habit_with_context` reads the standard depth.

Two guards stack: the parameter type, and the strict accessors (`get_blocked_tasks()`,
`get_habits_by_goal()`, …) that go through `UserContext._as_rich(operation)` and raise
`RichContextRequiredError` on a standard context. There is no universal runtime check —
`factory.create()` does not test the depth, so a wrong-depth context handed over by an unchecked
caller gets as far as the first strict accessor the call reaches. The type is the guard.

```python
context_result = await user_service.get_rich_unified_context(user_uid)
if context_result.is_error:
    return Result.fail(context_result)

intelligence = factory.create(context_result.value)
plan_result = await intelligence.get_ready_to_work_on_today()
```

What `build_rich()` reads, and why a new read is a new `RICH_CONTEXT_STATEMENTS` entry:
[UNIFIED_USER_ARCHITECTURE.md](../architecture/UNIFIED_USER_ARCHITECTURE.md).

---

## The flagship: the daily plan (method 5)

`get_ready_to_work_on_today(prioritize_life_path=True, respect_capacity=True)` fills its slots
in a fixed order — at-risk habits, today's events, pending revisions, unsubmitted exercises,
entries awaiting a report (named, no minutes), tasks, daily habits, learning, goals, decisions,
principles — accumulating `estimated_time` and, under `respect_capacity`, skipping a
capacity-checked item that would push the total past `context.available_minutes_daily`. The
learning slot takes the first source that answers: the ZPD assessment's learn actions, vector
search, `ps.get_ready_to_learn_for_user`; a candidate's minutes come from
`context.estimated_minutes(uid, default)` (a path step in progress answers with its own
estimate). A slot whose read fails contributes nothing; the plan is still `Result.ok`.

`prioritize_life_path` changes one clause of the rationale, not the selection. Warnings, the
domain-health checks over `filtered_providers`, the momentum signals and the ADR-059 engagement
buckets: skill § The Flagship.

`UserContextService.get_next_action` projects the plan into `NextActionResult` for
`/api/context/next-action`.

---

## Mixin architecture

```python
class UserContextIntelligence(
    LearningIntelligenceMixin,      # Methods 1-4
    LifePathIntelligenceMixin,      # Method 7
    SynergyIntelligenceMixin,       # Method 6
    ScheduleIntelligenceMixin,      # Method 8
    TemporalMomentumMixin,          # compute_momentum_signals() — feeds method 5
    DailyPlanningMixin,             # Method 5 — the flagship
    PerceptionIntelligenceMixin,    # Method 9
): ...
```

Every mixin inherits `IntelligenceMixinBase` (`_base.py`), the one declaration of the shared
attribute surface (`self.context`, `self.tasks`, …). A mixin declares no attributes of its own
and defines no `__init__`; state lives on the context. Per-mixin contracts:
[MIXIN_ARCHITECTURE.md](../../.claude/skills/user-context-intelligence/MIXIN_ARCHITECTURE.md).

Not the same method: `AnalyticsService.calculate_life_path_alignment(user_uid)` (the analytics
pages, `analytics_ui.py`, `analytics_summary_api.py`) is a different implementation returning a
dict. Method 7 is the hub's.

---

## Factory pattern

`UserContextIntelligenceFactory` holds the eleven services once, at bootstrap
(`services_bootstrap/_intelligence_hub.py`), and `create(context)` binds them to one user's
context. The context is user-specific and built on demand; the services are singletons. The
factory is stored on `services.context_intelligence` and post-wired onto
`user_service.intelligence_factory`. An instance is bound to the context it was created with —
keep the factory, not an instance; the context cache is the reuse mechanism and `create()` costs
nothing. Constructor, wiring and testing:
[FACTORY_PATTERN.md](../../.claude/skills/user-context-intelligence/FACTORY_PATTERN.md).

---

## Key source files

| File | Purpose |
|------|---------|
| `core/services/user/intelligence/core.py` | `UserContextIntelligence` |
| `core/services/user/intelligence/factory.py` | `UserContextIntelligenceFactory` |
| `core/services/user/intelligence/_base.py` | `IntelligenceMixinBase` |
| `core/services/user/intelligence/{learning,life_path,synergy,schedule,perception}_intelligence.py`, `daily_planning.py`, `temporal_momentum.py` | the mixins |
| `core/models/context_types.py` | the record types and the `Contextual*` items |
| `core/models/enums/intelligence_enums.py` | `HubQuestion` — card segment → method number |
| `adapters/inbound/insights_ui.py`, `ui/insights/hub_cards.py` | the first door |
| `adapters/inbound/learning_loop_routes.py` | method 3's door |
| `core/services/user/user_context_service.py` | method 5's door (`get_next_action`) |
| `core/services/askesis_service.py`, `core/ports/askesis_protocols.py` | the staged second door |
| `services_bootstrap/_intelligence_hub.py` | factory, ZPD and Askesis wiring |

## See also

- [ADR-021](../decisions/ADR-021-user-context-intelligence-modularization.md) — the mixin decomposition
- [ADR-030-dual-track-assessment-pattern.md](../decisions/ADR-030-dual-track-assessment-pattern.md) — the check-ins method 9 reads
- [UNIFIED_USER_ARCHITECTURE.md](../architecture/UNIFIED_USER_ARCHITECTURE.md) — `UserContext`, the builder, the MEGA-QUERY
- [ASKESIS_HOW_IT_WORKS.md](../architecture/ASKESIS_HOW_IT_WORKS.md) — the companion's two halves
- [askesis-intelligence-doors.md](../roadmap/askesis-intelligence-doors.md) — the doors ruling and the staged second door
- [hub-methods-residuals.md](../roadmap/hub-methods-residuals.md) — defects the F8 build found beside the hub and registered
- [CONTEXT_FIRST_RELATIONSHIP_PATTERN.md](../patterns/CONTEXT_FIRST_RELATIONSHIP_PATTERN.md)
