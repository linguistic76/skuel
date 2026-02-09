---
title: Context-First Relationship Pattern
updated: 2026-02-10
category: patterns
related_skills:
- neo4j-cypher-patterns
- user-context-intelligence
related_docs:
- /docs/architecture/UNIFIED_USER_ARCHITECTURE.md
- /docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md
---

# Context-First Relationship Pattern

**Version:** 2.0.0
**Date:** February 10, 2026
**Status:** Implemented
**Canonical File:** `core/models/context_types.py`

## Related Skills

For implementation guidance, see:
- [@neo4j-cypher-patterns](../../.claude/skills/neo4j-cypher-patterns/SKILL.md)
- [@user-context-intelligence](../../.claude/skills/user-context-intelligence/SKILL.md)


## Executive Summary

The Context-First pattern transforms raw graph entities into personalized, scored, and ranked recommendations by combining entity data with the ~240-field `UserContext`. Every relationship query becomes an opportunity to filter by readiness, rank by relevance, and enrich with actionable insights.

**Architecture (February 2026):** A harmonized scoring engine with factory classmethods on frozen dataclasses. All 7 ContextualEntity subclasses have `from_entity_and_context()` classmethods that accept domain-specific parameters and optional score overrides, producing fully-scored frozen instances from a single call.

## The Problem

Relationship services originally returned raw entities with no user awareness:

```python
# Old Pattern - Returns ALL related entities, context-blind
async def get_task_dependencies(self, task_uid: str) -> Result[list[Task]]:
    return await self.backend.get_task_dependencies(task_uid)

# What this misses:
# - Is the user ready for these dependencies? (prerequisites met?)
# - Which dependencies align with user's current goals?
# - Which should be prioritized based on user's capacity?
# - Are there knowledge gaps blocking these tasks?
```

## The Solution: Context-First Pattern

### Core Principle: "Filter by readiness, rank by relevance, enrich with insights"

```python
# Context-aware queries return scored, ranked, enriched results
async def get_actionable_tasks_for_user(
    self,
    context: UserContext,
    limit: int = 10,
) -> Result[list[ContextualTask]]:
    """Tasks the user can start NOW, ranked by priority."""
```

**Naming Convention:** `*_for_user()` suffix indicates context-awareness. Standard methods return raw data; context-first methods return `Contextual*` types.


## Architecture Overview

The Context-First system has three layers:

```
┌─────────────────────────────────────────────────────────┐
│  Layer 1: Scoring Engine (5 pure functions)              │
│  _compute_readiness, _compute_relevance,                 │
│  _compute_urgency, _compute_priority,                    │
│  _compute_blocking_reasons                               │
├─────────────────────────────────────────────────────────┤
│  Layer 2: Factory Classmethods (7 types)                 │
│  ContextualTask.from_entity_and_context()                │
│  ContextualGoal.from_entity_and_context()                │
│  ... one per domain ...                                  │
├─────────────────────────────────────────────────────────┤
│  Layer 3: Service Methods (18 call sites)                │
│  planning_mixin, context_first_mixin,                    │
│  5 domain planning services                              │
└─────────────────────────────────────────────────────────┘
```

**Key Design Decisions:**
- Scoring functions are module-level pure functions (no `self`, no I/O)
- Factory classmethods live on the frozen dataclasses (SKUEL pattern: logic on types)
- Services are thin callers that extract domain-specific parameters, then delegate to factories
- Override kwargs (`readiness_override`, `relevance_override`, etc.) let services bypass standard computation when they have domain-specific knowledge


## Layer 1: Harmonized Scoring Engine

Five pure functions in `core/models/context_types.py`, extracted from what was previously scattered across `ContextFirstMixin`, `PrerequisiteHelper`, and 5 domain planning services. Same formulas, one location, parameterized for all domains.

### `_compute_readiness(required_knowledge, required_tasks, knowledge_mastery, completed_task_uids, threshold=0.7) -> float`

Calculates what fraction of prerequisites are met.

