---
title: Tasks Domain
created: 2025-12-04
updated: 2026-01-11
status: current
category: domains
tags:
- tasks
- activity-domain
- domain
related_skills:
- activity-domains
---

# Tasks Domain

**Type:** Activity Domain (1 of 6)
**UID Prefix:** `task:`
**Entity Label:** `Task`
**Config:** `TASKS_CONFIG` (from `core.models.relationship_registry`)

## Purpose

**Skill:** [@activity-domains](../../.claude/skills/activity-domains/SKILL.md)

Tasks represent work items with dependencies, deadlines, and knowledge requirements. They are the primary unit of execution in SKUEL.

## Key Files

| Component | Location |
|-----------|----------|
| Model | `/core/models/task/task.py` |
| DTO | `/core/models/task/task_dto.py` |
| Request Models | `/core/models/task/task_request.py` |
| Relationships | `/core/models/task/task_relationships.py` |
| Core Service | `/core/services/tasks/tasks_core_service.py` |
| Search Service | `/core/services/tasks/tasks_search_service.py` |
| Progress Service | `/core/services/tasks/tasks_progress_service.py` |
| Scheduling Service | `/core/services/tasks/tasks_scheduling_service.py` |
| Analytics Service | `/core/services/tasks/tasks_analytics_service.py` |
| Intelligence Service | `/core/services/tasks/tasks_intelligence_service.py` |
| Facade | `/core/services/tasks_service.py` |
| Config | `TASKS_CONFIG` in `/core/models/relationship_registry.py` |
| Events | `/core/events/task_events.py` |
| UI Routes | `/adapters/inbound/tasks_ui.py` |
| View Components | `/ui/tasks/views.py` |

## Facade Pattern (February 2026)

`TasksService` uses explicit `async def` delegation methods:

```python
class TasksService(BaseService[TasksOperations, Task]):
    core: TasksCoreService
    search: TasksSearchService
    progress: TasksProgressService
    scheduling: TasksSchedulingService
    relationships: UnifiedRelationshipService
    intelligence: TasksIntelligenceService

    # Explicit delegation — MyPy-native, no mixin needed
    async def get_task(self, *args: Any, **kwargs: Any) -> Any:
        return await self.core.get_task(*args, **kwargs)

    async def analyze_task_learning_metrics(self, *args: Any, **kwargs: Any) -> Any:
        return await self.intelligence.analyze_task_learning_metrics(*args, **kwargs)
```

**Note (January 2026)**: TasksAnalyticsService removed. KU analytics methods are now direct in TasksService, Task model analysis moved to TasksIntelligenceService.

## Model Fields

| Field | Type | Description |
|-------|------|-------------|
| `uid` | `str` | Unique identifier (indexed) |
| `user_uid` | `str` | Owner user (indexed) |
| `title` | `str` | Task title |
| `description` | `str?` | Optional description |
| `due_date` | `date?` | When task is due (indexed) |
| `scheduled_date` | `date?` | When task is scheduled (indexed) |
| `completion_date` | `date?` | When task was completed |
| `duration_minutes` | `int` | Estimated duration (default: 30) |
| `actual_minutes` | `int?` | Actual time spent |
| `status` | `EntityStatus` | Draft, Active, Completed, etc. (indexed) |
| `priority` | `Priority` | Low, Medium, High, Urgent (indexed) |
| `project` | `str?` | Project grouping |
| `tags` | `tuple[str, ...]` | Tags for categorization |
| `parent_uid` | `str?` | Parent task UID |
| `recurrence_pattern` | `RecurrencePattern?` | Daily, Weekly, etc. |

## Relationships

### Outgoing (Task → Other)

| Key | Relationship | Target | Description |
|-----|--------------|--------|-------------|
| `knowledge` | `APPLIES_KNOWLEDGE` | Ku | Knowledge applied in this task |
| `prerequisite_knowledge` | `REQUIRES_KNOWLEDGE` | Ku | Knowledge required before starting |
| `principles` | `ALIGNED_WITH_PRINCIPLE` | Principle | Guiding principles |
| `enables` | `ENABLES_TASK` | Task | Tasks this enables |
| `triggers` | `TRIGGERS_ON_COMPLETION` | Task | Tasks triggered when complete |
| `unlocks_knowledge` | `UNLOCKS_KNOWLEDGE` | Ku | Knowledge unlocked by completion |
| `contributes_to_goal` | `CONTRIBUTES_TO_GOAL` | Goal | Goals this contributes to |
| `fulfills_goal` | `FULFILLS_GOAL` | Goal | Goals this fulfills |

### Incoming (Other → Task)

| Key | Relationship | Source | Description |
|-----|--------------|--------|-------------|
| `subtasks` | `HAS_CHILD` | Task | Child tasks |
| `prerequisite_tasks` | `DEPENDS_ON` | Task | Tasks that must complete first |
| `inferred_knowledge` | `INFERRED_KNOWLEDGE` | Ku | Inferred knowledge links |

### Bidirectional

- `DEPENDS_ON` - Task dependencies (both directions)

## Cross-Domain Mappings

| Field | Target Label | Relationships |
|-------|--------------|---------------|
| `prerequisites` | Task | `DEPENDS_ON` |
| `dependents` | Task | `DEPENDS_ON` |
| `required_knowledge` | Ku | `REQUIRES_KNOWLEDGE` |
| `applied_knowledge` | Ku | `APPLIES_KNOWLEDGE` |
| `contributing_goals` | Goal | `CONTRIBUTES_TO_GOAL`, `FULFILLS_GOAL` |

## Query Intent

**Default:** `QueryIntent.PREREQUISITE`

