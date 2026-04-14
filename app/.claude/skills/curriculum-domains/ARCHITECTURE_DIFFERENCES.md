# Curriculum vs Activity Domain Architecture

> Key architectural differences between Curriculum Domains (Ku, PathStep, LearningPath) and Activity Domains (Tasks, Goals, etc.).

## Ownership Model

| Aspect | Activity Domains | Curriculum Domains |
|--------|------------------|-------------------|
| **Ownership** | User-owned | Shared global content |
| **Relationship** | `_user_ownership_relationship = "OWNS"` | `_user_ownership_relationship = None` |
| **Creation** | Any authenticated user | TEACHER+ roles only |
| **Access** | Owner only (multi-tenant) | All users |
| **Filtering** | Always by `user_uid` | No user filter |

## Sub-service Creation Patterns

### Activity Domains — Generic Factory

The 6 Activity Domains (Tasks, Goals, Habits, Events, Choices, Principles) use a single generic factory:

```python
from core.services.activity_domain_config import create_common_sub_services

common = create_common_sub_services(
    domain="tasks",
    backend=backend,
    graph_intel=graph_intel,
    event_bus=event_bus,
)
self.core = common.core
self.search = common.search
self.relationships = common.relationships
self.intelligence = common.intelligence
```

### Curriculum Domains — Three Factory Patterns

| Domain | Pattern | Factory Function |
|--------|---------|-----------------|
| **KU** | Generic factory (4 services) | `create_curriculum_sub_services("ku", ...)` |
| **PS** | Specialized factory (12 services) | `create_ps_sub_services()` |
| **LP** | Specialized factory (5 services) | `create_lp_sub_services()` |

```python
# KU — generic factory
from core.services.curriculum_domain_config import create_curriculum_sub_services
common = create_curriculum_sub_services(domain="ku", backend=ku_backend, ...)

# PS — specialized factory (handles circular core <-> intelligence dependency)
from core.services.curriculum_domain_config import create_ps_sub_services
subs = create_ps_sub_services(backend=ps_backend, graph_intel=graph_intel, ...)

# LP — specialized factory (requires cross-domain PsService dependency)
from core.services.curriculum_domain_config import create_lp_sub_services
subs = create_lp_sub_services(backend=lp_backend, ps_service=ps_service, ...)
```

**Note on MOC:** There is no `MocService`. MOC identity is emergent — any Entity with outgoing `ORGANIZES` relationships is an organizer. For PathSteps this is managed by `PsOrganizationService` (sub-service of `PsService`).

## Intelligence Service Patterns

| Domain Type | Intelligence Creation | Where |
|-------------|----------------------|-------|
| **Activity (6)** | Generic factory | `create_common_sub_services()` |
| **KU** | Generic factory | `create_curriculum_sub_services()` |
| **PS** | Specialized factory (BEFORE core) | `create_ps_sub_services()` |
| **LP** | Specialized factory | `create_lp_sub_services()` |

**Key Difference:** `create_ps_sub_services` creates `PsIntelligenceService` BEFORE `PsCoreService` due to a circular dependency (core depends on intelligence for content analysis).

## Sub-service Count Comparison

| Domain | Sub-services | Factory Type | Complexity |
|--------|--------------|--------------|------------|
| **Tasks** | 7 | Generic | Medium-High |
| **Goals** | 9 | Generic | Medium |
| **Habits** | 8 | Generic | Medium |
| **Events** | 7 | Generic | Medium |
| **Choices** | 4 | Generic | Medium |
| **Principles** | 7 | Generic | Medium |
| **KU** | 4 | Generic | **Lowest** (atomic reference) |
| **PS (PathStep)** | 12 (+ optional `ai`) | Specialized | **Highest** (core, search, graph, semantic, practice, mastery, adaptive, application discovery, context, organization, intelligence, progress) |
| **LP** | 5 | Specialized | Medium (validation, adaptive) |

## Relationship Service Patterns

**Both domain types use `UnifiedRelationshipService`:**

```python
# Activity Domains
from core.models.relationship_registry import TASKS_CONFIG
from core.services.relationships import UnifiedRelationshipService
self.relationships = UnifiedRelationshipService(backend, TASKS_CONFIG, graph_intel)

# Curriculum Domains (PathStep)
from core.models.relationship_registry import PS_CONFIG
self.relationships = UnifiedRelationshipService(backend, PS_CONFIG, graph_intel)
```

**Direct backend calls for complex queries:**
```python
# Domain-specific Cypher lives in domain backends, not services.
# PsBackend.get_with_context_raw() fetches full graph neighborhood:
result = await self.backend.get_with_context_raw(uid, min_confidence)
# KuBackend.get_usage_summary() counts PathSteps using this Ku, MOC children, etc.:
result = await self.backend.get_usage_summary(ku_uid)
```

## BaseService Usage

Both domain types extend `BaseService[Backend, Model]`:

```python
# Activity Domain — with ownership
class TasksSearchService(BaseService[TasksOperations, Task]):
    _user_ownership_relationship = "OWNS"
    _supports_user_progress = True

# Curriculum Domain — shared content
class PsSearchService(BaseService[BackendOperations[PathStep], PathStep]):
    _user_ownership_relationship = None    # Shared content
    _supports_user_progress = True          # Still tracks per-user progress
```

## Per-User Data in Curriculum

Even though content is shared, Curriculum Domains track per-user data:

| Data Type | Storage | Example |
|-----------|---------|---------|
| **Learning state** | User→PathStep relationship | `(User)-[:IN_PROGRESS]->(PathStep)` / `:MASTERED` / `:BOOKMARKED` |
| **Completion progress** | User→PathStep mastery edge | `(User)-[:MASTERED {level: 0.8}]->(PathStep)` |
| **Path enrollment** | User→LearningPath relationship | `(User)-[:ENROLLED {progress: 0.6}]->(LearningPath)` |
| **Organization (MOC)** | PathStep→PathStep relationship | `(PathStep)-[:ORGANIZES {order, importance}]->(PathStep)` |

## Circular Dependencies

| Domain | Circular Dependency | Resolution |
|--------|---------------------|------------|
| **PS (PathStep)** | Core ↔ Intelligence | Create intelligence BEFORE core in factory |
| **KU** | None | Simple construction |
| **LP** | None | Standard factory order (but requires PsService injected) |

## Key Insight

**Curriculum content is global, but user interaction is personal.**

The content (Ku, PathStep, LearningPath) is shared across all users, but each user's progress, mastery, and preferences are stored in relationships TO that content.

**Factory Complexity Hierarchy:**
```
Generic Factory (KU) → Specialized Factories (PS, LP)
       ↓                           ↓
 Simple, uniform           Custom dependencies (circular; cross-domain)
```