```python
def _compute_readiness(
    required_knowledge: list[str],
    required_tasks: list[str],
    knowledge_mastery: dict[str, float],
    completed_task_uids: set[str] | list[str],
    threshold: float = 0.7,
) -> float:
    total = len(required_knowledge) + len(required_tasks)
    if total == 0:
        return 1.0  # No prerequisites = always ready

    met = 0
    for ku_uid in required_knowledge:
        if knowledge_mastery.get(ku_uid, 0.0) >= threshold:
            met += 1
    for task_uid in required_tasks:
        if task_uid in completed_task_uids:
            met += 1

    return met / total
```

**Returns:** 0.0 (no prerequisites met) to 1.0 (all met). No prerequisites returns 1.0.

### `_compute_relevance(goal_uids, principle_uids, active_goal_uids, primary_goal_focus, core_principle_uids, principle_priorities) -> float`

Calculates alignment with user's goals and principles.

```python
def _compute_relevance(
    goal_uids: list[str],           # Goals this entity contributes to
    principle_uids: list[str],      # Principles this entity aligns with
    active_goal_uids: set[str],     # User's active goals (from UserContext)
    primary_goal_focus: str,        # User's primary goal UID
    core_principle_uids: set[str],  # User's core principles
    principle_priorities: dict[str, float],  # Principle priority weights
) -> float:
```

**Scoring logic:**
- **Goal score:** Ratio of entity's goals that are in user's active goals, +0.2 bonus if primary goal focus matches
- **Principle score:** Ratio of aligned principles, weighted by principle priority
- **Combination:** If both present: `(goal * 0.6) + (principle * 0.4)`. If only one, use that score.
- **Default (neither):** 0.5

### `_compute_urgency(deadline, is_at_risk, streak_at_risk) -> float`

Calculates time pressure from deadlines and risk flags.

| Condition | Score |
|-----------|-------|
| Overdue (past deadline) | 1.0 |
| Due today | 0.9 |
| Due within 3 days | 0.7 |
| Due within 7 days | 0.5 |
| Due later | 0.2 |
| No deadline | 0.0 |
| `is_at_risk` flag | max(current, 0.8) |
| `streak_at_risk` flag | max(current, 0.85) |

### `_compute_priority(dimensions, weights) -> float`

**N-dimensional weighted sum**, capped at 1.0. This is the key generalization — different domains use different numbers of scoring dimensions:

```python
def _compute_priority(
    dimensions: tuple[float, ...],  # Score values (0.0-1.0 each)
    weights: tuple[float, ...],     # Weights (should sum to ~1.0)
) -> float:
    return min(1.0, sum(d * w for d, w in zip(dimensions, weights)))
```

**Domain Dimensionality:**

| Domain | Dimensions | Default Weights | Rationale |
|--------|-----------|-----------------|-----------|
| Task | 3D: readiness, relevance, urgency | `(0.4, 0.4, 0.2)` | Readiness and relevance equally important |
| Goal | 4D: readiness, relevance, progress, urgency | `(0.3, 0.4, 0.2, 0.1)` | Progress adds momentum dimension |
| Habit | 3D: readiness, relevance, urgency | `(0.3, 0.3, 0.4)` | Urgency-led (streak protection) |
| Knowledge | 3D: readiness, gap, impact | `(0.5, 0.3, 0.2)` | Readiness-led (prerequisites matter most) |
| Knowledge (gaps) | 2D: readiness, relevance | `(0.4, 0.6)` | Relevance-led (blocking goals matters) |

### `_compute_blocking_reasons(required_knowledge, required_tasks, knowledge_mastery, completed_task_uids, max_reasons=3) -> list[str]`

Generates human-readable strings explaining what blocks engagement:

```python
# Example output:
["Missing knowledge: ku_python-basics_abc123 (mastery: 45%)",
 "Incomplete prerequisite: task_setup-env_xyz789"]
```


## Layer 2: Factory Classmethods on Frozen Dataclasses

