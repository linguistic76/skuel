# Common Activity Domain Patterns

> Patterns shared across the 6 Activity Domains (Tasks, Goals, Habits, Events, Choices, Principles).

## BaseService Inheritance

All core and search services extend `BaseService[Backend, Model]` using `DomainConfig` — THE single source of truth for configuration (ONE PATH FORWARD since January 2026):

```python
from core.services.domain_config import create_activity_domain_config

class TasksCoreService(BaseService[TasksOperations, Task]):
    _config = create_activity_domain_config(
        dto_class=TaskDTO,
        model_class=Task,
        domain_name="tasks",
        date_field="due_date",
        completed_statuses=(EntityStatus.COMPLETED.value,),
    )
```

**`create_activity_domain_config` parameters:**
| Parameter | Purpose | Default |
|-----------|---------|---------|
| `dto_class` | DTO for serialization | Required |
| `model_class` | Domain model class | Required |
| `domain_name` | Domain identifier | Required |
| `date_field` | Date field for time queries | Required |
| `completed_statuses` | Terminal statuses | Required |
| `category_field` | Field for categorization | `"domain"` |
| `search_fields` | Fields for text search | `("title", "description")` |

All Activity Domains set `_user_ownership_relationship = "OWNS"` automatically via `create_activity_domain_config`. Do NOT use bare class attributes (`_dto_class`, `_model_class`) — that's the old pattern, fully migrated away.

## Event Publishing

All domains publish events for cross-service communication:

```python
from core.events.task_events import TaskCompleted

async def complete_task(self, uid: str) -> Result[Task]:
    result = await self.core.mark_complete(uid)
    if result.is_ok and self.event_bus:
        event = TaskCompleted(
            task_uid=uid,
            user_uid=result.value.user_uid,
            completion_date=date.today(),
        )
        await self.event_bus.publish_async(event)
    return result
```

**Event naming**: `{Domain}{Action}` - e.g., `TaskCompleted`, `GoalAchieved`, `HabitStreakBroken`

**Event files**: `/core/events/{domain}_events.py`

## Three-View UI Dashboard

All domains use identical UI structure:

```
/domain                    # Main dashboard
/domain?view=list          # List view (default)
/domain?view=create        # Create form
/domain?view=analytics     # Analytics view

/domain/view/list          # HTMX fragment
/domain/view/create        # HTMX fragment
/domain/view/analytics     # HTMX fragment

/domain/{uid}              # Detail view
/domain/{uid}/edit         # Edit modal
```

**View components** in `/ui/{domain}/views.py`:
```python
class TasksViewComponents:
    @staticmethod
    def render_list_view(ctx: TasksPageContext) -> Div: ...

    @staticmethod
    def render_create_view(user_uid): ...

    @staticmethod
    def render_detail_view(task, context): ...
```

## Hierarchy Delegation Pattern

All 6 Activity Domain backends extend `_HierarchyMixin` with a per-domain `HierarchyConfig`. Core services delegate hierarchy operations to the backend — **no inline Cypher in services**.

```python
# Backend (domain_backends.py) — owns the Cypher via _HierarchyMixin
class TasksBackend(_HierarchyMixin, UniversalNeo4jBackend[Task]):
    _hierarchy_config = HierarchyConfig(
        forward_rel="HAS_SUBTASK", inverse_rel="SUBTASK_OF",
        node_label="Entity", domain_name="subtask",
    )

# Service (tasks_core_service.py) — thin delegation + model conversion
async def get_subtasks(self, parent_uid: str, depth: int = 1) -> Result[list[Task]]:
    result = await self.backend.get_children_raw(parent_uid, depth)
    if result.is_error:
        return Result.fail(result)
    return Result.ok([self._to_domain_model(data, TaskDTO, Task) for data in result.value])

async def create_subtask_relationship(self, parent_uid, subtask_uid, progress_weight=1.0):
    return await self.backend.create_hierarchy_relationship(
        parent_uid, subtask_uid, {"progress_weight": progress_weight}
    )

async def get_stats_for_user(self, user_uid: str) -> Result[dict[str, int]]:
    return await self.backend.get_stats_for_user(user_uid)
```

