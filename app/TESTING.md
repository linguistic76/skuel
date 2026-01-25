# SKUEL Testing Guide

**Last Updated:** January 3, 2026

## Quick Reference

```bash
# RECOMMENDED: Run integration tests (100% passing in isolation)
./dev test-integration

# Run unit tests (100% passing)
./dev test-unit

# Run specific test files
poetry run pytest tests/test_tasks_service.py -v
poetry run pytest tests/test_tasks_scheduling_service.py -v

# Run with coverage
poetry run pytest tests/integration/ --cov=core --cov-report=term-missing
```

## Test Suite Status

### ✅ Unit Tests - 100% Passing

**Status:** 1,209/1,209 passing (100%)
**Speed:** ~30 seconds
**Reliability:** Fully passing

```bash
# Quick command
./dev test-unit

# Direct command
poetry run pytest tests/ --ignore=tests/integration/ -v
```

### ✅ Integration Tests - 100% Passing (in isolation)

**Status:** 654/654 passing (100% in isolation)
**Speed:** ~60-90 seconds
**Reliability:** Fully passing when run independently

```bash
# Quick command
./dev test-integration

# Direct command
poetry run pytest tests/integration/ -v
```

**Why Integration Tests Pass:**
- Use real database and services
- Test actual graph-native architecture
- No reliance on deprecated field access
- RelationshipService handles all graph queries correctly

### ✅ Route Tests - Fully Passing

**Status:** All route tests pass (isolation issue resolved)
**Fix Applied:** January 3, 2026
**Root Cause:** Deprecated `asyncio.get_event_loop().run_until_complete()` pattern

```bash
# Full suite now passes
poetry run pytest tests/ -v  # ✅ 1863 passed, 19 skipped, 0 failed
```

**Files Fixed (91 failures resolved):**
- test_tasks_api.py (33 tests)
- test_events_api.py (21 failures → 0)
- test_habits_api.py (19 failures → 0)
- test_goals_api.py (25 failures → 0)
- test_finance_api.py (26 failures → 0)

**Pattern Applied:**
- Added `pytestmark = pytest.mark.asyncio` at module level
- Converted `def test_*` to `async def test_*`
- Replaced `run_until_complete()` with `await`

### 🎯 Comprehensive Suite Summary

| Category | Status |
|----------|--------|
| **Full Test Suite** | ✅ **1863 passed, 19 skipped, 0 failed** |
| Unit Tests | ✅ All pass |
| Integration Tests | ✅ All pass |
| Route Tests | ✅ All pass (isolation issue resolved) |

**Speed:** ~77 seconds

### Recently Fixed (January 3, 2026)

**Async Test Pattern Fix (91 failures → 0):**
- ✅ Fixed test_tasks_api.py, test_events_api.py, test_habits_api.py, test_goals_api.py, test_finance_api.py
- ✅ Pattern: `pytestmark = pytest.mark.asyncio` + `async def` + `await`
- ✅ Replaced deprecated `asyncio.get_event_loop().run_until_complete()` pattern

**Graph-Native Migration Test Fixes:**
- ✅ Added `lp_relationship_service` fixture to conftest.py
- ✅ Added `create_relationship` and `count_relationships` test helpers
- ✅ Fixed ReportService constructor (journals_service → transcript_processor)
- ✅ Fixed relationship tests to use RelationshipName enum
- ✅ Fixed tasks_core_service.py query RETURN clause for `related_tasks`
- ✅ Fixed goals_core_service.py query RETURN clause for `related_goals`
- ✅ Fixed test_rich_context_pattern.py goal test milestone assertions
- ✅ Fixed test_curriculum_rich_context.py repo → backend references

**Documentation:** See `/docs/PHASES.md` Section 7 for full migration details

---

## Test Categories

### By Type

| Category | Command | Tests | Pass Rate | Speed |
|----------|---------|-------|-----------|-------|
| **Integration** | `./dev test-integration` | 654 | 100% | Fast (60-90s) |
| **Unit** | `./dev test-unit` | 1,209 | 100% | Fast (30s) |
| **All** | `./dev test-all` | 1,863 | **100%** | Fast (~77s) |

### By Domain

