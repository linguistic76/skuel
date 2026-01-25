# UserContextIntelligence - Central Intelligence Hub

## Overview

**Architecture:** Modular package with mixin composition (NOT BaseAnalyticsService)
**Location:** `/core/services/user/intelligence/` (package, ~3,124 lines total)
**Package Name:** `core.services.user.intelligence`
**Last Updated:** January 2026 (ADR-021 modular decomposition)

---

## Purpose

UserContextIntelligence is THE central intelligence hub answering: **"What should I work on next?"**

This service synthesizes user state (UserContext ~240 fields) with complete graph intelligence (13 domain services) to provide actionable daily planning, learning recommendations, and life path alignment insights.

**Core Value Proposition:**
- Combines user state (UserContext) with graph intelligence (13 domain services)
- Answers "What should I work on?" across all 14 domains
- Provides schedule-aware, capacity-respecting recommendations
- Measures life path alignment across 5 dimensions

**Key Difference from Domain Intelligence:**
- Domain intelligence services (TasksIntelligenceService, GoalsIntelligenceService, etc.) analyze SINGLE domains
- UserContextIntelligence synthesizes ACROSS ALL domains for holistic planning
- Uses mixin architecture (NOT BaseAnalyticsService pattern)

---

## Modular Package Architecture

**Philosophy:** One Path Forward (ADR-021)

The service is decomposed into a modular package using mixin composition. Total ~3,124 lines across 10 files:

```
core/services/user/intelligence/
├── __init__.py                   (95 lines)   - Package exports
├── types.py                      (205 lines)  - Data classes (return types)
├── learning_intelligence.py      (445 lines)  - LearningIntelligenceMixin (Methods 1-4)
├── life_path_intelligence.py     (429 lines)  - LifePathIntelligenceMixin (Method 7)
├── synergy_intelligence.py       (382 lines)  - SynergyIntelligenceMixin (Method 6)
├── schedule_intelligence.py      (469 lines)  - ScheduleIntelligenceMixin (Method 8)
├── daily_planning.py             (254 lines)  - DailyPlanningMixin (Method 5 - THE FLAGSHIP)
├── graph_native.py               (366 lines)  - GraphNativeMixin (context-based methods)
├── core.py                       (245 lines)  - UserContextIntelligence (composes mixins)
└── factory.py                    (234 lines)  - UserContextIntelligenceFactory
```

**Import:**
```python
# Primary import
from core.services.user.intelligence import (
    UserContextIntelligence,
    UserContextIntelligenceFactory,
)

# Data types
from core.services.user.intelligence import (
    LifePathAlignment,
    CrossDomainSynergy,
    LearningStep,
    DailyWorkPlan,
    ScheduleAwareRecommendation,
)

# Mixins (advanced usage/testing)
from core.services.user.intelligence import (
    LearningIntelligenceMixin,
    DailyPlanningMixin,
    SynergyIntelligenceMixin,
    LifePathIntelligenceMixin,
    ScheduleIntelligenceMixin,
    GraphNativeMixin,
)
```

---

## The 8 Flagship Methods

UserContextIntelligence provides 8 core methods across 5 mixins:

| # | Method | Mixin | Question Answered |
|---|--------|-------|-------------------|
| 1 | `get_optimal_next_learning_steps()` | LearningIntelligenceMixin | What should I learn next? |
| 2 | `get_learning_path_critical_path()` | LearningIntelligenceMixin | Fastest route to life path? |
| 3 | `get_knowledge_application_opportunities()` | LearningIntelligenceMixin | Where can I apply this knowledge? |
| 4 | `get_unblocking_priority_order()` | LearningIntelligenceMixin | What unlocks the most? |
| 5 | `get_ready_to_work_on_today()` | DailyPlanningMixin | **THE FLAGSHIP** - What's optimal for TODAY? |
| 6 | `get_cross_domain_synergies()` | SynergyIntelligenceMixin | Which entities create synergy? |
| 7 | `calculate_life_path_alignment()` | LifePathIntelligenceMixin | Am I living my life path? |
| 8 | `get_schedule_aware_recommendations()` | ScheduleIntelligenceMixin | What fits my schedule right now? |

---

## The 13 Required Domain Services

**Philosophy:** "SKUEL runs at full capacity or not at all"

UserContextIntelligence requires ALL 13 domain services because each contributes unique intelligence:

### Activity Domains (6) - All use UnifiedRelationshipService

| Service | Purpose | Implementation |
|---------|---------|----------------|
| **tasks** | What can I do now? | `tasks_service.relationships` (UnifiedRelationshipService) |
| **goals** | What goals need attention? | `goals_service.relationships` (UnifiedRelationshipService) |
| **habits** | What streaks are at risk? | `habits_service.relationships` (UnifiedRelationshipService) |
| **events** | What's scheduled? | `events_service.relationships` (UnifiedRelationshipService) |
| **choices** | What decisions await? | `choices_service.relationships` (UnifiedRelationshipService) |
| **principles** | What values guide this? | `principles_service.relationships` (UnifiedRelationshipService) |

### Curriculum Domains (3) - LS/LP unified in January 2026

| Service | Purpose | Implementation |
|---------|---------|----------------|
| **ku** | What knowledge is ready? | `ku_service` (KuGraphService) |
| **ls** | Learning step relationships | `ls_service.relationships` (UnifiedRelationshipService) |
| **lp** | Critical path to life path | `lp_service.relationships` (UnifiedRelationshipService) |

