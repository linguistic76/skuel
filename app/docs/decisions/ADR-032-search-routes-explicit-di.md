---
title: ADR-032: Search Routes Explicit Dependency Injection
updated: 2026-01-26
status: current
category: decisions
tags: [adr, decisions, search, routes, dependency-injection, one-path-forward]
related: [ADR-020-fasthtml-route-registration-pattern.md, SEARCH_ARCHITECTURE.md, DOMAIN_ROUTE_CONFIG_PATTERN.md]
---

# ADR-032: Search Routes Explicit Dependency Injection

**Status:** Accepted

**Date:** 2026-01-26

**Decision Type:** ☑ Pattern/Practice

**Related ADRs:**
- Related to: ADR-020 (FastHTML Route Registration Pattern)

---

## Context

### The Problem

`search_routes.py` was the **only route file in the entire codebase** using module-level global state for service dependencies:

```python
# search_routes.py - BEFORE (only file using globals)
_search_router: SearchRouter | None = None

def set_search_router(services: "Services"):
    global _search_router
    _search_router = services.search_router

def setup_search_routes(app):
    @app.get("/search/results")
    async def search_results(...):
        if _search_router is None:  # Defensive check
            return render_search_error(...)
        result = await _search_router.faceted_search(...)
```

This created architectural inconsistency:

| Pattern | Files Using | Example |
|---------|-------------|---------|
| **Module-level global** | 1 (search_routes.py only) | `_search_router: SearchRouter \| None = None` |
| **DomainRouteConfig** | 12 files (44% of routes) | tasks, goals, habits, events, choices, principles, etc. |
| **Explicit parameters** | 14 files (52% of routes) | GraphQL, admin, auth, ingestion, etc. |

### Why This Matters

