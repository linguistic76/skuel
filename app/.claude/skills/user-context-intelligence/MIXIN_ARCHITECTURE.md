# Mixin Architecture

`UserContextIntelligence` is composed from seven mixins (ADR-021) rather than inheriting
`BaseAnalyticsService`. A `BaseAnalyticsService` owns one domain's backend and analyses that
domain's entities; this class owns no backend and synthesises across domains from one user's
context.

```python
class UserContextIntelligence(
    LearningIntelligenceMixin,
    LifePathIntelligenceMixin,
    SynergyIntelligenceMixin,
    ScheduleIntelligenceMixin,
    TemporalMomentumMixin,
    DailyPlanningMixin,
    PerceptionIntelligenceMixin,
):
    ...
```

All files are in `core/services/user/intelligence/`.

---

## The Shared Base

Every mixin inherits `IntelligenceMixinBase` (`_base.py`). It carries annotations only — the
values are assigned in `UserContextIntelligence.__init__`.

```python
class IntelligenceMixinBase:
    context: RichUserContext

    tasks: Any  # boundary: TasksService, typed at __init__
    goals: Any  # boundary: GoalsService, typed at __init__
    habits: Any  # boundary: HabitsService, typed at __init__
    events: Any  # boundary: EventsService, typed at __init__
    choices: Any  # boundary: ChoicesService, typed at __init__
    principles: Any  # boundary: PrinciplesService, typed at __init__

    ps: Any  # boundary: PsService, typed at __init__
    lp: Any  # boundary: UnifiedRelationshipService, typed at __init__
    exercises: Any  # boundary: ExerciseService, duck-typed

    report: ReportRelationshipService
    calendar: CalendarService

    vector_search: Any  # boundary: optional Neo4jVectorSearchService
    zpd_service: Any  # boundary: optional ZPDOperations
    filtered_providers: dict[str, FilteredContextProvider]
```

The base uses `Any` for the facades to keep six facade imports out of a module every mixin
imports.

mypy checks the concrete facade types at the constructor (`tasks: TasksService`, …); inside a
mixin body, a call on `self.tasks` is unchecked. Verify a method name against the facade when
you add a call.

A mixin declares no attributes of its own and defines no `__init__`. State lives on the
context.

---

## What Each Mixin Computes

### LearningIntelligenceMixin — methods 1–4

**Method 1, `get_optimal_next_path_steps`** tries four sources in order and returns from the
first that yields steps:

1. **ZPD** — when `zpd_service` is set and `assess_zone(user_uid)` returns a non-empty
   assessment. Uses the assessment's `recommended_actions` of type `learn` when present;
   otherwise ranks `top_proximal_ku_uids()` by
   `readiness × 0.5 + life_path_alignment × 0.3 + behavioral_readiness × 0.2`, plus small boosts
   for confirmed zone evidence. An assessment with an empty proximal zone falls to step 2.
2. **Vector search** — `vector_search.learning_aware_search(...)`, when wired and non-empty.
3. **`ps.get_ready_to_learn_for_user(context, limit=max_steps * 2)`**.
4. **Context** — `context.get_ready_to_learn()`, scored by `_calculate_learning_priority`
   (base 0.5; goal alignment up to 0.3; unblocking up to 0.25; life path 0.25; capacity fit up
   to 0.2; capped at 1.0).

`consider_capacity=True` keeps the steps whose cumulative `estimated_time_minutes` fits
`context.available_minutes_daily`.

Steps from sources 1–3 are enriched by `_get_application_opportunities_for_ku`, which reads
`tasks.get_learning_tasks_for_user`, `ps.find_habits_reinforcing_knowledge` and
`ps.find_events_applying_knowledge`. A failed habits or events read there raises `RuntimeError`
rather than returning `Result.fail` — the one place in the package that raises on a service
failure. A caller of method 1 that must not raise guards the call.

How the assessment itself is computed belongs to the [zpd](../zpd/SKILL.md) skill.

**Method 2, `get_learning_path_critical_path`** returns `[]` when the context has no
`life_path_uid`. Otherwise it orders the unmastered UIDs in `context.knowledge_mastery` so that
each one's prerequisites (`context.prerequisites_needed`) come first, choosing at each step the
ready unit that unlocks the most. Context only — it calls no service.

