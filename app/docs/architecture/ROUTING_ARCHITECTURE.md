---
title: SKUEL Routing Architecture: Routes, Services, and Persistence
updated: 2026-03-03
status: current
category: architecture
tags: [architecture, routing, security]
related: [OWNERSHIP_VERIFICATION.md]
---

# SKUEL Routing Architecture: Routes, Services, and Persistence

**Last Updated**: March 19, 2026

## Overview

This document provides a detailed explanation of how **Routes**, **Services**, and **Persistence** layers work together in SKUEL, with concrete examples and data flow diagrams.

---

## 🏗️ The Three-Layer Architecture

### Visual Overview

```
┌────────────────────────────────────────────────────────────────────┐
│                         USER REQUEST                               │
│                    (HTTP POST /api/tasks)                          │
└───────────────────────────────┬────────────────────────────────────┘
                                │
                                ▼
┌────────────────────────────────────────────────────────────────────┐
│                      INBOUND LAYER                                 │
│  Location: /adapters/inbound/                                      │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ tasks_routes.py (Factory - 2K)                               │ │
│  │   ↓ Receives Services container                              │ │
│  │   ↓ Extracts tasks_service                                   │ │
│  │   ↓ Passes to API creation                                   │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                │                                    │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ tasks_api.py (API Endpoints - 20K)                           │ │
│  │   @rt("/api/tasks", methods=["POST"])                        │ │
│  │   @boundary_handler()                                        │ │
│  │   async def create_task_route(request):                      │ │
│  │       # 1. Parse & validate (Pydantic)                       │ │
│  │       # 2. Convert to DTO                                    │ │
│  │       # 3. Call service                                      │ │
│  │       # 4. Return Result[T]                                  │ │
│  └──────────────────────────────────────────────────────────────┘ │
└───────────────────────────────┬────────────────────────────────────┘
                                │
                                ▼
┌────────────────────────────────────────────────────────────────────┐
│                       SERVICE LAYER                                │
│  Location: /core/services/                                         │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ tasks_service.py (Business Logic)                            │ │
│  │                                                               │ │
│  │   class TasksService:                                        │ │
│  │       def __init__(self, backend: TaskOperations):           │ │
│  │           self.backend = backend  # Protocol interface!      │ │
│  │                                                               │ │
│  │       async def create_task(dto) -> Result[Task]:            │ │
│  │           # 1. Business validation                           │ │
│  │           # 2. Call backend via protocol                     │ │
│  │           # 3. Return Result[Task]                           │ │
│  └──────────────────────────────────────────────────────────────┘ │
└───────────────────────────────┬────────────────────────────────────┘
                                │
                                ▼
┌────────────────────────────────────────────────────────────────────┐
│                     PERSISTENCE LAYER                              │
│  Location: /adapters/persistence/neo4j/                            │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ backends/ (Data Access — 9 cluster files)             │ │
│  │                                                               │ │
│  │   class TasksBackend(                                        │ │
│  │       UniversalNeo4jBackend[Task],                           │ │
│  │       TasksOperations  # Implements protocol!                │ │
│  │   ):                                                          │ │
│  │       async def create(dto) -> Result[Task]:                 │ │
│  │           # 1. Convert DTO to Cypher query                   │ │
│  │           # 2. Execute Neo4j query                           │ │
│  │           # 3. Map result to domain model                    │ │
│  │           # 4. Return Result[Task]                           │ │
│  └──────────────────────────────────────────────────────────────┘ │
└───────────────────────────────┬────────────────────────────────────┘
                                │
                                ▼
                        ┌─────────────────┐
                        │   Neo4j Graph   │
                        │    Database     │
                        └─────────────────┘
```

---

## 📂 Directory Structure

### Complete File Layout

