---
title: Service Consolidation Patterns
updated: 2026-01-21
status: current
category: patterns
tags:
- patterns
- consolidation
- baseservice
- domainconfig
- facade
- delegation
- mixin
related:
- ADR-025-service-consolidation-patterns.md
- ADR-031-baseservice-mixin-decomposition.md
related_skills:
- activity-domains
- base-analytics-service
---

# Service Consolidation Patterns

Six patterns to reduce boilerplate in SKUEL services (~1,500+ lines saved across 10 facades).

**Decision context:** See [ADR-025](/docs/decisions/ADR-025-service-consolidation-patterns.md) for why these patterns were chosen over alternatives.

---

## 1. DomainConfig Dataclass

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
    dto_class=KuDTO,
    model_class=Ku,
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
| `TimeQueryMixin` | `mixins/time_query_mixin.py` | `get_user_items_in_range`, `get_due_soon`, `get_overdue` |
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

## 3. FacadeDelegationMixin

Auto-generates delegation methods for facade services at class definition time, **with signature preservation**.

### The Problem

Facade services had 20-30 one-line delegation methods:

```python
# OLD PATTERN - ~30 lines of boilerplate
class TasksService:
    async def create_task(self, *args, **kwargs):
        return await self.core.create_task(*args, **kwargs)

    async def get_task(self, *args, **kwargs):
        return await self.core.get_task(*args, **kwargs)

    async def search(self, *args, **kwargs):
        return await self.search.search(*args, **kwargs)

    # ... 27 more methods
```

### The Solution

```python
from core.services.mixins import FacadeDelegationMixin, merge_delegations

class TasksService(FacadeDelegationMixin, BaseService[TasksOperations, Task]):
    # Class-level type annotations enable signature preservation
    core: TasksCoreService
    search: TasksSearchService
    intelligence: TasksIntelligenceService  # January 2026: TasksAnalyticsService removed

    _delegations = merge_delegations(
        # CRUD delegations to core
        {
            "create_task": ("core", "create_task"),
            "get_task": ("core", "get_task"),
            "update_task": ("core", "update_task"),
            "delete_task": ("core", "delete_task"),
        },
        # Search delegations
        {
            "search": ("search", "search"),
            "intelligent_search": ("search", "intelligent_search"),
        },
        # Analytics delegations
        {
            "get_learning_opportunities": ("analytics", "get_learning_opportunities"),
        },
    )
```

### How It Works

1. Define `_delegations` as a dict mapping `{facade_method: (sub_service, target_method)}`
2. `__init_subclass__` generates async methods at class definition time
3. IDE completion works because methods exist on the class (not `__getattr__`)

### Signature Preservation (January 2026)

When class-level type annotations are provided, the mixin preserves method signatures:

```python
# Without annotations - inspect.signature() returns (*args, **kwargs)
class BadFacade(FacadeDelegationMixin):
    _delegations = {"method": ("service", "method")}

# With annotations - inspect.signature() returns actual parameters
class GoodFacade(FacadeDelegationMixin):
    service: SomeService  # <-- Type annotation required
    _delegations = {"method": ("service", "method")}
```

**How it works internally:**
1. `__init_subclass__` reads `__annotations__` from the class
2. String annotations (from `from __future__ import annotations`) are resolved using `eval()` with module globals
3. The target method's signature is extracted using `inspect.signature()`
4. The delegator's `__signature__` attribute is set to the resolved signature

**Benefits:**
- `inspect.signature(Facade.method)` returns actual parameter names
- IDE tools and documentation generators see real signatures
- Type checkers can validate call sites

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

This convention signals architectural intent: the API contract is defined, but implementation is deferred.

### Delegation Format

```python
_delegations = {
    "facade_method_name": ("sub_service_attr", "target_method_name"),
}
```

- `facade_method_name`: Name of the method on this facade
- `sub_service_attr`: Attribute name of the sub-service (e.g., `"core"`, `"search"`)
- `target_method_name`: Method name on the sub-service to call

### Pre-defined Delegation Sets

Import common delegation patterns:

```python
from core.services.mixins import (
    CRUD_DELEGATIONS,      # create, get, get_many, update, delete, list
    SEARCH_DELEGATIONS,    # search, get_by_status, get_by_category, etc.
    RELATIONSHIP_DELEGATIONS,  # link_to_knowledge, link_to_goal, etc.
    merge_delegations,
)

class MyService(FacadeDelegationMixin):
    _delegations = merge_delegations(
        CRUD_DELEGATIONS,
        SEARCH_DELEGATIONS,
        {
            # Domain-specific delegations
            "complete_task": ("core", "complete_task"),
        }
    )
```

