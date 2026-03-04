# Common Activity Domain Patterns

> Patterns shared across all 6 Activity Domains.

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
    def render_list_view(tasks, filters, user_uid): ...

    @staticmethod
    def render_create_view(user_uid): ...

    @staticmethod
    def render_detail_view(task, context): ...
```

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

All domains have intelligence services extending `BaseIntelligenceService`:

```python
class TasksIntelligenceService(BaseIntelligenceService[TasksOperations, Task]):
    _service_name = "tasks.intelligence"

    async def get_task_with_context(self, uid: str) -> Result[dict]:
        """Get task with full graph neighborhood."""
        ...

    async def get_learning_opportunities(self, user_uid: str) -> Result[list]:
        """Identify learning opportunities from tasks."""
        ...
```

## Cross-Domain Relationships

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
