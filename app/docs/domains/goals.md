---
title: Goals Domain
created: 2025-12-04
updated: 2026-04-11
status: current
category: domains
tags:
- goals
- activity-domain
- domain
related_skills:
- activity-domains
---

# Goals Domain

**Type:** Activity Domain (2 of 6)
**UID Prefix:** `goal:`
**Entity Label:** `Goal`
**Config:** `GOAPS_CONFIG` (from `core.models.relationship_registry`)

## Purpose

**Skill:** [@activity-domains](../../.claude/skills/activity-domains/SKILL.md)

Goals represent desired outcomes that guide learning and habit formation. They provide direction for tasks, habits, and knowledge acquisition.

## Key Files

| Component | Location |
|-----------|----------|
| Model | `/core/models/goal/goal.py` |
| DTO | `/core/models/goal/goal_dto.py` |
| Request Models | `/core/models/goal/goal_request.py` |
| Relationships | `/core/services/goals/goal_relationships.py` |
| **Backend** | `/adapters/persistence/neo4j/backends/activity_backends.py` (`GoalsBackend`) |
| Core Service | `/core/services/goals/goals_core_service.py` |
| Search Service | `/core/services/goals/goals_search_service.py` |
| Progress Service | `/core/services/goals/goals_progress_service.py` |
| Learning Service | `/core/services/goals/goals_learning_service.py` |
| Planning Service | `/core/services/goals/goals_planning_service.py` |
| Scheduling Service | `/core/services/goals/goals_scheduling_service.py` |
| Intelligence Service | `/core/services/goals/goals_intelligence_service.py` |
| Event Handler Service | `/core/services/goals/goal_event_handler_service.py` |
| Facade | `/core/services/goals_service.py` |
| Config | `GOAPS_CONFIG` in `/core/models/relationship_registry.py` |
| Events | `/core/events/goal_events.py` |
| UI Routes | `/adapters/inbound/goals_ui.py` |
| View Components | `/ui/goals/views.py` |

## Domain Enums

| Enum | Import | Values | YAML Field |
|------|--------|--------|------------|
| `GoalType` | `core.models.enums` | OUTCOME, PROCESS, LEARNING, PROJECT, MILESTONE, MASTERY | `goal_type` |
| `GoalTimeframe` | `core.models.enums` | DAILY, WEEKLY, MONTHLY, QUARTERLY, YEARLY, MULTI_YEAR | `timeframe` |
| `MeasurementType` | `core.models.enums` | BINARY, PERCENTAGE, NUMERIC, MILESTONE, HABIT_BASED, KNOWLEDGE_BASED, TASK_BASED, MIXED | `measurement_type` |
| `HabitEssentiality` | `core.models.enums` | ESSENTIAL, CRITICAL, SUPPORTING, OPTIONAL | — (goal-habit link weight) |
| `Priority` | `core.models.enums` | LOW, MEDIUM, HIGH, CRITICAL | `priority` |

**See:** [Enum Architecture](/docs/architecture/ENUM_ARCHITECTURE.md)

## Facade Pattern (February 2026, mixins April 2026)

`GoalsService` delegates to sub-services + 1 focused facade mixin for orchestration:

```python
class GoalsService(
    _OrchestrationMixin,    # cross-domain orchestration (create_goal_with_context, etc.)
    KnowledgeIntelligenceDelegationMixin,
    BaseService[GoalsOperations, Goal],
):
    # Delegation methods delegate to the sub-services below
    async def get_goal(self, uid: str) -> Result[Goal]:
        return await self.core.get_goal(uid)
```

**Facade Mixin** (`core/services/goals/`):

| Mixin | File | Methods |
|-------|------|---------|
| `_OrchestrationMixin` | `_orchestration_mixin.py` | `create_goal_with_context`, `generate_tasks_for_goal`, `assess_goal_feasibility` |

Graph relationship methods (`create_user_goal_relationship`, `link_goal_to_habit/knowledge/principle`, `unlink_goal_from_habit`, `create_semantic_goal_relationship`, `find_goals_requiring_knowledge`) are inline on `GoalsService` directly — inlined June 2026 per the decomposition floor rule.

