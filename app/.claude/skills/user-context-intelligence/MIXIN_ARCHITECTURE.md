# Mixin Architecture

## Overview

`UserContextIntelligence` uses a **mixin composition pattern** (ADR-021) instead of inheriting from `BaseIntelligenceService`. This allows organizing the 8 core methods into focused, cohesive units.

```python
class UserContextIntelligence(
    LearningIntelligenceMixin,      # Methods 1-4
    LifePathIntelligenceMixin,      # Method 7
    SynergyIntelligenceMixin,       # Method 6
    ScheduleIntelligenceMixin,      # Method 8
    TemporalMomentumMixin,          # Momentum signals (entities_rich analysis)
    DailyPlanningMixin,             # Method 5 (THE FLAGSHIP)
):
    """Composed from 6 specialized mixins."""
```

---

## Why Mixins Instead of BaseIntelligenceService?

| Aspect | BaseIntelligenceService | Mixin Composition |
|--------|------------------------|-------------------|
| **Focus** | Single domain entities | Cross-domain synthesis |
| **Backend** | Single domain backend | 13 domain services |
| **Context** | Entity-focused | User state (~250 fields) |
| **Methods** | CRUD + intelligence | 8 specialized methods |
| **Testing** | Mock single backend | Mock context + services |

`UserContextIntelligence` doesn't manage entities - it synthesizes across ALL domains. Mixins allow organizing methods by their conceptual purpose rather than forcing a single-domain pattern.

---

## The 6 Mixins

### 1. LearningIntelligenceMixin

**File:** `learning_intelligence.py` (~470 lines)

**Methods:**
1. `get_optimal_next_learning_steps()` - What should I learn next?
2. `get_learning_path_critical_path()` - Fastest route to life path?
3. `get_knowledge_application_opportunities()` - Where can I apply this?
4. `get_unblocking_priority_order()` - What unlocks the most?

**Required Attributes:**
```python
class LearningIntelligenceMixin:
    context: UserContext      # User state
    tasks: Any                # UnifiedRelationshipService
    ku: Any                   # KuGraphService
    vector_search: Any        # Neo4jVectorSearchService (optional, may be None)
    zpd_service: Any          # ZPDOperations (optional, may be None — FULL tier only)
```

**Key Logic:**
- ZPD path (when `zpd_service` set): ranks by proximal zone readiness scores
- Fallback path: ranks by goal alignment, unblocking potential, life path alignment, capacity
- Filters by user capacity (available time)
- Finds application opportunities across tasks, habits, goals, events

```python
async def get_optimal_next_learning_steps(
    self,
    max_steps: int = 5,
    consider_goals: bool = True,
    consider_capacity: bool = True,
) -> Result[list[LearningStep]]:
    """
    Priority Path (when zpd_service is set — FULL tier):
    - ZPD proximal zone ranking: priority_score = readiness_score × (0.7 + 0.3 × behavioral_readiness)
    - Graceful degradation: falls through to activity-based if ZPD assessment is empty

    Fallback Ranking Factors (activity-based — always available):
    - Prerequisites met (ready to learn)
    - Goal alignment (30% weight)
    - Unblocking potential (25% weight)
    - Life path alignment (25% weight)
    - Capacity fit (20% weight)
    """
```

---

### 2. LifePathIntelligenceMixin

**File:** `life_path_intelligence.py` (~150 lines)

**Methods:**
7. `calculate_life_path_alignment()` - Life path alignment scoring

**Required Attributes:**
```python
class LifePathIntelligenceMixin:
    context: UserContext
    goals: Any      # UnifiedRelationshipService
    habits: Any     # UnifiedRelationshipService
    ku: Any         # KuGraphService
```

**Key Logic:**
- Calculates 5-dimension alignment score:
  - Knowledge (25%): Mastery of life path knowledge
  - Activity (25%): Tasks/habits supporting life path
  - Goal (20%): Goals contributing to life path
  - Principle (15%): Values supporting life path
  - Momentum (15%): Recent activity trend