```
/adapters/
├── inbound/                           # HTTP Routes
│   ├── tasks_routes.py               # Factory (2K)
│   ├── tasks_api.py                  # API endpoints (20K)
│   ├── tasks_intelligence_api.py     # Advanced features (10K)
│   ├── tasks_ui.py                   # UI components (8K)
│   ├── events_routes.py              # Similar pattern
│   ├── events_api.py
│   └── ... (entity types total)
│
└── persistence/                       # Data Access
    ├── neo4j/
    │   ├── universal_backend.py          # Shell: __init__, helpers (~527 lines)
    │   ├── _crud_mixin.py                # CrudOperations[T]
    │   ├── _search_mixin.py              # EntitySearchOperations[T]
    │   ├── _relationship_query_mixin.py  # RelationshipQuery + EdgeMetadata + fluent relate() API
    │   ├── _relationship_ordered_mixin.py# Ordered/hierarchical traversals + lateral-getter wrappers
    │   ├── _relationship_crud_mixin.py   # RelationshipCrud + validation helpers
    │   ├── _user_entity_mixin.py         # Generic user-entity ops
    │   ├── _traversal_mixin.py           # GraphTraversalOperations
    │   └── backends/                     # 27 domain subclasses split across 9 cluster files
    │
    └── base_adapter.py               # Shared persistence logic

/core/
├── ports/                            # Protocol interfaces
│   ├── domain_protocols.py          # TasksOperations, GoalsOperations, etc.
│   ├── curriculum_protocols.py      # KuOperations, PsOperations, LpOperations
│   ├── infrastructure_protocols.py  # EventBus, User ISP hierarchy, Schema, Ingestion
│   ├── base_protocols.py            # BackendOperations[T] ISP hierarchy
│   ├── search_protocols.py          # SearchRouter, domain search ops
│   └── ... (15 total protocol files)
│
├── services/                         # Business Logic
│   ├── tasks_service.py             # Task facade (explicit delegation methods)
│   ├── events_service.py            # Event facade
│   └── ... (entity type services)
│
├── models/                          # Domain Models
│   ├── task/
│   │   ├── task.py                 # Domain model (Tier 3)
│   │   ├── task_dto.py             # Transfer object (Tier 2)
│   │   └── task_request.py         # Pydantic models (Tier 1)
│   ├── event/
│   │   ├── event.py
│   │   ├── event_dto.py
│   │   └── event_request.py
│   └── ... (entity types)
│
└── utils/
    ├── result_simplified.py         # Result[T] pattern
    ├── error_boundary.py            # @boundary_handler
    └── logging.py                   # Logging utilities
```

---

## 🔄 Complete Data Flow Example

### Creating a Task: Step-by-Step

#### Step 1: HTTP Request Arrives

```
POST /api/tasks
Content-Type: application/json

{
  "title": "Learn Python decorators",
  "due_date": "2025-10-10",
  "priority": "high"
}
```

#### Step 2: Route Factory (tasks_routes.py)

```python
# File: /adapters/inbound/tasks_routes.py

def create_tasks_routes(app, rt, services):
    """
    Factory receives services container from bootstrap.
    Services container already has:
    - services.tasks = TasksService(TasksBackend(...))
    """
    tasks_service = services.tasks  # Extract service

    # Wire API routes
    api_routes = create_tasks_api_routes(app, rt, tasks_service)

    return api_routes
```

#### Step 3: API Route (tasks_api.py)

```python
# File: /adapters/inbound/tasks_api.py

from core.models.task.task_request import TaskCreateRequest
from core.models.task.task_dto import TaskDTO
from adapters.inbound.boundary import boundary_handler

@rt("/api/tasks", methods=["POST"])
@boundary_handler()  # Auto-converts Result[T] to HTTP response
async def create_task_route(request):
    # 1. Parse JSON body
    body = await request.json()

    # 2. Validate with Pydantic (Tier 1)
    task_request = TaskCreateRequest.model_validate(body)

    # 3. Convert to DTO (Tier 2)
    task_dto = TaskDTO(
        uid=generate_uid(),
        title=task_request.title,
        due_date=task_request.due_date,
        priority=task_request.priority
    )

    # 4. Call service
    result = await tasks_service.create_task(task_dto)

    # 5. Return Result[T]
    # @boundary_handler converts to HTTP response:
    #   - Result.ok(task) → ({"success": True, "data": task}, 200)
    #   - Result.fail(error) → ({"success": False, "error": ...}, 400)
    return result
```

#### Step 4: Service Layer (tasks_service.py)

```python
# File: /core/services/tasks_service.py

from core.ports.domain_protocols import TaskOperations
from core.models.task.task import Task
from core.utils.result_simplified import Result, Errors

class TasksService:
    def __init__(self, backend: TaskOperations):
        """
        Backend is injected as protocol interface.
        Service doesn't know concrete backend implementation!
        """
        if not backend:
            raise ValueError("Tasks backend is required")
        self.backend = backend

    async def create_task(self, dto: TaskDTO) -> Result[Task]:
        """Business logic layer."""
        # 1. Business validation
        if not dto.title:
            return Result.fail(Errors.validation(
                "Title is required",
                field="title"
            ))

        if dto.due_date and dto.due_date < date.today():
            return Result.fail(Errors.validation(
                "Due date must be in the future",
                field="due_date"
            ))

        # 2. Call backend via protocol interface
        result = await self.backend.create(dto)

        # 3. Propagate result — @boundary_handler converts to HTTP
        return result
```

