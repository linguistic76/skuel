# Curriculum vs Activity Domain Architecture

> Key architectural differences between Curriculum Domains (KU, LS, LP, MOC) and Activity Domains (Tasks, Goals, etc.).

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

All 6 Activity Domains use a single generic factory:

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

### Curriculum Domains - Mixed Patterns

Curriculum uses **three different patterns**:

| Domain | Pattern | Factory Function |
|--------|---------|-----------------|
| **KU** | Specialized factory | `create_ku_sub_services()` |
| **LS** | Generic factory | `create_curriculum_sub_services()` |
| **LP** | Specialized factory | `create_lp_sub_services()` |
| **MOC** | **Manual** | None (circular deps) |

```python
# KU - Specialized factory (handles circular core↔intelligence dependency)
from core.utils.curriculum_domain_config import create_ku_sub_services
subs = create_ku_sub_services(backend=repo, graph_intel=graph_intel, ...)

# LS - Generic factory (simple 4-service pattern)
from core.utils.curriculum_domain_config import create_curriculum_sub_services
common = create_curriculum_sub_services(domain="ls", backend=ls_backend, ...)

# LP - Specialized factory (requires cross-domain LsService dependency)
from core.utils.curriculum_domain_config import create_lp_sub_services
subs = create_lp_sub_services(driver=driver, ls_service=ls_service, ...)

# MOC - Manual creation (core↔section circular dependency)
class MocService:
    def __init__(self, backend, driver, ...):
        self.section = MocSectionService(backend, driver, core_service=None)
        self.core = MocCoreService(backend, driver, section_service=self.section)
        self.section.core_service = self.core  # Post-init wiring
```

## Intelligence Service Patterns

| Domain Type | Intelligence Creation | Where |
|-------------|----------------------|-------|
| **Activity (6)** | Factory | `create_common_sub_services()` |
| **KU** | Specialized factory (BEFORE core) | `create_ku_sub_services()` |
| **LS** | Generic factory | `create_curriculum_sub_services()` |
| **LP** | Specialized factory | `create_lp_sub_services()` |
| **MOC** | Manual in `__init__()` | `MocService.__init__()` |

**Key Difference:** KU creates intelligence BEFORE core due to circular dependency (core depends on intelligence for content analysis).

## Sub-service Count Comparison

| Domain | Sub-services | Factory Type | Complexity |
|--------|--------------|--------------|------------|
| **Tasks** | 7 | Generic | Medium-High |
| **Goals** | 5 | Generic | Medium |
| **Habits** | 6 | Generic | Medium |
| **Events** | 5 | Generic | Medium |
| **Choices** | 6 | Generic | Medium |
| **Principles** | 7 | Generic | Medium |
| **KU** | 8 | Specialized | **High** (semantic, practice, interaction) |
| **LS** | 4 | Generic | **Lowest** (minimal design) |
| **LP** | 5 | Specialized | Medium (validation, adaptive) |
| **MOC** | 8 | **Manual** | High (circular deps, dual relationships) |

## Relationship Service Patterns

**Both domain types use `UnifiedRelationshipService`:**

```python
# Activity Domains
from core.models.relationship_registry import TASKS_CONFIG
from core.services.relationships import UnifiedRelationshipService
self.relationships = UnifiedRelationshipService(backend, TASKS_CONFIG, graph_intel)

# Curriculum Domains
from core.models.relationship_registry import KU_CONFIG
self.relationships = UnifiedRelationshipService(backend, KU_CONFIG, graph_intel)
```

**MOC Special Case** - Uses KU config (MOC is KU with ORGANIZES):
```python
from core.models.relationship_registry import KU_CONFIG
self.relationships = UnifiedRelationshipService(backend, KU_CONFIG, graph_intel)
```

**Direct Driver for Complex Queries:**
```python
# When UnifiedRelationshipService doesn't fit
async def get_semantic_neighborhood(self, ku_uid: str) -> Result[dict]:
    query = """
    MATCH (ku:Curriculum {uid: $uid})-[r]-(related)
    WHERE type(r) IN ['REQUIRES_KNOWLEDGE', 'ENABLES', 'HAS_NARROWER', 'RELATED_TO']
    RETURN related.uid, type(r), labels(related)
    """
    result = await self.backend.driver.execute_query(query, {"uid": ku_uid})
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
| **Mastery level** | User→KU relationship | `(User)-[:MASTERED {level: 0.8}]->(Curriculum)` |
| **Completion** | User→LS relationship | `(User)-[:COMPLETED]->(Ls)` |
| **Progress** | User→LP relationship | `(User)-[:ENROLLED {progress: 0.6}]->(Lp)` |
| **Bookmarks** | User→MOC relationship | `(User)-[:BOOKMARKED]->(Moc)` |

## Circular Dependencies

| Domain | Circular Dependency | Resolution |
|--------|---------------------|------------|
| **KU** | Core ↔ Intelligence | Create intelligence BEFORE core in factory |
| **MOC** | Core ↔ Section | Create section with `core_service=None`, wire after core creation |
| **LS/LP** | None | Standard factory order |

## Key Insight

**Curriculum content is global, but user interaction is personal.**

The content (KU, LS, LP, MOC) is shared across all users, but each user's progress, mastery, and preferences are stored in relationships TO that content.

**Factory Complexity Hierarchy:**
```
Generic Factory (LS) → Specialized Factory (KU, LP) → Manual Creation (MOC)
        ↓                       ↓                            ↓
   Simple, uniform        Custom dependencies         Circular deps
```
