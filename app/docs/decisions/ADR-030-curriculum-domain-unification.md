# ADR-030: Curriculum Domain Unification

**Status:** Accepted
**Date:** 2026-01-11
**Category:** Pattern/Practice

## Context

Before this unification, Curriculum domains (KU, LS, LP) and MOC (Content/Organization domain that provides navigation) had inconsistent architectures:

1. **Different numbers of sub-services:**
   - KU: 9 sub-services (highest complexity)
   - LP: 8 sub-services
   - MOC: 6 sub-services (no intelligence)
   - LS: 3 sub-services (no intelligence)

2. **Inconsistent `graph_intel` wiring:**
   - KU, LP: Correctly wired with GraphIntelligenceService
   - LS, MOC: Passed `graph_intel=None` (bug)

3. **No factory pattern:**
   - Activity domains use `create_common_sub_services()` factory
   - Curriculum domains used manual initialization

4. **Missing intelligence services:**
   - KU, LP: Had intelligence services
   - LS, MOC: No intelligence (inconsistent with Activity domains)

These inconsistencies meant:
- LS and MOC couldn't access cross-domain intelligence
- KU couldn't reliably recommend Activity domains based on UserContext
- Developer confusion about architectural patterns

## Decision

Unify all 4 Curriculum Domain facades to follow the same pattern as Activity Domains:

### 1. All domains have the same 4 common sub-services

```python
# Every Curriculum Domain facade now has:
self.core           # CRUD operations
self.search         # Discovery operations
self.relationships  # UnifiedRelationshipService
self.intelligence   # Intelligence analytics
```

### 2. `graph_intel` is REQUIRED (fail-fast)

```python
# Before (bug)
self.relationships = UnifiedRelationshipService(
    backend=backend,
    config=get_ls_config(),
    graph_intel=None,  # BUG: No cross-domain intelligence
)

# After (ADR-030)
if not graph_intel:
    raise ValueError("graph_intel is REQUIRED for curriculum domains")

self.relationships = UnifiedRelationshipService(
    backend=backend,
    config=get_ls_config(),
    graph_intel=graph_intel,  # Cross-domain intelligence enabled
)
```

### 3. Factory pattern for LS (standard signatures)

LsService uses `create_curriculum_sub_services()` factory since all its services have standard signatures:

```python
from core.utils.curriculum_domain_config import create_curriculum_sub_services

common = create_curriculum_sub_services(
    domain="ls",
    backend=ls_backend,
    graph_intel=graph_intelligence,
    event_bus=event_bus,
)
self.core = common.core
self.search = common.search
self.relationships = common.relationships
self.intelligence = common.intelligence
```

### 4. Manual init for KU, LP, MOC (non-standard signatures)

These domains have non-standard core/intelligence dependencies:
- **KU Core:** `repo, content_repo, intelligence, chunking, event_bus`
- **LP Core:** `backend, ls_service, event_bus`
- **LP Intelligence:** Standalone service (passed in from bootstrap)
- **MOC Core:** `backend, driver, section_service, event_bus`

Following TasksService pattern, these create core/intelligence manually but ensure all 4 sub-services exist:

```python
# LpService - intelligence passed in from bootstrap
def __init__(self, driver, ls_service, ..., intelligence_service=None):
    self.core = LpCoreService(backend, ls_service, event_bus)  # Manual - non-standard
    self.search = LpSearchService(backend)
    self.relationships = UnifiedRelationshipService(...)
    self.intelligence = intelligence_service  # Passed in (standalone service)
```

### 5. Created MocIntelligenceService

New service extending `BaseAnalyticsService[BackendOperations[MapOfContent], MapOfContent]`:

```python
class MocIntelligenceService(BaseAnalyticsService[...]):
    """Intelligence service for Maps of Content."""

    async def get_navigation_recommendations(self, moc_uid: str) -> Result[list[dict]]:
        """Recommend related MOCs for navigation."""

    async def get_content_coverage(self, moc_uid: str) -> Result[dict[str, int]]:
        """Calculate KU/LP coverage metrics."""

    async def calculate_bridge_strength(self, moc_uid: str) -> Result[float]:
        """Score cross-domain bridge connections (0.0-1.0)."""

    async def has_cross_domain_bridges(self, moc_uid: str) -> Result[bool]:
        """Check if MOC has cross-domain bridges."""
```

## Consequences

### Positive

1. **Cross-domain intelligence enabled for all domains:**
   - LS can now access graph queries via `self.relationships` and `self.intelligence`
   - MOC can analyze content coverage and bridge strength
   - KU can recommend Activity domains based on UserContext

2. **Consistent architecture:**
   - All 10 domain facades (6 Activity + 4 Curriculum) have `.core`, `.search`, `.relationships`, `.intelligence`
   - Developers familiar with Activity domains immediately understand Curriculum domains

3. **Factory pattern available:**
   - `create_curriculum_sub_services()` factory mirrors Activity domain pattern
   - Reduces boilerplate for domains with standard signatures

4. **Fail-fast validation:**
   - `graph_intel` is validated at initialization
   - No silent failures from missing intelligence service

### Negative

1. **Breaking change:** Services now require `graph_intel` parameter
   - Mitigated: Only affects service composition in bootstrap

2. **Factory limited to LS:** Only LsService can use the factory
   - Other domains have non-standard signatures requiring manual init
   - This matches Activity domain pattern (TasksService also creates core manually)

## Implementation

### Files Changed

| File | Change |
|------|--------|
| `/core/utils/curriculum_domain_config.py` | NEW: Factory module |
| `/core/services/moc/moc_intelligence_service.py` | NEW: MOC intelligence |
| `/core/services/ls_service.py` | Use factory, require `graph_intel` |
| `/core/services/lp_service.py` | Add `intelligence_service` param, require `graph_intel` |
| `/core/services/ku_service.py` | Require `graph_intel` |
| `/core/services/moc_service.py` | Add intelligence, require `graph_intel` |
| `/services_bootstrap.py` | Pass `graph_intel` to all curriculum domains |

### Domain Summary After Unification

| Domain | Factory | Core Signature | Intelligence | graph_intel |
|--------|---------|----------------|--------------|-------------|
| **KU** | Manual | Non-standard | Created internally | REQUIRED |
| **LS** | Factory | Standard | Created by factory | REQUIRED |
| **LP** | Manual | Non-standard | Passed in | REQUIRED |
| **MOC** | Manual | Non-standard | Created internally | REQUIRED |

## Verification

1. **Type check:** `poetry run mypy core/services/ls_service.py core/services/lp_service.py core/services/ku_service.py core/services/moc_service.py`
2. **Unit tests:** Verify all 4 curriculum services have `.intelligence` attribute
3. **Integration:** Verify LS and MOC can now access graph queries

## Related Decisions

- **ADR-023:** Curriculum BaseService Migration (core/search extend BaseService)
- **ADR-024:** BaseAnalyticsService Migration (Activity + Curriculum intelligence)
- **ADR-026:** Unified Relationship Registry (single source for all configs)
- **ADR-029:** GraphNative Service Removal (simplified relationship patterns)
