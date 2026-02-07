# Service Topology

**Purpose:** Visual architecture diagrams showing how BaseService, mixins, sub-services, and facades interconnect.

**Last Updated:** 2026-01-29

---

## Table of Contents

- [BaseService + Mixins Architecture](#baseservice--mixins-architecture)
- [Activity Domain Facade Pattern](#activity-domain-facade-pattern)
- [Sub-Service Communication](#sub-service-communication)
- [Data Flow Examples](#data-flow-examples)
- [Dependency Graphs](#dependency-graphs)

---

## BaseService + Mixins Architecture

### Mixin Composition Hierarchy

```
BaseService[B: BackendOperations, T: DomainModelProtocol]
    │
    ├─ ConversionHelpersMixin      ← Foundation (no dependencies)
    │   └─ Methods: _to_domain_model(), _from_domain_model(), _ensure_exists()
    │
    ├─ CrudOperationsMixin          ← Depends on ConversionHelpersMixin
    │   └─ Methods: create(), get(), update(), delete(), list()
    │                verify_ownership(), get_for_user(), update_for_user()
    │
    ├─ SearchOperationsMixin        ← Depends on ConversionHelpersMixin
    │   └─ Methods: search(), get_by_status(), get_by_category()
    │                search_by_tags(), get_by_relationship()
    │
    ├─ RelationshipOperationsMixin  ← Depends on ConversionHelpersMixin
    │   └─ Methods: add_relationship(), get_relationships(), traverse()
    │                get_prerequisites(), get_enables()
    │
    ├─ TimeQueryMixin               ← Depends on ConversionHelpersMixin
    │   └─ Methods: get_user_items_in_range(), get_due_soon(), get_overdue()
    │
    ├─ UserProgressMixin            ← Depends on ConversionHelpersMixin
    │   └─ Methods: get_user_progress(), update_user_mastery()
    │
    └─ ContextOperationsMixin       ← Depends on CrudOperationsMixin
        └─ Methods: get_with_content(), get_with_context()
```

### Mixin Dependency Graph

```
┌─────────────────────────┐
│ ConversionHelpersMixin  │ ← Base layer (no dependencies)
└──────────┬──────────────┘
           │
           ├─────────────────────────────────────────────┐
           │                                             │
           ▼                                             ▼
┌──────────────────────┐                    ┌────────────────────────┐
│ CrudOperationsMixin  │                    │ SearchOperationsMixin  │
└──────────┬───────────┘                    └────────────────────────┘
           │
           │                        ┌────────────────────────────────┐
           │                        │ RelationshipOperationsMixin    │
           │                        └────────────────────────────────┘
           │
           │                        ┌────────────────────────────────┐
           │                        │ TimeQueryMixin                 │
           │                        └────────────────────────────────┘
           │
           │                        ┌────────────────────────────────┐
           │                        │ UserProgressMixin              │
           │                        └────────────────────────────────┘
           ▼
┌──────────────────────────┐
│ ContextOperationsMixin   │ ← Top layer (depends on CrudOperationsMixin)
└──────────────────────────┘
```

**Key Insight:** ConversionHelpersMixin is the foundation - 5 mixins depend on it.

---

## Activity Domain Facade Pattern

### Facade + Sub-Services Structure (Tasks Example)

```
TasksService (Facade)
├─ Inherits: FacadeDelegationMixin + BaseService[TasksOperations, Task]
├─ Provides: ~35 auto-generated delegation methods
└─ Composes 7 sub-services:
    │
    ├─ self.core: TasksCoreService
    │   ├─ Extends: BaseService[TasksOperations, Task]
    │   ├─ Responsibility: CRUD operations, event publishing
    │   └─ Methods: create_task(), get_task(), update_task(), delete_task()
    │
    ├─ self.search: TasksSearchService
    │   ├─ Extends: BaseService[TasksOperations, Task]
    │   ├─ Responsibility: Search and discovery
    │   ├─ Config: _config = create_activity_domain_config(...)
    │   └─ Methods: search(), get_tasks_for_goal(), get_prioritized_tasks()
    │
    ├─ self.progress: TasksProgressService
    │   ├─ Extends: BaseService[TasksOperations, Task]
    │   ├─ Responsibility: Progress tracking, completion
    │   └─ Methods: complete_task_with_cascade(), check_prerequisites()
    │
    ├─ self.scheduling: TasksSchedulingService
    │   ├─ Extends: BaseService[TasksOperations, Task]
    │   ├─ Responsibility: Scheduling and capacity management
    │   └─ Methods: create_task_with_context(), suggest_learning_aligned_tasks()
    │
    ├─ self.planning: TasksPlanningService
    │   ├─ Extends: BaseService[TasksOperations, Task]
    │   ├─ Responsibility: Context-aware recommendations
    │   └─ Methods: get_actionable_tasks_for_user(), get_learning_tasks_for_user()
    │
    ├─ self.relationships: UnifiedRelationshipService
    │   ├─ Extends: N/A (standalone service)
    │   ├─ Responsibility: Cross-domain relationships
    │   └─ Methods: link_to_knowledge(), get_with_context()
    │
    └─ self.intelligence: TasksIntelligenceService
        ├─ Extends: BaseAnalyticsService[TasksOperations, Task]
        ├─ Responsibility: Pure Cypher analytics
        └─ Methods: analyze_task_learning_metrics(), generate_task_knowledge_insights()
```

### All Activity Domains

```
Activity Domain Facades (6 total)
│
├─ TasksService (7 sub-services)
│   └─ core, search, progress, scheduling, planning, relationships, intelligence
│
├─ GoalsService (9 sub-services)
│   └─ core, search, progress, scheduling, learning, recommendation, relationships, intelligence, + custom
│
├─ HabitsService (11 sub-services) ← Most complex
│   └─ core, search, progress, scheduling, planning, learning, completions, events, achievements, relationships, intelligence
│
├─ EventsService (8 sub-services)
│   └─ core, search, progress, scheduling, relationships, intelligence, + custom
│
├─ ChoicesService (7 sub-services)
│   └─ core, search, learning, relationships, intelligence, + custom
│
└─ PrinciplesService (3 sub-services) ← Simplest
    └─ core, search, intelligence
```

**Pattern:** All 6 domains have 4 common sub-services (core, search, relationships, intelligence) + domain-specific services.

---

## Sub-Service Communication

### Internal Communication Flow

```
Route Layer
    │
    ▼
┌────────────────────────────────────────────────────────┐
│ TasksService (Facade)                                  │
│                                                         │
│  _delegations = {                                      │
│    "create_task": ("core", "create_task"),            │
│    "search": ("search", "search"),                     │
│    "complete_task": ("progress", "complete_task"),    │
│  }                                                      │
│                                                         │
│  FacadeDelegationMixin auto-generates:                │
│    async def create_task(self, *args, **kwargs):      │
│        return await self.core.create_task(*args, **kwargs)  │
└───────────┬────────────────────────────────────────────┘
            │
            ├─────────────────┬─────────────────┬──────────────────┐
            │                 │                 │                  │
            ▼                 ▼                 ▼                  ▼
    ┌───────────────┐ ┌──────────────┐ ┌─────────────────┐ ┌─────────────────┐
    │ CoreService   │ │ SearchService│ │ ProgressService │ │ IntelligenceServ│
    │               │ │              │ │                 │ │                 │
    │ create_task() │ │ search()     │ │ complete_task() │ │ analyze_metrics()│
    └───────┬───────┘ └──────┬───────┘ └────────┬────────┘ └────────┬────────┘
            │                │                  │                   │
            │                │                  ├───────────────────┘
            │                │                  │ (Cross-service calls)
            │                │                  │
            ▼                ▼                  ▼
    ┌────────────────────────────────────────────────────────────────┐
    │ UniversalNeo4jBackend[Task]                                    │
    │                                                                 │
    │  create(), get(), list(), find_by(), update(), delete()       │
    └────────────────────────┬───────────────────────────────────────┘
                             │
                             ▼
                        Neo4j Database
```

**Key Observations:**

1. **Facade → Sub-Service** - Auto-delegation via FacadeDelegationMixin
2. **Sub-Service → Backend** - Direct calls to UniversalNeo4jBackend
3. **Sub-Service ↔ Sub-Service** - Cross-service calls (e.g., progress calls relationships)
4. **Backend → Neo4j** - Single path to database

---

### Cross-Service Dependencies

```
TasksService Sub-Services
│
├─ TasksCoreService
│   └─ Depends on: ku_inference_service (optional), event_bus (optional)
│
├─ TasksProgressService
│   └─ Depends on: analytics_engine (KuAnalyticsEngine), event_bus (optional)
│       └─ Calls: relationships service internally
│
├─ TasksSchedulingService
│   └─ Depends on: (none - self-contained)
│
├─ TasksPlanningService
│   └─ Depends on: relationship_service (UnifiedRelationshipService)
│
├─ TasksSearchService
│   └─ Depends on: (none - uses DomainConfig)
│
├─ TasksIntelligenceService
│   └─ Depends on: graph_intelligence_service, relationship_service, event_bus (optional)
│
└─ UnifiedRelationshipService
    └─ Depends on: relationship_config (TASKS_UNIFIED)
```

**Pattern:** Most sub-services are self-contained. Cross-service dependencies are explicit in `__init__`.

---

## Data Flow Examples

### Example 1: Create Task

```
1. HTTP Request
   POST /api/tasks/create
   Body: {title: "Learn BaseService", priority: "high"}
   │
   ▼
2. Route Handler
   @rt("/api/tasks/create")
   async def create_task_route(request, body: TaskCreateRequest):
       user_uid = require_authenticated_user(request)
       result = await services.tasks.create_task(body, user_uid)
       return {"task_uid": result.value.uid}
   │
   ▼
3. Facade Delegation
   TasksService.create_task()  ← Auto-generated method
       └─ Delegates to: self.core.create_task()
   │
   ▼
4. Core Service
   TasksCoreService.create_task()
       ├─ Validates request
       ├─ Infers knowledge (ku_inference_service)
       ├─ Converts to domain model (Task)
       ├─ Calls backend.create()
       └─ Publishes TaskCreated event
   │
   ▼
5. Backend
   UniversalNeo4jBackend[Task].create()
       ├─ Converts Task → Neo4j properties
       ├─ Generates Cypher CREATE query
       └─ Executes via driver
   │
   ▼
6. Neo4j Database
   CREATE (t:Task {uid: "task.learn-baseservice", title: "Learn BaseService", ...})
   CREATE (u:User {uid: "user.mike"})-[:OWNS]->(t)
   │
   ▼
7. Response
   Result.ok(Task(uid="task.learn-baseservice", ...))
```

**Total layers:** 6 (HTTP → Route → Facade → Sub-Service → Backend → Database)

---

### Example 2: Complete Task with Cascade

```
1. HTTP Request
   POST /api/tasks/task.learn-baseservice/complete
   Body: {actual_minutes: 30, quality_score: 4}
   │
   ▼
2. Route Handler
   result = await services.tasks.complete_task_with_cascade(
       task_uid, user_context, actual_minutes, quality_score
   )
   │
   ▼
3. Facade Method (Explicit, not delegated)
   TasksService.complete_task_with_cascade()
       └─ Delegates to: self.progress.complete_task_with_cascade()
       └─ Triggers: self._trigger_knowledge_generation() (async)
   │
   ▼
4. Progress Service
   TasksProgressService.complete_task_with_cascade()
       ├─ Verifies ownership
       ├─ Updates Task status → COMPLETED
       ├─ Updates UserContext.completed_tasks_count++
       ├─ Checks prerequisites → unblocks dependent tasks
       ├─ Calls: relationships.get_completion_impact()
       └─ Publishes: TaskCompleted event
   │
   ├─────────────────────┐
   │                     │
   ▼                     ▼
5a. Backend          5b. Event Bus
   update_task()         TaskCompleted
       │                     └─> Listeners:
       ▼                         - UserContextService (update stats)
   Neo4j UPDATE              - KuAnalyticsEngine (track mastery)
                                 - AchievementService (check badges)
   │
   ▼
6. Knowledge Generation (Async)
   TasksService._trigger_knowledge_generation()
       └─ ku_generation_service.extract_knowledge_from_completed_tasks()
           └─ Analyzes last 30 days → generates KUs
```

**Key Observations:**
- **Orchestration at facade level** - `complete_task_with_cascade()` is explicit in facade
- **Cascade handled by ProgressService** - updates UserContext, unblocks tasks, publishes events
- **Event-driven side effects** - listeners react to TaskCompleted event
- **Async knowledge generation** - doesn't block completion response

---

### Example 3: Search Tasks for Goal

```
1. HTTP Request
   GET /api/tasks/search?goal_uid=goal.health-2024
   │
   ▼
2. Route Handler
   result = await services.tasks.get_tasks_for_goal(goal_uid)
   │
   ▼
3. Facade Delegation
   TasksService.get_tasks_for_goal()  ← Auto-generated
       └─ Delegates to: self.search.get_tasks_for_goal()
   │
   ▼
4. Search Service
   TasksSearchService.get_tasks_for_goal(goal_uid)
       ├─ Builds Cypher query via UnifiedQueryBuilder
       ├─ MATCH (t:Task)-[:FULFILLS_GOAL]->(g:Goal {uid: $goal_uid})
       └─ Returns: list[Task]
   │
   ▼
5. Backend
   UniversalNeo4jBackend[Task].find_by(...)
       ├─ Executes Cypher query
       └─ Converts Neo4j records → Task domain models
   │
   ▼
6. Neo4j Database
   MATCH (t:Task)-[:FULFILLS_GOAL]->(g:Goal {uid: "goal.health-2024"})
   WHERE (u:User {uid: $user_uid})-[:OWNS]->(t)
   RETURN t
```

**Key Observations:**
- **Search logic in SearchService** - not in Core
- **UnifiedQueryBuilder** - generates Cypher queries
- **Ownership filter automatic** - added by BaseService mixin

---

## Dependency Graphs

### Service-Level Dependencies

```
Routes / Application Code
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│ Service Bootstrap (DI Container)                         │
│                                                           │
│  services = ServiceContainer(                            │
│      tasks=TasksService(...),                           │
│      goals=GoalsService(...),                            │
│      ku=KuService(...),                                  │
│      user=UserService(...),                              │
│      ...                                                  │
│  )                                                        │
└───────┬──────────────────────────────────────────────────┘
        │
        ├─────────────────┬──────────────────┬────────────────┐
        │                 │                  │                │
        ▼                 ▼                  ▼                ▼
┌──────────────┐  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐
│TasksService  │  │GoalsService  │  │KuService    │  │UserService   │
└──────┬───────┘  └──────┬───────┘  └──────┬──────┘  └──────┬───────┘
       │                 │                 │                │
       │                 │                 │                │
       └────────────┬────┴─────────────────┴────────────────┘
                    │
                    ▼
        ┌────────────────────────────────┐
        │ Shared Infrastructure Services │
        │                                 │
        │  - UniversalNeo4jBackend       │
        │  - UnifiedRelationshipService  │
        │  - GraphIntelligenceService    │
        │  - KuAnalyticsEngine           │
        │  - EventBus                    │
        └────────────────────────────────┘
```

---

### Module-Level Dependencies

```
/core/services/
│
├─ base_service.py
│   └─ Uses: mixins/ (7 mixins)
│
├─ mixins/
│   ├─ conversion_helpers_mixin.py    (no dependencies)
│   ├─ crud_operations_mixin.py       (uses conversion_helpers)
│   ├─ search_operations_mixin.py     (uses conversion_helpers)
│   ├─ relationship_operations_mixin.py (uses conversion_helpers)
│   ├─ time_query_mixin.py            (uses conversion_helpers)
│   ├─ user_progress_mixin.py         (uses conversion_helpers)
│   ├─ context_operations_mixin.py    (uses crud_operations)
│   └─ facade_delegation_mixin.py     (standalone - introspection only)
│
├─ tasks/
│   ├─ tasks_core_service.py          (extends BaseService)
│   ├─ tasks_search_service.py        (extends BaseService)
│   ├─ tasks_progress_service.py      (extends BaseService)
│   ├─ tasks_scheduling_service.py    (extends BaseService)
│   ├─ tasks_planning_service.py      (extends BaseService)
│   └─ tasks_intelligence_service.py  (extends BaseAnalyticsService)
│
├─ tasks_service.py                   (facade - uses tasks/ sub-services)
│
├─ domain_config.py                   (configuration dataclass + factories)
│
└─ relationships/
    └─ unified_relationship_service.py (standalone, used by all domains)
```

---

## Factory Pattern Architecture

### create_common_sub_services() Flow

```
TasksService.__init__()
    │
    ▼
create_common_sub_services(
    domain="tasks",
    backend=backend,
    graph_intel=graph_intelligence_service,
    event_bus=event_bus,
)
    │
    ▼
ACTIVITY_DOMAIN_CONFIGS["tasks"]  ← Registry lookup
    │
    ├─ core_module: "core.services.tasks"
    ├─ core_class: "TasksCoreService"
    ├─ search_module: "core.services.tasks"
    ├─ search_class: "TasksSearchService"
    ├─ intelligence_module: "core.services.tasks"
    ├─ intelligence_class: "TasksIntelligenceService"
    └─ relationship_config: TASK_CONFIG
    │
    ▼
Dynamic imports + instantiation
    │
    ├─ importlib.import_module("core.services.tasks")
    ├─ getattr(module, "TasksCoreService")
    ├─ core = TasksCoreService(backend=backend, ...)
    │
    ├─ search = TasksSearchService(backend=backend, ...)
    ├─ intel = TasksIntelligenceService(backend=backend, ...)
    └─ rels = UnifiedRelationshipService(backend=backend, config=TASKS_UNIFIED)
    │
    ▼
CommonSubServices[TasksIntelligenceService]
    ├─ core: TasksCoreService
    ├─ search: TasksSearchService
    ├─ relationships: UnifiedRelationshipService
    └─ intelligence: TasksIntelligenceService
```

**Benefits:**
- Eliminates ~80 lines of boilerplate per facade
- Centralized configuration via ACTIVITY_DOMAIN_CONFIGS registry
- Type-safe (Generic type parameter for intelligence service)

---

## Configuration Architecture

### DomainConfig Flow

```
TasksSearchService
    │
    ├─ Class-level attribute
    │   _config = create_activity_domain_config(
    │       dto_class=TaskDTO,
    │       model_class=Task,
    │       domain_name="tasks",
    │       date_field="due_date",
    │       completed_statuses=("completed",),
    │   )
    │
    ▼
DomainConfig dataclass
    │
    ├─ dto_class: TaskDTO
    ├─ model_class: Task
    ├─ search_fields: ("title", "description")  ← Default from factory
    ├─ search_order_by: "created_at"             ← Default from factory
    ├─ category_field: "category"                ← Default from factory
    ├─ user_ownership_relationship: "OWNS"       ← Default from Activity factory
    ├─ date_field: "due_date"                    ← Provided
    ├─ completed_statuses: ("completed",)        ← Provided
    └─ ... (14 more fields)
    │
    ▼
BaseService._get_config_value("search_fields")
    │
    └─ Returns: ("title", "description")
       Used by: SearchOperationsMixin.search() method
```

**Key Insight:** DomainConfig is THE single source of truth - replaces 18 scattered class attributes.

---

## Summary

### Key Architectural Patterns

1. **Mixin Composition** - 7 focused mixins provide 100+ methods to BaseService
2. **Facade Pattern** - 1 facade per domain delegates to 3-11 specialized sub-services
3. **Auto-Delegation** - FacadeDelegationMixin generates ~50 methods from `_delegations` dict
4. **Factory Pattern** - `create_common_sub_services()` creates 4 common sub-services
5. **Configuration Pattern** - DomainConfig dataclass provides single source of truth
6. **Event-Driven** - Domain events published for side effects (analytics, achievements, etc.)

### Service Layers

```
Layer 1: BaseService (7 mixins)                  ← Foundation (100+ methods)
Layer 2: Sub-Services (3-11 per domain)          ← Implementation (specialized)
Layer 3: Facades (1 per domain)                  ← Public API (auto-delegation)
Layer 4: Routes (HTTP → Facades)                 ← Interface (HTTP boundaries)
```

### Design Principles

- **Single Responsibility** - Each mixin/sub-service has ONE focused responsibility
- **Composition over Inheritance** - Facades compose sub-services, don't inherit from them
- **DRY via Auto-Generation** - FacadeDelegationMixin eliminates 1,500 lines of boilerplate
- **Configuration over Code** - DomainConfig replaces scattered class attributes
- **Fail-Fast** - All dependencies REQUIRED at init (no graceful degradation)

---

## See Also

- [Sub-Service Catalog](/docs/reference/SUB_SERVICE_CATALOG.md) - Which service does what
- [Method Index](/docs/reference/BASESERVICE_METHOD_INDEX.md) - Complete method listing
- [Quick Start Guide](/docs/guides/BASESERVICE_QUICK_START.md) - New developer onboarding
- [BaseService Source](/core/services/base_service.py) - Implementation
- [FacadeDelegationMixin Source](/core/services/mixins/facade_delegation_mixin.py) - Auto-delegation
