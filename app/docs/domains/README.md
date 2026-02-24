---
title: Domain Documentation
created: 2025-12-04
updated: 2026-01-20
status: current
category: domains
tags: [domains, reference, architecture]
---

# Domain Documentation

This folder contains documentation for each of SKUEL's 14 domains.

## Domain Categories

### Activity Domains (6)
User-facing entities with shared patterns via `UnifiedRelationshipService`:

| Domain | File | UID Prefix | Key Purpose |
|--------|------|------------|-------------|
| [Tasks](tasks.md) | `task:` | Work items with dependencies and deadlines |
| [Goals](goals.md) | `goal:` | Objectives with milestones and progress |
| [Habits](habits.md) | `habit:` | Recurring behaviors with streak tracking |
| [Events](events.md) | `event:` | Calendar items with scheduling |
| [Choices](choices.md) | `choice:` | Decisions with outcome tracking |
| [Principles](principles.md) | `principle:` | Values that guide goals and choices |

### Finance Domain (1)
Standalone expense/budget tracker (NOT an Activity Domain):

| Domain | File | UID Prefix | Key Purpose |
|--------|------|------------|-------------|
| [Finance](finance.md) | `expense:` | Expense and budget tracking |

### Curriculum Domains (3)
Three knowledge organization patterns:

| Domain | File | UID Prefix | Topology | Key Purpose |
|--------|------|------------|----------|-------------|
| [KU](ku.md) | `ku:` | Point | Atomic knowledge content |
| [LS](ls.md) | `ls:` | Edge | Sequential learning steps |
| [LP](lp.md) | `lp:` | Path | Complete learning sequences |

### Content/Processing Domains (2)
Content processing and file handling:

| Domain | File | UID Prefix | Key Purpose |
|--------|------|------------|-------------|
| [Journals](journals.md) | `journal:` | Two-tier system: Voice (ephemeral) + Curated (permanent) |
| [Assignments](assignments.md) | `assignment:` | User-facing assignment interface |

### Organizational Domain (1)
KU-based knowledge organization:

| Domain | File | UID Prefix | Key Purpose |
|--------|------|------------|-------------|
| [MOC](moc.md) | `ku:` | KU-based non-linear navigation (graph topology via ORGANIZES) |

**MOC Architecture (January 2026):** MOC is NOT a separate entity - it IS a KU with ORGANIZES relationships. A KU "is" a MOC when it has outgoing ORGANIZES relationships (emergent identity).

**Journals Two-Tier System (December 2025):**
- **PJ1 (Voice)**: Audio journals, max 3 stored, FIFO auto-cleanup (`JOURNAL_VOICE`)
- **PJ2 (Curated)**: Text/markdown journals, permanent storage (`JOURNAL_CURATED`)

### The Destination (1)
The ultimate goal all domains flow toward:

| Domain | File | Key Purpose |
|--------|------|-------------|
| [LifePath](lifepath.md) | "Am I living my life path?" |

## Quick Reference

### Domain → Config Mapping

```python
from core.models.relationship_registry import DOMAIN_CONFIGS, TASKS_CONFIG
from core.models.enums import Domain

# Get config for a domain
config = DOMAIN_CONFIGS[Domain.TASKS]  # or use TASKS_CONFIG directly
```

### Service Location Pattern

```
core/services/{domain}/
├── {domain}_core_service.py      # Core CRUD operations
├── {domain}_search_service.py    # Search operations
└── {domain}_service.py           # Facade (combines core + search)
```

### Facade Delegation Pattern (February 2026)

Activity Domain facades use explicit `async def` delegation methods — MyPy-native, no mixin needed:

```python
from typing import Any

class TasksService(BaseService[TasksOperations, Task]):
    core: TasksCoreService
    search: TasksSearchService
    intelligence: TasksIntelligenceService

    # Explicit delegation — each method is a real async def
    async def get_task(self, *args: Any, **kwargs: Any) -> Any:
        return await self.core.get_task(*args, **kwargs)

    async def search_tasks(self, *args: Any, **kwargs: Any) -> Any:
        return await self.search.search(*args, **kwargs)
```

**Key features:**
- **MyPy-native**: All methods are real `async def` — no workaround needed
- **Underscore prefix convention**: `_filters` means "placeholder for future implementation" (not "unused")
- **One file**: The service class is the single source of truth

**Note:** `FacadeDelegationMixin` and `facade_protocols.py` are deleted (February 2026).

### Intelligence Service Pattern (January 2026 - ADR-031)

Domain intelligence services follow the **unified internal creation pattern**:

| Domain Type | Domains | Intelligence Pattern |
|-------------|---------|---------------------|
| **Activity (6)** | Tasks, Goals, Habits, Events, Choices, Principles | Created internally by facade |
| **Curriculum (3)** | KU, LS, LP | Created internally by facade |
| **Organizational (1)** | MOC | No intelligence (KU-based, uses KU intelligence) |

**Unified Pattern:**
- All facades create their intelligence service internally (not passed in from bootstrap)
- All extend `BaseAnalyticsService[BackendOperations[T], T]`
- No external intelligence creation in `services_bootstrap.py`

```python
# Example: LpService creates intelligence internally
class LpService(BaseService[LpOperations, LearningPath]):
    def __init__(self, driver, ls_service, graph_intelligence_service, ...):
        # Step 5: Create intelligence INTERNALLY (January 2026 - Unified Pattern)
        self.intelligence = LpIntelligenceService(
            backend=lp_backend,
            graph_intelligence_service=graph_intelligence_service,
            ...
        )
```

**See:** `/docs/intelligence/INTELLIGENCE_SERVICES_INDEX.md`

## See Also

- [14-Domain Architecture](../architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md)
- [UnifiedRelationshipService](../patterns/UNIFIED_RELATIONSHIP_SERVICE.md)
- [Relationship Registry](../../core/models/relationship_registry.py)
