---
title: SKUEL Architecture Guide
updated: 2026-01-20
status: current
category: architecture
tags: [architecture, overview]
related: []
tracking: conceptual
last_reviewed: 2026-01-20
review_frequency: quarterly
---

# SKUEL Architecture Guide

**Last Updated**: January 20, 2026

## Executive Summary

SKUEL is a **knowledge-centric productivity platform** built on clean architecture principles. The system embodies the insight that **knowledge is the fertile soil from which all productivity grows**, with every operation connecting to and enriching understanding.

### The 14-Domain + 5 Cross-Cutting Systems Architecture

SKUEL organizes human experience into **14 domains** across five categories, with 5 cross-cutting systems that orchestrate intelligence:

| Category | Domains | Purpose |
|----------|---------|---------|
| **Activity (6)** | Tasks, Habits, Goals, Events, Principles, Choices | What I DO |
| **Finance (1)** | Finance | What I MANAGE (standalone) |
| **Curriculum (3)** | KnowledgeUnit, LearningStep, LearningPath | What I LEARN |
| **Content/Processing (2)** | Assignments, Journals | How I PROCESS |
| **Organizational (1)** | MOC (KU-based) | How I ORGANIZE |
| **LifePath (1)** | LifePath | Where I'm GOING (The Destination) |

**Cross-Cutting Systems (5)**: UserContext (✅), Search (✅), Calendar (✅), Askesis (✅), Messaging (📋 planned)

> **See**: [FOURTEEN_DOMAIN_ARCHITECTURE.md](./FOURTEEN_DOMAIN_ARCHITECTURE.md) for complete domain documentation including DSL integration, graph architecture, and service patterns.

### Core Philosophy
- **Knowledge-First Design**: All operations begin with knowledge discovery or application
- **One Path Forward**: Single, clear way to accomplish tasks - no backward compatibility burden
- **Clean Code Focus**: Deprecated code archived, not maintained in active codebase
- **Protocol-Based Dependency Injection**: All services use Python Protocol interfaces
- **Three-Tier Type System**: Pydantic at edges, DTOs for transfer, frozen domain models at core
- **Fail-Fast Philosophy**: Require components to work properly - no graceful degradation
- **LifePath Destination**: Everything flows toward your ultimate life vision

---

## 🏗️ System Architecture Layers

### Complete Architecture Flow

```
External World (HTTP/Files)
        ↓
┌─────────────────────────────────────────────────────────────┐
│                    INBOUND LAYER                            │
│  Routes (FastHTML) → Pydantic Validation → @boundary_handler│
│  Location: /adapters/inbound/                               │
│  Pattern: Factory → API + Intelligence + UI                 │
└─────────────────────────────────────────────────────────────┘
        ↓ Services Container
┌─────────────────────────────────────────────────────────────┐
│                    SERVICE LAYER                            │
│  Business Logic with Protocol Dependencies                  │
│  Location: /core/services/                                  │
│  Returns: Result[T] for all operations                      │
└─────────────────────────────────────────────────────────────┘
        ↓ Protocol Interfaces
┌─────────────────────────────────────────────────────────────┐
│                    DOMAIN LAYER                             │
│  Pure Domain Models (Frozen Dataclasses)                    │
│  Location: /core/models/                                    │
│  Pattern: Three-Tier (Pydantic → DTO → Domain)             │
└─────────────────────────────────────────────────────────────┘
        ↓ Backend Protocols
┌─────────────────────────────────────────────────────────────┐
│                    PERSISTENCE LAYER                        │
│  Universal Backends with Protocol Implementation            │
│  Location: /adapters/persistence/                           │
│  Storage: Neo4j Graph Database                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 📋 Routing Architecture (Factory Pattern)

### Clean Separation of Concerns

Every domain follows a consistent **Factory Pattern** with clean separation:

```
Domain Routes Structure:
├── {domain}_routes.py          # Thin factory (2-4K)
├── {domain}_api.py             # Pure JSON endpoints (10-30K)
├── {domain}_intelligence_api.py # Advanced features (5-15K) [optional]
└── {domain}_ui.py              # Component rendering (5-15K)
```

### The Flow: Bootstrap → Routes → Services

```python
# 1. Bootstrap (services_bootstrap.py)
#    Creates Universal Backends
#    Injects backends into Services
#    Returns Services container