**Sub-services:**
| Service | Purpose |
|---------|---------|
| `core` | CRUD operations, status transitions (takes `cross_domain_query` for goal-abandonment guard) |
| `search` | Text search, filtering, graph-aware queries |
| `progress` | Progress tracking and milestones |
| `learning` | Learning path integration |
| `planning` | Context-first planning methods |
| `scheduling` | Capacity management, timeline optimization (January 2026) |
| `relationships` | Cross-domain links via `UnifiedRelationshipService` |
| `intelligence` | Analytics, predictions, dual-track assessment (decomposed into 5 mixins — see below) |
| `event_handler` | Event-driven reactive handlers (achievements, abandonment, progress) |

Created via `create_common_sub_services()` factory in facade `__init__` (core, intelligence, planning, and scheduling skipped — built manually with extra dependencies).

## Event Handler — Insight Persistence (March 2026)

`GoalEventHandlerService` handles fire-and-forget reactive logic and persists structured insights to `InsightStore`:

| Handler | Trigger | InsightType | Impact |
|---------|---------|------------|--------|
| `handle_goal_abandoned` | All abandonments | `COMPLETION_PATTERN` | HIGH (near-miss) / MEDIUM |
| `handle_goal_progress_updated` | `progress_delta < 0.01` | `IMBALANCE_DETECTED` | MEDIUM |
| `handle_goal_progress_updated` | Within 5% of 25/50/75/100% | `COMPLETION_PATTERN` | LOW |

Also handles: recommendation generation (via `backend.get_achievement_context()` — a `GoalsOperations` protocol method that fetches goal properties + related Kus/habits/principles), duration calibration, principle alignment, cross-domain trigger logging.

## Model Fields

| Field | Type | Description |
|-------|------|-------------|
| `uid` | `str` | Unique identifier |
| `user_uid` | `str` | Owner user |
| `title` | `str` | Goal title |
| `description` | `str?` | Goal description |
| `goal_type` | `GoalType` | Outcome, Process, Learning, Project, Milestone, Mastery |
| `timeframe` | `GoalTimeframe` | Daily, Weekly, Monthly, Quarterly, Yearly, Multi-year |
| `status` | `GoalStatus` | Not Started, In Progress, Completed, etc. |
| `priority` | `Priority` | Low, Medium, High, Urgent |
| `target_date` | `date?` | Target completion date |
| `progress` | `float` | Progress percentage (0.0-1.0) |
| `measurement_type` | `MeasurementType` | Binary, Percentage, Numeric, Milestone, etc. |
| `domain` | `Domain` | TECH, HEALTH, PERSONAL, etc. |

## Relationships

### Outgoing (Goal → Other)

| Key | Relationship | Target | Description |
|-----|--------------|--------|-------------|
| `knowledge` | `REQUIRES_KNOWLEDGE` | Ku | Knowledge required for goal |
| `principles` | `GUIDED_BY_PRINCIPLE` | Principle | Guiding principles |
| `aligned_paths` | `ALIGNED_WITH_PATH` | Lp | Aligned learning paths |
| `required_paths` | `REQUIRES_PATH_COMPLETION` | Lp | Required learning paths |
| `parent_goal` | `SUBGOAL_OF` | Goal | Parent goal |

### Incoming (Other → Goal)

| Key | Relationship | Source | Description |
|-----|--------------|--------|-------------|
| `subgoals` | `SUBGOAL_OF` | Goal | Child goals |
| `supporting_habits` | `SUPPORTS_GOAL` | Habit | Habits that support this goal |
| `fulfilling_tasks` | `FULFILLS_GOAL` | Task | Tasks that fulfill this goal |
| `essential_habits` | `SUPPORTS_GOAL` (essentiality=essential) | Habit | Essential habits |
| `critical_habits` | `SUPPORTS_GOAL` (essentiality=critical) | Habit | Critical habits |
| `optional_habits` | `SUPPORTS_GOAL` (essentiality=optional) | Habit | Optional habits |

### Bidirectional

