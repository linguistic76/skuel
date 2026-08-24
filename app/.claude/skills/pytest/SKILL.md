---
name: pytest
description: SKUEL testing patterns - fixtures, async testing, mocking with Result[T]. Use when writing tests, debugging failures, or setting up test infrastructure.
allowed-tools: Read, Grep, Glob
---

# pytest: SKUEL Testing Patterns

## Core Philosophy

> "Test behavior through Result[T], not implementation"

All SKUEL services return `Result[T]`. Tests verify success via `result.is_ok` and access values via `result.value`. Never test internal state - test the contract.

## SKUEL Test Architecture

```
tests/
├── conftest.py                 # Session fixtures (app, auth clients)
├── fixtures/
│   └── service_factories.py    # Mock creation utilities
├── helpers/
├── integration/
│   ├── conftest.py             # TestContainers, backends
│   └── test_*.py               # Real Neo4j tests
├── unit/
│   ├── scripts/                # Linter unit tests (lint_skuel, cypher_linter)
│   ├── ui/                     # UI helper tests (enum_helpers, calendar, text, layout, buttons)
│   ├── services/               # Service unit tests (mocked backends)
│   └── test_*.py               # Other unit tests
└── templates/
    └── integration_test_template.py
```

## Quick Reference - Running Tests

| Command | Purpose |
|---------|---------|
| `uv run pytest` | Run all tests |
| `uv run pytest tests/unit/` | Unit tests only (fast) |
| `uv run pytest tests/integration/` | Integration tests (needs Docker) |
| `uv run pytest tests/unit/test_tasks_service.py` | Single file |
| `uv run pytest -k "test_create"` | Tests matching pattern |
| `uv run pytest -x` | Stop on first failure |
| `uv run pytest -v` | Verbose output |
| `uv run pytest --tb=short` | Short tracebacks |
| `uv run pytest --cov=core` | With coverage |

## Result[T] Testing Patterns

### Testing Success

```python
@pytest.mark.asyncio
async def test_create_task_success(tasks_service, sample_task):
    # Act
    result = await tasks_service.create(sample_task)

    # Assert - ALWAYS check is_ok first
    assert result.is_ok, f"Expected success, got: {result.error}"

    # Then access value
    task = result.value
    assert task.uid.startswith("task:")
    assert task.title == sample_task.title
```

### Testing Errors

```python
@pytest.mark.asyncio
async def test_get_task_not_found(tasks_service):
    # Act
    result = await tasks_service.get("nonexistent-uid")

    # Assert - use is_error (NOT is_err)
    assert result.is_error
    assert "not found" in result.error.message.lower()
```

### Testing Validation

```python
@pytest.mark.asyncio
async def test_create_task_validation_error(tasks_service):
    # Arrange - missing required field
    invalid_data = {"description": "No title"}

    # Act
    result = await tasks_service.create(invalid_data)

    # Assert
    assert result.is_error
    assert result.error.category == ErrorCategory.VALIDATION
```

## Markers Reference

| Marker | Purpose |
|--------|---------|
| `@pytest.mark.asyncio` | Required for async tests |
| `@pytest.mark.integration` | Integration tests (real Neo4j) |
| `@pytest.mark.slow` | Long-running tests |

```python
# pyproject.toml configuration
[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = [
    "integration: integration tests (require Docker)",
    "slow: slow tests",
]
```

## Assertions Quick Reference

```python
# Result assertions
assert result.is_ok                    # Success (NEVER .is_err)
assert result.is_error                 # Failure
assert result.value == expected        # Value access
assert result.error.category == ...    # Error category

# Standard assertions
assert task.title == "Expected"        # Equality
assert task in tasks                   # Containment
assert len(tasks) == 5                 # Length
assert task.is_active                  # Boolean

# Exception testing
with pytest.raises(ValueError, match="invalid"):
    service.validate(bad_data)

# Approximate floats
assert task.progress == pytest.approx(0.75, rel=0.01)
```

## Parametrized Tests