#### Step 5: Backend Layer (universal_backend.py)

> **Note (March 2026):** The code below shows the historical per-domain backend pattern (pre-January 2026). The current architecture uses `UniversalNeo4jBackend[T]` — a single generic backend (shell + 6 focused mixin files) that dynamically handles all domains via Python introspection. Domain subclasses (`TasksBackend`) add only domain-specific relationship Cypher; generic CRUD/search is fully automatic. See `/docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md` and `/docs/patterns/BACKEND_OPERATIONS_ISP.md`.

```python
# File: /adapters/persistence/neo4j/universal_backend.py
# HISTORICAL EXAMPLE — current pattern is 100% dynamic via UniversalNeo4jBackend[T]

from adapters.persistence.neo4j.universal_neo4j_backend import UniversalNeo4jBackend
from core.ports.domain_protocols import TaskOperations
from core.utils.error_boundary import safe_backend_operation

class TasksUniversalBackend(UniversalNeo4jBackend, TaskOperations):
    """
    Universal backend implements TaskOperations protocol.
    """

    def __init__(self, driver):
        super().__init__(
            driver=driver,
            node_label="Task",      # Neo4j node label
            uid_prefix="task"       # UID prefix
        )

    @safe_backend_operation("create_task")
    async def create(self, dto: TaskDTO) -> Result[Task]:
        """
        Data access layer.
        Executes Neo4j query and maps result to domain model.
        """
        # 1. Build Cypher query
        cypher = """
        CREATE (t:Task {
            uid: $uid,
            title: $title,
            due_date: $due_date,
            priority: $priority,
            created_at: datetime(),
            updated_at: datetime()
        })
        RETURN t
        """

        # 2. Execute query
        params = {
            "uid": dto.uid,
            "title": dto.title,
            "due_date": dto.due_date.isoformat() if dto.due_date else None,
            "priority": dto.priority
        }

        result = await self.execute_query(cypher, params)

        # 3. Map Neo4j result to domain model
        if not result:
            return Result.fail(Errors.database(
                "Failed to create task",
                operation="create"
            ))

        node = result[0]["t"]
        task = Task.from_node(node)  # Domain model

        # 4. Return Result[Task]
        return Result.ok(task)
```

#### Step 6: Neo4j Database

```cypher
// Query executed in Neo4j:
CREATE (t:Task {
  uid: "task_abc123",
  title: "Learn Python decorators",
  due_date: "2025-10-10",
  priority: "high",
  created_at: datetime(),
  updated_at: datetime()
})
RETURN t

// Result stored as graph node
```

#### Step 7: Response Flow Back

```python
# Backend returns: Result.ok(Task(...))
#     ↓
# Service returns: Result.ok(Task(...))
#     ↓
# Route returns: Result.ok(Task(...))
#     ↓
# @boundary_handler converts to HTTP response:
#     {
#         "success": true,
#         "data": {
#             "uid": "task_abc123",
#             "title": "Learn Python decorators",
#             "due_date": "2025-10-10",
#             "priority": "high",
#             "created_at": "2025-10-02T10:30:00Z"
#         }
#     }
# HTTP Status: 201 Created
```

---

## 📦 DomainRouteConfig Pattern

### Configuration-Driven Route Registration

**What:** Declarative pattern for wiring domain routes that eliminates boilerplate in `*_routes.py` files.

**Impact:** Reduces route file complexity from ~80 lines to ~15 lines per domain (83% reduction).

**Adoption:** 42 of 46 route files (91%). ai_routes.py uses its own config-driven pattern (AIRouteSpec). All DomainRouteConfig routes are registered without `if services.X:` guards in `_wire_all_routes()` — `register_domain_routes()` handles missing services via soft-fail.

**Three tiers of the config pattern:**

| Pattern | Factory | Used By |
|---------|---------|---------|
| `create_activity_domain_route_config()` | CRUD + Query + Intelligence factories in config | All 6 Activity Domains |
| `DomainRouteConfig(crud=CRUDRouteConfig(...))` | CRUD (+ optional Intelligence) in config; domain-specific in api_factory | PathStep, Exercises, LP, Groups, RevisedExercise, FormTemplate |
| `DomainRouteConfig(...)` | API + UI factories only; no config-driven factories | KU, Askesis, Context, Search, etc. |

