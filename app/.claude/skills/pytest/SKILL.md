---
name: pytest
description: SKUEL testing patterns - fixtures, async testing, mocking with Result[T]. Use when writing tests, debugging failures, or setting up test infrastructure.
allowed-tools: Read, Grep, Glob
---

# pytest: SKUEL Testing Patterns

## Core Philosophy

> "Test behavior through Result[T], not implementation"

All SKUEL services return `Result[T]`. Tests verify success via `result.is_ok` and access values via `result.value`. Never test internal state — test the contract.

## SKUEL Test Architecture

```
tests/
├── conftest.py                 # pin_process_clock_to_utc() FIRST, then load_dotenv(), the embedding mocks, laptop_zone
├── fixtures/
│   ├── service_factories.py    # create_mock_backend, create_mock_driver, create_tasks_service_for_testing, …
│   ├── embedding_fixtures.py   # mock_embeddings_service, mock_vector_search_service, … (re-exported by the root conftest)
│   ├── llm_doubles.py          # scripted_llm, failing_llm, embeddings_double — doubles that keep the real shapes
│   └── csrf.py                 # attach_csrf — a matching cookie + header pair on a request stub
├── helpers/
│   ├── status_guarded_backend.py  # guarded_backend, guarded_rows_backend, resolve_merged_patch, guard_refuses (ADR-087)
│   ├── forced_zone.py / laptop_clock.py  # forced_zone(zone), laptop_wall(...) — the clock helpers of the UTC arc
│   └── faceted_capture.py
├── integration/                # Real Neo4j via testcontainers — serial by ruling
│   ├── conftest.py             # the shared container, the app's own container, skuel_app, backends, services
│   ├── _container_lifecycle.py # bounded_neo4j_container(): pinned image, JVM sized, Ryuk ACK
│   ├── _neo4j_pin.py           # reads the image tag from infrastructure/docker-compose.yml
│   ├── routes/ relationships/ cross_domain/ user_entry/ migrations/ golden/ probes/ e2e/
│   └── test_*.py
├── unit/                       # Mock-based, no Docker — parallel (./dev test-unit)
│   ├── adapters/ auth/ config/ conversation/ docs/ infrastructure/ models/ orchestrator/
│   ├── scripts/ services/ services_bootstrap/ ui/ utils/
│   └── test_*.py
├── js/                         # vitest (./dev test-js)
├── benchmarks/                 # an uncollected script (./dev test ignores the directory by name)
└── templates/integration_test_template.py
```

`ls tests tests/unit tests/integration` is the live tree; this sketch names the directories that matter.

## Quick Reference - Running Tests

| Command | Purpose |
|---------|---------|
| `./dev test-unit` | Unit tier, parallel (`-n logical --maxprocesses 8 --dist loadfile`: one xdist worker per logical CPU, at most **eight** — the cap is measured, past it the longest module is the floor and a laptop swaps); `./dev test-unit -n 1` one worker, `-n 0` in-process serial; flags forward (`-k`, `-x`, `--tb=short`) |
| `uv run pytest tests/unit/` | The same tier, serial (bare pytest adds no `-n`; the runner does) |
| `./dev test-integration` / `uv run pytest tests/integration/` | Integration tier (needs local Docker) — **serial by ruling**: its session fixtures are three testcontainers + an app boot, and xdist would build a set per worker |
| `./dev test` | Both tiers in ONE session, serial (the composed-session guard; its CI twin is the weekly `composed-test-run.yml`) |
| `./dev test-quick` | Integration tier + the auth / error-handling unit files |
| `uv run pytest tests/unit/test_foo.py::test_bar -v` | One test; `-k "pattern"`, `-x`, `--tb=short`, `-s` as usual |
| `./dev test --cov` | Coverage — opt-in, the one path (writes `coverage.xml` + `coverage.json` + `htmlcov/`); every pytest `./dev test*` arm accepts it |
| `./dev coverage-summary` | The gap picture from `coverage.json` — per-package rates, zero-coverage files, large files under 50 % (`scripts/coverage_summary.py`). An instrument, never a threshold |

Every test body has a **120 s ceiling** (`pytest-timeout`, `timeout_func_only` — fixture setup is not charged): `Failed: Timeout (>120.0s) from pytest-timeout` is a hang, not a slow test. A test that legitimately needs longer declares `@pytest.mark.timeout(N)` with a one-line reason.

