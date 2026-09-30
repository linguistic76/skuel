# Mocking Patterns - SKUEL Services

## Core Philosophy

> "Mock backends, not services"

SKUEL tests mock at the infrastructure boundary. Services receive mock backends that implement the same protocol as real backends.

## When to Mock vs. Use Real Dependencies

| Scenario | Approach |
|----------|----------|
| Unit tests | Mock backend, fast execution |
| Integration tests | Real Neo4j (TestContainers) |
| Service behavior | Mock backend returns |
| Domain logic | Real domain models |
| Graph relationships | Real Neo4j preferred |

## Mock Creation Utilities

Located in `/tests/fixtures/service_factories.py`:

### create_mock_backend()

```python
from tests.fixtures.service_factories import create_mock_backend
from core.utils.result_simplified import Result

# Basic mock with defaults
backend = create_mock_backend()

# Custom behavior
backend = create_mock_backend({
    "get": Result.ok(my_task),
    "create": Result.ok(created_task),
    "delete": Result.ok(True),
})

# The mock's pre-built AsyncMocks (read create_mock_backend for the exact set):
backend.create / get / update / delete / list_by_user / list_by_domain / find_by / get_stats
# A behavior key naming any OTHER method is added as a fresh AsyncMock. The base is a
# plain Mock(): an unscripted method the service AWAITS raises TypeError (a Mock is not
# awaitable), and one it merely reads returns a Mock, never a Result. Script every
# method the path under test reaches.
```

⚠ **A status-bearing write does NOT go through `backend.update`** (ADR-087) — the Activity
update chokepoints call `backend.update_with_status_guard(uid, changes, guard)`, which
`create_mock_backend` does not provide. Mocking `update` for one of those tests asserts
nothing while passing. Use the shared fake instead, which evaluates the guard the way the
Cypher does and records what the service asked for:

```python
from tests.helpers.status_guarded_backend import guarded_backend

backend, recorder = guarded_backend(current_entity, updated_entity)
service = GoalsCoreService(backend=backend)
await service.update_goal("goal_1", GoalUpdateIntent(status="completed"))

recorder.last_guard        # the StatusWriteGuard the service built
recorder.merged_patch()    # what the write would merge for THIS prior
```

`guarded_rows_backend(rows)` is the multi-row form (per-row loops such as bulk completion),
and `echoing_guarded_write(backend)` adapts fixtures that configure `get`/`update` return
values. `resolve_merged_patch(prior, updates, guard)` resolves a guard by hand — the
Cypher's CASE arms in one place, so no test re-implements them — and
`guard_refuses(prior, guard)` answers the refusal verdict alone, both gates
(`refuse_if_prior_in`, and a prior outside a non-empty `refuse_unless_prior_in`). ⚠ `StatusWriteGuard` is not
hashable (its patch holds a dict) — assert guard identity, never set membership.

⚠ **A fake driven by `backend.get` cannot test a transition verdict.** It answers the guard
from whatever the read returned, which is exactly the coupling ADR-087 removed — such a test
passes against the pre-ADR code too. Seed the write-time prior SEPARATELY from the read
(`guarded_backend(stored, read)`) so the two disagree, which is what a race produces. See
`tests/unit/services/goals/test_goal_progress_status_guard.py` and
`tests/unit/services/test_completion_stamping.py`.

### create_mock_driver()

```python
from tests.fixtures.service_factories import create_mock_driver

# Basic mock driver
driver = create_mock_driver()

# Driver with session context manager
async with driver.session() as session:
    await session.run("MATCH (n) RETURN n")  # Returns []
```

## Service Factory Pattern

Create services the same way production does, but with mock backends:

```python
from tests.fixtures.service_factories import create_tasks_service_for_testing
# Siblings in the same module: create_finance_service_for_testing,
# create_mock_backend_for_base_service, create_unified_user_context_for_testing,
# create_askesis_user_context_for_testing.

# Simple - all defaults
service = create_tasks_service_for_testing()

# Custom backend behavior
service = create_tasks_service_for_testing(
    backend_behavior={"get": Result.ok(task)}
)

# Full control with custom backend
my_backend = create_mock_backend({"create": Result.ok(task)})
service = create_tasks_service_for_testing(backend=my_backend)
# Keyword deps it accepts: backend, cross_domain_query, ku_inference_service,
# ku_generation_service, graph_intel, event_bus, backend_behavior — a TasksService facade.
```

