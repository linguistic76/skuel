---
title: SKUEL Refactoring Checklist
updated: 2026-01-03
status: current
category: general
tags: [checklist, refactoring]
related: [PHASES.md, PHASE_DEPENDENCIES.md]
---

# SKUEL Refactoring Checklist

**Generated:** 2025-11-28
**Last Updated:** 2026-01-03 (test suite fully passing)
**Analysis Scope:** 501 core + 91 adapter + 131 test files (~150K LOC)

> **Source of Truth:** Status tracking is in `/docs/PHASES.md` Section #2 (Refactoring Roadmap).
> This file contains detailed task lists. For current phase status, see PHASES.md.

---

## PHASE 1: QUICK WINS ✅ COMPLETE

**Status:** ✅ COMPLETE (per PHASES.md)
**Completed:** 2025-12 (estimated)

### Task 1.1: Extract Validation Rules ✅
**Priority:** HIGH
**Effort:** 2-3 hours
**Impact:** Affects 22+ request models

- [x] Create `/core/models/validation_rules.py` ✅ (23K file)
- [x] Extract common validation functions
- [x] Create unit tests for all validators
- [x] Update request model files to use new validators

### Task 1.2: Create MetadataManagerMixin ✅
**Priority:** MEDIUM
**Effort:** 1-2 hours
**Impact:** Affects 30+ service files

- [x] Create `/core/services/metadata_manager_mixin.py` ✅
- [x] Implement metadata management methods
- [x] Document in CLAUDE.md

### Task 1.3: Extract Timestamp Helpers ✅
**Priority:** LOW
**Effort:** 1 hour
**Impact:** Affects 15 files

- [x] Create `/core/utils/timestamp_helpers.py` ✅
- [x] Extract timestamp utilities

**Phase 1 Completion Criteria:** ✅ MET
- [x] Validation rules consolidated
- [x] MetadataManagerMixin created and documented
- [x] Timestamp helpers extracted
- [x] All tests passing

---

## PHASE 2: MAJOR REFACTORING ✅ COMPLETE

**Status:** ✅ COMPLETE (per PHASES.md)
**Completed:** 2025-12 (estimated)

### Task 2.1: Move Business Logic from Route Handlers ✅
**Priority:** HIGH
**Effort:** 4-5 hours
**Impact:** HIGH - Separation of concerns

- [x] Business logic extracted from route handlers
- [x] Intelligence services created for enrichment
- [x] Mock data centralized in `/core/mock_data/intelligence/`
- [x] Route factories (CRUDRouteFactory, StatusRouteFactory) handle boilerplate

**Pattern Established:**
- Routes call services, services contain logic
- Intelligence routes use centralized mock data
- Factory pattern eliminates route boilerplate (~60% reduction)

### Task 2.2: Relationship Service Architecture ✅
**Priority:** MEDIUM
**Effort:** 3-4 hours
**Impact:** MEDIUM - Architecture clarity

- [x] Relationship services unified (ADR-017)
- [x] Graph-native pattern implemented
- [x] `RelationshipName` enum for type safety (SKUEL013)

**Key Change:** Relationships stored as Neo4j edges, not serialized fields.
See: `/docs/patterns/DOMAIN_RELATIONSHIPS_PATTERN.md`

### Task 2.3: Request/Response Architecture ✅
**Priority:** MEDIUM
**Effort:** 4-5 hours
**Impact:** MEDIUM

- [x] Three-tier type system established (Pydantic → DTO → Domain Model)
- [x] Validation rules centralized in `/core/models/validation_rules.py`
- [x] DomainModelProtocol for type-safe generic operations

**Phase 2 Completion Criteria:** ✅ MET
- [x] Business logic in services, not routes
- [x] Relationship architecture documented
- [x] Type system patterns established
- [x] Route factories reduce boilerplate
- [x] All tests passing

---

## PHASE 3: ADVANCED REFACTORING 🟡 READY

**Status:** 🟡 READY (per PHASES.md)
**Blocked By:** None - can proceed when prioritized