**January 2026 Consolidation:**
- `LsRelationshipService` DELETED → LS now uses `UnifiedRelationshipService` with LS domain config
- `LpRelationshipService` DELETED → LP now uses `UnifiedRelationshipService` with LP domain config
- All curriculum relationships now use the same unified service pattern as Activity domains

### Processing Domains (3)

| Service | Purpose | Implementation |
|---------|---------|----------------|
| **assignments** | Student submissions | AssignmentRelationshipService |
| **journals** | Reflection (fire in the engine) | JournalRelationshipService |
| **reports** | System feedback (report cards) | ReportRelationshipService |

### Temporal Domain (1)

| Service | Purpose | Implementation |
|---------|---------|----------------|
| **calendar** | Schedule-aware intelligence | CalendarService |

### Factory Pattern

**Location:** `/core/services/user/intelligence/factory.py` (lines 94-167)

```python
class UserContextIntelligenceFactory:
    def __init__(
        self,
        # Activity Domains (6) - All UnifiedRelationshipService with domain configs
        tasks: UnifiedRelationshipService,
        goals: UnifiedRelationshipService,
        habits: UnifiedRelationshipService,
        events: UnifiedRelationshipService,
        choices: UnifiedRelationshipService,
        principles: UnifiedRelationshipService,
        # Curriculum Domains (3)
        ku: KuGraphService,
        ls: UnifiedRelationshipService,  # January 2026: Unified
        lp: UnifiedRelationshipService,  # January 2026: Unified
        # Processing Domains (3)
        assignments: AssignmentRelationshipService,
        journals: JournalRelationshipService,
        reports: ReportRelationshipService,
        # Temporal Domain (1)
        calendar: CalendarService,
    ) -> None:
        # Fail-fast validation: ALL 13 services REQUIRED
        required = {
            "tasks": tasks, "goals": goals, "habits": habits,
            "events": events, "choices": choices, "principles": principles,
            "ku": ku, "ls": ls, "lp": lp,
            "assignments": assignments, "journals": journals, "reports": reports,
            "calendar": calendar,
        }
        missing = [name for name, service in required.items() if service is None]
        if missing:
            raise ValueError(
                f"UserContextIntelligenceFactory requires all 13 domain services. "
                f"Missing: {', '.join(missing)}"
            )

    def create(self, context: UserContext) -> UserContextIntelligence:
        """Create intelligence instance bound to specific user context."""
        return UserContextIntelligence(context=context, services=self)
```

---

## Context Depth: Standard vs Rich

**Philosophy:** UserContextIntelligence operations require RICH context.

UserContext has two depth levels:

| Depth | Method | Fields | Use Case | Intelligence Compatible? |
|-------|--------|--------|----------|--------------------------|
| **Standard** | `build()` | UIDs only (~150) | API responses, lightweight checks | ❌ NO - missing entities/graph |
| **Rich** | `build_rich()` | UIDs + entities + graph (~240) | Intelligence operations | ✅ YES - full context |

**Standard Context:**
- Contains entity UIDs only (e.g., `task_uids: list[str]`)
- Fast to build (~50-100ms)
- Sufficient for ownership checks, simple queries
- NOT sufficient for intelligence operations

**Rich Context:**
- Contains UIDs + full entities + graph neighborhoods
- Slower to build (~200-500ms) due to MEGA-QUERY
- Includes: tasks with their goals/habits, KUs with prerequisites, etc.
- Required for all 8 flagship methods

### Validation at Runtime

UserContextIntelligence validates context depth on creation:

```python
# File: /core/services/user/unified_user_context.py

class UserContext:
    def require_rich_context(self, operation: str) -> None:
        """
        Validate that context has rich data for intelligence operations.

        Raises:
            ValueError: If context is standard (UIDs only)
        """
        if not self.tasks:  # Rich context has full Task entities
            raise ValueError(
                f"Operation '{operation}' requires rich context. "
                f"Use UserContextBuilder.build_rich() instead of build()."
            )

# Usage in intelligence methods:
async def get_ready_to_work_on_today(self) -> Result[DailyWorkPlan]:
    """THE FLAGSHIP - requires rich context."""
    self.context.require_rich_context("get_ready_to_work_on_today")
    # Proceed with full entities available
```

**MEGA-QUERY for Rich Context:**
- Location: `/core/services/user/user_context_queries.py`
- Single ~1,000 line Cypher query
- Fetches UIDs + entities + graph context in one round-trip
- Populates all ~240 fields of UserContext

---

## Method 1: get_optimal_next_learning_steps()

**Mixin:** LearningIntelligenceMixin

**Purpose:** Determine what to learn next based on ALL factors (prerequisites, goals, capacity, life path).

**Signature:**
```python
async def get_optimal_next_learning_steps(
    self,
    max_steps: int = 5,
    consider_goals: bool = True,
    consider_capacity: bool = True,
) -> list[LearningStep]:
```

**Parameters:**
- `max_steps` (int, default=5) - Maximum number of steps to return
- `consider_goals` (bool, default=True) - Weight by goal alignment
- `consider_capacity` (bool, default=True) - Respect user capacity limits

**Returns:**
```python
[
    LearningStep(
        ku_uid="ku.python-async",
        title="Python Async Programming",
        rationale="Needed for 2 goals, unlocks 5 tasks, prerequisites met",
        prerequisites_met=True,
        aligns_with_goals=["goal_001", "goal_003"],
        unlocks_count=5,
        estimated_time_minutes=60,
        priority_score=0.85,
        application_opportunities={
            "tasks": ["task_042", "task_087"],
            "goals": ["goal_001"]
        }
    )
]
```