backend = TasksUniversalBackend(driver)
tasks_service = TasksService(backend)
services = Services(tasks=tasks_service, ...)

# 2. Route Factory ({domain}_routes.py)
#    Receives Services container
#    Extracts specific service
#    Passes to API/UI creation

def create_tasks_routes(app, rt, services):
    tasks_service = services.tasks
    api_routes = create_tasks_api_routes(app, rt, tasks_service)
    ui_routes = create_tasks_ui_routes(app, rt, tasks_service)
    return api_routes + ui_routes

# 3. API Files ({domain}_api.py)
#    Receives service parameter
#    Calls service methods
#    NEVER directly touches backends

@rt("/api/tasks", methods=["POST"])
@boundary_handler()
async def create_task_route(request):
    result = await tasks_service.create_task(dto)
    return result  # Auto-converts to HTTP response
```

### Decoupling Achieved

| Layer | Knows About | Doesn't Know About |
|-------|-------------|-------------------|
| **Routes** | Services | ❌ Backends, Database |
| **Services** | Protocols, Domain Models | ❌ Routes, HTTP |
| **Backends** | Database, Protocols | ❌ Services, Routes |

### Route Files Status (15 Domains)

**All domains follow Factory Pattern (100% consistency)**:

1. **tasks** - Factory + API + Intelligence + UI
2. **events** - Factory + API + Intelligence + UI
3. **habits** - Factory + API + Intelligence + UI
4. **goals** - Factory + API + Intelligence + UI
5. **knowledge** - Factory + API + Intelligence + UI
6. **choice** - Factory + API + Intelligence + UI
7. **principles** - Factory + API + Intelligence + UI
8. **askesis** - Factory + API + Intelligence + UI
9. **learning** - Factory + API + Intelligence + UI
10. **context_aware** - Factory + API + Intelligence + UI
11. **search** - Factory + API + Intelligence + UI
12. **finance** - Factory + API + UI
13. **journals** - Factory + API + UI
14. **system** - Factory + API + UI
15. **transcription** - Factory + API + UI

---

## 🔧 Protocol-Based Architecture

### The Revolution: Zero Port Dependencies

All services use **Protocol interfaces exclusively** - no concrete dependencies, no circular imports.

#### Protocol Organization

```
core/ports/
├── domain_protocols.py          # Business domain operations
├── knowledge_protocols.py       # Knowledge management
├── search_protocols.py          # Search operations
└── infrastructure_protocols.py  # System & infrastructure
```

#### Service Declaration Pattern

```python
# Modern Protocol-Based Approach
from core.ports.domain_protocols import TaskOperations

class TasksService:
    def __init__(self, backend: Optional[TaskOperations] = None):
        if not backend:
            raise ValueError("Tasks backend is required")
        self.backend = backend  # Protocol interface
```

#### Benefits

✅ **Type Safety** - MyPy validates at development time
✅ **Easy Testing** - Mock protocols, not implementations
✅ **Clear Contracts** - Services declare exactly what they need
✅ **No Circular Dependencies** - Services depend on abstractions
✅ **One Path Forward** - Single approach everywhere

---

## 📊 Three-Tier Type System

### Core Principle: "Pydantic at the edges, pure Python at the core"

```
External World → [Pydantic] → [DTOs] → [Domain Models] → Core Logic
```

| Tier | Type | Mutability | Purpose | Location |
|------|------|------------|---------|----------|
| **External** | Pydantic Models | N/A | Validation & serialization | `*_request.py` |
| **Transfer** | DTOs | Mutable | Data movement between layers | `*_dto.py` |
| **Core** | Domain Models | **Frozen** | Immutable business entities | `{domain}.py` |

### Implementation Example

```python
# Tier 1: Pydantic (External Boundary)
class TaskCreateRequest(BaseModel):
    title: str
    due_date: Optional[date]

# Tier 2: DTO (Transfer Layer)
@dataclass
class TaskDTO:
    uid: str
    title: str
    due_date: Optional[date]