```python
async def calculate_life_path_alignment(self) -> Result[LifePathAlignment]:
    """
    Alignment Levels:
    - 0.9+: Flourishing (fully integrated)
    - 0.7-0.9: Aligned (actively living the path)
    - 0.4-0.7: Exploring (some alignment)
    - <0.4: Drifting (significant misalignment)
    """
```

---

### 3. SynergyIntelligenceMixin

**File:** `synergy_intelligence.py` (~200 lines)

**Methods:**
6. `get_cross_domain_synergies()` - Cross-domain synergy detection

**Required Attributes:**
```python
class SynergyIntelligenceMixin:
    context: UserContext
    habits: Any     # UnifiedRelationshipService
    goals: Any      # UnifiedRelationshipService
    tasks: Any      # UnifiedRelationshipService
    ku: Any         # KuGraphService
```

**Key Logic:**
- Detects synergies between entities across domains
- Calculates synergy strength (0.0-1.0)
- Identifies hub entities with high leverage

```python
async def get_cross_domain_synergies(self) -> Result[list[CrossDomainSynergy]]:
    """
    Synergy Types:
    - Habit->Goal: "Morning meditation" supports multiple goals
    - Task->Habit: "Write entry" builds "Daily journaling"
    - Knowledge->Task: "Python async" enables multiple tasks
    - Principle->Choice: "Growth mindset" informs decisions

    Synergy Score:
    - 0.0-0.3: Weak (single connection)
    - 0.4-0.6: Moderate (multiple connections)
    - 0.7-1.0: Strong (hub entity)
    """
```

---

### 4. ScheduleIntelligenceMixin

**File:** `schedule_intelligence.py` (~180 lines)

**Methods:**
8. `get_schedule_aware_recommendations()` - Schedule-aware recommendations

**Required Attributes:**
```python
class ScheduleIntelligenceMixin:
    context: UserContext
    calendar: Any   # CalendarService
    events: Any     # UnifiedRelationshipService
    tasks: Any      # UnifiedRelationshipService
    habits: Any     # UnifiedRelationshipService
```

**Key Logic:**
- Considers current events and scheduled activities
- Matches recommendations to energy levels
- Identifies conflicts and suggests alternatives

```python
async def get_schedule_aware_recommendations(
    self, time_slot: str = "now"
) -> Result[list[ScheduleAwareRecommendation]]:
    """
    Recommendation Types:
    - "learn": Knowledge unit to study
    - "task": Task to complete
    - "habit": Habit to maintain
    - "goal": Goal to advance
    - "rest": Rest (capacity exceeded)
    - "reschedule": Reschedule (conflicts)

    Time Slots: morning, afternoon, evening, now, later
    """
```

---

### 5. TemporalMomentumMixin

**File:** `temporal_momentum.py`

**Methods:**
- `compute_momentum_signals()` — Analyzes `context.entities_rich` (all 9 keys)
- `_momentum_warnings()` — Formats neglected-domain + habit-consistency warnings
- `_momentum_rationale()` — Returns phase-based rationale clause

**Required Attributes:**
```python
class TemporalMomentumMixin:
    context: UserContext  # needs context.entities_rich populated (rich context only)
```

**Key Logic:**
- Computes completion velocity per activity domain (0.0–1.0)
- Detects neglected domains (zero window activity)
- Computes habit consistency from `completion_rate` field
- Derives phase: `"accelerating"` (≥0.6), `"steady"` (≥0.3), `"decelerating"` (<0.3)
- Pure Python — no I/O, no await. Returns empty signals when `entities_rich` is empty (standard context)

```python
def compute_momentum_signals(self) -> dict[str, Any]:
    """
    Returns:
        velocities: {domain: 0.0-1.0}
        neglected: [domain, ...]
        habit_consistency: float
        phase: "accelerating" | "steady" | "decelerating" | "unknown"
    """
```

---

### 6. DailyPlanningMixin

**File:** `daily_planning.py` (~256 lines)

**Methods:**
5. **`get_ready_to_work_on_today()`** - THE FLAGSHIP METHOD

