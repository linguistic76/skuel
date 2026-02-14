---
title: Configuration-Driven Service Architecture
updated: 2026-01-29
category: patterns
related_skills:
- base-analytics-service
related_docs:
- /docs/decisions/ADR-023-curriculum-baseservice-migration.md
- /docs/decisions/ADR-025-service-consolidation-patterns.md
- /docs/patterns/DOMAINCONFIG_MIGRATION_COMPLETE.md
---

# Configuration-Driven Service Architecture

How SKUEL services use DomainConfig for unified, type-safe configuration.

**Decision context:** See [ADR-023](/docs/decisions/ADR-023-curriculum-baseservice-migration.md) for the unification decision.

**Migration Status:** ✅ **100% Complete** (January 2026) - All services migrated to DomainConfig.

---
## Related Skills

For implementation guidance, see:
- [@base-analytics-service](../../.claude/skills/base-analytics-service/SKILL.md)


## Core Principle

**Configuration over inheritance** - Services opt-in to features via DomainConfig, not by inheriting from specialized base classes.

### Evolution: From Two Base Classes → Class Attributes → DomainConfig

**Phase 1 (Before 2025):** Two separate base classes
```python
# Activity domains used BaseService
class TasksSearchService(BaseService[TasksOperations, Task]): ...

# Curriculum domains used CurriculumBaseService (819 lines of separate code)
class LsSearchService(CurriculumBaseService[LsOperations, Ls]): ...
```

**Phase 2 (2025):** Unified BaseService with class attributes
```python
# ALL domains use BaseService with class attributes
class TasksSearchService(BaseService[TasksOperations, Task]):
    _dto_class = TaskDTO
    _model_class = Task
    _supports_user_progress = True
    # ... 15 more scattered attributes
```

**Phase 3 (January 2026):** DomainConfig - THE path
```python
from core.services.domain_config import create_activity_domain_config

# ALL domains use BaseService with DomainConfig
class TasksSearchService(BaseService[TasksOperations, Task]):
    _config = create_activity_domain_config(
        dto_class=TaskDTO,
        model_class=Task,
        domain_name="tasks",
        date_field="due_date",
        completed_statuses=(KuStatus.COMPLETED.value,),
    )
```

---

## DomainConfig Architecture

### Factory Functions (One Path Forward)

| Factory | Use For | Key Settings |
|---------|---------|--------------|
| `create_activity_domain_config()` | Tasks, Goals, Habits, Events, Choices, Principles | `user_ownership_relationship="OWNS"` |
| `create_curriculum_domain_config()` | KU, LS, LP, MOC | `user_ownership_relationship=None` (shared) |

### Activity Domain Configuration

```python
from core.services.domain_config import create_activity_domain_config

class TasksSearchService(BaseService[TasksOperations, Task]):
    _config = create_activity_domain_config(
        dto_class=TaskDTO,                 # Required: DTO class
        model_class=Task,                  # Required: Domain model class
        domain_name="tasks",               # Required: Logger name
        date_field="due_date",             # Optional: Default "created_at"
        completed_statuses=(KuStatus.COMPLETED.value,),
        category_field="category",         # Optional: Default "category"
        search_fields=("title", "description"),  # Optional
        search_order_by="created_at",      # Optional
    )
```

### Curriculum Domain Configuration

```python
from core.services.domain_config import create_curriculum_domain_config

class LsSearchService(BaseService[BackendOperations[Ls], Ls]):
    _config = create_curriculum_domain_config(
        dto_class=LsDTO,
        model_class=Ls,
        domain_name="ls",
        search_fields=("title", "description", "content"),
        category_field="domain",           # Curriculum uses "domain"
        # user_ownership_relationship=None automatically set (shared content)
    )
```

### Curriculum Features (Opt-In)

```python
    # Enable mastery/progress tracking (default: False)
    _supports_user_progress: bool = True

    # Content field for full-text (default: "content")
    _content_field: str = "description"

    # Mastery threshold (default: 0.7)
    _mastery_threshold: float = 0.7

    # Prerequisite relationship types (default: [])
    _prerequisite_relationships: ClassVar[list[str]] = [
        "REQUIRES_STEP",
        "REQUIRES_KNOWLEDGE",
    ]

    # Enables relationship types (default: [])
    _enables_relationships: ClassVar[list[str]] = [
        "ENABLES_STEP",
        "ENABLES_LEARNING",
    ]
```

### Graph Enrichment Configuration

```python
    # Graph enrichment patterns for faceted search
    _graph_enrichment_patterns: ClassVar[list[tuple[str, str, str, str]]] = [
        # (relationship_type, target_label, context_field, direction)
        ("CONTAINS_KNOWLEDGE", "Ku", "knowledge_units", "outgoing"),
        ("HAS_STEP", "Lp", "learning_paths", "incoming"),
    ]
```

---

## Complete Example: Curriculum Search Service