```bash
# Tasks domain
poetry run pytest tests/test_tasks*.py -v
poetry run pytest tests/integration/test_tasks*.py -v

# Habits domain
poetry run pytest tests/test_habits*.py -v
poetry run pytest tests/integration/test_habits*.py -v

# Goals domain
poetry run pytest tests/test_goals*.py -v
poetry run pytest tests/integration/test_goals*.py -v

# All services
poetry run pytest tests/test_*_service.py -v
```

## Understanding Test Failures

### Phase 2 Migration Issues

**Root Cause:** Phase 2 moved relationship fields from models to graph edges

**Before Phase 2:**
```python
# Relationships stored as UID lists in model
task.prerequisite_knowledge_uids  # ['ku.python.basics']
task.applies_knowledge_uids       # ['ku.python.async']
```

**After Phase 2:**
```python
# Relationships stored as Neo4j graph edges
# Query via RelationshipService
relationship_service.get_task_prerequisite_knowledge(task_uid)
relationship_service.get_task_knowledge(task_uid)
```

**Impact on Tests:**
- Unit tests with old mock data fail
- Tests trying to access removed fields fail
- Integration tests pass (use real graph queries)

### Event-Driven Architecture Changes

**Old Pattern (Direct Dependencies):**
```python
class TasksService:
    def __init__(self, backend, context_service):
        self.context_service = context_service

    async def create_task(self, ...):
        # Direct invalidation
        await self.context_service.invalidate_context(user_uid)
```

**New Pattern (Events):**
```python
class TasksService:
    def __init__(self, backend, event_bus):
        self.event_bus = event_bus

    async def create_task(self, ...):
        # Publish event
        await self.event_bus.publish_async(TaskCreated(...))
        # Context invalidation handled by event subscriber
```

**Impact on Tests:**
- Tests expecting direct `context_service` calls fail
- Remove assertions for `mock_context_service.invalidate_context()`
- Document event-driven behavior in test comments

### Test Failure Patterns (Detailed Analysis - 2026-01-03)

**Pattern #1: AsyncMock Initialization Issues (~33 tests)**

**Problem:** AsyncMock created without `return_value` parameter causes unawaited coroutine warnings.

**Error Message:**
```
RuntimeWarning: coroutine 'AsyncMockMixin._execute_mock_call' was never awaited
assert False
 +  where False = Result(..., _error=<coroutine object>).is_ok
```

**Fix:**
```python
# ❌ BEFORE
backend.create_task = AsyncMock()
mock_backend.create_task.return_value = Result.ok(data)  # Too late!

# ✅ AFTER
backend.create_task = AsyncMock(return_value=Result.ok({}))
```

**Affected Files:**
- `tests/test_tasks_core_service.py` (lines 38-43)
- `tests/test_habits_completion_service.py` (lines 29-38)

---

**Pattern #2: Service Constructor Parameter Mismatches (~27 tests)**

**Problem:** Test fixtures use outdated parameter names from refactored services.

**Example:**
```python
# ❌ BEFORE
AssignmentProcessorService(
    audio_service=mock_audio_service  # Wrong parameter name
)

# ✅ AFTER
AssignmentProcessorService(
    transcription_service=mock_transcription_service  # Correct per ADR-019
)
```

**Affected Files:**
- `tests/integration/test_option_a_journals_processing.py` (lines 106-177)

---

**Pattern #3: Invalid Enum Values & Past Dates (~15 tests)**

**Problem #1:** Tests use "reflection" context which is not in EntityType enum.
**Problem #2:** Hardcoded 2025 dates now fail validation (today is 2026-01-03).

**Fix:**
```python
# ❌ BEFORE
parse_activity_line("- [ ] Meeting @context(event) @when(2025-11-27T09:30)")
parse_activity_line("- [ ] Daily reflection @context(reflection)")  # Invalid enum

# ✅ AFTER
from datetime import timedelta
future_date = datetime.now() + timedelta(days=30)
when_str = future_date.strftime("%Y-%m-%dT%H:%M")
parse_activity_line(f"- [ ] Meeting @context(event) @when({when_str})")
parse_activity_line("- [ ] Daily journal @context(journal)")  # Valid enum
```

