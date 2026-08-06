---
title: Service Consolidation Patterns
updated: 2026-04-10
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

Nine patterns to reduce boilerplate in SKUEL services. Includes the explicit delegation pattern (February 2026) that replaced FacadeDelegationMixin, saving 2,422 lines across all 9 facade services. Patterns 7-9 added April 2026.

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

## Foundational Principle: Harmony Without Over-Generalization

The tactical patterns below (DomainConfig, explicit delegation, factory-created sub-services, etc.) exist in service of one design decision: **all 6 Activity Domains share the same seven common sub-services, and no domain opts out.** `core`, `search`, `relationships`, `intelligence`, `event_handler`, `learning`, `knowledge_intelligence` — every facade has all seven, produced by `create_common_sub_services()`.

**The shared shape is a contract for interconnectivity, not a cage.** Unified search, user context aggregation, cross-domain relationship queries, the knowledge substance pipeline, ZPD assessment — these all work because every domain exposes the same surface in the same place. When the system asks "what is this user working on today," the answer doesn't care whether it comes from Tasks, Habits, or Events.

**Inside the shape, each domain keeps its voice.** Habits's `completions`/`patterns`, Events's `habit_integration`, Principles's `alignment`, Tasks's `progress`/`scheduling`/`planning` are specific to their domain and belong nowhere else. Facade mixins (`_OrchestrationMixin`, `_GravityMixin`, etc.) organize domain-specific delegation methods by concern without leaking them into the shared layer.

**The harmony enables the uniqueness.** Without the shared shape, every cross-domain operation fragments into a case statement. Without the domain-specific sub-services, the model collapses into a generic "thing with a status" — exactly the over-generalization to avoid. One shape for what a domain owes the system, total freedom for what it owes itself.

**When adding a capability, ask in this order:**
1. Does it fit in the existing shared shape? (new method on an existing common sub-service)
2. Is it cross-domain infrastructure all 6 will benefit from? (extend `create_common_sub_services()` — raises the floor for every domain, as the April 2026 Tasks learning extraction did)
3. Is it genuinely domain-specific? (new domain-specific sub-service or facade mixin — keep it out of the shared layer)

Never promote a capability only one domain uses into a common sub-service. Never push a genuinely domain-specific concern into a shared sub-service.

**See:** `.claude/skills/activity-domains/SKILL.md` § "Harmony Without Over-Generalization" for the canonical statement with examples.

**Structural contract vs. consultation contract.** Service Consolidation describes the *structural contract* — which 7 sub-services every facade owns and how they are composed. The [Shared Signal Pattern](SHARED_SIGNAL_PATTERN.md) describes the orthogonal *consultation contract* — how a cross-cutting concern (Knowledge today; Calendar and user-capacity next) is injected into each facade as a narrow protocol + delegation mixin. Together, they answer two different questions: "what does a facade own?" and "what does a facade consult?" The `knowledge_intelligence` sub-service sits at the intersection — structurally a common sub-service, functionally the first realization of Shared Signal.

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
| `create_curriculum_domain_config()` | KU, PS, LP, MOC | `user_ownership_relationship=None` (shared content) |

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
    domain_name="path_step",
    search_fields=("title", "content", "description"),  # PathStep has more searchable fields
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
| `entity_label` | `str \| None` | Auto-inferred | Neo4j base-label for multi-label Cypher matching (e.g., `"Entity"`, `"Ku"`) |
| `config_lookup_label` | `str \| None` | `model_class.__name__` | `LABEL_CONFIGS` registry key (e.g., `"Task"`, `"PathStep"`). Split from `entity_label` on 2026-04-21 — separates Neo4j-match concerns from registry-lookup concerns |
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
    ContextOperationsMixin[B, T],       # get_with_context, graph enrichment
):
    """Unified base service - now composed of focused mixins."""