All 6 Activity Domains have read-focused UI views: Tasks (`/tasks`), Goals (`/goals`), Habits (`/habits`), Events (`/events`), Choices (`/choices`), Principles (`/principles`).

### Pattern Structure (Activity Domains — current)

```python
# File: /adapters/inbound/tasks_routes.py

from typing import Any

from adapters.inbound.fasthtml_types import FastHTMLApp, RouteDecorator
from adapters.inbound.route_factories import (
    create_activity_domain_route_config,
    register_domain_routes,
)
from adapters.inbound.tasks_api import create_tasks_api_routes
from adapters.inbound.tasks_ui import create_tasks_ui_routes
from core.models.task.task_request import TaskCreateRequest, TaskUpdateRequest

TASKS_CONFIG = create_activity_domain_route_config(
    domain_name="tasks",
    primary_service_attr="tasks",  # services.tasks
    api_factory=create_tasks_api_routes,
    ui_factory=create_tasks_ui_routes,
    create_schema=TaskCreateRequest,      # CRUD factory moved to config
    update_schema=TaskUpdateRequest,
    uid_prefix="task",
    supports_goal_filter=True,            # Query factory params
    supports_habit_filter=True,
    api_related_services={
        "goals_service": "goals",
        "habits_service": "habits",
    },
    prometheus_metrics_attr="prometheus_metrics",
)

def create_tasks_routes(
    app: FastHTMLApp, rt: RouteDecorator, services: Any, _sync_service: Any = None
) -> None:
    """Wire tasks API and UI routes using configuration-driven registration."""
    register_domain_routes(app, rt, services, TASKS_CONFIG)
```

**What `create_activity_domain_route_config` eliminates from `tasks_api.py`:**
- `CRUDRouteFactory` instantiation (→ config)
- `CommonQueryRouteFactory` instantiation (→ config)
- `IntelligenceRouteFactory` instantiation (→ config)

**What remains in `tasks_api.py`:**
- `create_activity_field_api_routes` (inline field updates: status, priority)
- `AnalyticsRouteFactory` (custom handlers)

### Benefits

1. **Consistency** - All domains follow same pattern
2. **Soft-fail validation** - Returns empty list if service missing (no ValueError)
3. **Automatic logging** - Built-in structured logging for route registration
4. **Clear dependencies** - Explicit service mapping via api_related_services
5. **Minimal boilerplate** - 15 lines vs 80 lines of manual wiring

**See:** `/docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md` for complete documentation and migration guide.

---

## 🏭 Route Factories

### Five Factory Types for Endpoint Generation

SKUEL uses specialized factories to generate common endpoint patterns. All factories support `ContentScope` for multi-tenant security.

#### Factory Overview

| Factory | Purpose | Endpoints Generated | ContentScope |
|---------|---------|---------------------|--------------|
| **CRUDRouteFactory** | Standard CRUD operations | create, get, update, delete, list | USER_OWNED (default) / SHARED |
| **create_activity_field_api_routes** | Inline field updates (status, priority) | `POST /api/{domain}/{uid}/{field}` | USER_OWNED |
| **CommonQueryRouteFactory** | Cross-domain query patterns | mine, by-status, goal, habit filters | USER_OWNED (default) / SHARED |
| **IntelligenceRouteFactory** | Analytics and insights | context, analytics, insights | USER_OWNED (default) / SHARED |
| **AnalyticsRouteFactory** | Custom analytics handlers | performance, behavioral, etc. | USER_OWNED only |

#### ContentScope Values

```python
from core.models.enums import ContentScope

# Activity domains (Tasks, Goals, Habits, Events, Choices, Principles, Finance, Journals)
CRUDRouteFactory(
    service=tasks_service,
    scope=ContentScope.USER_OWNED,  # Default - ownership verification
    ...
)

# Curriculum domains (KU, PS, LP)
CRUDRouteFactory(
    service=ku_service,
    scope=ContentScope.SHARED,  # No ownership checks - shared content
    ...
)
```

### Tasks API: Complete Factory Example

The following shows four of the factories in a single API file (the fifth,
`create_activity_field_api_routes`, is shown under Factory Overview above):