**Synthesis Algorithm:**
1. Get ready-to-learn KUs via `ku.get_ready_to_learn_for_user()`
2. For each KU, find application opportunities (tasks/goals it enables)
3. Count items unlocked (knowledge with high unblocking potential)
4. Find aligned goals (knowledge supporting active goals)
5. Generate rationale and priority score
6. Sort by priority, return top N

**Example:**
```python
intelligence = factory.create(context)
steps = await intelligence.get_optimal_next_learning_steps(
    max_steps=3,
    consider_goals=True,
    consider_capacity=True
)

for step in steps:
    print(f"Learn: {step.title}")
    print(f"  Priority: {step.priority_score:.2f}")
    print(f"  Unlocks: {step.unlocks_count} items")
    print(f"  Rationale: {step.rationale}")
```

**Dependencies:** ku (KuGraphService), tasks, goals (UnifiedRelationshipService)

---

## Method 2: get_learning_path_critical_path()

**Mixin:** LearningIntelligenceMixin

**Purpose:** Find the fastest route to the user's life path by identifying critical learning steps.

**Signature:**
```python
async def get_learning_path_critical_path(
    self,
    life_path_uid: str | None = None,
    max_depth: int = 5,
) -> list[LearningStep]:
```

**Parameters:**
- `life_path_uid` (str, optional) - Target life path (defaults to context.life_path_uid)
- `max_depth` (int, default=5) - Maximum prerequisite chain depth

**Returns:**
Ordered list of LearningStep objects representing the critical path.

**Algorithm:**
1. Get user's life path (from context or parameter)
2. Identify terminal knowledge required for life path
3. Traverse prerequisite chains backwards
4. Identify critical bottlenecks (single prerequisite paths)
5. Calculate time estimates for each step
6. Return ordered sequence (earliest prerequisite first)

**Example:**
```python
critical_path = await intelligence.get_learning_path_critical_path()

print(f"Critical path has {len(critical_path)} steps")
for i, step in enumerate(critical_path, 1):
    print(f"{i}. {step.title} ({step.estimated_time_minutes}min)")
```

**Dependencies:** lp (UnifiedRelationshipService), ku (KuGraphService)

---

## Method 3: get_knowledge_application_opportunities()

**Mixin:** LearningIntelligenceMixin

**Purpose:** Discover where specific knowledge can be applied across tasks, goals, and events.

**Signature:**
```python
async def get_knowledge_application_opportunities(
    self,
    ku_uid: str,
) -> dict[str, list[str]]:
```

**Parameters:**
- `ku_uid` (str) - Knowledge unit UID to analyze

**Returns:**
```python
{
    "tasks": ["task_042", "task_087"],  # Tasks requiring this knowledge
    "goals": ["goal_001"],              # Goals enabled by this knowledge
    "events": ["event_023"],            # Events applying this knowledge
    "habits": ["habit_005"]             # Habits reinforcing this knowledge
}
```

**Example:**
```python
opportunities = await intelligence.get_knowledge_application_opportunities(
    ku_uid="ku.python-async"
)

print(f"Can apply to {len(opportunities['tasks'])} tasks")
print(f"Supports {len(opportunities['goals'])} goals")
```

**Dependencies:** tasks, goals, events, habits (UnifiedRelationshipService)

---

## Method 4: get_unblocking_priority_order()

**Mixin:** LearningIntelligenceMixin

**Purpose:** Identify knowledge/tasks with highest unblocking potential (what unlocks the most downstream work).

**Signature:**
```python
async def get_unblocking_priority_order(
    self,
    max_items: int = 10,
) -> list[dict[str, Any]]:
```

**Parameters:**
- `max_items` (int, default=10) - Maximum items to return

**Returns:**
```python
[
    {
        "uid": "ku.python-basics",
        "type": "knowledge",
        "title": "Python Basics",
        "unlocks_count": 23,  # Unlocks 23 downstream items
        "unlocks": {
            "knowledge": ["ku.django", "ku.flask"],
            "tasks": ["task_001", "task_002"],
            "goals": ["goal_005"]
        },
        "priority_score": 0.92
    }
]
```

**Algorithm:**
1. Traverse prerequisite graph for all user entities
2. Count downstream items for each knowledge/task
3. Calculate priority score (unlocks_count / total_items)
4. Sort by priority score descending
5. Return top N items

**Example:**
```python
unblocking = await intelligence.get_unblocking_priority_order(max_items=5)

for item in unblocking:
    print(f"{item['title']}: Unlocks {item['unlocks_count']} items")
```

**Dependencies:** ku (KuGraphService), tasks, goals (UnifiedRelationshipService)

---

## Method 5: get_ready_to_work_on_today() - THE FLAGSHIP

**Mixin:** DailyPlanningMixin

**Purpose:** THE core method - synthesize ALL 9 domains to answer "What should I focus on TODAY?"

**Signature:**
```python
async def get_ready_to_work_on_today(
    self,
    prioritize_life_path: bool = True,
    respect_capacity: bool = True,
) -> DailyWorkPlan:
```

**Parameters:**
- `prioritize_life_path` (bool, default=True) - Weight life path alignment highly
- `respect_capacity` (bool, default=True) - Don't exceed available time