All 7 ContextualEntity subclasses have a `from_entity_and_context()` classmethod. This is the SKUEL pattern: logic lives on the types, not in the services.

### Base Type: `ContextualEntity`

```python
@dataclass(frozen=True)
class ContextualEntity:
    uid: str
    title: str

    # Context-derived scores (0.0-1.0)
    readiness_score: float = 0.0
    relevance_score: float = 0.0
    priority_score: float = 0.0

    # Context-derived insights
    blocking_reasons: tuple[str, ...] = ()
    unlocks: tuple[str, ...] = ()
    learning_gaps: tuple[str, ...] = ()

    # Metadata
    enriched_at: datetime = field(default_factory=datetime.now)

    # Convenience methods
    def is_ready(self, threshold=0.7) -> bool: ...
    def is_relevant(self, threshold=0.5) -> bool: ...
    def is_high_priority(self, threshold=0.7) -> bool: ...
    def has_blockers(self) -> bool: ...

    # Entity type discriminator for dispatch
    @property
    def entity_type(self) -> str: ...  # "task", "goal", "habit", etc.
```

**Entity Type Discriminator:** All 7 subclasses override `entity_type` for unified dispatch:

| Class | entity_type |
|-------|-------------|
| ContextualTask | `"task"` |
| ContextualKnowledge | `"knowledge"` |
| ContextualGoal | `"goal"` |
| ContextualHabit | `"habit"` |
| ContextualEvent | `"event"` |
| ContextualPrinciple | `"principle"` |
| ContextualChoice | `"choice"` |

### Factory Pattern: `from_entity_and_context()`

Every factory classmethod follows the same structure:

1. Accept `uid`, `title`, `context: "UserContext"` + domain-specific keyword args
2. Accept optional `*_override` kwargs for bypassing standard computation
3. Accept optional `weights` tuple for custom priority weighting
4. Call scoring functions with UserContext fields unpacked
5. Return frozen instance

**Override Pattern:** When a service has domain-specific knowledge that should bypass the standard scoring formula, it passes `*_override` kwargs:

```python
# Standard path — scoring engine computes everything
contextual = ContextualTask.from_entity_and_context(
    uid=task_uid, title=title, context=context,
    goal_uids=goals, prerequisite_knowledge=knowledge,
)

# Override path — service knows better for this specific case
contextual = ContextualTask.from_entity_and_context(
    uid=task_uid, title=title, context=context,
    readiness_override=0.8,        # Learning task — known to be ready
    relevance_override=0.7,        # Always relevant for learning
    priority_override=0.3 * count + 0.4,  # Custom learning impact formula
)
```

### `ContextualTask.from_entity_and_context()`

```python
@classmethod
def from_entity_and_context(
    cls, uid: str, title: str, context: "UserContext", *,
    goal_uids: list[str] | None = None,
    knowledge_uids: list[str] | None = None,
    prerequisite_knowledge: list[str] | None = None,
    prerequisite_tasks: list[str] | None = None,
    deadline: date | None = None,
    estimated_time_minutes: int = 0,
    # Overrides
    readiness_override: float | None = None,
    relevance_override: float | None = None,
    urgency_override: float | None = None,
    priority_override: float | None = None,
    weights: tuple[float, float, float] = (0.4, 0.4, 0.2),
) -> "ContextualTask":
```

**Standard scoring path:** Readiness from prerequisite knowledge/tasks, relevance from goal alignment, urgency from deadline + overdue status, priority from 3D weighted sum.

**Additional fields populated:** `can_start` (readiness >= 0.7), `is_overdue` (uid in `context.overdue_task_uids`), `is_milestone` (uid in `context.milestone_tasks`), `contributes_to_goals`, `applies_knowledge`, `blocking_reasons`.