```python
# File: /adapters/inbound/tasks_api.py

from adapters.inbound.route_factories import (
    CRUDRouteFactory,
    CommonQueryRouteFactory,
    IntelligenceRouteFactory,
)
from adapters.inbound.route_factories.analytics_route_factory import AnalyticsRouteFactory
from core.models.enums import ContentScope
from core.models.task.task_request import TaskCreateRequest, TaskUpdateRequest

def create_tasks_api_routes(
    app, rt, tasks_service,
    user_service=None,
    goals_service=None,
    habits_service=None
):
    """Create task API routes using 4 factory patterns."""

    # 1. CRUD FACTORY - Standard operations
    crud_factory = CRUDRouteFactory(
        service=tasks_service,
        domain_name="tasks",
        create_schema=TaskCreateRequest,
        update_schema=TaskUpdateRequest,
        uid_prefix="task",
        scope=ContentScope.USER_OWNED,
    )
    crud_factory.register_routes(app, rt)
    # Generates:
    #   POST /api/tasks/create
    #   GET  /api/tasks/get?uid=...
    #   POST /api/tasks/update?uid=...
    #   POST /api/tasks/delete?uid=...
    #   GET  /api/tasks/list

    # 2. COMMON QUERY FACTORY - Cross-domain filters
    query_factory = CommonQueryRouteFactory(
        service=tasks_service,
        domain_name="tasks",
        user_service=user_service,
        goals_service=goals_service,
        habits_service=habits_service,
        supports_goal_filter=True,
        supports_habit_filter=True,
        scope=ContentScope.USER_OWNED,
    )
    query_factory.register_routes(app, rt)
    # Generates:
    #   GET /api/tasks/mine
    #   GET /api/tasks/user?user_uid=... (admin only)
    #   GET /api/tasks/goal?goal_uid=...
    #   GET /api/tasks/habit?habit_uid=...
    #   GET /api/tasks/by-status?status=...

    # 3. INTELLIGENCE FACTORY - Analytics endpoints
    intelligence_factory = IntelligenceRouteFactory(
        intelligence_service=tasks_service.intelligence,
        domain_name="tasks",
        ownership_service=tasks_service,
        scope=ContentScope.USER_OWNED,
    )
    intelligence_factory.register_routes(app, rt)
    # Generates:
    #   GET /api/tasks/context?uid=...&depth=2
    #   GET /api/tasks/analytics?period_days=30
    #   GET /api/tasks/insights?uid=...

    # 4. ANALYTICS FACTORY - Custom handlers
    async def handle_performance(service, params):
        period_days = parse_int_query_param(params, "period_days", 30, minimum=1, maximum=365)
        user_uid = params.get("_user_uid", "")
        return await service.intelligence.get_performance_analytics(user_uid, period_days)

    analytics_factory = AnalyticsRouteFactory(
        service=tasks_service,
        domain_name="tasks",
        analytics_config={
            "performance": {
                "path": "/api/tasks/analytics/performance",
                "handler": handle_performance,
                "description": "Get task performance analytics",
                "methods": ["GET"],
            },
        },
    )
    analytics_factory.register_routes(app, rt)
    # Generates:
    #   GET /api/tasks/analytics/performance

    return []  # Factories register routes via app, not return list
```

**See:** `/docs/patterns/ROUTE_FACTORIES.md` for detailed factory documentation.

---

## 🔗 Protocol-Based Dependency Injection

### Two Protocol Types in SKUEL

SKUEL uses two distinct protocol categories:

| Protocol Type | Location | Purpose | Usage |
|--------------|----------|---------|-------|
| **Domain Protocols** | `/core/ports/domain_protocols.py` | Service operation interfaces | Dependency injection (backends implement, services depend on) |
| **Facade Services** | `/core/services/{domain}_service.py` | Concrete classes with explicit delegation | Route files import concrete class as type hint |

### Domain Protocols: Service Operation Interfaces

**Purpose:** Define what operations a domain service must support, with Result[T] return types.

```python
# File: /core/ports/domain_protocols.py

from typing import Protocol
from core.models.task.task import Task
from core.utils.result_simplified import Result

class TasksOperations(Protocol):
    """
    Protocol defines what operations a task backend must support.
    Services depend on this protocol, not concrete implementations.

    All methods return Result[T] for error handling.
    """

    async def create(self, dto: TaskDTO) -> Result[Task]:
        """Create a new task"""
        ...

    async def get(self, uid: str) -> Result[Task | None]:
        """Get task by UID"""
        ...

    async def update(self, uid: str, updates: dict) -> Result[Task]:
        """Update task"""
        ...

    async def delete(self, uid: str) -> Result[bool]:
        """Delete task"""
        ...

    async def list(self, limit: int = 100) -> Result[list[Task]]:
        """List tasks"""
        ...
```