```python
@pytest.mark.parametrize("priority,expected_color", [
    (Priority.LOW, "gray"),
    (Priority.MEDIUM, "blue"),
    (Priority.HIGH, "orange"),
    (Priority.URGENT, "red"),
])
def test_priority_colors(priority, expected_color):
    assert priority.get_color() == expected_color


@pytest.mark.parametrize("status,should_be_terminal", [
    pytest.param(ActivityStatus.PENDING, False, id="pending"),
    pytest.param(ActivityStatus.COMPLETED, True, id="completed"),
    pytest.param(ActivityStatus.CANCELLED, True, id="cancelled"),
])
def test_status_is_terminal(status, should_be_terminal):
    assert status.is_terminal() == should_be_terminal
```

## Test Naming Convention

```python
# Pattern: test_{action}_{expected_outcome}
def test_create_task_returns_success(): ...
def test_create_task_with_invalid_data_fails_validation(): ...
def test_get_task_when_exists_returns_task(): ...
def test_get_task_when_missing_returns_not_found(): ...
def test_update_task_status_triggers_event(): ...
```

## Arrange-Act-Assert Pattern

```python
@pytest.mark.asyncio
async def test_update_task_status(tasks_service, sample_task):
    # Arrange
    created = await tasks_service.create(sample_task)
    assert created.is_ok
    task_uid = created.value.uid

    # Act — the domain's one update path, with a typed intent (ADR-066). There is no
    # generic status write: the status chokepoint owns the guard its write is evaluated
    # against (ADR-087), so `BaseService.update_status` was deleted.
    result = await tasks_service.update_task(
        task_uid,
        TaskUpdateIntent(status=EntityStatus.COMPLETED.value),
    )

    # Assert
    assert result.is_ok
    assert result.value.status == EntityStatus.COMPLETED
```

## Integration Test Pattern

```python
@pytest.mark.asyncio
@pytest.mark.integration
class TestTasksCRUD:
    """Test complete CRUD flow with real Neo4j."""

    async def test_create_task(self, tasks_backend, clean_neo4j):
        # Arrange
        task = Task(
            uid="task:test_1",
            title="Test Task",
            priority=Priority.HIGH,
        )

        # Act
        result = await tasks_backend.create(task)

        # Assert
        assert result.is_ok, f"Create failed: {result.error}"
        assert result.value.uid == "task:test_1"
```

### Guard tests: where mocks are blind

A mocked backend (`AsyncMock`) resolves **any** attribute, so it returns success for a
backend method that does not exist — hiding missing-method bugs (e.g. a service calling
`getattr(backend, "link_task_to_<key>")`). Round-trip behaviour against a **real Neo4j**
is the only thing that catches this class of bug. When you fix one:

1. Write the guard as an **integration** test that creates the edge/row and reads it
   back (e.g. `backend.get_relationships(rel_type=...)`), not a mock assertion.
2. **Prove it fails first** — temporarily restore the broken code and confirm the test
   goes red, then revert. A regression test never shown to fail against the bug is
   theatre.

See `tests/integration/test_task_dependency_edge_roundtrip.py` for a worked example.

## SKUEL-Specific Patterns

### Testing with Ownership

```python
@pytest.mark.asyncio
async def test_get_for_user_returns_owned_entity(
    tasks_service,
    sample_task,
    test_user_uid
):
    # Arrange - create task owned by user
    created = await tasks_service.create(sample_task, user_uid=test_user_uid)
    assert created.is_ok

    # Act - get as same user
    result = await tasks_service.get_for_user(
        created.value.uid,
        test_user_uid
    )

    # Assert
    assert result.is_ok
    assert result.value.uid == created.value.uid


async def test_get_for_user_returns_not_found_for_other_user(
    tasks_service,
    sample_task,
):
    # Arrange - create task for user A
    created = await tasks_service.create(sample_task, user_uid="user.a")
    assert created.is_ok

    # Act - try to get as user B
    result = await tasks_service.get_for_user(
        created.value.uid,
        "user.b"
    )

    # Assert - returns NotFound, not Forbidden
    assert result.is_error
    assert "not found" in result.error.message.lower()
```

### Testing Event Publishing

