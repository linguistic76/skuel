---
title: Service Consolidation Patterns
updated: 2026-01-29
category: patterns
related_skills:
- base-analytics-service
- activity-domains
related_docs:
- /docs/decisions/ADR-025-service-consolidation-patterns.md
- /docs/decisions/ADR-031-baseservice-mixin-decomposition.md
- /docs/patterns/DOMAINCONFIG_MIGRATION_COMPLETE.md
---

# Service Consolidation Patterns

Six patterns to reduce boilerplate in SKUEL services. Includes the explicit delegation pattern (February 2026) that replaced FacadeDelegationMixin, saving 2,422 lines across all 9 facade services.

## Quick Start

**Skills:** [@base-analytics-service](../../.claude/skills/base-analytics-service/SKILL.md), [@activity-domains](../../.claude/skills/activity-domains/SKILL.md)

For hands-on implementation:
1. Invoke `@base-analytics-service` for intelligence service patterns
2. Invoke `@activity-domains` for facade delegation patterns
3. See [BASESERVICE_QUICK_START.md](../guides/BASESERVICE_QUICK_START.md) for new developer onboarding
4. Continue below for all 6 consolidation patterns

**Related ADRs:** [ADR-025](../decisions/ADR-025-service-consolidation-patterns.md), [ADR-031](../decisions/ADR-031-baseservice-mixin-decomposition.md)

---

**Migration Status:** ✅ **100% Complete** (January 2026) - All 34 BaseService subclasses migrated to DomainConfig across all domains (Activity: 25, Curriculum: 2, Content: 3, Assignments: 3, Infrastructure: 1). See [Migration Guide](/docs/migrations/DOMAINCONFIG_MIGRATION_COMPLETE.md).

---

## 1. DomainConfig Dataclass

**Status:** ✅ Production (January 2026)

Consolidates 18 class attributes into a single, immutable configuration object.

### The Problem

Before DomainConfig, each service defined 18+ class attributes:

```python
# OLD PATTERN - ~15 lines per service
class TasksSearchService(BaseService):
    _dto_class = TaskDTO
    _model_class = Task
    _search_fields = ["title", "description"]
    _search_order_by = "created_at"
    _date_field = "due_date"
    _completed_statuses = ("completed",)
    _category_field = "category"
    _graph_enrichment_patterns = [...]  # 5 tuples
    _prerequisite_relationships = [...]
    _enables_relationships = [...]
    _user_ownership_relationship = "OWNS"
    _supports_user_progress = True
    # ... more attributes
```

### The Solution

```python
# NEW PATTERN - 1 config object
from core.services.domain_config import create_activity_domain_config

class TasksSearchService(BaseService[TasksOperations, Task]):
    _config = create_activity_domain_config(
        dto_class=TaskDTO,
        model_class=Task,
        domain_name="tasks",
        date_field="due_date",
        completed_statuses=("completed",),
    )
```

### Factory Functions

Use the appropriate factory for your domain type:

| Factory | Use For | Key Difference |
|---------|---------|----------------|
| `create_activity_domain_config()` | Tasks, Goals, Habits, Events, Choices, Principles | `user_ownership_relationship="OWNS"` |
| `create_curriculum_domain_config()` | KU, LS, LP, MOC | `user_ownership_relationship=None` (shared content) |

### Activity Domain Factory

```python
from core.services.domain_config import create_activity_domain_config

_config = create_activity_domain_config(
    dto_class=TaskDTO,              # Required: DTO class
    model_class=Task,               # Required: Domain model class
    domain_name="tasks",            # Required: Used for logger name
    date_field="due_date",          # Optional: Default "created_at"
    completed_statuses=("completed",),  # Optional: Status values for completion
    category_field="category",      # Optional: Default "category"
    search_fields=("title", "description"),  # Optional: Default ("title", "description")
    search_order_by="created_at",   # Optional: Default "created_at"
)
```

### Curriculum Domain Factory