**Returns:**
```python
DailyWorkPlan(
    # Domain items (UIDs)
    learning=["ku.python-async"],
    tasks=["task_042", "task_087"],
    habits=["habit_005"],
    events=["event_023"],
    goals=["goal_001"],
    choices=["choice_012"],
    principles=["principle_003"],

    # Contextual items (enriched entities)
    contextual_tasks=[ContextualTask(...), ...],
    contextual_habits=[ContextualHabit(...), ...],
    contextual_goals=[ContextualGoal(...), ...],
    contextual_knowledge=[ContextualKnowledge(...), ...],

    # Plan metadata
    estimated_time_minutes=240,
    fits_capacity=True,
    workload_utilization=0.72,  # 72% capacity

    rationale="Focus on at-risk habits first, then advance goal_001",
    priorities=[
        "1. Maintain meditation habit (streak at risk)",
        "2. Complete task_042 (unblocks 3 items)",
        "3. Learn Python async (needed for 2 goals)"
    ],
    warnings=["Approaching 75% capacity - consider lighter afternoon"]
)
```

**Synthesis Algorithm:**

```
Priority 1: At-risk habits (maintain streaks - highest priority)
  └─ habits.get_at_risk_habits_for_user() → Top 3 habits
     Cost: ~15min per habit

Priority 2: Today's events (can't reschedule)
  └─ events.get_upcoming_events_for_user() → Events today
     Cost: Event duration

Priority 3: High-priority tasks (urgent/important)
  └─ tasks.get_actionable_tasks_for_user() → Priority > HIGH
     Filter: Has prerequisites met
     Cost: Task estimated_time

Priority 4: Advancing goals (make progress)
  └─ goals.get_advancing_goals_for_user() → Active goals
     Include: Next actions for each goal
     Cost: ~30min per goal

Priority 5: Ready-to-learn knowledge (growth)
  └─ ku.get_ready_to_learn_for_user() → Prerequisites met
     Filter: Aligns with goals or life path
     Cost: KU estimated_time

Priority 6: Pending decisions (reduce cognitive load)
  └─ choices.get_pending_decisions_for_user() → Awaiting decision
     Cost: ~20min per choice

Priority 7: Principle embodiment (value alignment)
  └─ principles.get_aligned_principles_for_user() → Active principles
     Cost: Reflection time
```

**Capacity Management:**
- Respects `context.available_minutes_daily`
- Considers `context.current_energy_level`
- Warns when `context.current_workload_score >= 0.75`
- Stops adding items when capacity reached

**Example:**
```python
intelligence = factory.create(context)
plan = await intelligence.get_ready_to_work_on_today(
    prioritize_life_path=True,
    respect_capacity=True
)

print(f"Daily Plan ({plan.estimated_time_minutes}min)")
print(f"Workload: {plan.workload_utilization:.0%}")
print(f"\nPriorities:")
for priority in plan.priorities:
    print(f"  {priority}")

print(f"\nFocus Areas:")
print(f"  - {len(plan.habits)} habits")
print(f"  - {len(plan.tasks)} tasks")
print(f"  - {len(plan.learning)} learning")
print(f"  - {len(plan.goals)} goals")
```

**Dependencies:** ALL 9 domain services (tasks, goals, habits, events, choices, principles, ku, ls, lp)

---

## Method 6: get_cross_domain_synergies()

**Mixin:** SynergyIntelligenceMixin

**Purpose:** Detect synergies between entities across different domains (high-leverage opportunities).

**Signature:**
```python
async def get_cross_domain_synergies(
    self,
    min_synergy_score: float = 0.3,
    include_types: list[str] | None = None,
) -> list[CrossDomainSynergy]:
```

**Parameters:**
- `min_synergy_score` (float, default=0.3) - Minimum score to include (0.0-1.0)
- `include_types` (list[str], optional) - Filter to specific types ["habit_goal", "task_habit", etc.]

**Synergy Types Detected:**
1. **Habit→Goal**: Habits supporting multiple goals (high leverage)
2. **Task→Habit**: Tasks that build habits (behavior change)
3. **Knowledge→Task**: Knowledge enabling tasks (skill application)
4. **Principle→Goal**: Principles guiding goal pursuit (value alignment)
5. **Goal→Learning**: Goals requiring specific knowledge (learning gaps)

**Returns:**
```python
[
    CrossDomainSynergy(
        source_uid="habit_005",
        source_domain="habit",
        target_uids=["goal_001", "goal_003", "goal_007"],
        target_domain="goal",
        synergy_type="supports",
        synergy_score=0.85,  # High leverage - supports 3 goals
        rationale="Morning meditation supports mental clarity, stress reduction, and focus",
        recommendations=[
            "Prioritize this habit - it advances multiple goals",
            "Track which goal it helps most each day"
        ]
    )
]
```

**Synergy Score Scale:**
- 0.0-0.3: Weak synergy (single connection)
- 0.4-0.6: Moderate synergy (multiple connections)
- 0.7-1.0: Strong synergy (hub entity, high leverage)

**Example:**
```python
synergies = await intelligence.get_cross_domain_synergies(
    min_synergy_score=0.5,
    include_types=["habit_goal", "knowledge_task"]
)

for synergy in synergies:
    print(f"{synergy.source_domain} → {synergy.target_domain}")
    print(f"  {synergy.rationale}")
    print(f"  Score: {synergy.synergy_score:.2f}")
```

**Dependencies:** tasks, goals, habits, principles, ku (relationship services)

---

## Method 7: calculate_life_path_alignment()

