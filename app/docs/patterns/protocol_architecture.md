---
title: Protocol-Based Architecture
created: 2026-01-03
updated: 2026-01-07
status: active
audience: developers
tags: [patterns, protocols, architecture]
related: [ADR-017-relationship-service-unification.md, ADR-023-curriculum-baseservice-migration.md]
---

# Protocol-Based Architecture

**Last Updated**: January 6, 2026

## Overview

SKUEL uses Python's Protocol typing (PEP 544) for dependency injection without framework overhead. This provides type safety, testability, and clean architecture while maintaining the "one path forward" philosophy.

**Core Achievements**:
- **100% hasattr elimination** - All attribute checks now use Protocol-based type checking
- **Zero port dependencies** - All services use `core/services/protocols/*` exclusively
- **75% code reduction** through generic programming patterns
- **21 services** using protocol interfaces exclusively

## What Are Protocols?

Protocols are Python's way of defining structural subtyping (duck typing with type hints). They define interfaces that classes can satisfy without explicit inheritance.

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class Flyable(Protocol):
    def fly(self) -> None: ...

# Any class with a fly() method satisfies Flyable
class Bird:
    def fly(self) -> None:
        print("Flying!")

# Bird satisfies Flyable without inheriting from it
def make_it_fly(thing: Flyable) -> None:
    thing.fly()

make_it_fly(Bird())  # Works!
```

## Protocol Architecture in SKUEL

### Directory Structure

```
core/
├── protocols.py                      # Core type-checking protocols
└── services/
    └── protocols/
        ├── domain_protocols.py       # Business domain operations
        ├── knowledge_protocols.py    # Knowledge management
        ├── search_protocols.py       # Search & query operations
        └── infrastructure_protocols.py # System & infrastructure
```

### Protocol Categories

| Category | File | Purpose |
|----------|------|---------|
| **Type Checking** | `core/protocols.py` | Attribute checking (replaces hasattr) |
| **Domain Operations** | `domain_protocols.py` | Business logic interfaces (TasksOperations, GoalsOperations) |
| **Curriculum (3)** | `curriculum_protocols.py` | KU, LS, LP operations (unified hierarchy) |
| **Content/Org** | `curriculum_protocols.py` | MOC operations (navigation across curriculum) |
| **Search** | `search_protocols.py` | Search and query operations |
| **Infrastructure** | `infrastructure_protocols.py` | EventBus, caching, etc. |
| **Legacy (deprecated)** | `ku_protocols.py` | Being phased out - use curriculum_protocols.py |

### Protocol Cleanup (January 2026)

Following "One Path Forward", unused and dead protocols have been removed:

**Deleted from `ku_protocols.py`:**
- `LearningOperations` - Dead code (type hint was wrong, never implemented)
- `LearningQueryOperations` - Unused legacy protocol
- `ContentOperations` - Aspirational (never properly implemented)
- `ContentQueryOperations` - Unused legacy protocol

**Deleted from `domain_protocols.py`:**
- `HasModelDump`, `HasDict` (duplicate), `HasValue`, `HasStatus`
- `HasInsights`, `HasTimestamps`, `HasCreatedBy` (7 orphaned protocols)

**Migration Path:**
- Use `LpOperations` from `curriculum_protocols.py` instead of `LearningPathsOperations`
- Use `KuOperations` from `curriculum_protocols.py` instead of `KuOperationsLegacy`
- Use duck typing or `Any` for services without proper protocol alignment

### Architecture Pattern

```
Core Domain (Business Logic)
    ↓ depends on
Protocols (in core/services/protocols/)
    ↑ implemented by
Adapters (in adapters/)
```

**Key Insight**: Protocols ARE your ports - they provide the same contract/interface capability as traditional ports, but with better type checking and less boilerplate.

## Best Practices

### 1. Use @runtime_checkable

```python
@runtime_checkable  # Allows isinstance() checks
class HasMetrics(Protocol):
    metrics: Any
```

### 2. Prefer Specific Protocols Over hasattr

```python
# ✅ Good - Specific protocol
if isinstance(obj, HasCreatedAt):
    use(obj.created_at)

# ❌ Bad - Generic hasattr
if hasattr(obj, 'created_at'):
    use(obj.created_at)
```

### 3. No Lambdas

```python
# ❌ Bad - Lambda function
TaskPure.get_color = lambda self: self.color if isinstance(self, HasColor) else None

# ✅ Good - Named function
def _get_color(self):
    """Get task color if available."""
    if isinstance(self, HasColor):
        return self.color
    return None

TaskPure.get_color = _get_color
```

### 4. Duck Typing for Backends

```python
# ✅ Good - Backend satisfies protocol through methods
class MyBackend:
    async def create_journal(self, journal): ...
    # Automatically satisfies JournalOperations

# ❌ Bad - Explicit inheritance (not needed)
class MyBackend(JournalOperations):
    async def create_journal(self, journal): ...
```

### 5. Use Protocols to Break Circular Dependencies

```python
# ❌ Bad - Circular dependency
from core.services.user_context_service import UserContextService

class TasksService:
    def __init__(self, context_service: UserContextService):
        self.context_service = context_service
        # Now TasksService → UserContextService → TasksService ❌

# ✅ Good - Protocol breaks the cycle
from core.services.protocols import UserContextOperations

class TasksService:
    def __init__(
        self,
        backend: TasksOperations,
        context_service: Optional[UserContextOperations] = None
    ):
        self.context_service = context_service
        # Now TasksService → Protocol (no circular dependency) ✅

# Implementation can be provided later during bootstrap
# No import cycle because protocol is just an interface
```

**Pattern for Breaking Circular Dependencies:**
1. Identify the circular dependency (Service A → Service B → Service A)
2. Create a minimal protocol interface for the needed operations
3. Have Service A depend on the protocol, not the concrete Service B
4. Wire up the concrete implementation during bootstrap
5. Use `Optional[Protocol]` to allow None during initialization

## Benefits Summary

### Type Safety
- **Compile-time checking** with MyPy
- **IDE autocomplete** and refactoring support
- **No runtime AttributeErrors**
- **Clear contracts** between components

### Code Quality
- **100% hasattr elimination** - All checks now type-safe
- **Zero port dependencies** - Clean protocol-based architecture
- **No lambdas** - Proper named methods throughout
- **75% code reduction** through generic patterns

### Testability
- **Mock protocols**, not implementations
- **No database required** for unit tests
- **Fast test execution**
- **Reusable test patterns**

### Maintainability
- **No circular dependencies**
- **Clear separation of concerns**
- **Duck typing** - Implementations satisfy protocols automatically
- **One path forward** - No alternatives, no confusion

## See Also

- [BACKEND_OPERATIONS_ISP.md](BACKEND_OPERATIONS_ISP.md) - BackendOperations protocol hierarchy (ISP-compliant design)
- [PROTOCOL_REFERENCE.md](../reference/PROTOCOL_REFERENCE.md) - Complete protocol catalog
- [PORTS_TO_PROTOCOLS_MIGRATION.md](../migrations/PORTS_TO_PROTOCOLS_MIGRATION.md) - Migration history and lessons learned
- [PROTOCOL_IMPLEMENTATION_GUIDE.md](../guides/PROTOCOL_IMPLEMENTATION_GUIDE.md) - How to implement and use protocols

---

**Status:** Active - Core pattern for all dependency injection in SKUEL
