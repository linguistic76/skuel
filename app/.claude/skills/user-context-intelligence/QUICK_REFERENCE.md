# UserContextIntelligence Quick Reference

## File Locations

### Package Structure

```
core/services/user/intelligence/
├── __init__.py                    # Package exports
├── core.py                        # UserContextIntelligence class
├── factory.py                     # UserContextIntelligenceFactory
├── daily_planning.py              # DailyPlanningMixin
├── learning_intelligence.py       # LearningIntelligenceMixin
├── life_path_intelligence.py      # LifePathIntelligenceMixin
├── synergy_intelligence.py        # SynergyIntelligenceMixin
└── schedule_intelligence.py       # ScheduleIntelligenceMixin

core/models/context_types.py       # Return types (LearningStep, DailyWorkPlan, etc.)
```

### Documentation

| File | Purpose |
|------|---------|
| `/docs/intelligence/USER_CONTEXT_INTELLIGENCE.md` | Full documentation |
| `/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md` | Master index |
| `/docs/decisions/ADR-021-user-context-intelligence-modularization.md` | Architecture ADR |
| `/docs/decisions/ADR-029-graphnative-service-removal.md` | GraphNative removal |

---

## Imports

### Primary Imports

```python
from core.services.user.intelligence import (
    UserContextIntelligence,
    UserContextIntelligenceFactory,
)
```

### Return Types

```python
# Via package (re-exported from core.models.context_types)
from core.services.user.intelligence import (
    LifePathAlignment,
    CrossDomainSynergy,
    LearningStep,
    DailyWorkPlan,
    ScheduleAwareRecommendation,
)

# Or import directly from their canonical location
from core.models.context_types import (
    LifePathAlignment,
    CrossDomainSynergy,
    LearningStep,
    DailyWorkPlan,
    ScheduleAwareRecommendation,
)
```

### Mixins (for testing/extension)

```python
from core.services.user.intelligence import (
    DailyPlanningMixin,
    LearningIntelligenceMixin,
    LifePathIntelligenceMixin,
    ScheduleIntelligenceMixin,
    SynergyIntelligenceMixin,
)
```

### Supporting Types

```python
from core.services.user.unified_user_context import UserContext
from core.models.context_types import (
    ContextualTask,
    ContextualHabit,
    ContextualGoal,
    ContextualKnowledge,
)
```

---

## The 12 Required Services

| # | Domain | Service Type | Attribute |
|---|--------|--------------|-----------|
| **Activity (6)** |
| 1 | Tasks | `UnifiedRelationshipService` | `self.tasks` |
| 2 | Goals | `UnifiedRelationshipService` | `self.goals` |
| 3 | Habits | `UnifiedRelationshipService` | `self.habits` |
| 4 | Events | `UnifiedRelationshipService` | `self.events` |
| 5 | Choices | `UnifiedRelationshipService` | `self.choices` |
| 6 | Principles | `UnifiedRelationshipService` | `self.principles` |
| **Curriculum (3)** |
| 7 | KU | `KuGraphService` | `self.ku` |
| 8 | LS | `UnifiedRelationshipService` | `self.ls` |
| 9 | LP | `UnifiedRelationshipService` | `self.lp` |
| **Processing (3)** |
| 10 | Submissions | `SubmissionsRelationshipService` | `self.submissions` |
| 11 | Feedback | `FeedbackRelationshipService` | `self.feedback` |
| 12 | Analytics | `AnalyticsRelationshipService` | `self.analytics` |
| **Temporal (1)** |
| 13 | Calendar | `CalendarService` | `self.calendar` |

---

## The 8 Core Methods

### Method Signatures