**Call sites (5):**
- `context_first_mixin._enrich_task_with_context()` — default weights
- `tasks_planning_service.get_task_dependencies_for_user()` — default weights
- `tasks_planning_service.get_actionable_tasks_for_user()` — default weights, filter readiness >= 0.7
- `tasks_planning_service.get_learning_tasks_for_user()` — `readiness_override=0.8, priority_override=learning_impact`
- `planning_mixin.get_actionable_tasks_for_user()` — default weights with overdue boost

### `ContextualKnowledge.from_entity_and_context()`

```python
@classmethod
def from_entity_and_context(
    cls, uid: str, title: str, context: "UserContext", *,
    prerequisite_uids: list[str] | None = None,
    application_task_uids: list[str] | None = None,
    dependent_count: int = 0,
    substance_score: float = 0.0,
    readiness_override: float | None = None,
    relevance_override: float | None = None,
    priority_override: float | None = None,
    weights: tuple[float, ...] = (0.5, 0.3, 0.2),
) -> "ContextualKnowledge":
```

**Standard scoring path:** Mastery from `context.knowledge_mastery`, prerequisites check (all >= 0.7), readiness = 1.0 if met else 0.3, relevance = 1.0 - mastery (gap-based), third dimension = `dependent_count/5` (impact). **Supports 2D or 3D weights** — `dims[:len(weights)]` truncation handles both.

**Call sites (4):**
- `context_first_mixin._enrich_knowledge_with_context()` — default weights
- `ku_graph_service.get_ready_to_learn_for_user()` — `weights=(0.5, 0.3, 0.2)`
- `ku_graph_service.get_learning_gaps_for_user()` — `relevance_override=goals_blocked_ratio, weights=(0.4, 0.6)` (2D)
- `ku_graph_service.get_knowledge_to_reinforce_for_user()` — `readiness_override=0.9`, decay as relevance

### `ContextualGoal.from_entity_and_context()`

```python
@classmethod
def from_entity_and_context(
    cls, uid: str, title: str, context: "UserContext", *,
    contributing_task_uids: list[str] | None = None,
    contributing_habit_uids: list[str] | None = None,
    required_knowledge_uids: list[str] | None = None,
    readiness_override: float | None = None,
    relevance_override: float | None = None,
    urgency_override: float | None = None,
    priority_override: float | None = None,
    weights: tuple[float, ...] = (0.3, 0.4, 0.2, 0.1),
) -> "ContextualGoal":
```

**Standard scoring path (4D):** Readiness from knowledge prerequisites, relevance = 1.0 if active else 0.5, progress from `context.goal_progress`, urgency from deadline + at-risk status. 4D weighted sum with `(readiness, relevance, progress, urgency)`.

**Additional fields populated:** `current_progress`, `days_to_deadline`, `is_at_risk`, `contributing_tasks`, `contributing_habits`, `knowledge_required`, `learning_gaps`.

**Call sites (5):**
- `context_first_mixin._enrich_goal_with_context()` — standard path
- `goals_planning_service.get_advancing_goals_for_user()` — default 4D weights
- `goals_planning_service.get_stalled_goals_for_user()` — `relevance_override=0.7, priority_override=0.7*(1-progress)`
- `goals_planning_service.get_achievable_goals_for_user()` — `readiness_override=1.0, relevance_override=0.9, priority_override=min(1.0, progress*1.2)`
- `planning_mixin.get_advancing_goals_for_user()` — standard with at-risk check

### `ContextualHabit.from_entity_and_context()`

```python
@classmethod
def from_entity_and_context(
    cls, uid: str, title: str, context: "UserContext", *,
    supported_goal_uids: list[str] | None = None,
    applied_knowledge_uids: list[str] | None = None,
    is_due_today: bool = False,
    current_streak: int | None = None,
    completion_rate: float | None = None,
    is_keystone: bool | None = None,
    days_since_last: int = 0,
    best_streak: int = 0,
    readiness_override: float | None = None,
    relevance_override: float | None = None,
    urgency_override: float | None = None,
    priority_override: float | None = None,
    weights: tuple[float, float, float] = (0.3, 0.3, 0.4),
) -> "ContextualHabit":
```

