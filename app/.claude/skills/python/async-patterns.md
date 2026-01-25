# Async/Await Patterns

## Core Principle

> "Async for I/O, sync for computation"

Use `async def` when you need `await` inside the function. Everything else should be sync.

## Layer Guidelines

| Layer | Async | Sync | Rationale |
|-------|-------|------|-----------|
| **Database/Persistence** | 100% | 0% | All Neo4j operations require await |
| **Service Layer** | ~95% | ~5% | Most call backends; init/helpers are sync |
| **Data Conversion** | 0% | 100% | Pure type transformation, no I/O |
| **Domain Models** | 0% | 100% | Pure business logic |
| **Utilities** | ~5% | ~95% | Most are pure functions |

## Basic Patterns

### Async Service Methods

```python
class TasksService:
    async def get(self, uid: str) -> Result[Task]:
        """I/O operation - must be async"""
        return await self.backend.get(uid)

    async def create(self, data: dict) -> Result[Task]:
        """I/O operation - must be async"""
        validated = self.validate(data)  # Sync validation
        return await self.backend.create(validated)

    def validate(self, data: dict) -> dict:
        """Pure computation - should be sync"""
        return {k: v.strip() if isinstance(v, str) else v for k, v in data.items()}
```

### Awaiting Multiple Operations

```python
import asyncio

async def get_user_context(user_uid: str) -> Result[UserContext]:
    # Run independent operations concurrently
    tasks_result, goals_result, habits_result = await asyncio.gather(
        self.tasks_service.list_for_user(user_uid),
        self.goals_service.list_for_user(user_uid),
        self.habits_service.list_for_user(user_uid),
    )

    # Check all results
    if tasks_result.is_error:
        return tasks_result
    if goals_result.is_error:
        return goals_result
    if habits_result.is_error:
        return habits_result

    return Result.ok(UserContext(
        tasks=tasks_result.value,
        goals=goals_result.value,
        habits=habits_result.value,
    ))
```

### Sequential vs Concurrent

```python
# Sequential - when order matters or operations depend on each other
async def create_task_with_goal(data: dict) -> Result[Task]:
    # Goal must exist before creating task
    goal_result = await self.goals_service.get(data["goal_uid"])
    if goal_result.is_error:
        return goal_result

    # Now create task
    task_result = await self.tasks_service.create(data)
    if task_result.is_error:
        return task_result

    # Link task to goal
    return await self.tasks_service.link_to_goal(
        task_result.value.uid,
        data["goal_uid"]
    )


# Concurrent - when operations are independent
async def get_dashboard_data(user_uid: str) -> Result[Dashboard]:
    # These don't depend on each other
    stats, notifications, recommendations = await asyncio.gather(
        self.stats_service.get_user_stats(user_uid),
        self.notifications_service.get_unread(user_uid),
        self.recommendations_service.get_daily(user_uid),
    )
    return Result.ok(Dashboard(stats, notifications, recommendations))
```

## Error Handling with Gather

### Pattern 1: Fail on First Error

```python
async def get_all_required(user_uid: str) -> Result[tuple]:
    """Fails if any operation fails"""
    try:
        results = await asyncio.gather(
            self.service_a.get(user_uid),
            self.service_b.get(user_uid),
            self.service_c.get(user_uid),
        )
    except Exception as e:
        return Errors.system(str(e))

    # Check all results
    for result in results:
        if result.is_error:
            return result

    return Result.ok(tuple(r.value for r in results))
```

### Pattern 2: Collect Partial Results

```python
async def get_best_effort(user_uid: str) -> Result[PartialData]:
    """Returns partial data if some operations fail"""
    results = await asyncio.gather(
        self.required_service.get(user_uid),
        self.optional_service.get(user_uid),
        return_exceptions=True,
    )

    required_result = results[0]
    optional_result = results[1]

    # Required must succeed
    if isinstance(required_result, Exception) or required_result.is_error:
        return Errors.database("Required data unavailable")

    # Optional can fail gracefully
    optional_data = None
    if not isinstance(optional_result, Exception) and not optional_result.is_error:
        optional_data = optional_result.value

    return Result.ok(PartialData(
        required=required_result.value,
        optional=optional_data,
    ))
```

## Async Context Managers

```python
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

@asynccontextmanager
async def transaction() -> AsyncGenerator[Session, None]:
    """Async context manager for database transactions"""
    session = await get_session()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()

# Usage
async def create_with_transaction(data: dict) -> Result[Task]:
    async with transaction() as session:
        task = await session.create(data)
        await session.flush()
        return Result.ok(task)
```

## Async Iterators