# Tier 3: Domain Model (Core Business Logic)
@dataclass(frozen=True)
class Task:
    uid: str
    title: str
    due_date: Optional[date]

    def is_overdue(self) -> bool:
        """Business logic lives here"""
        return self.due_date and self.due_date < date.today()
```

### Directory Structure

```
/core/models/
├── task/
│   ├── task.py            # Tier 3: Domain model
│   ├── task_dto.py        # Tier 2: DTO
│   └── task_request.py    # Tier 1: Pydantic
├── event/
│   ├── event.py
│   ├── event_dto.py
│   └── event_request.py
└── enums/                 # Shared enumerations (organized by domain)
```

---

## ⚡ Error Handling Pattern

### Results Internally, Exceptions at Boundaries

SKUEL uses a consistent error handling pattern throughout:

```python
# Service Layer - Returns Result[T]
async def get_task(self, uid: str) -> Result[Task]:
    result = await self.backend.get_task(uid)
    if result.is_error:
        return result  # Propagate error

    if not result.value:
        return Result.fail(not_found_error(f"Task {uid} not found"))

    return Result.ok(result.value)

# Route Layer - Boundary conversion with @boundary_handler
@rt("/api/tasks/{uid}")
@boundary_handler()  # Converts Result to HTTP response
async def get_task_route(request, uid: str):
    return await service.get_task(uid)
    # Automatically becomes (response_body, status_code)
```

### Error Categories (6 Total)

| Category | Description | HTTP Status |
|----------|-------------|-------------|
| VALIDATION | Invalid input data | 400 |
| NOT_FOUND | Resource doesn't exist | 404 |
| BUSINESS | Business rule violation | 422 |
| DATABASE | Storage layer issues | 503 |
| INTEGRATION | External service issues | 502 |
| SYSTEM | Unexpected errors | 500 |

### Key Benefits

- ✅ **No unexpected exceptions** in business logic
- ✅ **Type-safe error handling** with Result[T]
- ✅ **Automatic HTTP mapping** at boundaries
- ✅ **Rich error context** for debugging
- ✅ **Consistent pattern** everywhere

---

## 💾 Persistence Layer Architecture

### Universal Backend Pattern

All domains use **Universal Backends** that implement protocol interfaces:

```python
class TasksUniversalBackend(UniversalNeo4jBackend, TaskOperations):
    """
    Universal backend for tasks domain.
    Implements TaskOperations protocol.
    """
    def __init__(self, driver):
        super().__init__(
            driver=driver,
            node_label="Task",
            uid_prefix="task"
        )
```

### Neo4j Graph Database

**Structure**:
```
Nodes: Domain entities (Task, Event, Goal, Knowledge, etc.)
Relationships: Domain connections (DEPENDS_ON, ENABLES, REQUIRES, etc.)
Properties: Entity data as node properties
Indexes: UID-based for fast lookups
```

**Location**: `/adapters/persistence/neo4j/`

### Generic Programming Patterns

1. **Generic Repository[T]** - `/core/patterns/repository.py`
2. **Generic Neo4j Mapper** - `/core/utils/neo4j_mapper.py`
3. **Unified Query Builder** - `/core/services/unified_query_builder.py`
4. **Result[T] Pattern** - `/core/utils/result_simplified.py`
5. **BaseAdapter Pattern** - `/adapters/persistence/base_adapter.py`

---

## 🌐 Domain Architecture

### The 14-Domain Mental Model

SKUEL's architecture represents human experience as **14 interconnected domains** flowing toward your LifePath:

```
                        ┌──────────────────┐
                        │    LifePath      │ ← THE DESTINATION
                        │  (Your Vision)   │
                        └────────┬─────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        │                        │                        │
        ▼                        ▼                        ▼
┌───────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  PRINCIPLES   │      │     GOALS       │      │   KNOWLEDGE     │
│   (Values)    │─────►│   (Outcomes)    │◄─────│  (KU → LS → LP) │
└───────────────┘      └────────┬────────┘      └─────────────────┘
        │                       │                        │
        ▼                       ▼                        ▼
┌───────────────┐      ┌─────────────────┐      ┌─────────────────┐
│    CHOICES    │      │     HABITS      │      │    CALENDAR     │
│  (Decisions)  │─────►│   (Practices)   │◄─────│   (Schedule)    │
└───────────────┘      └────────┬────────┘      └─────────────────┘
        │                       │                        │
        ▼                       ▼                        ▼