**Standard scoring path:** Readiness = 1.0 (habits are always "ready"), relevance from goal alignment (0.6) + streak ratio (0.4), urgency from at-risk flags. Default weights are urgency-led `(0.3, 0.3, 0.4)` because habits are about maintaining streaks.

**Context lookups:** Streak from `context.habit_streaks`, completion rate from `context.habit_completion_rates`, at-risk from `context.at_risk_habits`, keystone from `context.keystone_habits`.

**Call sites (7):**
- `context_first_mixin._enrich_habit_with_context()` — standard path
- `habits_planning_service.get_habit_priorities_for_user()` — `weights=(0.3, 0.3, 0.4)`
- `habits_planning_service.get_actionable_habits_for_user()` — urgency-heavy weights + keystone bonus
- `habits_planning_service.get_learning_habits_for_user()` — `readiness_override=0.8, priority_override=learning_impact`
- `habits_planning_service.get_goal_supporting_habits_for_user()` — `priority_override=goal_support_score`
- `habits_planning_service.get_habit_readiness_for_user()` — `readiness_override=streak/7`
- `planning_mixin.get_at_risk_habits_for_user()` — `readiness_override=1.0, relevance_override=0.9, priority_override=0.95`

### `ContextualEvent.from_entity_and_context()`

```python
@classmethod
def from_entity_and_context(
    cls, uid: str, title: str, context: "UserContext", *,
    days_until: int = 0,
    duration_minutes: int = 0,
    supports_habits: list[str] | None = None,
    applies_knowledge: list[str] | None = None,
) -> "ContextualEvent":
```

**Simplified scoring:** Events use proximity-based scoring. Today's events get maximum priority (0.95), upcoming events get 0.7. No override kwargs — events are straightforward.

**Call sites (1):**
- `planning_mixin.get_upcoming_events_for_user()`

### `ContextualPrinciple.from_entity_and_context()`

```python
@classmethod
def from_entity_and_context(
    cls, uid: str, name: str, context: "UserContext", *,
    alignment_score: float = 0.5,
    days_since_reflection: int = 0,
    alignment_trend: str = "stable",
    attention_reasons: list[str] | None = None,
    suggested_action: str = "",
    connected_task_uids: list[str] | None = None,
    connected_event_uids: list[str] | None = None,
    connected_goal_uids: list[str] | None = None,
    practice_opportunity: str = "",
    priority_override: float | None = None,
    relevance_override: float | None = None,
) -> "ContextualPrinciple":
```

**Two scoring paths:**

1. **Standard path:** Readiness = 1.0, relevance = alignment_score, priority = 0.8 if core else 0.5.

2. **Attention path** (when `days_since_reflection > 0`): Computes `attention_score` as a 3-factor formula:
   - Reflection urgency: `min(1.0, days_since_reflection / 28)` — weight 0.4
   - Alignment weakness: `1.0 - alignment_score` — weight 0.35
   - Trend score: declining=1.0, stable=0.3, improving=0.0 — weight 0.25
   - Priority defaults to `attention_score` when computed

**Call sites (3):**
- `planning_mixin.get_aligned_principles_for_user()` — standard path
- `principles_planning_service.get_principles_needing_attention_for_user()` — attention path
- `principles_planning_service.get_contextual_principles_for_user()` — `relevance_override=accumulated_relevance`

### `ContextualChoice.from_entity_and_context()`

```python
@classmethod
def from_entity_and_context(
    cls, uid: str, title: str, context: "UserContext", *,
    priority_level: str = "medium",
    informed_by_knowledge: list[str] | None = None,
    aligned_principles: list[str] | None = None,
) -> "ContextualChoice":
```

**Simplified scoring:** Readiness = 1.0, relevance = 0.7, priority from enum mapping:

| Priority Level | Score |
|---------------|-------|
| urgent | 0.9 |
| high | 0.7 |
| medium | 0.5 |
| low | 0.3 |

**Call sites (1):**
- `planning_mixin.get_pending_decisions_for_user()`