**Required Attributes:**
```python
class DailyPlanningMixin:
    context: UserContext
    tasks: Any          # UnifiedRelationshipService
    habits: Any         # UnifiedRelationshipService
    goals: Any          # UnifiedRelationshipService
    events: Any         # UnifiedRelationshipService
    choices: Any        # UnifiedRelationshipService
    principles: Any     # UnifiedRelationshipService
    ku: Any             # KuGraphService
    feedback: Any       # FeedbackRelationshipService (exercises now via context.unsubmitted_exercises)
```

**Note:** The 6 domain-specific planning methods this mixin calls (`get_at_risk_habits_for_user`, `get_upcoming_events_for_user`, `get_actionable_tasks_for_user`, `get_advancing_goals_for_user`, `get_pending_decisions_for_user`, `get_aligned_principles_for_user`) are provided by `_domain_planning_mixin.py` via the `UnifiedRelationshipService` MRO — they are not on the `UnifiedRelationshipService` shell itself.

Each of these 6 methods:
- Accepts a **domain-specific protocol slice** (`HabitAwareness`, `TaskAwareness`, etc.), not `UserContext`
- Returns `Result.fail()` immediately if `context.is_rich_context` is `False` (standard `build()` context)
- Uses `context.get_rich_entities(domain, filter_uids)` for entity extraction instead of manual loop

**Key Logic:**
- Synthesizes 10 entity domains into one daily plan
- Respects user capacity and energy
- Generates warnings for overload or missed learning

```python
async def get_ready_to_work_on_today(
    self,
    prioritize_life_path: bool = True,
    respect_capacity: bool = True,
) -> Result[DailyWorkPlan]:
    """
    Priority Order:
    1. At-risk habits (maintain streaks)
    2. Today's events (can't reschedule)
    2.5. Unsubmitted exercises (from context.unsubmitted_exercises — no extra query)
    3. Overdue and actionable tasks
    4. Daily habits (consistency)
    5. Learning (if capacity allows)
    6. Advancing goals
    7. Pending decisions (high priority)
    8. Aligned principles (for focus)
    """
```

---

## Mixin Composition Flow

```
UserContextIntelligence.__init__()
         │
         ├── Store context and 13 services
         │
         ▼
     Mixins provide methods
         │
         ├── LearningIntelligenceMixin: 4 methods
         ├── LifePathIntelligenceMixin: 1 method
         ├── SynergyIntelligenceMixin: 1 method
         ├── ScheduleIntelligenceMixin: 1 method
         ├── TemporalMomentumMixin: momentum signals (entities_rich analysis)
         └── DailyPlanningMixin: 1 method (calls TemporalMomentumMixin)
         │
         ▼
     Methods access self.context, self.tasks, self.ku, etc.
```

---

## Mixin Dependencies

### Service Dependencies by Mixin

| Mixin | Required Attributes |
|-------|---------------------|
| `LearningIntelligenceMixin` | context, tasks, ku |
| `LifePathIntelligenceMixin` | context, goals, habits, ku |
| `SynergyIntelligenceMixin` | context, habits, goals, tasks, ku |
| `ScheduleIntelligenceMixin` | context, calendar, events, tasks, habits |
| `TemporalMomentumMixin` | context (needs `entities_rich` — rich context only; returns empty signals otherwise) |
| `DailyPlanningMixin` | context, tasks, habits, goals, events, choices, principles, ku, feedback |

### All Services Required

The main class requires ALL 13 services because `DailyPlanningMixin` synthesizes all domains:

```python
class UserContextIntelligence(...):
    def __init__(
        self,
        context: UserContext,
        # Activity Domains (5) + Events (Scheduling/Integration)
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
        # Optional
        vector_search: Any = None,
    ):
        # Validate all 13 required services present
        required = {
            "context": context,
            "tasks": tasks,
            # ... all 13
        }
        missing = [name for name, svc in required.items() if svc is None]
        if missing:
            raise ValueError(f"Missing: {', '.join(missing)}")
```

---

## Testing Mixins