```

### Mixin Responsibilities

| Mixin | Location | Responsibility |
|-------|----------|----------------|
| `ConversionHelpersMixin` | `mixins/conversion_helpers_mixin.py` | DTO conversion, `_to_domain_model`, `_to_domain_models`, `_validate_required_user_uid` |
| `CrudOperationsMixin` | `mixins/crud_operations_mixin.py` | `create`, `get`, `update`, `delete`, `verify_ownership` + pre-validation hooks (`_validate_create`, `_validate_update`) + post-lifecycle hooks (`_post_create`, `_post_update`, `_post_delete`) |
| `SearchOperationsMixin` | `mixins/search_operations_mixin.py` | `search`, `get_by_status`, `graph_aware_faceted_search` |
| `RelationshipOperationsMixin` | `mixins/relationship_operations_mixin.py` | `add_relationship`, `traverse`, `get_prerequisites` |
| `TimeQueryMixin` | `mixins/time_query_mixin.py` | `get_user_items_in_range`, `get_upcoming`, `get_overdue`, `get_active` (config-driven via `date_field` + `temporal_exclude_statuses` + `temporal_secondary_sort` + `completed_statuses`) |
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
    async def create_task(self, data: dict, user_uid: UserUID) -> Result[Task]:
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
| PS | `"Ls"` | 3 | 2 | 1 |
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
GOAPS_CONFIG = DomainRelationshipConfig(
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

1. Add function to `/adapters/persistence/neo4j/query/cypher/post_processors.py`
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

Specialized factory functions for curriculum domains with complex initialization requirements.

### The Problem

Activity domains use `create_common_sub_services()` with standard signatures. Some curriculum domains have non-standard requirements:

- **PS**: 12+ sub-services + circular dependency (intelligence must be created before core)
- **LP**: 5 sub-services + cross-domain dependency (requires `ps_service`)
- **KU**: Uses generic `create_curriculum_sub_services()` factory (4 sub-services)

### The Solution

Domain-specific factory functions in `/core/services/curriculum_domain_config.py`:

```python
from core.services.curriculum_domain_config import (
    create_ps_sub_services,
    create_lp_sub_services,
    PsSubServices,
    LpSubServices,
)
```

### PS Factory

```python
# In PsService.__init__
from core.services.curriculum_domain_config import create_ps_sub_services

subs = create_ps_sub_services(
    backend=repo,
    _chunking_service=chunking_service,
    graph_intel=graph_intel,
    _query_builder=query_builder,
    event_bus=event_bus,
    _executor=executor,
)

# Assign sub-services from factory result
self.core = subs.core
self.search_service = subs.search
self.graph = subs.graph
self.semantic = subs.semantic
self.practice = subs.practice
self.mastery = subs.mastery
self.relationships = subs.relationships
self.intelligence = subs.intelligence
self.adaptive = subs.adaptive
```

**Creation Order (handles circular dependency):**
1. `UnifiedRelationshipService` (needed by intelligence)
2. `PsIntelligenceService` (BEFORE core — core depends on intelligence)
3. `PsCoreService` (requires intelligence)
4. `PsSearchService`, `PsSemanticService`, `PsPracticeService`, `PsMasteryService`, `PsAdaptiveService`, `PsKnowledgeContextService`

### KU — Generic Factory

KU uses `create_curriculum_sub_services()` for 4 standard sub-services:

```python
# In KuService.__init__
from core.services.curriculum_domain_config import create_curriculum_sub_services

common = create_curriculum_sub_services(
    domain="ku",
    backend=backend,
    graph_intel=graph_intel,
    event_bus=event_bus,
)
self.core = common.core
self.search_service = common.search
self.relationships = common.relationships
self.intelligence = common.intelligence
```

### LP Factory

```python
# In LpService.__init__
from core.services.curriculum_domain_config import create_lp_sub_services