**Mixin:** LifePathIntelligenceMixin

**Purpose:** Calculate comprehensive life path alignment across 5 dimensions.

**Signature:**
```python
async def calculate_life_path_alignment(
    self
) -> Result[LifePathAlignment]:
```

**Returns:**
```python
LifePathAlignment(
    # Overall score
    overall_score=0.73,
    alignment_level="aligned",  # "drifting", "exploring", "aligned", "flourishing"

    # Dimension scores (0.0-1.0 each)
    knowledge_score=0.68,     # Mastery of life path knowledge (25% weight)
    activity_score=0.81,      # Tasks/habits supporting life path (25% weight)
    goal_score=0.75,          # Goals contributing to life path (20% weight)
    principle_score=0.62,     # Values supporting life path (15% weight)
    momentum_score=0.79,      # Recent trend toward life path (15% weight)

    # Insights
    strengths=[
        "Strong momentum - 79% of recent activity aligns",
        "Activity patterns well-aligned with life path goals"
    ],
    gaps=[
        "Low principle alignment - clarify core values",
        "Some knowledge remains theoretical (not applied)"
    ],
    recommendations=[
        "Focus on embodying principles in daily choices",
        "Apply Python knowledge to more real-world projects",
        "Schedule weekly life path review sessions"
    ],

    # Supporting data
    life_path_uid="lp.full-stack-developer",
    life_path_milestones_completed=12,
    life_path_milestones_total=18,
    aligned_goals=["goal_001", "goal_003"],
    supporting_habits=["habit_005", "habit_009"],
    knowledge_gaps=["ku.kubernetes", "ku.microservices"]
)
```

**Alignment Dimensions:**

| Dimension | Weight | Calculation |
|-----------|--------|-------------|
| **Knowledge** | 25% | Mastery of life path knowledge units |
| **Activity** | 25% | Tasks/habits supporting life path goals |
| **Goal** | 20% | Active goals contributing to life path |
| **Principle** | 15% | Values supporting life path direction |
| **Momentum** | 15% | Recent activity trend toward life path |

**Alignment Levels:**
- 0.0-0.3: **Drifting** (significant misalignment)
- 0.4-0.6: **Exploring** (some alignment, room for growth)
- 0.7-0.8: **Aligned** (actively living the path)
- 0.9-1.0: **Flourishing** (fully integrated, embodied)

**Example:**
```python
result = await intelligence.calculate_life_path_alignment()

if result.is_ok:
    alignment = result.value
    print(f"Life Path Alignment: {alignment.overall_score:.1%}")
    print(f"Level: {alignment.alignment_level}")
    print(f"\nStrengths:")
    for strength in alignment.strengths:
        print(f"  ✓ {strength}")
    print(f"\nGaps:")
    for gap in alignment.gaps:
        print(f"  ✗ {gap}")
```

**Dependencies:** lp (UnifiedRelationshipService), goals, habits, principles, ku (graph analysis)

---

## Method 8: get_schedule_aware_recommendations()

**Mixin:** ScheduleIntelligenceMixin

**Purpose:** Get recommendations that consider schedule, capacity, and energy levels.

**Signature:**
```python
async def get_schedule_aware_recommendations(
    self,
    max_recommendations: int = 5,
    time_horizon_hours: int = 8,
    respect_energy: bool = True,
) -> list[ScheduleAwareRecommendation]:
```

**Parameters:**
- `max_recommendations` (int, default=5) - Maximum number of recommendations
- `time_horizon_hours` (int, default=8) - How far ahead to look
- `respect_energy` (bool, default=True) - Consider current energy level

**Returns:**
```python
[
    ScheduleAwareRecommendation(
        uid="task_042",
        entity_type="task",
        recommendation_type="task",
        title="Complete Python API integration",
        rationale="Fits morning energy, no conflicts, unblocks 3 tasks",

        # Schedule context
        suggested_time_slot="morning",
        estimated_duration_minutes=90,
        fits_available_time=True,
        conflicts_with=[],

        # Scoring
        schedule_fit_score=0.88,
        energy_match_score=0.92,
        priority_score=0.85,
        overall_score=0.88,  # Weighted combination

        # Decision context
        deadline="2026-01-10",
        streak_at_risk=False,
        blocks_other_work=True,  # Unblocks 3 tasks
        life_path_aligned=True,

        # Guidance
        preparation_needed=["Review API docs", "Set up test environment"],
        alternatives=["task_087", "task_091"]
    )
]
```

**Synthesis Algorithm:**
1. Calculate available time slots from calendar events
2. Assess current energy level and capacity
3. Gather candidates from all domains (tasks, habits, learning, goals)
4. Score each by: schedule_fit × energy_match × priority
5. Filter conflicts and capacity violations
6. Rank by overall score
7. Generate actionable recommendations with preparation steps

**Recommendation Types:**
- **"learn"**: Knowledge unit to study
- **"task"**: Task to complete
- **"habit"**: Habit to maintain
- **"goal"**: Goal to advance
- **"rest"**: Rest recommendation (capacity exceeded)
- **"reschedule"**: Reschedule suggestion for conflicts

**Example:**
```python
recommendations = await intelligence.get_schedule_aware_recommendations(
    max_recommendations=3,
    time_horizon_hours=4,
    respect_energy=True
)

for rec in recommendations:
    print(f"\n{rec.title}")
    print(f"  When: {rec.suggested_time_slot}")
    print(f"  Duration: {rec.estimated_duration_minutes}min")
    print(f"  Overall Score: {rec.overall_score:.2f}")
    print(f"  Why: {rec.rationale}")
    if rec.preparation_needed:
        print(f"  Prep: {', '.join(rec.preparation_needed)}")
```

