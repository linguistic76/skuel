# UserContextIntelligence Quick Reference

## Files

```
core/services/user/intelligence/
├── __init__.py                 # package exports
├── _base.py                    # IntelligenceMixinBase — shared attribute annotations
├── core.py                     # UserContextIntelligence
├── factory.py                  # UserContextIntelligenceFactory
├── daily_planning.py           # DailyPlanningMixin (method 5)
├── learning_intelligence.py    # LearningIntelligenceMixin (methods 1-4)
├── life_path_intelligence.py   # LifePathIntelligenceMixin (method 7)
├── synergy_intelligence.py     # SynergyIntelligenceMixin (method 6)
├── schedule_intelligence.py    # ScheduleIntelligenceMixin (method 8)
├── perception_intelligence.py  # PerceptionIntelligenceMixin (method 9)
└── temporal_momentum.py        # TemporalMomentumMixin

core/models/context_types.py                 # return types + Contextual* items
core/services/user/unified_user_context.py   # UserContext, RichUserContext, is_rich
core/services/user/user_context_builder.py   # build() / build_rich()
core/services/user/rich_context.py           # entities_rich lookup helpers
adapters/persistence/neo4j/user_context_queries.py  # RICH_CONTEXT_STATEMENTS + the executor
services_bootstrap/_intelligence_hub.py      # factory wiring
```

## Imports

```python
from core.services.user.intelligence import (
    UserContextIntelligence,
    UserContextIntelligenceFactory,
)

# Return types — re-exported by the package, defined in core.models.context_types
from core.models.context_types import (
    CrossDomainSynergy,
    DailyWorkPlan,
    LifePathAlignment,
    PathStep,
    ScheduleAwareRecommendation,
)

# Enriched items inside a DailyWorkPlan
from core.models.context_types import (
    ContextualExercise,
    ContextualGoal,
    ContextualHabit,
    ContextualKnowledge,
    ContextualTask,
    EngagedPsGroup,
)

from core.services.user.unified_user_context import RichUserContext, UserContext, is_rich
```

The package exports six of the seven mixins. `PerceptionIntelligenceMixin` is imported from its
module:

```python
from core.services.user.intelligence import (
    DailyPlanningMixin,
    LearningIntelligenceMixin,
    LifePathIntelligenceMixin,
    ScheduleIntelligenceMixin,
    SynergyIntelligenceMixin,
    TemporalMomentumMixin,
)
from core.services.user.intelligence.perception_intelligence import PerceptionIntelligenceMixin
```

---

## Required Services

| # | Parameter | Wired value | Read by a mixin |
|---|-----------|-------------|-----------------|
| 1 | `tasks` | `TasksService` | yes |
| 2 | `goals` | `GoalsService` | yes |
| 3 | `habits` | `HabitsService` | yes |
| 4 | `events` | `EventsService` | yes |
| 5 | `choices` | `ChoicesService` | yes |
| 6 | `principles` | `PrinciplesService` | yes |
| 7 | `ps` | `PsService` | yes |
| 8 | `lp` | `LpService.relationships` | no |
| 9 | `exercises` | `ExerciseService` | yes |
| 10 | `report` | `ReportRelationshipService` | no |
| 11 | `calendar` | `CalendarService` | no |

Optional: `vector_search_service`, `zpd_service`, `filtered_providers` — see
[FACTORY_PATTERN.md](FACTORY_PATTERN.md).

---

## Method Signatures

```python
# 1
async def get_optimal_next_path_steps(
    self,
    max_steps: int = 5,
    consider_goals: bool = True,
    consider_capacity: bool = True,
) -> Result[list[PathStep]]: ...

# 2
async def get_learning_path_critical_path(self) -> Result[list[str]]: ...

# 3
async def get_knowledge_application_opportunities(
    self, ku_uid: str
) -> Result[dict[str, list[str]]]: ...

# 4
async def get_unblocking_priority_order(self) -> Result[list[tuple[str, int]]]: ...

# 5 — the flagship
async def get_ready_to_work_on_today(
    self,
    prioritize_life_path: bool = True,
    respect_capacity: bool = True,
) -> Result[DailyWorkPlan]: ...

# 6
async def get_cross_domain_synergies(
    self,
    min_synergy_score: float = 0.3,
    include_types: list[str] | None = None,
) -> Result[list[CrossDomainSynergy]]: ...

# 7
async def calculate_life_path_alignment(self) -> Result[LifePathAlignment]: ...

# 8 — returns a bare list
async def get_schedule_aware_recommendations(
    self,
    max_recommendations: int = 5,
    time_horizon_hours: int = 8,
    respect_energy: bool = True,
) -> list[ScheduleAwareRecommendation]: ...

# 9
async def get_cross_domain_perception_analysis(
    self,
) -> Result[dict[str, Any]]: ...  # boundary: heterogeneous rollup map

# TemporalMomentumMixin — synchronous
def compute_momentum_signals(self) -> MomentumSignals: ...  # TypedDict, core/ports/query_types.py
```

