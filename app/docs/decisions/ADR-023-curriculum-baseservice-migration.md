---
title: ADR-023: Unified BaseService Architecture
updated: 2026-01-06
status: accepted
category: decisions
tags: [adr, decisions, baseservice, unified-architecture, search, curriculum]
related: [ADR-014-unified-ingestion.md, ADR-017-relationship-service-unification.md]
---

# ADR-023: Unified BaseService Architecture

**Status:** Accepted

**Date:** 2026-01-05

**Decision Type:** Pattern/Practice

**Related ADRs:**
- Related to: ADR-014 (Unified Ingestion), ADR-017 (Relationship Service Unification)

---

## Context

**What was the issue?**

SKUEL had two base service classes:
- `BaseService[B, T]` - Used by Activity Domains (Tasks, Goals, Habits, Events, Choices, Principles)
- `CurriculumBaseService[B, T]` - Extended BaseService for Curriculum Domains (KU, LS, LP) and MOC (Content/Organization)

This created:
1. **Artificial separation** - Activity and Curriculum domains treated as different categories
2. **EntityType categorization methods** - `is_activity_domain()`, `is_curriculum_domain()`, etc.
3. **Cognitive overhead** - Two inheritance patterns to understand
4. **Limited cross-domain features** - Activity domains couldn't use curriculum methods

**User's Goals:**
1. Simplify codebase - reduce cognitive load
2. Enable cross-domain features - activities can use curriculum features and vice versa
3. Flatten EntityType enum - remove categorization methods
4. Philosophical alignment - all 14 domains as peers, not two categories

---

## Decision

**Merge CurriculumBaseService into BaseService and eliminate domain categorization.**

### Implementation Phases

**Phase 1: Merge CurriculumBaseService methods into BaseService**

Added curriculum configuration class attributes to BaseService:
```python
class BaseService[B, T](Generic[B, T]):
    # Curriculum configuration (empty by default for Activity Domains)
    _prerequisite_relationships: ClassVar[list[str]] = []
    _enables_relationships: ClassVar[list[str]] = []
    _content_field: str = "content"
    _mastery_threshold: float = 0.7
    _supports_user_progress: bool = False
```

Added curriculum methods to BaseService:
- `get_prerequisites(uid, depth)` - Traverse prerequisite chain
- `get_enables(uid, depth)` - Find what entity enables
- `add_prerequisite(entity_uid, prerequisite_uid, confidence)`
- `get_hierarchy(uid)` - Hierarchical position
- `get_user_progress(user_uid, entity_uid)` - Mastery tracking
- `update_user_mastery(user_uid, entity_uid, mastery_level)`
- `get_with_content(uid)` - Entity with full content
- `get_with_context(uid, depth)` - Entity with graph neighborhood

**Phase 2: Migrate curriculum search services to BaseService**

Search services now inherit from BaseService:
```python
class LsSearchService(BaseService["LsUniversalBackend", Ls]):
    _supports_user_progress = True

class LpSearchService(BaseService["LpUniversalBackend", Lp]):
    _supports_user_progress = True
```

**Phase 2b: Migrate curriculum core services to BaseService (January 2026)**

Core services now also inherit from BaseService, sharing backends with search:
```python
class LsCoreService(BaseService["BackendOperations[Ls]", Ls]):
    _user_ownership_relationship = None  # Shared curriculum content
    # Accesses driver via self.backend.driver for specialized queries

class LpCoreService(BaseService["BackendOperations[Lp]", Lp]):
    _user_ownership_relationship = None  # Shared curriculum content
    # Accesses driver via self.backend.driver for specialized queries
```

Facades create shared backends using `UniversalNeo4jBackend[T]` directly:
```python
# LsService facade - uses UniversalNeo4jBackend directly (no wrapper)
ls_backend = UniversalNeo4jBackend[Ls](driver, NeoLabel.LS, Ls)
self.core = LsCoreService(backend=ls_backend, event_bus=event_bus)
self.search = LsSearchService(backend=ls_backend)

# LpService facade - uses UniversalNeo4jBackend directly (no wrapper)
lp_backend = UniversalNeo4jBackend[Lp](driver, NeoLabel.LP, Lp)
self.core = LpCoreService(backend=lp_backend, ls_service=ls_service, event_bus=event_bus)
self.search = LpSearchService(backend=lp_backend)

# MocService facade - uses UniversalNeo4jBackend directly (no wrapper)
moc_backend = UniversalNeo4jBackend[MapOfContent](driver, NeoLabel.MOC, MapOfContent)
self.search = MocSearchService(backend=moc_backend, discovery_service=self.discovery)
```