## Layer 3: Service Integration

The 18 construction sites across 7 service files now delegate to factory classmethods. Each service extracts domain-specific parameters from its data source (rich context, graph queries, or entity attributes) and passes them to the factory.

### Service Architecture

```
UserContext (MEGA-QUERY)
    │
    ├── context_first_mixin.py         (4 enrichment methods → 4 factories)
    │   _enrich_task_with_context     → ContextualTask.from_entity_and_context()
    │   _enrich_goal_with_context     → ContextualGoal.from_entity_and_context()
    │   _enrich_habit_with_context    → ContextualHabit.from_entity_and_context()
    │   _enrich_knowledge_with_context→ ContextualKnowledge.from_entity_and_context()
    │
    ├── planning_mixin.py              (6 methods → 6 factories)
    │   get_at_risk_habits_for_user   → ContextualHabit.from_entity_and_context()
    │   get_upcoming_events_for_user  → ContextualEvent.from_entity_and_context()
    │   get_actionable_tasks_for_user → ContextualTask.from_entity_and_context()
    │   get_advancing_goals_for_user  → ContextualGoal.from_entity_and_context()
    │   get_pending_decisions_for_user→ ContextualChoice.from_entity_and_context()
    │   get_aligned_principles_for_user→ContextualPrinciple.from_entity_and_context()
    │
    ├── tasks_planning_service.py      (3 methods → ContextualTask factory)
    ├── goals_planning_service.py      (3 methods → ContextualGoal factory)
    ├── habits_planning_service.py     (5 methods → ContextualHabit factory)
    ├── principles_planning_service.py (2 methods → ContextualPrinciple factory)
    └── ku_graph_service.py            (3 methods → ContextualKnowledge factory)
```

### Enrichment Adapter Pattern (`context_first_mixin.py`)

The mixin's `_enrich_*_with_context()` methods are thin adapters that extract fields from domain objects and delegate to factories:

```python
async def _enrich_task_with_context(self, task, context, goal_uids=None, ...):
    """Enrich a task with user context. Delegates to factory classmethod."""
    uid = _get_attr(task, "uid", "")
    title = _get_attr(task, "title", "")
    deadline = _get_attr(task, "due_date")
    return ContextualTask.from_entity_and_context(
        uid=uid, title=title, context=context,
        goal_uids=goal_uids, deadline=deadline, ...
    )
```

### Domain Planning Service Pattern

Planning services iterate over UserContext data, extract domain-specific parameters, and call the factory:

```python
# goals_planning_service.py — get_advancing_goals_for_user()
for goal_uid in context.active_goal_uids:
    goal_data = rich_goals_by_uid[goal_uid]
    graph_ctx = goal_data.get("graph_context", {})

    # Extract domain-specific parameters from rich context
    knowledge_uids = [k.get("uid") for k in graph_ctx.get("required_knowledge", [])]
    contributing_tasks = context.tasks_by_goal.get(goal_uid, [])
    contributing_habits = context.habits_by_goal.get(goal_uid, [])

    # Delegate to factory — scoring engine handles the rest
    contextual = ContextualGoal.from_entity_and_context(
        uid=goal_uid,
        title=goal_dict.get("title", str(goal_uid)),
        context=context,
        contributing_task_uids=contributing_tasks,
        contributing_habit_uids=contributing_habits,
        required_knowledge_uids=knowledge_uids,
    )
    advancing_goals.append(contextual)
```

### Override Pattern in Practice

Services use overrides when they have domain-specific scoring knowledge:

```python
# Stalled goals — inverted priority (more stalled = higher priority)
contextual = ContextualGoal.from_entity_and_context(
    uid=goal_uid, title=title, context=context,
    relevance_override=0.7,
    priority_override=0.7 * (1 - progress),  # Inversely proportional to progress
)

# Learning tasks — known readiness, custom learning impact formula
contextual = ContextualTask.from_entity_and_context(
    uid=task.uid, title=task.title, context=context,
    readiness_override=0.8,        # Learning tasks are known-ready
    relevance_override=0.7,        # Always relevant for learning
    priority_override=min(1.0, learning_impact * 0.3 + 0.4),
)

# Achievable goals — near completion boost
contextual = ContextualGoal.from_entity_and_context(
    uid=goal_uid, title=title, context=context,
    readiness_override=1.0,        # Always ready (near completion)
    relevance_override=0.9,        # High relevance (finish line)
    priority_override=min(1.0, progress * 1.2),  # Progress-proportional priority
)
```


## Aggregate Types

### `ContextualDependencies`

Container for categorized dependency analysis:

```python
@dataclass(frozen=True)
class ContextualDependencies:
    entity_uid: str
    entity_type: str  # "Task", "Goal", "Habit", etc.

    # Categorized by readiness
    ready_dependencies: tuple[ContextualEntity, ...]
    blocked_dependencies: tuple[ContextualEntity, ...]

    # Aggregated insights
    total_blocking_items: int = 0
    recommended_next_action: str = ""
```

Used by `TasksPlanningService.get_task_dependencies_for_user()` to return ready vs. blocked dependencies with an actionable recommendation.

### `PracticeOpportunity`

Separate frozen dataclass (not a ContextualEntity subclass) for principle practice opportunities:

```python
@dataclass(frozen=True)
class PracticeOpportunity:
    principle_uid: str
    principle_name: str
    activity_type: str   # "task", "event", "goal", "habit"
    activity_uid: str
    activity_title: str
    opportunity_type: str  # "direct_alignment", "practice_context", "reflection_trigger"
    guidance: str
```

Used by `PrinciplesPlanningService.get_principle_practice_opportunities_for_user()`. This is the only planning method that does NOT use a factory classmethod — it constructs a different type entirely.


## Integration with UserContextIntelligence

**Location:** `core/services/user/intelligence/` (modular package)

The Context-First types are the output of intelligence methods. The 8 flagship methods produce `DailyWorkPlan`, `LifePathAlignment`, and other aggregate types that contain `ContextualTask`, `ContextualHabit`, `ContextualGoal`, and `ContextualKnowledge` instances.

### DailyWorkPlan (THE FLAGSHIP OUTPUT)

```python
@dataclass(frozen=True)
class DailyWorkPlan:
    # Contextual items (enriched with user context via factories)
    contextual_tasks: tuple[ContextualTask, ...]
    contextual_habits: tuple[ContextualHabit, ...]
    contextual_goals: tuple[ContextualGoal, ...]
    contextual_knowledge: tuple[ContextualKnowledge, ...]

    # Capacity metrics
    estimated_time_minutes: int = 0
    fits_capacity: bool = True
    workload_utilization: float = 0.0
```

**Flow:**
```
UserContext (MEGA-QUERY)
    → Planning Services call factory classmethods
    → ContextualTask/Goal/Habit/Knowledge instances
    → DailyWorkPlan aggregates ranked items
    → UserContextIntelligence.get_ready_to_work_on_today()
    → UI renders personalized daily plan
```


## Complete Call Site Reference