`prioritize_life_path` changes one clause of the plan's `rationale`; it does not change which
items are selected.

---

## Return Types

All are `@dataclass(frozen=True)`; build a changed copy with `dataclasses.replace`. Sequence
fields are tuples; `PathStep.application_opportunities` is the one mapping field.

### DailyWorkPlan

```python
@dataclass(frozen=True)
class DailyWorkPlan:
    # UIDs per domain
    learning: tuple[str, ...] = ()
    tasks: tuple[str, ...] = ()
    habits: tuple[str, ...] = ()
    events: tuple[str, ...] = ()
    goals: tuple[str, ...] = ()
    choices: tuple[str, ...] = ()
    principles: tuple[str, ...] = ()
    exercises: tuple[str, ...] = ()

    # Enriched items
    contextual_tasks: tuple[ContextualTask, ...] = ()
    contextual_habits: tuple[ContextualHabit, ...] = ()
    contextual_goals: tuple[ContextualGoal, ...] = ()
    contextual_knowledge: tuple[ContextualKnowledge, ...] = ()
    contextual_exercises: tuple[ContextualExercise, ...] = ()

    # PS-engagement buckets (ADR-059)
    engaged_ps_groups: tuple[EngagedPsGroup, ...] = ()
    available_to_start: tuple[str, ...] = ()

    # Capacity
    estimated_time_minutes: int = 0
    fits_capacity: bool = True
    workload_utilization: float = 0.0

    # Metadata
    rationale: str = ""
    priorities: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
```

`habits` holds both the at-risk habits (slot 1) and the daily habits (slot 4);
`contextual_habits` holds only the at-risk ones. `exercises` holds revisions and assignments —
tell them apart by `ContextualExercise.subtype` (`"revision"` / `"assignment"`).

### PathStep

```python
@dataclass(frozen=True)
class PathStep:
    ku_uid: str
    title: str
    rationale: str = ""
    prerequisites_met: bool = False
    aligns_with_goals: tuple[str, ...] = ()
    unlocks_count: int = 0
    estimated_time_minutes: int = 60
    priority_score: float = 0.0
    application_opportunities: dict[str, tuple[str, ...]] = field(default_factory=dict)
```

### LifePathAlignment

```python
@dataclass(frozen=True)
class LifePathAlignment:
    overall_score: float
    alignment_level: str  # undefined | drifting | exploring | aligned | flourishing

    knowledge_score: float
    activity_score: float
    goal_score: float
    principle_score: float
    momentum_score: float

    strengths: tuple[str, ...] = ()
    gaps: tuple[str, ...] = ()
    recommendations: tuple[str, ...] = ()

    life_path_uid: str | None = None
    life_path_milestones_completed: int = 0
    life_path_milestones_total: int = 0
    aligned_goals: tuple[str, ...] = ()
    supporting_habits: tuple[str, ...] = ()
    knowledge_gaps: tuple[str, ...] = ()
```

### CrossDomainSynergy

```python
@dataclass(frozen=True)
class CrossDomainSynergy:
    source_uid: str
    source_domain: str  # habit | knowledge | principle | pathstep
    target_uids: tuple[str, ...] = ()
    target_domain: str = ""  # goal | task | multi
    synergy_type: str = ""  # supports | builds | enables | informs | spawns
    synergy_score: float = 0.0
    rationale: str = ""
    recommendations: tuple[str, ...] = ()
```

### ScheduleAwareRecommendation

