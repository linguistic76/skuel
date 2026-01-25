---
title: Goals Domain
created: 2025-12-04
updated: 2026-01-19
status: current
category: domains
tags: [goals, activity-domain, domain]
---

# Goals Domain

**Type:** Activity Domain (2 of 6)
**UID Prefix:** `goal:`
**Entity Label:** `Goal`
**Config:** `GOAL_CONFIG`

## Purpose

Goals represent desired outcomes that guide learning and habit formation. They provide direction for tasks, habits, and knowledge acquisition.

## Key Files

| Component | Location |
|-----------|----------|
| Model | `/core/models/goal/goal.py` |
| DTO | `/core/models/goal/goal_dto.py` |
| Request Models | `/core/models/goal/goal_request.py` |
| Relationships | `/core/models/goal/goal_relationships.py` |
| Core Service | `/core/services/goals/goals_core_service.py` |
| Search Service | `/core/services/goals/goals_search_service.py` |
| Progress Service | `/core/services/goals/goals_progress_service.py` |
| Learning Service | `/core/services/goals/goals_learning_service.py` |
| Planning Service | `/core/services/goals/goals_planning_service.py` |
| Scheduling Service | `/core/services/goals/goals_scheduling_service.py` |
| Intelligence Service | `/core/services/goals/goals_intelligence_service.py` |
| Recommendation Service | `/core/services/goals/goals_recommendation_service.py` |
| Facade | `/core/services/goals_service.py` |
| Config | `GOAL_CONFIG` in `/core/services/relationships/domain_configs.py` |
| Events | `/core/events/goal_events.py` |
| UI Routes | `/adapters/inbound/goals_ui.py` |
| View Components | `/components/goals_views.py` |

## Facade Pattern (January 2026)

`GoalsService` uses `FacadeDelegationMixin` with signature preservation for clean delegation to 8 specialized sub-services:

```python
class GoalsService(FacadeDelegationMixin, BaseService[GoalsOperations, Goal]):
    _delegations = merge_delegations(
        {"get_goal": ("core", "get_goal"), ...},                # Core CRUD
        {"search_goals": ("search", "search"), ...},            # Search
        create_relationship_delegations("goal"),                 # Relationships
        {"check_goal_capacity": ("scheduling", ...), ...},      # Scheduling
        {"get_goal_with_context": ("intelligence", ...), ...},  # Intelligence
    )
```

**Sub-services:**
| Service | Purpose |
|---------|---------|
| `core` | CRUD operations, status transitions |
| `search` | Text search, filtering, graph-aware queries |
| `progress` | Progress tracking and milestones |
| `learning` | Learning path integration |
| `planning` | Context-first planning methods |
| `scheduling` | Capacity management, timeline optimization (January 2026) |
| `relationships` | Cross-domain links via `UnifiedRelationshipService` |
| `intelligence` | Analytics, predictions, dual-track assessment |
| `recommendations` | Event-driven goal recommendations |

Created via `create_common_sub_services()` factory in facade `__init__`.

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
| `milestones` | `HAS_MILESTONE` | Milestone | Goal milestones |
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
- `active_goals_rich` - Full goal data with graph context

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
| `get_by_domain(domain, user_uid)` | Filter by Domain |
| `get_by_category(category, user_uid)` | Filter by domain (category_field) |
| `get_by_relationship(related_uid, rel, dir)` | Graph traversal |
| `graph_aware_faceted_search(request)` | Unified search with graph context |

### Domain-Specific Methods

| Method | Description |
|--------|-------------|
| `get_by_priority(priority, user_uid)` | Filter by priority |
| `get_by_progress(min, max, user_uid)` | Filter by progress range |
| `get_by_milestone_status(status, user_uid)` | Filter by milestone status |
| `get_active_goals(user_uid)` | Active goals only |
| `get_goals_needing_attention(user_uid)` | Stalled or at-risk goals |
| `get_goals_with_tasks(user_uid)` | Goals with linked tasks |
| `get_aligned_with_principle(principle_uid, user_uid)` | Goals aligned with principle |
| `intelligent_search(query, user_uid, context)` | AI-enhanced search |
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

## Intelligence Service

`GoalsIntelligenceService` provides goal analysis and insights:

| Method | Description |
|--------|-------------|
| `get_goal_with_context(uid)` | Goal with full graph neighborhood |
| `analyze_goal_progress(uid)` | Detailed progress analysis |
| `get_achievement_recommendations(user_uid)` | Recommendations to achieve goals |
| `identify_blocking_factors(uid)` | Identify what's blocking goal progress |

**See:** [Intelligence Services Index](/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md)

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

### Three-View Dashboard

| Route | Method | Description |
|-------|--------|-------------|
| `/goals` | GET | Main dashboard with List/Create/Analytics tabs |
| `/goals?view=list` | GET | List view (default) |
| `/goals?view=create` | GET | Create goal form |
| `/goals?view=analytics` | GET | Goal analytics |

### HTMX Fragments

| Route | Method | Description |
|-------|--------|-------------|
| `/goals/view/list` | GET | List view fragment |
| `/goals/view/create` | GET | Create form fragment |
| `/goals/view/analytics` | GET | Analytics fragment |
| `/goals/list-fragment` | GET | Filtered list for updates |
| `/goals/quick-add` | POST | Create goal via form |

### Detail Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/goals/{uid}` | GET | View goal detail |
| `/goals/{uid}/edit` | GET/POST | Edit goal |
| `/goals/{uid}/progress` | POST | Update progress |
| `/goals/{uid}/milestones` | GET | View milestones |

## Code Examples

### Create a Goal

```python
from core.models.goal.goal_request import GoalCreateRequest
from core.models.goal.goal import GoalType, GoalTimeframe
from core.models.shared_enums import Priority

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
