---
related_skills:
- pytest
---
# SKUEL Testing Guide

## Quick Reference

**Skill:** [@pytest](.claude/skills/pytest/SKILL.md)

```bash
# Run integration tests (real Neo4j via Docker)
./dev test-integration

# Run unit tests (fast, no Docker)
./dev test-unit

# Run specific test files
uv run pytest tests/unit/test_tasks_service.py -v
uv run pytest tests/unit/test_tasks_scheduling_service.py -v

# Run with coverage
uv run pytest tests/integration/ --cov=core --cov-report=term-missing
```

## Test Suite Status

SKUEL runs two primary tiers, both gated in CI (`.github/workflows/ci.yml`):

- **Unit** (`tests/unit/`) — mock-based, no Docker. `./dev test-unit`
- **Integration** (`tests/integration/`) — real Neo4j via testcontainers. `./dev test-integration`

Run the full suite with `./dev test-all` (needs Docker), or the quick smoke subset
with `./dev test-quick`.

**Why integration tests are the primary tier:**
- Use a real database and services
- Exercise the actual graph-native architecture
- Relationship queries run against real edges, not mocked field access

## Test Categories

### By Type

| Category | Command | Notes |
|----------|---------|-------|
| **Integration** | `./dev test-integration` | Real Neo4j (Docker), ~60-90s |
| **Unit** | `./dev test-unit` | Mock-based, no Docker, fastest |
| **All** | `./dev test-all` | Full suite, needs Docker |

### By Domain

```bash
# Tasks domain (recurse, then filter by keyword — catches nested suites)
uv run pytest tests/unit/ -k "task" -v
uv run pytest tests/integration/ -k "task" -v

# Habits domain
uv run pytest tests/unit/ -k "habit" -v
uv run pytest tests/integration/ -k "habit" -v

# Goals domain
uv run pytest tests/unit/ -k "goal" -v
uv run pytest tests/integration/ -k "goal" -v

# All unit tests (pytest recurses into tests/unit/ subdirectories)
uv run pytest tests/unit/ -v
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

## Fixing Unit Tests

### Step-by-Step Process

**1. Identify Deprecated Field References**
```bash
# Search for specific deprecated fields
grep -r "prerequisite_knowledge_uids" tests/unit/
grep -r "applies_knowledge_uids" tests/unit/
grep -r "subtask_uids" tests/unit/
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

## Common Test Commands

### Quick Verification

```bash
# Run specific test file with verbose output
uv run pytest tests/unit/test_tasks_service.py -v

# Run specific test function
uv run pytest tests/unit/test_tasks_service.py::test_create_task_succeeds -v

# Show short traceback for failures
uv run pytest tests/unit/test_tasks_service.py --tb=short

# Run with print output visible
uv run pytest tests/unit/test_tasks_service.py -v -s
```

### Coverage Analysis

```bash
# Integration tests coverage
uv run pytest tests/integration/ --cov=core/services --cov-report=term-missing

# Specific service coverage
uv run pytest tests/integration/ -k "task" --cov=core/services/tasks --cov-report=html

# Open HTML coverage report
xdg-open htmlcov/index.html
```

### Filtering Tests

```bash
# Run only tests matching pattern
uv run pytest tests/ -k "task" -v

# Run only integration tests for tasks
uv run pytest tests/integration/ -k "task" -v

# Exclude a path from collection (e.g. the nested service suites)
uv run pytest tests/unit/ --ignore=tests/unit/services
```

### Parallel Execution

```bash
# Run tests in parallel (requires pytest-xdist)
uv run pytest tests/integration/ -n auto

# Limit parallel workers
uv run pytest tests/integration/ -n 4
```

## Test Philosophy

### Integration Tests First

**SKUEL prioritizes integration tests because:**

1. **Graph-Native Architecture** - Real Neo4j queries test actual behavior
2. **End-to-End Validation** - Service → Backend → Database → Result
3. **Relationship Testing** - Graph edges tested properly
4. **Fast & Reliable** - Quick feedback against real behavior

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

**When to Use:**
- Fast feedback on pure logic without spinning up Docker
- Complementary to integration tests, which remain the primary verification tier

## Test Organization

### Directory Structure

```
tests/
├── unit/                     # Mock-based, no Docker (./dev test-unit)
│   ├── test_tasks_service.py
│   ├── test_tasks_scheduling_service.py
│   └── ...
│
├── integration/              # Real Neo4j via testcontainers (./dev test-integration)
│   ├── routes/               # Route / API tests
│   ├── relationships/        # Graph-edge tests
│   ├── conftest.py           # Testcontainer lifecycle
│   └── ...
│
├── e2e/                      # End-to-end (local only)
└── conftest.py               # Shared fixtures
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

CI (`.github/workflows/ci.yml`, both jobs path-gated on Python changes) runs:

- **`unit_tests`** — `pytest tests/unit/` (mock-based, no Docker)
- **`integration_tests`** — `pytest tests/integration/ --override-ini=addopts=`;
  testcontainers boots the pinned Neo4j image on the runner's Docker daemon,
  identical to `./dev test-integration` locally. No `services:` block needed —
  the testcontainer fixture in `tests/integration/conftest.py` owns the
  container lifecycle.

e2e, benchmarks, and infrastructure tiers remain local-only (`./dev test` /
`scripts/run_tests.py all`).

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

**Cause:** Docker isn't ready. Integration tests boot an **ephemeral Neo4j
testcontainer** (`tests/integration/conftest.py`) on the Docker daemon — not the
Compose `skuel-neo4j` container — so the daemon must be running and able to start
the pinned Neo4j image.
**Fix:**
```bash
# Ensure the Docker daemon is running (testcontainers manages Neo4j itself)
docker info >/dev/null && echo "Docker OK"

# While the suite runs, watch the ephemeral Neo4j testcontainer start
docker ps

# If startup is the problem, inspect the most recent container's logs
docker logs "$(docker ps -lq)"
```

### Import Errors

**Cause:** Missing test dependencies
**Fix:**
```bash
uv sync
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
./dev test-integration  # Real Neo4j, primary verification tier
```

**For Comprehensive Verification:**
```bash
./dev test-all  # Full suite (needs Docker)
```

**For Specific Features:**
```bash
uv run pytest tests/unit/ -k "<feature>" -v
uv run pytest tests/integration/ -k "<feature>" -v
```

**Priority:** Integration tests are the primary verification tier; unit tests give
fast, Docker-free feedback on pure logic. Both are gated in CI.