**Usage Pattern:**
```python
# Backend implements protocol
class TasksService:
    def __init__(self, backend: TasksOperations):
        self.backend = backend  # Protocol interface - dependency injection
```

### Facade Services: Concrete Classes with Explicit Delegation (February 2026)

**Purpose:** All 9 facade services (`TasksService`, `GoalsService`, etc.) have explicit `async def` delegation methods. Route files import the concrete service class directly.

**Previous approach (deleted):** `FacadeDelegationMixin` generated methods dynamically from a `_delegations` dict. `facade_protocols.py` existed to make those dynamic methods visible to MyPy. Both are deleted.

```python
# Current pattern — route file imports concrete class
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.services.goals_service import GoalsService

async def analyze_goals(goals_service: "GoalsService") -> dict:
    """
    MyPy sees all explicit methods on GoalsService directly.
    No protocol workaround needed.
    """
    milestones = await goals_service.get_goal_milestones(uid)
    progress = await goals_service.update_goal_progress(uid, 0.5)
    return {"milestones": milestones, "progress": progress}
```

### Why Two Protocol Types?

**Domain Protocols** solve dependency injection:
- Services depend on abstract interfaces, not concrete backends
- Enables testing with mocks
- Prevents circular dependencies
- All return Result[T] for consistent error handling

**Facade Services** solve type safety with explicit methods:
- All delegation methods are real `async def` — MyPy sees them natively
- Route files use `TYPE_CHECKING` import of the concrete class
- No parallel protocol file needed

### Protocol Benefits

**Without Protocols** (old way):
```python
# ❌ Service directly depends on concrete backend
from adapters.persistence.tasks_backend import TasksBackend

class TasksService:
    def __init__(self, backend: TasksBackend):
        self.backend = backend  # Concrete dependency!
```

**Problems**:
- Circular dependency risk
- Hard to test (need real backend)
- Tight coupling
- Can't swap implementations

**With Domain Protocols** (current way):
```python
# ✅ Service depends on protocol interface
from core.ports.domain_protocols import TasksOperations

class TasksService:
    def __init__(self, backend: TasksOperations):
        self.backend = backend  # Protocol interface!
```

**Benefits**:
- No circular dependencies
- Easy to mock for testing
- Loose coupling
- Can swap implementations
- Type-safe (MyPy validates)

**See:** `/docs/reference/PROTOCOL_REFERENCE.md` for complete protocol documentation.

---

## 🚀 Bootstrap Process

### How Everything Gets Wired Together

**Philosophy Change (January 2026):**
- **REQUIRED**: Neo4j (graph database), Deepgram (audio transcription) - fail fast if missing
- **OPTIONAL**: HuggingFace API (AI features) - graceful degradation with basic features if missing
- Embeddings via `EmbeddingsService` (OpenAI `text-embedding-3-small`, 1024d — ADR-068) + vector search via `Neo4jVectorSearchService`

```python
# File: /services_bootstrap/compose.py

async def compose_services(neo4j_adapter, event_bus=None, config=None, ...) -> Result[Services]:
    """
    Bootstrap delegates to helper functions for readability:
    1. Validate Neo4j + API keys (fail-fast)
    2. Create domain backends (UniversalNeo4jBackend[T])
    3. _create_activity_services() — 6 Activity Domain facades
    4. _create_core_services() — Finance, Transcription, User passthrough
    5. _create_learning_services() — Curriculum (KU, PS, LP)
    6. _wire_ai_services() — 12 AI services into facades (FULL tier only)
    7. _wire_event_subscribers() — 43 context invalidation + cross-domain events
    8. _create_intelligence_hub() — UserContextIntelligence, ZPD, Askesis
    9. Validate post-construction wiring (fail-fast if any missed)
    10. Create SearchRouter (One Path Forward)
    """

    # 1. Validate required infrastructure
    driver = neo4j_adapter.get_driver()  # Fail-fast if unavailable
    # Required: DEEPGRAM_API_KEY — fail-fast
    # Optional: OPENAI_API_KEY — warn only

    # 2. Create domain backends (15 backend instances)
    tasks_backend = TasksBackend(driver, NeoLabel.TASK, Task, base_label=NeoLabel.ENTITY)
    # ... all entity types use domain-specific Backend subclasses

    # 3-5. Delegate to helper functions
    activity_services = _create_activity_services(tasks_backend=..., ...)  # 6 facades
    core_services = _create_core_services(finance_backend=..., ...)  # Finance + Transcription
    learning_services = _create_learning_services(driver=..., ...)  # KU, PS, LP

    # 6. Wire AI (FULL tier: 12 services — 6 Activity + 3 Curriculum + 2 cross-cutting + Askesis AI)
    _wire_ai_services(llm_service=..., activity_services=activity_services, ...)

    # 7. Event-driven architecture (data-driven subscription loops)
    _wire_event_subscribers(event_bus=event_bus, ...)

    # 8. Intelligence hub (UserContextIntelligence factory + ZPD + Askesis)
    await _create_intelligence_hub(services=services, ...)

    # 9. Validate post-construction wiring (10 attributes checked)
    # Fails immediately if any post-wired dependency is None

    # 10. Return services container
    return Result.ok(services)
```

