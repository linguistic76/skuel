---
title: ADR-015: MEGA-QUERY Rich Queries Completion for All Activity Domains
updated: 2026-01-24
status: current
category: decisions
tags: [adr, decisions, query, mega-query, user-context]
related: [ADR-001, ADR-007, ADR-030]
---

# ADR-015: MEGA-QUERY Rich Queries Completion for All Activity Domains

**Status:** Accepted

**Date:** 2025-12-04

**Decision Type:** ☑ Query Architecture  ⬜ Graph Schema  ☑ Performance Optimization  ☑ Pattern/Practice

**Complexity Score:** 50+ (Extended from ADR-001's 38-point base query)

**Related ADRs:**
- Extends: ADR-001 (Single Complex Query for Unified User Context)
- Related to: ADR-007 (Graph-Sourced Context Builder Pattern)

---

## Context

**What is the issue we're facing?**

The MEGA-QUERY in `user_context_builder.py` was designed to fetch user context data efficiently in a single database round-trip. However, as of November 2025, three activity domains were incomplete:

| Domain | UID Collection | Rich Query | Status |
|--------|----------------|------------|--------|
| Tasks | Done | Done | COMPLETE |
| Goals | Done | Done | COMPLETE |
| Habits | Done | Done | COMPLETE |
| Knowledge | Done | Done | COMPLETE |
| Learning Paths | Done | Done | COMPLETE |
| Learning Steps | Done | Done | COMPLETE |
| **Events** | Done | **MISSING** | Only UIDs |
| **Principles** | **MISSING** | **MISSING** | Not in query |
| **Choices** | **MISSING** | **MISSING** | Not in query |

**Problem:**
- Events only collected UIDs, no graph neighborhood data
- Principles and Choices were completely absent from the MEGA-QUERY
- UserContext fields (`active_events_rich`, `core_principles_rich`, `recent_choices_rich`) were populated with empty arrays
- Cross-domain intelligence for these three domains was unavailable

**Requirements:**
- Complete rich query implementation for Events, Principles, Choices
- Follow existing pattern (entity properties + graph neighborhoods)
- Maintain single round-trip performance
- Use LIMIT clauses for performance optimization
- Filter Choices by status ('pending', 'active' only)

---

## Decision

**What is the change we're proposing/making?**

We implemented rich queries for all three missing domains, extending the MEGA-QUERY from ~400 lines to ~650 lines of Cypher while maintaining single round-trip performance.

**Implementation:**

### Events Rich Query
**Relationships traversed:**
- `APPLIES_KNOWLEDGE` → Ku (LIMIT 10)
- `CONTRIBUTES_TO_GOAL` → Goal (LIMIT 10)
- `PRACTICED_AT_EVENT` (incoming) → Habit (LIMIT 10)
- `CONFLICTS_WITH` (bidirectional) → Event (LIMIT 5)

### Principles Rich Query
**Relationships traversed:**
- `GROUNDED_IN_KNOWLEDGE` → Ku (LIMIT 10)
- `GUIDES_GOAL` → Goal (LIMIT 10)
- `GUIDES_CHOICE` → Choice (LIMIT 10)
- `EMBODIES_PRINCIPLE` (incoming) → Habit (LIMIT 10)
- `ALIGNED_WITH_PRINCIPLE` (incoming) → Task (LIMIT 10)

### Choices Rich Query
**Status filter:** `status IN ['pending', 'active']`

**Relationships traversed:**
- `INFORMED_BY_KNOWLEDGE` → Ku (LIMIT 10)
- `INFORMED_BY_PRINCIPLE` → Principle (LIMIT 10)
- `AFFECTS_GOAL` → Goal (LIMIT 10)
- `OPENS_LEARNING_PATH` → Lp (LIMIT 5)
- `IMPLEMENTS_CHOICE` (incoming) → Task (LIMIT 10)

**File:** `/core/services/user/user_context_queries.py` (MEGA_QUERY constant)

---

## Alternatives Considered

### Alternative 1: Lazy Loading via Separate Queries
**Description:**
Keep Events/Principles/Choices as UID-only and fetch rich data on demand.

**Pros:**
- Smaller initial query
- Only fetch data when needed

**Cons:**
- Multiple round-trips when rich data needed
- Inconsistent behavior across domains
- Complex client-side logic

**Why rejected:**
Violates the MEGA-QUERY philosophy of "one query fetches everything." The performance gain of lazy loading is offset by additional round-trips.

### Alternative 2: Use UnifiedRelationshipService
**Description:**
Call UnifiedRelationshipService methods for Events/Principles/Choices instead of raw Cypher.

**Pros:**
- Uses existing relationship infrastructure
- DRY with relationship definitions in domain_configs.py

**Cons:**
- Would require multiple service calls (multiple round-trips)
- UnifiedRelationshipService designed for individual entity queries, not bulk aggregation
- Breaks single round-trip principle

**Why rejected:**
UnifiedRelationshipService operates at a different semantic level (per-entity queries). The MEGA-QUERY requires raw Cypher for aggregation across ALL user entities in ONE query.

---

## Consequences

### Positive Consequences
- ✅ **Complete cross-domain intelligence** - All 9 domains now have rich data
- ✅ **Consistent pattern** - All domains follow same structure (entity + graph_context)
- ✅ **Single round-trip maintained** - No additional database queries
- ✅ **UserContext fully populated** - All `*_rich` fields now have data
- ✅ **Performance-optimized** - LIMIT clauses prevent runaway relationship fetching

### Negative Consequences
- ⚠️ **Increased query complexity** - Query grew from ~400 to ~650 lines
- ⚠️ **Longer maintenance effort** - More WITH clauses to propagate variables through
- ⚠️ **Memory usage increase** - More data returned per query

### Neutral Consequences
- ℹ️ Query follows exact pattern established by Habits (lines 386-437)
- ℹ️ Relationship definitions sourced from domain_configs.py

---

## Implementation Details

### Code Location
**Where is this decision implemented?**
- Primary file: `/core/services/user/user_context_queries.py` (MEGA_QUERY constant, ~700 lines of Cypher)
- Related files:
  - `/core/services/user/user_context_builder.py` (orchestration, ~331 lines)
  - `/core/services/user/user_context_extractor.py` (result parsing, ~351 lines)
  - `/core/services/user/user_context_populator.py` (context population, ~235 lines)
  - `/core/services/relationships/domain_configs.py` (relationship definitions)
  - `/core/services/user/unified_user_context.py` (field definitions)
- Tests:
  - `/tests/integration/test_rich_user_context_pattern.py` (has pre-existing fixture issues)
  - `/tests/integration/test_unified_user_context.py`

**Note:** Context builder decomposed December 2025 - see ADR-016.

### Output Structure
**Each domain returns:**
```python
{
    entity: properties(entity),
    graph_context: {
        relationship1: [{uid, title, ...}],  # LIMIT 10
        relationship2: [{uid, title, status}],
        # ...
    }
}
```

### Testing Strategy
**How is this decision validated?**
- ✅ Python syntax validation: `python -m py_compile` passed
- ✅ Import test: `from core.services.user.user_context_builder import UserContextBuilder` works
- ✅ Ruff format: No changes needed
- ✅ Integration tests: 63/63 user_context tests pass (4 errors are pre-existing fixture issues)

---

## Context Builder Decomposition (2026-01 Update)

**Date:** January 2026
**Related:** ADR-030 (UserContext File Consolidation)

The UserContext builder was decomposed into a 4-module structure for better maintainability:

### The 4 Modules

| Module | Lines | Purpose |
|--------|-------|---------|
| **user_context_builder.py** | ~331 | Orchestration - `build()` and `build_rich()` methods |
| **user_context_queries.py** | ~1,000 | MEGA-QUERY constant (~700 lines of Cypher) |
| **user_context_extractor.py** | ~351 | Result parsing - extracts data from Neo4j results |
| **user_context_populator.py** | ~235 | Context population - populates UnifiedUserContext fields |

**Total:** ~1,917 lines (previously in one 2,147-line file)

### Architecture

```
user_context_builder.py (orchestration)
    ↓
user_context_queries.py (MEGA-QUERY ~700 lines)
    ↓
user_context_extractor.py (parse Neo4j results)
    ↓
user_context_populator.py (populate UnifiedUserContext)
```

**Key Benefit:** Separation of concerns - query definition, result parsing, and context population are now independent modules.

**See:**
- ADR-030 (UserContext File Consolidation) for decomposition rationale
- `/docs/architecture/UNIFIED_USER_ARCHITECTURE.md` for complete architecture details

---

## Documentation & Communication

### Related Documentation
- Architecture docs: `/docs/architecture/UNIFIED_USER_ARCHITECTURE.md` (updated)
- Code comments: Inline section headers in MEGA-QUERY

### Changelog

| Date | Author | Change | Version |
|------|--------|--------|---------|
| 2026-01-24 | Claude | Context builder decomposition (4 modules) | 2.0 |
| 2025-12-04 | Claude | Initial implementation | 1.0 |

---

## Appendix

### Rich Query Pattern (from Habits)

```cypher
// ====================================================================
// DOMAIN - Fetch UIDs AND rich data with graph neighborhoods
// ====================================================================
OPTIONAL MATCH (user)-[:HAS_ENTITY]->(entity:Entity)
WHERE entity.status = 'active'
WITH user, ...,
     collect(entity.uid) as entity_uids,
     collect(entity) as all_entity_nodes

// Filter entities for rich data (with graph neighborhoods)
UNWIND CASE WHEN size(all_entity_nodes) > 0 THEN all_entity_nodes ELSE [null] END as entity
OPTIONAL MATCH (entity)-[:RELATIONSHIP1]->(related1:Type1)
WHERE entity IS NOT NULL
WITH user, ..., entity,
     collect(DISTINCT {uid: related1.uid, title: related1.title})[0..10] as entity_related1

// ... more relationship traversals ...

WITH user, ...,
     collect(CASE WHEN entity IS NOT NULL THEN {
         entity: properties(entity),
         graph_context: {
             related1: entity_related1,
             related2: entity_related2
         }
     } END) as entities_rich
```

### Domain Relationship Mappings

**Events:**
| Relationship | Direction | Target | Key |
|-------------|-----------|--------|-----|
| APPLIES_KNOWLEDGE | outgoing | Ku | applied_knowledge |
| CONTRIBUTES_TO_GOAL | outgoing | Goal | linked_goals |
| PRACTICED_AT_EVENT | incoming | Habit | practiced_habits |
| CONFLICTS_WITH | both | Event | conflicting_events |

**Principles:**
| Relationship | Direction | Target | Key |
|-------------|-----------|--------|-----|
| GROUNDED_IN_KNOWLEDGE | outgoing | Ku | grounded_knowledge |
| GUIDES_GOAL | outgoing | Goal | guided_goals |
| GUIDES_CHOICE | outgoing | Choice | guided_choices |
| EMBODIES_PRINCIPLE | incoming | Habit | embodying_habits |
| ALIGNED_WITH_PRINCIPLE | incoming | Task | aligned_tasks |

**Choices:**
| Relationship | Direction | Target | Key |
|-------------|-----------|--------|-----|
| INFORMED_BY_KNOWLEDGE | outgoing | Ku | informing_knowledge |
| INFORMED_BY_PRINCIPLE | outgoing | Principle | guiding_principles |
| AFFECTS_GOAL | outgoing | Goal | affected_goals |
| OPENS_LEARNING_PATH | outgoing | Lp | opened_paths |
| IMPLEMENTS_CHOICE | incoming | Task | implementing_tasks |