- `SUBGOAL_OF` - Goal hierarchy

## Cross-Domain Mappings

| Field | Target Label | Relationships |
|-------|--------------|---------------|
| `tasks` | Task | `FULFILLS_GOAL` |
| `habits` | Habit | `SUPPORTS_GOAL` |
| `knowledge` | Ku | `REQUIRES_KNOWLEDGE` |
| `subgoals` | Goal | `SUBGOAL_OF` |
| `principles` | Principle | `GUIDED_BY_PRINCIPLE` |

## Query Intent

**Default:** `QueryIntent.GOAL_ACHIEVEMENT`

| Context | Intent |
|---------|--------|
| `context` | `GOAL_ACHIEVEMENT` |
| `achievement` | `GOAL_ACHIEVEMENT` |
| `impact` | `HIERARCHICAL` |

## MEGA-QUERY Sections

- `active_goal_uids` - Active goal UIDs
- `completed_goal_uids` - Completed goal UIDs
- `goal_progress` - Progress per goal `{uid, progress}`
- `entities_rich["goals"]` - Full goal data with graph context

## Goal Types

| Type | Description |
|------|-------------|
| `OUTCOME` | Result-focused (achieve X) |
| `PROCESS` | Activity-focused (do Y consistently) |
| `LEARNING` | Knowledge/skill acquisition |
| `PROJECT` | Complete a specific project |
| `MILESTONE` | Reach a specific milestone |
| `MASTERY` | Master a domain/skill |

## Habit Essentiality

Goals track which habits are essential for achievement:

| Essentiality | Meaning |
|--------------|---------|
| `ESSENTIAL` | Goal is impossible without this habit |
| `CRITICAL` | Goal is very difficult without this habit |
| `SUPPORTING` | Goal is easier with this habit |
| `OPTIONAL` | Habit is tangentially helpful |

## Search Methods

**Service:** `GoalsSearchService` (`/core/services/goals/goals_search_service.py`)

### Inherited from BaseService

| Method | Description |
|--------|-------------|
| `search(query, user_uid)` | Text search across title, description, success_criteria |
| `get_by_status(status, user_uid)` | Filter by GoalStatus |
| `get_by_category(category, user_uid)` | Filter by domain (category_field) |
| `get_by_relationship(related_uid, rel, dir)` | Graph traversal |
| `graph_aware_faceted_search(request)` | Unified search with graph context |

### Domain-Specific Methods

| Method | Description |
|--------|-------------|
| `get_by_priority(priority, user_uid)` | Filter by priority |
| `get_by_progress(min, max, user_uid)` | Filter by progress range |
| `get_by_milestone_status(status, user_uid)` | Filter by milestone status |
| `get_active(user_uid)` | Active goals — inherited from `TimeQueryMixin`; excludes `completed` + `cancelled` via `completed_statuses` config |
| `get_upcoming(days_ahead, user_uid)` | Goals with `target_date` approaching — inherited |
| `get_overdue(user_uid)` | Goals past `target_date` — inherited |
| `get_goals_needing_attention(user_uid)` | Stalled or at-risk goals |
| `get_goals_with_tasks(user_uid)` | Goals with linked tasks |
| `get_aligned_with_principle(principle_uid, user_uid)` | Goals aligned with principle |
| `list_milestones(goal_uid, user_uid)` | Get goal milestones |
| `get_prioritized(user_uid, limit=10)` | Smart prioritization |

**Full catalog:** [Search Service Methods Reference](/docs/reference/SEARCH_SERVICE_METHODS.md)

## Scheduling Service (January 2026)

`GoalsSchedulingService` provides capacity management and timeline optimization:

| Method | Description |
|--------|-------------|
| `check_goal_capacity(user_uid)` | Can user handle another active goal? |
| `create_goal_with_context(data, context)` | Context-validated goal creation |
| `create_goal_with_learning_context(data, pos, context)` | Create with learning alignment |
| `suggest_goal_timeline(user_uid, type, timeframe)` | Recommend target date based on history |
| `assess_goal_achievability(goal_uid, context)` | Can goal be achieved by target date? |
| `get_schedule_aware_next_goal(context)` | Best goal to focus on now |
| `optimize_goal_sequencing(user_uid, goal_uids)` | Optimal order for multiple goals |
| `get_goal_load_by_timeframe(user_uid)` | Goal distribution across timeframes |

