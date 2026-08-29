# Pytest - Quick Reference

> **Fast lookup** for common syntax, methods, and operations

---

## Running Tests

```bash
uv run pytest tests/unit/ --no-cov -q          # fast unit sweep (skip coverage addopts)
uv run pytest tests/integration/ -q            # needs LOCAL Docker (testcontainers Neo4j)
uv run pytest tests/unit/test_foo.py -k "create" -x --tb=short
./dev test | test-unit | test-integration | test-quick | smoke
```

**When to use**: `--no-cov` — `addopts` in `pyproject.toml` bakes in `--cov=core --cov=adapters --cov=components` + `-v`; disable for speed. **CI runs `tests/unit/` ONLY** (`uv run pytest tests/unit/ -x --tb=short -q`) — integration behavior is NOT in CI and needs local Docker.

---

## Canonical Snippets

### Async test (asyncio_mode = "auto")

```python
@pytest.mark.asyncio  # conventional; auto mode makes it optional for async def tests
async def test_create_task_success(tasks_service, sample_task):
    result = await tasks_service.create(sample_task)
    assert result.is_ok, f"Expected success, got: {result.error}"
    assert result.value.title == sample_task.title
```

**When to use**: Any test calling a service/backend — all SKUEL I/O is async. `asyncio_mode = "auto"` is set in `[tool.pytest.ini_options]`.

### Async fixture — MUST be `@pytest_asyncio.fixture`

```python
import pytest_asyncio

@pytest_asyncio.fixture
async def tasks_backend(neo4j_driver):
    return UniversalNeo4jBackend[Task](neo4j_driver, NeoLabel.TASK, Task, base_label=NeoLabel.ENTITY)
```

**When to use**: Any `async def` fixture. Plain `@pytest.fixture` on an async fixture hands the test an un-awaited coroutine.

### Mocking a backend that returns Result[T]

```python
from unittest.mock import AsyncMock
from core.utils.result_simplified import Result, Errors

backend.get = AsyncMock(return_value=Result.ok(task))
backend.get.return_value = Result.fail(Errors.not_found("Task", "task_123"))
backend.get.side_effect = [Result.ok(t1), Result.fail(Errors.not_found("Task", "x"))]
```

**When to use**: Unit tests — mock at the backend boundary, never internal service methods. Mocks must return `Result`, never raw values.

### Testing errors

```python
result = await tasks_service.get("nonexistent-uid")
assert result.is_error                                  # NOT .is_err (SKUEL003)
assert "not found" in result.error.message.lower()      # ownership miss = 404, not 403
```

**When to use**: Every failure-path test. Check `is_ok`/`is_error` FIRST, then touch `.value`/`.error`.

### Integration test (real Neo4j)

```python
@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_roundtrip(tasks_backend, clean_neo4j):
    result = await tasks_backend.create(task)
    assert result.is_ok, f"Create failed: {result.error}"
```

**When to use**: Graph relationships, round-trips, guard tests. An `AsyncMock` backend resolves ANY attribute — it silently "passes" calls to methods that don't exist; only real Neo4j catches that bug class. Prove guard tests fail first against the broken code.

---

## Key Infrastructure

### Shared fixtures — `tests/conftest.py` (root)

| Fixture | Provides |
|---------|----------|
| `skuel_app` (session) | Full bootstrapped app via `scripts/dev/bootstrap.py` |
| `authenticated_client` / `authenticated_client_simple` | `TestClient` with session cookie (register+login / dev user) |
| `test_user_uid` | `"test_graphql_user"` |
| Embedding mocks | `mock_embedding_vector`, `mock_embeddings_service`, `mock_embeddings_unavailable`, `mock_vector_search_service`, `mock_vector_search_unavailable`, `services_with_embeddings` (re-exported from `tests/fixtures/embedding_fixtures.py`) |

### Shared fixtures — `tests/integration/conftest.py`

| Fixture | Provides |
|---------|----------|
| `neo4j_container` / `neo4j_uri` / `neo4j_driver` (session) | Testcontainers `Neo4jContainer(NEO4J_IMAGE)` — the tag is read from `infrastructure/docker-compose.yml` (`tests/integration/_neo4j_pin.py`) + async driver |
| `clean_neo4j` | Per-test wipe of all non-`:User` nodes + creates `entity_embedding_idx` vector index |
| `ensure_test_users` (session) | MERGEs the shared test-user UIDs (`user_test_*`, `user_mike`, …) plus the resolved ingestion fallback owner. **Required by any test that creates or ingests an owned entity** — the `:OWNS` write doors refuse an owner with no `:User` node (ADR-086) |
| `{tasks,goals,habits,events,choices,principles}_backend` / `_service` | Real `UniversalNeo4jBackend[T]` + core sub-service per domain |
| `services` | Container with all domain facades wired to real backends |
| `event_bus` | Real `InMemoryEventBus`; `create_relationship` / `count_relationships` — raw edge helpers |

### Mock factories

```python
from tests.fixtures.service_factories import create_mock_backend, create_mock_driver, create_tasks_service_for_testing
from core.services.relationship_builder import relate  # mock backend.add_relationship, not a chain

backend = create_mock_backend({"get": Result.ok(task)})   # AsyncMock CRUD with Result defaults
service = create_tasks_service_for_testing(backend=backend)
```

### Config — `pyproject.toml [tool.pytest.ini_options]`

`asyncio_mode = "auto"` · `--strict-markers --strict-config` · markers: `unit`, `integration`, `e2e`, `type_safety`, `slow`, `asyncio` (undeclared markers ERROR under strict).

---

## Common Pitfalls

| Problem | Solution |
|---------|----------|
| `.is_err` | `.is_error` (SKUEL003) |
| `@pytest.fixture` on an `async def` fixture | `@pytest_asyncio.fixture` |
| `Mock()` for an async method → "coroutine was never awaited" / not awaitable | `AsyncMock(return_value=Result.ok(...))` |
| Mock returns raw value (`= task`) | Return `Result.ok(task)` — services unwrap Result |
| Mocked backend "passes" for a method that doesn't exist | Guard with an integration round-trip against real Neo4j |
| Unit tests green in CI but integration broken | CI runs `tests/unit/` only — run `./dev test-integration` locally |
| New `@pytest.mark.foo` errors | `--strict-markers` — declare it in `pyproject.toml` markers list |
| Mocking domain models (`mock_task.is_overdue.return_value`) | Construct the real frozen dataclass; mock only the backend |
| Event assertions on real bus | Mock bus: `event_bus.publish_async.assert_called_once()` + check event type |
| Test data leaks between integration tests | Depend on `clean_neo4j` (preserves `:User` nodes only) |

---

**See Also**: [SKILL.md](SKILL.md) for full patterns · [async-testing.md](async-testing.md) · [fixtures-reference.md](fixtures-reference.md) · [mocking-patterns.md](mocking-patterns.md)
