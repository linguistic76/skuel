# BaseService Mixins
*Last updated: 2026-01-29*

## Overview

BaseService is composed from **7 focused mixins** following the Single Responsibility Principle (SRP). Each mixin provides a cohesive set of related operations.

```python
class BaseService[B: BackendOperations, T: DomainModelProtocol](
    ConversionHelpersMixin[B, T],
    CrudOperationsMixin[B, T],
    SearchOperationsMixin[B, T],
    RelationshipOperationsMixin[B, T],
    TimeQueryMixin[B, T],
    UserProgressMixin[B, T],
    ContextOperationsMixin[B, T],
):
    """Unified base service for 6 of 14 SKUEL domains."""
```

---

## Mixin Dependency Graph

```
Foundation Layer (No Dependencies):
├── ConversionHelpersMixin    # DTO ↔ Domain conversion
└── CrudOperationsMixin        # CRUD + ownership verification
        │
        ├─────────────────────────────────────┐
        │                                     │
        ▼                                     ▼
Service Layer (Depends on Foundation):
├── SearchOperationsMixin      ← ConversionHelpersMixin (_to_domain_models)
├── RelationshipOperationsMixin ← ConversionHelpersMixin (_records_to_domain_models)
├── TimeQueryMixin             ← ConversionHelpersMixin (_to_domain_models)
├── UserProgressMixin          ← ConversionHelpersMixin (_records_to_domain_models)
└── ContextOperationsMixin     ← CrudOperationsMixin (get)
```

**Key Insight:** ConversionHelpersMixin and CrudOperationsMixin are **foundational** - they have no dependencies and are used by all other mixins.

---

## Mixin Catalog

### 1. ConversionHelpersMixin
**Responsibility:** DTO ↔ Domain model conversion and result handling

**Dependencies:** None (foundational)

**Key Methods:**
- `_to_domain_model(dto)` - Single DTO → Domain model
- `_to_domain_models(dtos)` - Bulk DTO → Domain models
- `_from_domain_model(model)` - Domain model → DTO
- `_records_to_domain_models(records)` - Neo4j records → Domain models
- `_ensure_exists(result)` - Convert `Result[T | None]` → `Result[T]`

**Used By:** SearchOperationsMixin, RelationshipOperationsMixin, TimeQueryMixin, UserProgressMixin

**File:** `conversion_helpers_mixin.py`

---

### 2. CrudOperationsMixin
**Responsibility:** Core CRUD operations + ownership-verified CRUD

**Dependencies:** None (foundational)

**Key Methods:**

*Core CRUD:*
- `create(entity)` - Create new entity
- `get(uid)` - Get entity by UID
- `update(uid, updates)` - Update entity
- `delete(uid, cascade)` - Delete entity
- `list(filters, limit, offset)` - List with pagination

*Ownership-Verified CRUD (Multi-Tenant Security):*
- `verify_ownership(uid, user_uid)` - Verify entity ownership
- `get_for_user(uid, user_uid)` - Get only if owned
- `update_for_user(uid, user_uid, updates)` - Update only if owned
- `delete_for_user(uid, user_uid)` - Delete only if owned

**Used By:** ContextOperationsMixin

**File:** `crud_operations_mixin.py`

---

### 3. SearchOperationsMixin
**Responsibility:** Text search, graph search, and filtering

**Dependencies:** ConversionHelpersMixin (`_to_domain_models`)

**Key Methods:**

*Text Search:*
- `search(query, limit, user_uid)` - Full-text search across configured fields
- `search_by_tags(tags, user_uid)` - Filter by tag array
- `search_array_field(field, values)` - Generic array field search

*Graph Search:*
- `get_by_relationship(rel_type, target_uid)` - Get entities via relationship
- `search_connected_to(target_uid, rel_type)` - Search + graph traversal
- `graph_aware_faceted_search(filters, include_context)` - Unified faceted search

*Filtering:*
- `get_by_status(status, user_uid)` - Filter by status
- `get_by_category(category, user_uid)` - Filter by category
- `list_user_categories(user_uid)` - List unique categories for user
- `count(filters)` - Count matching entities

**File:** `search_operations_mixin.py`

---

### 4. RelationshipOperationsMixin
**Responsibility:** Graph relationship management and prerequisite traversal

**Dependencies:** ConversionHelpersMixin (`_records_to_domain_models`)

**Key Methods:**

*Core Relationships:*
- `add_relationship(from_uid, rel_type, to_uid, properties)` - Create edge
- `get_relationships(uid, rel_type, direction)` - Get all relationships
- `traverse(start_uid, rel_patterns, depth)` - Graph traversal