```python
from core.services.domain_config import create_curriculum_domain_config

_config = create_curriculum_domain_config(
    dto_class=CurriculumDTO,
    model_class=Curriculum,
    domain_name="ku",
    search_fields=("title", "content", "description"),  # KU has more searchable fields
    search_order_by="updated_at",   # Curriculum sorts by update time
    category_field="domain",        # Curriculum uses 'domain' not 'category'
    content_field="content",        # Field containing main content
)
```

### DomainConfig Fields Reference

| Field | Type | Default | Purpose |
|-------|------|---------|---------|
| `dto_class` | `type` | Required | DTO class for this domain |
| `model_class` | `type` | Required | Domain model class |
| `entity_label` | `str \| None` | Auto-inferred | Neo4j label |
| `service_name` | `str \| None` | Auto-inferred | Logger name prefix |
| `date_field` | `str` | `"created_at"` | Field for date range queries |
| `completed_statuses` | `tuple[str, ...]` | `()` | Status values indicating completion |
| `search_fields` | `tuple[str, ...]` | `("title", "description")` | Fields for text search |
| `search_order_by` | `str` | `"created_at"` | Default sort field |
| `category_field` | `str` | `"category"` | Field for category filtering |
| `graph_enrichment_patterns` | `tuple[...]` | Auto from registry | Relationship patterns |
| `user_ownership_relationship` | `str \| None` | `"OWNS"` | Ownership relationship (None for shared) |
| `prerequisite_relationships` | `tuple[str, ...]` | Auto from registry | Prerequisite relationship types |
| `enables_relationships` | `tuple[str, ...]` | Auto from registry | Enables relationship types |
| `content_field` | `str` | `"content"` | Main content field |
| `mastery_threshold` | `float` | `0.7` | Mastery threshold |
| `supports_user_progress` | `bool` | `False` | Enable progress tracking |

### Accessing Config Values in BaseService

BaseService uses `_get_config_value()` to access config with fallback to class attributes:

```python
# Inside a service method
dto_class = self._get_config_value("dto_class")
search_fields = self._get_config_value("search_fields")
```

---

## 2. BaseService Mixin Decomposition

Decomposes the monolithic BaseService into 7 focused mixins following Single Responsibility Principle.

**Decision context:** See [ADR-031](/docs/decisions/ADR-031-baseservice-mixin-decomposition.md) for the full decomposition rationale.

### The Problem

BaseService had grown to 2,973 lines handling CRUD, search, graph traversal, ownership, progress tracking, and context enrichment - violating SRP and making changes risky for all 6 Activity Domains.

### The Solution

```python
# BaseService now inherits from 7 focused mixins
class BaseService[B: BackendOperations, T: DomainModelProtocol](
    ConversionHelpersMixin[B, T],      # DTO conversion, result handling
    CrudOperationsMixin[B, T],          # create, get, update, delete, ownership
    SearchOperationsMixin[B, T],        # search, filtering, graph-aware search
    RelationshipOperationsMixin[B, T],  # graph relationships, prerequisites
    TimeQueryMixin[B, T],               # date range queries, due_soon, overdue
    UserProgressMixin[B, T],            # mastery tracking, curriculum progress
    ContextOperationsMixin[B, T],       # get_with_context, graph enrichment
):
    """Unified base service - now composed of focused mixins."""
```

### Mixin Responsibilities

| Mixin | Location | Responsibility |
|-------|----------|----------------|
| `ConversionHelpersMixin` | `mixins/conversion_helpers_mixin.py` | DTO conversion, `_to_domain_model`, `_ensure_exists` |
| `CrudOperationsMixin` | `mixins/crud_operations_mixin.py` | `create`, `get`, `update`, `delete`, `verify_ownership` |
| `SearchOperationsMixin` | `mixins/search_operations_mixin.py` | `search`, `get_by_status`, `graph_aware_faceted_search` |
| `RelationshipOperationsMixin` | `mixins/relationship_operations_mixin.py` | `add_relationship`, `traverse`, `get_prerequisites` |
| `TimeQueryMixin` | `mixins/time_query_mixin.py` | `get_user_items_in_range`, `get_due_soon`, `get_overdue` (config-driven via `temporal_exclude_statuses` + `temporal_secondary_sort`) |
| `UserProgressMixin` | `mixins/user_progress_mixin.py` | `get_user_progress`, `update_user_mastery` |
| `ContextOperationsMixin` | `mixins/context_operations_mixin.py` | `get_with_context`, `get_with_content` |