**Capacity Criteria:**
- Maximum active goals (default: 5)
- Priority distribution (max 1 CRITICAL, max 2 HIGH)
- Complexity scoring (type × timeframe)

**Result Types:**
- `GoalCapacityResult` - Capacity check with recommendations
- `TimelineSuggestion` - Timeline suggestions with confidence
- `AchievabilityResult` - Achievability assessment with velocity metrics
- `GoalSequenceItem` - Goal sequencing with reasoning

## Intelligence Service (decomposed April 2026)

`GoalsIntelligenceService` provides goal analysis and insights. Inherits `get_with_context`
(mechanism B) from the shared `core/services/intelligence/_CoreIntelligenceMixin` and is
decomposed into focused mixins:

| Mixin | File | Methods |
|-------|------|---------|
| `_AnalyticsMixin` | `_analytics_mixin.py` | `get_performance_analytics`, `get_domain_insights`, `get_goal_progress_dashboard`, `_generate_progress_recommendations`, `get_goal_completion_forecast`, `get_goal_learning_requirements` |
| `_PredictiveMixin` | `_predictive_mixin.py` | `predict_goal_success`, `analyze_habit_impact`, `assess_goal_risk`, `run_scenario_analysis` + private helpers |
| `_DualTrackMixin` | `_dual_track_mixin.py` | `assess_progress_dual_track`, `_calculate_system_progress`, `_progress_level_to_score`, `_generate_progress_gap_*` |

**See:** [Intelligence Services Index](/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md), [Goals Intelligence](/docs/intelligence/GOALS_INTELLIGENCE.md)

## Events/Publishing

The Goals domain publishes domain events for cross-service communication:

| Event | Trigger | Data |
|-------|---------|------|
| `GoalCreated` | Goal created | `goal_uid`, `user_uid`, `title` |
| `GoalAchieved` | Goal marked complete | `goal_uid`, `user_uid`, `achieved_at` |
| `GoalProgressUpdated` | Progress changed | `goal_uid`, `user_uid`, `old_progress`, `new_progress` |
| `GoalAbandoned` | Goal abandoned | `goal_uid`, `user_uid`, `reason` |

**Event handling:** Other services subscribe to these events (e.g., UserContext invalidation, task updates).

## UI Routes

Goals has an active read-focused UI at `/goals` with filtering and progress display.

| Route | Method | Description |
|-------|--------|-------------|
| `/goals` | GET | Read-focused goal list with filtering |
| `/goals/list-fragment` | GET | HTMX filtered list fragment |

## Code Examples

### Create a Goal

```python
from core.models.goal.goal_request import GoalCreateRequest
from core.models.goal.goal import GoalType, GoalTimeframe
from core.models.enums import Priority

result = await goals_service.create_goal(
    GoalCreateRequest(
        title="Master FastHTML Framework",
        description="Become proficient in building web apps with FastHTML",
        goal_type=GoalType.MASTERY,
        timeframe=GoalTimeframe.QUARTERLY,
        priority=Priority.HIGH,
        target_date=date.today() + timedelta(days=90),
    ),
    user_uid=user_uid,
)
goal = result.value
```

### Update Goal Progress

```python
result = await goals_service.update_progress(
    goal_uid=goal.uid,
    progress=0.6,  # 60% complete
    notes="Completed core tutorials",
)
```

### Link Goal to Principle

```python
result = await goals_service.link_goal_to_principle(
    goal_uid=goal.uid,
    principle_uid="principle.continuous-learning",
    alignment_score=0.9,
)
```

## See Also

- [Tasks Domain](tasks.md) - Tasks fulfill goals
- [Habits Domain](habits.md) - Habits support goals
- [Principles Domain](principles.md) - Principles guide goals
- [LifePath Domain](lifepath.md) - Goals serve life path
