# BaseService Method Index

**Purpose:** Complete reference of all methods available in BaseService and Activity Domain facades.

**Last Updated:** 2026-03-04 (Auto-generated)

**WARNING:** This file is AUTO-GENERATED. Do not edit manually.
**To update:** Run `python scripts/generate_method_index.py`

---

## Table of Contents

- [BaseService Mixin Methods](#baseservice-mixin-methods) - Methods from 7 mixins
- [Activity Domain Facades](#activity-domain-facades) - Facade delegations
- [Common Patterns](#common-patterns) - Usage examples

---

## BaseService Mixin Methods

These methods are available on **all services that extend BaseService**.

### ConversionHelpersMixin

**Purpose:** DTO ↔ Domain model conversion and result handling

| Method | Public |
|--------|--------|
| `__init__()` | 🔒 (internal) |

---

### CrudOperationsMixin

**Purpose:** CRUD operations with ownership verification

| Method | Public |
|--------|--------|
| `__init__()` | 🔒 (internal) |
| `create()` | ✅ |
| `delete()` | ✅ |
| `delete_for_user()` | ✅ |
| `get()` | ✅ |
| `get_for_user()` | ✅ |
| `list()` | ✅ |
| `update()` | ✅ |
| `update_for_user()` | ✅ |
| `verify_ownership()` | ✅ |

---

### SearchOperationsMixin

**Purpose:** Text search, filtering, and graph-aware queries

| Method | Public |
|--------|--------|
| `__init__()` | 🔒 (internal) |
| `count()` | ✅ |
| `get_by_category()` | ✅ |
| `get_by_domain()` | ✅ |
| `get_by_relationship()` | ✅ |
| `get_by_status()` | ✅ |
| `graph_aware_faceted_search()` | ✅ |
| `list_all_categories()` | ✅ |
| `list_user_categories()` | ✅ |
| `search()` | ✅ |
| `search_array_field()` | ✅ |
| `search_by_tags()` | ✅ |
| `search_connected_to()` | ✅ |

---

### RelationshipOperationsMixin

**Purpose:** Graph relationship operations and traversal

| Method | Public |
|--------|--------|
| `__init__()` | 🔒 (internal) |
| `add_prerequisite()` | ✅ |
| `add_relationship()` | ✅ |
| `get_enables()` | ✅ |
| `get_hierarchy()` | ✅ |
| `get_prerequisites()` | ✅ |
| `get_relationships()` | ✅ |
| `traverse()` | ✅ |

---

### TimeQueryMixin

**Purpose:** Calendar and scheduling queries

**Config fields:** `temporal_exclude_statuses` (default: 4 terminal statuses), `temporal_secondary_sort` (optional secondary ORDER BY)

| Method | Public |
|--------|--------|
| `__init__()` | 🔒 (internal) |
| `get_due_soon()` | ✅ |
| `get_overdue()` | ✅ |
| `get_user_items_in_range()` | ✅ |
| `get_user_items_in_range_base()` | ✅ |

---

### UserProgressMixin

**Purpose:** Progress and mastery tracking

| Method | Public |
|--------|--------|
| `__init__()` | 🔒 (internal) |
| `get_user_curriculum()` | ✅ |
| `get_user_progress()` | ✅ |
| `update_user_mastery()` | ✅ |

---

### ContextOperationsMixin

**Purpose:** Retrieve entities with enriched graph context

| Method | Public |
|--------|--------|
| `__init__()` | 🔒 (internal) |
| `get()` | ✅ |
| `get_with_content()` | ✅ |
| `get_with_context()` | ✅ |

---

## Activity Domain Facades

Auto-generated delegation methods for each Activity Domain facade.

### TasksService

**Total Delegated Methods:** 0

---

### GoalsService

**Total Delegated Methods:** 0

---

### HabitsService

**Total Delegated Methods:** 0

---

### EventsService

**Total Delegated Methods:** 0

---

### ChoicesService

**Total Delegated Methods:** 0

---

### PrinciplesService

**Total Delegated Methods:** 0

---

## Common Patterns

### Facade Usage (Production)

```python
from core.services.tasks_service import TasksService

# Auto-delegation to sub-services
result = await tasks_service.create_task(request, user_uid)
```

### Direct Sub-Service Usage (Testing)

```python
from core.services.tasks import TasksCoreService

core = TasksCoreService(backend=mock_backend)
result = await core.create_task(request, user_uid)
```

---

## See Also

- [Sub-Service Catalog](/docs/reference/SUB_SERVICE_CATALOG.md) - Which service does what
- [Quick Start Guide](/docs/guides/BASESERVICE_QUICK_START.md) - Usage patterns
- [Service Topology](/docs/architecture/SERVICE_TOPOLOGY.md) - Architecture diagrams
- [BaseService Source](/core/services/base_service.py) - Implementation