### Fail-Fast Philosophy

All mixins follow SKUEL's fail-fast philosophy - no fallback paths:

```python
# CORRECT - fail-fast when not configured
if self._dto_class is None or self._model_class is None:
    return Result.fail(
        Errors.system(
            message=f"{self.entity_label} must configure _dto_class and _model_class",
            operation="get_with_context",
        )
    )

# WRONG - graceful degradation (removed)
# if get_user_entities:
#     return await get_user_entities(...)
# else:
#     # Fallback path - DELETED
```

### Benefits

- **Single Responsibility**: Each mixin has one reason to change
- **Zero Breaking Changes**: All public methods remain accessible via inheritance
- **Testable Units**: Mixins can be tested in isolation
- **Clear Organization**: Easy to find code by responsibility

### Usage

Services continue to extend BaseService unchanged:

```python
from core.services.base_service import BaseService

class TasksCoreService(BaseService[TasksOperations, Task]):
    _dto_class = TaskDTO
    _model_class = Task
    # All mixin methods available via inheritance
```

---

## 3. Explicit Delegation Methods (February 2026)

All 9 facade services use explicit `async def` delegation methods — MyPy-native, no mixin needed.

### The Problem (Historical)

`FacadeDelegationMixin` (deleted February 2026) generated delegation methods dynamically via a `_delegations` dict. This required a parallel `facade_protocols.py` file to make the dynamic methods visible to MyPy — a three-way synchronization burden (service class, delegations dict, protocol file).

### The Solution

```python
from typing import Any

class TasksService(BaseService[TasksOperations, Task]):
    core: TasksCoreService
    search: TasksSearchService
    intelligence: TasksIntelligenceService

    # Explicit delegation — MyPy-native, no mixin needed
    async def create_task(self, *args: Any, **kwargs: Any) -> Any:
        return await self.core.create_task(*args, **kwargs)

    async def get_task(self, *args: Any, **kwargs: Any) -> Any:
        return await self.core.get_task(*args, **kwargs)

    async def search_tasks(self, *args: Any, **kwargs: Any) -> Any:
        return await self.search.search(*args, **kwargs)
```

### How It Works

1. Every delegated method is a real `async def` on the class
2. MyPy sees all methods natively — no protocol workaround required
3. Route files import the concrete service class as the type hint

### Route Files Use Concrete Class Types

```python
# Before (deleted)
if TYPE_CHECKING:
    from core.ports.facade_protocols import TasksFacadeProtocol

def create_tasks_api_routes(app, rt, tasks_service: "TasksFacadeProtocol", ...):
    ...

# After (current)
if TYPE_CHECKING:
    from core.services.tasks_service import TasksService

def create_tasks_api_routes(app, rt, tasks_service: "TasksService", ...):
    ...
```

### Underscore Prefix Convention

Parameters with underscore prefix (e.g., `_filters`, `_domain_filter`) indicate **placeholders for future implementation**:

```python
async def get_learning_opportunities(
    self, _filters: dict[str, Any] | None = None
) -> Result[list[dict[str, Any]]]:
    """
    Get learning opportunities.

    Args:
        _filters: Placeholder for future filtering capability (not yet implemented)
    """
    # Currently discovers all opportunities - filtering will be added later
    ...
```

**Convention meaning:**
- `_param` = "This parameter exists in the signature but is not yet implemented"
- NOT "This parameter is unused and should be deleted"

### Custom Logic Methods

For methods requiring orchestration across sub-services, write the logic directly:

```python
class TasksService(BaseService[TasksOperations, Task]):

    # Simple delegation
    async def get_task(self, *args: Any, **kwargs: Any) -> Any:
        return await self.core.get_task(*args, **kwargs)

    # Custom logic (not a delegation — orchestrates multiple sub-services)
    async def create_task(self, data: dict, user_uid: str) -> Result[Task]:
        if not data.get("title"):
            return Result.fail(Errors.validation("Title required"))
        result = await self.core.create_task(data, user_uid)
        if result.is_ok:
            await self._send_notification(result.value)
        return result
```

