---
title: Route Factory Patterns - Complete Guide
updated: 2026-01-17
category: patterns
related_skills:
- fasthtml
related_docs:
- /docs/patterns/OWNERSHIP_VERIFICATION.md
---

# Route Factory Patterns - Complete Guide
**Date:** 2026-01-12
**Status:** ✅ Production Ready

## Overview

SKUEL uses route factories to eliminate boilerplate and enforce consistency across all domain APIs. This guide documents the complete factory ecosystem.

**Current Status (2025-12-05):**
- ✅ **Phase 1 Complete:** CRUDRouteFactory applied to 100% of domains (16/16)
- ✅ **Phase 2 Complete:** CommonQueryRouteFactory applied to 100% of activity domains (7/7)
- ✅ **Phase 3 Complete:** All integration tests passing (87/87)
- ✅ **Phase 4 Complete:** Ownership verification on all manual routes (42/42)
- ✅ **~2,400 lines of boilerplate eliminated** (66% reduction)
- ✅ **All 3 domain pairs architecturally aligned** (tasks+events, habits+goals, principles+choices)

**Philosophy:**
- **Factories for patterns** - Use factories when routes follow predictable patterns
- **Manual for uniqueness** - Write manual routes for domain-specific logic
- **100% not always the goal** - Some domains (Finance, Principles) intentionally use manual routes for complex query patterns

---

## Factory Hierarchy

```
Route Factories (3 types)
├── CRUDRouteFactory        # Standard CRUD operations
├── CommonQueryRouteFactory  # Common query patterns (NEW)
└── IntelligenceRouteFactory # Intelligence/analytics routes
```

---

## 1. CRUDRouteFactory (Established)

**Purpose:** Generate standard CRUD routes for all domains

**Routes Generated:**
- `POST /api/{domain}/create` - Create entity
- `GET /api/{domain}/get?uid=...` - Get by UID
- `POST /api/{domain}/update?uid=...` - Update entity
- `POST /api/{domain}/delete?uid=...` - Delete entity
- `GET /api/{domain}/list` - List with pagination

**Usage:**
```python
from core.infrastructure.routes import CRUDRouteFactory

crud_factory = CRUDRouteFactory(
    service=tasks_service,
    domain_name="tasks",
    create_schema=TaskCreateRequest,
    update_schema=TaskUpdateRequest,
    uid_prefix="task",
)

crud_factory.register_routes(app, rt)
```

**Domains Using It:** 16/16 (ALL)
- Tasks, Goals, Habits, Events, Finance, Choices, Principles
- Journals, Knowledge, Learning Paths, Learning Steps
- Askesis, MOC, Context Aware, System, Transcription

**Impact:** ~150-200 lines saved per domain

---

## 2. CommonQueryRouteFactory (NEW - 2025-11-18)

**Purpose:** Generate common query patterns across domains

**Routes Generated:**
- `GET /api/{domain}/user?user_uid=...` - Get user's entities
- `GET /api/{domain}/goal?goal_uid=...` - Get entities for goal (optional)
- `GET /api/{domain}/habit?habit_uid=...` - Get entities for habit (optional)
- `GET /api/{domain}/by-status?status=...` - Filter by status

**Note:** All routes use query parameters (`?uid=...`) per FastHTML's "query parameters preferred" pattern.

**Usage:**
```python
from core.infrastructure.routes.query_route_factory import CommonQueryRouteFactory

query_factory = CommonQueryRouteFactory(
    service=tasks_service,
    domain_name="tasks",
    supports_goal_filter=True,   # Tasks can be filtered by goal
    supports_habit_filter=True,  # Tasks can be filtered by habit
)

query_factory.register_routes(app, rt)
```

**Domains Using It:** 7/7 activity domains (100%)
- ✅ Tasks (user + goal + habit filters)
- ✅ Goals (user + habit filter)
- ✅ Habits (user + goal filter)
- ✅ Events (user + goal + habit filters)
- ✅ Journals (user filter only)
- ✅ Choices (user + goal filter)
- ✅ Principles (user + goal + habit filters)

