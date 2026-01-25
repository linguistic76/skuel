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
from core.services.relationships import get_config_for_domain, ACTIVITY_DOMAIN_CONFIGS
from core.models.shared_enums import Domain

# Get config for a domain
config = get_config_for_domain(Domain.TASKS)  # Returns TASK_CONFIG
```

### Service Location Pattern

```
core/services/{domain}/
├── {domain}_core_service.py      # Core CRUD operations
├── {domain}_search_service.py    # Search operations
└── {domain}_service.py           # Facade (combines core + search)
```

### Facade Delegation Pattern (January 2026)

Activity Domain facades use `FacadeDelegationMixin` with **signature preservation**:

```python
from core.services.mixins import FacadeDelegationMixin, merge_delegations

class TasksService(FacadeDelegationMixin, BaseService[TasksOperations, Task]):
    # Class-level type annotations enable signature preservation
    core: TasksCoreService
    search: TasksSearchService
    intelligence: TasksIntelligenceService

    _delegations = merge_delegations(
        {"get_task": ("core", "get_task"), ...},
        {"search": ("search", "search"), ...},
    )
```

**Key features:**
- **Signature preservation**: `inspect.signature()` on facade methods returns actual parameter names (not `*args, **kwargs`)
- **Class-level annotations**: Required for the mixin to resolve method signatures at class definition time
- **Underscore prefix convention**: `_filters` means "placeholder for future implementation" (not "unused")

**See:** `/core/services/mixins/facade_delegation_mixin.py`

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
class LpService(FacadeDelegationMixin):
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
- [Domain Configs](../../core/services/relationships/domain_configs.py)