### Benefits

- **2,422 lines removed** — no mixin, no protocol file, no three-way sync
- **MyPy-native** — all methods visible without workarounds
- **One file** — everything in the service class itself
- **No ceremony** — add a method, it just works

---

## 4. Relationship Registry

Centralized source of truth for graph enrichment patterns.

### The Problem

Graph enrichment patterns were scattered across services:

```python
# OLD - each service defined its own patterns
class TasksSearchService(BaseService):
    _graph_enrichment_patterns = [
        ("APPLIES_KNOWLEDGE", "Ku", "applied_knowledge", "outgoing"),
        ("FULFILLS_GOAL", "Goal", "fulfills_goals", "outgoing"),
        # ...
    ]

class GoalsSearchService(BaseService):
    _graph_enrichment_patterns = [
        # Similar patterns, different service
    ]
```

### The Solution

```python
from core.models.relationship_registry import (
    generate_graph_enrichment,
    generate_prerequisite_relationships,
    generate_enables_relationships,
)

# Look up patterns for a domain
task_patterns = generate_graph_enrichment("Task")
task_prerequisites = generate_prerequisite_relationships("Task")
task_enables = generate_enables_relationships("Task")

# Or use helper functions
patterns = get_graph_enrichment("Task")
```

### Registry Structure

**Location:** `/core/models/relationship_registry.py`

Three generator functions, keyed by entity label:

```python
from core.models.relationship_registry import (
    generate_graph_enrichment,           # -> list[tuple[str, str, str, str]]
    generate_prerequisite_relationships, # -> list[str]
    generate_enables_relationships,      # -> list[str]
)
```

### Graph Enrichment Pattern Format

```python
# Format: (relationship_type, target_label, context_field_name, direction)
("APPLIES_KNOWLEDGE", "Ku", "applied_knowledge", "outgoing")
```

| Field | Purpose |
|-------|---------|
| `relationship_type` | The Neo4j relationship type |
| `target_label` | The Neo4j label of related nodes |
| `context_field_name` | Name in `_graph_context` response |
| `direction` | `"outgoing"`, `"incoming"`, or `"both"` |

### Supported Domains

| Domain | Entity Label | Graph Patterns | Prerequisites | Enables |
|--------|--------------|----------------|---------------|---------|
| Tasks | `"Task"` | 5 | 2 | 2 |
| Goals | `"Goal"` | 6 | 2 | 1 |
| Habits | `"Habit"` | 4 | 1 | 1 |
| Events | `"Event"` | 3 | 1 | 1 |
| Choices | `"Choice"` | 3 | 1 | 1 |
| Principles | `"Principle"` | 4 | 1 | 3 |
| KU | `"Ku"` | 6 | 1 | 1 |
| LS | `"Ls"` | 3 | 2 | 1 |
| LP | `"Lp"` | 3 | 2 | 1 |
### Adding New Relationships

To add a new relationship pattern:

1. Add the relationship to the domain's `DomainRelationshipConfig` in `/core/models/relationship_registry.py`
2. Use `RelationshipName` enum — add a new enum value if needed

```python
# In relationship_registry.py — add to domain config
TASKS_CONFIG = DomainRelationshipConfig(
    relationships=[
        ...,
        UnifiedRelationshipSpec(
            relationship=RelationshipName.NEW_RELATIONSHIP,
            target_label="TargetLabel",
            direction="outgoing",
            context_field="field_name",
        ),
    ],
)
```

---

## 5. Post-Query Processors

Registry-driven Python calculations for computed context fields.

### The Problem

Domain services needed calculated fields derived from relationship data:

```python
# OLD PATTERN - hardcoded in BaseService
if self.entity_label == "Goal" and "milestones" in graph_context:
    milestone_data = graph_context.get("milestones", [])
    total = len(milestone_data)
    completed = sum(1 for m in milestone_data if m.get("is_completed"))
    percentage = (completed / total * 100.0) if total > 0 else 0.0
    graph_context["milestone_progress"] = {...}
```

### The Solution

Define processors declaratively in the registry, implement once in `post_processors.py`:

```python
# In relationship_registry.py
GOALS_CONFIG = DomainRelationshipConfig(
    # ... relationships ...
    post_processors=(
        PostProcessor(
            source_field="milestones",       # Field from Cypher query
            target_field="milestone_progress",  # Computed field name
            processor_name="calculate_milestone_progress",  # Function in registry
        ),
    ),
)

# In post_processors.py
def calculate_milestone_progress(milestones: list[dict]) -> dict:
    if not milestones:
        return {"total": 0, "completed": 0, "percentage": 0.0}
    total = len(milestones)
    completed = sum(1 for m in milestones if m.get("is_completed"))
    return {
        "total": total,
        "completed": completed,
        "percentage": round((completed / total * 100.0), 2),
    }

PROCESSOR_REGISTRY = {
    "calculate_milestone_progress": calculate_milestone_progress,
    "calculate_habit_streak_summary": calculate_habit_streak_summary,
    "calculate_task_status_summary": calculate_task_status_summary,
}
```

### How It Works

1. `BaseService.get_with_context()` calls `generate_context_query()` from registry
2. Query returns relationship data (e.g., `milestones` list)
3. `_parse_context_result()` loops through `config.post_processors`
4. Each processor transforms source data into computed field

```python
# In BaseService._parse_context_result()
for processor in config.post_processors:
    source_data = graph_context.get(processor.source_field, [])
    if source_data:
        graph_context[processor.target_field] = apply_processor(
            processor.processor_name, source_data
        )
```

### Available Processors

| Processor | Source Field | Output |
|-----------|--------------|--------|
| `calculate_milestone_progress` | `milestones` | `{total, completed, percentage}` |
| `calculate_habit_streak_summary` | `habits` | `{total, active, total_streak_days, avg_streak}` |
| `calculate_task_status_summary` | `tasks` | `{total, completed, in_progress, pending, completion_percentage}` |

### Adding New Processors

1. Add function to `/core/models/query/cypher/post_processors.py`
2. Register in `PROCESSOR_REGISTRY`
3. Add `PostProcessor` to domain config in `relationship_registry.py`

```python
# Step 1: Add function
def calculate_new_metric(items: list[dict]) -> dict:
    # Your calculation logic
    return {"metric": calculated_value}

# Step 2: Register
PROCESSOR_REGISTRY["calculate_new_metric"] = calculate_new_metric

# Step 3: Add to domain config
DOMAIN_CONFIG = DomainRelationshipConfig(
    post_processors=(
        PostProcessor(
            source_field="items",
            target_field="new_metric",
            processor_name="calculate_new_metric",
        ),
    ),
)
```

---

## 6. Domain-Specific Factories (Curriculum)

Specialized factory functions for KU and LP domains with complex initialization requirements.

### The Problem

Activity domains use `create_common_sub_services()` with standard signatures. Curriculum domains (KU, LP) have non-standard requirements:

- **KU**: 8 sub-services + circular dependency (intelligence must be created before core)
- **LP**: 5 sub-services + cross-domain dependency (requires `ls_service`)
- **LS**: Uses generic factory (standard signatures)
- **MOC**: Has circular dependencies (core ↔ section) handled in facade

### The Solution

Domain-specific factory functions in `/core/utils/curriculum_domain_config.py`:

```python
from core.utils.curriculum_domain_config import (
    create_ku_sub_services,
    create_lp_sub_services,
    KuSubServices,
    LpSubServices,
)
```

### KU Factory

```python
# In KuService.__init__
from core.utils.curriculum_domain_config import create_ku_sub_services

subs = create_ku_sub_services(
    backend=repo,
    content_repo=content_repo,
    neo4j_adapter=neo4j_adapter,
    chunking_service=chunking_service,
    graph_intelligence_service=graph_intelligence_service,
    embeddings_service=embeddings_service,
    llm_service=llm_service,
    query_builder=query_builder,
    event_bus=event_bus,
    driver=driver,
)

# Assign sub-services from factory result
self.core = subs.core
self.search_service = subs.search
self.graph = subs.graph
self.semantic = subs.semantic
self.practice = subs.practice
self.interaction = subs.interaction
self.relationships = subs.relationships
self.intelligence = subs.intelligence
```