```python
from collections.abc import AsyncIterator

async def stream_tasks(user_uid: str) -> AsyncIterator[Task]:
    """Stream tasks without loading all into memory"""
    async with self.driver.session() as session:
        result = await session.run(
            "MATCH (u:User {uid: $uid})-[:HAS_TASK]->(t:Task) RETURN t",
            uid=user_uid
        )
        async for record in result:
            yield Task.from_dict(record["t"])

# Usage
async def process_all_tasks(user_uid: str) -> None:
    async for task in stream_tasks(user_uid):
        await process(task)
```

## Common Anti-Patterns

### 1. Async Without Await

```python
# BAD - async keyword but no await
async def format_title(title: str) -> str:
    return title.strip().title()  # No I/O, should be sync

# GOOD
def format_title(title: str) -> str:
    return title.strip().title()
```

### 2. Blocking in Async

```python
import time

# BAD - blocks the event loop
async def slow_operation() -> None:
    time.sleep(5)  # Blocks everything!

# GOOD - use async sleep
async def slow_operation() -> None:
    await asyncio.sleep(5)

# For CPU-bound work, use thread pool
from concurrent.futures import ThreadPoolExecutor

async def cpu_bound_work() -> Result:
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        ThreadPoolExecutor(),
        heavy_computation,
    )
    return Result.ok(result)
```

### 3. Sequential When Concurrent is Possible

```python
# BAD - sequential for independent operations
async def get_stats(user_uid: str) -> Stats:
    tasks = await self.get_tasks(user_uid)  # Wait...
    goals = await self.get_goals(user_uid)  # Then wait...
    habits = await self.get_habits(user_uid)  # Then wait...
    return Stats(tasks, goals, habits)

# GOOD - concurrent for independent operations
async def get_stats(user_uid: str) -> Stats:
    tasks, goals, habits = await asyncio.gather(
        self.get_tasks(user_uid),
        self.get_goals(user_uid),
        self.get_habits(user_uid),
    )
    return Stats(tasks, goals, habits)
```

### 4. Not Awaiting Coroutines

```python
# BAD - coroutine never awaited
async def create_task(data: dict) -> Result[Task]:
    self.backend.create(data)  # Missing await! Returns coroutine
    return Result.ok(...)

# GOOD
async def create_task(data: dict) -> Result[Task]:
    result = await self.backend.create(data)
    return result
```

## Testing Async Code

```python
import pytest

@pytest.mark.asyncio
async def test_get_task(tasks_service):
    result = await tasks_service.get("test-uid")
    assert not result.is_error
    assert result.value.uid == "test-uid"

@pytest.mark.asyncio
async def test_concurrent_operations(service):
    # Test that concurrent operations work correctly
    results = await asyncio.gather(
        service.operation_a(),
        service.operation_b(),
    )
    assert all(not r.is_error for r in results)
```

### Async Fixtures

```python
import pytest_asyncio

@pytest_asyncio.fixture
async def async_client():
    client = await create_client()
    yield client
    await client.close()

@pytest_asyncio.fixture
async def populated_db(async_client):
    await async_client.create_test_data()
    yield async_client
    await async_client.cleanup()
```

## Performance Tips

### 1. Use Connection Pools

```python
# Neo4j driver handles pooling automatically
driver = AsyncGraphDatabase.driver(uri, auth=auth)

# Reuse the driver across requests
async def get_task(uid: str) -> Result[Task]:
    async with driver.session() as session:
        result = await session.run(query, uid=uid)
        return Result.ok(Task.from_record(result.single()))
```

### 2. Batch Operations

```python
# BAD - N queries
async def get_tasks(uids: list[str]) -> list[Task]:
    return [await self.get(uid) for uid in uids]

# GOOD - 1 query
async def get_tasks(uids: list[str]) -> Result[list[Task]]:
    return await self.backend.get_many(uids)
```

### 3. Timeout Protection

```python
async def with_timeout(coro, seconds: float = 5.0):
    """Add timeout to any coroutine"""
    try:
        return await asyncio.wait_for(coro, timeout=seconds)
    except asyncio.TimeoutError:
        return Errors.system(f"Operation timed out after {seconds}s")
```

## Semaphore for Rate Limiting

```python
# Limit concurrent operations
semaphore = asyncio.Semaphore(10)

async def rate_limited_fetch(uid: str) -> Result[Task]:
    async with semaphore:
        return await self.fetch(uid)

# Process many items with rate limit
async def process_all(uids: list[str]) -> list[Result[Task]]:
    return await asyncio.gather(
        *(rate_limited_fetch(uid) for uid in uids)
    )
```
