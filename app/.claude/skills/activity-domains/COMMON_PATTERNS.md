# Common Activity Domain Patterns

> Patterns shared across the 6 Activity Domains (Tasks, Goals, Habits, Events, Choices, Principles).

## BaseService Inheritance

Core services extend `BaseService[Backend, Model, UpdateIntent]` and declare a `DomainConfig` — THE single source of truth for configuration. The third type parameter is the domain's frozen `*UpdateIntent` (ADR-066); it defaults to `RawChanges`. The six Activity facades and core services pin it; sub-services such as `TasksSearchService` use the two-argument form:

```python
from core.services.domain_config import create_activity_domain_config

class TasksCoreService(BaseService[TasksOperations, Task, TaskUpdateIntent]):
    _config = create_activity_domain_config(
        dto_class=TaskDTO,
        model_class=Task,
        domain_name="tasks",
        date_field="due_date",
        completed_statuses=(EntityStatus.COMPLETED.value,),
        entity_label="Entity",
    )
```

**`create_activity_domain_config` parameters:**
| Parameter | Purpose | Default |
|-----------|---------|---------|
| `dto_class` | DTO for serialization | Required |
| `model_class` | Domain model class | Required |
| `domain_name` | Domain identifier | Required |
| `date_field` | Date field for time queries | `"created_at"` |
| `completed_statuses` | Terminal statuses | `()` |
| `category_field` | Field for categorization | `"category"` |
| `search_fields` | Fields for text search | `("title", "description")` |
| `search_order_by` | Default sort field | `"created_at"` |
| `entity_label` | Neo4j base label | `"Entity"` |
| `config_lookup_label` | `LABEL_CONFIGS` key (must exist, else `ValueError`) | `model_class.__name__` |
| `temporal_secondary_sort` | Secondary sort for `get_upcoming` / `get_overdue` (Events: `"start_time"`) | `None` |

The factory also sets `user_ownership_relationship=RelationshipName.OWNS` and `supports_user_progress=True`, and derives `graph_enrichment_patterns` and `prerequisite_relationships` from the relationship registry.

## Event Publishing

Domain events are published after the write that caused them, through `publish_event()`:

```python
from core.events import TaskUpdated, publish_event

event = TaskUpdated(task_uid=task.uid, user_uid=task.user_uid, updated_fields=updated_fields)
await publish_event(self.event_bus, event, self.logger)
```

**Completion events are transition-gated.** `TasksCoreService.update_task` publishes
`TaskCompleted` only when `is_completion_transition(outcome.prior_status, changes)` holds — the
prior status comes back from `backend.update_with_status_guard(...)`, so a re-post of
`completed` publishes no `TaskCompleted` and leaves the completion stamp alone. The write
itself still lands (`status`, `updated_at`), and `TaskUpdated` still fires. `GoalAchieved` (Goals) and
`CalendarEventCompleted` (Events) are gated the same way, and `TaskReopened` mirrors
`TaskCompleted` on the way out. `HabitCompleted` is not a status transition — it records one
completion of a recurring habit. `TaskCompleted` carries `task_uid`,
`user_uid`, `completion_time_seconds` and `was_overdue`; a completion that happened away from
the app carries its date as `occurred_at`.

**Event naming**: `{Domain}{Action}` - e.g., `TaskCompleted`, `GoalAchieved`, `HabitStreakBroken`

**Event files**: `/core/events/{domain}_events.py` (Events: `calendar_event_events.py`)

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
- **`RawChanges` is still a legitimate `U`.** A service that is its own `BaseService[Op, T]`
  instantiation inherits `U = RawChanges` and may call `self.update(uid, RawChanges({...}))`
  for a non-status patch — the same validated, event-firing contract. `PsService` does (tags,
  field patches); no Activity sub-service does, because their writes carry `status` and go
  through the guard below. The typed `*UpdateIntent` is the contract for the **public**
  facade/route update, not every call in the domain.
- **`backend.update(uid, dict)` directly** is the persistence seam (always a dict) and is
  allowed only for full-DTO replaces and timestamp/system bumps that carry **no `status`** —
  each marked `# raw-write:`. A partial field update that bypasses *both* the intent and the
  `RawChanges` service contract (i.e. straight to `backend.update`) is a defect.
