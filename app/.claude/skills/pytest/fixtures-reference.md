# Fixtures Reference - SKUEL Ecosystem

## Core Philosophy

> "Fixtures provide dependency injection for tests"

SKUEL fixtures follow the protocol-based architecture: services depend on protocols, tests inject real or mock implementations.

## Fixture Scopes

| Scope | Lifetime | Use Case |
|-------|----------|----------|
| `function` | Per test (default) | Most fixtures - isolated tests |
| `class` | Per test class | Shared setup for related tests |
| `module` | Per test file | Expensive setup shared across file |
| `session` | Entire test run | TestContainers, app bootstrap |

## Core SKUEL Fixtures

### Root conftest.py (`/tests/conftest.py`)

```python
@pytest.fixture(scope="session")
def event_loop():
    """Session-scoped event loop for async fixtures."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def skuel_app():
    """Bootstrap SKUEL app once per test session."""
    container = await bootstrap_skuel()
    yield container.app
    await container.services.cleanup()


@pytest.fixture
def authenticated_client(skuel_app):
    """TestClient with authenticated session."""
    with TestClient(skuel_app) as client:
        # Register and login
        client.post("/register", data={...})
        client.post("/login", data={...})
        yield client
```

### Integration conftest.py (`/tests/integration/conftest.py`)

```python
@pytest.fixture(scope="session")
def neo4j_container():
    """Start Neo4j container for integration tests."""
    container = Neo4jContainer("neo4j:5.26.0")
    container.with_env("NEO4J_dbms_security_auth__enabled", "false")
    container.with_env("NEO4J_PLUGINS", '["apoc"]')
    container.start()
    yield container
    container.stop()


@pytest.fixture(scope="session")
def neo4j_uri(neo4j_container):
    """Get Neo4j connection URI."""
    return neo4j_container.get_connection_url()


@pytest_asyncio.fixture(scope="session")
async def neo4j_driver(neo4j_uri):
    """Create Neo4j driver connected to test container."""
    driver = AsyncGraphDatabase.driver(neo4j_uri, auth=("neo4j", "testpassword"))
    yield driver
    await driver.close()


@pytest_asyncio.fixture
async def clean_neo4j(neo4j_container, ensure_test_users):
    """Clean database before each test (preserves User nodes)."""
    uri = neo4j_container.get_connection_url()
    driver = AsyncGraphDatabase.driver(uri)

    async def cleanup():
        async with driver.session() as session:
            await session.run("MATCH (n) WHERE NOT n:User DETACH DELETE n")

    await cleanup()  # Before test
    yield
    await cleanup()  # After test
    await driver.close()
```

## Domain Backend Fixtures

```python
@pytest_asyncio.fixture
async def tasks_backend(neo4j_container):
    """Create UniversalNeo4jBackend for tasks."""
    uri = neo4j_container.get_connection_url()
    driver = AsyncGraphDatabase.driver(uri)

    backend = UniversalNeo4jBackend[Task](driver, "Task", Task)
    yield backend
    await driver.close()


@pytest_asyncio.fixture
async def goals_backend(neo4j_container):
    """Create UniversalNeo4jBackend for goals."""
    uri = neo4j_container.get_connection_url()
    driver = AsyncGraphDatabase.driver(uri)

    backend = UniversalNeo4jBackend[Goal](driver, "Goal", Goal)
    yield backend
    await driver.close()

# Similar fixtures for: events_backend, habits_backend, ku_backend, etc.
```

## TestServices Container

```python
@pytest_asyncio.fixture
async def services(neo4j_container):
    """Unified services fixture with all domain services."""
    uri = neo4j_container.get_connection_url()
    driver = AsyncGraphDatabase.driver(uri)

    @dataclass
    class TestServices:
        choices: ChoicesService
        principles: PrinciplesService
        lp: LpService
        ls: LsService
        ku: KuService
        tasks: TasksService
        goals: GoalsService
        events: EventsService
        users: UserService

    # Create backends
    tasks_backend = UniversalNeo4jBackend[Task](driver, "Task", Task)
    goals_backend = UniversalNeo4jBackend[Goal](driver, "Goal", Goal)
    # ... more backends

    # Create services
    tasks_service = TasksService(backend=tasks_backend)
    goals_service = GoalsService(backend=goals_backend, ...)
    # ... more services

    yield TestServices(tasks=tasks_service, goals=goals_service, ...)
    await driver.close()
```

**Usage:**
```python
async def test_cross_domain_flow(services, clean_neo4j):
    # Create goal
    goal_result = await services.goals.create(goal_data)
    assert goal_result.is_ok

    # Create task linked to goal
    task_data = {"title": "Task", "goal_uid": goal_result.value.uid}
    task_result = await services.tasks.create(task_data)
    assert task_result.is_ok
```