## LLM and embeddings doubles — keep the real shape

`tests/fixtures/llm_doubles.py`:

```python
from tests.fixtures.llm_doubles import scripted_llm, failing_llm, embeddings_double

llm = scripted_llm("a canned insight")        # a REAL LLMService over a ScriptedChatCaller
llm = failing_llm("rate limited")             # every call answers a provider failure
emb = embeddings_double()                     # MagicMock(spec=[the public names]); create_embedding scripted
emb = embeddings_double(create_embedding=AsyncMock(return_value=Result.ok([0.1] * 1024)))
```

Use these instead of replacing a helper on the service under test: a replaced helper hides a mismatch between the helper and the service it is wired to (that is exactly how the AI tier's `_generate_insight` returned a dataclass typed `Result[str]` for months). `LLMService()` with no arguments is the MOCK provider — a real return type, no network.

⚠ `MagicMock(spec=<class>)` evaluates the class's annotations under Python 3.14 and fails on a `TYPE_CHECKING`-only name — pass `spec=[names]` (a list of the public names), as `embeddings_double` does.

## Result[T] Return Values

SKUEL services return `Result[T]`. Mocks must do the same:

```python
from core.utils.result_simplified import Result

# Success case
mock_backend.get.return_value = Result.ok(task)

# Error case
from core.utils.result_simplified import Errors
mock_backend.get.return_value = Result.fail(
    Errors.not_found("Task", "task_missing_000123")   # (resource NAME, identifier) — never a sentence (SKUEL037)
)

# Multiple return values (sequential calls)
mock_backend.get.side_effect = [
    Result.ok(task1),
    Result.ok(task2),
    Result.fail(Errors.not_found("Task", "task_missing_000999")),
]
```

## AsyncMock for Async Methods

All SKUEL backend methods are async. Use `AsyncMock`:

```python
from unittest.mock import AsyncMock, Mock

backend = Mock()
backend.create = AsyncMock(return_value=Result.ok(task))
backend.get = AsyncMock(return_value=Result.ok(task))

# Then in test:
result = await service.create(task_data)  # Works!
```

## Fluent Relationship Builder — nothing special to mock

`core/services/relationship_builder.py` holds no state a test needs to fake: it
accumulates three values and delegates to `backend.add_relationship`. So mock
**that**, not the chain.

```python
backend.add_relationship = AsyncMock(return_value=Result.ok(True))

await relate(backend, "task.123").via(
    RelationshipName.REQUIRES_KNOWLEDGE
).to("ku.python.async").create()

backend.add_relationship.assert_awaited_once_with(
    from_uid="task.123",
    to_uid="ku.python.async",
    relationship_type=RelationshipName.REQUIRES_KNOWLEDGE,
    properties=None,
)
```

Sequential results are a plain `side_effect`:

```python
backend.add_relationship = AsyncMock(side_effect=[Result.ok(True), Result.fail(...)])
```

⚠️ **The old `fluent_mocks.py` test helper and `backend.relate()` are DELETED.**
That was a chain-of-mocks helper for `RelationshipBuilder` in
`adapters/persistence/neo4j/`, which no service could ever call — it sat below the
hexagonal boundary and was on no port. It had zero importers, including from the
one test file written for it.

## Mocking Event Bus

```python
from unittest.mock import AsyncMock

# Mock event bus — services publish through publish_event(...) → bus.publish_async(event)
event_bus = AsyncMock()

service = create_tasks_service_for_testing(backend=guarded, event_bus=event_bus)

# Completion is the status chokepoint with a typed intent (there is no `complete()`)
await service.update_task(task_uid, TaskUpdateIntent(status=EntityStatus.COMPLETED.value))

# A completion publishes TaskUpdated AND TaskCompleted — assert on the type, not on the count
published = [c.args[0] for c in event_bus.publish_async.await_args_list]
completed = [e for e in published if isinstance(e, TaskCompleted)]
assert len(completed) == 1
assert completed[0].task_uid == task_uid
```

`guarded` above is a `guarded_backend(...)` fake (§ create_mock_backend) — a plain `create_mock_backend` has no `update_with_status_guard`, so the status write would hit an unscripted `Mock` and the completion verdict would never be derived.

## Mocking Neo4j Session

```python
from unittest.mock import AsyncMock, Mock

def create_mock_session():
    """Create mock Neo4j session with context manager."""
    session = Mock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.run = AsyncMock(return_value=[])
    return session

# Usage
mock_driver = Mock()
mock_driver.session = Mock(return_value=create_mock_session())
```

## Full Unit Test Example

```python
import pytest
from unittest.mock import AsyncMock, Mock
from tests.fixtures.service_factories import create_tasks_service_for_testing
from core.utils.result_simplified import Result
from core.models.task.task import Task

@pytest.fixture
def sample_task():
    return Task(
        uid="task_test_000001",     # API-minted shape: task_{slug}_{random}; colons are never a uid spelling
        title="Test Task",
        priority=Priority.HIGH,
    )


@pytest.fixture
def mock_backend(sample_task):
    from tests.fixtures.service_factories import create_mock_backend
    return create_mock_backend({
        "get": Result.ok(sample_task),
        "create": Result.ok(sample_task),
    })


@pytest.fixture
def tasks_service(mock_backend):
    return create_tasks_service_for_testing(backend=mock_backend)


@pytest.mark.asyncio
async def test_get_task_success(tasks_service, sample_task):
    # Act
    result = await tasks_service.get(sample_task.uid)

    # Assert
    assert result.is_ok
    assert result.value.uid == sample_task.uid


@pytest.mark.asyncio
async def test_get_task_not_found(tasks_service, mock_backend):
    # Arrange
    from core.utils.result_simplified import Errors
    mock_backend.get.return_value = Result.fail(
        Errors.not_found("Task", "task_nonexistent_000000")
    )

    # Act
    result = await tasks_service.get("task_nonexistent_000000")

    # Assert
    assert result.is_error
    assert result.error.category == ErrorCategory.NOT_FOUND


@pytest.mark.asyncio
async def test_create_task_calls_backend(tasks_service, mock_backend, sample_task):
    # Act — the facade's `create` takes the domain model; `create_task` takes a request + user_uid
    await tasks_service.create(sample_task)

    # Assert
    mock_backend.create.assert_awaited_once_with(sample_task)
```

## Assertion Helpers

### Verify Method Called

```python
# Called once
mock_backend.create.assert_called_once()

# Called with specific args
mock_backend.create.assert_called_once_with(expected_task)

# Called multiple times
assert mock_backend.get.call_count == 3

# Access call arguments
call_args = mock_backend.create.call_args
first_arg = call_args[0][0]  # Positional arg
kwargs = call_args[1]        # Keyword args
```

### Verify Not Called

```python
mock_backend.delete.assert_not_called()
```

### Verify Call Order

```python
from unittest.mock import call

mock_backend.assert_has_calls([
    call.get("task_one_000001"),
    call.update("task_one_000001", {"title": "Revised title"}),
])
```

## Anti-Patterns

### Over-Mocking

```python
# BAD - mocking internal implementation
mock_service._internal_method = Mock()

# GOOD - mock at backend boundary
mock_backend.get = AsyncMock(return_value=Result.ok(task))
```

### Mocking Domain Models

```python
# BAD - mocking domain logic
mock_task = Mock()
mock_task.is_overdue.return_value = True

# GOOD - use real domain model
task = Task(uid="task_one_000001", title="One", due_date=yesterday)
assert task.is_overdue()   # reads today_in(current_zone()) itself — a day in the user's zone
```

### Forgetting AsyncMock

```python
# BAD - Mock for async method
backend.create = Mock(return_value=Result.ok(task))
await service.create(...)  # Error!

# GOOD - AsyncMock for async method
backend.create = AsyncMock(return_value=Result.ok(task))
await service.create(...)  # Works!
```

### Returning Raw Values Instead of Result

```python
# BAD - returning raw task
mock_backend.get.return_value = task

# GOOD - returning Result[Task]
mock_backend.get.return_value = Result.ok(task)
```

## Key Files

- `/tests/fixtures/service_factories.py` - Mock creation factories
- `/tests/fixtures/llm_doubles.py` - `scripted_llm`, `failing_llm`, `embeddings_double`
- `/tests/helpers/status_guarded_backend.py` - the ADR-087 fakes
- `/core/utils/result_simplified.py` - Result[T] implementation + Errors factory (Errors.not_found, etc.)
