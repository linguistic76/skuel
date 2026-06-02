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

## UI Pattern

Activity Domains support both bulk ingestion (`/upload` of YAML) and direct
authoring through per-domain create/edit forms. All 6 domains share a collapsible
Activity sidebar (`render_activity_sidebar_page()` from `ui/activities/nav.py`)
linking back to `/profile`. Activity Domains content is embedded inline in
`/profile` via `ActivityHubView()`.

```
/profile                   # Activity Domains embedded inline (6 HTMX lazy-loaded blocks)
/domain                    # Main page — stats, filters, list (with Activity sidebar)
/domain/list-fragment      # HTMX fragment for filter updates
/domain/detail?uid=...     # Detail page with EntityRelationshipsSection (with Activity sidebar)
/domain/create             # FormGenerator-rendered create form (GET render, POST submit)
/domain/edit?uid=...       # FormGenerator-rendered edit form prefilled from existing entity

/api/{domain}/{uid}/status # HTMX status toggle (POST)
```

Forms live in `ui/activities/{domain}_form.py` and are appended inside the
`create_{domain}_ui_routes` factory (so they ride along with DomainRouteConfig).
List-typed cross-domain fields and free-text list fields are intentionally
omitted from forms — assign those via the detail-page relationship picker.

**Cross-domain connections** — the fetch Cypher lives below the hexagonal boundary in `ConnectionFetchBackend` (`adapters/persistence/neo4j/`), behind the `ConnectionFetchOperations` port (ADR-044); the pure-data configs live in `core/utils/connection_configs.py`:
- `backend.fetch_entity_connections(config, entity_uids)` — unified batch query for cross-domain relationships. Each domain has a `ConnectionConfig` constant (e.g. `TASK_CONNECTION_CONFIG`) specifying entity label, direction (`outgoing` or `incoming` for gravity wells), and relationship types. UI factories receive the port as `ActivityUIConfig.backend` and call `config.backend.fetch_entity_connections(config.connection_config, uids)`.
- Returns `dict[str, list[dict[str, str]]]` with normalized keys: `rel_type`, `connected_uid`, `title`, `connected_type`.

**Entity filtering** (`core/utils/entity_filters.py`):
- `filter_tasks()`, `filter_goals()`, `filter_habits()`, `filter_events()`, `filter_choices()`, `filter_principles()` — pure functions applying status/category/priority filtering and sorting to domain model lists. Business rules (what "active" or "overdue" means) live here, not in UI views.

**Shared UI utilities** (`ui/activities/_shared.py`):
- `MetadataField(label, *value)` — label + value pair for detail page metadata grids. Variadic `*value` supports simple (`Span`), paragraph (`P`), list (`Ul`), and multi-element (stars + score) content. Used ~60 times across all 6 detail views.
- `safe_id(uid)` — converts UIDs to safe HTML id attributes (replaces `.` and `:` with `-`)
- `CONNECTION_ICONS` — universal icon + href mapping for all 9 cross-domain connection types
- `ConnectionBadges(connections)` — renders icon+title badge links for outgoing connections (used by Tasks, Habits, Events, Choices). Reads `connected_uid`/`connected_type` keys.
- `ConnectionSummary(connections)` — renders compact icon+count badges for incoming connections (used by gravity-well domains: Goals, Principles). Reads `connected_type` keys.

Calendar cross-cutting system still works (reads service protocols, not UI routes).

## Hierarchy Delegation Pattern

All 6 Activity Domain backends extend `_HierarchyMixin` with a per-domain `HierarchyConfig`. Core services delegate hierarchy operations to the backend — **no inline Cypher in services**.

```python
# Backend (backends/activity_backends.py) — owns the Cypher via _HierarchyMixin
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

async def get_stats_for_user(self, user_uid: UserUID) -> Result[dict[str, int]]:
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

    async def get_behavioral_insights(self, user_uid: UserUID) -> Result[dict]:
        """Task completion patterns analysis."""
        ...
```

**Shared knowledge intelligence** (suggestions, prerequisites, learning opportunities) lives in
`ActivityKnowledgeIntelligenceService` (`core/services/knowledge/`) — wired into all 6 activity
domain facades as `self.knowledge_intelligence`. The 4 delegation methods are provided by
`KnowledgeIntelligenceDelegationMixin` (`core/services/mixins/`) — facades inherit it instead of
copy-pasting the methods. Satisfies `KnowledgeIntelligenceOperations` protocol (4 methods):
`get_knowledge_suggestions()`, `generate_knowledge_from_entities()`,
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

### Knowledge application is graph-native (no node field)

`applies_knowledge` is stored **only** as the edge `(Task)-[:APPLIES_KNOWLEDGE]->(Ku)` —
there is no `applies_knowledge_uids` property on the frozen models (removed in the
ADR-035/ADR-065 graph-native migration; do not reintroduce it). The string list survives
*only* at the API boundary (`TaskCreateRequest`/`TaskUpdateRequest`/`TaskResponse`); the
service layer translates it to/from edges.

- **Write:** both create AND update must route `applies_knowledge_uids` to edge mutation.
  `TasksService.update_task` pops it out of the property `updates` dict and re-syncs edges
  (symmetric to `reinforces_habit_uid`) — leaving it in `updates` writes a junk node
  property and silently skips the edge, because the backend does `SET n += $updates`.
- **Read:** `TaskRelationships.fetch(uid, service.relationships)` or
  `get_related_uids("knowledge", uid)` — never a node attribute.
- **Consume:** `InsightGenerationService._analyze_knowledge_application_patterns` emits a
  `KNOWLEDGE_APPLICATION` pattern when knowledge-applying tasks are >10% more efficient.

**See:** `/docs/patterns/KNOWLEDGE_APPLICATION_TRACKING.md`.

### Runtime (Service API)

**Writes** — All domains connect via `UnifiedRelationshipService`:

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

For a relationship with **no typed `link_to_*` method** (e.g. task dependencies,
`DEPENDS_ON`), create the edge through the backend batch path — **never** the generic
`service.create_relationship(key, ...)`, which is broken for tasks (it dispatches to a
non-existent `link_task_to_<key>` backend method and fails at runtime; mocks hide it):

```python
await backend.create_relationships_batch(
    [(dependent_uid, blocks_uid, RelationshipName.DEPENDS_ON.value, props)]
)  # e.g. TasksService.create_task_dependency
```

After **any** edge-only mutation (no node property changed), publish the domain's
`*Updated` event (e.g. `TaskUpdated`) so `UnifiedUserContext` caches invalidate — the
same rule that applies to `applies_knowledge_uids`/`reinforces_habit_uid` edge syncs.

**Reads (cross-domain)** — Queries spanning 2+ domain labels go through `CrossDomainQueryService` (`core/services/cross_domain/`):

```python
# Single Cypher query — no N+1, no fan-out-and-loop
result = await cross_domain_query.get_principle_alignment_evidence(principle_uid, user_uid)
evidence = result.value  # PrincipleAlignmentEvidence (frozen dataclass)

result = await cross_domain_query.count_active_tasks_for_goal(goal_uid)
count = result.value  # ActiveTaskCount (frozen dataclass)
```

Takes only a `QueryExecutor` (no per-domain backends). 9 methods, each runs exactly one Cypher query and returns a frozen typed dataclass from `cross_domain_types.py`. Replaces the old pattern of domain services calling `self.backend.find_by()` across types and joining in Python.

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