**Dependencies:** calendar (CalendarService), tasks, habits, goals, ku (all domain services)

---

## Mixin Architecture

UserContextIntelligence uses **mixin composition** to organize the 8 flagship methods:

```python
class UserContextIntelligence(
    LearningIntelligenceMixin,      # Methods 1-4
    LifePathIntelligenceMixin,      # Method 7
    SynergyIntelligenceMixin,       # Method 6
    ScheduleIntelligenceMixin,      # Method 8
    DailyPlanningMixin,             # Method 5
    GraphNativeMixin,               # Graph-native methods
):
    """Main intelligence class - composes all mixins."""
```

### LearningIntelligenceMixin (Methods 1-4)

**Location:** `/core/services/user/intelligence/learning_intelligence.py` (445 lines)

**Methods:**
1. `get_optimal_next_learning_steps()` - What should I learn next?
2. `get_learning_path_critical_path()` - Fastest route to life path?
3. `get_knowledge_application_opportunities()` - Where can I apply this?
4. `get_unblocking_priority_order()` - What unlocks the most?

**Purpose:** Learning journey intelligence - synthesize KU, Goals, Tasks, and Context to determine optimal learning priorities.

### LifePathIntelligenceMixin (Method 7)

**Location:** `/core/services/user/intelligence/life_path_intelligence.py` (429 lines)

**Methods:**
7. `calculate_life_path_alignment()` - Multi-dimensional life path alignment scoring

**Purpose:** Measure how well user's daily activities, knowledge, habits, goals, and principles align with ultimate life path.

### SynergyIntelligenceMixin (Method 6)

**Location:** `/core/services/user/intelligence/synergy_intelligence.py` (382 lines)

**Methods:**
6. `get_cross_domain_synergies()` - Cross-domain synergy detection

**Purpose:** Detect high-leverage opportunities where entities across domains create synergy (habits supporting multiple goals, knowledge enabling multiple tasks).

### ScheduleIntelligenceMixin (Method 8)

**Location:** `/core/services/user/intelligence/schedule_intelligence.py` (469 lines)

**Methods:**
8. `get_schedule_aware_recommendations()` - Schedule-aware recommendations

**Purpose:** Recommendations considering schedule, capacity, energy levels, and conflict avoidance.

### DailyPlanningMixin (Method 5 - THE FLAGSHIP)

**Location:** `/core/services/user/intelligence/daily_planning.py` (254 lines)

**Methods:**
5. `get_ready_to_work_on_today()` - THE FLAGSHIP - What's optimal for TODAY?

**Purpose:** THE core method - synthesize ALL 9 domains to answer "What should I focus on today?"

### GraphNativeMixin

**Location:** `/core/services/user/intelligence/graph_native.py` (366 lines)

**Purpose:** Context-based graph intelligence methods (internal helpers for the 8 flagship methods).

---

## Factory Pattern

**Location:** `/core/services/user/intelligence/factory.py` (234 lines)

**Why a Factory?**
- UserContextIntelligence requires a **context at construction** (user-specific)
- The **13 domain services are singletons** (created once at bootstrap)
- Factory separates service wiring from context binding

**Bootstrap (services_bootstrap.py):**
```python
from core.services.user.intelligence import UserContextIntelligenceFactory

# Create factory with all 13 domain services
factory = UserContextIntelligenceFactory(
    # Activity Domains (6)
    tasks=tasks_service.relationships,
    goals=goals_service.relationships,
    habits=habits_service.relationships,
    events=events_service.relationships,
    choices=choices_service.relationships,
    principles=principles_service.relationships,
    # Curriculum Domains (3)
    ku=ku_service.graph,
    ls=ls_service.relationships,
    lp=lp_service.relationships,
    # Processing Domains (3)
    assignments=assignments_service.relationships,
    journals=journals_service.relationships,
    reports=reports_service.relationships,
    # Temporal Domain (1)
    calendar=calendar_service,
)

# Store in services container
services.context_intelligence = factory
```

**Runtime (UserService):**
```python
# Build context for specific user
context = await user_service.get_user_context(user_uid)

# Create intelligence instance bound to context
intelligence = factory.create(context)

# Use intelligence methods
plan = await intelligence.get_ready_to_work_on_today()
```

---

## Integration with Other Services

### UserService Integration

**Location:** `/core/services/user_service.py`

UserService uses the factory to create intelligence instances:

```python
async def get_daily_plan(self, user_uid: str) -> Result[DailyWorkPlan]:
    """Get daily work plan for user."""
    # Build context
    context = await self.get_user_context(user_uid)

    # Create intelligence
    intelligence = self.context_intelligence.create(context)

    # Get plan
    return await intelligence.get_ready_to_work_on_today()
```

### Askesis Service Integration

**Location:** `/core/services/askesis_service.py`

Askesis (AI coach) uses UserContextIntelligence for recommendations:

```python
async def get_coaching_recommendations(self, user_uid: str):
    """Get AI coaching recommendations."""
    context = await self.user_service.get_user_context(user_uid)
    intelligence = self.context_intelligence.create(context)

    # Use intelligence for insights
    plan = await intelligence.get_ready_to_work_on_today()
    alignment = await intelligence.calculate_life_path_alignment()
    synergies = await intelligence.get_cross_domain_synergies()

    # Generate coaching based on intelligence
    return self._generate_coaching(plan, alignment, synergies)
```

