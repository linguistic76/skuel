# Domain Intelligence Models - Quick Reference

**All domains now have persistent intelligence entities that learn from user behavior.**

## Import Patterns

```python
# Task Intelligence
from core.models.task import TaskIntelligence, TaskCompletionContext, EnergyLevel

# Event Intelligence
from core.models.event import EventIntelligence, EventParticipationContext, EnergyImpact

# Habit Intelligence
from core.models.habit import HabitIntelligence, HabitCompletionContext

# Finance Intelligence
from core.models.finance import FinancialHealthScore, SpendingVelocity, FinancialHealthTier

# Goal Intelligence
from core.models.goal import GoalIntelligence, GoalAchievementContext, MotivationLevel

# Knowledge Intelligence (original pattern)
from core.models.knowledge.knowledge_intelligence import KnowledgeMastery, MasteryLevel
```

## Domain Intelligence Summary

### Tasks - Completion & Scheduling Intelligence
```python
task_intel = TaskIntelligence(
    optimal_scheduling_patterns={...},  # Best times for task types
    duration_estimation_accuracy={...}, # How accurate user estimates are
    procrastination_trigger_analysis={...},  # What causes delays
    energy_task_matching={...}  # Energy level requirements
)

# Business logic methods
task_intel.get_optimal_scheduling_window()
task_intel.predict_completion_time()
task_intel.assess_procrastination_risk()
```

### Events - Participation & Energy Intelligence
```python
event_intel = EventIntelligence(
    attendance_pattern_analysis={...},  # Attendance reliability
    energy_impact_patterns={...},  # How events affect energy
    preparation_effectiveness={...},  # Preparation quality
    optimal_event_timing={...}  # Best times for event types
)

# Business logic methods
event_intel.predict_attendance_likelihood()
event_intel.assess_energy_impact()
event_intel.recommend_preparation_strategy()
```

### Habits - Streak & Behavior Intelligence
```python
habit_intel = HabitIntelligence(
    streak_pattern_analysis={...},  # Streak patterns
    optimal_completion_window={...},  # Best completion times
    failure_trigger_detection={...},  # What breaks streaks
    motivation_effectiveness={...}  # What motivates completion
)

# Business logic methods
habit_intel.predict_streak_continuation()
habit_intel.assess_completion_difficulty()
habit_intel.recommend_optimal_timing()
```

### Finance - Spending & Budget Intelligence
```python
fin_health = FinancialHealthScore(
    overall_health=FinancialHealthTier.GOOD,
    budget_adherence_rate=0.85,
    savings_rate=0.15,
    spending_pattern=SpendingPattern.VALUE_FOCUSED,
    emergency_fund_months=3.5
)

# Business logic methods
fin_health.is_healthy()
fin_health.needs_immediate_attention()
fin_health.get_health_recommendations()
```

### Goals - Achievement & Motivation Intelligence
```python
goal_intel = GoalIntelligence(
    achievement_pattern_analysis={...},  # Success patterns
    motivation_level_tracking={...},  # Motivation over time
    obstacle_identification={...},  # Common blockers
    progress_velocity_patterns={...}  # Progress speed
)

# Business logic methods
goal_intel.predict_achievement_likelihood()
goal_intel.assess_motivation_sustainability()
goal_intel.recommend_intervention_strategy()
```

## Common Patterns

### 1. All Intelligence Entities Are Frozen

```python
@dataclass(frozen=True)
class DomainIntelligence:
    """Immutable intelligence entity."""
    uid: str
    user_uid: str
    # ... intelligence fields ...
    created_at: datetime
    updated_at: datetime
```

### 2. All Have Business Logic Methods

```python
class DomainIntelligence:
    def is_current_intelligence(self) -> bool:
        """Check if intelligence is current (not stale)."""

    def get_recommendations(self) -> List[Recommendation]:
        """Generate actionable recommendations."""

    def assess_performance(self) -> PerformanceScore:
        """Assess current performance against patterns."""
```

### 3. All Track Temporal Evolution

```python
class DomainIntelligence:
    created_at: datetime  # When intelligence tracking started
    updated_at: datetime  # When last updated
    last_analyzed: datetime  # When patterns last analyzed
    analysis_period_days: int  # Days of data in analysis
```

### 4. All Have Factory Functions

```python
def create_task_intelligence(user_uid: str, task_category: str) -> TaskIntelligence:
    """Create initial intelligence with sensible defaults."""
    return TaskIntelligence(
        uid=f"task_intel_{user_uid}_{task_category}",
        user_uid=user_uid,
        # ... defaults ...
    )
```

## Usage in Services

### Intelligence Service Pattern

```python
class DomainIntelligenceService:
    """Service for managing domain intelligence."""

    async def get_intelligence(self, user_uid: str, context: str) -> Result[DomainIntelligence]:
        """Retrieve or create intelligence for user/context."""

    async def update_intelligence(self, intel: DomainIntelligence, event: DomainEvent) -> Result[DomainIntelligence]:
        """Update intelligence based on new event."""

    async def get_recommendations(self, intel: DomainIntelligence) -> Result[List[Recommendation]]:
        """Generate recommendations from intelligence."""
```

### Cross-Domain Intelligence Queries

```python
# Example: Task completion influenced by knowledge mastery
task_intel = await task_intelligence_service.get_intelligence(user_uid, "coding")
knowledge_mastery = await knowledge_service.get_mastery(user_uid, "ku.python.async")

# Combine intelligence for better recommendations
if knowledge_mastery.mastery_level == MasteryLevel.EXPERT:
    # Adjust task duration estimates down
    estimated_time = task_intel.average_duration * 0.8
```

## File Locations

```
/core/models/
├── task/task_intelligence.py         # Task intelligence entities
├── event/event_intelligence.py       # Event intelligence entities
├── habit/habit_intelligence.py       # Habit intelligence entities
├── finance/finance_intelligence.py   # Finance intelligence entities
├── goal/goal_intelligence.py         # Goal intelligence entities
└── knowledge/knowledge_intelligence.py  # Knowledge intelligence (original)
```

## Design Principles

1. **Persistent** - Intelligence is stored, not recalculated each time
2. **Learning** - Improves over time with more user data
3. **Immutable** - Frozen dataclasses prevent accidental mutation
4. **Domain-Driven** - Business logic methods on entities
5. **Consistent** - Same pattern across all domains

## Benefits

- **Adaptive** - Recommendations improve with usage
- **Personalized** - User-specific patterns
- **Predictive** - Forecast behavior and outcomes
- **Actionable** - Generate concrete recommendations
- **Cross-Domain** - Intelligence can be combined

## Next Steps

Phase 3 will create a `GraphIntelligenceService` to:
- Aggregate intelligence across domains
- Provide cross-domain insights
- Enable relationship-based intelligence
- Power holistic user recommendations
