# SKUEL Development Phases - Unified Reference

**Purpose:** Central catalog of all phase-based migrations and development initiatives in SKUEL.

**Last Updated:** 2026-01-03

---

## Table of Contents

1. [Route Factory Migration](#1-route-factory-migration-phases-1-4)
2. [Refactoring Roadmap](#2-refactoring-roadmap-phases-1-3)
3. [Universal Backend Migration](#3-universal-backend-migration-phases-1-4)
4. [Mock Data Migration](#4-mock-data-migration-phases)
5. [Neo4j Label Standardization](#5-neo4j-label-standardization-phases-1-3)
6. [Return Value Error Fixes](#6-return-value-error-fix-phases-a-c)
7. [Test Migration (Graph-Native)](#7-test-migration-phase-2)
8. [Event-Driven Architecture](#8-event-driven-architecture-migration)

---

## 1. Route Factory Migration (Phases 1-4)

**Status:** ✅ COMPLETE
**Documentation:** `/docs/patterns/ROUTE_FACTORIES.md`
**Completion Date:** 2025-12-05
**Dependencies:** None (infrastructure layer, can run independently)

### Purpose
Eliminate route boilerplate by generating routes from configuration.

### Phases

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1 | CRUDRouteFactory - Basic CRUD operations | ✅ Complete |
| Phase 2 | StatusRouteFactory - Status changes | ✅ Complete |
| Phase 3 | CommonQueryRouteFactory - Query patterns | ✅ Complete |
| Phase 4 | AnalyticsRouteFactory - Domain analytics | ✅ Complete |

### Key Files
- `/adapters/inbound/common/route_factories.py`
- `/adapters/inbound/*_routes.py` (all domain routes)

### Migration Impact
- Reduced route code by ~60% (~2,400 lines eliminated)
- Standardized ownership verification across all domains
- Consistent error handling patterns

---

## 2. Refactoring Roadmap (Phases 1-3)

**Status:** 🟡 Phase 3 Ready
**Documentation:** `/docs/REFACTORING_CHECKLIST.md`
**Last Updated:** 2025-11-28
**Dependencies:**
  - Phase 3 should follow: Test Migration (#7) ✅ - refactoring needs test coverage
  - Phases 1-2 can run in parallel with other work

### Purpose
Systematic code quality improvement across the codebase.

### Phases

| Phase | Description | Effort | Status |
|-------|-------------|--------|--------|
| Phase 1 | Quick Wins (validation, metadata helpers) | 1-2 days | ✅ Complete |
| Phase 2 | Major Refactoring (business logic extraction) | 2-3 days | ✅ Complete |
| Phase 3 | Advanced Refactoring (query consolidation) | 1-2 days | 🟡 Ready |

### Phase 3 Projects
1. Query caching optimization
2. Event-driven architecture completion
3. Generic relationship service consolidation

### Expected Impact
- Code reduction: ~2,300 lines
- Quality improvement: HIGH
- Risk: MEDIUM

### Key Files
- See `/docs/REFACTORING_CHECKLIST.md` for complete task list

---

## 3. Universal Backend Migration (Phases 1-4)

**Status:** 🟢 Hybrid (Some complete, some pending)
**Documentation:** `/docs/patterns/MODEL_TO_ADAPTER_DYNAMIC_ARCHITECTURE.md`
**Last Updated:** 2025-11-28
**Dependencies:**
  - None (foundational layer)
  - **Blocks:** Graph-Native Pattern, Event-Driven (#8), Test Migration (#7)

### Purpose
Migrate all domains to use `UniversalNeo4jBackend[T]` directly, eliminating wrapper classes.

### Phases

| Phase | Domains | Status |
|-------|---------|--------|
| Phase 1 | Core Activity (Tasks, Goals, Habits) | ✅ Complete |
| Phase 2 | Secondary Activity (Events, Choices, Principles) | ✅ Complete |
| Phase 3 | Curriculum (KU, LS, LP) + MOC (Content/Org) | 🟡 Partial |
| Phase 4 | Special (Finance, User) | ⏸️ Deferred |

### Implementation Pattern

**Before (Wrapper Class):**
```python
class TasksBackend(UniversalNeo4jBackend[Task]):
    async def get_task_with_context(self, uid: str) -> Result[Task]:
        # Custom logic
        ...
```

**After (Direct Usage):**
```python
# services_bootstrap.py
tasks_backend = UniversalNeo4jBackend[Task](driver, "Task", Task)
tasks_service = TasksService(backend=tasks_backend)

# All queries now dynamic:
tasks = await backend.find_by(priority='high', due_date__gte=date.today())
```

### Key Benefits
- Zero wrapper code
- 100% dynamic field support
- Instant query capabilities via `find_by(field__operator=value)`
- Code reduction: 83% once fully migrated

### Known Issues
- ~46 MyPy errors (documented as acceptable technical debt)
- See: `/docs/technical_debt/MYPY_BACKEND_LIMITATIONS.md`

---

## 4. Mock Data Migration (Phases)

**Status:** ✅ COMPLETE (per CLAUDE.md)
**Documentation:** CLAUDE.md "Intelligence API Mock Data" section
**Completion Date:** 2025-12-02
**Dependencies:** None (data organization, can run independently)

### Purpose
Centralize mock intelligence data, separating it from route definitions.

### Pattern

**Before (Inline Mock Data):**
```python
@rt("/api/tasks/intelligence/upcoming")
async def get_upcoming_tasks(request):
    return {
        "tasks": [
            {"uid": "task.1", "title": "Sample Task", ...}
        ],
        "insights": [...],
    }
```

**After (Centralized):**
```python
# /core/mock_data/intelligence/tasks.py
def get_upcoming_tasks_mock(user_uid: str) -> dict:
    return {
        "tasks": [...],
        "insights": [...],
    }

# Route
@rt("/api/tasks/intelligence/upcoming")
async def get_upcoming_tasks(request):
    user_uid = require_authenticated_user(request)
    return get_upcoming_tasks_mock(user_uid)
```

### Migration Status
- 10 domains migrated
- 161 routes updated
- Centralized in `/core/mock_data/intelligence/`

### Future Work
Replace mock data with actual intelligence service calls.

---

## 5. Neo4j Label Standardization (Phases 1-3)

**Status:** ✅ COMPLETE
**Documentation:** `/docs/migrations/NEO4J_LABEL_STANDARDIZATION.md`
**Completion Date:** 2025-11-27
**Dependencies:** None (naming convention, can run independently)

### Purpose
Standardize Neo4j node labels across all domains.

### Phases

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 1 | Code Migration (string literals → enum) | ✅ Complete |
| Phase 2 | Neo4j Data Migration (add new labels) | ✅ Complete |
| Phase 3 | Index Migration (update indexes) | ✅ Complete |

### Standard Format
```cypher
:Task           # Entity nodes (PascalCase singular)
:User           # Not :user or :USER
:KnowledgeUnit  # Not :ku or :knowledge_unit
```

### Migration Impact
- ~667 code replacements across 100 files
- All indexes updated
- Consistent label conventions

---

## 6. Return Value Error Fix (Phases A-C)

**Status:** ✅ COMPLETE
**Documentation:** `/docs/technical_debt/RETURN_VALUE_ERRORS_ANALYSIS.md`
**Completion Date:** 2025-12-02
**Dependencies:** None (error pattern standardization, can run independently)

### Purpose
Fix services returning `Result.fail("string")` instead of using `Errors` factory.

### Phases

| Phase | Description | Status |
|-------|-------------|--------|
| Phase A | Identify violations (111 errors) | ✅ Complete |
| Phase B | Implement linter rule (SKUEL007) | ✅ Complete |
| Phase C | Fix all violations | ✅ Complete |

### Pattern Change

**Before (WRONG):**
```python
return Result.fail("User not found")  # ❌ String failures
```

**After (CORRECT):**
```python
from core.utils.result_simplified import Errors

return Result.fail(
    Errors.not_found(
        resource="user",
        identifier=user_uid
    )
)  # ✅ Structured error
```

### Enforcement
- SKUEL007 linter rule warns on string failures
- Auto-fix available: `./dev quality-fix`
- Result: 111 errors → 0 errors

---

## 7. Test Migration Phase 2 (Graph-Native Architecture)

**Status:** ✅ COMPLETE (isolation mode)
**Documentation:** `/TESTING.md`, `/home/mike/.claude/plans/phase2-graph-native-migration-plan.md`
**Completion Date:** 2026-01-03
**Dependencies:**
  - Requires: Universal Backend Migration (#3) ✅
  - Requires: Graph-Native Pattern (model changes) ✅
  - Requires: Event-Driven Architecture (#8) ✅
  - **Blocks:** Refactoring Roadmap Phase 3 (#2)

### Purpose
Update unit tests to reflect graph-native relationship architecture.

### Final Results (January 3, 2026)

| Test Category | Status |
|--------------|--------|
| Full Test Suite | ✅ **1863 passed**, 19 skipped, 0 failed |
| Route Integration Tests | ✅ 98 tests pass (events, habits, goals, finance APIs) |
| All Other Tests | ✅ All pass |

### Fixes Applied

1. ✅ Added `lp_relationship_service` fixture to conftest.py
2. ✅ Added `create_relationship` and `count_relationships` helpers
3. ✅ Fixed ReportService constructor (journals_service → transcript_processor)
4. ✅ Fixed relationship tests to use RelationshipName enum for method calls
5. ✅ Fixed tasks_core_service.py query RETURN clause for `related_tasks`
6. ✅ Fixed goals_core_service.py query RETURN clause for `related_goals`
7. ✅ Fixed test_rich_context_pattern.py goal test milestone assertions
8. ✅ Fixed test_curriculum_rich_context.py repo → backend references

### Remaining Work

**Route Test Isolation Issue:** ✅ RESOLVED (2026-01-03)
- Root cause: `asyncio.get_event_loop().run_until_complete()` pattern in sync tests
- Fix: Converted all affected test files to proper async tests with `async def` and `await`
- Files fixed (91 total failures resolved):
  - test_tasks_api.py (33 tests)
  - test_events_api.py (21 failures → 0)
  - test_habits_api.py (19 failures → 0)
  - test_goals_api.py (25 failures → 0)
  - test_finance_api.py (26 failures → 0)
- Pattern applied: Added `pytestmark = pytest.mark.asyncio`, converted to `async def`, replaced `run_until_complete()` with `await`
- Result: **1863 passed, 19 skipped, 0 failed** (full test suite)

---

## 8. Event-Driven Architecture Migration

**Status:** ✅ COMPLETE
**Documentation:** `/docs/patterns/event_driven_architecture.md`
**Completion Date:** 2026-01-03
**Dependencies:**
  - Requires: Universal Backend Migration (#3) ✅
  - Requires: Graph-Native Pattern (cleaner event payloads) ✅
  - **Blocks:** Test Migration (#7) ✅

### Purpose
Migrate from direct service dependencies to event-driven architecture.

### Pattern Change

**Before (Direct Dependencies):**
```python
class TasksService:
    def __init__(self, backend, context_service, user_service):
        self.context_service = context_service
        self.user_service = user_service

    async def create_task(self, ...):
        # Direct calls
        await self.context_service.invalidate_context(user_uid)
        await self.user_service.update_stats(user_uid)
```

**After (Event-Driven):**
```python
class TasksService:
    def __init__(self, backend, event_bus):
        self.event_bus = event_bus

    async def create_task(self, ...):
        # Publish event
        await self.event_bus.publish_async(TaskCreated(task_uid, user_uid))

        # Other services subscribe:
        # - UserContextService listens to TaskCreated → invalidates cache
        # - UserStatsService listens to TaskCreated → updates stats
```

### Benefits
- Zero coupling between services
- Easy testing (mock event bus only)
- Flexible bootstrap (any initialization order)
- Full audit trail

### Migration Status (All 7 Activity Domains Complete)

| Service | Events Published |
|---------|-----------------|
| TasksCoreService | TaskCreated, TaskUpdated, TaskDeleted, TaskPriorityChanged, TasksBulkCompleted, KnowledgeAppliedInTask |
| GoalsCoreService | GoalCreated, GoalAchieved, GoalProgressUpdated, GoalAbandoned |
| HabitsCoreService | HabitCreated (+ streak events via HabitsProgressService) |
| EventsCoreService | CalendarEventCreated, CalendarEventUpdated, CalendarEventCompleted, CalendarEventDeleted, CalendarEventRescheduled |
| ChoicesCoreService | ChoiceCreated, ChoiceUpdated, ChoiceDeleted, ChoiceOutcomeRecorded, ChoiceMade, KnowledgeInformedChoice |
| PrinciplesCoreService | PrincipleCreated, PrincipleUpdated, PrincipleDeleted, PrincipleStrengthChanged |
| FinanceCoreService | ExpenseCreated, ExpenseUpdated, ExpensePaid, ExpenseDeleted |

### Event Subscriptions (37 total in services_bootstrap.py)
- Context invalidation handlers for all 7 domains
- Cross-domain event subscriptions (Task→Goal, Habit→Goal, Event→KU, etc.)
- Substance tracking events
- Analytics subscriptions

---

## Phase Summary Table

| # | Phase System | Status | Tests Affected | Priority |
|---|--------------|--------|----------------|----------|
| 1 | Route Factory Migration | ✅ Complete | 0 | Low |
| 2 | Refactoring Roadmap | 🟡 Phase 3 Ready | 0 | Medium |
| 3 | Universal Backend | 🟢 Hybrid | ~46 MyPy warnings | Low |
| 4 | Mock Data Migration | ✅ Complete | 0 | Low |
| 5 | Neo4j Label Standardization | ✅ Complete | 0 | Low |
| 6 | Return Value Error Fixes | ✅ Complete | 0 | Low |
| 7 | Test Migration Phase 2 | ✅ Complete | 0 | Low |
| 8 | Event-Driven Architecture | ✅ Complete | 0 | Low |

**Legend:**
- ✅ Complete - Fully implemented and verified
- 🟢 Hybrid - Partially complete, stable in production
- 🟡 In Progress - Active work ongoing
- ⏸️ Deferred - Planned but not started

---

## Phase Naming Conventions

When adding new phases to SKUEL:

1. **Use descriptive names** - "Route Factory Migration" not "Migration Phase 1"
2. **Document in this file** - Update `/docs/PHASES.md` immediately
3. **Update CLAUDE.md** - Add brief summary with `**See:**` pointer
4. **Create ADR if architectural** - Document decision rationale in `/docs/decisions/`
5. **Track in relevant docs** - Link from architecture/pattern docs

**Example:**
```markdown
## Curriculum Refactor (Phases 1-3)

**Status:** 🟡 Phase 2
**Documentation:** `/docs/architecture/CURRICULUM_REFACTOR.md`
**ADR:** `/docs/decisions/ADR-XXX-curriculum-refactor.md`
```

---

## Related Documentation

- `/docs/PHASE_DEPENDENCIES.md` - **Dependency graph between phases**
- `/TESTING.md` - Test suite status and strategy
- `/CLAUDE.md` - Quick reference (points here for phase details)
- `/docs/INDEX.md` - Complete documentation index
- `/docs/patterns/` - Implementation patterns
- `/docs/decisions/` - Architecture Decision Records (ADRs)
- `/docs/REFACTORING_CHECKLIST.md` - Phase 2 refactoring tasks
- `/docs/migrations/` - Migration guides and scripts

---

## Maintenance Notes

**When to Update This File:**
1. New phase system introduced → Add new section
2. Phase status changes → Update status icon and table
3. Phase completes → Update completion date, move to "Complete"
4. Major milestone reached → Document in relevant section

**Cross-Reference Check:**
- Ensure all `/docs/decisions/ADR-*.md` references are valid
- Verify all file paths exist
- Update CLAUDE.md summary section when this file changes

**Last Full Review:** 2026-01-03