```python
@dataclass(frozen=True)
class ScheduleAwareRecommendation:
    uid: str
    entity_type: str
    recommendation_type: str  # learn | task | habit | goal | rest | reschedule
    title: str
    rationale: str

    suggested_time_slot: str = ""
    estimated_duration_minutes: int = 30
    fits_available_time: bool = True
    conflicts_with: tuple[str, ...] = ()

    schedule_fit_score: float = 0.0
    energy_match_score: float = 0.0
    priority_score: float = 0.0
    overall_score: float = 0.0

    deadline: str | None = None
    streak_at_risk: bool = False
    blocks_other_work: bool = False
    life_path_aligned: bool = False

    preparation_needed: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = ()
```

The `rest` recommendation has `uid="rest"` and `entity_type="meta"`.

### ContextualExercise

```python
@dataclass(frozen=True)
class ContextualExercise:
    uid: str
    title: str
    due_date: date | None = None
    is_overdue: bool = False
    days_until_due: int | None = None
    subtype: str = "assignment"  # assignment | revision
    blocking_kus: tuple[str, ...] = ()
    readiness_score: float = 1.0
    est_time_minutes: int = 60
```

Properties: `entity_type` (`"exercise"`), `is_urgent` (due within 3 days), `is_blocked` (any
`blocking_kus`), `is_ready` (`readiness_score >= 0.7`).

---

## Building a Context

| Call | Returns |
|------|---------|
| `await user_service.get_rich_unified_context(user_uid, min_confidence=0.7)` | `Result[RichUserContext]` — cache, else build |
| `user_service.peek_cached_context(user_uid)` | `RichUserContext \| None` — never builds |
| `await context_builder.build_rich(user_uid, min_confidence=0.7, window="30d")` | `Result[RichUserContext]` |
| `await context_builder.build(user_uid)` | `Result[UserContext]` — standard |
| `await user_service.get_user_context(user_uid)` | `Result[UserContext]` — standard |

`min_confidence` outside `0.0–1.0` and an unknown `window` token are validation failures.

In a test, construct one directly:

```python
context = RichUserContext(
    user_uid="user_alice",
    available_minutes_daily=120,
    active_task_uids=["task_abc"],
    entities_rich={
        "tasks": [{"entity": {"uid": "task_abc", "title": "Fix bug"}, "graph_context": {}}]
    },
)
```

`UserContext` is a mutable `@dataclass`, treated as read-only by convention: a change that must
outlive the context goes through the domain service.

---

## UserContext Fields the Mixins Read

Every `UserContext` field a mixin reads, taken from the mixin sources. A stub context for a
test needs the fields listed against the mixin it exercises.

| Field | Type | Read by |
|-------|------|---------|
| `active_goal_uids` | `list[str]` | life path, synergy |
| `active_habit_uids` | `list[str]` | learning, life path, synergy |
| `active_path_steps_rich` | `list[RichPathStepItem]` | daily plan |
| `active_ps_engagements` | `dict[str, Engagement]` or `None` | daily plan, synergy |
| `active_task_uids` | `list[str]` | life path, synergy |
| `available_minutes_daily` | `int` | daily plan, learning, schedule |
| `completed_goal_uids` | `set[str]` | synergy |
| `completed_task_uids` | `set[str]` | synergy |
| `core_principle_uids` | `list[str]` | life path, synergy |
| `current_energy_level` | `EnergyLevel` or `None` | schedule |
| `current_learning_focus` | `str` or `None` | learning |
| `current_workload_score` | `float` | life path, schedule |
| `daily_habits` | `list[str]` | daily plan, schedule |
| `decisions_against_principles` | `int` | life path |
| `decisions_aligned_with_principles` | `int` | life path |
| `dual_track_checkins` | `dict[str, list[dict[str, Any]]]` | perception |
| `entities_rich` | `dict[str, list[RichEntityItem]]` | momentum |
| `estimated_time_to_mastery` | `dict[str, int]` | daily plan, learning |
| `events_by_habit` | `dict[str, list[str]]` | learning |
| `goal_progress` | `dict[str, float]` | life path, schedule |
| `habit_streaks` | `dict[str, int]` | life path, synergy, schedule |
| `knowledge_checkins` | `dict[str, list[dict[str, Any]]]` | perception |
| `knowledge_mastery` | `dict[str, float]` | learning, life path, synergy |
| `latest_activity_report_period` | `str` or `None` | daily plan |
| `latest_activity_report_uid` | `str` or `None` | daily plan |
| `learning_goals` | `list[str]` | daily plan, learning, life path, synergy, schedule |
| `life_path_alignment_score` | `float` | life path |
| `life_path_milestones` | `list[str]` | life path, schedule |
| `life_path_uid` | `str` or `None` | daily plan, learning, life path |
| `mastered_knowledge_uids` | `set[str]` | learning, life path, synergy |
| `next_recommended_knowledge` | `list[str]` | learning |
| `overdue_task_uids` | `list[str]` | schedule |
| `pending_choice_uids` | `list[str]` | synergy |
| `pending_revised_exercises` | `list[PendingRevisedExerciseItem]` | daily plan |
| `preferred_time` | `TimeOfDay` | schedule |
| `prerequisites_completed` | `set[str]` | learning |
| `prerequisites_needed` | `dict[str, list[str]]` | learning, life path, synergy |
| `primary_goal_focus` | `str` or `None` | daily plan, schedule |
| `principle_alignment_by_domain` | `dict[Domain, float]` | life path |
| `principle_priorities` | `dict[str, float]` | synergy |
| `recently_mastered_uids` | `set[str]` | life path |
| `resolved_choice_uids` | `set[str]` | synergy |
| `spawned_uid_to_ps_uid` | `dict[str, str]` | life path |
| `task_priorities` | `dict[str, float]` | schedule |
| `today_event_uids` | `list[str]` | schedule |
| `today_task_uids` | `list[str]` | schedule |
| `upcoming_event_uids` | `list[str]` | learning |
| `user_uid` | `UserUID` | daily plan, learning, perception |
| `zpd_assessment` | `ZPDAssessment` or `None` | daily plan |

