---
title: Habits Domain
created: 2025-12-04
updated: 2026-01-19
status: current
category: domains
tags:
- habits
- activity-domain
- domain
related_skills:
- activity-domains
---

# Habits Domain

**Type:** Activity Domain (3 of 6)
**UID Prefix:** `habit:`
**Entity Label:** `Habit`
**Config:** `HABITS_CONFIG` (from `core.models.relationship_registry`)

## Purpose

**Skill:** [@activity-domains](../../.claude/skills/activity-domains/SKILL.md)

Habits represent recurring behaviors with streak tracking. They form the "system" that supports goal achievement (per James Clear's Atomic Habits philosophy).

## Key Files

| Component | Location |
|-----------|----------|
| Model | `/core/models/habit/habit.py` |
| DTO | `/core/models/habit/habit_dto.py` |
| Request Models | `/core/models/habit/habit_request.py` |
| Relationships | `/core/models/habit/habit_relationships.py` |
| Core Service | `/core/services/habits/habits_core_service.py` |
| Search Service | `/core/services/habits/habit_search_service.py` |
| Completion Service | `/core/services/habits/habits_completion_service.py` |
| Progress Service | `/core/services/habits/habits_progress_service.py` |
| Planning Service | `/core/services/habits/habits_planning_service.py` |
| Scheduling Service | `/core/services/habits/habits_scheduling_service.py` |
| Intelligence Service | `/core/services/habits/habits_intelligence_service.py` |
| Learning Service | `/core/services/habits/habits_learning_service.py` |
| Achievement Service | `/core/services/habits/habit_achievement_service.py` |
| Facade | `/core/services/habits_service.py` |
| Config | `HABITS_CONFIG` in `/core/models/relationship_registry.py` |
| Events | `/core/events/habit_events.py` |
| UI Routes | `/adapters/inbound/habits_ui.py` |
| View Components | `/components/habits_views.py` |

## Facade Pattern (January 2026)

`HabitsService` uses `FacadeDelegationMixin` with signature preservation for clean delegation to 11 specialized sub-services:

```python
class HabitsService(FacadeDelegationMixin, BaseService[HabitsOperations, Habit]):
    _delegations = merge_delegations(
        {"get_habit": ("core", "get_habit"), ...},              # Core CRUD
        {"search_habits": ("search", "search"), ...},           # Search
        create_relationship_delegations("habit"),                # Relationships
        {"record_completion": ("completion", ...), ...},        # Completion
        {"get_habit_with_context": ("intelligence", ...), ...}, # Intelligence
        {"get_habit_priorities_for_user": ("planning", ...), ...},  # Planning
        {"check_habit_capacity": ("scheduling", ...), ...},     # Scheduling
    )
```

**Sub-services:**
| Service | Purpose |
|---------|---------|
| `core` | CRUD operations, habit configuration |
| `search` | Text search, filtering, graph-aware queries |
| `progress` | Streaks, consistency, keystone habits |
| `completions` | Record completions, track daily progress |
| `learning` | Learning path integration |
| `planning` | Context-aware habit recommendations (January 2026) |
| `scheduling` | Smart scheduling and capacity management (January 2026) |
| `relationships` | Cross-domain links via `UnifiedRelationshipService` |
| `intelligence` | Pattern analysis, habit stacking recommendations |
| `events` | Cross-domain event scheduling integration |
| `achievements` | Achievement badge awarding (Phase 4) |

Created via `create_common_sub_services()` factory in facade `__init__`.

## Model Fields

| Field | Type | Description |
|-------|------|-------------|
| `uid` | `str` | Unique identifier |
| `user_uid` | `str` | Owner user |
| `title` | `str` | Habit title |
| `description` | `str?` | Habit description |
| `frequency` | `HabitFrequency` | Daily, Weekly, etc. |
| `target_count` | `int` | Target completions per period |
| `current_streak` | `int` | Current streak count |
| `best_streak` | `int` | Best streak achieved |
| `completion_rate` | `float` | Historical completion rate (0.0-1.0) |
| `is_active` | `bool` | Whether habit is active |
| `priority` | `Priority` | Low, Medium, High, Urgent |
| `cue` | `str?` | Habit cue (trigger) |
| `craving` | `str?` | What the habit satisfies |
| `response` | `str?` | The habit action |
| `reward` | `str?` | The habit reward |

## Relationships

### Outgoing (Habit → Other)

| Key | Relationship | Target | Description |
|-----|--------------|--------|-------------|
| `knowledge` | `REINFORCES_KNOWLEDGE` | Ku | Knowledge reinforced by habit |
| `principles` | `EMBODIES_PRINCIPLE` | Principle | Principles embodied |
| `supported_goals` | `SUPPORTS_GOAL` | Goal | Goals supported |

### Incoming (Other → Habit)

| Key | Relationship | Source | Description |
|-----|--------------|--------|-------------|
| `prerequisite_habits` | `REQUIRES_PREREQUISITE_HABIT` | Habit | Required prerequisite habits |
| `reinforcing_habits` | `REINFORCES_HABIT` | Habit | Habits that reinforce this one |
| `enabling_habits` | `ENABLES_HABIT` | Habit | Habits that enable this one |

## Cross-Domain Mappings

| Field | Target Label | Relationships |
|-------|--------------|---------------|
| `knowledge` | Ku | `REINFORCES_KNOWLEDGE` |
| `goals` | Goal | `SUPPORTS_GOAL` |
| `principles` | Principle | `EMBODIES_PRINCIPLE` |
| `prerequisites` | Habit | `REQUIRES_PREREQUISITE_HABIT` |

## Query Intent

**Default:** `QueryIntent.PRACTICE`

| Context | Intent |
|---------|--------|
| `context` | `PRACTICE` |
| `practice` | `PRACTICE` |
| `impact` | `HIERARCHICAL` |

## MEGA-QUERY Sections

- `active_habit_uids` - Active habit UIDs
- `habit_metadata` - Streak and rate per habit `{uid, streak, rate}`
- `habit_streaks` - Current streaks dict
- `habit_completion_rates` - Completion rates dict
- `active_habits_rich` - Full habit data with graph context

## Habit Loop (Atomic Habits)

The habit model tracks all four components of the habit loop:

| Component | Field | Description |
|-----------|-------|-------------|
| **Cue** | `cue` | The trigger that initiates the behavior |
| **Craving** | `craving` | The motivation behind the habit |
| **Response** | `response` | The actual behavior/action |
| **Reward** | `reward` | The benefit received |

## Scoring Weights

| Factor | Weight | Description |
|--------|--------|-------------|
| `consistency` | 0.4 | Streak and completion rate |
| `goals` | 0.3 | Goal support strength |
| `knowledge` | 0.2 | Knowledge reinforcement |
| `habits` | 0.1 | Related habit support |
| `tasks` | 0.0 | Not directly related to tasks |

## Search Methods

**Service:** `HabitsSearchService` (`/core/services/habits/habit_search_service.py`)

### Inherited from BaseService

| Method | Description |
|--------|-------------|
| `search(query, user_uid)` | Text search across title, description, cue, routine, reward |
| `get_by_status(status, user_uid)` | Filter by status |
| `get_by_domain(domain, user_uid)` | Filter by Domain |
| `get_by_category(category, user_uid)` | Filter by frequency (category_field) |
| `get_by_relationship(related_uid, rel, dir)` | Graph traversal |
| `graph_aware_faceted_search(request)` | Unified search with graph context |

### Domain-Specific Methods

| Method | Description |
|--------|-------------|
| `get_by_frequency(frequency, user_uid)` | Filter by frequency (daily/weekly/etc) |
| `get_by_streak_status(min_streak, user_uid)` | Filter by streak length |
| `get_active_habits(user_uid)` | Active habits only |
| `get_habits_needing_attention(user_uid)` | Broken streaks or declining |
| `get_reinforcing_knowledge(ku_uid, user_uid)` | Habits reinforcing a KU |
| `get_supporting_goal(goal_uid, user_uid)` | Habits supporting a goal |
| `intelligent_search(query, user_uid, context)` | AI-enhanced search |
| `get_habits_by_time_of_day(time, user_uid)` | Morning/afternoon/evening habits |
| `get_habit_chain_candidates(habit_uid, user_uid)` | Potential habit stacking |
| `get_knowledge_reinforcement_opportunities(user_uid)` | KU-habit connection opportunities |
| `get_prioritized(user_uid, limit=10)` | Smart prioritization |

**Full catalog:** [Search Service Methods Reference](/docs/reference/SEARCH_SERVICE_METHODS.md)

## Intelligence Service

`HabitsIntelligenceService` provides habit analysis and insights:

| Method | Description |
|--------|-------------|
| `get_habit_with_context(uid)` | Habit with full graph neighborhood |
| `analyze_habit_patterns(user_uid)` | Pattern analysis for all habits |
| `get_stacking_recommendations(uid)` | Habit stacking suggestions |
| `identify_at_risk_habits(user_uid)` | Habits with declining streaks |

**See:** [Intelligence Services Index](/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md)

## Planning Service (January 2026)

`HabitsPlanningService` provides context-aware habit recommendations based on UserContext (~240 fields).

**Philosophy:** "Filter by readiness, rank by relevance, enrich with insights"

### Methods

| Method | Description |
|--------|-------------|
| `get_habit_priorities_for_user(context)` | Habits ranked by urgency (streak risk) and importance |
| `get_actionable_habits_for_user(context)` | Habits due today that haven't been completed |
| `get_learning_habits_for_user(context)` | Habits that reinforce knowledge being learned |
| `get_goal_supporting_habits_for_user(context)` | Habits that contribute to active goals |
| `get_habit_readiness_for_user(habit_uid, context)` | Readiness assessment with blocking reasons |

### Habits-Specific Scoring

| Factor | Calculation | Description |
|--------|-------------|-------------|
| **Urgency** | `(streak_factor × 0.3) + (at_risk_factor × 0.7)` | Based on streak risk |
| **Readiness** | `1.0` if scheduled for today, `0.0` otherwise | Based on frequency pattern |
| **Relevance** | Goal support + identity alignment + keystone status | Based on alignment |

### Prerequisites

Unlike tasks which require knowledge mastery, habits require **prerequisite habits** to be established (streak >= 7 days).

## Scheduling Service (January 2026)

`HabitsSchedulingService` provides smart habit scheduling, frequency optimization, and capacity management.

**Pattern Source:** `EventsSchedulingService` + `TasksSchedulingService`

### Methods

| Method | Description |
|--------|-------------|
| `check_habit_capacity(user_uid)` | Can user handle another habit? (effort load check) |
| `create_habit_with_context(data, context)` | Context-validated habit creation with capacity checking |
| `create_habit_with_learning_context(data, position, context)` | Create habit aligned with learning path |
| `suggest_habit_frequency(user_uid, category)` | Recommend optimal frequency based on history |
| `optimize_habit_schedule(habit_uid, context)` | Suggest schedule adjustments based on patterns |
| `suggest_habit_stacking(user_uid)` | Find established habits to stack with (James Clear pattern) |
| `create_habit_from_learning_step(step_uid, context)` | Generate practice habit from curriculum |
| `get_habit_load_by_day(user_uid)` | Calculate effort distribution across the week |

### Habit Load Capacity

Unlike Events which check calendar conflicts, Habits checks **effort load**:

```python
# Each habit has an effort score based on difficulty + duration
effort = base_difficulty_score × max(1, duration_minutes / 15)

# Users have maximum load capacity (default: 25)
remaining_capacity = max_load - sum(active_habit_efforts)
can_add = proposed_effort <= remaining_capacity
```

### Habit Stacking (James Clear Pattern)

"After [CURRENT HABIT], I will [NEW HABIT]"

Finds established habits (streak >= 7 days) that can serve as anchors:
- Same preferred time (or close)
- Complementary category (not duplicate)
- High success rate

## Events/Publishing

The Habits domain publishes domain events for cross-service communication:

| Event | Trigger | Data |
|-------|---------|------|
| `HabitCreated` | Habit created | `habit_uid`, `user_uid`, `title` |
| `HabitCompleted` | Daily completion recorded | `habit_uid`, `user_uid`, `completion_date` |
| `HabitStreakBroken` | Streak reset to zero | `habit_uid`, `user_uid`, `previous_streak` |
| `HabitMissed` | Expected completion missed | `habit_uid`, `user_uid`, `missed_date` |

**Event handling:** Other services subscribe to these events (e.g., UserContext invalidation, goal progress updates, knowledge substance updates).

## UI Routes

### Three-View Dashboard

| Route | Method | Description |
|-------|--------|-------------|
| `/habits` | GET | Main dashboard with List/Create/Analytics tabs |
| `/habits?view=list` | GET | List view (default) |
| `/habits?view=create` | GET | Create habit form |
| `/habits?view=analytics` | GET | Habit analytics |

### HTMX Fragments

| Route | Method | Description |
|-------|--------|-------------|
| `/habits/view/list` | GET | List view fragment |
| `/habits/view/create` | GET | Create form fragment |
| `/habits/view/analytics` | GET | Analytics fragment |
| `/habits/list-fragment` | GET | Filtered list for updates |
| `/habits/quick-add` | POST | Create habit via form |

### Detail Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/habits/{uid}` | GET | View habit detail |
| `/habits/{uid}/edit` | GET/POST | Edit habit |
| `/habits/{uid}/complete` | POST | Record completion |
| `/habits/{uid}/streak` | GET | View streak history |

## Code Examples

### Create a Habit

```python
from core.models.ku.ku_request import KuHabitCreateRequest as HabitCreateRequest
from core.models.enums.scheduling_enums import RecurrencePattern

result = await habits_service.create_habit(
    HabitCreateRequest(
        title="Morning Reading",
        description="Read for 30 minutes each morning",
        frequency=RecurrencePattern.DAILY,
        target_count=1,
        cue="After morning coffee",
        craving="Knowledge and calm start",
        response="Read current book",
        reward="Check off habit, feel accomplished",
    ),
    user_uid=user_uid,
)
habit = result.value
```

### Record Completion

```python
from datetime import date

result = await habits_service.record_completion(
    habit_uid=habit.uid,
    completion_date=date.today(),
    notes="Finished chapter 5 of Atomic Habits",
)
```

### Link Habit to Goal

```python
result = await habits_service.link_habit_to_goal(
    habit_uid=habit.uid,
    goal_uid="goal.read-24-books",
    essentiality="essential",  # essential, critical, supporting, optional
)
```

### Get Habit Stacking Recommendations

```python
result = await habits_service.intelligence.get_stacking_recommendations(
    habit_uid=habit.uid,
)
recommendations = result.value
# Returns habits that could be "stacked" before/after this habit
```

### Get Prioritized Habits for Today (Planning Service)

```python
# Get habits ranked by urgency and importance
result = await habits_service.get_habit_priorities_for_user(
    context=user_context,
    limit=10,
)
prioritized_habits = result.value
# Returns ContextualHabit objects with:
# - readiness_score, relevance_score, priority_score
# - is_at_risk, is_keystone, current_streak
# - supports_goals, applies_knowledge
```

### Check Habit Capacity (Scheduling Service)

```python
# Before creating a new habit, check if user has capacity
capacity = await habits_service.check_habit_capacity(
    user_uid=user_uid,
    proposed_difficulty=HabitDifficulty.MODERATE,
    proposed_duration=15,
)

if capacity.value["can_add_habit"]:
    # User has room for another habit
    pass
else:
    print(f"Load: {capacity.value['load_percentage']}%")
    print(capacity.value["recommendations"])
```

### Suggest Habit Stacking (Scheduling Service)

```python
# Find established habits to stack with a new habit
result = await habits_service.suggest_habit_stacking(
    user_uid=user_uid,
    new_habit_time="morning",
    new_habit_category=HabitCategory.LEARNING,
)

for suggestion in result.value:
    print(f'After "{suggestion["anchor_habit_name"]}", I will [NEW HABIT]')
    print(f"  Stacking score: {suggestion['stacking_score']}")
```

## See Also

- [Goals Domain](goals.md) - Habits support goals
- [Principles Domain](principles.md) - Habits embody principles
- [Knowledge (KU) Domain](ku.md) - Habits reinforce knowledge