┌───────────────┐      ┌─────────────────┐      ┌─────────────────┐
│    FINANCE    │      │     TASKS       │      │     EVENTS      │
│  (Resources)  │─────►│    (Actions)    │◄─────│    (Time)       │
└───────────────┘      └────────┬────────┘      └─────────────────┘
                                │
                    ┌───────────┴───────────┐
                    │      ASSIGNMENTS      │ ← Content Processing
                    │  (Journals, Essays)   │
                    └───────────────────────┘
                                │
                    ┌───────────┴───────────┐
                    │       REPORTS         │ ← Analytics & Insights
                    │  (Progress Reviews)   │
                    └───────────────────────┘
```

### The Five Domain Categories

**Activity Domains (6)** - What I DO:
| Domain | Purpose | Key Relationships |
|--------|---------|-------------------|
| **Tasks** | Concrete work items | APPLIES_KNOWLEDGE, FULFILLS_GOAL |
| **Habits** | Recurring behaviors | REINFORCES, BUILDS_TOWARD_GOAL |
| **Goals** | Desired outcomes | GUIDED_BY_PRINCIPLE, REQUIRES_KNOWLEDGE |
| **Events** | Scheduled occurrences | PRACTICES_KNOWLEDGE, EXECUTES_TASK |
| **Principles** | Core values | GROUNDED_IN_KNOWLEDGE, GUIDES_GOAL |
| **Choices** | Decision points | INFORMED_BY_KNOWLEDGE, ALIGNED_WITH |

**Finance Domain (1)** - What I MANAGE (standalone):
| Domain | Purpose | Key Relationships |
|--------|---------|-------------------|
| **Finance** | Resource management | ENABLES_GOAL, SUPPORTS_HABIT |

**Curriculum Domains (3)** - What I LEARN:
| Domain | Purpose | Key Relationships |
|--------|---------|-------------------|
| **KnowledgeUnit (KU)** | Atomic knowledge | REQUIRES, ENABLES, HAS_NARROWER |
| **LearningStep (LS)** | Learning activities | TEACHES_KU, NEXT_STEP, BELONGS_TO |
| **LearningPath (LP)** | Learning sequences | CONTAINS, PREREQUISITE, ACHIEVES |

**Content/Processing Domains (2)** - How I PROCESS:
| Domain | Purpose | Key Relationships |
|--------|---------|-------------------|
| **Assignments** | Content processing | PRODUCES_INSIGHT, REFLECTS_ON |
| **Journals** | AI formatting | PROCESSES_INPUT, EXTRACTS_ACTIVITIES |

**Organizational Domain (1)** - How I ORGANIZE (January 2026 - KU-based):
| Domain | Purpose | Key Relationships |
|--------|---------|-------------------|
| **MOC** | KU-based hierarchy | ORGANIZES (KU → KU) |

**Note:** MOC is NOT a separate entity - it IS a KU with ORGANIZES relationships. A KU "is" a MOC when it has outgoing ORGANIZES relationships (emergent identity).

**LifePath (1)** - The Destination:
| Domain | Purpose | Key Relationships |
|--------|---------|-------------------|
| **LifePath** | Ultimate vision | GUIDES_ALL, MEASURES_ALIGNMENT |

> **Complete Documentation**: See [FOURTEEN_DOMAIN_ARCHITECTURE.md](./FOURTEEN_DOMAIN_ARCHITECTURE.md) for DSL integration, graph architecture, and service patterns.

---

## 🔄 Service Architecture

### Base Service Pattern

```python
from typing import Generic, TypeVar, Optional
from core.ports.domain_protocols import TaskOperations

class TasksService:
    """Service for task management with protocol-based dependency injection"""

    def __init__(self, backend: Optional[TaskOperations] = None):
        if not backend:
            raise ValueError("Tasks backend is required")
        self.backend = backend
        self.logger = get_logger(__name__)

    async def create_task(self, dto: TaskDTO) -> Result[Task]:
        """Create task - returns Result[T] for error handling"""
        # Validation
        if not dto.title:
            return Result.fail(validation_error("Title required"))

        # Backend operation
        result = await self.backend.create(dto)
        if result.is_error:
            return result

        return Result.ok(result.value)
