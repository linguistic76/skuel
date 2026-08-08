# Common Activity Domain Patterns

> Patterns shared across the 6 Activity Domains (Tasks, Goals, Habits, Events, Choices, Principles).

## BaseService Inheritance

All core and search services extend `BaseService[Backend, Model, UpdateIntent]` using `DomainConfig` — THE single source of truth for configuration (ONE PATH FORWARD since January 2026). The third type parameter is the domain's frozen `*UpdateIntent` (ADR-066); it defaults to `RawChanges`, so only the six Activity Domains pin it:

```python
from core.services.domain_config import create_activity_domain_config

class TasksCoreService(BaseService[TasksOperations, Task, TaskUpdateIntent]):
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

## How to update an entity (the ONE path — ADR-066)

A **user-facing / facade** Activity Domain update is a frozen `*UpdateIntent`, never a raw
dict — that is the one canonical path for public CRUD (the `update_<domain>` facades, the
ownership-checked `update_for_user`, and the generic `CRUDRouteFactory`). What ADR-066 removed
is the *opaque* alternatives: the six `*UpdatePayload` TypedDicts, the `_intent_from_mapping`
funnels, and the facade `Mapping` overrides. It did **not** remove `RawChanges` — that is the
documented `U` default, and internal sub-services still use it (see below), so don't read this
as "no activity service may ever pass `RawChanges`".

```python
from core.models.task import TaskUpdateIntent

# 1. Service-authored transition — construct the intent directly.
intent = TaskUpdateIntent(status="in_progress", priority="urgent")
await tasks_service.update_task(uid, intent)

# 2. From an HTTP body — build the intent from the validated request.
intent = TaskUpdateRequest.model_validate(body).to_intent()
await tasks_service.update_for_user(uid, intent, user_uid)  # ownership-checked
```

How it flows:

- Every updatable column is a field on the intent, defaulted to the shared `UNSET` sentinel.
  `to_changes()` emits **only** the fields you set — so omitting a field leaves it untouched,
  while setting it to `None` is an explicit clear (a distinction a dict patch can't make).
- The shared base (`CrudOperationsMixin[B, T, U]`) is parameterized over the update type `U`
  (bound `SupportsToChanges`, default `RawChanges`). It runs `_validate_update` / `_post_update`
  and materializes the patch once at `backend.update(uid, updates.to_changes())`.
- `*UpdateRequest.to_intent()` builds the intent from `model_fields_set` (enums lowered to
  `.value`). The generic `CRUDRouteFactory` calls it automatically for any `SupportsToIntent`
  schema, so config-driven routes need no per-domain update code.
- **Internal sub-service transitions may pass `RawChanges`, not an intent.** A domain
  sub-service that is its own `BaseService[Op, T]` instantiation (e.g. `TasksProgressService`)
  inherits `U = RawChanges`, so a system transition it owns calls
  `self.update(uid, RawChanges({"status": ...}))` — still the *validated, event-firing* service
  contract (same `_validate_update` / `_post_update`), just with a `RawChanges` value rather
  than the domain intent. These are legitimate; don't rewrite or flag them. The typed
  `*UpdateIntent` is the contract for the **public** facade/route update, not every call in the
  domain.
- **`backend.update(uid, dict)` directly** is the persistence seam (always a dict) and is
  allowed only for full-DTO replaces and timestamp/system bumps — each marked `# raw-write:`.
  A partial field update that bypasses *both* the intent and the `RawChanges` service contract
  (i.e. straight to `backend.update`) is a defect.

Per-domain deviations: **Habits** keeps `update_habit(uid, intent, *, force_archive=False)`
(the transient `force_archive` directive can't ride the intent — it would persist as a junk
column); **Tasks/Events** split edge-typed fields off the intent before the property write.
See [ADR-066](/docs/decisions/ADR-066-typed-update-intents.md) and `docs/roadmap/done/update-intents.md`.

## UI Pattern