**Method 3, `get_knowledge_application_opportunities(ku_uid)`** returns a dict with six keys
(`tasks`, `habits`, `goals`, `events`, `choices`, `principles`). It fills four: tasks from
`tasks.get_learning_tasks_for_user`, goals from the context's learning goals, habits and events
by following those goals through the context. `choices` and `principles` are always `[]`.

**Method 4, `get_unblocking_priority_order`** counts, for each unmet prerequisite in
`context.prerequisites_needed`, how many entries list it, and returns `(uid, count)` pairs
sorted by count. Context only.

### LifePathIntelligenceMixin — method 7

`calculate_life_path_alignment()` reads the context and calls no service.

- No `context.life_path_uid` → `Result.ok` with every score 0.0 and
  `alignment_level="undefined"`.
- Otherwise a weighted sum: knowledge 25%, activity 25%, goal 20%, principle 15%, momentum 15%.
- The activity and goal scores are multiplied by an engagement bonus in `[1.0, 1.2]` — the share
  of active tasks, habits and goals spawned from PS engagements
  (`context.spawned_uid_to_ps_uid`) — and capped at 1.0.

| `overall_score` | `alignment_level` |
|-----------------|-------------------|
| `>= 0.9` | `flourishing` |
| `>= 0.7` | `aligned` |
| `>= 0.4` | `exploring` |
| below | `drifting` |

The knowledge and activity dimensions measure against `context.learning_goals`, used as the
proxy for the life path's goals.

This is not the alignment the analytics pages show: `analytics_summary_api.py` and
`analytics_ui.py` call `AnalyticsService.calculate_life_path_alignment(user_uid)`, a different
implementation returning a dict.

### SynergyIntelligenceMixin — method 6

`get_cross_domain_synergies(min_synergy_score=0.3, include_types=None)` runs six detectors over
the context, drops results under the minimum score, and sorts by score.

| `include_types` key | `source_domain` → `target_domain` | `synergy_type` |
|---------------------|----------------------------------|----------------|
| `habit_goal` | `habit` → `goal` | `supports` |
| `task_habit` | `habit` → `task` | `builds` |
| `knowledge_task` | `knowledge` → `task` | `enables` |
| `principle_goal` | `principle` → `goal` | `informs` |
| `goal_learning` | `knowledge` → `goal` | `enables` |
| `engagement_completion` | `pathstep` → `multi` | `spawns` |

`include_types=None` runs all six.

The engagement detector scores each non-abandoned PS engagement by the completion ratio of its
spawned tasks, goals and choices; a completed engagement scores 1.0.

### ScheduleIntelligenceMixin — method 8

`get_schedule_aware_recommendations(max_recommendations=5, time_horizon_hours=8,
respect_energy=True)` returns a **bare list**.

- Available minutes = the horizon, minus 60 per event in `context.today_event_uids`, minus the
  share already committed (`context.current_workload_score`), capped at
  `context.available_minutes_daily`.
- The time slot is `context.preferred_time` when set, otherwise the hour in the user's zone
  (`morning` / `afternoon` / `evening` / `night`).
- `context.current_workload_score >= 0.9` adds a `rest` recommendation.
- Candidates come from the context's task, habit, learning and goal fields. Each is scored
  `priority × 0.4 + schedule_fit × 0.35 + energy_match × 0.25`.

It calls no service — `self.calendar` is not read.

### TemporalMomentumMixin

Synchronous; no I/O.

```python
def compute_momentum_signals(self) -> dict[str, Any]:  # boundary: heterogeneous signal map
    ...
```

Returns `velocities` (per Activity domain, the completed share of its `entities_rich` items),
`neglected` (domains with no items), `habit_consistency` (mean `completion_rate` across habit
items) and `phase` — `accelerating` at an average velocity of 0.6 or more, `steady` at 0.3 or
more, otherwise `decelerating`. With an empty `entities_rich` every value is empty and the phase
is `unknown`.

`DailyPlanningMixin` turns the signals into warnings and a rationale clause.

### DailyPlanningMixin — method 5