## TestBackendWrapper

For tests that pass dicts instead of dataclasses:

```python
class TestBackendWrapper:
    """Wrapper to make backends accept dicts."""

    def __init__(self, backend, model_class):
        self.backend = backend
        self.model_class = model_class
        self.driver = backend.driver

    async def create(self, entity):
        if isinstance(entity, dict):
            valid_fields = {f.name for f in dataclasses.fields(self.model_class)}
            filtered = {k: v for k, v in entity.items() if k in valid_fields}
            entity = self.model_class(**filtered)
        return await self.backend.create(entity)

    def __getattr__(self, name):
        return getattr(self.backend, name)
```

## Test User Fixtures

```python
@pytest_asyncio.fixture(scope="session")
async def ensure_test_users(neo4j_container):
    """Create all test User nodes (session scope)."""
    test_user_uids = [
        "user.test",
        "user.test_integration",
        "user.mike",
    ]

    async with driver.session() as session:
        for uid in test_user_uids:
            await session.run(
                "MERGE (u:User {uid: $uid}) ON CREATE SET u.created_at = datetime()",
                uid=uid,
            )
    yield
    # Cleanup after all tests


@pytest.fixture
def test_user_uid() -> str:
    """Standard test user UID."""
    return "user.test"
```

## Relationship Helper Fixtures

```python
@pytest_asyncio.fixture
async def create_relationship(neo4j_container):
    """Fixture to create relationships in Neo4j."""
    driver = AsyncGraphDatabase.driver(neo4j_container.get_connection_url())

    async def _create_relationship(
        from_uid: str,
        from_label: str,
        to_uid: str,
        to_label: str,
        rel_type: str,
        properties: dict | None = None,
    ):
        async with driver.session() as session:
            await session.run(
                f"""
                MERGE (a:{from_label} {{uid: $from_uid}})
                MERGE (b:{to_label} {{uid: $to_uid}})
                CREATE (a)-[r:{rel_type}]->(b)
                """,
                from_uid=from_uid,
                to_uid=to_uid,
            )

    yield _create_relationship
    await driver.close()


@pytest_asyncio.fixture
async def count_relationships(neo4j_container):
    """Fixture to count relationships for assertions."""
    driver = AsyncGraphDatabase.driver(neo4j_container.get_connection_url())

    async def _count_relationships(uid: str, rel_type: str) -> int:
        async with driver.session() as session:
            result = await session.run(
                f"MATCH (n {{uid: $uid}})-[r:{rel_type}]->() RETURN count(r) as count",
                uid=uid,
            )
            record = await result.single()
            return record["count"] if record else 0

    yield _count_relationships
    await driver.close()
```

## conftest.py Hierarchy

```
tests/
├── conftest.py                    # Root: event_loop, skuel_app, auth clients
├── integration/
│   └── conftest.py                # TestContainers, backends, services
├── unit/
│   └── conftest.py (optional)     # Unit-test specific mocks
└── domain_specific/
    └── conftest.py (optional)     # Domain-specific fixtures
```

**Rules:**
- Fixtures are inherited from parent conftest files
- More specific conftest files can override parent fixtures
- Session-scoped fixtures in root conftest for expensive setup

## Best Practices

### 1. Explicit Dependencies

```python
# GOOD - explicit fixture dependencies
async def test_task_flow(tasks_backend, clean_neo4j, test_user_uid):
    ...

# BAD - implicit dependencies (hard to understand)
async def test_task_flow(tasks_backend):  # Missing clean_neo4j!
    ...
```

### 2. Cleanup in Fixtures

```python
@pytest_asyncio.fixture
async def backend(neo4j_container):
    driver = AsyncGraphDatabase.driver(...)
    backend = UniversalNeo4jBackend[Task](driver, "Task", Task)

    yield backend  # Test runs here

    await driver.close()  # Cleanup ALWAYS runs
```

### 3. Session Scope for Expensive Resources

```python
# GOOD - container started once
@pytest.fixture(scope="session")
def neo4j_container(): ...

# BAD - container started per test (slow!)
@pytest.fixture
def neo4j_container(): ...
```

### 4. Avoid Fixture Side Effects

```python
# GOOD - fixture just provides resources
@pytest.fixture
def sample_task():
    return Task(uid="task:test", title="Test Task")

# BAD - fixture modifies state
@pytest.fixture
def sample_task(tasks_service):
    task = Task(uid="task:test", title="Test Task")
    await tasks_service.create(task)  # Side effect!
    return task
```

## Key Files

- `/tests/conftest.py` - Root fixtures
- `/tests/integration/conftest.py` - TestContainers + backends
- `/tests/fixtures/service_factories.py` - Mock creation utilities
- `/tests/templates/integration_test_template.py` - Template with fixture patterns