| Context | Intent |
|---------|--------|
| `context` | `PREREQUISITE` |
| `dependencies` | `PREREQUISITE` |
| `impact` | `HIERARCHICAL` |
| `practice` | `PRACTICE` |

## MEGA-QUERY Sections

The MEGA-QUERY in `/core/services/user/user_context_queries.py` fetches:

- `active_task_uids` - Active task UIDs
- `completed_task_uids` - Completed task UIDs
- `overdue_task_uids` - Overdue task UIDs
- `today_task_uids` - Tasks due today
- `entities_rich["tasks"]` - Full task data with graph context

## Usage Examples

```python
from core.models.relationship_registry import TASKS_CONFIG
from core.services.relationships import UnifiedRelationshipService

# Create relationship service
tasks_rel = UnifiedRelationshipService(backend, graph_intel, TASKS_CONFIG)

# Get related knowledge
knowledge_uids = await tasks_rel.get_related_uids("knowledge", "task:123")

# Get task with full context
task, context = await tasks_rel.get_entity_with_context("task:123", depth=2)
```

## Search Methods

**Service:** `TasksSearchService` (`/core/services/tasks/tasks_search_service.py`)

### Inherited from BaseService

| Method | Description |
|--------|-------------|
| `search(query, user_uid)` | Text search across title, description |
| `get_by_status(status, user_uid)` | Filter by EntityStatus |
| `get_by_domain(domain, user_uid)` | Filter by Domain |
| `get_by_category(category, user_uid)` | Filter by category field |
| `get_by_relationship(related_uid, rel, dir)` | Graph traversal |
| `graph_aware_faceted_search(request)` | Unified search with graph context |

### Domain-Specific Methods

| Method | Description |
|--------|-------------|
| `get_blocking_tasks(uid, user_uid)` | Tasks blocking this task |
| `get_blocked_tasks(uid, user_uid)` | Tasks blocked by this task |
| `get_by_priority(priority, user_uid)` | Filter by priority level |
| `get_overdue(user_uid)` | Tasks past due date |
| `get_due_soon(user_uid, days=7)` | Tasks due within N days |
| `get_pending(user_uid)` | Tasks with pending status |
| `search_by_parent_goal(goal_uid, user_uid)` | Tasks fulfilling a goal |
| `get_prioritized(user_uid, limit=10)` | Smart prioritization |

**Full catalog:** [Search Service Methods Reference](/docs/reference/SEARCH_SERVICE_METHODS.md)

## Intelligence Service

`TasksIntelligenceService` provides task analysis and insights:

| Method | Description |
|--------|-------------|
| `get_task_with_context(uid)` | Task with full graph neighborhood |
| `generate_knowledge_from_task(uid)` | Generate KU from task content |
| `get_learning_opportunities(user_uid)` | Learning opportunities from tasks |
| `get_behavioral_insights(user_uid)` | Task completion patterns analysis |

**See:** [Intelligence Services Index](/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md)

## Events/Publishing

The Tasks domain publishes domain events for cross-service communication:

| Event | Trigger | Data |
|-------|---------|------|
| `TaskCreated` | Task created | `task_uid`, `user_uid`, `title` |
| `TaskCompleted` | Task marked complete | `task_uid`, `user_uid`, `completion_date` |
| `TaskUpdated` | Task modified | `task_uid`, `user_uid`, `changed_fields` |
| `TaskDeleted` | Task removed | `task_uid`, `user_uid` |
| `TaskPriorityChanged` | Priority changed | `task_uid`, `old_priority`, `new_priority` |

**Event handling:** Other services subscribe to these events (e.g., UserContext invalidation, goal progress updates).

## UI Routes

### Three-View Dashboard

| Route | Method | Description |
|-------|--------|-------------|
| `/tasks` | GET | Main dashboard with List/Create/Calendar tabs |
| `/tasks?view=list` | GET | List view (default) |
| `/tasks?view=create` | GET | Create task form |
| `/tasks?view=calendar` | GET | Calendar view |

### HTMX Fragments

| Route | Method | Description |
|-------|--------|-------------|
| `/tasks/view/list` | GET | List view fragment |
| `/tasks/view/create` | GET | Create form fragment |
| `/tasks/view/calendar` | GET | Calendar fragment |
| `/tasks/list-fragment` | GET | Filtered list for updates |
| `/tasks/quick-add` | POST | Create task via form |

### Detail Routes

| Route | Method | Description |
|-------|--------|-------------|
| `/tasks/{uid}` | GET | View task detail |
| `/tasks/{uid}/edit` | GET/POST | Edit task |
| `/tasks/{uid}/complete` | POST | Mark task complete |
| `/tasks/{uid}/reschedule` | POST | Reschedule task |

## Code Examples

### Create a Task

```python
from core.models.task.task_request import TaskCreateRequest
from core.models.enums import Priority

result = await tasks_service.create_task(
    TaskCreateRequest(
        title="Review PR #123",
        description="Review and approve the authentication PR",
        priority=Priority.HIGH,
        due_date=date.today() + timedelta(days=1),
        project="skuel-auth",
    ),
    user_uid=user_uid,
)
task = result.value
```

### Link Task to Goal

```python
result = await tasks_service.link_task_to_goal(
    task_uid=task.uid,
    goal_uid="goal.launch-auth-system",
    contribution_score=0.8,
)
```

### Get Tasks with Dependencies

```python
# Get tasks blocking this task
blocking = await tasks_service.search.get_blocking_tasks(task.uid, user_uid)

# Get tasks blocked by this task
blocked = await tasks_service.search.get_blocked_tasks(task.uid, user_uid)
```

## See Also

- [Goals Domain](goals.md) - Tasks fulfill goals
- [Knowledge (KU) Domain](ku.md) - Tasks apply/require knowledge
- [Principles Domain](principles.md) - Tasks align with principles