- **A write that carries `status` goes through `backend.update_with_status_guard(uid,
  changes, guard)`, never `super().update` or `backend.update`** (ADR-087). Build the guard
  with `status_transition_guard(EntityType.X, changes, zone=current_zone())` (a Task or Goal
  completed today is stamped with today in the user's zone); the write evaluates it against the
  status the node holds under its lock and hands the prior back, so transition verdicts come
  from `outcome.prior_status`, not from a status read beforehand. The five stamping domains
  (Task, Goal, Habit, Event, Choice) are all on it; **Principles is the one exception** — its
  gate is target-only legality, prior-independent, so there is no race to close, and it
  calls `validate_status_target(EntityType.PRINCIPLE, changes)` for that check alone
  (ADR-087 § Scope).
- **A non-null completion stamp is refused unless the entity is completed**, in both
  shapes. Supplying the stamp field stands the guard's own patches down — the authority
  rule, so an explicit complete can carry its own date — which means such a patch would
  otherwise take the reopen without its clear and leave the entity open and still
  stamped. A patch that NAMES a status other than `completed` is refused from the patch
  alone (`_refuse_stranded_stamp`); a patch that names NO status resolves against the
  prior, so it travels to the write as `refuse_unless_prior_in={completed}`
  (`_bare_stamp_gate`) and comes back `applied=False` for the chokepoint to voice with
  `stranded_stamp_error`. Demanding the status in the same patch would have been
  unsatisfiable rather than strict for `ChoiceUpdateRequest`, which exposes `completed_at`
  and no status — demanding the PRIOR is satisfiable at every door. Clearing (`None`) and
  re-posting `completed` with a corrected date both stay legal. Both refusals are the
  guard's alone: `validate_status_target` keeps only the legality check, because the
  ingestion validator shares it and a vault file with a stale `completion_date:` beside
  an open status must be ingested and cleaned, not refused.
- ⚠ **A `# raw-write:` is not an exemption from the guard.** A writer that sets a status
  outside its domain chokepoint (`make_decision`, `miss_habit_event`,
  `unblock_task_if_ready`, the four `GoalsProgressService` progress writers) keeps its raw
  shape — each publishes an event with provenance the generic contract cannot express — but
  it still writes through the primitive. Either `status_transition_guard` (which returns the
  reopen clear, so a completed entity's stamp is cleared rather than stranded on an open
  one) or `StatusWriteGuard(refuse_if_prior_in=<terminal values>)` where the write must not
  resurrect finished work. A writer that derives completion from its own recompute rather
  than a caller's target puts only the "…and not already completed" half in the guard, as
  `patch_if_prior_not_in`.
- ⚠ **Leaving `CrudOperationsMixin.update` takes `_validate_update` off the path.** The
  facades route the generic CRUD to the per-domain method, so the inherited hook is the
  only thing that was running the domain rules — a backend-direct write must call
  `self._validate_update(current, intent)` itself, or every rule dies silently while the
  tests still pass. Pin each rule with a test that it still refuses through the door the
  facade actually uses.

Per-domain deviations: **Habits** keeps `update_habit(uid, intent, *, force_archive=False)`
(the transient `force_archive` directive can't ride the intent — it would persist as a junk
column); **Tasks/Events** split edge-typed fields off the intent before the property write.
See [ADR-066](/docs/decisions/ADR-066-typed-update-intents.md),
[ADR-087](/docs/decisions/ADR-087-status-guarded-conditional-writes.md) and
`docs/roadmap/done/update-intents.md`.

## UI Pattern

Activity Domains support authoring through per-domain create/edit forms and Obsidian vault sync (`/submissions/sync`). All 6 domains are pages of the
**Tasks+ section**: one sidebar (`render_activity_sidebar_page()` from `ui/activities/nav.py` —
Today, Weekly, Monthly, the six domain rows, Journal, GradeBook) on every one of them, the
calendar month/week views and `/today` included, and the Tasks+ door (→ `/today`) lit in the
chrome. The section has no hub page — `/today` is the cross-domain glance and the sidebar shows
the siblings (below `lg`, as the scrolling section nav).

```
/today                     # Tasks+ landing — the cross-domain glance
/domain                    # Main page — stats, filters, list (with the Tasks+ sidebar, its row lit)
/domain/content            # HTMX fragment: filter bar + list + stats bar
/domain/list-fragment      # HTMX fragment for filter updates
/domain/detail?uid=...     # Detail page with EntityRelationshipsSection (with Activity sidebar)
/domain/create             # create form (render_activity_form over FormGenerator; GET render, POST submit)
/domain/edit?uid=...       # edit form prefilled from the existing entity

/api/{domain}/{uid}/status   # HTMX status toggle (POST)
/api/{domain}/{uid}/priority # HTMX inline priority change (POST)
```

Forms live in `ui/activities/{domain}_form.py` and are appended inside the
`create_{domain}_ui_routes` factory (so they ride along with DomainRouteConfig).
List-typed cross-domain fields and free-text list fields are intentionally
omitted from forms — assign those via the detail-page relationship picker.

**Cross-domain connections** — the fetch Cypher lives below the hexagonal boundary in `ConnectionFetchBackend` (`adapters/persistence/neo4j/`), behind the `ConnectionFetchOperations` port (ADR-044); the pure-data configs live in `core/utils/connection_configs.py`:
- `backend.fetch_entity_connections(config, entity_uids)` — unified batch query for cross-domain relationships. Each domain has a `ConnectionConfig` constant (e.g. `TASK_CONNECTION_CONFIG`) specifying entity label, direction (`outgoing` or `incoming` for gravity wells), and relationship types. UI factories receive the port as `ActivityUIConfig.backend` and call `config.backend.fetch_entity_connections(config.connection_config, uids)`.
- Returns `dict[str, list[dict[str, str]]]` with normalized keys: `rel_type`, `connected_uid`, `title`, `connected_type`. A connected entity is the entity owner's own or published shared content (`build_far_node_clause`) — another user's node, or a draft, is left out.

**Entity filtering** (`core/utils/entity_filters.py`):
- `filter_tasks()`, `filter_goals()`, `filter_habits()`, `filter_events()`, `filter_choices()`, `filter_principles()` — pure functions applying status/category/priority filtering and sorting to domain model lists. Business rules (what "active" or "overdue" means) live here, not in UI views.

**Shared UI utilities** (`ui/activities/_shared.py`):
- `MetadataField(label, *value)` — label + value pair for detail page metadata grids. Variadic `*value` supports simple (`Span`), paragraph (`P`), list (`Ul`), and multi-element (stars + score) content. Used ~60 times across all 6 detail views.
- `safe_id(uid)` — converts UIDs to safe HTML id attributes (replaces `.` and `:` with `-`)
- `PRIORITY_ORDER` lives in `core/utils/entity_filters.py` (a business rule), not here
- `CONNECTION_ICONS` — universal icon + href mapping for all 9 cross-domain connection types
- `ConnectionBadges(connections)` — renders icon+title badge links for outgoing connections (used by Tasks, Habits, Events, Choices). Reads `connected_uid`/`connected_type` keys.
- `ConnectionSummary(connections)` — renders compact icon+count badges for incoming connections (used by gravity-well domains: Goals, Principles). Reads `connected_type` keys.
- `PriorityBadgeDropdown(uid, priority, domain, singular)` — interactive priority badge on all 6 cards: Alpine dropdown of the 3 `Priority` levels (`low`, `medium`, `high`), picks POST `/api/{domain}/{uid}/priority` via HTMX and swap the re-rendered card. Both `/status` and `/priority` endpoints come from `activity_field_api_factory` (`create_activity_field_api_routes` + one `FieldUpdateSpec` per field; priority carries the `PRIORITY_VALUES` whitelist).

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

# 4. API routes (tasks_api.py) — one config call; the shared factory owns the handlers
create_activity_hierarchy_api_routes(
    rt,
    ActivityHierarchyApiConfig(
        domain_name="tasks",
        singular="task",
        service=tasks_service,                    # verify_ownership comes from BaseService
        get_children=tasks_service.get_subtasks,
        get_parent=tasks_service.get_parent_task,
        get_hierarchy=tasks_service.get_task_hierarchy,
        add_child_relationship=add_subtask_relationship,  # named adapter: passes progress_weight
        remove_child_relationship=tasks_service.remove_subtask_relationship,
    ),
)
```

`create_activity_hierarchy_api_routes` (`adapters/inbound/route_factories/hierarchy_api_factory.py`)
registers the same block for every Activity Domain. Both `children` variants render from one
ownership-checked fetch (`_fetch_owned_children`: `verify_entity_ownership` on the parent, then
the children filtered to `child.user_uid == user_uid`).

**Live API routes per domain** (`{domain}` is the plural path segment, e.g. `tasks`; reads are
ownership-verified on the queried uid, and the two writes verify both `parent_uid` **and**
`child_uid`):
- `GET  /api/{domain}/children?uid=<uid>` → direct children (JSON)
- `GET  /api/{domain}/{uid}/children` → the same children as a `TreeNodeList` fragment (HTMX lazy load)
- `GET  /api/{domain}/parent?uid=<uid>` → immediate parent (or null)
- `GET  /api/{domain}/hierarchy?uid=<uid>` → `{ancestors, current, siblings, children, depth}`
- `POST /api/{domain}/add-child` → body `{parent_uid, child_uid, progress_weight?}` — creates the edge (Tasks, Goals, Habits use `progress_weight`)
- `POST /api/{domain}/remove-child` → body `{parent_uid, child_uid}` — removes the edge, not the nodes

**HierarchyMixin backend methods** (return raw dicts — core services convert to domain models):
- `get_children_raw(parent_uid, depth)` → list of child node dicts
- `get_parent_raw(child_uid)` → parent node dict or None
- `get_hierarchy_raw(entity_uid)` → `{ancestors, siblings, children}` dicts
- `create_hierarchy_relationship(parent_uid, child_uid, forward_props)` → with cycle detection
- `remove_hierarchy_relationship(parent_uid, child_uid)`
- `would_create_cycle(parent_uid, child_uid)`

## Search Service Pattern

Each search service satisfies its domain's `*SearchOperations` protocol, which extends
`DomainSearchOperations[T]` (`core/ports/search_protocols.py`):

```python
class TasksSearchService(BaseService["TasksOperations", Task]):
    # Inherited from BaseService (SearchOperationsMixin, TimeQueryMixin):
    # - search(query, limit=50, user_uid=None)
    # - get_by_status(status, limit=100, user_uid=None)
    # - get_by_category(category, user_uid=None, limit=100)
    # - get_by_relationship(related_uid, relationship_type, direction="outgoing", user_uid=None)
    # - graph_aware_faceted_search(request, user_uid)
    # - list_user_categories(user_uid)
    # - get_upcoming(...), get_overdue(user_uid=None, limit=100), get_active(...)

    # Domain-specific methods, e.g.:
    async def get_tasks_for_goal(self, goal_uid): ...
    async def get_blocked_by_prerequisites(self, user_uid): ...
    async def get_prioritized(self, user_context, limit=10): ...
```

## Ownership Verification

Activity Domains enforce multi-tenant security:

```python
# API routes — returns an error Result (404, not 403) or None
ownership_error = await verify_entity_ownership(tasks_service, uid, user_uid, "task")
if ownership_error:
    return ownership_error

# UI routes — returns (entity, None) or (None, refusal Response)
task, refusal = await require_owned_entity(tasks_service, uid, user_uid, "Task")
if refusal:
    return refusal

# Both come from adapters.inbound.route_factories. BaseService provides:
await service.verify_ownership(uid, user_uid)  # Result[T]; NotFound for another user's uid
await service.get_for_user(uid, user_uid)      # Get with ownership check
await service.update_for_user(uid, intent, user_uid)   # intent = a *UpdateIntent (ADR-066)
await service.delete_for_user(uid, user_uid)
```

## Intelligence Service Pattern

All domains have intelligence services extending `BaseAnalyticsService` (graph + Python, no AI),
composed from mixins:

```python
class TasksIntelligenceService(
    _CoreIntelligenceMixin,   # shared get_with_context(uid, depth=2) -> Result[tuple[T, GraphContext]]
    _AnalyticsMixin,          # get_behavioral_insights(user_uid, period_days=90), ...
    _ProductivityMixin,
    _DualTrackMixin,          # assess_productivity_dual_track (ADR-030)
    BaseAnalyticsService["TasksOperations", Task],
):
    _service_name = "tasks.intelligence"
```

Every Activity domain's intelligence service provides `get_with_context`, `get_performance_analytics` and
`get_domain_insights` — the three `IntelligenceRouteFactory` serves at `/api/{domain}/context`,
`/analytics` and `/insights`.

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

Knowledge relationships declared in `connections.*` frontmatter are created at ingestion time. Targets are authored UIDs (dot form; the colon spelling is retired) of any knowledge entity — a Ku or a PathStep:

```yaml
# Task applies knowledge (substance weight: 0.05)
connections:
  applies_knowledge: [ps.mindfulness.breath-awareness-basics]

# Choice informed by knowledge (substance weight: 0.07)
connections:
  informed_by_knowledge: [ps.mindfulness.breath-awareness-basics]

# Principle grounded in knowledge (substance weight: 0.07)
connections:
  grounded_in_knowledge: [ku.mindfulness.mind-wandering]
```

See `/docs/guides/YAML_AUTHORING_GUIDE.md` for the field reference per entity type. See `/docs/architecture/knowledge_substance_philosophy.md` for the substance scoring model.

### Knowledge application is graph-native (no node field)

`applies_knowledge` is stored **only** as the edge `(Task)-[:APPLIES_KNOWLEDGE]->(Ku)` —
there is no `applies_knowledge_uids` property on the frozen models (ADR-035/ADR-065; do not
reintroduce it). The string list survives
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
        "goals",
        choice_uid,
        goal_uid,
        {"contribution_score": contribution_score},
        far_end=GOAL_FAR_END,  # core/services/mixins/link_edge_guard.py
    )

# create_relationship validates the key against the domain config (fails closed on a
# typo — e.g. "habits" when the Choice config key is "impacted_habits"), admits the far
# end (it exists, is one of far_end.labels, and is owned by the source's owner or is
# published shared content — anything else is not found), orients direction from the registry
# spec, and writes via the batch path. far_end is required: there is no unchecked link.

# Get related entities (key + uid — no direction arg; the registry spec supplies it):
related = await service.relationships.get_related_uids("knowledge", entity_uid)  # Result[list[str]]
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
`*Updated` event (e.g. `TaskUpdated`) so the `UserContext` cache invalidates — the
same rule that applies to `applies_knowledge_uids`/`reinforces_habit_uid` edge syncs.

**Reads (cross-domain)** — Queries spanning 2+ domain labels go through `CrossDomainQueryService` (`core/services/cross_domain/`):

```python
# One backend query per call — no N+1, no fan-out-and-loop
result = await cross_domain_query.get_principle_alignment_evidence(principle_uid, user_uid)
evidence = result.value  # PrincipleAlignmentEvidence (frozen dataclass)

result = await cross_domain_query.count_active_tasks_for_goal(goal_uid)
count = result.value  # ActiveTaskCount (frozen dataclass)
```

Holds one `CrossDomainBackendOperations` backend (no per-domain backends; the Cypher lives in `adapters/persistence/neo4j/cross_domain_backend.py`). 9 methods, each one query, each returning a frozen typed dataclass from `cross_domain_types.py`. Don't fetch across types with `self.backend.find_by()` and join in Python.

## Result[T] Error Handling

All service methods return `Result[T]`:

```python
result = await tasks_service.create_task(request, user_uid)
if result.is_error:
    return Result.fail(result)  # Propagate error across a type boundary

task = result.value  # Access success value
```

**At route boundaries**, `@boundary_handler()` converts the returned `Result` to HTTP (the CRUD
factory's routes are built the same way; a hand-written domain route looks like this):
```python
@rt("/api/goals/stalled", methods=["GET"])
@boundary_handler()
async def goals_stalled(request: Request) -> Result[list[ContextualGoal]]:
    user_uid = require_authenticated_user(request)
    max_progress = parse_float_query_param(request.query_params, "max_progress", 0.1)
    limit = parse_int_query_param(request.query_params, "limit", 10)
    ctx_result = await fetch_context(user_uid)
    if ctx_result.is_error:
        return Result.fail(ctx_result)
    return await goals_service.get_stalled_goals_for_user(ctx_result.value, max_progress, limit)
```
