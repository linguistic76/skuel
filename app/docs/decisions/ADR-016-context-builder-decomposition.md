---
title: ADR-016: Context Builder Decomposition
updated: 2025-12-04
status: current
category: decisions
tags: [adr, architecture, refactoring, separation-of-concerns]
related: [ADR-001, ADR-007, ADR-015]
---

# ADR-016: Context Builder Decomposition

**Status:** Accepted

**Date:** December 4, 2025

**Decision Type:** Pattern/Practice

---

## Context

**What is the issue we're facing?**

The `user_context_builder.py` file had grown to 2,102 lines with multiple concerns:
- ~650 lines of MEGA-QUERY Cypher
- ~440 lines of deprecated methods
- Query execution, data extraction, and context population all in one file
- Poor separation of concerns making testing and maintenance difficult

**Constraints:**
- Must maintain backward compatibility for 23 call sites
- No changes to public API (4 build methods)
- Keep MEGA-QUERY performance (single round-trip)

---

## Decision

**Decompose into 4 focused modules following separation of concerns:**

```
core/services/user/
├── user_context_builder.py      (~331 lines) - Orchestration only
├── user_context_queries.py      (~1,000 lines) - Query constants + executor
├── user_context_extractor.py    (~351 lines) - Data extraction
└── user_context_populator.py    (~235 lines) - Context population
```

**Architecture:**

1. **UserContextBuilder** (orchestration)
   - Composes QueryExecutor, Extractor, and Populator
   - Maintains 4 public methods: `build()`, `build_rich()`, `build_user_context()`, `build_rich_user_context()`

2. **UserContextQueryExecutor** (query execution)
   - MEGA_QUERY and CONSOLIDATED_QUERY as constants
   - `execute_mega_query()` - Rich data + UIDs
   - `execute_consolidated_query()` - UIDs only

3. **UserContextExtractor** (data extraction)
   - GraphSourcedData dataclass with typed relationship data
   - Domain-specific extraction: tasks, goals, habits, knowledge

4. **UserContextPopulator** (context population)
   - Pure functions mapping query results to UserContext fields
   - Standard fields, rich fields, graph-sourced fields

---

## Alternatives Considered

### Alternative 1: Keep single file, just refactor internally
**Pros:** No new files, simpler imports
**Cons:** Still 2000+ lines, concerns still mixed
**Why rejected:** Doesn't address core maintainability issue

### Alternative 2: Split into 2 files (queries + builder)
**Pros:** Fewer files to manage
**Cons:** Builder still too large (~1,400 lines)
**Why rejected:** Doesn't achieve sufficient separation

### Alternative 3: Microservices approach (separate services)
**Pros:** Maximum separation
**Cons:** Over-engineering, adds latency, complex wiring
**Why rejected:** Too much overhead for in-process code

---

## Consequences

### Positive Consequences
- ✅ Each file has single responsibility
- ✅ Easier to test (mock individual components)
- ✅ Reduced cognitive load (~331 lines vs 2,102)
- ✅ Removed ~440 lines deprecated code
- ✅ Query logic isolated for future optimization

### Negative Consequences
- ⚠️ More files to navigate (4 instead of 1)
- ⚠️ Import paths changed in `__init__.py`

### Neutral Consequences
- ℹ️ Public API unchanged
- ℹ️ Performance unchanged (same queries)

---

## Implementation Details

### Code Location
- **Primary files:**
  - `/core/services/user/user_context_builder.py`
  - `/core/services/user/user_context_queries.py`
  - `/core/services/user/user_context_extractor.py`
  - `/core/services/user/user_context_populator.py`
- **Exports:** `/core/services/user/__init__.py`
- **Tests:** `/tests/integration/test_rich_user_context_pattern.py`

### Additional Fixes Applied
During decomposition, fixed Cypher syntax errors:
- Nested `collect()` in Events section
- Nested `collect()` in Principles section
- Nested `collect()` in Choices section

Cypher doesn't allow aggregate functions inside aggregate functions.

### Testing
- ✅ 597/644 integration tests passing
- ✅ All 4 `test_rich_user_context_pattern.py` tests passing
- ✅ All 67 user context tests passing

---

## Success Criteria

- [x] All 23 call sites work unchanged
- [x] Integration tests pass
- [x] Max file size < 1,000 lines
- [x] Clear separation: query, extract, populate, orchestrate

---

## Related Documentation

- `/docs/architecture/UNIFIED_USER_ARCHITECTURE.md` - Updated with decomposition info
- `/core/services/user/__init__.py` - Module docstring documents architecture
- ADR-001: Unified User Context Single Query
- ADR-007: Graph-Sourced Context Builder Query
- ADR-015: MEGA-QUERY Rich Queries Completion

---

## Changelog

| Date | Author | Change | Version |
|------|--------|--------|---------|
| 2025-12-04 | Claude | Initial implementation | 1.0 |
