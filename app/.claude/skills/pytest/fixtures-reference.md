# Fixtures Reference - SKUEL Ecosystem

## Core Philosophy

> "Fixtures provide dependency injection for tests"

SKUEL fixtures follow the protocol-based architecture: services depend on protocols, tests inject real or mock implementations. Everything below is a description of `tests/conftest.py` and `tests/integration/conftest.py` — read the fixture's docstring before relying on a detail here.

## Fixture Scopes

| Scope | Lifetime | Use Case |
|-------|----------|----------|
| `function` | Per test (default) | Most fixtures - isolated tests |
| `class` | Per test class | Shared setup for related tests |
| `module` | Per test file | Expensive setup shared across a file (`scratch_neo4j_container`) |
| `session` | Entire test run | TestContainers, app bootstrap |

Under pytest-xdist (the unit tier's default, `./dev test-unit`) a session is one *worker's* session: a `session` fixture is built once per worker, and a `module` fixture stays on one worker because `--dist loadfile` never splits a file. That is why the integration tier — whose session fixtures are three containers and an app boot — runs serially.

## Root conftest.py (`/tests/conftest.py`)

Order matters and is deliberate:

1. `pin_process_clock_to_utc()` — before any other import, as every entry point does (the graph driver factory refuses an unpinned process).
2. `load_dotenv()` — every `.env` value the developer runs the app with is in the test process (credential backend, tier, vault paths). It does not override a variable already set. **The Neo4j target is the one exception**, overridden by the app fixture below — `.env`'s `NEO4J_URI` is the production AuraDB instance.
3. Re-exports the embedding mocks from `tests/fixtures/embedding_fixtures.py`: `mock_embedding_vector`, `mock_embeddings_service`, `mock_embeddings_unavailable`, `mock_vector_search_service`, `mock_vector_search_unavailable`, `services_with_embeddings`.
4. `laptop_zone` — the one clock fixture shared by every tier, opt-in, never autouse: removes `SKUEL_TIMEZONE` so the user zone is `DEFAULT_TIMEZONE` (America/Vancouver) while the process stays pinned to UTC. `pytestmark = pytest.mark.usefixtures("laptop_zone")` for a module whose expectations are a Vancouver user's.

No app or database fixture lives here. pytest-asyncio ≥ 1.0 provides the loops itself (`asyncio_default_fixture_loop_scope = "session"`) — there is no `event_loop` fixture to define or request.

## Integration conftest.py (`/tests/integration/conftest.py`)

### Containers and drivers

Every Neo4j container in the tier is built by `bounded_neo4j_container()` (`tests/integration/_container_lifecycle.py`): the image tag read from `infrastructure/docker-compose.yml` (`tests/integration/_neo4j_pin.py` — one authored site, nothing to bump in tests), auth off, the JVM sized for the test graphs (a code-side ceiling, never derived from the host — TESTING.md § Parallel Execution has the numbers), and Ryuk's `ACK` read before the container starts so a killed session is still reaped (TESTING.md § Troubleshooting).

Every driver is built by `open_async_driver` (`adapters/persistence/neo4j/graph_driver.py`) — the one construction site, held by `tests/unit/test_graph_driver_construction_sites.py`.

| Fixture | Scope | Provides |
|---------|-------|----------|
| `neo4j_container` | session | The shared container, `NEO4J_PLUGINS='["apoc"]'` with `procedures_unrestricted=apoc.*` — **deliberately wider than compose** (the APOC canary needs `apoc.version()`); the lockdown suite starts its own compose-shaped container |
| `neo4j_uri` | session | `neo4j_container.get_connection_url()` |
| `neo4j_driver` | session, `loop_scope="session"` | `open_async_driver(uri, auth=("neo4j", "testpassword"))`, probed with `RETURN 1`, then `require_utc_instants(driver)` — stamps the empty container with the UTC migration's `:MigrationRecord`; every fixture that clears the graph keeps that node |
| `scratch_neo4j_container` | **module** | A graph of its own for a module that empties or reads the WHOLE graph (the data-version guard, the UTC census) |
| `connection_settings` | function | For a test that opens a `Neo4jConnection` onto a testcontainer: puts the container password in the environment and rebuilds the cached settings, since the connection's settings validate a password CI's environment does not carry |
| `skuel_app_container` / `skuel_app` | session | The whole app bootstrapped (`scripts/dev/bootstrap.bootstrap_skuel`) **against its own container**: `NEO4J_URI` / `NEO4J_USERNAME` / `NEO4J_PASSWORD` are overridden before settings are built (`reload_config()`), and the fixture **refuses to yield** an app whose driver reports a kernel other than the pinned image (`tests/integration/test_skuel_app_fixture.py` keeps that refusal as a permanent test). Private, not shared, because the boot syncs uniqueness constraints on `:User` that the shared graph's accumulated users violate. Boots at any tier — CI runs the integration job at `INTELLIGENCE_TIER=core`; the Askesis modules skip on their own gate |

```python
@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def neo4j_driver(neo4j_uri):
    driver = open_async_driver(neo4j_uri, auth=("neo4j", "testpassword"))
    ...
    await require_utc_instants(driver)
    yield driver
    await driver.close()
```

Fixtures that seed data for the app (`populated_test_data`, `enrolled_user_with_lp`) write through `skuel_app.state.services.neo4j_driver`, never `neo4j_driver` — the two are different graphs.

### Users and cleanup

| Fixture | Scope | Provides |
|---------|-------|----------|
| `ensure_test_users` | session | `MERGE`s every `:User` uid the tier's tests use (`user_test`, `user_test_integration`, `user_mike`, the per-flow `user_test_*` uids, …) plus the ingestion fallback owner **resolved, not spelled**: `DEFAULT_USER_UID` (a developer's `.env` sets `SKUEL_DEFAULT_USER_UID` to their own uid; CI falls back to `SYSTEM_USER_UID`) and `SYSTEM_USER_UID`. Seeding the literal passes on one machine and fails on the other |
| `create_moc_test_user` | session | `user_test_integration` with the properties the MOC tests read |
| `clean_neo4j` | function | Depends on `neo4j_driver`, `create_moc_test_user`, `ensure_test_users`. Before AND after the test: `MATCH (n) WHERE NOT n:User AND NOT n:MigrationRecord DETACH DELETE n`; then creates the `entity_embedding_idx` vector index (1024-dim cosine on `:Entity(embedding)`) the semantic-search tests need |
| `test_user` | function | A `User` domain model (for tests that read `test_user.uid` etc.) |
| `user_uid` | function | The string `"user_test_async_embeddings"` — there is no `test_user_uid` fixture |