```

### Service Categories

**Core Domain Services** (Protocol-Based):
- TasksService, EventsService, HabitsService, GoalsService
- KnowledgeService, LearningService, PrinciplesService

**Orchestration Services**:
- UnifiedCalendarService - Combines tasks, events, habits
- PathOrchestratorService - Unifies learning & goal paths
- AskesisService - AI learning assistant

**Infrastructure Services**:
- UserService, TranscriptionService, SyncService

---

## 🎯 Key Design Decisions

### Why Protocols?

1. **No Circular Dependencies** - Services depend on abstractions (See: [Circular Dependency Resolution](./archive/migrations_2025/CIRCULAR_DEPENDENCY_RESOLUTION_OCT_2025.md))
2. **Type Safety** - MyPy catches errors at development time
3. **Easy Testing** - Mock protocols, not implementations
4. **Clean Architecture** - Clear separation of concerns

**Protocol Pattern for Breaking Circular Dependencies**:
When Service A needs Service B, but Service B also needs Service A:
1. Create a minimal protocol with just the methods Service A needs
2. Service A depends on the protocol, not concrete Service B
3. Wire up concrete implementation during bootstrap
4. Result: Service A → Protocol (no circular dependency!)

### Why Three Tiers?

1. **Separation** - External validation separate from business logic
2. **Immutability** - Domain models can't be accidentally modified
3. **Flexibility** - DTOs allow data transformation
4. **Simplicity** - No complex framework inheritance

### Why Neo4j?

1. **Natural Fit** - Knowledge is inherently graph-structured
2. **Relationships** - First-class citizens, not afterthoughts
3. **Flexibility** - Schema-optional for evolving knowledge
4. **Performance** - Optimized for relationship traversal

### Why Factory Pattern for Routes?

1. **Consistency** - Same pattern everywhere (15/15 domains)
2. **Scalability** - Domains can grow without file bloat
3. **Maintainability** - Easy to find and modify functionality
4. **Separation** - API, Intelligence, and UI cleanly separated

---

## 📈 Recent Evolution (October 2025)

### Route Architecture Migration (Complete)

- ✅ **15/15 domains** migrated to Factory Pattern
- ✅ **40 split files** (API + Intelligence + UI)
- ✅ **100% consistency** across all route files
- ✅ **Zero MonsterUI/FastHTML conflicts**
- ✅ **Predictable file structure** everywhere

### Universal Backend Migration (Complete)

- ✅ All domains use Universal Backends
- ✅ Protocol-based interfaces everywhere
- ✅ Generic programming patterns reduce duplication
- ✅ Consistent Neo4j interaction

### Error Handling Migration (Complete)

- ✅ All services return Result[T]
- ✅ All routes use @boundary_handler
- ✅ Consistent error categories (6 total)
- ✅ Rich error context for debugging

---

## 📚 Essential Documentation

### Core Architecture
- **ARCHITECTURE_OVERVIEW.md** (this file) - Complete system architecture
- **[FOURTEEN_DOMAIN_ARCHITECTURE.md](./FOURTEEN_DOMAIN_ARCHITECTURE.md)** - **The 14-domain vision** (DSL, graph, services)
- **[ROUTING_ARCHITECTURE.md](./ROUTING_ARCHITECTURE.md)** - Routes, services, and persistence details
- **[../patterns/three_tier_type_system.md](../patterns/three_tier_type_system.md)** - Type system implementation

### Patterns & Protocols
- **[../patterns/protocol_architecture.md](../patterns/protocol_architecture.md)** - Protocol-based architecture
- **[../patterns/ERROR_HANDLING.md](../patterns/ERROR_HANDLING.md)** - Result[T] pattern

### Domain Documentation
- **[UNIFIED_USER_ARCHITECTURE.md](./UNIFIED_USER_ARCHITECTURE.md)** - User context system
- **[REPORTS_ARCHITECTURE.md](./REPORTS_ARCHITECTURE.md)** - Meta-service aggregation pattern

### Database & Infrastructure
- **[SEARCH_ARCHITECTURE.md](./SEARCH_ARCHITECTURE.md)** - Semantic search

---

## 🚀 Getting Started

1. **Install Dependencies**: `poetry install`
2. **Start Neo4j**: Ensure Neo4j is running locally
3. **Configure Environment**: Set up `.env` with API keys
4. **Run Application**: `poetry run python main.py`
5. **Access UI**: Open browser to `http://localhost:5001`