**Finance Domain:**
- ⏸️ Finance - Uses domain-specific date-range/category queries instead of factory patterns

**Impact:** ~20-30 lines saved per domain

**Service Method Convention:**

The factory expects services to implement these methods:

```python
class TasksService:
    async def get_user_tasks(self, user_uid: str) -> Result[list[Task]]:
        """Get all tasks for a user."""
        ...

    async def get_tasks_for_goal(self, goal_uid: str) -> Result[list[Task]]:
        """Get tasks that fulfill a goal."""
        ...

    async def get_tasks_for_habit(self, habit_uid: str) -> Result[list[Task]]:
        """Get tasks that reinforce a habit."""
        ...

    async def find_tasks(self, filters: dict) -> Result[list[Task]]:
        """Find tasks by filters (used for status filtering)."""
        ...
```

**Configuration Guide:**

| Domain | User Query | Goal Filter | Habit Filter | Factory Used? | Notes |
|--------|------------|-------------|--------------|---------------|-------|
| **Tasks** | ✅ | ✅ | ✅ | ✅ | Tasks fulfill goals and reinforce habits |
| **Goals** | ✅ | ❌ | ✅ | ✅ | Goals can have supporting habits |
| **Habits** | ✅ | ✅ | ❌ | ✅ | Habits support goals |
| **Events** | ✅ | ✅ | ✅ | ✅ | Events can support goals and practice habits |
| **Journals** | ✅ | ❌ | ❌ | ✅ | Journals are user-specific only |
| **Choices** | ✅ | ✅ | ❌ | ✅ | Choices motivated by goals |
| **Principles** | ✅ | ✅ | ✅ | ✅ | Principles guide goals and habits |
| **Finance** | N/A | N/A | N/A | ❌ | Uses domain-specific date-range/category queries |

**When to Use CommonQueryRouteFactory:**

✅ **USE IT when domain has:**
- Standard user-owned entities (tasks, goals, habits, events, journals)
- Goal/habit relationship filtering (optional, configurable)
- Simple status-based filtering
- Queries follow pattern: "Get all X for user/goal/habit"

❌ **DON'T USE IT when domain has:**
- Complex query parameters (date ranges, category hierarchies, budget calculations)
- Domain-specific filtering logic (alignment scores, expression tracking)
- Specialized aggregations or computations
- Query patterns that don't fit user/goal/habit model

**Examples:**

```python
# ✅ GOOD FIT - Tasks domain
query_factory = CommonQueryRouteFactory(
    service=tasks_service,
    domain_name="tasks",
    supports_goal_filter=True,   # Simple: "tasks for this goal"
    supports_habit_filter=True,  # Simple: "tasks for this habit"
)

# ❌ BAD FIT - Finance domain
# Instead use manual routes:
@rt("/api/expenses/date-range")
async def get_expenses_by_date_range(request: Request):
    # Complex: date range + category + budget + reconciliation status
    start = request.query_params.get("start")
    end = request.query_params.get("end")
    category = request.query_params.get("category")
    ...
```

---

## 3. IntelligenceRouteFactory (Existing)

**Purpose:** Generate intelligence/analytics routes for domains

**Routes Generated:** (Depends on configuration)
- Knowledge analysis endpoints
- Performance metrics endpoints
- Behavioral insights endpoints

**Usage:** See `/core/infrastructure/routes/intelligence_route_factory.py`

**Domains Using It:** Intelligence services

---

## Factory Pattern Best Practices

### 1. Always Use CRUDRouteFactory First

**Every domain should start with:**
```python
# ========================================================================
# STANDARD CRUD ROUTES (Factory-Generated)
# ========================================================================

crud_factory = CRUDRouteFactory(...)
crud_factory.register_routes(app, rt)
```

### 2. Add CommonQueryRouteFactory for Standard Queries

**If domain has common query patterns:**
```python
# ========================================================================
# COMMON QUERY ROUTES (Factory-Generated)
# ========================================================================

query_factory = CommonQueryRouteFactory(...)
query_factory.register_routes(app, rt)
```

