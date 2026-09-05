---
title: Habits Domain
created: 2025-12-04
updated: 2026-09-05
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
| Relationships | `/core/services/habits/habit_relationships.py` |
| **Backend** | `/adapters/persistence/neo4j/backends/activity_backends.py` (`HabitsBackend`) |
| Core Service | `/core/services/habits/habits_core_service.py` |
| Search Service | `/core/services/habits/habit_search_service.py` |
| Completion Service | `/core/services/habits/habits_completion_service.py` |
| Completion Exporter | `/core/utils/completion_exporter.py` |
| Progress Service | `/core/services/habits/habits_progress_service.py` |
| Planning Service | `/core/services/habits/habits_planning_service.py` |
| Scheduling Service | `/core/services/habits/habits_scheduling_service.py` |
| Intelligence Service | `/core/services/habits/habits_intelligence_service.py` |
| Learning Service | `/core/services/habits/habits_learning_service.py` |
| Event Handler Service | `/core/services/habits/habit_event_handler_service.py` |
| Facade | `/core/services/habits_service.py` |
| Config | `HABITS_CONFIG` in `/core/models/relationship_registry.py` |
| Events | `/core/events/habit_events.py` |
| UI Routes | `/adapters/inbound/habits_ui.py` |
| View Components | `/ui/habits/views.py` |

## Domain Enums

| Enum | Import | Values | YAML Field |
|------|--------|--------|------------|
| `HabitPolarity` | `core.models.enums` | BUILD, BREAK, NEUTRAL | `polarity` |
| `HabitCategory` | `core.models.enums` | HEALTH, FITNESS, MINDFULNESS, LEARNING, PRODUCTIVITY, CREATIVE, SOCIAL, FINANCIAL, OTHER | `category` |
| `HabitDifficulty` | `core.models.enums` | TRIVIAL, EASY, MODERATE, CHALLENGING, HARD | `difficulty` |
| `CompletionStatus` | `core.models.enums` | DONE, PARTIAL, SKIPPED, MISSED, PAUSED | — (daily tracking) |
| `RecurrencePattern` | `core.models.enums` | DAILY, WEEKLY, MONTHLY, etc. (10 values) | `recurrence_pattern` |
| `TimeOfDay` | `core.models.enums` | EARLY_MORNING, MORNING, AFTERNOON, EVENING, NIGHT, LATE_NIGHT, ANYTIME | `preferred_time` |
| `Priority` | `core.models.enums` | LOW, MEDIUM, HIGH, CRITICAL | `priority` |

**See:** [Enum Architecture](../architecture/ENUM_ARCHITECTURE.md)

## Facade Pattern (April 2026)

`HabitsService` is SKUEL's most complex Activity Domain facade: **13 sub-services + 3 facade mixins**.

```python
class HabitsService(
    _CompletionMixin,       # track/untrack, streak/progress/history, reminders
    _EnrichmentMixin,       # analytics + enriched metadata views
    _OrchestrationMixin,    # graph relationships + cross-domain orchestration
    KnowledgeIntelligenceDelegationMixin,
    BaseService[HabitsOperations, Habit],
):
    # Delegation methods (~45) delegate to the 13 sub-services below
    async def get_habit(self, uid: str) -> Result[Habit]:
        return await self.core.get_habit(uid)

    async def complete_habit_with_quality(self, ...) -> Result[Habit]:
        return await self.progress.complete_habit_with_quality(...)

```

**Facade Mixins** (`core/services/habits/`):

| Mixin | File | Methods |
|-------|------|---------|
| `_CompletionMixin` | `_completion_mixin.py` | `track_habit`, `untrack_habit`, `get_habit_streak/progress/history`, `get_completion_calendar`, `set/get/delete_habit_reminder` |
| `_EnrichmentMixin` | `_enrichment_mixin.py` | `get_habit_analytics`, `get_habits_summary_analytics`, `get_habit_trends`, `get_enriched_learning/curriculum/prerequisite_metadata` |
| `_OrchestrationMixin` | `_orchestration_mixin.py` | `complete_with_goal_impacts`, `create_with_goal_links`, `link_habit_to_knowledge/principle`, `get_skills_developed_by_habits`, `create_habit_with_context` |

**Sub-services** (13, created in `__init__`):

| Sub-service | Purpose |
|-------------|---------|
| `core` | CRUD operations, habit configuration |
| `search` | Text search, filtering, graph-aware queries |
| `progress` | Streaks, consistency, keystone habits |
| `completions` | Record completions, track daily progress |
| `learning` | Learning path integration |
| `planning` | Context-aware habit recommendations (January 2026) |
| `scheduling` | Smart scheduling and capacity management (January 2026) |
| `relationships` | Cross-domain links via `UnifiedRelationshipService` |
| `intelligence` | Pattern analysis, habit stacking recommendations |
| `event_integration` | Cross-domain event scheduling integration |
| `event_handler` | Event-driven reactive logic (streak + aggregate badges, difficulty) |
| `patterns` | Atomic Habits pattern recognition with confidence scoring |
| `knowledge_intelligence` | Shared singleton — domain-agnostic knowledge intelligence |

Common sub-services created via `create_common_sub_services()` factory (with `skip={"intelligence"}` — Habits intelligence is created manually to receive `cross_domain_query`).

### Cross-Domain Wiring

`HabitsService.goals_service` is post-wired in `services_bootstrap.py` (circular dependency). The facade's orchestration methods (`create_with_goal_links`, `complete_with_goal_impacts`) use `self.goals_service` internally — routes do not pass cross-domain services as parameters.

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

### Derived fields (populated at fetch time, never persisted)