Read through a service, for the daily plan: `unsubmitted_exercises` and
`pending_revised_exercises` (`ExerciseService`). The daily plan also reads the length of
`pending_revised_exercises` directly.

`entities_rich` keys: the six Activity domains, `learning_paths`, `path_steps`, and `ku`. Every
item is `{"entity": {...}, "graph_context": {...}}` (`RichEntityItem`,
`core/ports/query_types.py`).

### Rich-only fields and their accessors

| Field | Strict accessor | Graceful accessor |
|-------|-----------------|-------------------|
| `tasks_by_goal` | `get_tasks_by_goal()` | `tasks_by_goal_or_empty()` |
| `habits_by_goal` | `get_habits_by_goal()` | `habits_by_goal_or_empty()` |
| `at_risk_habits` | `get_habits_needing_reinforcement()` | `at_risk_habits_or_empty()` |
| `blocked_task_uids` | `get_blocked_tasks()` | `blocked_task_uids_or_empty()` |
| `principle_guided_choice_counts` | `get_principle_guided_choice_counts()` | `principle_guided_choice_counts_or_empty()` |
| `recent_principle_aligned_choices` | `get_recent_principle_aligned_choices()` | `recent_principle_aligned_choices_or_empty()` |
| `principle_integration_score` | `get_principle_integration_score()` | — |

`get_tasks_for_goal(goal_uid)` and `get_habits_for_goal(goal_uid)` are per-goal lookups over the
first two. `at_risk_habits` is the one at-risk definition, `habit_at_risk`
(`core/models/habit/adherence.py`): an active habit overdue for its own cadence, or with adherence
under 0.5 once at least three completions were due — never the stored streak, which does not
decay. `/api/habits/analytics` and the ZPD knowledge signals call the same function.

### Context methods the mixins call

| Method | Called by | Strict |
|--------|-----------|--------|
| `get_blocked_tasks()` | schedule | yes |
| `get_habits_by_goal()` | synergy | yes |
| `get_habits_for_goal()` | learning, life path | yes |
| `get_habits_needing_reinforcement()` | life path, synergy, schedule | yes |
| `get_life_path_gaps()` | life path | no |
| `get_principle_integration_score()` | life path | yes |
| `get_ready_to_learn()` | learning, schedule | no |
| `get_tasks_for_goal()` | life path, synergy | yes |

A strict method raises `RichContextRequiredError` on a standard context.

| Method | Returns |
|--------|---------|
| `get_ready_to_learn()` | the UIDs in `next_recommended_knowledge` whose prerequisites are all in `prerequisites_completed` |
| `get_life_path_gaps()` | every UID in `knowledge_mastery` below 0.5, or `[]` without a life path. It does not filter to the life path's own knowledge. |