### 3. Add StatusRouteFactory for Status Changes (January 2026)

**Tasks, Goals, Habits, Events now use StatusRouteFactory:**
```python
# ========================================================================
# STATUS ROUTES (Factory-Generated)
# ========================================================================

status_factory = StatusRouteFactory(
    service=tasks_service,
    domain_name="tasks",
    transitions={
        "complete": StatusTransition(
            target_status="completed",
            requires_body=True,
            body_fields=["actual_minutes", "quality_score"],
            method_name="complete_task",
        ),
        "uncomplete": StatusTransition(
            target_status="in_progress",
            method_name="uncomplete_task",
        ),
    },
)
status_factory.register_routes(app, rt)
```

### 4. Keep Domain-Specific Routes Manual

**Routes that don't fit factory patterns:**
```python
# ========================================================================
# DOMAIN-SPECIFIC ROUTES (Manual)
# ========================================================================
# SECURITY: All UID-based routes verify user owns the entity before operating

@rt("/api/tasks/assign", methods=["POST"])
@boundary_handler()
async def assign_task_route(request: Request, uid: str) -> Result[Any]:
    """Assign task to user (requires ownership)."""
    user_uid = require_authenticated_user(request)

    # Verify user owns this task
    ownership = await tasks_service.verify_ownership(uid, user_uid)
    if ownership.is_error:
        return ownership

    body = await request.json()
    # Domain-specific parameters and logic
    return await tasks_service.assign_task_to_user(...)
```

**Examples of domain-specific routes:**
- Task assignment and dependencies
- Relationship creation (dependencies, links)
- Domain-specific analytics beyond standard patterns
- Bulk operations

### 5. Always Add Ownership Verification to Manual Routes

**All manual routes operating on user-owned entities must verify ownership:**

```python
from core.auth import require_authenticated_user

@rt("/api/{domain}/action", methods=["POST"])
@boundary_handler()
async def domain_action_route(request: Request, uid: str) -> Result[Any]:
    """Perform action (requires ownership)."""
    user_uid = require_authenticated_user(request)

    # Verify user owns this entity
    ownership = await service.verify_ownership(uid, user_uid)
    if ownership.is_error:
        return ownership

    # Safe to proceed - user owns this entity
    return await service.perform_action(uid, ...)
```

**Why this pattern?**
- Prevents IDOR (Insecure Direct Object Reference) attacks
- Returns 404 (not 403) to avoid revealing UID existence
- Consistent with factory-generated routes

**See:** `/docs/patterns/OWNERSHIP_VERIFICATION.md` for complete documentation

---

## Migration Statistics (Phase 1 Complete - 2025-11-18)

### Before Factories

**Total Lines:** ~3,500 lines of route definitions
- Manual CRUD routes: ~2,400 lines (16 domains × 150 lines)
- Manual query routes: ~1,100 lines (7 domains × ~160 lines)

### After Factories

**Total Lines:** ~1,200 lines (66% reduction)
- CRUD factory calls: ~240 lines (16 domains × 15 lines)
- Query factory calls: ~75 lines (5 domains × 15 lines)
- Domain-specific routes: ~885 lines (remaining unique logic)

**Lines Eliminated:** ~2,300 lines (66% reduction)

### Per-Domain Impact

| Domain | Before | After | Reduction |
|--------|--------|-------|-----------|
| **Tasks** | ~400 lines | ~150 lines | 62% |
| **Goals** | ~380 lines | ~140 lines | 63% |
| **Habits** | ~360 lines | ~130 lines | 64% |
| **Events** | ~340 lines | ~120 lines | 65% |
| **Finance** | ~320 lines | ~160 lines | 50% |
| **Journals** | ~280 lines | ~110 lines | 61% |
| **Choices** | ~280 lines | ~100 lines | 64% |

**Average Reduction:** 62% fewer lines per domain

---

## Testing

### Integration Tests