**Mixin methods** (return raw dicts — services convert to domain models):
- `get_children_raw(parent_uid, depth)` → list of child node dicts
- `get_parent_raw(child_uid)` → parent node dict or None
- `get_hierarchy_raw(entity_uid)` → `{ancestors, siblings, children}` dicts
- `create_hierarchy_relationship(parent_uid, child_uid, forward_props)` → with cycle detection
- `remove_hierarchy_relationship(parent_uid, child_uid)`
- `would_create_cycle(parent_uid, child_uid)`

## Search Service Pattern

All search services implement `DomainSearchOperations[T]`:

```python
class TasksSearchService(BaseService[TasksOperations, Task]):
    # Inherited methods (from BaseService):
    # - search(query, limit=50, user_uid=None)
    # - get_by_status(status, limit=100, user_uid=None)
    # - get_by_category(category, user_uid=None, limit=100)
    # - get_by_domain(domain, limit=100)
    # - get_by_relationship(related_uid, rel_type, direction)
    # - graph_aware_faceted_search(request, user_uid)
    # - list_user_categories(user_uid)

    # Domain-specific methods:
    async def get_blocking_tasks(self, uid, user_uid): ...
    async def get_overdue(self, user_uid, limit=100): ...
    async def get_prioritized(self, user_context, limit=10): ...
```

## Ownership Verification

Activity Domains enforce multi-tenant security:

```python
# In routes - verify ownership before operations
result = await service.verify_ownership(uid, user_uid)
if result.is_error:
    return result  # Returns 404 (not 403, for security)

# BaseService provides these methods:
await service.get_for_user(uid, user_uid)      # Get with ownership check
await service.update_for_user(uid, updates, user_uid)
await service.delete_for_user(uid, user_uid)
```

## Intelligence Service Pattern

All domains have intelligence services extending `BaseAnalyticsService`:

```python
class TasksIntelligenceService(BaseAnalyticsService[TasksOperations, Task]):
    _service_name = "tasks.intelligence"

    async def get_with_context(self, uid: str, depth: int = 2) -> Result[tuple]:
        """Get task with full graph neighborhood."""
        ...

    async def get_behavioral_insights(self, user_uid: str) -> Result[dict]:
        """Task completion patterns analysis."""
        ...
```

**Shared knowledge intelligence** (suggestions, prerequisites, learning opportunities) lives in
`ActivityKnowledgeIntelligenceService` (`core/services/knowledge/`) — wired into all 6 activity
domain facades as `self.knowledge_intelligence`. Satisfies `KnowledgeIntelligenceOperations`
protocol (4 methods): `get_knowledge_suggestions()`, `generate_knowledge_from_entities()`,
`get_knowledge_prerequisites()`, `get_learning_opportunities()`.
Uses `UniversalNeo4jBackend[Entity]` with `NeoLabel.ENTITY` so `find_by(user_uid=...)` returns
user-owned activity entities across all domains (shared entities lack `user_uid` and filter out).

## Cross-Domain Relationships

### YAML Ingestion (Structural)

Knowledge relationships declared in YAML `connections.*` fields are created at ingestion time:

```yaml
# Task applies knowledge (substance weight: 0.05)
connections:
  applies_knowledge: [l:mindfulness:breath-awareness-basics]

# Choice informed by knowledge (substance weight: 0.07)
connections:
  informed_by_knowledge: [l:mindfulness:breath-awareness-basics]

# Principle grounded in knowledge (substance weight: 0.07)
connections:
  grounded_in_knowledge: [l:mindfulness:mind-wandering-happens]
```

See `yaml_templates/_schemas/` for complete field reference. See `/docs/architecture/knowledge_substance_philosophy.md` for the substance scoring model.

### Runtime (Service API)

All domains connect via `UnifiedRelationshipService`:

```python
# Link to goal
await service.link_to_goal(entity_uid, goal_uid, contribution_score=0.8)

# Link to principle
await service.link_to_principle(entity_uid, principle_uid, alignment_score=0.9)

# Link to knowledge
await service.link_to_knowledge(entity_uid, ku_uid, relevance="fundamental")

# Get related entities
related_uids = await service.relationships.get_related_uids(
    "knowledge", entity_uid, direction="outgoing"
)
```

## Result[T] Error Handling

All service methods return `Result[T]`:

```python
result = await service.create_task(request, user_uid)
if result.is_error:
    return result  # Propagate error

task = result.value  # Access success value
```

**At route boundaries**, use `@boundary_handler`:
```python
@rt("/api/tasks/create", methods=["POST"])
@boundary_handler()
async def create_task(request):
    return await service.create_task(...)  # Auto-converts Result to HTTP
```
