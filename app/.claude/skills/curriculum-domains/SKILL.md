# Curriculum Domains Skill

> Use when building features for KU (Knowledge Units), LS (Learning Steps), LP (Learning Paths), or MOC (Maps of Content).

## When to Use This Skill

- Adding new features to any Curriculum Domain
- Understanding how KU, LS, LP, MOC differ from Activity Domains
- Implementing service methods for curriculum content
- Working with shared (non-user-owned) content
- Building learning path validation or adaptive sequencing
- Understanding factory patterns for curriculum sub-services

## The 4 Curriculum Domains

Four grouping patterns for organizing knowledge - different perspectives on the same content:

| Domain | Prefix | Topology | Purpose | Sub-services | Factory |
|--------|--------|----------|---------|--------------|---------|
| **KU** | `ku:` | Point | Atomic knowledge content | 8 | Specialized (`create_ku_sub_services`) |
| **LS** | `ls:` | Edge | Sequential learning steps | 4 | Generic (`create_curriculum_sub_services`) |
| **LP** | `lp:` | Path | Complete learning sequences | 5 | Specialized (`create_lp_sub_services`) |
| **MOC** | `moc:` | Graph | Non-linear navigation maps | 8 | **Manual** (circular deps) |

## Key Difference from Activity Domains

**Curriculum content is SHARED, not user-owned:**

```python
# Activity Domains - user ownership
_user_ownership_relationship = "OWNS"  # Multi-tenant security

# Curriculum Domains - shared content
_user_ownership_relationship = None  # Global access
```

This means:
- No ownership verification on CRUD operations
- Content created by TEACHER+ roles, consumed by all
- User progress tracked via separate relationships (MASTERED, ENROLLED, etc.)

## Architecture Overview

```
UniversalNeo4jBackend[T]     <- ONE instance per domain (no wrappers)
        |
        v
Factory / Manual             <- Creates sub-services
        |
        v
    {Domain}Service          <- Facade with explicit delegation methods
        |
        v
    Sub-services             <- core, search, intelligence, relationships
```

**Key Patterns:**
- **Factory pattern** - KU, LS, LP use factory functions for sub-service creation
- **Manual creation** - MOC uses manual creation due to circular dependencies
- **Internal intelligence** - ALL domains create intelligence services internally
- **BaseService inheritance** - All core/search services extend BaseService

## Factory Functions

| Domain | Factory | Location |
|--------|---------|----------|
| **KU** | `create_ku_sub_services()` | `core/utils/curriculum_domain_config.py` |
| **LS** | `create_curriculum_sub_services()` | `core/utils/curriculum_domain_config.py` |
| **LP** | `create_lp_sub_services()` | `core/utils/curriculum_domain_config.py` |
| **MOC** | Manual in `__init__()` | `core/services/moc_service.py` |

## Common Operations

### Get knowledge with context
```python
result = await ku_service.intelligence.get_ku_with_context(uid)
```

### Check learning step readiness
```python
result = await ls_service.intelligence.is_ready(ls_uid, completed_step_uids)
```

### Validate learning path
```python
result = await lp_service.intelligence.validate_path_prerequisites(lp_uid)
```

### Get MOC navigation
```python
result = await moc_service.intelligence.suggest_navigation(moc_uid, user_context)
```

### Create with factory (LS example)
```python
from core.utils.curriculum_domain_config import create_curriculum_sub_services

common = create_curriculum_sub_services(
    domain="ls",
    backend=ls_backend,
    graph_intel=graph_intelligence_service,
    event_bus=event_bus,
)
self.core = common.core
self.search = common.search
self.relationships = common.relationships
self.intelligence = common.intelligence
```

## Deep Dive Resources

**Architecture:**
- [CURRICULUM_GROUPING_PATTERNS.md](/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md) - Three grouping patterns (KU, LS, LP)
- [ADR-023](/docs/decisions/ADR-023-curriculum-baseservice-migration.md) - Curriculum BaseService migration
- [FOURTEEN_DOMAIN_ARCHITECTURE.md](/docs/architecture/FOURTEEN_DOMAIN_ARCHITECTURE.md) - Complete domain architecture

**Intelligence:**
- [KU_INTELLIGENCE.md](/docs/intelligence/KU_INTELLIGENCE.md) - KU intelligence guide
- [LS_INTELLIGENCE.md](/docs/intelligence/LS_INTELLIGENCE.md) - LS intelligence guide
- [LP_INTELLIGENCE.md](/docs/intelligence/LP_INTELLIGENCE.md) - LP intelligence guide
- [MOC_INTELLIGENCE.md](/docs/intelligence/MOC_INTELLIGENCE.md) - MOC intelligence guide

**Patterns:**
- [OWNERSHIP_VERIFICATION.md](/docs/patterns/OWNERSHIP_VERIFICATION.md) - ContentScope.SHARED pattern

---

## Related Skills

- [activity-domains](../activity-domains/SKILL.md) - Contrast with user-owned domains
- [result-pattern](../result-pattern/SKILL.md) - All methods return `Result[T]`
- [neo4j-cypher-patterns](../neo4j-cypher-patterns/SKILL.md) - Graph queries

## Related Documentation

- `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` - Curriculum architecture
- `/docs/intelligence/KU_INTELLIGENCE.md` - KU intelligence guide
- `/docs/intelligence/LS_INTELLIGENCE.md` - LS intelligence guide
- `/docs/intelligence/LP_INTELLIGENCE.md` - LP intelligence guide
- `/docs/intelligence/MOC_INTELLIGENCE.md` - MOC intelligence guide