**Creation Order (handles circular dependency):**
1. `UnifiedRelationshipService` (needed by intelligence)
2. `KuIntelligenceService` (BEFORE core - core depends on intelligence)
3. `KuCoreService` (requires intelligence)
4. `KuSearchService`, `KuGraphService`, `KuSemanticService`, `KuPracticeService`, `KuInteractionService`

### LP Factory

```python
# In LpService.__init__
from core.utils.curriculum_domain_config import create_lp_sub_services

subs = create_lp_sub_services(
    driver=driver,
    ls_service=ls_service,  # Cross-domain dependency
    graph_intelligence_service=graph_intelligence_service,
    event_bus=event_bus,
    embeddings_service=embeddings_service,
    llm_service=llm_service,
    progress_backend=progress_backend,
    user_service=user_service,
)

# Assign sub-services from factory result
self.core = subs.core
self.search = subs.search
self.relationships = subs.relationships
self.intelligence = subs.intelligence
self.progress = subs.progress
```

**Creation Order (handles cross-domain dependency):**
1. `UniversalNeo4jBackend[Lp]` (shared by all sub-services)
2. `LpSearchService`, `UnifiedRelationshipService`
3. `LpCoreService` (requires `ls_service`)
4. `LpProgressService`, `LpIntelligenceService`

### Factory Return Types

```python
@dataclass
class KuSubServices:
    core: KuCoreService
    search: KuSearchService
    graph: KuGraphService
    semantic: KuSemanticService
    practice: KuPracticeService
    interaction: KuInteractionService
    relationships: UnifiedRelationshipService
    intelligence: KuIntelligenceService

@dataclass
class LpSubServices:
    core: LpCoreService
    search: LpSearchService
    relationships: UnifiedRelationshipService
    intelligence: LpIntelligenceService
    progress: LpProgressService
    backend: UniversalNeo4jBackend[Lp]  # Exposed for legacy access
```

### When to Use Each Factory

| Domain | Factory | Reason |
|--------|---------|--------|
| **LS** | `create_curriculum_sub_services()` | Standard 4-service pattern |
| **KU** | `create_ku_sub_services()` | 8 services + circular dependency |
| **LP** | `create_lp_sub_services()` | 5 services + cross-domain dependency |
| **MOC** | Manual in facade | Circular (core ↔ section) requires post-init wiring |

### Benefits

1. **Encapsulation**: Complex initialization logic in one place
2. **Testability**: Factory functions are independently testable
3. **Single Responsibility**: Facades orchestrate, factories construct
4. **Documentation**: Factory docstrings explain initialization order
5. **Consistency**: All curriculum domains now follow factory pattern

---

## Quick Reference

| Pattern | File | Import |
|---------|------|--------|
| DomainConfig | `/core/services/domain_config.py` | `from core.services.domain_config import DomainConfig, create_activity_domain_config` |
| BaseService Mixins | `/core/services/mixins/` | `from core.services.mixins import ConversionHelpersMixin, CrudOperationsMixin, ...` |
| Explicit Delegation | `/core/services/tasks_service.py` | Explicit `async def` methods on facade class (no import needed) |
| Relationship Registry | `/core/models/relationship_registry.py` | `from core.models.relationship_registry import generate_graph_enrichment` |
| Post-Query Processors | `/core/models/query/cypher/post_processors.py` | `from core.models.query.cypher.post_processors import apply_processor, PROCESSOR_REGISTRY` |
| KU/LP Factories | `/core/utils/curriculum_domain_config.py` | `from core.utils.curriculum_domain_config import create_ku_sub_services, create_lp_sub_services` |

---

## See Also

- **Decision context:** [ADR-025](/docs/decisions/ADR-025-service-consolidation-patterns.md) - Why these patterns were chosen
- **Mixin decomposition:** [ADR-031](/docs/decisions/ADR-031-baseservice-mixin-decomposition.md) - BaseService mixin architecture
- **BaseService:** `/core/services/base_service.py` - Uses DomainConfig, composed of mixins
- **Example facade:** `/core/services/tasks_service.py` - Explicit delegation pattern