**Problems with global pattern:**
- Hidden dependencies (function signature doesn't show SearchRouter requirement)
- Defensive checks needed (`if _search_router is None`)
- Testing difficulty (must mutate global state)
- Thread safety concerns (mutable module-level state)
- Implicit coupling (routes depend on initialization order)

**Violations of SKUEL principles:**
- **"One Path Forward"** - Should have single DI pattern across all routes
- **Fail-fast philosophy** - Defensive checks mask missing dependencies
- **Explicit dependencies** - Function signatures should declare requirements

---

## Decision

**Refactor search routes to use explicit parameter-based dependency injection, matching the GraphQL routes pattern.**

### Implementation

**After (explicit parameters):**
```python
# search_routes.py
def create_search_routes(
    app: Any,
    rt: Any,
    services: "Services",
    search_router: SearchRouter,  # ← Explicit parameter (no global)
) -> None:
    """Wire search routes with explicit SearchRouter dependency."""

    @app.get("/search/results")
    async def search_results(...):
        # search_router available via closure - NO global
        result = await search_router.faceted_search(search_request, user_uid)
        ...
```

**Bootstrap wiring:**
```python
# scripts/dev/bootstrap.py - BEFORE
from adapters.inbound.search_routes import (
    set_search_router,
    setup_search_routes,
)

set_search_router(services)    # ← Implicit global mutation
setup_search_routes(app)       # ← Implicit global access

# scripts/dev/bootstrap.py - AFTER
from adapters.inbound.search_routes import create_search_routes

create_search_routes(app, rt, services, services.search_router)  # ← Explicit
```

### Pattern Consistency

Search routes now match GraphQL routes pattern:

| Route Type | Function Call |
|------------|---------------|
| **Search** | `create_search_routes(app, rt, services, services.search_router)` |
| **GraphQL** | `create_graphql_routes_manual(app, rt, services, services.search_router)` |

---

## Alternatives Considered

### Alternative 1: DomainRouteConfig Pattern

**Description:** Use the configuration-driven pattern like tasks, goals, etc.

```python
SEARCH_CONFIG = DomainRouteConfig(
    domain_name="search",
    primary_service_attr="search_router",
    api_factory=create_search_api_routes,
    ui_factory=create_search_ui_routes,
)
```

**Pros:**
- Matches 12 other domain route files
- Configuration-driven (consistent with Activity domains)

**Cons:**
- Search is a meta-service (orchestrates domain search services, not a domain itself)
- Overhead of configuration object for single dependency
- GraphQL already established precedent for explicit parameters with meta-services

**Why rejected:** Search and GraphQL are both meta-services that orchestrate other services. Explicit parameters are more appropriate than domain configuration.

### Alternative 2: Keep Global Pattern

**Description:** Retain module-level `_search_router` global variable.

**Pros:**
- No code changes required
- Pattern works (routes function correctly)

**Cons:**
- Violates "One Path Forward" (only route file using globals)
- Requires defensive checks throughout code
- Hidden dependencies (unclear from function signature)
- Testing difficulty

**Why rejected:** Violates core SKUEL architectural principles. Inconsistency with rest of codebase.

---

## Consequences

### Positive Consequences

- ✅ **Architectural consistency** - All 27 route files now follow one of two consistent patterns (no globals)
- ✅ **Explicit dependencies** - Function signature declares requirements clearly
- ✅ **Testability** - Easy to inject test doubles via parameters
- ✅ **Thread safety** - No shared mutable state
- ✅ **"One Path Forward"** - Single dependency injection philosophy across codebase
- ✅ **Fail-fast** - No defensive checks needed; function signature guarantees dependency exists
- ✅ **Pattern clarity** - Meta-services (search, GraphQL) use explicit parameters; domains use DomainRouteConfig

### Negative Consequences

- ⚠️ None identified - purely beneficial refactoring

### Neutral Consequences

- ℹ️ Bootstrap call changes from 2 lines to 1 line (minor simplification)
- ℹ️ `__all__` export changes from 2 names to 1 name

---

## Implementation Details

### Files Modified

| File | Changes | Impact |
|------|---------|--------|
| `adapters/inbound/search_routes.py` | Removed global, refactored function signature | Eliminated 3 defensive checks, removed 15 lines |
| `scripts/dev/bootstrap.py` | Updated wiring call | Simplified from 2 lines to 1 line |

### Code Changes Summary

**Removed:**
- Module-level `_search_router` global variable
- `set_search_router()` function
- Three defensive `if _search_router is None` checks (lines 137, 247, 318)

**Changed:**
- `setup_search_routes(app)` → `create_search_routes(app, rt, services, search_router)`
- All route functions now access `search_router` via closure

**Updated:**
- `__all__` export: `["set_search_router", "setup_search_routes"]` → `["create_search_routes"]`

### Testing Strategy

- ✅ Python syntax validation passed
- ✅ Import verification passed
- ✅ Ruff linter passed (all checks)
- ✅ Code formatting applied
- ⏸️ Manual testing required (start dev server, test search UI and API)

---

## Documentation Updates

### Updated Files

1. **`docs/architecture/SEARCH_ARCHITECTURE.md`**
   - Added "Route Wiring (Explicit Dependency Injection)" section
   - Updated Key Files table
   - Documented pattern choice rationale

2. **`docs/patterns/DOMAIN_ROUTE_CONFIG_PATTERN.md`**
   - Updated "Justified Exceptions" section
   - Noted search_routes.py uses explicit DI (not globals)

---

## Future Considerations

### Pattern Consolidation Complete

With this change, SKUEL now has **two consistent route wiring patterns**:

| Pattern | Usage | Files |
|---------|-------|-------|
| **DomainRouteConfig** | Standard domains | 12 files (tasks, goals, habits, events, choices, principles, learning, knowledge, context, reports, finance, askesis) |
| **Explicit parameters** | Meta-services + specialized | 15 files (search, GraphQL, admin, auth, ingestion, nous, AI, etc.) |

**Total:** 27 route files, 0 using module-level globals.

### When to Revisit

This decision should be revisited if:
- New route files introduce different patterns
- DomainRouteConfig pattern proves insufficient for meta-services
- Performance issues emerge from closure-based dependency access

### Evolution Path

Possible future improvements:
- Type-safe Protocol for route factory signatures
- Automated validation of dependency injection patterns
- Route wiring telemetry/observability

---

## Approval

**Decision Made By:** Claude Code + Mike (project lead)

**Date:** 2026-01-26

**Implementation Status:** ✅ Complete

**Verification Checklist:**
- ✅ Code changes implemented
- ✅ Documentation updated
- ✅ Syntax validation passed
- ✅ Linting passed
- ⏸️ Manual testing pending

---

## Changelog

| Date | Author | Change | Version |
|------|--------|--------|---------|
| 2026-01-26 | Claude Code | Initial implementation and documentation | 1.0 |

---

## Appendix

### Code Before/After Comparison

**Before (global pattern):**
```python
# Module-level global
_search_router: SearchRouter | None = None

def set_search_router(services: "Services"):
    global _search_router
    _search_router = services.search_router

def setup_search_routes(app):
    @app.get("/search/results")
    async def search_results(...):
        if _search_router is None:
            return render_search_error("Search service unavailable")
        result = await _search_router.faceted_search(...)
```

**After (explicit parameters):**
```python
# No global variable

def create_search_routes(
    app: Any,
    rt: Any,
    services: "Services",
    search_router: SearchRouter,
) -> None:
    @app.get("/search/results")
    async def search_results(...):
        # No defensive check needed
        result = await search_router.faceted_search(...)
```

### Pattern Alignment

**Meta-services using explicit parameters:**
```python
# Search (this ADR)
create_search_routes(app, rt, services, services.search_router)

# GraphQL (established pattern)
create_graphql_routes_manual(app, rt, services, services.search_router)
```

Both meta-services now follow the same explicit dependency injection pattern.