Covered in [SKILL.md](SKILL.md) § The Flagship. It is the only mixin that reads
`filtered_providers`, and it reaches `TemporalMomentumMixin`'s methods through the composed
class (declared for mypy under `TYPE_CHECKING`).

The two bucketing helpers, `_build_engaged_groups` and `_compute_available_to_start`, are
module-level functions in `daily_planning.py` — pure transformations of the assembled plan.

### PerceptionIntelligenceMixin — method 9

`get_cross_domain_perception_analysis()` merges three sources of dual-track check-ins
(ADR-030-dual-track-assessment-pattern) into one rollup:

| Source | Read from |
|--------|-----------|
| Per-entity — Goals, Habits, Principles | each facade's `backend.find_by(user_uid=...)`, taking `dual_track_checkins[-1]` per entity |
| User-level — productivity, engagement, decision quality | `context.dual_track_checkins` |
| Knowledge — per-Ku mastery | `context.knowledge_checkins` |

A failed per-entity read is logged and counted as empty; the others still contribute. The result
dict carries `per_domain`, `over_rated_domains`, `under_rated_domains`, `accurate_domains`,
`total_assessed_entities`, `insights` and `has_data`.

No LLM. No production caller yet — see [SKILL.md](SKILL.md) § Who calls them.

---

## Adding a Mixin

1. Create the module beside `daily_planning.py`. Inherit `IntelligenceMixinBase`; declare
   nothing the base already declares.

   ```python
   class FocusIntelligenceMixin(IntelligenceMixinBase):
       """Deep-work recommendations from the context's schedule fields."""

       def get_deep_work_minutes(self) -> int:
           event_minutes = 60 * len(self.context.today_event_uids)
           return max(0, self.context.available_minutes_daily - event_minutes)
   ```

2. Add it to the bases of `UserContextIntelligence` in `core.py`.
3. Export it from `core/services/user/intelligence/__init__.py`.
4. If it needs a service the class does not hold, add the annotation to `IntelligenceMixinBase`,
   the parameter to `UserContextIntelligence.__init__`, the entry to the factory's
   `_required_services`, and the argument in `services_bootstrap/_intelligence_hub.py`.
5. A method with no `await` is `def`, not `async def` (SKUEL029). Methods 2, 4, 6, 7 and 8 are
   `async` without awaiting because a protocol or a facade delegation awaits them; each carries
   the lint suppression naming that reason.

---

## Testing a Mixin

Compose the mixins under test into a small class and give it a stub context — a dataclass with
the fields the method reads. `tests/unit/test_daily_planning_domain_stats.py` is the model:

```python
class MockDailyPlanningService(TemporalMomentumMixin, DailyPlanningMixin):
    def __init__(
        self,
        context: object,
        filtered_providers: dict[str, object] | None = None,
    ) -> None:
        self.context = cast("Any", context)  # boundary: stub stands in for RichUserContext
        no_op = make_no_op_service()
        self.tasks = self.habits = self.goals = no_op
        self.events = self.choices = self.principles = no_op
        self.ps = self.exercises = no_op
        self.vector_search = None
        self.filtered_providers = cast("Any", filtered_providers or {})  # boundary: mock providers
```

Guard each mocked method name against the real facade so a rename fails the test:

```python
_ = HabitsService.get_at_risk_habits_for_user
service = AsyncMock()
service.get_at_risk_habits_for_user = AsyncMock(return_value=Result.ok([]))
```

A provider mock returns a `ListContext`-shaped dict; the stats it carries are whatever the test
supplies, so a passing warning test says nothing about what the live facade's stats contain.

---

## Anti-Patterns

### Overriding a mixin method on the composed class

Put the change in the mixin that owns the method, or in a new mixin placed earlier in the bases.

### State on a mixin

```python
# WRONG
class CachingMixin(IntelligenceMixinBase):
    def __init__(self) -> None:
        self._cache: dict[str, int] = {}
```

`UserContextIntelligence.__init__` does not call `super().__init__()`, so a mixin's `__init__`
never runs.

### Re-declaring the shared attributes

Declaring `tasks` or `context` on a mixin creates a second declaration that can drift from
`IntelligenceMixinBase`. Inherit the base.