Activity Domains support authoring through per-domain create/edit forms and Obsidian vault sync (`/submissions/sync`). All 6 domains share a collapsible
Activity sidebar (`render_activity_sidebar_page()` from `ui/activities/nav.py`)
linking back to `/profile` — except the Events calendar month/week views,
which are navbar-only full-width pages. Activity Domains content lives on the `/profile`
Activities tab (`ACTIVITY_BLOCKS` accordion, `ui/activities/hub.py`).

```
/profile?tab=activities    # Activities tab — 6 accordion blocks, HTMX lazy-loaded previews
/domain                    # Main page — stats, filters, list (with Activity sidebar)
/domain/list-fragment      # HTMX fragment for filter updates
/domain/detail?uid=...     # Detail page with EntityRelationshipsSection (with Activity sidebar)
/domain/create             # FormGenerator-rendered create form (GET render, POST submit)
/domain/edit?uid=...       # FormGenerator-rendered edit form prefilled from existing entity

/api/{domain}/{uid}/status   # HTMX status toggle (POST)
/api/{domain}/{uid}/priority # HTMX inline priority change (POST)
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
- `PriorityBadgeDropdown(uid, priority, domain, singular)` — interactive priority badge on all 6 cards: Alpine dropdown of the 4 `Priority` levels, picks POST `/api/{domain}/{uid}/priority` via HTMX and swap the re-rendered card. Both `/status` and `/priority` endpoints come from `activity_field_api_factory` (`create_activity_field_api_routes` + one `FieldUpdateSpec` per field; priority carries the `PRIORITY_VALUES` whitelist).

Calendar cross-cutting system still works (reads service protocols, not UI routes).

## Hierarchy Delegation Pattern

All 6 Activity Domain backends extend `_HierarchyMixin` with a per-domain `HierarchyConfig`. The full stack is: backend Cypher → core service model conversion → facade delegation → API route.

```python
# 1. Backend (backends/activity_backends.py) — owns the Cypher via _HierarchyMixin
class TasksBackend(_HierarchyMixin, UniversalNeo4jBackend[Task]):
    _hierarchy_config = HierarchyConfig(
        forward_rel="HAS_SUBTASK", inverse_rel="SUBTASK_OF",
        node_label="Entity", domain_name="subtask",
    )

# 2. Core service (tasks_core_service.py) — inherits the typed hierarchy READS from
#    HierarchyReadMixin (generic get_subentities / get_parent_entity / get_entity_hierarchy,
#    converting via the DomainConfig dto/model). Only domain-specific WRITES stay per-domain.
class TasksCoreService(
    HierarchyReadMixin["TasksOperations", Task],
    BaseService["TasksOperations", Task, TaskUpdateIntent],
):
    # No hand-written get_subtasks/get_task_hierarchy — the mixin provides them.
    async def remove_subtask_relationship(self, parent_uid: str, subtask_uid: str) -> Result[bool]:
        return await self.backend.remove_hierarchy_relationship(parent_uid, subtask_uid)

# 3. Facade (tasks_service.py) — thin delegation; keeps the domain-named method,
#    points it at the generic mixin read.
async def get_subtasks(self, parent_uid: str, depth: int = 1) -> Result[list[Task]]:
    return await self.core.get_subentities(parent_uid, depth)

async def remove_subtask_relationship(self, parent_uid: str, child_uid: str) -> Result[bool]:
    return await self.core.remove_subtask_relationship(parent_uid, child_uid)

# 4. API routes (tasks_api.py) — ownership check, user-scoped filtering, delegate to facade
@rt("/api/tasks/children", methods=["GET"])
@boundary_handler()
async def task_children(request: Request) -> Result[list[Task]]:
    user_uid = require_authenticated_user(request)
    uid = request.query_params.get("uid", "")
    ownership_error = await verify_entity_ownership(tasks_service, uid, user_uid, "task")
    if ownership_error:
        return ownership_error
    result = await tasks_service.get_subtasks(uid)
    if result.is_error:
        return Result.fail(result)
    return Result.ok([t for t in result.value if t.user_uid == user_uid])  # P1: scope to caller

