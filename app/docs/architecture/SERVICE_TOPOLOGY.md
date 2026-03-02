# Service Architecture: File Organization & Topology

**Purpose:** File organization rules, import guidelines, and visual architecture diagrams for `/core/services/`.

**Last Updated:** 2026-03-03

---

## Table of Contents

- [File Organization](#file-organization)
- [Import Guidelines](#import-guidelines)
- [BaseService + Mixins Architecture](#baseservice--mixins-architecture)
- [Activity Domain Facade Pattern](#activity-domain-facade-pattern)
- [Sub-Service Communication](#sub-service-communication)
- [Data Flow Examples](#data-flow-examples)
- [Dependency Graphs](#dependency-graphs)
- [Factory Pattern Architecture](#factory-pattern-architecture)
- [Configuration Architecture](#configuration-architecture)
- [Summary](#summary)

---

## File Organization

> **Core Principle:** "Facade at root, implementation in folder"

### 1. DUAL-LOCATION Services

Services with **both** a root-level facade AND a subfolder of sub-services.

| Category | Services | Sub-service count |
|----------|----------|-------------------|
| Activity Domains (6) | tasks, goals, habits, events, choices, principles | 5–11 per domain |
| Curriculum Domains (3) | ku, lp, ls | 4–11 per domain |
| Cross-Cutting (4) | user, askesis, finance, lifepath | varies |

**Structure:**
```
/core/services/
  tasks_service.py          # Facade (public API)
  tasks/                    # Implementation folder
    __init__.py             # Re-exports sub-services
    tasks_core_service.py
    tasks_search_service.py
    tasks_intelligence_service.py
    tasks_progress_service.py
    tasks_scheduling_service.py
    tasks_planning_service.py
    tasks_ai_service.py
    task_relationships.py   # Relationship config (not a service)
```

**Rationale:** The facade provides a stable public API while internal implementation evolves freely. External code imports `TasksService`; sub-services are implementation details.

---

### 2. FOLDER-ONLY Services

Infrastructure modules with no root-level facade.

| Folder | Purpose |
|--------|---------|
| `relationships/` | UnifiedRelationshipService + 6 mixin files |
| `sharing/` | UnifiedSharingService (entity-agnostic sharing) |
| `search/` | Unified search across all domains |
| `submissions/` | Student work — CRUD, processing, search |
| `feedback/` | Teacher/AI feedback, activity reports, review queue |
| `mixins/` | 7 BaseService mixin files |
| `intelligence/` | GraphContextOrchestrator + analytics helpers |
| `infrastructure/` | Cross-cutting helpers (PrerequisiteHelper, etc.) |
| `ingestion/` | UnifiedIngestionService |
| `query/` | Query builders (CypherGenerator, etc.) |
| `insight/` | Insight analytics |
| `dsl/` | Activity DSL parser & engine |
| `lateral_relationships/` | Lateral relationship graph queries |
| `groups/` | Group CRUD and membership |
| `exercises/` | Exercise CRUD and curriculum linking |
| `lp_intelligence/` | Learning path intelligence |
| `adaptive_lp/` | Adaptive learning path engine |
| `analytics/` | Domain analytics |
| `background/` | Background task workers |
| `notifications/` | Notification services |

---

### 3. ROOT-ONLY Services

Standalone services without subfolders.

| Category | Services |
|----------|----------|
| **Base Classes** | `base_service.py`, `base_analytics_service.py`, `base_ai_service.py`, `base_planning_service.py` |
| **AI/LLM** | `ai_service.py`, `llm_service.py`, `neo4j_genai_embeddings_service.py`, `neo4j_vector_search_service.py`, `context_aware_ai_service.py` |
| **Analytics** | `analytics_engine.py`, `analytics_service.py`, `cross_domain_analytics_service.py`, `analytics_relationship_service.py` |
| **Askesis Secondary** | `askesis_ai_service.py`, `askesis_citation_service.py` |
| **KU Generation Pipeline** | `entity_chunking_service.py`, `insight_generation_service.py`, `entity_inference_service.py`, `ku_intelligence_service.py` |
| **Calendar** | `calendar_service.py`, `calendar_optimization_service.py` |
| **Content** | `conversion_service.py`, `content_enrichment_service.py` |
| **User Secondary** | `user_progress_service.py`, `user_relationship_service.py` |
| **System** | `system_service.py`, `visualization_service.py`, `schema_service.py`, `performance_optimization_service.py` |
| **Config/Helpers** | `domain_config.py`, `query_builder.py`, `metadata_manager_mixin.py`, `context_first_mixin.py` |

---

### When to Use Each Pattern

| Pattern | Use When |
|---------|----------|
| **DUAL** | Complex domain with multiple responsibilities; external API stability needed |
| **FOLDER-ONLY** | Infrastructure or processing module; no facade needed |
| **ROOT-ONLY** | Single-responsibility service; base class; config helper |

---

## Import Guidelines

### Domain Services (DUAL pattern)

**External code imports the facade:**
```python
# CORRECT — import from facade
from core.services.tasks_service import TasksService
from core.services.goals_service import GoalsService
```

**Sub-services can be imported directly when needed (e.g., tests):**
```python
# ALLOWED — direct import for specific testing or composition
from core.services.tasks import TasksCoreService
from core.services.tasks.tasks_intelligence_service import TasksIntelligenceService
```

### Infrastructure (FOLDER-ONLY)

```python
from core.ports import BackendOperations, TasksOperations
from core.services.relationships import UnifiedRelationshipService
from core.services.search.search_router import SearchRouter
from core.services.sharing import UnifiedSharingService
```

### Utilities (ROOT-ONLY)

```python
from core.services.base_service import BaseService
from core.services.llm_service import LLMService
from core.services.analytics_engine import AnalyticsEngine
```

### Service Bootstrap

All services are composed in `/services_bootstrap.py`. This file:
- Imports all facades and utilities
- Creates dependency graph
- Instantiates services with proper dependencies
- Exposes the `Services` dataclass with all service instances (~72 typed fields, zero `Any`)

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

**File layout** (`/core/services/mixins/`):

```
mixins/
  conversion_helpers_mixin.py    (no dependencies)
  crud_operations_mixin.py       (uses conversion_helpers)
  search_operations_mixin.py     (uses conversion_helpers)
  relationship_operations_mixin.py (uses conversion_helpers)
  time_query_mixin.py            (uses conversion_helpers)
  user_progress_mixin.py         (uses conversion_helpers)
  context_operations_mixin.py    (uses crud_operations)
```

**Key Insight:** `ConversionHelpersMixin` is the foundation — 5 of 7 mixins depend on it directly.

---

## Activity Domain Facade Pattern

### Facade + Sub-Services Structure (Tasks Example)

```
TasksService (Facade)
├─ Inherits: BaseService[TasksOperations, Task]
├─ Provides: ~35 explicit async delegation methods
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

### All Activity Domains — Sub-Service Counts

```
Activity Domain Facades (6 total)
│
├─ TasksService      (7 sub-services)
│   └─ core, search, progress, scheduling, planning, intelligence, ai
│
├─ GoalsService      (9 sub-services)
│   └─ core, search, progress, scheduling, learning, planning, recommendation, intelligence, ai
│
├─ HabitsService    (11 sub-services)  ← Most complex
│   └─ core, search, progress, scheduling, planning, learning, completions,
│      event_integration, achievement, intelligence, ai
│
├─ EventsService     (8 sub-services)
│   └─ core, search, progress, scheduling, learning, habit_integration, intelligence, ai
│
├─ ChoicesService    (5 sub-services)
│   └─ core, search, learning, intelligence, ai
│
└─ PrinciplesService (8 sub-services)
    └─ core, search, alignment, learning, planning, reflection, intelligence, ai
```

**Pattern:** All 6 domains share 4 common sub-services (core, search, intelligence, ai) plus domain-specific services.

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
│  # Explicit delegation methods (February 2026)        │
│  async def create_task(self, *args, **kwargs):        │
│      return await self.core.create_task(*args, **kwargs) │
│                                                         │
│  async def search(self, *args, **kwargs):             │
│      return await self.search.search(*args, **kwargs) │
│                                                         │
│  async def complete_task(self, *args, **kwargs):      │
│      return await self.progress.complete_task(*args, **kwargs) │
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
            └────────────────┴──────────────────┴───────────────────┘
                                                │
                                                ▼
                    ┌────────────────────────────────────────────────────────────┐
                    │ UniversalNeo4jBackend[Task]                                │
                    │                                                             │
                    │  create(), get(), list(), find_by(), update(), delete()   │
                    └────────────────────────┬───────────────────────────────────┘
                                             │
                                             ▼
                                        Neo4j Database
```

**Key Observations:**

1. **Facade → Sub-Service** — Explicit one-line `async def` delegation methods (not dynamic)
2. **Sub-Service → Backend** — Direct calls to `UniversalNeo4jBackend`
3. **Sub-Service ↔ Sub-Service** — Occasional cross-service calls (e.g., progress calls relationships)
4. **Backend → Neo4j** — Single path to database

### Cross-Service Dependencies (Tasks Example)

```
TasksCoreService        ← Depends on: entity_inference_service (optional), event_bus (optional)
TasksProgressService    ← Depends on: analytics_engine, event_bus (optional)
TasksSchedulingService  ← Self-contained
TasksPlanningService    ← Depends on: relationship_service (UnifiedRelationshipService)
TasksSearchService      ← Self-contained (uses DomainConfig)
TasksIntelligenceService← Depends on: graph_intelligence_service, relationship_service
UnifiedRelationshipService ← Depends on: relationship_config (TASKS_CONFIG)
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
   TasksService.create_task()
       └─ Delegates to: self.core.create_task()
   │
   ▼
4. Core Service
   TasksCoreService.create_task()
       ├─ Validates request
       ├─ Infers knowledge (entity_inference_service)
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
   CREATE (t:Entity:Task {uid: "task_learn-baseservice_abc123", ...})
   CREATE (u:User {uid: "user_mike"})-[:OWNS]->(t)
   │
   ▼
7. Response
   Result.ok(Task(uid="task_learn-baseservice_abc123", ...))
```

---

### Example 2: Complete Task with Cascade

```
1. HTTP Request
   POST /api/tasks/task_learn-baseservice_abc123/complete
   Body: {actual_minutes: 30, quality_score: 4}
   │
   ▼
2. Route Handler
   result = await services.tasks.complete_task_with_cascade(
       task_uid, user_context, actual_minutes, quality_score
   )
   │
   ▼
3. Facade (explicit delegation)
   TasksService.complete_task_with_cascade()
       └─ Delegates to: self.progress.complete_task_with_cascade()
   │
   ▼
4. Progress Service
   TasksProgressService.complete_task_with_cascade()
       ├─ Verifies ownership
       ├─ Updates Task status → COMPLETED
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
   Neo4j UPDATE              - AnalyticsEngine (track mastery)
```

**Key Observations:**
- **Cascade handled by ProgressService** — updates UserContext, unblocks tasks, publishes events
- **Event-driven side effects** — listeners react to `TaskCompleted`

---

### Example 3: Search Tasks for Goal

```
1. GET /api/tasks/search?goal_uid=goal_health-2024_xyz
   │
   ▼
2. Route → services.tasks.get_tasks_for_goal(goal_uid)
   │
   ▼
3. Facade → self.search.get_tasks_for_goal(goal_uid)
   │
   ▼
4. TasksSearchService
   MATCH (t:Task)-[:FULFILLS_GOAL]->(g:Goal {uid: $goal_uid})
   WHERE (u:User {uid: $user_uid})-[:OWNS]->(t)
   RETURN t
   │
   ▼
5. Backend converts Neo4j records → list[Task]
```

---

## Dependency Graphs

### Service-Level Dependencies

```
Routes / Application Code
    │
    ▼
┌──────────────────────────────────────────────────────────┐
│ services_bootstrap.py  (Services dataclass)              │
│                                                           │
│  services.tasks    = TasksService(...)                   │
│  services.goals    = GoalsService(...)                    │
│  services.ku       = KuService(...)                      │
│  services.user     = UserService(...)                    │
│  services.sharing  = UnifiedSharingService(...)          │
│  ...                                                      │
└───────┬──────────────────────────────────────────────────┘
        │
        ├─────────────────┬──────────────────┬────────────────┐
        │                 │                  │                │
        ▼                 ▼                  ▼                ▼
┌──────────────┐  ┌──────────────┐  ┌─────────────┐  ┌──────────────┐
│TasksService  │  │GoalsService  │  │KuService    │  │UserService   │
└──────┬───────┘  └──────┬───────┘  └──────┬──────┘  └──────┬───────┘
       │                 │                 │                │
       └────────────┬────┴─────────────────┴────────────────┘
                    │
                    ▼
        ┌────────────────────────────────┐
        │ Shared Infrastructure Services │
        │                                 │
        │  - UniversalNeo4jBackend       │
        │  - UnifiedRelationshipService  │
        │  - UnifiedSharingService       │
        │  - AnalyticsEngine             │
        │  - EventBus                    │
        └────────────────────────────────┘
```

### Module-Level Dependencies

```
/core/services/
│
├─ base_service.py
│   └─ Uses: mixins/ (7 mixin files)
│
├─ mixins/
│   ├─ conversion_helpers_mixin.py    (no dependencies)
│   ├─ crud_operations_mixin.py       (uses conversion_helpers)
│   ├─ search_operations_mixin.py     (uses conversion_helpers)
│   ├─ relationship_operations_mixin.py (uses conversion_helpers)
│   ├─ time_query_mixin.py            (uses conversion_helpers)
│   ├─ user_progress_mixin.py         (uses conversion_helpers)
│   └─ context_operations_mixin.py    (uses crud_operations)
│
├─ tasks/
│   ├─ tasks_core_service.py          (extends BaseService)
│   ├─ tasks_search_service.py        (extends BaseService)
│   ├─ tasks_progress_service.py      (extends BaseService)
│   ├─ tasks_scheduling_service.py    (extends BaseService)
│   ├─ tasks_planning_service.py      (extends BaseService)
│   ├─ tasks_intelligence_service.py  (extends BaseAnalyticsService)
│   └─ tasks_ai_service.py            (extends BaseAIService)
│
├─ tasks_service.py                   (facade — uses tasks/ sub-services)
│
├─ domain_config.py                   (DomainConfig dataclass + factory functions)
│
├─ relationships/                     (decomposed shell + 6 mixin files)
│   ├─ unified_relationship_service.py  (shell: constructor, generic CRUD, typed links)
│   ├─ _batch_operations_mixin.py       (N+1 elimination helpers)
│   ├─ _ordered_relationships_mixin.py  (curriculum hierarchy + edge metadata)
│   ├─ _intelligence_mixin.py           (graph intelligence, semantic, cross-domain context)
│   ├─ _life_path_mixin.py              (SERVES_LIFE_PATH)
│   ├─ planning_mixin.py                (generic UserContext-aware planning + scoring)
│   └─ _domain_planning_mixin.py        (6 Activity Domain-specific planning methods)
│
├─ sharing/
│   └─ unified_sharing_service.py     (entity-agnostic SHARES_WITH + SHARED_WITH_GROUP)
│
├─ submissions/
│   ├─ submissions_service.py         (entry point — not a root-level facade)
│   ├─ submissions_core_service.py
│   ├─ submissions_search_service.py
│   ├─ submissions_processing_service.py
│   └─ submissions_relationship_service.py
│
└─ feedback/
    ├─ feedback_service.py            (entry point)
    ├─ activity_report_service.py     (CRUD for ActivityReport)
    ├─ review_queue_service.py        (ReviewRequest node management)
    ├─ teacher_review_service.py
    ├─ progress_feedback_generator.py (LLM → processed_content)
    └─ progress_schedule_service.py
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
    ├─ core_class: "TasksCoreService"
    ├─ search_class: "TasksSearchService"
    ├─ intelligence_class: "TasksIntelligenceService"
    └─ relationship_config: TASK_CONFIG
    │
    ▼
Dynamic imports + instantiation
    │
    ├─ core = TasksCoreService(backend=backend, ...)
    ├─ search = TasksSearchService(backend=backend, ...)
    ├─ intel = TasksIntelligenceService(backend=backend, ...)
    └─ rels = UnifiedRelationshipService(backend=backend, config=TASKS_CONFIG)
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
- Centralized configuration via `ACTIVITY_DOMAIN_CONFIGS` registry
- Generic type parameter for intelligence service

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
    ├─ search_fields: ("title", "description")   ← Default from factory
    ├─ search_order_by: "created_at"             ← Default from factory
    ├─ category_field: "category"                ← Default from factory
    ├─ user_ownership_relationship: "OWNS"       ← Default from Activity factory
    ├─ date_field: "due_date"                    ← Provided
    ├─ completed_statuses: ("completed",)        ← Provided
    └─ ... (14+ more fields)
    │
    ▼
BaseService._get_config_value("search_fields")
    └─ Returns: ("title", "description")
       Used by: SearchOperationsMixin.search()
```

**Key Insight:** `DomainConfig` is THE single source of truth — replaces scattered per-class attributes.

---

## Summary

### Key Architectural Patterns

1. **Mixin Composition** — 7 focused mixins provide 100+ methods to `BaseService`
2. **Facade Pattern** — 1 facade per domain delegates to 5–11 specialized sub-services
3. **Explicit Delegation** — Facade services have explicit `async def` delegation methods (not dynamic generation)
4. **Factory Pattern** — `create_common_sub_services()` creates 4 common sub-services from registry
5. **Configuration Pattern** — `DomainConfig` dataclass is single source of truth
6. **Event-Driven** — Domain events published for side effects (analytics, achievements, etc.)

### Service Layers

```
Layer 1: BaseService (7 mixins)             ← Foundation (100+ methods)
Layer 2: Sub-Services (5–11 per domain)     ← Implementation (specialized)
Layer 3: Facades (1 per domain)             ← Public API (explicit delegation)
Layer 4: Routes (HTTP → Facades)            ← Interface (HTTP boundaries)
```

### Design Principles

- **Single Responsibility** — Each mixin/sub-service has ONE focused responsibility
- **Composition over Inheritance** — Facades compose sub-services, don't inherit from them
- **Explicit over Magic** — Explicit delegation methods, no dynamic generation
- **Configuration over Code** — `DomainConfig` replaces scattered class attributes
- **Fail-Fast** — All dependencies REQUIRED at init (no graceful degradation)

---

## See Also

- [Sub-Service Catalog](/docs/reference/SUB_SERVICE_CATALOG.md) — Which service does what
- [Method Index](/docs/reference/BASESERVICE_METHOD_INDEX.md) — Complete method listing
- [Quick Start Guide](/docs/guides/BASESERVICE_QUICK_START.md) — New developer onboarding
- [Service Consolidation Patterns](/docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md)
- [14-Domain Architecture](/docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md)
- [BaseService Source](/core/services/base_service.py)
- [Example Facade Source](/core/services/tasks_service.py)