**A test that creates or ingests an owned entity MUST depend on `ensure_test_users`** (directly, or through `clean_neo4j`). The `:OWNS` write doors refuse an owner with no `:User` node rather than leaving a property-only orphan (ADR-086) — the CRUD door aborts the write, the bulk ingestion door refuses the batch. The failure names the missing owner, so the fix is normally "add the uid" — except for the ingestion fallback owner above, which must be resolved rather than spelled.

## Domain Backend and Service Fixtures

The per-domain fixtures take the **shared session driver** — they open none of their own:

```python
@pytest_asyncio.fixture
async def tasks_backend(neo4j_driver):
    return UniversalNeo4jBackend[Task](neo4j_driver, NeoLabel.TASK, Task, base_label=NeoLabel.ENTITY)


@pytest_asyncio.fixture
async def tasks_service(tasks_backend, event_bus):
    return TasksCoreService(backend=tasks_backend, event_bus=event_bus)   # the CORE sub-service, not the facade
```

`{tasks,goals,habits,events,choices,principles}_backend` / `_service` follow this shape (`event_bus` is a real `InMemoryEventBus`). `ku_backend`, `ku_service`, `ingestion_service`, `user_service`, `lp_relationship_service`, `embeddings_service`, `temp_yaml_dir` are the others — read their bodies for what they wire.

## `services` — the composed container

