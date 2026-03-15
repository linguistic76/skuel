# Curriculum Domains Skill

> Use when building features for Lesson (teaching compositions), KU (atomic knowledge units), LS (Learning Steps), LP (Learning Paths), or MOC (Maps of Content).

## When to Use This Skill

- Adding new features to any Curriculum Domain
- Understanding how Lesson, KU, LS, LP differ from Activity Domains
- Implementing service methods for curriculum content
- Working with shared (non-user-owned) content
- Building learning path validation or adaptive sequencing
- Working with Lesson organization (non-linear navigation, MOC-style)

## The 4 Curriculum Domains

Four structural patterns for organizing knowledge:

| Domain | UID Format | Topology | Purpose | Sub-services | Factory |
|--------|-----------|----------|---------|--------------|---------|
| **Lesson** | `l_{slug}_{random}` | Composition | Teaching narrative (composes Kus) | 10 | Specialized (`create_lesson_sub_services`) |
| **KU** | `ku_{slug}_{random}` | Atom | Atomic knowledge unit (concept, principle, practice) | 4 | Generic (`create_curriculum_sub_services`) |
| **LS** | `ls:{random}` | Edge | Sequential learning steps | 4 | Generic (`create_curriculum_sub_services`) |
| **LP** | `lp:{random}` | Path | Complete learning sequences | 5 | Specialized (`create_lp_sub_services`) |

**Composition:** `(Lesson)-[:USES_KU]->(Ku)` — Lessons compose atomic Kus into narrative. `(Ls)-[:TRAINS_KU]->(Ku)` — Learning steps train specific Kus.

**Note on MOC:** MOC (Map of Content) is NOT a separate domain or EntityType. Any Entity with outgoing `ORGANIZES` relationships IS an organizer. This emergent identity is managed via `LessonOrganizationService` — a sub-service of `LessonService`. See `core/services/lesson/lesson_organization_service.py`.

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
- **Factory pattern** - Lesson, LS, LP use factory functions for sub-service creation
- **Internal intelligence** - ALL domains create intelligence services internally
- **BaseService inheritance** - All core/search services extend BaseService with `_config = create_curriculum_domain_config(...)`
- **Lesson Organization** - Non-linear navigation via `ORGANIZES` relationships (replaces old MOC domain)

## Factory Functions

| Domain | Factory | Location |
|--------|---------|----------|
| **Lesson** | `create_lesson_sub_services()` | `core/utils/curriculum_domain_config.py` |
| **LS** | `create_curriculum_sub_services()` | `core/utils/curriculum_domain_config.py` |
| **LP** | `create_lp_sub_services()` | `core/utils/curriculum_domain_config.py` |

## Model Locations

| Domain | Directory | Model | DTO |
|--------|-----------|-------|-----|
| **Lesson** | `core/models/lesson/` | `article.py` (extends Curriculum) | `article_dto.py` |
| **KU** | `core/models/ku/` | `ku.py` (extends Entity) | `ku_dto.py` |
| **LS** | `core/models/pathways/` | `learning_step.py` | `learning_step_dto.py` |
| **LP** | `core/models/pathways/` | `learning_path.py` | `learning_path_dto.py` |
| **Base** | `core/models/` | `curriculum.py` | `curriculum_dto.py` |

## Common Operations

### Get knowledge with context
```python
result = await lesson_service.intelligence.get_article_with_context(uid)
```

### Check learning step readiness
```python
result = await ls_service.intelligence.is_ready(ls_uid, completed_step_uids)
```

### Validate learning path
```python
result = await lp_service.intelligence.validate_path_prerequisites(lp_uid)
```

### Lesson Organization (non-linear navigation)
```python
# Organize Lessons into a non-linear map
await lesson_service.organize_article(parent_uid, child_uid, order=1, importance="core")
await lesson_service.get_organized_children(parent_uid, depth=1)
await lesson_service.get_parent_articles(article_uid)  # Multiple parents possible
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
- [CURRICULUM_GROUPING_PATTERNS.md](/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md) - Four grouping patterns (Lesson, KU, LS, LP)
- [ADR-023](/docs/decisions/ADR-023-curriculum-baseservice-migration.md) - Curriculum BaseService migration
- [ENTITY_TYPE_ARCHITECTURE.md](/docs/architecture/ENTITY_TYPE_ARCHITECTURE.md) - Complete domain architecture

**Patterns:**
- [OWNERSHIP_VERIFICATION.md](/docs/patterns/OWNERSHIP_VERIFICATION.md) - ContentScope.SHARED pattern

---

## Related Skills

- [activity-domains](../activity-domains/SKILL.md) - Contrast with user-owned domains
- [result-pattern](../result-pattern/SKILL.md) - All methods return `Result[T]`
- [neo4j-cypher-patterns](../neo4j-cypher-patterns/SKILL.md) - Graph queries

## Related Documentation

- `/docs/architecture/CURRICULUM_GROUPING_PATTERNS.md` - Curriculum architecture
- `/docs/domains/moc.md` - MOC as emergent identity (ORGANIZES pattern)