**Every run is pinned to UTC.** `tests/conftest.py` calls `pin_process_clock_to_utc()` before any other import (the graph driver factory refuses an unpinned process) and `./dev` exports `TZ=UTC`. A test whose expectations are a Vancouver user's opts into `laptop_zone` (`pytestmark = pytest.mark.usefixtures("laptop_zone")`); a test of the unpinned behaviour forces a zone for its own block with `forced_zone("America/Vancouver")` (`tests/helpers/forced_zone.py`), which restores the pin on exit.

**Do not run `./dev quality` beside a test session** on the laptop — the gate's processes peak at ~1.9 GiB for ~80 s and the box swaps beside eight unit workers or the container set (`docs/roadmap/development-machine-capacity.md`).

## Result[T] Testing Patterns

### Testing Success

```python
async def test_create_task_success(tasks_service, sample_task):
    # tasks_service here is the integration conftest's TasksCoreService; `create`
    # takes the frozen Task model (the request-model door is create_task(request, user_uid))
    result = await tasks_service.create(sample_task)

    # Assert - ALWAYS check is_ok first
    assert result.is_ok, f"Expected success, got: {result.error}"

    task = result.value
    assert task.uid == sample_task.uid          # API-minted uids are task_{slug}_{random}
    assert task.title == sample_task.title
```

### Testing Errors

```python
async def test_get_task_not_found(tasks_service):
    result = await tasks_service.get("task_nonexistent_000000")

    # use is_error (NOT is_err — SKUEL003)
    assert result.is_error
    assert result.error.category == ErrorCategory.NOT_FOUND
```

`Errors.not_found(resource, identifier, *, reason=)` takes a resource NAME; the client-visible message is built from it (SKUEL037), so assert on the category (or `result.error.code`), not on prose you did not write.

### Testing Validation

```python
def test_task_request_refuses_an_empty_title():
    # A request model refuses at CONSTRUCTION — Pydantic raises, no Result involved
    with pytest.raises(ValidationError):
        TaskCreateRequest(title="")            # min_length=1


async def test_verify_ownership_without_user_fails_validation(tasks_service):
    # A rule the model cannot see answers as a Result
    result = await tasks_service.verify_ownership("task_x_000001", UserUID(""))

    assert result.is_error
    assert result.error.category == ErrorCategory.VALIDATION
```

The service-level `Result.fail(VALIDATION)` is for rules the model cannot see (a status transition, a missing argument, an owner with no `:User` node); a malformed request model never reaches the service.

## Markers and Config

`pyproject.toml [tool.pytest.ini_options]` — `asyncio_mode = "auto"` · `--strict-markers --strict-config -v` · markers `integration`, `slow`, `asyncio` (undeclared markers ERROR under strict; a declared marker nobody selects is deleted) · `asyncio_default_fixture_loop_scope = "session"`, `asyncio_default_test_loop_scope = "session"` · `timeout = 120`, `timeout_func_only = true` · `filterwarnings` escalates FastHTML's "has no type annotation and is not a recognised special name" to an error (a handler parameter FastHTML cannot bind fails the first test that registers its route).

| Marker | Purpose |
|--------|---------|
| `@pytest.mark.asyncio` | Conventional on async tests; `asyncio_mode = "auto"` makes it optional |
| `@pytest.mark.integration` | Integration tests (real Neo4j) |
| `@pytest.mark.slow` | Long-running tests |
| `@pytest.mark.timeout(N)` | Registered by pytest-timeout — a test that provably needs more than 120 s, with its reason |

## Assertions Quick Reference

```python
# Result assertions
assert result.is_ok                    # Success (NEVER .is_err)
assert result.is_error                 # Failure
assert result.value == expected        # Value access
assert result.error.category == ...    # Error category

# Standard assertions
assert task.title == "Expected"
assert task in tasks
assert len(tasks) == 5

# Exception testing
with pytest.raises(ValueError, match="invalid"):
    service.validate(bad_data)

# Approximate floats
assert goal.progress_percentage == pytest.approx(75.0, rel=0.01)
```

## Parametrized Tests