**Affected Files:**
- `tests/test_dsl_parser.py` (search for "2025-", "reflection")
- `tests/test_dsl_integration.py` (search for "2025-")
- `tests/test_graphql_queries.py` (search for "2025-")

---

**Pattern #4: Missing Facade Method Delegation (~3 tests)**

**Problem:** `KuService` facade missing `search` attribute delegation to `KuSearchService`.

**Fix:**
```python
# In KuService.__init__():
self.search = ku_search_service  # ✅ Add convenience delegation
```

**Affected Files:**
- `tests/test_ku_search_service.py`
- `core/services/ku/ku_service.py` (fix location)

---

**Pattern #5: Integration Route Cascade Failures (~388 tests)**

**Status:** Under investigation - likely cascade failures from Patterns #1-4.

**Recommendation:** Fix Patterns #1-4 first, then re-run to see if cascade failures resolve.

**Affected Files:**
- `tests/integration/routes/test_finance_api.py` (78 failures)
- `tests/integration/routes/test_tasks_api.py` (75 failures)
- `tests/integration/routes/test_goals_api.py` (75 failures)
- `tests/integration/routes/test_events_api.py` (63 failures)
- `tests/integration/routes/test_habits_api.py` (57 failures)

## Fixing Unit Tests

### Step-by-Step Process

**1. Identify Deprecated Field References**
```bash
# Search for specific deprecated fields
grep -r "prerequisite_knowledge_uids" tests/test_*.py
grep -r "applies_knowledge_uids" tests/test_*.py
grep -r "subtask_uids" tests/test_*.py
```

**2. Update Mock Data**
```python
# ❌ WRONG - Includes deprecated fields
task_dict = {
    "uid": "task-123",
    "title": "Test Task",
    "prerequisite_knowledge_uids": [],  # DEPRECATED!
    "applies_knowledge_uids": [],       # DEPRECATED!
}

# ✅ CORRECT - Only core fields
task_dict = {
    "uid": "task-123",
    "title": "Test Task",
    # Phase 2: Relationship fields removed
}
```

**3. Remove Field Access Assertions**
```python
# ❌ WRONG - Accessing removed field
assert task.prerequisite_knowledge_uids == expected_uids

# ✅ CORRECT - Document migration
# Phase 2: Relationship fields removed from Task model
# Query via TasksRelationshipService.get_task_prerequisite_knowledge()
```

**4. Remove Obsolete Service Calls**
```python
# ❌ WRONG - Expecting direct context invalidation
mock_context_service.invalidate_context.assert_called_once_with(user_uid)

# ✅ CORRECT - Document event-driven architecture
# Note: Context invalidation now happens via event-driven architecture
# TaskCreated events trigger user_service.invalidate_context() in bootstrap
```

### Example: Task Tests Cleanup (November 8, 2025)

**Files Fixed:**
- `/tests/test_tasks_service.py`
- `/tests/test_tasks_scheduling_service.py`

**Changes Made:**
1. Removed 10 deprecated fields from mock backend data
2. Removed assertions checking `prerequisite_knowledge_uids`
3. Removed assertions checking `applies_knowledge_uids`
4. Removed obsolete `mock_context_service` fixture
5. Fixed parameter name: `user_uid=` → `_user_uid=`

**Result:** 19/19 tests passing

**Full Details:** See `/tmp/test_cleanup_complete.md`

## Common Test Commands

### Quick Verification

```bash
# Run specific test file with verbose output
poetry run pytest tests/test_tasks_service.py -v

# Run specific test function
poetry run pytest tests/test_tasks_service.py::test_create_task_succeeds -v

# Show short traceback for failures
poetry run pytest tests/test_tasks_service.py --tb=short

# Run with print output visible
poetry run pytest tests/test_tasks_service.py -v -s
```

### Coverage Analysis

```bash
# Integration tests coverage
poetry run pytest tests/integration/ --cov=core/services --cov-report=term-missing

# Specific service coverage
poetry run pytest tests/integration/test_tasks*.py --cov=core/services/tasks --cov-report=html

# Open HTML coverage report
xdg-open htmlcov/index.html
```

### Filtering Tests

```bash
# Run only tests matching pattern
poetry run pytest tests/ -k "task" -v

# Run only integration tests for tasks
poetry run pytest tests/integration/ -k "task" -v

# Exclude specific tests
poetry run pytest tests/ --ignore=tests/test_broken_service.py
```