```python
@pytest.mark.asyncio
async def test_complete_task_publishes_event(
    tasks_service,
    mock_event_bus,
    sample_task
):
    # Arrange
    created = await tasks_service.create(sample_task)
    assert created.is_ok

    # Act
    result = await tasks_service.complete(created.value.uid)

    # Assert
    assert result.is_ok
    mock_event_bus.publish_async.assert_called_once()
    event = mock_event_bus.publish_async.call_args[0][0]
    assert isinstance(event, TaskCompleted)
```

## Pure Helper Unit Tests

For pure functions (no I/O), test by calling directly with synthetic data:

```python
# Linter rule tests — instantiate SkuelLinter, call _check_* with synthetic content
from lint_skuel import SkuelLinter
linter = SkuelLinter(root_dir=Path("/fake"), rules_filter=["SKUEL003"])
linter._check_is_err_usage(fp, rel, content, lines)
assert len(linter.result.violations) == 1

# UI helper tests — call bridge functions with valid/invalid strings
from ui.enum_helpers import get_status_badge_class
assert get_status_badge_class("active") != ""
assert get_status_badge_class("invalid") == "bg-gray-100 text-gray-600 border-gray-200"

# Calendar component tests — build frozen CalendarItem fixtures directly
from core.models.event.calendar_models import CalendarItem, CalendarItemType
item = CalendarItem(uid="task-task_1", source_uid="task_1", item_type=CalendarItemType.TASK,
                    title="Test", start_time=start, end_time=end)
assert "hx-get" in to_xml(_event_chip(item))
```

**Coverage:** 276 tests across 7 files cover linters (SKUEL001-017, CYP001-009), UI helpers (enum bridges, calendar components, typography, layout, buttons).

## Learning Loop Service Tests

The core learning-loop services have dedicated unit tests using the `_make_service()` helper pattern (no fixtures — inline construction):

| Service | Test File | Tests | Pattern |
|---------|-----------|-------|---------|
| `TeacherReviewService` | `tests/unit/services/test_teacher_review_service.py` | 60 | 4 backend mocks (`_make_user_entry_backend()`, `_make_report_backend()`, `_make_exercise_backend()`, `_make_group_backend()`) with per-method `AsyncMock` return values |
| `AssessmentService` | `tests/unit/test_assessment_service.py` | 2 | Backend mock pattern (received-feedback read) |

**Key mocking patterns in these tests:**
- Backend method mocks: `backend.method_name = AsyncMock(return_value=Result.ok([...]))` for per-method return values
- Event verification: `event_bus.publish_async.assert_awaited_once()` + check event type/fields
- Access control: `_verify_teacher_has_group_access` returns `Result.fail(Errors.not_found(...))` — 404, not 403
- `_make_entity(**overrides)` helper using `MagicMock()` with attribute assignment (avoids frozen dataclass construction)

## Additional Resources

- [Fixtures Reference](fixtures-reference.md) - SKUEL fixture ecosystem
- [Async Testing](async-testing.md) - pytest-asyncio patterns
- [Mocking Patterns](mocking-patterns.md) - Service mocking

## Related Skills

- **[python](../python/SKILL.md)** - Python patterns tested
- **[result-pattern](../result-pattern/SKILL.md)** - All tests verify Result[T] outcomes

## Foundation

- **[python](../python/SKILL.md)** - Core Python patterns
- **[result-pattern](../result-pattern/SKILL.md)** - Understanding Result[T] for test assertions

## See Also

- `/tests/conftest.py` - Root fixtures
- `/tests/integration/conftest.py` - TestContainers setup
- `/tests/templates/integration_test_template.py` - Best practices template
- `/tests/unit/ui/test_cross_domain_consistency.py` - Cross-domain UI component consistency tests (PageHeader, EmptyState, StatsGrid, EntityRelationshipsSection across all 6 activity domains + 4 hub pages)
- `/docs/patterns/ERROR_HANDLING.md` - Result[T] pattern details
- `/docs/patterns/TESTING_PATTERNS.md` - Integration + unit testing patterns
- `/docs/patterns/linter_rules.md` - Linter rules (unit-tested)
