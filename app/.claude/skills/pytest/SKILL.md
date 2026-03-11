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
│   └── fluent_mocks.py         # Fluent API mocking
├── integration/
│   ├── conftest.py             # TestContainers, backends
│   └── test_*.py               # Real Neo4j tests
├── unit/
│   └── test_*.py               # Mocked backend tests
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

    # Act
    result = await tasks_service.update_status(
        task_uid,
        ActivityStatus.COMPLETED
    )

    # Assert
    assert result.is_ok
    assert result.value.status == ActivityStatus.COMPLETED
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
- `/docs/patterns/ERROR_HANDLING.md` - Result[T] pattern details
