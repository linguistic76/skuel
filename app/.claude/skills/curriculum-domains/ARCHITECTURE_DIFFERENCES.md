# Curriculum vs Activity Domain Architecture

> Key architectural differences between Curriculum Domains (Article, KU, LS, LP, MOC) and Activity Domains (Tasks, Goals, etc.).

## Ownership Model

| Aspect | Activity Domains | Curriculum Domains |
|--------|------------------|-------------------|
| **Ownership** | User-owned | Shared global content |
| **Relationship** | `_user_ownership_relationship = "OWNS"` | `_user_ownership_relationship = None` |
| **Creation** | Any authenticated user | TEACHER+ roles only |
| **Access** | Owner only (multi-tenant) | All users |
| **Filtering** | Always by `user_uid` | No user filter |

## Sub-service Creation Patterns

### Activity Domains - Generic Factory

The 5 Activity Domains (Tasks, Goals, Habits, Choices, Principles) plus Events (Scheduling/Integration domain) use a single generic factory:

```python
# Uses create_common_sub_services() for ALL activity domains
from core.utils.activity_domain_config import create_common_sub_services

common = create_common_sub_services(
    domain="tasks",
    backend=backend,
    graph_intel=graph_intelligence_service,
    event_bus=event_bus,
)
self.core = common.core
self.search = common.search
self.relationships = common.relationships
self.intelligence = common.intelligence
```

### Curriculum Domains - Three Factory Patterns

| Domain | Pattern | Factory Function |
|--------|---------|-----------------|
| **Article** | Specialized factory | `create_article_sub_services()` |
| **KU** | No factory (2 services) | — |
| **LS** | Generic factory | `create_curriculum_sub_services()` |
| **LP** | Specialized factory | `create_lp_sub_services()` |

```python
# Article - Specialized factory (handles circular core<->intelligence dependency)
from core.utils.curriculum_domain_config import create_article_sub_services
subs = create_article_sub_services(backend=repo, graph_intel=graph_intel, ...)

# LS - Generic factory (simple 4-service pattern)
from core.utils.curriculum_domain_config import create_curriculum_sub_services
common = create_curriculum_sub_services(domain="ls", backend=ls_backend, ...)

# LP - Specialized factory (requires cross-domain LsService dependency)
from core.utils.curriculum_domain_config import create_lp_sub_services
subs = create_lp_sub_services(driver=driver, ls_service=ls_service, ...)
```

**Note on MOC:** There is no `MocService`. MOC identity is emergent — any Entity with outgoing `ORGANIZES` relationships is an organizer. This is managed by `ArticleOrganizationService` (sub-service of `ArticleService`).

## Intelligence Service Patterns

| Domain Type | Intelligence Creation | Where |
|-------------|----------------------|-------|
| **Activity (6)** | Factory | `create_common_sub_services()` |
| **Article** | Specialized factory (BEFORE core) | `create_article_sub_services()` |
| **KU** | None (lightweight) | — |
| **LS** | Generic factory | `create_curriculum_sub_services()` |
| **LP** | Specialized factory | `create_lp_sub_services()` |

**Key Difference:** Article creates intelligence BEFORE core due to circular dependency (core depends on intelligence for content analysis).

## Sub-service Count Comparison

| Domain | Sub-services | Factory Type | Complexity |
|--------|--------------|--------------|------------|
| **Tasks** | 7 | Generic | Medium-High |
| **Goals** | 9 | Generic | Medium |
| **Habits** | 8 | Generic | Medium |
| **Events** | 7 | Generic | Medium |
| **Choices** | 4 | Generic | Medium |
| **Principles** | 7 | Generic | Medium |
| **Article** | 10 | Specialized | **High** (semantic, practice, organization, adaptive) |
| **KU** | 2 | None | **Lowest** (atomic reference) |
| **LS** | 4 | Generic | Low (minimal design) |
| **LP** | 5 | Specialized | Medium (validation, adaptive) |

## Relationship Service Patterns

**Both domain types use `UnifiedRelationshipService`:**

```python
# Activity Domains
from core.models.relationship_registry import TASKS_CONFIG
from core.services.relationships import UnifiedRelationshipService
self.relationships = UnifiedRelationshipService(backend, TASKS_CONFIG, graph_intel)

# Curriculum Domains
from core.models.relationship_registry import ARTICLE_CONFIG
self.relationships = UnifiedRelationshipService(backend, ARTICLE_CONFIG, graph_intel)
```

**MOC Special Case** - Uses Article config (MOC is Article with ORGANIZES):
```python
from core.models.relationship_registry import ARTICLE_CONFIG
self.relationships = UnifiedRelationshipService(backend, ARTICLE_CONFIG, graph_intel)
```

**Direct Driver for Complex Queries:**
```python
# When UnifiedRelationshipService doesn't fit
async def get_semantic_neighborhood(self, article_uid: str) -> Result[dict]:
    query = """
    MATCH (a:Article {uid: $uid})-[r]-(related)
    WHERE type(r) IN ['REQUIRES_KNOWLEDGE', 'ENABLES', 'HAS_NARROWER', 'RELATED_TO']
    RETURN related.uid, type(r), labels(related)
    """
    result = await self.backend.driver.execute_query(query, {"uid": article_uid})
    return Result.ok(self._parse_neighborhood(result.records))
```

## BaseService Usage

Both domain types extend `BaseService[Backend, Model]`:

```python
# Activity Domain - with ownership
class TasksSearchService(BaseService[TasksOperations, Task]):
    _user_ownership_relationship = "OWNS"
    _supports_user_progress = True

# Curriculum Domain - shared content
class LsSearchService(BaseService[BackendOperations[Ls], Ls]):
    _user_ownership_relationship = None  # Shared content
    _supports_user_progress = True  # Still tracks per-user progress
```

## Per-User Data in Curriculum

Even though content is shared, Curriculum Domains track per-user data:

| Data Type | Storage | Example |
|-----------|---------|---------|
| **Mastery level** | User→Article relationship | `(User)-[:MASTERED {level: 0.8}]->(Article)` |
| **Completion** | User→LS relationship | `(User)-[:COMPLETED]->(Ls)` |
| **Progress** | User→LP relationship | `(User)-[:ENROLLED {progress: 0.6}]->(Lp)` |
| **Organization** | Article→Article relationship | `(Article)-[:ORGANIZES {order, importance}]->(Article)` |

## Circular Dependencies

| Domain | Circular Dependency | Resolution |
|--------|---------------------|------------|
| **Article** | Core ↔ Intelligence | Create intelligence BEFORE core in factory |
| **KU** | None | Simple construction |
| **LS/LP** | None | Standard factory order |

## Key Insight

**Curriculum content is global, but user interaction is personal.**

The content (Article, KU, LS, LP, MOC) is shared across all users, but each user's progress, mastery, and preferences are stored in relationships TO that content.

**Factory Complexity Hierarchy:**
```
No Factory (KU) → Generic Factory (LS) → Specialized Factory (Article, LP)
        ↓                    ↓                           ↓
   Simplest            Simple, uniform           Custom dependencies
```
