---
title: SKUEL Routing Architecture: Routes, Services, and Persistence
updated: 2026-01-29
status: current
category: architecture
tags: [architecture, routing, security]
related: [OWNERSHIP_VERIFICATION.md]
---

# SKUEL Routing Architecture: Routes, Services, and Persistence

**Last Updated**: January 29, 2026

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
│  │ universal_backend.py (Data Access)                     │ │
│  │                                                               │ │
│  │   class TasksUniversalBackend(                               │ │
│  │       UniversalNeo4jBackend,                                 │ │
│  │       TaskOperations  # Implements protocol!                 │ │
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
│   └── ... (15 domains total)
│
└── persistence/                       # Data Access
    ├── neo4j/
    │   ├── universal_backend.py      # Task data access
    │   ├── events_universal_backend.py     # Event data access
    │   ├── universal_neo4j_backend.py      # Base class
    │   └── ... (15 domain backends)
    │
    └── base_adapter.py               # Shared persistence logic

/core/
├── services/                         # Business Logic
│   ├── tasks_service.py             # Task business logic
│   ├── events_service.py            # Event business logic
│   ├── protocols/                   # Protocol interfaces
│   │   ├── domain_protocols.py     # TaskOperations, EventOperations
│   │   ├── knowledge_protocols.py
│   │   └── infrastructure_protocols.py
│   └── ... (15 domain services)
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
│   └── ... (15 domains)
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
    - services.tasks = TasksService(TasksUniversalBackend(...))
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
from core.utils.error_boundary import boundary_handler

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

from core.services.protocols.domain_protocols import TaskOperations
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
        """
        Business logic layer.
        Returns Result[T] for error handling.
        """
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

        # 3. Handle backend result
        if result.is_error:
            return result  # Propagate error

        # 4. Return success
        return Result.ok(result.value)
```

#### Step 5: Backend Layer (universal_backend.py)

```python
# File: /adapters/persistence/neo4j/universal_backend.py

from adapters.persistence.neo4j.universal_neo4j_backend import UniversalNeo4jBackend
from core.services.protocols.domain_protocols import TaskOperations
from core.utils.backend_decorators import safe_backend_operation

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

**Adoption:** 12 of 27 route files (44%) - all Activity domains plus Learning, Knowledge, Context, Reports, Finance, and Askesis.

### Pattern Structure

```python
# File: /adapters/inbound/tasks_routes.py

from adapters.inbound.tasks_api import create_tasks_api_routes
from adapters.inbound.tasks_ui import create_tasks_ui_routes
from core.infrastructure.routes import DomainRouteConfig, register_domain_routes

TASKS_CONFIG = DomainRouteConfig(
    domain_name="tasks",
    primary_service_attr="tasks",  # services.tasks
    api_factory=create_tasks_api_routes,
    ui_factory=create_tasks_ui_routes,
    api_related_services={
        # Format: {kwarg_name: container_attr}
        "user_service": "user_service",  # Passed as user_service=services.user_service
        "goals_service": "goals",        # Passed as goals_service=services.goals
        "habits_service": "habits",      # Passed as habits_service=services.habits
    },
)

def create_tasks_routes(app, rt, services, _sync_service=None):
    """Wire tasks API and UI routes using configuration-driven registration."""
    return register_domain_routes(app, rt, services, TASKS_CONFIG)
```

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
| **StatusRouteFactory** | Status transitions with validation | complete, uncomplete, archive, etc. | USER_OWNED (default) / SHARED |
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

# Curriculum domains (KU, LS, LP)
CRUDRouteFactory(
    service=ku_service,
    scope=ContentScope.SHARED,  # No ownership checks - shared content
    ...
)
```

### Tasks API: Complete Factory Example

The following shows all 5 factories in a single API file:

```python
# File: /adapters/inbound/tasks_api.py

from core.infrastructure.routes import (
    CRUDRouteFactory,
    StatusRouteFactory,
    CommonQueryRouteFactory,
    IntelligenceRouteFactory,
)
from core.infrastructure.routes.analytics_route_factory import AnalyticsRouteFactory
from core.models.enums import ContentScope
from core.models.task.task_request import TaskCreateRequest, TaskUpdateRequest

def create_tasks_api_routes(
    app, rt, tasks_service,
    user_service=None,
    goals_service=None,
    habits_service=None
):
    """Create task API routes using 5 factory patterns."""

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

    # 2. STATUS FACTORY - Status transitions with body validation
    status_factory = StatusRouteFactory(
        service=tasks_service,
        domain_name="tasks",
        transitions={
            "complete": StatusTransition(
                target_status="completed",
                requires_body=True,
                body_fields=["actual_minutes", "quality_score"],
                method_name="complete_task",
            ),
            "uncomplete": StatusTransition(
                target_status="in_progress",
                method_name="uncomplete_task",
            ),
        },
        scope=ContentScope.USER_OWNED,
    )
    status_factory.register_routes(app, rt)
    # Generates:
    #   POST /api/tasks/complete?uid=...
    #   POST /api/tasks/uncomplete?uid=...

    # 3. COMMON QUERY FACTORY - Cross-domain filters
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

    # 4. INTELLIGENCE FACTORY - Analytics endpoints
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

    # 5. ANALYTICS FACTORY - Custom handlers
    async def handle_performance(service, params):
        period_days = int(params.get("period_days", "30"))
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
| **Domain Protocols** | `/core/services/protocols/domain_protocols.py` | Service operation interfaces | Dependency injection (backends implement, services depend on) |
| **Facade Protocols** | `/core/services/protocols/facade_protocols.py` | Type hints for dynamic methods | Type safety at call sites (NOT for inheritance) |

### Domain Protocols: Service Operation Interfaces

**Purpose:** Define what operations a domain service must support, with Result[T] return types.

```python
# File: /core/services/protocols/domain_protocols.py

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

### Facade Protocols: Type Hints for Dynamic Methods

**Purpose:** Provide type declarations for methods created dynamically by `FacadeDelegationMixin`.

**CRITICAL:** These are for TYPE HINTS only, NOT for inheritance. Facade methods are created dynamically at class definition time - MyPy can't see them, so protocols enable structural subtyping.

```python
# File: /core/services/protocols/facade_protocols.py

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from core.models.goal.goal import Goal
    from core.utils.result_simplified import Result

class GoalsFacadeProtocol(Protocol):
    """
    Type declarations for dynamically delegated methods.

    WARNING: Do NOT inherit from this protocol in GoalsService.
    Use as TYPE HINT for parameters accepting facade instances.
    """

    async def get_goal_milestones(self, uid: str) -> Result[list[dict]]:
        """Get goal milestones (delegated to goals_milestones sub-service)"""
        ...

    async def update_goal_progress(self, uid: str, progress: float) -> Result[Goal]:
        """Update goal progress (delegated to goals_progress sub-service)"""
        ...
```

**Usage Pattern:**
```python
# At call sites (NOT in service definition)
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from core.services.protocols.facade_protocols import GoalsFacadeProtocol

async def analyze_goals(goals_service: "GoalsFacadeProtocol") -> dict:
    """
    MyPy sees method declarations from protocol.
    Runtime uses structural subtyping (duck typing).
    """
    milestones = await goals_service.get_goal_milestones(uid)
    progress = await goals_service.update_goal_progress(uid, 0.5)
    return {"milestones": milestones, "progress": progress}

# In routes with dynamic delegation
@rt("/api/tasks/assign")
async def assign_task_route(request: Request) -> Result[Any]:
    # Cast to protocol for MyPy (FacadeDelegationMixin creates methods dynamically)
    facade = cast("TasksFacadeProtocol", tasks_service)
    return await facade.assign_task_to_user(uid, target_uid, assigned_by)
```

### Why Two Protocol Types?

**Domain Protocols** solve dependency injection:
- Services depend on abstract interfaces, not concrete backends
- Enables testing with mocks
- Prevents circular dependencies
- All return Result[T] for consistent error handling

**Facade Protocols** solve type safety with dynamic methods:
- FacadeDelegationMixin creates methods at class definition time
- MyPy can't see dynamically created methods
- Protocols provide structural subtyping (duck typing)
- Used as type hints at call sites, NOT base classes

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
from core.services.protocols.domain_protocols import TasksOperations

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
- **OPTIONAL**: OpenAI API (AI features) - graceful degradation with basic features if missing
- Neo4j GenAI embeddings and vector search services enabled via Neo4j GenAI Plugin (Docker/AuraDB)

```python
# File: /core/utils/services_bootstrap.py

async def compose_services(neo4j_adapter, event_bus=None) -> Result[Services]:
    """
    Bootstrap process:
    1. Create driver
    2. Validate required API keys (fail-fast: Deepgram; optional: OpenAI)
    3. Create universal backends
    4. Create optional AI services (Neo4j GenAI embeddings, vector search)
    5. Inject backends into services
    6. Return services container
    """

    # 1. Get Neo4j driver
    driver = neo4j_adapter.get_driver()

    # 2. Validate API keys (GRACEFUL DEGRADATION)
    # Required: DEEPGRAM_API_KEY - app fails without it
    # Optional: OPENAI_API_KEY - app runs with basic features
    required_keys = {
        "DEEPGRAM_API_KEY": "Deepgram API (required for audio transcription)",
    }

    recommended_keys = {
        "OPENAI_API_KEY": "OpenAI API (optional - enables embeddings, semantic search, AI features)",
    }

    # Fail fast on missing required keys
    # Warn on missing optional keys (app continues)

    # 3. Create optional AI services
    try:
        openai_api_key = get_credential("OPENAI_API_KEY", fallback_to_env=True)
        if openai_api_key and openai_api_key not in ["your-openai-api-key-here", "", "sk-"]:
            embeddings_service = OpenAIEmbeddingsService(api_key=openai_api_key)
            logger.info("✅ Embeddings service initialized (OpenAI)")
        else:
            embeddings_service = None
            logger.warning("⚠️ Embeddings service disabled - app runs with basic features only")
    except Exception as e:
        embeddings_service = None
        logger.warning("⚠️ Embeddings service disabled - continuing with basic features")

    # 4. Create Neo4j GenAI services (January 2026 - Vector Search Integration)
    # Uses Neo4j's native GenAI plugin for embeddings and vector search
    # Docker: API key via environment variable (per-query token)
    # AuraDB: API key at database level (see /docs/deployment/AURADB_MIGRATION_GUIDE.md)
    try:
        genai_embeddings_service = Neo4jGenAIEmbeddingsService(driver)
        vector_search_service = Neo4jVectorSearchService(driver, genai_embeddings_service)
        logger.info("✅ Neo4j GenAI services created (vector search enabled)")
    except Exception as e:
        genai_embeddings_service = None
        vector_search_service = None
        logger.warning("⚠️ Neo4j GenAI services unavailable - using keyword search fallback")

    # 5. Create universal backends (implement protocols)
    tasks_backend = TasksUniversalBackend(driver)
    events_backend = EventsUniversalBackend(driver)
    habits_backend = HabitsUniversalBackend(driver)
    # ... all 15 domains

    # 6. Create services with backend injection and optional AI services
    tasks_service = TasksService(backend=tasks_backend)
    events_service = EventsService(backend=events_backend)
    habits_service = HabitsService(backend=habits_backend)

    # KU service receives optional vector search and embeddings services
    ku_service = KuService(
        repo=knowledge_backend,
        # ... other dependencies ...
        vector_search_service=vector_search_service,  # Optional - can be None
        embeddings_service=genai_embeddings_service,  # Optional - can be None
    )
    # ... all 15 domains

    # 7. Return services container
    services = Services(
        tasks=tasks_service,
        events=events_service,
        habits=habits_service,
        ku=ku_service,
        # ... all 15 domains
    )

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
    # ... all 15 domains

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

**Factory-Generated Routes:** CRUDRouteFactory and StatusRouteFactory automatically verify ownership when `scope=ContentScope.USER_OWNED` (default for user-owned domains).

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
from core.auth import require_authenticated_user

@rt("/api/tasks/{uid}/complete")
@boundary_handler()
async def complete_task_route(request: Request) -> Result[Any]:
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
| **User-Owned** | Tasks, Goals, Habits, Events, Choices, Principles, Finance, Journals | `ContentScope.USER_OWNED` |
| **Shared** | KU, LS, LP, MOC | `ContentScope.SHARED` |

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
    backend = TasksUniversalBackend(driver)

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

*Last Updated: January 29, 2026*
*Architecture: Routes → Services → Backends → Neo4j*
*Pattern: Protocol-Based Dependency Injection*
*Security: Content Scope (USER_OWNED vs SHARED) on All Routes*
*Philosophy: Clean Architecture, One Path Forward, Graceful Degradation for AI Features*
*AI Services: OpenAI (optional), Neo4j GenAI Vector Search (optional)*
