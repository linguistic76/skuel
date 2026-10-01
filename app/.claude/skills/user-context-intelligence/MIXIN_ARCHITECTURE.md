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

## What Each Mixin Provides

This section gives each method's contract — what it reads, what it returns, and the behaviour
a caller can rely on or must not assume. It does not restate the scoring. Weights, thresholds
and branch order live in the method and change there; read the method before depending on a
number.

### LearningIntelligenceMixin — methods 1–4

| Method | Reads | Returns |
|--------|-------|---------|
| 1 `get_optimal_next_path_steps` | `zpd_service`, `vector_search`, `ps`, `tasks`, context | `Result[list[PathStep]]`, at most `max_steps` |
| 2 `get_learning_path_critical_path` | context | `Result[list[str]]` — `[]` without a `life_path_uid` |
| 3 `get_knowledge_application_opportunities` | `tasks`, context | `Result[dict[str, list[str]]]` |
| 4 `get_unblocking_priority_order` | context | `Result[list[tuple[str, int]]]`, highest count first |

**Method 1 has four candidate sources, tried in this order:** the ZPD assessment, vector
search, `ps.get_ready_to_learn_for_user`, and the context's own `get_ready_to_learn()`. Which
one answers depends on what is wired and what each returns.

What a caller must not assume:

- **`consider_capacity` is not a guarantee that the steps fit the day.** The ZPD, vector and
  `ps` sources filter by it. The context source only adds to a step's score, so its steps can
  exceed `context.available_minutes_daily`.
- **`consider_goals` is not honoured on every path.** Only the context source reads it. The
  vector source accepts and ignores it. When a ZPD assessment is non-empty but yields no
  candidates, the fall-through to the other sources passes `True` regardless of what the caller
  sent.
- **It can raise.** Steps from the first three sources are enriched by
  `_get_application_opportunities_for_ku`, which raises `RuntimeError` when its habits or
  events read fails — the one place in the package that raises on a service failure rather than
  returning `Result.fail`.
- A step's `title` is the entity's title only on the vector and `ps` sources. The ZPD and
  context sources build it from the uid.

How the assessment is computed belongs to the [zpd](../zpd/SKILL.md) skill.

**Method 3** returns six keys — `tasks`, `habits`, `goals`, `events`, `choices`, `principles` —
and fills the first four. `choices` and `principles` are always `[]`.

### LifePathIntelligenceMixin — method 7

`calculate_life_path_alignment()` reads the context and calls no service.

- Without `context.life_path_uid` it returns `Result.ok` with every score `0.0` and
  `alignment_level="undefined"`.
- With one, `alignment_level` is `flourishing`, `aligned`, `exploring` or `drifting`.
- With one, it always reaches a strict accessor, so it needs a rich context.

This is not the alignment the analytics pages show: `analytics_summary_api.py` and
`analytics_ui.py` call `AnalyticsService.calculate_life_path_alignment(user_uid)`, a different
implementation returning a dict.

### SynergyIntelligenceMixin — method 6

`get_cross_domain_synergies(min_synergy_score=0.3, include_types=None)` runs one detector per
key in `include_types`, drops results under the minimum score, and sorts by score.
`include_types=None` runs all six.

| `include_types` key | `source_domain` → `target_domain` | `synergy_type` |
|---------------------|----------------------------------|----------------|
| `habit_goal` | `habit` → `goal` | `supports` |
| `task_habit` | `habit` → `task` | `builds` |
| `knowledge_task` | `knowledge` → `task` | `enables` |
| `principle_goal` | `principle` → `goal` | `informs` |
| `goal_learning` | `knowledge` → `goal` | `enables` |
| `engagement_completion` | `pathstep` → `multi` | `spawns` |

It reads the context and calls no service. Each detector has its own scoring and its own
skip conditions — `_detect_engagement_synergies`, for one, emits nothing for an abandoned
engagement or one that spawned nothing, and scores the rest by branch. Read the detector.

### ScheduleIntelligenceMixin — method 8

`get_schedule_aware_recommendations(max_recommendations=5, time_horizon_hours=8,
respect_energy=True)` returns a **bare list**, at most `max_recommendations` long, highest
`overall_score` first.

- It reads the context and calls no service — `self.calendar` is not read.
- It always reaches a strict accessor, so it needs a rich context.
- The time slot is `context.preferred_time.value`. The field is a `TimeOfDay` that defaults to
  `TimeOfDay.ANYTIME`, and every member is truthy, so for a user with no preference the slot is
  `"anytime"`. The method's clock fallback sits behind `if self.context.preferred_time:` and is
  not reached by a context built the normal way.
- A `rest` recommendation (`uid="rest"`, `entity_type="meta"`) may be in the list.

### TemporalMomentumMixin

Synchronous; no I/O.

```python
def compute_momentum_signals(self) -> MomentumSignals:
    ...
```

`MomentumSignals` is a TypedDict in `core/ports/query_types.py`. The keys are `velocities`,
`neglected`, `habit_consistency` and `phase`. `habit_consistency` is `float | None` — `None`
when no habit item carries a rate to average. `phase` is one of
`accelerating`, `steady`, `decelerating`, `unknown`; it is `unknown` only when
`context.entities_rich` is empty. `DailyPlanningMixin` turns the signals into warnings and a
rationale clause.

### DailyPlanningMixin — method 5

Covered in [SKILL.md](SKILL.md) § The Flagship. It is the only mixin that reads
`filtered_providers`, and it reaches `TemporalMomentumMixin`'s methods through the composed
class (declared for mypy under `TYPE_CHECKING`).

The two bucketing helpers, `_build_engaged_groups` and `_compute_available_to_start`, are
module-level functions in `daily_planning.py`.

### PerceptionIntelligenceMixin — method 9

`get_cross_domain_perception_analysis()` merges three sources of dual-track check-ins
(ADR-030-dual-track-assessment-pattern) into one rollup:

| Source | Read from |
|--------|-----------|
| Per-entity — Goals, Habits, Principles | each facade's `backend.find_by(user_uid=..., limit=QueryLimit.COMPREHENSIVE)` — at most 100 entities per domain — taking `dual_track_checkins[-1]` per entity |
| User-level — productivity, engagement, decision quality | `context.dual_track_checkins` |
| Knowledge — per-Ku mastery | `context.knowledge_checkins` |

A failed per-entity read is logged and counted as empty; the others still contribute. The result
dict carries `per_domain`, `over_rated_domains`, `under_rated_domains`, `accurate_domains`,
`total_assessed_entities`, `insights` and `has_data`.

No LLM. No production caller — see [SKILL.md](SKILL.md) § Who calls them.

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
