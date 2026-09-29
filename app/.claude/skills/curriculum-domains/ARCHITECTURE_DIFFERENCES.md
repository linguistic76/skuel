# Curriculum vs Activity Domain Architecture

> Key architectural differences between Curriculum Domains (Ku, PathStep, LearningPath) and Activity Domains (Tasks, Goals, etc.).

## Ownership Model

| Aspect | Activity Domains | Curriculum Domains (Ku, PS, LP) |
|--------|------------------|-------------------|
| **Ownership** | User-owned | Shared global content |
| **`DomainConfig.user_ownership_relationship`** | `RelationshipName.OWNS` | `None` |
| **Creation** | Any authenticated user (forms, API, vault sync) | Content-vault ingestion; generated Kus from `KuService.create_ku`. No CRUD API |
| **Access** | Owner only (multi-tenant) | All users |
| **Filtering** | Always by `user_uid` | No user filter |

Exercise sits between the two: its CRUD routes are `ContentScope.USER_OWNED` with
`require_role=UserRole.TEACHER`, and a CURRICULUM-scope exercise is vault-authored shared content.

## Sub-service Creation Patterns

### Activity Domains — One Generic Factory

The 6 Activity Domains (Tasks, Goals, Habits, Events, Choices, Principles) call
`create_common_sub_services()`. It builds `core`, `search`, `relationships`, `event_handler` and
`learning`, passes the shared `knowledge_intelligence` through, and builds `intelligence` only
for Principles; the other five facades build their own intelligence service:

```python
from core.services.activity_domain_config import create_common_sub_services

common = create_common_sub_services(
    domain="principles",
    backend=backend,
    graph_intel=graph_intel,
    event_bus=event_bus,
    insight_store=insight_store,
    activity_knowledge_intelligence=activity_knowledge_intelligence,
)
self.core = common.core
self.search = common.search
self.relationships = common.relationships
self.intelligence = common.intelligence  # built by the factory for Principles only
```

### Curriculum Domains — Three Factories

| Domain | Factory Function | Builds |
|--------|-----------------|--------|
| **KU** | `create_curriculum_sub_services(backend, graph_intel, event_bus)` — Ku only, no `domain` argument | `core`, `search`, `relationships`, `intelligence` |
| **PS** | `create_ps_sub_services()` | 12 slots (the facade adds `progress` and `ai`) |
| **LP** | `create_lp_sub_services()` — requires `ps_service` | `core`, `search`, `relationships`, `intelligence`, `progress` (the facade adds `ai`) |

```python
# KU
from core.services.curriculum_domain_config import create_curriculum_sub_services
common = create_curriculum_sub_services(backend=backend, graph_intel=graph_intel, event_bus=event_bus)

# PS
from core.services.curriculum_domain_config import create_ps_sub_services
subs = create_ps_sub_services(
    backend=backend, _chunking_service=chunking_service, graph_intel=graph_intel,
    event_bus=event_bus, user_service=user_service, ps_intelligence_backend=ps_intelligence_backend,
)

# LP — cross-domain PsService dependency
from core.services.curriculum_domain_config import create_lp_sub_services
subs = create_lp_sub_services(backend=backend, ps_service=ps_service, graph_intel=graph_intel, ...)
```

**Note on MOC:** There is no `MocService`. MOC identity is emergent — any Entity with outgoing
`ORGANIZES` relationships is an organizer. The operations are `PsService.organization`
(`PsOrganizationService`).

## Creation Order

Each curriculum factory builds `UnifiedRelationshipService` first, because intelligence takes
it. `create_ps_sub_services` then builds `PsIntelligenceService` before the rest, because
`PsSemanticService` takes it (`PsSemanticService(repo=backend, intelligence=intelligence)`).
`PsCoreService(backend, event_bus)` takes no intelligence, so there is no core ↔ intelligence
cycle. LP's only ordering constraint is outside its factory: `PsService` must exist first.

## Sub-service Count Comparison

Facade slots, counting the seven common Activity slots and the FULL-tier `ai`:

| Domain | Slots | Factory Type |
|--------|-------|--------------|
| **Tasks** | 11 | Generic |
| **Goals** | 11 | Generic |
| **Habits** | 13 | Generic |
| **Events** | 11 | Generic |
| **Choices** | 8 | Generic |
| **Principles** | 10 | Generic |
| **KU** | 4 (no `ai`) | Ku factory — **lowest** (atomic reference) |
| **PS (PathStep)** | 14 | Specialized — **highest** (`core`, `search`, `graph`, `semantic`, `practice`, `mastery`, `relationships`, `intelligence`, `adaptive`, `application_discovery`, `context_service`, `organization`, `progress`, `ai`) |
| **LP** | 6 | Specialized |

Read the slots off each facade's `__init__`; this table is a snapshot of it.

## Relationship Service Patterns

**Both domain types use `UnifiedRelationshipService`:**

```python
from core.models.relationship_registry import PS_CONFIG, TASKS_CONFIG
from core.services.relationships import UnifiedRelationshipService

# Activity Domains
self.relationships = UnifiedRelationshipService(
    backend=backend, config=TASKS_CONFIG, graph_intel=graph_intel
)

# Curriculum Domains (PathStep)
self.relationships = UnifiedRelationshipService(
    backend=backend, config=PS_CONFIG, graph_intel=graph_intel
)
```

**Direct backend calls for complex queries:**
```python
# Domain-specific Cypher lives in domain backends, not services.
# PsBackend.get_with_context_raw() (_KnowledgeContextMixin) fetches the graph neighborhood:
result = await self.backend.get_with_context_raw(uid, min_confidence)
# KuBackend.get_usage_summary() counts the PathSteps using / training this Ku, organized children:
result = await self.backend.get_usage_summary(ku_uid)
```

## BaseService Usage

Both domain types extend `BaseService` and declare a `DomainConfig`:

```python
# Activity Domain — with ownership
class TasksCoreService(BaseService["TasksOperations", Task, TaskUpdateIntent]):
    _config = create_activity_domain_config(...)   # user_ownership_relationship=OWNS

# Curriculum Domain — shared content
class PsSearchService(BaseService["PsOperations", PathStep]):
    _config = create_curriculum_domain_config(
        dto_class=PathStepDTO,
        model_class=PathStep,
        entity_label="Entity",
        domain_name="ps",
        search_fields=("title", "intent", "description"),
        search_order_by="updated_at",
        category_field="nous",
        content_field="description",
    )   # user_ownership_relationship=None; supports_user_progress=True
```

Ku sets `supports_user_progress=False` and `entity_label="Ku"`.

## Per-User Data in Curriculum

Even though content is shared, Curriculum Domains track per-user data:

| Data Type | Storage | Example |
|-----------|---------|---------|
| **Learning state** | User→PathStep edges | `(User)-[:VIEWED]->(PathStep)`, `:IN_PROGRESS`, `:MARKED_AS_READ`, `:BOOKMARKED` |
| **Mastery** | User→PathStep / User→Ku edge | `(User)-[:MASTERED {mastery_score}]->(PathStep)` |
| **Path enrollment** | User→LearningPath edge | `(User)-[:ENROLLED_IN {enrolled_at, status}]->(LearningPath)` |
| **Life-path designation** | User→LearningPath edge | `(User)-[:ULTIMATE_PATH {designated_at, alignment_score}]->(LearningPath)` |

Organization is shared structure, not per-user: `(parent)-[:ORGANIZES {order}]->(child)`.

## Key Insight

**Curriculum content is global, but user interaction is personal.**

The content (Ku, PathStep, LearningPath) is shared across all users, but each user's progress,
mastery, and preferences are stored in relationships TO that content.
