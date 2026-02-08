---
title: ADR-028: KU & MOC Unified Relationship Migration
updated: 2026-01-07
status: current
category: decisions
tags: [adr, decisions, relationships, unified-architecture, ku, moc]
related: [ADR-017, ADR-026]
---

# ADR-028: KU & MOC Unified Relationship Migration

**Status:** Accepted

**Date:** 2026-01-07

**Decision Type:** ☑️ Pattern/Practice

**Related ADRs:**
- Builds on: ADR-017 (Relationship Service Unification)
- Builds on: ADR-026 (Unified Relationship Registry)

---

## Context

**What is the issue we're facing?**

KU and MOC domains had specialized relationship services (MocRelationshipService ~694 lines) alongside intelligence services (KuGraphService, KuSemanticService). This created inconsistency with Activity Domains that had already migrated to UnifiedRelationshipService.

**Key question:** Should we decompose ALL specialized services, or identify which provide relationship CRUD vs intelligence?

**Constraints:**
- KuGraphService (~54k lines): Prerequisite chains, learning recommendations, hub scores
- KuSemanticService (~20k lines): RDF-inspired semantic relationships, confidence scoring
- MocRelationshipService (~694 lines): Basic relationship CRUD operations
- UnifiedRelationshipService already handles relationship CRUD for 6 Activity Domains

---

## Decision

**Principle: Separate relationship handling (migrate) from intelligence/analytics (keep specialized).**

### Phase 1: MOC Domain Migration (COMPLETED)

1. Added `MOC_SECTION_CONFIG` and `MOC_CONFIG` configs to unified relationship registry
2. Added `NeoLabel.MOC_SECTION` for section nodes
3. Updated MocService facade with two UnifiedRelationshipService instances:
   - `self.relationships` for MapOfContent relationships
   - `self.section_relationships` for MOCSection relationships
4. Updated MocSectionService to use unified service for practice templates
5. Updated MocDiscoveryService to use unified service for learning paths
6. Added inline `_get_moc_knowledge_units()` method for KU aggregation
7. **DELETED `moc_relationship_service.py` (~694 lines)**

### Phase 2: KU Relationships Migration (COMPLETED)

1. Added `self.relationships = UnifiedRelationshipService(...)` to KuService
2. Updated `get_enables()` to use unified service
3. Added `fetch_via_unified()` method to KuRelationships container
4. Added helper functions for safe relationship queries

### Phases 3-4: RECONSIDERED

**Decision:** Keep `KuGraphService` and `KuSemanticService` as specialized services.

**Rationale:**
- These services provide **specialized graph intelligence**, NOT basic relationship CRUD
- `KuGraphService`: Prerequisite chains, learning recommendations, hub scores, readiness calculations
- `KuSemanticService`: RDF-inspired semantic relationships, confidence scoring, transitive inference
- UnifiedRelationshipService handles CRUD; specialized services handle intelligence
- Harmonious architecture achieved via `self.relationships` attribute

---

## Alternatives Considered

### Alternative 1: Full Decomposition (Original Plan)
**Description:** Delete KuGraphService and KuSemanticService, migrate all methods to UnifiedRelationshipService or KuIntelligenceService.

**Pros:**
- Maximum code reduction (~4,500 lines)
- Simpler service count

**Cons:**
- Loses specialized intelligence methods that don't fit UnifiedRelationshipService's generic API
- KuGraphService/KuSemanticService do much more than relationship CRUD
- High risk of breaking complex graph algorithms

**Why rejected:** Intelligence methods require specialized algorithms, not generic CRUD.

### Alternative 2: Harmonious Coexistence (CHOSEN)
**Description:** Add UnifiedRelationshipService to facade, keep specialized services for intelligence.

**Pros:**
- Clean separation: CRUD (unified) vs Intelligence (specialized)
- Low migration risk
- Preserves complex algorithms
- Follows Activity Domain pattern via `self.relationships`

**Cons:**
- Keeps more service files
- Slightly higher complexity

**Why chosen:** Best balance of consistency and functionality.

---

## Consequences

### Positive Consequences
- ✅ MOC domain now uses harmonious UnifiedRelationshipService pattern
- ✅ KU domain has `self.relationships` for consistent relationship access
- ✅ ~650 lines deleted (MocRelationshipService)
- ✅ Clear separation: relationship CRUD vs graph intelligence
- ✅ All 14 domains now use `self.relationships` pattern

### Negative Consequences
- ⚠️ KuGraphService and KuSemanticService remain separate services
- ⚠️ KU has more services than Activity Domains (appropriate for domain complexity)

### Neutral Consequences
- ℹ️ KuRelationships.fetch_via_unified() provides alternative to graph-service-based fetch()
- ℹ️ Both fetch methods remain available during transition

---

## Implementation Details

### Code Location

**Primary files:**
- `/core/services/ku_service.py` - Added UnifiedRelationshipService
- `/core/services/moc_service.py` - Two relationship service instances
- `/core/models/ku/ku_relationships.py` - fetch_via_unified() method

**Deleted files:**
- `/core/services/moc/moc_relationship_service.py` (~694 lines)

**Kept specialized services:**
- `/core/services/ku/ku_graph_service.py` - Graph intelligence
- `/core/services/ku/ku_semantic_service.py` - Semantic relationships

### Key Code Patterns

```python
# KuService pattern
from core.services.relationships import UnifiedRelationshipService
from core.services.relationships.domain_configs import get_ku_config

self.relationships: "UnifiedRelationshipService" = UnifiedRelationshipService(
    backend=repo,
    config=get_ku_config(),
    graph_intel=graph_intelligence_service,
)

# MocService pattern (dual instances)
self.relationships = UnifiedRelationshipService(
    backend=moc_backend,
    config=get_moc_config(),
    graph_intel=graph_intelligence_service,
)
self.section_relationships = UnifiedRelationshipService(
    backend=section_backend,
    config=get_moc_section_config(),
    graph_intel=graph_intelligence_service,
)
```

```python
# KuRelationships.fetch_via_unified()
@classmethod
async def fetch_via_unified(
    cls,
    ku_uid: str,
    relationship_service: "UnifiedRelationshipService",
) -> "KuRelationships":
    results = await asyncio.gather(
        relationship_service.get_related_uids("prerequisites", ku_uid),
        relationship_service.get_related_uids("enables_learning", ku_uid),
        # ... parallel queries for all relationship types
    )
    return cls(
        prerequisite_uids=_extract_uids_from_result(results[0]),
        enables_uids=_extract_uids_from_result(results[1]),
        # ...
    )
```

---

## Summary

| Domain | Specialized Lines | Lines Deleted | Pattern |
|--------|------------------|---------------|---------|
| MOC | 694 | ~650 | Full migration |
| KU | ~4,500 | 0 | Harmonious coexistence |
| **Total** | ~5,200 | ~650 | Balanced approach |

**Key Insight:** Not all specialized services should be deleted. The decision criterion is:
- **Relationship CRUD** → Migrate to UnifiedRelationshipService
- **Graph Intelligence** → Keep as specialized service

---

## Changelog

| Date | Author | Change | Version |
|------|--------|--------|---------|
| 2026-01-07 | Claude | Initial implementation | 1.0 |