```python
# Method 1: Learning - What to learn next
async def get_optimal_next_learning_steps(
    self,
    max_steps: int = 5,
    consider_goals: bool = True,
    consider_capacity: bool = True,
) -> Result[list[LearningStep]]: ...

# Method 2: Learning - Critical path to life path
async def get_learning_path_critical_path(self) -> Result[list[str]]: ...

# Method 3: Learning - Application opportunities
async def get_knowledge_application_opportunities(
    self, ku_uid: str
) -> Result[dict[str, list[str]]]: ...

# Method 4: Learning - Unblocking priority
async def get_unblocking_priority_order(
    self
) -> Result[list[tuple[str, int]]]: ...

# Method 5: Daily - THE FLAGSHIP
async def get_ready_to_work_on_today(
    self,
    prioritize_life_path: bool = True,
    respect_capacity: bool = True,
) -> Result[DailyWorkPlan]: ...

# Method 6: Synergy - Cross-domain synergies
async def get_cross_domain_synergies(
    self
) -> Result[list[CrossDomainSynergy]]: ...

# Method 7: Life Path - Alignment scoring
async def calculate_life_path_alignment(
    self
) -> Result[LifePathAlignment]: ...

# Method 8: Schedule - Schedule-aware recommendations
async def get_schedule_aware_recommendations(
    self, time_slot: str = "now"
) -> Result[list[ScheduleAwareRecommendation]]: ...
```

---

## The 5 Return Types

### LearningStep

```python
@dataclass
class LearningStep:
    ku_uid: str
    title: str
    rationale: str
    prerequisites_met: bool
    aligns_with_goals: list[str]
    unlocks_count: int
    estimated_time_minutes: int
    priority_score: float  # 0.0-1.0
    application_opportunities: dict[str, list[str]]
```

### DailyWorkPlan

```python
@dataclass
class DailyWorkPlan:
    # UIDs by domain
    learning: list[str]
    tasks: list[str]
    habits: list[str]
    events: list[str]
    goals: list[str]
    choices: list[str]
    principles: list[str]

    # Contextual items
    contextual_tasks: list[ContextualTask]
    contextual_habits: list[ContextualHabit]
    contextual_goals: list[ContextualGoal]
    contextual_knowledge: list[ContextualKnowledge]

    # Metadata
    estimated_time_minutes: int = 0
    fits_capacity: bool = True
    workload_utilization: float = 0.0
    rationale: str = ""
    priorities: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
```

### LifePathAlignment

```python
@dataclass
class LifePathAlignment:
    overall_score: float           # 0.0-1.0
    alignment_level: str           # drifting|exploring|aligned|flourishing

    # Dimension scores
    knowledge_score: float
    activity_score: float
    goal_score: float
    principle_score: float
    momentum_score: float

    # Insights
    strengths: list[str]
    gaps: list[str]
    recommendations: list[str]

    # Supporting data
    life_path_uid: str | None
    life_path_milestones_completed: int
    life_path_milestones_total: int
    aligned_goals: list[str]
    supporting_habits: list[str]
    knowledge_gaps: list[str]
```

### CrossDomainSynergy

```python
@dataclass
class CrossDomainSynergy:
    source_uid: str
    source_domain: str
    target_uids: list[str]
    target_domain: str
    synergy_type: str     # supports|enables|builds|informs
    synergy_score: float  # 0.0-1.0
    rationale: str
    recommendations: list[str]
```

### ScheduleAwareRecommendation

```python
@dataclass
class ScheduleAwareRecommendation:
    uid: str
    entity_type: str       # task|habit|goal|knowledge|event
    recommendation_type: str  # learn|task|habit|goal|rest|reschedule
    title: str
    rationale: str

    # Schedule context
    suggested_time_slot: str  # morning|afternoon|evening|now|later
    estimated_duration_minutes: int = 30
    fits_available_time: bool = True
    conflicts_with: list[str] = field(default_factory=list)

    # Scoring
    schedule_fit_score: float = 0.0
    energy_match_score: float = 0.0
    priority_score: float = 0.0
    overall_score: float = 0.0

    # Context
    deadline: str | None = None
    streak_at_risk: bool = False
    blocks_other_work: bool = False
    life_path_aligned: bool = False

    # Guidance
    preparation_needed: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
```