### Parallel Execution

```bash
# Run tests in parallel (requires pytest-xdist)
poetry run pytest tests/integration/ -n auto

# Limit parallel workers
poetry run pytest tests/integration/ -n 4
```

## Test Philosophy

### Integration Tests First

**SKUEL prioritizes integration tests because:**

1. **Graph-Native Architecture** - Real Neo4j queries test actual behavior
2. **End-to-End Validation** - Service → Backend → Database → Result
3. **Relationship Testing** - Graph edges tested properly
4. **100% Passing** - Reliable, fast, comprehensive

**When to Use:**
- ✅ Verifying feature implementation
- ✅ Testing relationship queries
- ✅ Validating service integrations
- ✅ Continuous development workflow

### Unit Tests Second

**Unit tests are valuable for:**
- Testing pure business logic
- Validating error handling
- Testing edge cases
- Isolated component behavior

**Current Challenge:**
- Many need Phase 2 migration updates
- Use integration tests as primary verification
- Fix unit tests systematically over time

## Test Organization

### Directory Structure

```
tests/
├── integration/              # ✅ 434 tests, 100% passing
│   ├── test_tasks_integration.py
│   ├── test_habits_integration.py
│   ├── test_goals_integration.py
│   └── ...
│
├── test_tasks_service.py     # ✅ Unit tests (19 passing)
├── test_tasks_scheduling_service.py  # ✅ Unit tests (19 passing)
├── test_habits_service.py    # ⚠️ Needs Phase 2 migration
├── test_goals_service.py     # ⚠️ Needs Phase 2 migration
└── ...
```

### Test Naming Conventions

```python
# Integration tests
def test_create_task_with_relationships_integration():
    """Integration test - uses real database and services"""

# Unit tests
def test_create_task_success():
    """Unit test - uses mocks"""

# Service tests
def test_tasks_service_creation():
    """Service-level test"""
```

## Continuous Integration

### Recommended CI Pipeline

```yaml
# Example GitHub Actions workflow
test:
  runs-on: ubuntu-latest
  services:
    neo4j:
      image: neo4j:5.15.0
      ports:
        - 7687:7687
  steps:
    - uses: actions/checkout@v3
    - name: Run Integration Tests
      run: ./dev test-integration
    - name: Run Comprehensive Suite
      run: ./dev test
```

### Pre-Commit Hooks

```bash
# .git/hooks/pre-commit
#!/bin/bash
./dev format-check
./dev lint
./dev test-quick
```

## Troubleshooting

### Tests Hang or Timeout

**Cause:** Neo4j connection issues
**Fix:**
```bash
# Check Neo4j status
neo4j status

# Restart Neo4j
neo4j restart

# Verify connection
poetry run python -c "from neo4j import GraphDatabase; driver = GraphDatabase.driver('bolt://localhost:7687', auth=('neo4j', 'password')); driver.verify_connectivity(); print('Connected!')"
```

### Import Errors

**Cause:** Missing test dependencies
**Fix:**
```bash
poetry install --with dev
```

### Fixture Errors

**Cause:** Shared database state between tests
**Fix:**
```python
# Use proper fixture scoping
@pytest.fixture(scope="function")  # New instance per test
def backend():
    ...

# Clean up after tests
@pytest.fixture(autouse=True)
async def cleanup():
    yield
    # Clean up code
```

### Mock Issues

**Cause:** Using deprecated field patterns
**Fix:** Follow "Fixing Unit Tests" section above

## Summary

**For Daily Development:**
```bash
./dev test-integration  # Fast, reliable, 100% passing
```

**For Comprehensive Verification:**
```bash
./dev test  # ~95% passing, includes most tests
```

**For Specific Features:**
```bash
poetry run pytest tests/test_<feature>*.py -v
```

**Current Status:**
- ✅ Integration tests: 100% passing (434/434)
- ✅ Task unit tests: 100% passing (19/19) - Fixed Nov 8, 2025
- ⚠️ Other unit tests: Variable - Need Phase 2 migration updates
- 🎯 Overall: ~95% of meaningful tests passing

**Priority:** Focus on integration tests, fix unit tests systematically over time.