---

## Domain-Specific Features

### Daily Planning (Method 5)

**Priority Order (hardcoded for predictable planning):**
1. **At-risk habits** - Maintain streaks (highest priority)
2. **Today's events** - Can't reschedule
3. **High-priority tasks** - Urgent/important work
4. **Advancing goals** - Make progress
5. **Ready-to-learn knowledge** - Growth opportunities
6. **Pending decisions** - Reduce cognitive load
7. **Principle embodiment** - Value alignment

**Capacity Management:**
- Respects `context.available_minutes_daily`
- Warns at 75% capacity
- Stops at 100% capacity
- Considers `context.current_energy_level`

### Cross-Domain Synthesis

**Unique Capability:** UserContextIntelligence is the ONLY service that synthesizes across all 14 domains:

| Synthesis Type | Domains Combined | Output |
|----------------|------------------|--------|
| Daily Planning | 9 domains | Prioritized work plan |
| Life Path Alignment | 5 dimensions | Alignment score + insights |
| Cross-Domain Synergies | 6 domains | High-leverage opportunities |
| Schedule-Aware | 4 domains + calendar | Time-optimized recommendations |

---

## Data Types

**Location:** `/core/services/user/intelligence/types.py` (205 lines)

### LifePathAlignment

```python
@dataclass
class LifePathAlignment:
    overall_score: float              # 0.0-1.0
    alignment_level: str              # "drifting", "exploring", "aligned", "flourishing"
    knowledge_score: float            # 0.0-1.0
    activity_score: float             # 0.0-1.0
    goal_score: float                 # 0.0-1.0
    principle_score: float            # 0.0-1.0
    momentum_score: float             # 0.0-1.0
    strengths: list[str]
    gaps: list[str]
    recommendations: list[str]
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
    source_domain: str                # "habit", "task", "knowledge", "principle"
    target_uids: list[str]
    target_domain: str                # "goal", "habit", "task", "choice"
    synergy_type: str                 # "supports", "enables", "builds", "informs"
    synergy_score: float              # 0.0-1.0
    rationale: str
    recommendations: list[str]
```

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
    priority_score: float             # 0.0-1.0
    application_opportunities: dict[str, list[str]]
```

### DailyWorkPlan

```python
@dataclass
class DailyWorkPlan:
    learning: list[str] = field(default_factory=list)
    tasks: list[str] = field(default_factory=list)
    habits: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)
    choices: list[str] = field(default_factory=list)
    principles: list[str] = field(default_factory=list)

    contextual_tasks: list[ContextualTask] = field(default_factory=list)
    contextual_habits: list[ContextualHabit] = field(default_factory=list)
    contextual_goals: list[ContextualGoal] = field(default_factory=list)
    contextual_knowledge: list[ContextualKnowledge] = field(default_factory=list)

    estimated_time_minutes: int = 0
    fits_capacity: bool = True
    workload_utilization: float = 0.0
    rationale: str = ""
    priorities: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
```

### ScheduleAwareRecommendation

```python
@dataclass
class ScheduleAwareRecommendation:
    uid: str
    entity_type: str
    recommendation_type: str          # "learn", "task", "habit", "goal", "rest", "reschedule"
    title: str
    rationale: str
    suggested_time_slot: str          # "morning", "afternoon", "evening", "now", "later"
    estimated_duration_minutes: int = 30
    fits_available_time: bool = True
    conflicts_with: list[str] = field(default_factory=list)
    schedule_fit_score: float = 0.0
    energy_match_score: float = 0.0
    priority_score: float = 0.0
    overall_score: float = 0.0
    deadline: str | None = None
    streak_at_risk: bool = False
    blocks_other_work: bool = False
    life_path_aligned: bool = False
    preparation_needed: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
```

---

## Testing

### Unit Tests

**Location:** `/tests/services/user/intelligence/`

Test each mixin independently:

```python
# Test LearningIntelligenceMixin
async def test_get_optimal_next_learning_steps():
    # Mock context and services
    context = create_mock_context()
    intelligence = create_test_intelligence(context)

    # Test
    steps = await intelligence.get_optimal_next_learning_steps(max_steps=3)

    # Assert
    assert len(steps) <= 3
    assert all(step.prerequisites_met for step in steps)
```

### Integration Tests

**Location:** `/tests/integration/intelligence/`

Test full intelligence workflow:

```python
async def test_daily_planning_workflow():
    # Build real context
    context = await user_service.get_user_context("user.mike")

    # Create intelligence
    intelligence = factory.create(context)

    # Get daily plan
    plan = await intelligence.get_ready_to_work_on_today()

    # Verify plan structure
    assert plan.fits_capacity
    assert plan.workload_utilization <= 1.0
    assert len(plan.priorities) > 0
```

### Mock Factory for Testing

```python
def create_test_intelligence(context: UserContext) -> UserContextIntelligence:
    """Create intelligence with mock services for testing."""
    return UserContextIntelligence(
        context=context,
        tasks=mock_tasks_service(),
        goals=mock_goals_service(),
        habits=mock_habits_service(),
        # ... etc for all 13 services
    )