All factory-generated routes are covered by domain integration tests:

```bash
# Test all core domains
poetry run pytest tests/integration/test_tasks_core_operations.py       # 15 tests
poetry run pytest tests/integration/test_goals_core_operations.py       # 15 tests
poetry run pytest tests/integration/test_habits_core_operations.py      # 15 tests
poetry run pytest tests/integration/test_events_core_operations.py      # 15 tests
poetry run pytest tests/integration/test_choices_core_operations.py     # 12 tests
poetry run pytest tests/integration/test_principles_core_operations.py  # 15 tests

# Results: 87/87 passed ✅
```

### Manual HTTP Testing

Test factory-generated routes via curl:

```bash
# CRUD routes (CRUDRouteFactory)
curl "http://localhost:8000/api/tasks/get?uid=task:123"
curl "http://localhost:8000/api/tasks/list?limit=10&offset=0"

# Query routes (CommonQueryRouteFactory)
curl "http://localhost:8000/api/tasks/user?user_uid=user:mike"
curl "http://localhost:8000/api/tasks/goal?goal_uid=goal:fitness"
curl "http://localhost:8000/api/tasks/by-status?status=active"
```

---

## Migration Script

**Note:** This was a one-time migration script (January 2026) that has been completed. The pattern is now applied across all domains.

**Historical Usage:**
```bash
# Apply CommonQueryRouteFactory to all configured domains
poetry run python scripts/apply_query_factory.py

# Configuration in script:
DOMAIN_CONFIG = {
    "goals": {...},
    "habits": {...},
    "events": {...},
    # Add new domains here
}
```

**What It Does:**
1. Adds CommonQueryRouteFactory import
2. Adds factory registration after CRUD factory
3. Removes manual routes that are now generated
4. Adds comments noting factory-generated routes

---

## Future Enhancements

### Possible Additional Factories

1. **StatusUpdateRouteFactory**
   - Challenge: Domain-specific status logic
   - Feasibility: Low (too varied across domains)

2. **RelationshipRouteFactory**
   - Challenge: Different relationship types per domain
   - Feasibility: Medium (possible with configuration)

3. **BulkOperationsFactory**
   - Patterns: Bulk create, bulk update, bulk delete
   - Feasibility: High (very standardizable)

4. **AnalyticsRouteFactory**
   - Patterns: Date range queries, aggregations, metrics
   - Feasibility: Medium (some standardization possible)

---

## Lessons Learned (V3 Type Hints Migration)

**Failed Approach:** Leveraging FastHTML type hints for parameter extraction

**Why It Failed:**
- FastHTML type hints are designed for UI routes, not JSON APIs
- `-> Result[Any]` return type causes TypeError with type-hint-only routes
- Routes without `request: Request` parameter return HTML instead of JSON
- V2 pattern (manual extraction) is proven and works correctly

**Recommendation:** Stay with V2 pattern (CRUDRouteFactory + manual extraction)

---

## Quick Reference

### Adding Factory to New Domain

```python
# 1. Import factories
from core.infrastructure.routes import CRUDRouteFactory
from core.infrastructure.routes.query_route_factory import CommonQueryRouteFactory

# 2. Register CRUD factory
crud_factory = CRUDRouteFactory(
    service=domain_service,
    domain_name="domain",
    create_schema=DomainCreateRequest,
    update_schema=DomainUpdateRequest,
    uid_prefix="domain",
)
crud_factory.register_routes(app, rt)

# 3. Register query factory (if applicable)
query_factory = CommonQueryRouteFactory(
    service=domain_service,
    domain_name="domain",
    supports_goal_filter=True,
    supports_habit_filter=True,
)
query_factory.register_routes(app, rt)

# 4. Add domain-specific routes manually
@rt("/api/domain/custom-action", methods=["POST"])
@boundary_handler()
async def custom_action_route(request: Request, uid: str) -> Result[Any]:
    # Domain-specific logic (uid from query param)
    ...
```

---

## Summary