```python
# Enums carry their presentation (Dynamic Enum Pattern) — parametrize over the members
@pytest.mark.parametrize("priority", list(Priority))            # LOW, MEDIUM, HIGH
def test_priority_color_is_a_hex_token(priority):
    assert priority.get_color().startswith("#")


@pytest.mark.parametrize("status,should_be_terminal", [
    pytest.param(EntityStatus.ACTIVE, False, id="active"),
    pytest.param(EntityStatus.COMPLETED, True, id="completed"),
    pytest.param(EntityStatus.CANCELLED, True, id="cancelled"),
    pytest.param(EntityStatus.ARCHIVED, True, id="archived"),
])
def test_status_is_terminal(status, should_be_terminal):
    assert status.is_terminal() == should_be_terminal
```

## Test Naming Convention

```python
# Pattern: test_{action}_{expected_outcome}
def test_create_task_returns_success(): ...
def test_create_task_with_invalid_data_fails_validation(): ...
def test_get_task_when_missing_returns_not_found(): ...
def test_update_task_status_publishes_event(): ...
```

## Arrange-Act-Assert Pattern

```python
async def test_update_task_status(tasks_service, sample_task):
    # Arrange
    created = await tasks_service.create(sample_task)
    assert created.is_ok
    task_uid = created.value.uid

    # Act — the domain's one update path, with a typed intent (ADR-066). There is no
    # generic status write: the status chokepoint owns the guard its write is evaluated
    # against (ADR-087, `update_with_status_guard`).
    result = await tasks_service.update_task(
        task_uid,
        TaskUpdateIntent(status=EntityStatus.COMPLETED.value),
    )

    # Assert
    assert result.is_ok
    assert result.value.status == EntityStatus.COMPLETED
```

⚠ A same-day re-date is invisible to a same-day test (a Task/Goal completion stamp is "today in the user's zone"): backdate the stored stamp in the graph between two writes.

## Integration Test Pattern

```python
@pytest.mark.integration
class TestTasksCRUD:
    """Test complete CRUD flow with real Neo4j."""

    async def test_create_task(self, tasks_backend, clean_neo4j, ensure_test_users):
        task = Task(uid="task_test-create_000001", title="Test Task", priority=Priority.HIGH, user_uid="user_test")

        result = await tasks_backend.create(task)

        assert result.is_ok, f"Create failed: {result.error}"
        assert result.value.uid == "task_test-create_000001"
```

A test that creates or ingests an **owned** entity depends on `ensure_test_users`: the `:OWNS` write doors refuse an owner with no `:User` node (ADR-086) rather than leaving a property-only orphan.

### Guard tests: where mocks are blind

A mocked backend (`AsyncMock`) resolves **any** attribute, so it returns success for a backend method that does not exist. Round-trip behaviour against a **real Neo4j** is the only thing that catches this class of bug. When you fix one:

1. Write the guard as an **integration** test that creates the edge/row and reads it back, not a mock assertion.
2. **Prove it fails first.** The safe procedure: `git stash push -- <the tree you fixed>` (e.g. `core/`), run a scratch copy of the test with any new import inlined, then `git stash pop`. Never stash while a background suite runs, and `git add` a staged deletion before the run — `stash pop` restores a staged `git rm` as unstaged and `test_secret_scan_floor` then fails on a path `git ls-files` lists but grep cannot open. Mutating the gating condition to show the test goes red is the second half of the proof.

See `tests/integration/test_task_dependency_edge_roundtrip.py` for a worked example.

### Host-day tests

CI at 00:00–07:00Z exposes a test that builds "today" from the host's day (the Vancouver day differs then). `faketime` is not installed; probe with `time_machine.travel(ts, tick=…)` — at 03:00Z today and at 03:00Z on a month's 1st (`tests/unit/adapters/test_activity_reports_ui.py` combines it with `forced_zone`). A jump of days also breaks import-time clock constants — separate those with a same-length jump that crosses no boundary.

## SKUEL-Specific Patterns

### Testing with Ownership

```python
async def test_get_for_user_returns_not_found_for_other_user(tasks_service, clean_neo4j, ensure_test_users):
    # Arrange — create a task owned by user A (the model carries user_uid; the backend writes :OWNS)
    created = await tasks_service.create(Task(uid="task_owned_000001", title="Owned", user_uid="user_test"))
    assert created.is_ok

    # Act — read as user B
    result = await tasks_service.get_for_user(created.value.uid, UserUID("user_test_integration"))

    # Assert — returns NotFound, not Forbidden: an ownership miss must answer like a missing uid
    assert result.is_error
    assert result.error.category == ErrorCategory.NOT_FOUND
```