### Main Application Startup

```python
# File: main.py

async def startup():
    # 1. Initialize Neo4j
    neo4j_adapter = Neo4jGraphAdapter(uri, user, password)

    # 2. Bootstrap services
    result = await compose_services(neo4j_adapter)
    if result.is_error:
        raise Exception("Failed to bootstrap services")

    services = result.value

    # 3. Create FastHTML app
    app, rt = fast_app()

    # 4. Register routes (all domains)
    create_tasks_routes(app, rt, services)
    create_events_routes(app, rt, services)
    create_habits_routes(app, rt, services)
    # ... all entity types

    # 5. Start server
    serve()
```

---

## 📊 Layer Responsibilities

### What Each Layer Knows

| Layer | Knows About | Doesn't Know About | Responsibility |
|-------|-------------|-------------------|----------------|
| **Routes** | - Services<br>- HTTP protocols<br>- Pydantic models | ❌ Backends<br>❌ Database<br>❌ Business logic | - Parse requests<br>- Validate input<br>- Call services<br>- Format responses |
| **Services** | - Domain models<br>- Business rules<br>- Protocols | ❌ HTTP<br>❌ Routes<br>❌ Database details | - Business validation<br>- Orchestration<br>- Domain logic<br>- Error handling |
| **Backends** | - Database<br>- Queries<br>- Protocols | ❌ HTTP<br>❌ Routes<br>❌ Business logic | - Data access<br>- Query execution<br>- Result mapping<br>- Transaction handling |

---

## 🔒 Security: Ownership Verification

### Multi-Tenant Data Isolation

SKUEL implements ownership verification to ensure users can only access entities they own. This prevents IDOR (Insecure Direct Object Reference) attacks.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  1. AUTHENTICATION (Session Layer)                                   │
│     require_authenticated_user(request) → user_uid                  │
│     Raises 401 if not logged in                                     │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│  2. OWNERSHIP VERIFICATION (Service Layer)                           │
│     service.verify_ownership(uid, user_uid) → Result[Entity]        │
│     Returns 404 if user doesn't own entity                          │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│  3. DATA ACCESS (Backend Layer)                                      │
│     Entity retrieved and verified to belong to user                  │
└─────────────────────────────────────────────────────────────────────┘
```

### Route Implementation Pattern

**Factory-Generated Routes:** CRUDRouteFactory automatically verifies ownership when `scope=ContentScope.USER_OWNED` (default for user-owned domains).

**Factory Examples:**

```python
from core.models.enums import ContentScope

# Activity domains - user-owned content
factory = CRUDRouteFactory(
    service=tasks_service,
    scope=ContentScope.USER_OWNED  # Default - ownership verification
)

# Curriculum domains - shared content
factory = CRUDRouteFactory(
    service=ku_service,
    scope=ContentScope.SHARED  # No ownership checks
)
```

**Manual Routes:** Must include explicit ownership check for user-owned content:

```python
from adapters.inbound.auth import require_authenticated_user

@rt("/api/tasks/{uid}/complete")
@boundary_handler()
async def complete_task_route(request: Request) -> Result[Task]:
    """Complete a task (requires ownership)."""
    uid = request.path_params["uid"]
    user_uid = require_authenticated_user(request)  # 1. Authenticate

    # 2. Verify ownership
    ownership = await tasks_service.verify_ownership(uid, user_uid)
    if ownership.is_error:
        return ownership  # Returns 404

    # 3. Safe to proceed
    return await tasks_service.complete_task(uid)