| Field | Edge | Populated by |
|-------|------|--------------|
| `supports_goal_uid` | `(Habit)-[:SUPPORTS_GOAL]->(Goal)` | `enrich_habits_with_goal_links()` |

The helper lives in `core/services/habits/_goal_links.py` and is called by `HabitsSearchService.get_prioritized()` before scoring so the priority scorer can read the edge-derived field rather than using streak presence as a proxy for goal linkage.

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
- `entities_rich["habits"]` - Full habit data with graph context

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
| `get_by_category(category, user_uid)` | Filter by frequency (category_field) |
| `get_by_relationship(related_uid, rel, dir)` | Graph traversal |
| `graph_aware_faceted_search(request)` | Unified search with graph context |

### Domain-Specific Methods

| Method | Description |
|--------|-------------|
| `get_by_frequency(frequency, user_uid)` | Filter by frequency (daily/weekly/etc) |
| `get_by_streak_status(min_streak, user_uid)` | Filter by streak length |
| `get_active(user_uid)` | Override of `TimeQueryMixin.get_active` — keeps PAUSED alongside ACTIVE |
| `get_upcoming(days_ahead, user_uid)` | Override — frequency-window logic, not due-date columns |
| `get_overdue(user_uid)` | Override — frequency-window logic, not due-date columns |
| `get_user_due_today(user_uid)` | Habits due today (frequency-window) |
| `get_habits_needing_attention(user_uid)` | Broken streaks or declining |
| `get_habit_chain_candidates(habit_uid, user_uid)` | Potential habit stacking |
| `get_knowledge_reinforcement_opportunities(user_uid)` | KU-habit connection opportunities |
| `get_prioritized(user_uid, limit=10)` | Smart prioritization |

**Full catalog:** [Search Service Methods Reference](../reference/SEARCH_SERVICE_METHODS.md)

## Intelligence Service

`HabitsIntelligenceService` provides habit analysis and insights:

| Method | Description |
|--------|-------------|
| `get_with_context(uid)` | Habit with full graph neighborhood (shared mechanism B) |
| `analyze_habit_patterns(user_uid)` | Pattern analysis for all habits |
| `get_stacking_recommendations(uid)` | Habit stacking suggestions |
| `identify_at_risk_habits(user_uid)` | Habits with declining streaks |

**See:** [Intelligence Services Index](../intelligence/INTELLIGENCE_SERVICES_INDEX.md)

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

### Frequency Window Logic (Due/Overdue)

Unlike deadline-based domains (Goals, Events, Choices), Habits use **backwards-looking** frequency windows to determine due/overdue status. The shared `FREQUENCY_WINDOWS_DAYS` dict and `get_frequency_window_days()` helper from `core/utils/timestamp_helpers.py` eliminate duplication across three methods:

| Frequency | Window (days) | "Due" when | "Overdue" when |
|-----------|--------------|------------|----------------|
| `daily` | 1 | `days_since_last >= 1` | `days_since_last > 1` |
| `weekly` | 7 | `days_since_last >= 7` | `days_since_last > 7` |
| `monthly` | 30 | `days_since_last >= 30` | `days_since_last > 30` |

**Methods using this logic:**
- `_is_habit_due_in_window()` — used by the `get_upcoming()` override
- `_is_habit_overdue()` — used by the `get_overdue()` override
- `get_user_due_today()` — standalone method for daily planning

**Never-completed habits** are always considered due. Unknown frequencies default to daily.

**See:** `/docs/architecture/SEARCH_ARCHITECTURE.md` → "Temporal Scoring Patterns" for how this relates to deadline proximity scoring in other domains.

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

**Pattern Source:** `TasksSchedulingService`

### Methods

| Method | Description |
|--------|-------------|
| `check_habit_capacity(user_uid)` | Can user handle another habit? (effort load check) |
| `create_habit_with_context(data, context)` | Context-validated habit creation with capacity checking |
| `suggest_habit_frequency(user_uid, category)` | Recommend optimal frequency based on history |
| `optimize_habit_schedule(habit_uid, context)` | Suggest schedule adjustments based on patterns |
| `suggest_habit_stacking(user_uid)` | Find established habits to stack with (James Clear pattern) |
| `create_habit_from_path_step(step_uid, context)` | Generate practice habit from curriculum |
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
- Same `TimeOfDay` slot, or both in the routine-anchor pair (MORNING / EVENING)
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

Read-focused UI at `/habits` is planned. API routes remain active.

## Code Examples

### Create a Habit

```python
from core.models.habit.habit_request import HabitCreateRequest
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
from datetime import datetime

result = await habits_service.completions.record_completion(
    habit_uid=habit.uid,
    user_uid=user_uid,          # required — the completion is recorded against the owner
    completed_at=datetime.now(),
    notes="Finished chapter 5 of Atomic Habits",
)
```

**`HabitCompletion` is user-owned.** `user_uid` is a required field, so the
property is written AND `_create_node` writes the
`(User)-[:OWNS]->(:HabitCompletion)` edge with it — the property==`:OWNS`
invariant every other user-owned entity holds. User-scoped reads therefore filter
`completions_backend.find_by(user_uid=...)` directly, in one query.

⚠️ **History, so the old shape is not reintroduced.** Until 2026-08-20 the field
did not exist, so neither ownership mechanism did: `find_by(user_uid=...)`
compared against null and returned **zero rows with no error** — a silent wrong
answer, not a failure. `get_today_completions` and `get_badge_progress` were
silently returning 0; `export_completion_history` had been rewritten to walk the
user's habits instead. That workaround is gone (it was an N+1 standing in for a
missing field), and a regression test pins all three reads to `user_uid` scoping.

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