### Testing Individual Mixins

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

from core.services.user.intelligence import LearningIntelligenceMixin


class MockLearningService(LearningIntelligenceMixin):
    """Test harness for mixin."""

    def __init__(self, context, tasks, ku):
        self.context = context
        self.tasks = tasks
        self.ku = ku


@pytest.fixture
def learning_service():
    context = MagicMock()
    context.learning_goals = ["goal-1"]
    context.prerequisites_completed = {"ku-1"}
    context.prerequisites_needed = {"goal-1": ["ku-2"]}

    tasks = AsyncMock()
    ku = AsyncMock()

    return MockLearningService(context, tasks, ku)


async def test_get_optimal_next_learning_steps(learning_service):
    learning_service.ku.get_ready_to_learn_for_user.return_value = Result.ok([
        MagicMock(uid="ku-2", title="Next KU", prerequisites_met=True, priority_score=0.8)
    ])

    result = await learning_service.get_optimal_next_learning_steps(max_steps=3)

    assert result.is_ok
    assert len(result.value) >= 1
```

### Testing Full Integration

```python
async def test_full_daily_planning():
    # Create mock context with all required fields
    context = create_mock_context()

    # Create mock services
    services = create_mock_services()

    # Create factory and intelligence
    factory = UserContextIntelligenceFactory(**services)
    intelligence = factory.create(context)

    # Test flagship method
    result = await intelligence.get_ready_to_work_on_today()

    assert result.is_ok
    plan = result.value
    assert isinstance(plan, DailyWorkPlan)
    assert plan.fits_capacity
```

---

## Extending with New Mixins

### Step 1: Create New Mixin

```python
# core/services/user/intelligence/focus_intelligence.py
class FocusIntelligenceMixin:
    """Mixin for focus and deep work recommendations."""

    context: UserContext
    tasks: Any
    calendar: Any

    async def get_deep_work_blocks(self) -> Result[list[dict]]:
        """Find optimal blocks for deep work."""
        # Implementation
        pass

    async def get_focus_recommendations(self) -> Result[dict]:
        """Get focus recommendations based on current state."""
        pass
```

### Step 2: Add to Main Class

```python
# core/services/user/intelligence/core.py
from core.services.user.intelligence.focus_intelligence import FocusIntelligenceMixin

class UserContextIntelligence(
    LearningIntelligenceMixin,
    LifePathIntelligenceMixin,
    SynergyIntelligenceMixin,
    ScheduleIntelligenceMixin,
    TemporalMomentumMixin,
    DailyPlanningMixin,
    FocusIntelligenceMixin,  # New mixin
):
    pass
```

### Step 3: Update Package Exports

```python
# core/services/user/intelligence/__init__.py
from core.services.user.intelligence.focus_intelligence import FocusIntelligenceMixin

__all__ = [
    # ... existing exports
    "FocusIntelligenceMixin",
]
```

---

## Anti-Patterns

### Don't Override Mixin Methods in Main Class

```python
# WRONG - overriding defeats mixin purpose
class UserContextIntelligence(...):
    async def get_optimal_next_learning_steps(self, ...):
        # Custom implementation breaks composition
        pass

# CORRECT - extend in a new mixin
class EnhancedLearningMixin(LearningIntelligenceMixin):
    async def get_optimal_next_learning_steps(self, ...):
        base_result = await super().get_optimal_next_learning_steps(...)
        # Enhance result
        return enhanced_result
```

### Don't Add Instance State to Mixins

```python
# WRONG - mixins shouldn't own state
class BadMixin:
    def __init__(self):
        self._cache = {}  # State in mixin!

# CORRECT - use context for state
class GoodMixin:
    context: UserContext  # State in context

    async def method(self):
        # Use self.context for state
        pass
```

### Don't Hardcode Service Dependencies

```python
# WRONG - concrete service types in mixin
class BadMixin:
    tasks: TasksRelationshipService  # Concrete type

# CORRECT - use Any with documented expectations
class GoodMixin:
    tasks: Any  # TasksRelationshipService (documented)
```