### Task 3.1: Consolidate Query Building to CypherGenerator
**Priority:** MEDIUM
**Effort:** 3-4 hours
**Impact:** MEDIUM - Query maintainability

**Current State:** CypherGenerator exists with several patterns. MEGA-QUERY in user_context_queries.py demonstrates advanced consolidation.

- [ ] Identify remaining inline query patterns in services
- [ ] Add generic patterns to CypherGenerator:
  - [ ] `build_entity_with_context()` - Generic pattern
  - [ ] `build_entity_with_relationships()` - Relationship patterns
- [ ] Migrate services to use CypherGenerator patterns
- [ ] Verify performance unchanged

**Reference:** `/docs/patterns/query_architecture.md`

### Task 3.2: Expand Factory Pattern to Remaining Domains
**Priority:** MEDIUM
**Effort:** 2-3 hours
**Impact:** Additional 200+ lines saved

**Current State:** Route factories established (ADR-020). Many domains already migrated.

- [ ] Audit which domains still have manual route definitions
- [ ] Migrate remaining domains to factory pattern
- [ ] Run integration tests

**Reference:** `/docs/patterns/ROUTE_FACTORIES.md`

---

## CROSS-PHASE TASKS

### Testing
- [ ] Add unit tests for all extracted validation rules
- [ ] Add unit tests for MetadataManagerMixin
- [ ] Add integration tests for all refactored routes
- [ ] Run full test suite after each phase
- [ ] Measure test coverage (target: 100% maintained)

### Documentation
- [ ] Document validation rules in `/core/models/validation_rules.py`
- [ ] Document new base classes in docstrings
- [ ] Update architecture documentation
- [ ] Add examples to CLAUDE.md if patterns are generic

### Code Review
- [ ] Request code review after each phase
- [ ] Address reviewer feedback
- [ ] Document architectural decisions

### Performance
- [ ] Profile endpoints before/after refactoring
- [ ] Measure query performance (should be unchanged)
- [ ] Check memory usage (should decrease)
- [ ] Monitor test execution time

---

## SUMMARY BY PRIORITY

### Phase 1 (Quick Wins) ✅ COMPLETE
- [x] Extract validation rules
- [x] Create MetadataManagerMixin
- [x] Extract timestamp helpers

### Phase 2 (Major Refactoring) ✅ COMPLETE
- [x] Move business logic from routes
- [x] Relationship service architecture
- [x] Request/response architecture

### Phase 3 (Advanced) 🟡 READY
- [ ] Consolidate query building
- [ ] Expand factory pattern

**Results Achieved:**
- Code reduction: ~2,400 lines via route factories
- Quality improvement: HIGH
- All tests passing: **1863 passed, 19 skipped, 0 failed** (2026-01-03)

---

## SUCCESS CRITERIA

**Phases 1-2 (Achieved):**
- [x] Validation rules consolidated (`/core/models/validation_rules.py`)
- [x] Business logic moved from routes to services
- [x] Three-tier type system established
- [x] Route factories reduce boilerplate
- [x] All integration tests passing
- [x] Architecture documented in CLAUDE.md

**Phase 3 (Remaining):**
- [ ] All query building uses CypherGenerator
- [ ] All 14 domains use factory patterns

---

## NOTES FOR IMPLEMENTATION

1. **Backward Compatibility:** All changes should maintain backward compatibility with existing routes
2. **Testing Strategy:** Test each change individually before moving to next phase
3. **Code Review:** Request review after each task, not after each phase
4. **Communication:** Inform team of changes before starting each phase
5. **Version Control:** Consider branching per phase for easier rollback

---

## Related Documentation

- `/docs/PHASES.md` - **Source of truth for phase status**
- `/docs/PHASE_DEPENDENCIES.md` - Dependency graph between phases
- `/docs/patterns/ROUTE_FACTORIES.md` - Route factory patterns
- `/docs/patterns/query_architecture.md` - Query building patterns
- `/docs/patterns/three_tier_type_system.md` - Type system documentation

---

*Originally generated from: CODEBASE_ANALYSIS_DRY_SOC.md*
*Status synchronized with PHASES.md: 2026-01-03*