| # | Service | Method | Factory | Key Overrides |
|---|---------|--------|---------|---------------|
| 1 | context_first_mixin | `_enrich_task_with_context` | ContextualTask | — |
| 2 | context_first_mixin | `_enrich_goal_with_context` | ContextualGoal | — |
| 3 | context_first_mixin | `_enrich_habit_with_context` | ContextualHabit | — |
| 4 | context_first_mixin | `_enrich_knowledge_with_context` | ContextualKnowledge | — |
| 5 | planning_mixin | `get_at_risk_habits_for_user` | ContextualHabit | readiness=1.0, relevance=0.9, priority=0.95 |
| 6 | planning_mixin | `get_upcoming_events_for_user` | ContextualEvent | days_until |
| 7 | planning_mixin | `get_actionable_tasks_for_user` | ContextualTask | overdue boost |
| 8 | planning_mixin | `get_advancing_goals_for_user` | ContextualGoal | progress, at-risk |
| 9 | planning_mixin | `get_pending_decisions_for_user` | ContextualChoice | priority_level |
| 10 | planning_mixin | `get_aligned_principles_for_user` | ContextualPrinciple | alignment_score |
| 11 | tasks_planning | `get_task_dependencies_for_user` | ContextualTask | — |
| 12 | tasks_planning | `get_actionable_tasks_for_user` | ContextualTask | readiness filter |
| 13 | tasks_planning | `get_learning_tasks_for_user` | ContextualTask | readiness=0.8, priority=impact |
| 14 | goals_planning | `get_advancing_goals_for_user` | ContextualGoal | — |
| 15 | goals_planning | `get_stalled_goals_for_user` | ContextualGoal | priority=0.7*(1-progress) |
| 16 | goals_planning | `get_achievable_goals_for_user` | ContextualGoal | readiness=1.0, priority=progress*1.2 |
| 17 | habits_planning | `get_habit_priorities_for_user` | ContextualHabit | weights=(0.3,0.3,0.4) |
| 18 | habits_planning | `get_actionable_habits_for_user` | ContextualHabit | urgency-heavy + keystone |
| 19 | habits_planning | `get_learning_habits_for_user` | ContextualHabit | priority=learning_impact |
| 20 | habits_planning | `get_goal_supporting_habits_for_user` | ContextualHabit | priority=goal_support |
| 21 | habits_planning | `get_habit_readiness_for_user` | ContextualHabit | readiness=streak/7 |
| 22 | principles_planning | `get_principles_needing_attention` | ContextualPrinciple | attention path |
| 23 | principles_planning | `get_contextual_principles` | ContextualPrinciple | relevance=accumulated |
| 24 | ku_graph | `get_ready_to_learn_for_user` | ContextualKnowledge | weights=(0.5,0.3,0.2) |
| 25 | ku_graph | `get_learning_gaps_for_user` | ContextualKnowledge | 2D weights=(0.4,0.6) |
| 26 | ku_graph | `get_knowledge_to_reinforce` | ContextualKnowledge | readiness=0.9 |

**Exception (stays direct):** `principles_planning_service.get_principle_practice_opportunities_for_user()` constructs `PracticeOpportunity` (different type, not ContextualEntity).


## Key Implementation Files

| File | Purpose |
|------|---------|
| `core/models/context_types.py` | Scoring engine + 7 types + factories (canonical) |
| `core/services/context_first_mixin.py` | 4 enrichment adapters → factory delegation |
| `core/services/relationships/planning_mixin.py` | 6 methods → factory delegation |
| `core/services/tasks/tasks_planning_service.py` | 3 task planning methods |
| `core/services/goals/goals_planning_service.py` | 3 goal planning methods |
| `core/services/habits/habits_planning_service.py` | 5 habit planning methods |
| `core/services/principles/principles_planning_service.py` | 2 principle planning methods + 1 direct |
| `core/services/ku/ku_graph_service.py` | 3 knowledge planning methods |
| `core/utils/sort_functions.py` | Sorting helpers (`get_priority_score`, etc.) |
| `core/services/infrastructure/` | `PrerequisiteHelper` (shared by tasks/scheduling) |


## Implementation History

| Version | Date | Change |
|---------|------|--------|
| 1.0.0 | November 2025 | Original design: manual scoring in `_enrich_with_context()`, inline formulas |
| 1.1.0 | January 2026 | Protocol compliance update, package restructuring |
| **2.0.0** | **February 2026** | **Harmonized scoring engine + factory classmethods. 18 construction sites consolidated into 7 factory methods. One scoring engine, parameterized for all domains.** |

**See also:**
- `/docs/architecture/UNIFIED_USER_ARCHITECTURE.md` — UserContext architecture
- `/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md` — Intelligence service catalog
- `/docs/patterns/protocol_architecture.md` — Protocol-based architecture