**Phase 2c: Delete curriculum backend wrappers (January 2026)**

Removed three wrapper backend files (~2,000 lines total):
- `adapters/persistence/neo4j/ls_backend.py` (590 lines) - DELETED
- `adapters/persistence/neo4j/lp_backend.py` (748 lines) - DELETED
- `adapters/persistence/neo4j/moc_backend.py` (679 lines) - DELETED

These were thin wrappers around `UniversalNeo4jBackend[T]` that added no real value.
Per "One Path Forward", services now use `UniversalNeo4jBackend[T]` directly.

**Phase 3: Delete CurriculumBaseService**

Removed `/core/services/curriculum_base_service.py` (819 lines deleted).

**Phase 4: Flatten EntityType enum**

Removed categorization methods from EntityType:
- `is_activity_domain()` - DELETED
- `is_curriculum_domain()` - DELETED
- `is_content_org_domain()` - DELETED
- `is_meta_domain()` - DELETED
- `all_activity_types()` - DELETED
- `all_curriculum_types()` - DELETED
- `all_content_org_types()` - DELETED
- `all_cross_cutting_types()` - DELETED

Kept essential methods:
- `is_lifepath()` - Still needed for destination domain
- `get_canonical()` - Alias normalization
- `from_string()` - DSL parsing

**Phase 5: Update DSL Parser**

Removed category helper methods from ParsedActivityLine and ParsedJournal:
- `is_activity_domain()`, `is_curriculum_domain()`, `is_meta_domain()` - DELETED
- `get_activity_domain_items()`, `get_curriculum_domain_items()`, `get_meta_domain_items()` - DELETED

---

## Alternatives Considered

### Alternative 1: Keep CurriculumBaseService separate

**Pros:**
- No migration effort

**Cons:**
- Maintains artificial distinction
- Limits cross-domain features
- Higher cognitive load

**Why rejected:** Violates "One Path Forward" and user's goal of unified architecture.

### Alternative 2: Keep EntityType categorization methods

**Pros:**
- Backward compatibility

**Cons:**
- Reinforces mental model of "two types of domains"
- Code that uses these methods perpetuates the distinction

**Why rejected:** User explicitly requested philosophical alignment where all domains are peers.

---

## Consequences

### Positive Consequences
- **Unified architecture** - One BaseService for all 14 domains
- **Cross-domain features** - Any domain can use prerequisite/enables/mastery tracking
- **Massive code reduction** - ~2,800+ lines deleted:
  - 819 lines: CurriculumBaseService
  - 590 lines: ls_backend.py
  - 748 lines: lp_backend.py
  - 679 lines: moc_backend.py
- **Protocol cleanup** - 11 unused protocols removed (4 dead + 7 orphaned)
- **Flattened EntityType** - No more categorization methods
- **Cognitive simplicity** - One pattern to understand

### Negative Consequences
- **No backward compatibility** - Code using deleted methods needs update
- **All domains now load curriculum methods** - Slight overhead for Activity Domains

### Neutral Consequences
- **Configuration-based behavior** - Domains opt-in to features via class attributes

---

## Implementation Details

### Code Location

**Deleted Files:**
- `core/services/curriculum_base_service.py` (819 lines)
- `adapters/persistence/neo4j/ls_backend.py` (590 lines) - January 2026
- `adapters/persistence/neo4j/lp_backend.py` (748 lines) - January 2026
- `adapters/persistence/neo4j/moc_backend.py` (679 lines) - January 2026

**Deleted Protocols (ku_protocols.py) - January 2026:**
- `LearningOperations` - Dead code (type hint was wrong)
- `LearningQueryOperations` - Unused legacy protocol
- `ContentOperations` - Aspirational (never properly implemented)
- `ContentQueryOperations` - Unused legacy protocol

**Deleted Protocol Helper Classes (domain_protocols.py) - January 2026:**
- `HasModelDump`, `HasDict` (duplicate), `HasValue`, `HasStatus`
- `HasInsights`, `HasTimestamps`, `HasCreatedBy` (7 orphaned protocols)