```

---

## Profile Integration
*Last updated: January 2026*

### Fail-Fast Philosophy

The Profile page (`/profile`) integrates UserContextIntelligence following SKUEL's fail-fast principles:

**Key Distinction:**
- **Bootstrap dependency** (factory exists): Fail-fast at startup
- **Runtime operations** (methods return `Result[T]`): Propagate to HTTP boundary
- **UI components**: Expect data, no None fallbacks

### Integration Pattern

**Route Implementation** (`/adapters/inbound/user_profile_ui.py`):

```python
async def _get_intelligence_data(context: UserContext) -> Result[dict[str, Any]]:
    """Get intelligence data. Returns Result[T] for proper error propagation."""
    # Factory is REQUIRED (bootstrap dependency) - no graceful degradation
    intelligence = services.context_intelligence.create(context)

    # Methods return Result[T] - propagate errors via expect_error()
    plan_result = await intelligence.get_ready_to_work_on_today()
    if plan_result.is_error:
        return plan_result.expect_error()

    alignment_result = await intelligence.calculate_life_path_alignment()
    if alignment_result.is_error:
        return alignment_result.expect_error()

    synergies_result = await intelligence.get_cross_domain_synergies()
    if synergies_result.is_error:
        return synergies_result.expect_error()

    steps_result = await intelligence.get_optimal_next_learning_steps()
    if steps_result.is_error:
        return steps_result.expect_error()

    return Result.ok({
        "daily_plan": plan_result.value,
        "alignment": alignment_result.value,
        "synergies": synergies_result.value,
        "learning_steps": steps_result.value,
    })
```

**Route Handler:**

```python
@rt("/profile")
async def profile_page(request: Request) -> Any:
    user_uid = require_authenticated_user(request)
    context = await _get_user_context(user_uid)

    # Result propagation at HTTP boundary
    intel_result = await _get_intelligence_data(context)
    if intel_result.is_error:
        return JSONResponse({"error": str(intel_result.error)}, status_code=500)

    intel_data = intel_result.value
    content = OverviewView(
        context,
        daily_plan=intel_data["daily_plan"],
        alignment=intel_data["alignment"],
        synergies=intel_data["synergies"],
        learning_steps=intel_data["learning_steps"],
    )
    # ...
```

### UI Components

**OverviewView** (`/ui/profile/domain_views.py`) requires all intelligence data:

```python
def OverviewView(
    context: UserContext,
    daily_plan: "DailyWorkPlan",              # Required
    alignment: "LifePathAlignment",            # Required
    synergies: "list[CrossDomainSynergy]",     # Required (may be empty list)
    learning_steps: "list[LearningStep]",      # Required (may be empty list)
) -> Div:
    return Div(
        _daily_work_plan_card(daily_plan),
        _alignment_breakdown(alignment),
        _synergies_card(synergies),
        _learning_steps_card(learning_steps),
    )
```

**Key Distinction:** Empty list `[]` is valid data (user has no synergies). The pattern removes `| None`, NOT empty checks.

### Anti-Pattern: Graceful Degradation

**Do NOT do this:**

```python
# ❌ WRONG - Graceful degradation violates fail-fast
if not services.context_intelligence:
    return {"daily_plan": None}  # Silent failure

try:
    plan = await intelligence.get_ready_to_work_on_today()
except Exception as e:
    logger.debug(f"Failed: {e}")  # Silent failure
    return {"daily_plan": None}
```

**Problems:**
- Factory check enables "soft failures" - hides bootstrap problems
- try/except swallows errors - debugging nightmare
- None fallbacks propagate to UI - more defensive code needed

### Files

| File | Purpose |
|------|---------|
| `/adapters/inbound/user_profile_ui.py` | Routes with fail-fast error handling |
| `/ui/profile/domain_views.py` | UI components with required parameters |
| `/ui/profile/layout.py` | Profile Hub layout with sidebar |

**See:** `/docs/patterns/ERROR_HANDLING.md` § "Fail-Fast Philosophy for Required Dependencies"

---

## See Also

### Related Documentation

- **ADR-021:** User Context Intelligence Modularization (`/docs/decisions/ADR-021-user-context-intelligence-modularization.md`)
- **ADR-016:** Context Builder Decomposition (similar pattern)
- **Unified User Architecture:** `/docs/architecture/UNIFIED_USER_ARCHITECTURE.md`
- **Context First Relationship Pattern:** `/docs/patterns/CONTEXT_FIRST_RELATIONSHIP_PATTERN.md`

### Related Services

- **Domain Intelligence Services:**
  - `/docs/intelligence/TASKS_INTELLIGENCE.md`
  - `/docs/intelligence/GOALS_INTELLIGENCE.md`
  - `/docs/intelligence/HABITS_INTELLIGENCE.md`
  - `/docs/intelligence/EVENTS_INTELLIGENCE.md`
  - `/docs/intelligence/CHOICES_INTELLIGENCE.md`
  - `/docs/intelligence/PRINCIPLES_INTELLIGENCE.md`
  - `/docs/intelligence/KU_INTELLIGENCE.md`
  - `/docs/intelligence/LS_INTELLIGENCE.md`
  - `/docs/intelligence/LP_INTELLIGENCE.md`

- **UserContext:** `/core/services/user/unified_user_context.py`
- **UserService:** `/core/services/user_service.py`
- **Askesis Service:** `/core/services/askesis_service.py`

### CLAUDE.md Sections

- **Intelligence Services Architecture** - Overview of all intelligence services
- **UserContextIntelligence** - Quick reference for the 8 flagship methods
- **14-Domain + 5-System Architecture** - Domain organization