*Prerequisite Operations:*
- `get_prerequisites(uid)` - Get prerequisite entities (configured via DomainConfig)
- `get_enables(uid)` - Get entities this enables (inverse of prerequisites)
- `add_prerequisite(uid, prerequisite_uid)` - Add prerequisite relationship
- `get_hierarchy(uid, depth)` - Get hierarchical structure

**File:** `relationship_operations_mixin.py`

---

### 5. TimeQueryMixin
**Responsibility:** Date-based queries for calendar and scheduling

**Dependencies:** ConversionHelpersMixin (`_to_domain_models`)

**Key Methods:**
- `get_user_items_in_range(user_uid, start_date, end_date)` - Date range query
- `get_due_soon(user_uid, days)` - Items due within N days
- `get_overdue(user_uid)` - Items past due date

**Configuration:**
- Uses `DomainConfig.date_field` to determine which date field to query
- Uses `DomainConfig.completed_statuses` to exclude completed items

**File:** `time_query_mixin.py`

---

### 6. UserProgressMixin
**Responsibility:** User progress and mastery tracking

**Dependencies:** ConversionHelpersMixin (`_records_to_domain_models`)

**Key Methods:**
- `get_user_progress(user_uid, entity_uid)` - Get progress/mastery stats
- `update_user_mastery(uid, user_uid, mastery_level)` - Update mastery (0.0-1.0)
- `get_user_curriculum(user_uid)` - Get entities user is studying/has mastered

**Configuration:**
- Only active when `DomainConfig.supports_user_progress = True`
- Originally for Curriculum domains (KU, LS, LP), now available to any domain

**File:** `user_progress_mixin.py`

---

### 7. ContextOperationsMixin
**Responsibility:** Graph context retrieval and enrichment

**Dependencies:** CrudOperationsMixin (`get`)

**Key Methods:**
- `get_with_content(uid)` - Get entity with full content loaded
- `get_with_context(uid, depth)` - Get entity with graph neighborhood
- `_basic_get_with_context(uid, depth)` - Fallback for entities not in registry

**Use Cases:**
- Intelligence services need entities with related context
- Routes returning rich entity views
- Dashboard components showing entity + connections

**File:** `context_operations_mixin.py`

---

## Composition Pattern

### How Mixins Work Together

```python
# Example: search() method flow
async def search(query: str) -> Result[list[Task]]:
    # 1. SearchOperationsMixin.search()
    result = await self.backend.search(query, limit)

    # 2. Uses ConversionHelpersMixin._to_domain_models()
    entities = self._to_domain_models(result.value, TaskDTO, Task)

    # 3. Returns domain models
    return Result.ok(entities)
```

**Key Insight:** Mixins access each other's methods via `self.*` - Python's MRO (Method Resolution Order) ensures the right method is called.

---

## Configuration via DomainConfig

Mixins read configuration from `DomainConfig` via BaseService properties.

**Class-Level Configuration (January 2026):**
`_config` is a **class-level constant** (`ClassVar`) shared by all instances:

```python
class TasksSearchService(BaseService[TasksOperations, Task]):
    _config: ClassVar[DomainConfig] = create_activity_domain_config(
        dto_class=TaskDTO,
        model_class=Task,
        domain_name="tasks",
        date_field="due_date",  # Used by TimeQueryMixin
        completed_statuses=(KuStatus.COMPLETED.value,),  # Used by TimeQueryMixin
        search_fields=("title", "description"),  # Used by SearchOperationsMixin
        prerequisite_relationships=(...),  # Used by RelationshipOperationsMixin
        supports_user_progress=True,  # Used by UserProgressMixin
    )

# Access via classmethod (explicit)
config = TasksSearchService._get_config_cls()

# Or via instance properties (reads class-level config internally)
service = TasksSearchService(backend=backend)
search_fields = service.search_fields  # Reads from cls._config
```

**Key Design:** All instances of a service class share the **same immutable `_config` object**. Configuration is defined once at class definition time and never changes per instance.

**Configuration fields used by each mixin:**

| Mixin | DomainConfig Fields |
|-------|---------------------|
| ConversionHelpersMixin | `dto_class`, `model_class` |
| CrudOperationsMixin | (none - uses validation hooks) |
| SearchOperationsMixin | `search_fields`, `search_order_by`, `category_field`, `graph_enrichment_patterns`, `user_ownership_relationship` |
| RelationshipOperationsMixin | `prerequisite_relationships`, `enables_relationships` |
| TimeQueryMixin | `date_field`, `completed_statuses` |
| UserProgressMixin | `supports_user_progress`, `mastery_threshold` |
| ContextOperationsMixin | `content_field`, `prerequisite_relationships` |

---

## Testing Mixins

### Unit Testing Individual Mixins

Each mixin can be tested in isolation by creating a minimal mock BaseService:

```python
from core.services.mixins import SearchOperationsMixin

class MockService(SearchOperationsMixin):
    """Minimal service for testing SearchOperationsMixin."""

    def __init__(self, backend):
        self.backend = backend
        self.logger = get_logger("test")
        self.entity_label = "TestEntity"
        self._dto_class = TestDTO
        self._model_class = TestModel
        self._search_fields = ["title", "description"]

    def _to_domain_models(self, dtos, dto_class, model_class):
        # Provide required dependency from ConversionHelpersMixin
        return [model_class(**dto.dict()) for dto in dtos]

# Test
async def test_search():
    mock_backend = Mock(spec=BackendOperations)
    service = MockService(mock_backend)

    result = await service.search("test query")
    assert result.is_ok
```

### Integration Testing via BaseService

For integration tests, use actual BaseService instances:

```python
from core.services.tasks import TasksSearchService

async def test_tasks_search_integration():
    backend = UniversalNeo4jBackend[Task](driver, "Task", Task)
    service = TasksSearchService(backend=backend)

    # All 7 mixins available
    result = await service.search("urgent tasks")
    assert result.is_ok
```

---

## Creating New Mixins

### Guidelines

1. **Single Responsibility:** Each mixin should have ONE cohesive purpose
2. **Minimal Dependencies:** Prefer depending on foundational mixins only
3. **Document Dependencies:** Use REQUIRES/PROVIDES sections in docstring
4. **Type Parameters:** All mixins use `[B: BackendOperations, T: DomainModelProtocol]`
5. **Configuration:** Access config via `self._get_config_value()` or properties

### Template

```python
"""
MyFeature Mixin
===============

Brief description of what this mixin provides.

REQUIRES (Mixin Dependencies):
    - ConversionHelpersMixin: Uses _to_domain_models() for result conversion
    - CrudOperationsMixin: Uses get() for entity retrieval

PROVIDES (Methods for Routes/Services):
    - method_one: Description
    - method_two: Description

Methods:
    - method_one: Description
    - method_two: Description
"""

from __future__ import annotations
from typing import TYPE_CHECKING
from core.models.protocols import DomainModelProtocol
from core.ports import BackendOperations

if TYPE_CHECKING:
    from logging import Logger

class MyFeatureMixin[B: BackendOperations, T: DomainModelProtocol]:
    """
    Mixin providing my feature operations.

    Required attributes from composing class:
        backend: B - Backend implementation
        logger: Logger - For logging
        _to_domain_models: Conversion method (from ConversionHelpersMixin)
        get: Get method (from CrudOperationsMixin)
    """

    # Type hints for required attributes
    backend: B
    logger: Logger

    # Declare dependencies
    def _to_domain_models(self, dtos, dto_class, model_class):
        """Provided by ConversionHelpersMixin."""
        raise NotImplementedError

    async def get(self, uid: str):
        """Provided by CrudOperationsMixin."""
        raise NotImplementedError

    # Implement methods
    async def my_method(self, arg: str) -> Result[T]:
        """Method implementation."""
        ...
```

---

## Migration History

### January 2026: Mixin Decomposition
- **Before:** Monolithic 625-line `base_service.py`
- **After:** 7 focused mixins averaging ~150 lines each
- **Rationale:** Single Responsibility Principle, improved testability

### Key Design Decisions

1. **Why ConversionHelpersMixin is foundational:**
   - Every mixin needs to convert backend data → domain models
   - Making it foundational avoids circular dependencies

2. **Why CrudOperationsMixin is separate:**
   - Not all mixins need CRUD (e.g., RelationshipOperationsMixin)
   - CRUD is core but not universal

3. **Why mixins use `self.*` instead of explicit composition:**
   - Python MRO handles method resolution automatically
   - Cleaner syntax: `self.get()` vs `self.crud.get()`
   - Type inference works better with inheritance

---

## Related Documentation

- **Implementation:** `/core/services/base_service.py`
- **Protocols:** `/core/ports/base_service_interface.py`
- **Configuration:** `/core/services/domain_config.py`
- **Quick Start:** `/docs/guides/BASESERVICE_QUICK_START.md`
- **Method Index:** `/docs/reference/BASESERVICE_METHOD_INDEX.md`
- **Architecture Review:** `/docs/architecture/BASESERVICE_ARCHITECTURE_REVIEW.md`

---

## Summary

**7 Mixins = 45+ Methods**

Each mixin provides 5-10 focused methods for a specific concern:
- Foundation: Conversion + CRUD (16 methods)
- Search: Text + Graph + Filtering (14 methods)
- Relationships: Graph operations + Prerequisites (8 methods)
- Time: Calendar queries (4 methods)
- Progress: Mastery tracking (3 methods)
- Context: Graph enrichment (3 methods)

**Total: ~48 methods** available to any BaseService subclass via clean composition.