### Testing Event Publishing

```python
async def test_complete_task_publishes_event(mock_backend):
    event_bus = AsyncMock()
    service = create_tasks_service_for_testing(backend=mock_backend, event_bus=event_bus)

    result = await service.update_task(task_uid, TaskUpdateIntent(status=EntityStatus.COMPLETED.value))

    assert result.is_ok
    published = [c.args[0] for c in event_bus.publish_async.await_args_list]
    assert any(isinstance(e, TaskCompleted) for e in published)   # TaskUpdated is published too
```

`InMemoryEventBus` has `publish(event)` (sync) and `publish_async(event)`; services publish through `publish_event(...)` → `publish_async`. A completed re-post still writes (`status`, `updated_at`) and publishes `TaskUpdated` — only `TaskCompleted` and the stamp are held back, so assert on the event *type*, never `assert_called_once`.

### CSRF at the HTTP boundary

Mutating routes are `@csrf_protected`. Two ways to satisfy it:

- A **direct-call stub** (a `SimpleNamespace`/`MagicMock` request): `attach_csrf(request)` (`tests/fixtures/csrf.py`) mints one token and sets both the cookie and the header on the stub.
- A **`TestClient`**: set the cookie on the client and send the header — `tests/unit/adapters/test_ai_routes_http.py` is the worked example (`csrf` fixture → `client.cookies.set(CSRF_COOKIE_NAME, token)` + `headers={CSRF_HEADER_NAME: token}`; build the client with `raise_server_exceptions=False` so a 500 is a status, not a traceback).

### Doubles that keep the real shape

- `MagicMock(spec=[names])`, **never** `spec=<class>` — under Python 3.14 `spec=<class>` evaluates the class's annotations and fails on a `TYPE_CHECKING`-only name. `embeddings_double()` (`tests/fixtures/llm_doubles.py`) is the shared `EmbeddingsService` stand-in built that way.
- `scripted_llm(text)` / `failing_llm(reason)` return a **real** `LLMService` over a `ScriptedChatCaller`, so the service sees a real `LLMResponse`; `LLMService()` with no arguments is the MOCK provider (real return type, no network). Use these instead of replacing a helper on the service under test — replacing the helper is how two mismatched helpers went unnoticed.

## Pure Helper Unit Tests

For pure functions (no I/O), call directly with synthetic data:

```python
# Linter rule tests — instantiate SkuelLinter, call a _check_* with synthetic content
from lint_skuel import SkuelLinter
linter = SkuelLinter(root_dir=Path("/fake"), rules_filter=["SKUEL003"])
linter._check_is_err_usage(fp, rel, content, lines)
assert len(linter.result.violations) == 1

# UI helper tests — call bridge functions with valid/invalid strings
from ui.enum_helpers import get_status_badge_class
assert get_status_badge_class("active") != ""
```

`tests/unit/scripts/` (linters), `tests/unit/ui/`, `tests/unit/utils/` hold these; count them with `pytest --collect-only -q`, never from prose.

## Learning Loop Service Tests

`tests/unit/services/test_teacher_review_service.py` is the reference for the `_make_service()` style (no fixtures — inline construction): four backend mocks (`_make_user_entry_backend()`, `_make_report_backend()`, `_make_exercise_backend()`, `_make_group_backend()`) with per-method `AsyncMock` return values.

**Key mocking patterns in these tests:**
- Backend method mocks: `backend.method_name = AsyncMock(return_value=Result.ok([...]))`
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

- `/tests/conftest.py` - Root fixtures (the pin, `.env`, embedding mocks, `laptop_zone`)
- `/tests/integration/conftest.py` - TestContainers setup
- `/tests/templates/integration_test_template.py` - Best practices template
- `/TESTING.md` - Tiers, parallelism, CI, coverage, troubleshooting (orphaned containers, Ryuk)
- `/docs/patterns/TESTING_PATTERNS.md` - Integration + unit testing patterns (cascade deletes, dot-form UIDs)
- `/docs/patterns/ERROR_HANDLING.md` - Result[T] pattern details
- `/docs/patterns/linter_rules.md` - Linter rules (unit-tested)