@rt("/api/tasks/remove-child", methods=["POST"])
@csrf_protected
@boundary_handler()
async def task_remove_child(request: Request) -> Result[dict[str, Any]]:
    user_uid = require_authenticated_user(request)
    parsed = await parse_json_body(request, RemoveHierarchyChildRequest)  # {parent_uid, child_uid}
    ...
    ownership_error = await verify_entity_ownership(tasks_service, req.parent_uid, user_uid, "task")
    if ownership_error: return ownership_error
    child_ownership_error = await verify_entity_ownership(tasks_service, req.child_uid, user_uid, "task")
    if child_ownership_error: return child_ownership_error  # P2: verify both endpoints
    result = await tasks_service.remove_subtask_relationship(req.parent_uid, req.child_uid)
    return Result.ok({"removed": result.value})
```

**Live API routes per domain** (`GET` ownership-verified on the queried uid; `POST` verifies both parent_uid **and** child_uid):
- `GET  /api/{domain}s/children?uid=<uid>` → direct children
- `GET  /api/{domain}s/parent?uid=<uid>` → immediate parent (or null)
- `GET  /api/{domain}s/hierarchy?uid=<uid>` → `{ancestors, current, siblings, children, depth}`
- `POST /api/{domain}s/remove-child` → body `{parent_uid, child_uid}` — removes edge, not nodes

**HierarchyMixin backend methods** (return raw dicts — core services convert to domain models):
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
await service.update_for_user(uid, intent, user_uid)   # intent = a *UpdateIntent (ADR-066)
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
Uses `UniversalNeo4jBackend[Entity]` with `NeoLabel.ENTITY` so `find_by(user_uid=...)` matches the
denormalized `user_uid` PROPERTY across all domains (shared entities lack `user_uid` and filter out).
The property is kept aligned to the canonical `(User)-[:OWNS]->` owner by the live write-paths + the
2026-06 backfill (`docs/migrations/USER_UID_OWNS_BACKFILL_2026-06.md`); `:OWNS` is authoritative.

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
  `TasksService.update_task` splits the edge-typed fields off the `TaskUpdateIntent`
  (`_split_relationship_intent` resets them to `UNSET` on the property sub-intent) and
  re-syncs edges (symmetric to `reinforces_habit_uid`) — leaving them on the property
  intent would write junk node properties and silently skip the edge, because the backend
  does `SET n += $changes`.
- **Read:** `TaskRelationships.fetch(uid, service.relationships)` or
  `get_related_uids("knowledge", uid)` — never a node attribute.
- **Consume:** `InsightGenerationService._analyze_knowledge_application_patterns` emits a
  `KNOWLEDGE_APPLICATION` pattern when knowledge-applying tasks are >10% more efficient.

**See:** `/docs/patterns/KNOWLEDGE_APPLICATION_TRACKING.md`.

### Runtime (Service API)

**Writes** — All domains connect via `UnifiedRelationshipService.create_relationship`,
keyed off an **explicit** registry `method_key`. The facade exposes domain-named wrappers
that supply the key (it knows which edge it means):

```python
# Facade wrapper -> create_relationship with the explicit key:
async def link_choice_to_goal(self, choice_uid, goal_uid, contribution_score=0.5):
    return await self.relationships.create_relationship(
        "goals", choice_uid, goal_uid, {"contribution_score": contribution_score}
    )

# create_relationship validates the key against the domain config (fails closed on a
# typo — e.g. "habits" when the Choice config key is "impacted_habits"), orients
# direction from the registry spec, and writes via the proven batch path.

# Get related entities (key + uid — no direction arg; the registry spec supplies it):
related_uids = await service.relationships.get_related_uids("knowledge", entity_uid)
```

> Do **not** reintroduce candidate-list `link_to_goal`/`link_to_knowledge`/`link_to_principle`
> wrappers on the service — they guessed the key from a hand-maintained list and silently
> failed on a coverage gap or picked the wrong edge. Name the key explicitly at the facade.
> Coverage is guarded by `tests/unit/test_cross_domain_link_keys.py`.

For a relationship best expressed without a config `method_key` (e.g. task dependencies,
`DEPENDS_ON`), create the edge through the backend batch path directly:

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