```

### Domain Categories

| Category | Domains | Content Scope |
|----------|---------|---------------|
| **User-Owned** | Tasks, Goals, Habits, Events, Choices, Principles, Submissions (incl. Journals) | `ContentScope.USER_OWNED` |
| **Shared** | KU, PS, LP | `ContentScope.SHARED` |
| **Admin-Only** | Finance | `ContentScope.ADMIN_ONLY` |

**Note:** MOC is not a domain — it's emergent identity (any Entity with outgoing ORGANIZES relationships).

### Security Benefits

1. **IDOR Prevention** - Users cannot access other users' data
2. **Information Hiding** - Returns 404 (not 403) to avoid revealing UID existence
3. **Consistent Behavior** - Same pattern across all 42 manual routes

**See:** `/docs/patterns/OWNERSHIP_VERIFICATION.md` for complete documentation

---

## 🎯 Testing Strategy

### Layer-Specific Testing

#### Testing Routes (Fast, No DB)

```python
def test_create_task_route():
    # Mock service
    mock_service = Mock()
    mock_service.create_task.return_value = Result.ok(Task(...))

    # Test route with mock
    result = await create_task_route(mock_request, mock_service)

    assert result.is_success()
    assert mock_service.create_task.called
```

#### Testing Services (Medium, Protocol Mocks)

```python
def test_tasks_service_validation():
    # Mock backend (protocol)
    mock_backend = Mock(TaskOperations)

    # Create service with mock
    service = TasksService(backend=mock_backend)

    # Test validation
    result = await service.create_task(TaskDTO(title=""))

    assert result.is_error
    assert result.error.category == "VALIDATION"
    assert not mock_backend.create.called  # Validation failed before backend
```

#### Testing Backends (Slow, Needs DB)

```python
async def test_tasks_backend_integration():
    # Real Neo4j connection (test database)
    driver = get_test_driver()
    backend = TasksBackend(driver, NeoLabel.TASK, Task, base_label=NeoLabel.ENTITY)

    # Test real database operation
    dto = TaskDTO(uid="test", title="Test Task")
    result = await backend.create(dto)

    assert result.is_success()
    assert result.value.title == "Test Task"

    # Cleanup
    await cleanup_test_data(driver)
```

---

## 💡 Key Takeaways

### Architecture Benefits

1. **Decoupling** - Each layer independent
2. **Testability** - Mock at any layer
3. **Type Safety** - Protocols + MyPy
4. **Maintainability** - Clear responsibilities
5. **Scalability** - Add domains easily

### The Flow is Always

```
HTTP Request
    → Route (validate)
    → Service (business logic)
    → Backend (data access)
    → Database

Database
    → Backend (map result)
    → Service (process)
    → Route (format)
    → HTTP Response
```

### Protocol-Based Dependency Injection

```
Services depend on: Protocol interfaces (abstract)
Backends implement: Protocol interfaces (concrete)
Bootstrap wires: Concrete backends into services
```

This architecture ensures:
- ✅ No circular dependencies
- ✅ Easy testing (mock protocols)
- ✅ Type-safe (MyPy validates)
- ✅ Flexible (swap implementations)
- ✅ Clean (clear separation)

---

## See Also

- [Route Decorator Architecture](/docs/patterns/ROUTE_DECORATOR_ARCHITECTURE.md) — Decorator composition (`@rt` + `@boundary_handler`), lateral routes, FastHTML alignment
- [Route Factories](/docs/patterns/ROUTE_FACTORIES.md) — Factory reference (CRUD, Status, Query, Intelligence, Analytics)
- [Route Naming Convention](/docs/patterns/ROUTE_NAMING_CONVENTION.md) — File naming: `_routes.py`, `_api.py`, `_ui.py`

*Last Updated: March 3, 2026*
*Architecture: Routes → Services → Backends → Neo4j*
*Pattern: Protocol-Based Dependency Injection*
*Security: Content Scope (USER_OWNED / SHARED / ADMIN_ONLY) on All Routes*
*Philosophy: Clean Architecture, One Path Forward, Graceful Degradation for AI Features*
*AI Services: OpenAI embeddings via `create_embedding_client()` (ADR-068; BGE-M3 staged — ADR-083), Neo4j Vector Search (optional)*