---

## 🎨 Design Principles Summary

### One Path Forward
- Single, clear way to accomplish tasks
- No backward compatibility burden
- Dead code deleted, not archived

### Knowledge-First Design
- All operations connect to knowledge
- Knowledge enrichment automatic
- Cross-domain intelligence emerges

### Fail-Fast Philosophy
- Components must work properly
- No graceful degradation
- Clear error messages guide fixes

### Clean Code Focus
- Separation of concerns everywhere
- Protocol-based dependency injection
- Immutable domain models
- Consistent patterns

---

## 📊 Architecture Metrics

**Domain Organization (14-Domain + 5 Cross-Cutting Systems)**:
- 6 Activity domains (Tasks, Habits, Goals, Events, Principles, Choices)
- 1 Finance domain (standalone)
- 3 Curriculum domains (KU, LS, LP)
- 2 Content/Processing domains (Assignments, Journals)
- 1 Organizational domain (MOC - KU-based)
- 1 LifePath domain (The Destination)
- 5 Cross-cutting systems (UserContext, Search, Calendar, Askesis, Messaging)

**Code Organization**:
- 14 domains with consistent structure
- Factory pattern for all route files (API + Intelligence + UI)
- 100% protocol-based service layer
- 0 circular dependencies

**Type Safety**:
- Three-tier type system everywhere
- Frozen domain models (immutable)
- Protocol interfaces for all services
- MyPy validation passes

**Error Handling**:
- Result[T] throughout service layer
- @boundary_handler at all route boundaries
- 6 consistent error categories
- Rich debugging context

**DSL Integration**:
- 14-domain activity extraction from journals
- @context() tags for all domains
- Natural language parsing with structured output
- Full graph relationship creation

**Testing**:
- Services test with protocol mocks
- Routes test with service mocks
- Domain models test independently
- No database needed for unit tests

---

## See Also

### Core Architecture Documentation

| Document | Purpose |
|----------|---------|
| [FOURTEEN_DOMAIN_ARCHITECTURE.md](FOURTEEN_DOMAIN_ARCHITECTURE.md) | Complete 14-domain + 5 systems architecture |
| [../patterns/query_architecture.md](../patterns/query_architecture.md) | Database schema, constraints, indexes |
| [UNIFIED_USER_ARCHITECTURE.md](UNIFIED_USER_ARCHITECTURE.md) | UserContext (~240 fields) and ProfileHubData |
| [RELATIONSHIPS_ARCHITECTURE.md](RELATIONSHIPS_ARCHITECTURE.md) | Cross-domain relationship types |

### Key Patterns

- [protocol_architecture.md](../patterns/protocol_architecture.md) - Protocol-based dependency injection
- [query_architecture.md](../patterns/query_architecture.md) - Query builders and patterns
- [three_tier_type_system.md](../patterns/three_tier_type_system.md) - Pydantic/DTO/Domain models
- [ERROR_HANDLING.md](../patterns/ERROR_HANDLING.md) - Result[T] pattern

### Domain Documentation

- [/docs/domains/](../domains/) - Individual domain documentation
- [CURRICULUM_GROUPING_PATTERNS.md](CURRICULUM_GROUPING_PATTERNS.md) - KU/LS/LP patterns + MOC organization

### Quick Reference

- [/docs/INDEX.md](../INDEX.md) - Complete documentation index (123+ documents)
- [CLAUDE.md](/CLAUDE.md) - Project conventions and quick reference

---

*Last Updated: January 20, 2026*
*Architecture: Clean, Protocol-Based, Knowledge-Centric, 14-Domain + 5 Cross-Cutting Systems (4 active + 1 planned)*
*Status: Production-Ready*
*Philosophy: One Path Forward, Knowledge as Fertile Soil, Everything Flows to LifePath*