```python
from core.services.base_service import BaseService
from core.models.ls.ls import Ls
from core.models.ls.ls_dto import LearningStepDTO

class LsSearchService(BaseService["BackendOperations[Ls]", Ls]):
    """Learning Step search service - uses BaseService with curriculum configuration."""

    # Required
    _dto_class = LearningStepDTO
    _model_class = Ls

    # Search
    _search_fields: ClassVar[list[str]] = ["title", "intent", "description"]
    _search_order_by: str = "updated_at"

    # Ownership (None = shared curriculum content)
    _user_ownership_relationship: ClassVar[str | None] = None

    # Curriculum features (opt-in)
    _supports_user_progress: bool = True
    _content_field: str = "description"
    _mastery_threshold: float = 0.7
    _prerequisite_relationships: ClassVar[list[str]] = ["REQUIRES_STEP", "REQUIRES_KNOWLEDGE"]
    _enables_relationships: ClassVar[list[str]] = ["ENABLES_STEP", "ENABLES_LEARNING"]

    # Graph enrichment
    _graph_enrichment_patterns: ClassVar[list[tuple[str, str, str, str]]] = [
        ("CONTAINS_KNOWLEDGE", "Ku", "knowledge_units", "outgoing"),
        ("HAS_STEP", "Lp", "learning_paths", "incoming"),
        ("REQUIRES_STEP", "Ls", "prerequisites", "outgoing"),
    ]
```

---

## Complete Example: Activity Search Service

```python
from core.services.base_service import BaseService
from core.services.domain_config import create_activity_domain_config
from core.models.task.task import Task
from core.models.task.task_dto import TaskDTO

class TasksSearchService(BaseService["TasksOperations", Task]):
    """Task search service - uses DomainConfig factory for configuration."""

    # Use factory for Activity Domain configuration
    _config = create_activity_domain_config(
        dto_class=TaskDTO,
        model_class=Task,
        domain_name="tasks",
        date_field="due_date",
        completed_statuses=("completed",),
    )

    # Additional configuration if needed
    # _search_fields = ["title", "description", "notes"]  # Override default
```

---

## Methods Enabled by Configuration

### Ownership Methods

Enabled when `_user_ownership_relationship` is set:

```python
# Verifies user owns the entity
await service.verify_ownership(uid, user_uid)

# Get with ownership check
await service.get_for_user(uid, user_uid)

# Update with ownership check
await service.update_for_user(uid, updates, user_uid)

# Delete with ownership check
await service.delete_for_user(uid, user_uid)
```

### Curriculum Methods

Enabled when `_supports_user_progress = True`:

```python
# Prerequisite chain traversal
prerequisites = await service.get_prerequisites(uid, depth=3)

# What this entity enables
enables = await service.get_enables(uid, depth=3)

# User mastery tracking
progress = await service.get_user_progress(user_uid, entity_uid)
await service.update_user_mastery(user_uid, entity_uid, 0.85)

# Entity with content
entity = await service.get_with_content(uid)

# Entity with graph neighborhood
entity_with_context = await service.get_with_context(uid, depth=2)
```

### Graph-Aware Search

Enabled when `_graph_enrichment_patterns` is configured:

```python
# Search with graph context in results
results = await service.graph_aware_faceted_search(
    query="python",
    user_uid=user_uid,
    filters={"status": "active"},
)
# Results include _graph_context field with relationship summaries
```

---

## Facade Pattern with Shared Backend

Facades create one backend, share with sub-services:

```python
class LsService(FacadeDelegationMixin):
    """Learning Step facade - uses UniversalNeo4jBackend directly."""

    def __init__(self, driver: Neo4jDriver, event_bus: EventBus | None = None):
        # ONE backend instance
        ls_backend = UniversalNeo4jBackend[Ls](driver, NeoLabel.LS, Ls)

        # Shared across sub-services
        self.core = LsCoreService(backend=ls_backend, event_bus=event_bus)
        self.search = LsSearchService(backend=ls_backend)

    _delegations = merge_delegations(
        {"create_ls": ("core", "create_ls"), ...},
        {"search": ("search", "search"), ...},
    )
```

---

## Migration: From Domain-Specific Base Class

If you have a domain-specific base class, migrate to configuration:

### Before (Domain-Specific Base)

```python
class CurriculumBaseService(BaseService[B, T]):
    """Specialized base for curriculum domains."""

    async def get_prerequisites(self, uid, depth): ...
    async def get_enables(self, uid, depth): ...
    # 819 lines of specialized code

class LsSearchService(CurriculumBaseService[LsOperations, Ls]):
    pass
```

### After (Configuration)

```python
# CurriculumBaseService DELETED

class LsSearchService(BaseService[BackendOperations[Ls], Ls]):
    _supports_user_progress = True
    _prerequisite_relationships = ["REQUIRES_STEP", "REQUIRES_KNOWLEDGE"]
    _enables_relationships = ["ENABLES_STEP"]
    _user_ownership_relationship = None
```

---

## Code Reduction

The unified architecture achieved significant code reduction:

| Deleted | Lines |
|---------|-------|
| CurriculumBaseService | 819 |
| ls_backend.py wrapper | 590 |
| lp_backend.py wrapper | 748 |
| moc_backend.py wrapper | 679 |
| Unused protocols | ~200 |
| **Total** | **~3,000+ lines** |

---

## Benefits

1. **One pattern to understand** - All services use BaseService
2. **Cross-domain features** - Any domain can use curriculum methods
3. **Opt-in complexity** - Simple domains stay simple
4. **IDE support** - Class attributes are IDE-visible
5. **Type safety** - Generic typing preserved

---

## See Also

- **Decision context:** [ADR-023](/docs/decisions/ADR-023-curriculum-baseservice-migration.md)
- **DomainConfig pattern:** `/docs/patterns/SERVICE_CONSOLIDATION_PATTERNS.md`
- **Protocol architecture:** `/docs/patterns/protocol_architecture.md`
