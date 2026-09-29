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
    async def get_user_tasks(self, user_uid: UserUID) -> Result[list[Task]]:
        """I/O operation - must be async"""
        return await self.core.get_user_tasks(user_uid)

    async def create(self, task: Task) -> Result[Task]:
        """I/O operation - must be async"""
        return await self.backend.create(normalized(task))  # sync helper, awaited backend


def normalized(task: Task) -> Task:
    """Pure computation - should be sync"""
    return replace(task, title=task.title.strip())
```

### Awaiting Multiple Operations

```python
import asyncio

async def get_activities(
    self, user_uid: UserUID
) -> Result[tuple[list[Task], list[Goal], list[Habit]]]:
    # Run independent operations concurrently
    tasks_result, goals_result, habits_result = await asyncio.gather(
        self.tasks_service.get_user_tasks(user_uid),
        self.goals_service.get_user_goals(user_uid),
        self.habits_service.get_user_habits(user_uid),
    )

    # Check all results — a failure crosses a type boundary, so wrap it
    if tasks_result.is_error:
        return Result.fail(tasks_result)
    if goals_result.is_error:
        return Result.fail(goals_result)
    if habits_result.is_error:
        return Result.fail(habits_result)

    return Result.ok((tasks_result.value, goals_result.value, habits_result.value))
```

### Sequential vs Concurrent

```python
# Sequential - when order matters or operations depend on each other
async def create_task_for_goal(self, task: Task, goal_uid: str) -> Result[bool]:
    # Goal must exist before creating task
    goal_result = await self.goals_service.get(goal_uid)
    if goal_result.is_error:
        return Result.fail(goal_result)

    # Now create task
    task_result = await self.tasks_service.create(task)
    if task_result.is_error:
        return Result.fail(task_result)

    # Link task to goal (CONTRIBUTES_TO_GOAL)
    return await self.tasks_service.link_task_to_goal(task_result.value.uid, goal_uid)


# Concurrent - when operations are independent: the three reads in
# "Awaiting Multiple Operations" above don't depend on each other, so they
# share one asyncio.gather. UserContextBuilder's MEGA-QUERY is the same idea
# at scale — six statements plus their neighbours under one gather.
```

## Error Handling with Gather

### Pattern 1: Fail on First Error

Service methods return `Result` rather than raise, so a plain `gather` needs no `try` —
check each result instead:

```python
async def get_all_required(self, uids: list[str]) -> Result[list[Task]]:
    """Fails if any operation fails"""
    results = await asyncio.gather(*(self.tasks_service.get(uid) for uid in uids))

    for result in results:
        if result.is_error:
            return Result.fail(result)

    return Result.ok([r.value for r in results])
```

### Pattern 2: Collect Partial Results

```python
async def get_tasks_and_habits(
    self, user_uid: UserUID
) -> Result[tuple[list[Task], list[Habit] | None]]:
    """Tasks are required; habits are best-effort"""
    required_result, optional_result = await asyncio.gather(
        self.tasks_service.get_user_tasks(user_uid),
        self.habits_service.get_user_habits(user_uid),
        return_exceptions=True,
    )

    # Required must succeed
    if isinstance(required_result, BaseException) or required_result.is_error:
        return Result.fail(Errors.database("get_user_tasks", "Required data unavailable"))

    # Optional can fail gracefully
    habits = None
    if not isinstance(optional_result, BaseException) and not optional_result.is_error:
        habits = optional_result.value

    return Result.ok((required_result.value, habits))
```

## Async Context Managers

A context manager that only sets state needs no `await`, so it stays sync and still wraps
async work:

```python
# core/utils/zone_context.py
@contextmanager
def zone_scope(zone: ZoneInfo) -> Iterator[ZoneInfo]:
    """Every current_zone() inside the block reads zone; restored on any exit"""
    token = current_zone_var.set(zone)
    try:
        yield zone
    finally:
        current_zone_var.reset(token)