`services(neo4j_driver)` builds a `TestServices` dataclass of **facades** over real backends: `choices`, `principles`, `lp`, `ps` (+ the aliases `knowledge`, `path_steps` → ps and `learning_paths` → lp, kept for older tests), `tasks`, `goals`, `events`, `users`. The Activity backends are wrapped in a local `TestBackendWrapper` so `create()` accepts a dict as well as a dataclass (it filters the dict to the model's fields and delegates everything else via `__getattr__`).

```python
async def test_cross_domain_flow(services, clean_neo4j):
    goal_result = await services.goals.create(goal_data)          # dict accepted through the wrapper
    assert goal_result.is_ok
```

## Relationship Helper Fixtures

```python
# create_relationship(from_uid, from_label, to_uid, to_label, rel_type, properties=None)
#   MERGEs both endpoints by label + uid, then CREATEs the edge with the properties
await create_relationship("task_x_000001", "Task", "ku.python.basics", "Ku", "APPLIES_KNOWLEDGE", {"confidence": 0.9})

# count_relationships(uid, rel_type) -> int  (an UNLABELED uid match — fine for a test edge,
#   but a Ku/PathStep with a :Content shadow counts twice; label the uid yourself when it matters)
assert await count_relationships("task_x_000001", "APPLIES_KNOWLEDGE") == 1
```

Both take the shared `neo4j_driver`. For a RelationshipName-typed round-trip prefer the backend's own `add_relationship` / `get_relationships` (the guard-test shape in SKILL.md).

## conftest.py Hierarchy

```
tests/
├── conftest.py                    # Root: the pin, load_dotenv(), embedding mocks, laptop_zone
├── integration/
│   ├── conftest.py                # TestContainers (shared + the app's own), skuel_app, backends, services
│   └── e2e/conftest.py            # the e2e flows' own fixtures
└── unit/                          # no conftest of its own — unit tests build their doubles inline
```

**Rules:**
- Fixtures are inherited from parent conftest files; a more specific conftest can override
- Session-scoped fixtures for expensive setup live next to the container they need — never in the root

## Best Practices

### 1. Explicit Dependencies

```python
# GOOD - explicit fixture dependencies
async def test_task_flow(tasks_backend, clean_neo4j):
    ...

# BAD - implicit dependencies (leaks the previous test's rows)
async def test_task_flow(tasks_backend):  # Missing clean_neo4j!
    ...
```

### 2. Cleanup in Fixtures

```python
@pytest_asyncio.fixture
async def scratch_driver(scratch_neo4j_container):
    driver = open_async_driver(scratch_neo4j_container.get_connection_url(), auth=None)
    yield driver           # Test runs here
    await driver.close()   # Cleanup ALWAYS runs
```

### 3. Session Scope for Expensive Resources

```python
# GOOD - container started once per session
@pytest.fixture(scope="session")
def neo4j_container(): ...

# BAD - container started per test (slow!)
@pytest.fixture
def neo4j_container(): ...
```

### 4. Avoid Fixture Side Effects

```python
# GOOD - fixture just provides a value
@pytest.fixture
def sample_task():
    return Task(uid="task_sample_000001", title="Test Task", user_uid="user_test")

# BAD - fixture writes state (and `await` in a sync fixture is a SyntaxError anyway)
@pytest.fixture
def sample_task(tasks_service):
    ...  # tasks_service.create(task) here is a side effect every dependent test pays for
```

## Key Files

- `/tests/conftest.py` - Root fixtures
- `/tests/integration/conftest.py` - TestContainers + backends + `services`
- `/tests/integration/_container_lifecycle.py`, `_neo4j_pin.py` - the container builder and the pinned image
- `/tests/fixtures/service_factories.py`, `llm_doubles.py`, `csrf.py`, `embedding_fixtures.py` - doubles
- `/tests/helpers/status_guarded_backend.py`, `forced_zone.py`, `laptop_clock.py` - ADR-087 and clock helpers
- `/tests/templates/integration_test_template.py` - Template with fixture patterns