---

## Factory Pattern

### Factory Signature

```python
class UserContextIntelligenceFactory:
    def __init__(
        self,
        # Activity Domains (6)
        tasks: UnifiedRelationshipService,
        goals: UnifiedRelationshipService,
        habits: UnifiedRelationshipService,
        events: UnifiedRelationshipService,
        choices: UnifiedRelationshipService,
        principles: UnifiedRelationshipService,
        # Curriculum Domains (3)
        ku: KuGraphService,
        ls: UnifiedRelationshipService,
        lp: UnifiedRelationshipService,
        # Processing Domains (3)
        submissions: SubmissionsRelationshipService,
        feedback: FeedbackRelationshipService,
        analytics: AnalyticsRelationshipService,
        # Temporal Domain (1)
        calendar: CalendarService,
    ) -> None: ...

    def create(
        self, context: UserContext
    ) -> UserContextIntelligence: ...
```

### Usage Pattern

```python
# At bootstrap
factory = UserContextIntelligenceFactory(
    tasks=tasks_service.relationships,
    # ... 12 more services
)
services.context_intelligence = factory

# At runtime
context = await user_service.get_user_context(user_uid)
intelligence = factory.create(context)
plan = await intelligence.get_ready_to_work_on_today()
```

---

## Key UserContext Fields

| Field | Type | Purpose |
|-------|------|---------|
| `user_uid` | `str` | User identifier |
| `available_minutes_daily` | `int` | Daily capacity |
| `current_energy_level` | `float` | Energy 0.0-1.0 |
| `current_workload_score` | `float` | Workload 0.0-1.0 |
| `life_path_uid` | `str \| None` | Life path alignment |
| `primary_goal_focus` | `str \| None` | Current goal focus |
| `daily_habits` | `list[str]` | Daily habit UIDs |
| `active_habit_uids` | `list[str]` | All active habits |
| `upcoming_event_uids` | `list[str]` | Upcoming events |
| `learning_goals` | `list[str]` | Learning goal UIDs |
| `prerequisites_completed` | `set[str]` | Completed prereqs |
| `prerequisites_needed` | `dict[str, list[str]]` | Prereq mapping |
| `mastered_knowledge_uids` | `set[str]` | Mastered KUs |
| `estimated_time_to_mastery` | `dict[str, int]` | Time estimates |
| `knowledge_mastery` | `dict[str, float]` | Mastery levels |
| `next_recommended_knowledge` | `list[str]` | Recommendations |
| `habits_by_goal` | `dict[str, list[str]]` | Goal→Habits |
| `events_by_habit` | `dict[str, list[str]]` | Habit→Events |

---

## Common Usage Patterns

### Pattern 1: Daily Planning Route

```python
@rt("/api/daily-plan")
@boundary_handler()
async def get_daily_plan(request):
    user_uid = require_authenticated_user(request)
    context = await services.user.get_user_context(user_uid)
    intelligence = services.context_intelligence.create(context)
    return await intelligence.get_ready_to_work_on_today()
```

### Pattern 2: Learning Recommendations

```python
async def get_learning_recommendations(user_uid: str) -> list[LearningStep]:
    context = await user_service.get_user_context(user_uid)
    intelligence = factory.create(context)

    result = await intelligence.get_optimal_next_learning_steps(max_steps=5)
    return result.value if result.is_ok else []
```

### Pattern 3: Life Path Dashboard

```python
async def get_life_path_dashboard(user_uid: str) -> dict:
    context = await user_service.get_user_context(user_uid)
    intelligence = factory.create(context)

    alignment = await intelligence.calculate_life_path_alignment()
    synergies = await intelligence.get_cross_domain_synergies()
    critical_path = await intelligence.get_learning_path_critical_path()

    return {
        "alignment": alignment.value if alignment.is_ok else None,
        "synergies": synergies.value if synergies.is_ok else [],
        "critical_path": critical_path.value if critical_path.is_ok else [],
    }
```