# Usage — sync manager around async work
with zone_scope(owner_zone):
    await self._ingest(files)
```

When entering or leaving needs I/O, use `@asynccontextmanager` with an
`AsyncIterator[T]` return type and `async with`. Neo4j sessions and transactions are opened
only inside `adapters/persistence/neo4j/` — a service never holds the driver (SKUEL021).

## Async Iterators

```python
from collections.abc import AsyncIterator

async def iter_tasks(self, page_size: int = 100) -> AsyncIterator[Task]:
    """Walk every task page by page without loading all into memory"""
    offset = 0
    while True:
        result = await self.backend.list(limit=page_size, offset=offset)  # Result[(page, total)]
        if result.is_error:
            return
        page, total = result.value
        for task in page:
            yield task
        offset += page_size
        if offset >= total:
            return

# Usage
titles = [task.title async for task in service.iter_tasks()]
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

# For blocking work (file I/O, CPU-heavy parsing), hand it to a worker thread
async def load_history(path: Path) -> Result[str]:
    text = await asyncio.to_thread(path.read_text)  # as in schema_change_detector.py
    return Result.ok(text)
```

### 3. Sequential When Concurrent is Possible

```python
# BAD - sequential for independent operations
tasks = await self.tasks_service.get_user_tasks(user_uid)    # Wait...
goals = await self.goals_service.get_user_goals(user_uid)    # Then wait...
habits = await self.habits_service.get_user_habits(user_uid)  # Then wait...

# GOOD - concurrent for independent operations
tasks, goals, habits = await asyncio.gather(
    self.tasks_service.get_user_tasks(user_uid),
    self.goals_service.get_user_goals(user_uid),
    self.habits_service.get_user_habits(user_uid),
)
```

### 4. Not Awaiting Coroutines

```python
# BAD - coroutine never awaited
async def create_task(self, task: Task) -> Result[Task]:
    self.backend.create(task)  # Missing await! Returns coroutine
    return Result.ok(task)

# GOOD
async def create_task(self, task: Task) -> Result[Task]:
    return await self.backend.create(task)
```

## Testing Async Code

`asyncio_mode = "auto"` is set in `pyproject.toml`, so the `@pytest.mark.asyncio` marker is
optional — plain `async def test_*` functions run.

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

### 1. Share One Driver

The Neo4j driver pools connections itself. It is built once — `open_async_driver()` in
`adapters/persistence/neo4j/graph_driver.py` is the one construction site, and it refuses a
process whose clock is not pinned to UTC — and every backend shares it. Never open a
driver per request.

### 2. Batch Operations

```python
# BAD - N queries
async def get_tasks(self, uids: list[str]) -> list[Result[Task]]:
    return [await self.get(uid) for uid in uids]

# GOOD - 1 query (a missing uid comes back as None in its slot)
async def get_tasks(self, uids: list[str]) -> Result[list[Task | None]]:
    return await self.backend.get_many(uids)
```

### 3. Timeout Protection

```python
async def with_timeout[T](coro: Awaitable[Result[T]], seconds: float = 5.0) -> Result[T]:
    """Add a client-side timeout to a Result-returning coroutine"""
    try:
        return await asyncio.wait_for(coro, timeout=seconds)
    except TimeoutError:
        return Result.fail(Errors.system(f"Operation timed out after {seconds}s"))
```

Neo4j queries already carry a server-side ceiling (`NEO4J_TRANSACTION_TIMEOUT`, default
120s) — see `/docs/patterns/NEO4J_QUERY_TIMEOUT.md`.

## Semaphore for Rate Limiting

```python
# Limit concurrent operations
semaphore = asyncio.Semaphore(10)

async def rate_limited_fetch(self, uid: str) -> Result[Task]:
    async with semaphore:
        return await self.tasks_service.get(uid)

# Process many items with rate limit
async def process_all(self, uids: list[str]) -> list[Result[Task]]:
    return await asyncio.gather(
        *(self.rate_limited_fetch(uid) for uid in uids)
    )
```