**Modified Files:**
- `core/services/base_service.py` - Added curriculum methods (~270 lines)
- `core/services/ku/ku_core_service.py` - Changed inheritance to BaseService
- `core/services/ls/ls_core_service.py` - Changed inheritance to BaseService (January 2026)
- `core/services/ls/ls_search_service.py` - Changed inheritance to BaseService
- `core/services/ls_service.py` - Updated to use UniversalNeo4jBackend directly (January 2026)
- `core/services/lp/lp_core_service.py` - Changed inheritance to BaseService (January 2026)
- `core/services/lp/lp_search_service.py` - Changed inheritance to BaseService
- `core/services/lp_service.py` - Updated to use UniversalNeo4jBackend directly (January 2026)
- `core/services/moc_service.py` - Updated to use UniversalNeo4jBackend directly (January 2026)
- `core/services/moc/moc_search_service.py` - Changed inheritance to BaseService
- `core/models/enums/entity_enums.py` - Removed categorization methods
- `core/services/dsl/activity_dsl_parser.py` - Removed category helper methods
- `core/services/protocols/__init__.py` - Removed deleted protocol exports (January 2026)
- `core/services/protocols/ku_protocols.py` - Removed 4 dead protocols (January 2026)
- `core/services/protocols/domain_protocols.py` - Removed 7 orphaned protocols (January 2026)
- `core/utils/services_bootstrap.py` - Fixed wrong type hints (January 2026)

### Class Attribute Configuration

Services configure inherited behavior via class attributes:

```python
class LsSearchService(BaseService["LsUniversalBackend", Ls]):
    # Required - DTO and model classes
    _dto_class = LearningStepDTO
    _model_class = Ls

    # Search configuration
    _search_fields: ClassVar[list[str]] = ["title", "intent", "description"]
    _search_order_by: str = "updated_at"

    # Curriculum features (opt-in via configuration)
    _content_field: str = "description"
    _mastery_threshold: float = 0.7
    _supports_user_progress: bool = True  # Enable mastery tracking
    _prerequisite_relationships: ClassVar[list[str]] = ["REQUIRES_STEP", "REQUIRES_KNOWLEDGE"]
    _enables_relationships: ClassVar[list[str]] = ["ENABLES_STEP", "ENABLES_LEARNING"]

    # Graph enrichment for faceted search
    _graph_enrichment_patterns: ClassVar[list[tuple[str, str, str, str]]] = [
        ("CONTAINS_KNOWLEDGE", "Ku", "knowledge_units", "outgoing"),
        ("HAS_STEP", "Lp", "learning_paths", "incoming"),
    ]

    # Ownership (None = shared content, no user filter)
    _user_ownership_relationship: ClassVar[str | None] = None
```

---

## Related Documentation

- **Implementation guide:** `/docs/patterns/CONFIGURATION_DRIVEN_SERVICE_ARCHITECTURE.md` - How to configure services

---

## Success Criteria

- [x] CurriculumBaseService methods merged into BaseService
- [x] All curriculum services inherit from BaseService
- [x] CurriculumBaseService file deleted
- [x] EntityType categorization methods removed
- [x] DSL parser category methods removed
- [x] All tests pass

---

## Changelog

| Date | Author | Change | Version |
|------|--------|--------|---------|
| 2026-01-05 | Claude | Initial implementation complete | 1.0 |
| 2026-01-05 | Claude | Full unification - merged CurriculumBaseService, flattened EntityType | 2.0 |
| 2026-01-06 | Claude | Phase 2b: Migrated LsCoreService and LpCoreService to BaseService | 2.1 |
| 2026-01-06 | Claude | Phase 2c: Deleted curriculum backend wrappers (~2,000 lines) | 2.2 |
| 2026-01-06 | Claude | Protocol cleanup: Removed 11 unused protocols, fixed wrong type hints | 2.3 |
| 2026-01-20 | Claude | MOC cleanup: Removed MocOperations protocol, MOC events - MOC is KU-based | 2.4 |

**NOTE (January 2026):** MOC architecture has been fully refactored. MOC is now
KU-based - a KU "is" a MOC when it has outgoing ORGANIZES relationships.
MocOperations protocol, MocFacadeProtocol, and MOC events have been removed.
See `/docs/domains/moc.md` for the current MOC architecture.