### When NOT to Delegate

Override manually when custom logic is needed:

```python
class TasksService(FacadeDelegationMixin):
    _delegations = merge_delegations(
        CRUD_DELEGATIONS,
        # Don't include create_task - we override it
    )

    # Manual override with custom logic
    async def create_task(self, data: dict, user_uid: str) -> Result[Task]:
        # Validation before delegating
        if not data.get("title"):
            return Result.fail(Errors.validation("Title required"))

        # Now delegate with additional processing
        result = await self.core.create_task(data, user_uid)

        # Post-processing
        if result.is_ok:
            await self._send_notification(result.value)

        return result
```

### Error Handling

If a sub-service isn't initialized, a clear error is raised:

```
AttributeError: TasksService.create_task() requires 'core' sub-service to be initialized
```

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
    GRAPH_ENRICHMENT_REGISTRY,
    PREREQUISITE_REGISTRY,
    ENABLES_REGISTRY,
    get_graph_enrichment,
    get_prerequisite_relationships,
    get_enables_relationships,
)

# Look up patterns for a domain
task_patterns = GRAPH_ENRICHMENT_REGISTRY["Task"]
task_prerequisites = PREREQUISITE_REGISTRY["Task"]
task_enables = ENABLES_REGISTRY["Task"]

# Or use helper functions
patterns = get_graph_enrichment("Task")
```

### Registry Structure

**Location:** `/core/models/relationship_registry.py`

Three registries, keyed by entity label:

```python
# Graph enrichment: which relationships to include in search results
GRAPH_ENRICHMENT_REGISTRY: dict[str, list[GraphEnrichmentPattern]]

# Prerequisites: which relationships represent prerequisites
PREREQUISITE_REGISTRY: dict[str, list[str]]

# Enables: which relationships represent what this entity enables
ENABLES_REGISTRY: dict[str, list[str]]
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
| MOC | `"MapOfContent"` | 4 | 1 | 3 |

### Adding New Relationships

To add a new relationship pattern:

1. Add to the appropriate registry in `/core/models/relationship_registry.py`
2. Use `RelationshipName` enum if it exists, or add a new enum value

```python
# In relationship_registry.py
GRAPH_ENRICHMENT_REGISTRY["Task"].append(
    (RelationshipName.NEW_RELATIONSHIP.value, "TargetLabel", "field_name", "outgoing")
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
# In unified_relationship_registry.py
GOALS_UNIFIED = DomainRelationshipConfig(
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
3. Add `PostProcessor` to domain config in `unified_relationship_registry.py`

```python
# Step 1: Add function
def calculate_new_metric(items: list[dict]) -> dict:
    # Your calculation logic
    return {"metric": calculated_value}

# Step 2: Register
PROCESSOR_REGISTRY["calculate_new_metric"] = calculate_new_metric

# Step 3: Add to domain config
DOMAIN_UNIFIED = DomainRelationshipConfig(
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
| FacadeDelegationMixin | `/core/services/mixins/facade_delegation_mixin.py` | `from core.services.mixins import FacadeDelegationMixin, merge_delegations` |
| Relationship Registry | `/core/models/relationship_registry.py` | `from core.models.relationship_registry import GRAPH_ENRICHMENT_REGISTRY` |
| Post-Query Processors | `/core/models/query/cypher/post_processors.py` | `from core.models.query.cypher.post_processors import apply_processor, PROCESSOR_REGISTRY` |
| KU/LP Factories | `/core/utils/curriculum_domain_config.py` | `from core.utils.curriculum_domain_config import create_ku_sub_services, create_lp_sub_services` |

---

## See Also

- **Decision context:** [ADR-025](/docs/decisions/ADR-025-service-consolidation-patterns.md) - Why these patterns were chosen
- **Mixin decomposition:** [ADR-031](/docs/decisions/ADR-031-baseservice-mixin-decomposition.md) - BaseService mixin architecture
- **BaseService:** `/core/services/base_service.py` - Uses DomainConfig, composed of mixins
- **Example facade:** `/core/services/tasks_service.py` - FacadeDelegationMixin usage