subs = create_lp_sub_services(
    backend=backend,
    ps_service=ps_service,  # Cross-domain dependency
    graph_intel=graph_intel,
    event_bus=event_bus,
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
1. `LpBackend` (shared by all sub-services, created in composition root)
2. `LpSearchService`, `UnifiedRelationshipService`
3. `LpCoreService` (requires `ps_service`)
4. `LpProgressService`, `LpIntelligenceService`

### Factory Return Types

```python
@dataclass
class PsSubServices:
    core: PsCoreService
    search: PsSearchService
    semantic: PsSemanticService
    practice: PsPracticeService
    mastery: PsMasteryService
    relationships: UnifiedRelationshipService
    intelligence: PsIntelligenceService
    adaptive: PsAdaptiveService
    knowledge_context: PsKnowledgeContextService

@dataclass
class LpSubServices:
    core: LpCoreService
    search: LpSearchService
    relationships: UnifiedRelationshipService
    intelligence: LpIntelligenceService
    progress: LpProgressService
```

### When to Use Each Factory

| Domain | Factory | Reason |
|--------|---------|--------|
| **KU** | `create_curriculum_sub_services("ku", ...)` | Standard 4-service pattern |
| **PS** | `create_ps_sub_services()` | 12+ services + non-standard wiring (PathStep IS curriculum content) |
| **LP** | `create_lp_sub_services()` | 5 services + cross-domain dependency |

### Benefits

1. **Encapsulation**: Complex initialization logic in one place
2. **Testability**: Factory functions are independently testable
3. **Single Responsibility**: Facades orchestrate, factories construct
4. **Documentation**: Factory docstrings explain initialization order
5. **Consistency**: All curriculum domains now follow factory pattern

---

## 7. Cross-Domain Read Consolidation (April 2026)

**Problem:** Cross-domain reads were scattered across domain backends and services. Each domain had its own N+1 pattern: fetch all entities of one type, then fan-out queries for related entities in another type, then join in Python. This is the relational-brain pattern — treating the graph like SQL tables you join in application code. Cross-domain Cypher lived on the wrong domain's backend (e.g., `ChoicesBackend` knew about Principles, `GoalsBackend` knew about Tasks).

**Solution:** `CrossDomainQueryService` (`core/services/cross_domain/cross_domain_query_service.py`) — 9 methods, each running exactly one Cypher query across 2+ domain labels, returning a frozen typed dataclass from `cross_domain_types.py`.

**Rules (enforced at the top of the file):**
- Methods MUST touch 2+ domain labels
- Takes only `QueryExecutor`, never per-domain backends
- One Cypher per call, no N+1
- Returns typed dataclass (not `dict[str, Any]`)

**Methods:**
| Method | Domains Crossed |
|--------|----------------|
| `get_principle_alignment_evidence` | Principle + Goal + Habit |
| `get_tasks_applying_knowledge` | Task + Ku |
| `get_goals_for_tasks_batch` | Task + Goal |
| `count_active_tasks_for_goal` | Goal + Task |
| `get_habit_knowledge_reinforcement` | Habit + Ku |
| `get_choice_principle_adherence` | Choice + Principle |
| `get_choice_conflict_count` | Choice + Principle |

**What it replaced:** ~790 lines of N+1 queries, fan-out loops, and misplaced cross-domain Cypher from 6 Activity Domain backends and services (174 lines from activity domain backends, 375 lines from Choices `_behavioral_signals_mixin.py`, 86 lines from `events_intelligence_service.py`, 84 lines from `goals_search_service.py`, etc.).

**Bootstrap:** Wired in `services_bootstrap/compose.py` before activity services — `CrossDomainQueryService(query_executor)`.

---

## 8. Activity Stats Consolidation (April 2026)

**Problem:** Duplicated stats-building logic across 6 Activity Domain facade files. Each facade had its own `_compute_{domain}_stats()` function with similar patterns (counting active, completed, overdue, etc.) but subtly different implementations.

**Solution:** `core/utils/activity_stats.py` — 6 frozen dataclasses (`TaskStats`, `GoalStats`, `HabitStats`, `EventStats`, `ChoiceStats`, `PrincipleStats`) with corresponding `compute_{domain}_stats()` pure functions. No I/O. The facade-level `_compute_{domain}_stats()` wrappers remain as thin dict projections for the `ListContext` contract.

**Key fields per dataclass:**
- `TaskStats`: `total, active, completed, overdue`
- `GoalStats`: `total, active, completed, on_track, wobbly_count, overdue_count, behind_count`
- `HabitStats`: `total, active, streaks, avg_streak, keystone_count`
- `EventStats`: `total, active, scheduled, today`
- `ChoiceStats`: `total, active, pending, decided`
- `PrincipleStats`: `total, core, active`

---

## 9. Facade Mixin Decomposition (April 2026)

**Problem:** Facade files (500-900 lines) mix delegation methods with domain-specific logic (option management, relationship linking, analytics enrichment). Hard to navigate and inconsistent across domains.

**Solution:** Extract related groups of facade methods into `_*_mixin.py` files within the domain package. The facade inherits from the mixins — public API is unchanged, but methods are organized by concern. Mixins declare `Any`-typed class attributes for the sub-services they use (populated by the facade `__init__`).

**Pattern:**
```python
# core/services/choices/_option_management_mixin.py
class _OptionManagementMixin:
    core: Any  # populated by ChoicesService.__init__

    async def add_option(self, choice_uid: str, option: dict[str, Any]) -> Result[bool]:
        return await self.core.add_option(choice_uid, option)

# core/services/choices_service.py
class ChoicesService(
    _OptionManagementMixin,
    KnowledgeIntelligenceDelegationMixin,
    BaseService["ChoicesOperations", Choice],
): ...
```

**Note (June 2026):** `_RelationshipMixin` was inlined back into Goals, Tasks, and Choices — it was a thin (<130 lines) single-consumer delegation slice with methods that just forwarded to `self.relationships`. The floor rule in `SERVICE_DECOMPOSITION_RULE.md` now codifies when to inline vs. extract.

**Adoption (updated June 2026):**

| Domain | Facade Mixins | Intelligence Mixins |
|--------|--------------|-------------------|
| Goals | 1 (`_OrchestrationMixin`) | 5 (`_CoreIntelligenceMixin`, `_AnalyticsMixin`, `_PredictiveMixin`, `_DualTrackMixin`, `_LearningRequirementsMixin`) |
| Habits | 3 (`_CompletionMixin`, `_EnrichmentMixin`, `_OrchestrationMixin`) | 3 (`_CoreIntelligenceMixin`, `_AnalyticsMixin`, `_DualTrackMixin`) |
| Choices | 2 (`_OptionManagementMixin`, `_EnrichmentMixin`) | 3 (`_CoreIntelligenceMixin`, `_AnalyticsMixin`, `_BehavioralSignalsMixin`) |
| Principles | 3 (`_EmbodimentMixin`, `_GravityMixin`, `_EnrichmentMixin`) | 3 (`_CoreIntelligenceMixin`, `_AnalyticsMixin`, `_AlignmentMixin`) |
| Tasks | 1 (`_OrchestrationMixin`) | 0 |
| Events | 0 (no facade mixins) | 0; `get_with_context` inherited from `_CoreIntelligenceMixin` |

**Key rules:**
- Mixin files are prefixed with `_` (private, not exported from `__init__.py`)
- Each mixin declares `Any`-typed attributes for sub-services it touches
- The facade's `__init__` populates those attributes — no `__init__` in mixins
- Public API unchanged — callers don't know about the decomposition
- **Shared `_CoreIntelligenceMixin[T]`:** `core/services/intelligence/_core_intelligence_mixin.py` owns the `get_with_context()` delegation, routing through `self.relationships.get_with_context` (mechanism B — edge vocabulary from `DomainConfig.cross_domain_relationship_types`; the `GraphContextLoader`/`self.context_loader` path was deleted in #241). Generic in the domain model so subclasses get `Result[tuple[T, GraphContext]]` for free. Tasks, Goals, Habits, PS, LP, and KU intelligence services inherit it directly; Events, Choices, and Principles keep a per-package wrapper only because they add real domain methods (performance/decision/alignment lenses). The domain-named aliases (`get_goal_with_context`, etc.) were deleted in the tasks bloat campaign — generic `get_with_context` is the one path.

---

## Quick Reference

| Pattern | File | Import |
|---------|------|--------|
| DomainConfig | `/core/services/domain_config.py` | `from core.services.domain_config import DomainConfig, create_activity_domain_config` |
| BaseService Mixins | `/core/services/mixins/` | `from core.services.mixins import ConversionHelpersMixin, CrudOperationsMixin, ...` |
| Explicit Delegation | `/core/services/tasks_service.py` | Explicit `async def` methods on facade class (no import needed) |
| Relationship Registry | `/core/models/relationship_registry.py` | `from core.models.relationship_registry import generate_graph_enrichment` |
| Post-Query Processors | `/adapters/persistence/neo4j/query/cypher/post_processors.py` | `from adapters.persistence.neo4j.query.cypher.post_processors import apply_processor, PROCESSOR_REGISTRY` |
| PS/LP Factories | `/core/services/curriculum_domain_config.py` | `from core.services.curriculum_domain_config import create_ps_sub_services, create_lp_sub_services` |
| Cross-Domain Reads | `/core/services/cross_domain/cross_domain_query_service.py` | `from core.services.cross_domain import CrossDomainQueryService` |
| Activity Stats | `/core/utils/activity_stats.py` | `from core.utils.activity_stats import compute_task_stats, TaskStats` |
| Facade Mixins | `/core/services/{domain}/_*_mixin.py` | `from core.services.{domain}._orchestration_mixin import _OrchestrationMixin` |

---

## See Also

- **Decision context:** [ADR-025](/docs/decisions/ADR-025-service-consolidation-patterns.md) - Why these patterns were chosen
- **Mixin decomposition:** [ADR-031](/docs/decisions/ADR-031-baseservice-mixin-decomposition.md) - BaseService mixin architecture
- **BaseService:** `/core/services/base_service.py` - Uses DomainConfig, composed of mixins
- **Example facade:** `/core/services/tasks_service.py` - Explicit delegation pattern
