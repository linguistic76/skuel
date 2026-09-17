# Async Testing with pytest-asyncio

## Core Philosophy

> "Async for I/O, sync for computation"

All SKUEL services are async (database operations). Use `@pytest.mark.asyncio` for any test calling async methods.

## pytest-asyncio Setup

### pyproject.toml Configuration

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = [
    "integration: integration tests (require Docker)",
    "slow: slow tests",
]
```

With `asyncio_mode = "auto"`, pytest-asyncio handles event loop creation automatically.

## Async Test Patterns

### Basic Async Test

```python
import pytest

@pytest.mark.asyncio
async def test_create_task(tasks_service, sample_task):
    # All SKUEL services are async
    result = await tasks_service.create(sample_task)

    assert result.is_ok
    assert result.value.title == sample_task.title
```

### Class-Based Async Tests

```python
@pytest.mark.asyncio
class TestTasksCRUD:
    """Mark class for all async tests inside."""

    async def test_create(self, tasks_service, sample_task):
        result = await tasks_service.create(sample_task)
        assert result.is_ok

    async def test_get(self, tasks_service, sample_task):
        # Setup
        created = await tasks_service.create(sample_task)
        assert created.is_ok

        # Test
        result = await tasks_service.get(created.value.uid)
        assert result.is_ok
```

## Async Fixtures

### Critical: Use @pytest_asyncio.fixture

```python
import pytest_asyncio

# CORRECT - async fixture
@pytest_asyncio.fixture
async def tasks_backend(neo4j_container):
    driver = AsyncGraphDatabase.driver(neo4j_container.get_connection_url())
    backend = UniversalNeo4jBackend[Task](driver, "Task", Task)
    yield backend
    await driver.close()


# WRONG - will cause "coroutine never awaited" errors
@pytest.fixture
async def tasks_backend(neo4j_container):  # Missing pytest_asyncio!
    ...
```

### Async Fixture with Cleanup

```python
@pytest_asyncio.fixture
async def clean_neo4j(neo4j_container):
    """Clean database before/after each test."""
    driver = AsyncGraphDatabase.driver(...)

    async def cleanup():
        async with driver.session() as session:
            await session.run("MATCH (n) WHERE NOT n:User DETACH DELETE n")

    await cleanup()  # Before test
    yield
    await cleanup()  # After test
    await driver.close()
```

## Event Loop Scoping

### Loop scope is configuration, not a fixture

pytest-asyncio ≥ 1.0 owns the event loops. `pyproject.toml` sets
`asyncio_default_fixture_loop_scope = "session"` and
`asyncio_default_test_loop_scope = "session"`, so every async fixture and test
runs on one session loop unless it says otherwise (`loop_scope=` on the
decorator). **Do not define an `event_loop` fixture** — pytest-asyncio never
requests one, so it would be an ordinary, unused fixture that only misleads.

```python
# Session-scoped container + session-scoped async driver, no loop plumbing
@pytest.fixture(scope="session")
def neo4j_container(): ...

@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def neo4j_driver(neo4j_uri):
    driver = AsyncGraphDatabase.driver(neo4j_uri)
    yield driver
    await driver.close()
```

## Common Patterns

### Testing Async Context Managers

```python
@pytest.mark.asyncio
async def test_with_transaction(neo4j_driver):
    async with neo4j_driver.session() as session:
        result = await session.run("RETURN 1 as value")
        record = await result.single()
        assert record["value"] == 1
```

### Waiting for Async Operations

```python
import asyncio

@pytest.mark.asyncio
async def test_async_batch_processing(service):
    # Create multiple tasks concurrently
    tasks = [
        service.create({"title": f"Task {i}"})
        for i in range(10)
    ]

    results = await asyncio.gather(*tasks)

    assert all(r.is_ok for r in results)
```

### Testing Timeouts

```python
import asyncio

@pytest.mark.asyncio
async def test_operation_timeout():
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            slow_operation(),
            timeout=1.0
        )
```

## Troubleshooting

### Event Loop Closed Error

```
RuntimeError: Event loop is closed
```

**Cause:** Fixture cleanup running after loop closed — a session-scoped async
fixture whose loop scope is narrower than its fixture scope.

**Fix:** Give the fixture the loop scope its lifetime needs:
```python
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def neo4j_driver(neo4j_uri): ...
```

### Coroutine Never Awaited

```
RuntimeWarning: coroutine 'test_example' was never awaited
```

**Cause:** Missing `@pytest.mark.asyncio` decorator.

**Fix:**
```python
@pytest.mark.asyncio  # Add this!
async def test_example():
    ...
```

### Fixture Scope Mismatch

```
ScopeMismatch: You tried to access the function-scoped fixture 'clean_neo4j'
with a session-scoped request object
```

**Cause:** Session fixture depending on function fixture.

**Fix:** Match fixture scopes or restructure dependencies:
```python
# Session fixture can only depend on session fixtures
@pytest_asyncio.fixture(scope="session")
async def neo4j_driver(neo4j_uri):  # neo4j_uri must be session-scoped
    ...
```

### Async Fixture Not Awaited

```
TypeError: object coroutine can't be used in 'await' expression
```

**Cause:** Using `@pytest.fixture` instead of `@pytest_asyncio.fixture`.

**Fix:**
```python
import pytest_asyncio

@pytest_asyncio.fixture  # Not @pytest.fixture
async def async_fixture():
    ...
```

## SKUEL-Specific Patterns

### Testing Services with Result[T]

```python
@pytest.mark.asyncio
async def test_service_returns_result(tasks_service):
    result = await tasks_service.create(task_data)

    # Result is returned immediately (no extra await)
    assert result.is_ok

    # Value is accessed synchronously
    task = result.value
    assert task.uid.startswith("task:")
```

### Testing Multiple Service Calls

```python
@pytest.mark.asyncio
async def test_cross_domain_flow(services, clean_neo4j):
    # Create goal first
    goal_result = await services.goals.create(goal_data)
    assert goal_result.is_ok

    # Create task linked to goal
    task_result = await services.tasks.create({
        "title": "Task",
        "goal_uid": goal_result.value.uid,
    })
    assert task_result.is_ok

    # Verify relationship
    linked = await services.goals.get_tasks(goal_result.value.uid)
    assert linked.is_ok
    assert task_result.value.uid in [t.uid for t in linked.value]
```

## Key Configuration

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "session"
asyncio_default_test_loop_scope = "session"
timeout = 120
timeout_func_only = true
filterwarnings = [
    # module-scoped ignores for third-party deprecation noise (neo4j, fastcore, unittest.mock) ...
    # ... and one escalation: a handler parameter FastHTML cannot bind (a `_request`) is an
    # error, so it fails the first test that registers its route. The decorator-injected
    # `current_user: Any = None` never reaches FastHTML's binder — `require_role` publishes the
    # handler's signature without it and refuses any other spelling at decoration.
    "error:.*has no type annotation and is not a recognised special name:UserWarning:fasthtml",
]
```

## Best Practices

1. **Always use `@pytest.mark.asyncio`** on async tests
2. **Use `@pytest_asyncio.fixture`** for async fixtures (not `@pytest.fixture`)
3. **Match fixture scopes** - session fixtures can only use session fixtures
4. **Provide session event loop** for session-scoped async fixtures
5. **Handle cleanup in fixtures** using try/finally or yield pattern
6. **Check Result[T] before accessing value** - prevents cryptic errors