**Factory Pattern Achievement:**
- ✅ 2,400+ lines eliminated (66% reduction in route boilerplate)
- ✅ 100% CRUDRouteFactory coverage (16/16 domains)
- ✅ 100% CommonQueryRouteFactory coverage (7/7 activity domains)
- ✅ 100% ownership verification coverage (42/42 manual routes)
- ✅ Proven with 87/87 integration tests passing
- ✅ Easy to extend to new domains
- ✅ Self-documenting (factory calls explain structure)
- ✅ Multi-tenant security via ownership verification

**Coverage Breakdown:**
- **CRUDRouteFactory:** 16/16 domains (100%)
  - Tasks, Goals, Habits, Events, Finance, Choices, Principles
  - Journals, Knowledge, Learning Paths, Learning Steps
  - Askesis, MOC, Context Aware, System, Transcription
- **CommonQueryRouteFactory:** 7/7 activity domains (100%)
  - Tasks, Goals, Habits, Events, Journals, Choices, Principles
  - All activity domains now use consistent query patterns
  - Finance uses domain-specific queries (budget/category operations)

**V2 Pattern Confirmed:**
- ✅ Manual parameter extraction works reliably
- ✅ JSON responses work correctly
- ✅ No breaking URL changes
- ✅ Compatible with boundary_handler + Result[T]

**Next Steps:**
1. ✅ Query factory migration complete (7/7 activity domains)
2. ✅ Domain pairing architectural alignment complete (all 3 pairs aligned)
3. ✅ Goal/habit filter service methods implemented (2025-11-18)
   - ChoicesCoreService: `get_choices_for_goal()` - Graph query: `(goal)-[:MOTIVATED_BY_GOAL]->(choice)`
   - PrinciplesCoreService: `get_principles_for_goal()` - Graph query: `(goal)-[:GUIDED_BY_PRINCIPLE]->(principle)`
   - PrinciplesCoreService: `get_principles_for_habit()` - Graph query: `(habit)-[:ALIGNED_WITH_PRINCIPLE]->(principle)`
4. ✅ Ownership verification on all manual routes (2025-12-05)
   - 42 manual routes across 7 API files now verify ownership before operating
   - See `/docs/patterns/OWNERSHIP_VERIFICATION.md` for complete list
5. Consider BulkOperationsFactory for batch operations (future enhancement)
6. Continue using V2 pattern for all new domains

---

## See Also

### Route Factory Documentation

| Document | Purpose | When to Use |
|----------|---------|-------------|
| **This file** | **Complete guide** | Comprehensive documentation with migration stats, testing, and best practices |
| [ROUTE_FACTORIES.md](./ROUTE_FACTORIES.md) | Quick reference | Quick lookup of factory types, parameters, and usage patterns |

### Related Patterns

- `/docs/patterns/OWNERSHIP_VERIFICATION.md` - Ownership verification pattern
- `/docs/patterns/ERROR_HANDLING.md` - Result[T] error handling
- `/core/infrastructure/routes/crud_route_factory.py` - CRUDRouteFactory implementation
- `/core/infrastructure/routes/query_route_factory.py` - CommonQueryRouteFactory implementation

---

**Last Updated:** 2026-01-12
**Status:** Production Ready
**Tests:** 87/87 passing ✅
**Coverage:** 7/7 activity domains (100%), 42/42 manual routes secured

---

## Query Parameter Migration (2026-01-12)

All API routes have been standardized to use query parameters (`?uid=...`) instead of path parameters (`/{uid}`), following FastHTML's "query parameters preferred" pattern.

**Before:**
```python
@rt("/api/tasks/{uid}/complete")
async def complete_task(request):
    uid = request.path_params["uid"]
```

**After:**
```python
@rt("/api/tasks/complete", methods=["POST"])
async def complete_task(request, uid: str):
    # uid extracted from query params via type hint
```

**Benefits:**
- Consistent with FastHTML's preferred pattern
- Type hints provide automatic parameter extraction
- Cleaner route definitions
- Better alignment with FastHTML's philosophy
