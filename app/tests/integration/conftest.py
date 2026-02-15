"""
Integration Test Fixtures
==========================

Provides test infrastructure for integration tests with real Neo4j database.

Setup:
- Neo4j testcontainer
- Temporary file system
- Real service instances
"""

import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from neo4j import AsyncGraphDatabase
from testcontainers.neo4j import Neo4jContainer

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend

# Lazy imports to avoid circular import issues
# These are imported inside fixtures that need them
# from core.models.ku.ku import Ku  # (was Event, Goal, Habit, Task)
# from core.models.ku.ku_dto import KuDTO
# from core.services.ku_service import KuService
# from core.services.ingestion import UnifiedIngestionService
# from core.services.user_service import UserService

# NOTE: No custom event_loop fixture needed - pytest-asyncio provides one automatically
# with better cleanup handling for async fixtures


@pytest.fixture(scope="session")
def neo4j_container():
    """
    Start Neo4j container for integration tests.

    Note: Requires Docker to be running.
    Uses Neo4j 5.26 to match production environment.
    """
    container = Neo4jContainer("neo4j:5.26.0")
    # Disable auth completely for testing
    container.with_env("NEO4J_dbms_security_auth__enabled", "false")
    container.with_env("NEO4J_PLUGINS", '["apoc"]')

    # Start container
    container.start()

    yield container

    # Cleanup
    container.stop()


@pytest.fixture(scope="session")
def neo4j_uri(neo4j_container):
    """Get Neo4j connection URI."""
    return neo4j_container.get_connection_url()


@pytest_asyncio.fixture(scope="session")
async def neo4j_driver(neo4j_uri):
    """Create Neo4j driver connected to test container."""
    driver = AsyncGraphDatabase.driver(neo4j_uri, auth=("neo4j", "testpassword"))

    # Verify connection
    async with driver.session() as session:
        result = await session.run("RETURN 1 as test")
        record = await result.single()
        assert record["test"] == 1

    yield driver

    # Cleanup
    await driver.close()


@pytest_asyncio.fixture(scope="session")
async def ensure_test_users(neo4j_container):
    """
    Ensure all test user UIDs have User nodes in the database.

    This fixture creates User nodes for all UIDs used across integration tests,
    preventing "User not found" errors when creating user relationships.

    Created before any tests run (session scope).
    """
    from datetime import datetime

    from neo4j import AsyncGraphDatabase

    uri = neo4j_container.get_connection_url()
    driver = AsyncGraphDatabase.driver(uri)

    # All test user UIDs used across integration tests
    test_user_uids = [
        "user.test",
        "user.test_event_ku_flow",
        "user.test_goal_recommendations",
        "user.test_habit_goal_flow",
        "user.test_integration",
        "user.test_ku_lp_flow",
        "user.test_task_goal_flow",
        "user.mike",  # Used in askesis tests
        "user_test_123",  # Used in some tests
        "user_test_456",  # Used in some tests
        # Semantic search integration test users
        "user.test_learning",
        "user.discovery",
        "user.test_perf",
    ]

    async def create_users():
        """Create all test User nodes."""
        async with driver.session() as session:
            for user_uid in test_user_uids:
                result = await session.run(
                    """
                    MERGE (u:User {uid: $user_uid})
                    ON CREATE SET u.created_at = datetime($created_at)
                    """,
                    user_uid=user_uid,
                    created_at=datetime.now().isoformat(),
                )
                await result.consume()  # Ensure transaction commits

    # Create all test users before tests
    await create_users()

    yield

    # Cleanup after all tests (delete test users)
    async def cleanup():
        async with driver.session() as session:
            await session.run(
                """
                MATCH (u:User)
                WHERE u.uid IN $user_uids
                DETACH DELETE u
                """,
                user_uids=test_user_uids,
            )
        await driver.close()

    await cleanup()


@pytest_asyncio.fixture
async def clean_neo4j(neo4j_container, create_moc_test_user, ensure_test_users):
    """
    Clean Neo4j database before each test (after creating test users).

    Deletes all nodes EXCEPT User nodes, which are preserved across tests
    for user relationship creation.

    Also ensures vector indexes are created for semantic search tests.
    """
    from neo4j import AsyncGraphDatabase

    # Create driver for cleanup operations (no auth - use empty strings)
    uri = neo4j_container.get_connection_url()
    # No auth needed when auth is disabled
    driver = AsyncGraphDatabase.driver(uri)

    async def cleanup():
        async with driver.session() as session:
            # Delete all nodes except User nodes
            await session.run("MATCH (n) WHERE NOT n:User DETACH DELETE n")

    async def create_vector_indexes():
        """Create vector indexes required for semantic search tests."""
        async with driver.session() as session:
            # Create vector index for KU entities
            # Required by semantic search integration tests
            result = await session.run("""
                CREATE VECTOR INDEX ku_embedding_idx IF NOT EXISTS
                FOR (n:Ku)
                ON (n.embedding)
                OPTIONS {
                    indexConfig: {
                        `vector.dimensions`: 1536,
                        `vector.similarity_function`: 'cosine'
                    }
                }
            """)
            await result.consume()  # Ensure transaction commits

    # Cleanup before test
    await cleanup()

    # Create indexes after cleanup
    await create_vector_indexes()

    yield

    # Cleanup after test
    await cleanup()
    await driver.close()


@pytest.fixture
def temp_yaml_dir() -> Generator[Path, None, None]:
    """Create temporary directory for YAML files."""
    temp_dir = tempfile.mkdtemp(prefix="skuel_yaml_test_")
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


@pytest_asyncio.fixture
async def ku_backend(neo4j_container):
    """Create real KuService backend."""
    from neo4j import AsyncGraphDatabase

    from core.models.ku.ku_dto import KuDTO

    # Create driver synchronously within the fixture (no auth - use empty strings)
    uri = neo4j_container.get_connection_url()
    # No auth needed when auth is disabled
    driver = AsyncGraphDatabase.driver(uri)

    # Use "Ku" to match what UnifiedIngestionService creates
    backend = UniversalNeo4jBackend[KuDTO](driver, "Ku", KuDTO)

    yield backend

    # Cleanup
    await driver.close()


@pytest.fixture
def mock_intelligence_service() -> AsyncMock:
    """Create mock intelligence service for KuService."""
    from unittest.mock import AsyncMock

    return AsyncMock()


@pytest.fixture
def mock_graph_intel():
    """Create mock GraphIntelligenceService for services that require it.

    January 2026: graph_intel is REQUIRED for unified Curriculum architecture.
    This mock satisfies the fail-fast requirement.
    """
    from unittest.mock import MagicMock

    return MagicMock()


@pytest.fixture
def ku_service(ku_backend, mock_graph_intel):
    """Create real KuService with Neo4j backend."""
    from unittest.mock import AsyncMock, MagicMock

    from core.services.ku_service import KuService

    # Create mock dependencies (required by fail-fast pattern)
    mock_content_repo = AsyncMock()
    mock_query_builder = MagicMock()
    mock_neo4j_adapter = MagicMock()
    mock_driver = MagicMock()  # Required for KuSearchService

    # January 2026: graph_intelligence_service now REQUIRED for unified Curriculum architecture
    return KuService(
        repo=ku_backend,
        content_repo=mock_content_repo,
        graph_intelligence_service=mock_graph_intel,  # REQUIRED for cross-domain queries
        query_builder=mock_query_builder,
        neo4j_adapter=mock_neo4j_adapter,
        driver=mock_driver,
    )


@pytest_asyncio.fixture
async def ingestion_service(neo4j_container):
    """Create real UnifiedIngestionService."""
    from neo4j import AsyncGraphDatabase

    from core.services.ingestion import UnifiedIngestionService

    # Create driver synchronously within the fixture (no auth - use empty strings)
    uri = neo4j_container.get_connection_url()
    # No auth needed when auth is disabled
    driver = AsyncGraphDatabase.driver(uri)

    service = UnifiedIngestionService(driver=driver)

    yield service

    # Cleanup
    await driver.close()


@pytest_asyncio.fixture
async def user_service(neo4j_container):
    """Create UserService for user-entity tracking tests."""
    from neo4j import AsyncGraphDatabase

    from core.models.user.user import User
    from core.services.user_service import UserService

    uri = neo4j_container.get_connection_url()
    driver = AsyncGraphDatabase.driver(uri)

    # Create user backend
    user_backend = UniversalNeo4jBackend[User](driver, "User", User)

    # Create UserService with driver for aggregation queries
    service = UserService(user_repo=user_backend, driver=driver)

    yield service

    await driver.close()


@pytest_asyncio.fixture
async def test_user(neo4j_container):
    """
    Create and return a test User object for rich context pattern tests.

    Returns a User domain model that can be used in tests that need access
    to user properties (e.g., test_user.uid).
    """
    from datetime import datetime

    from neo4j import AsyncGraphDatabase

    from core.models.user.user import User

    uri = neo4j_container.get_connection_url()
    driver = AsyncGraphDatabase.driver(uri)

    # Create a test user with minimal required fields
    test_user_obj = User(
        uid="user.test_rich_context",
        title="Test User",
        description="User for rich context pattern tests",
        email="test@example.com",
        display_name="Test User",
        created_at=datetime.now(),
        is_active=True,
    )

    # Ensure the user exists in Neo4j
    async with driver.session() as session:
        await session.run(
            """
            MERGE (u:User {uid: $uid})
            ON CREATE SET
                u.title = $title,
                u.description = $description,
                u.email = $email,
                u.display_name = $display_name,
                u.created_at = datetime($created_at),
                u.is_active = $is_active
            """,
            uid=test_user_obj.uid,
            title=test_user_obj.title,
            description=test_user_obj.description,
            email=test_user_obj.email,
            display_name=test_user_obj.display_name,
            created_at=test_user_obj.created_at.isoformat(),
            is_active=test_user_obj.is_active,
        )

    yield test_user_obj

    # Cleanup: Delete the test user from Neo4j
    async with driver.session() as session:
        await session.run(
            "MATCH (u:User {uid: $uid}) DETACH DELETE u",
            uid=test_user_obj.uid,
        )

    await driver.close()


@pytest_asyncio.fixture
async def create_test_users(neo4j_container):
    """Create test user nodes in Neo4j for user-entity tracking tests."""
    from datetime import datetime

    from neo4j import AsyncGraphDatabase

    uri = neo4j_container.get_connection_url()
    driver = AsyncGraphDatabase.driver(uri)

    async def create_users():
        """Create User nodes in Neo4j."""
        async with driver.session() as session:
            # Create user_test_123
            await session.run(
                """
                MERGE (u:User {uid: $user_uid})
                ON CREATE SET u.created_at = datetime($created_at)
                RETURN u
                """,
                user_uid="user_test_123",
                created_at=datetime.now().isoformat(),
            )
            # Create user_test_456
            await session.run(
                """
                MERGE (u:User {uid: $user_uid})
                ON CREATE SET u.created_at = datetime($created_at)
                RETURN u
                """,
                user_uid="user_test_456",
                created_at=datetime.now().isoformat(),
            )

    # Create users before test
    await create_users()

    yield

    # Cleanup after test
    async def cleanup():
        async with driver.session() as session:
            await session.run(
                """
                MATCH (u:User)
                WHERE u.uid IN ['user_test_123', 'user_test_456']
                DETACH DELETE u
                """
            )
        await driver.close()

    await cleanup()


@pytest_asyncio.fixture(scope="session")
async def create_moc_test_user(neo4j_container):
    """Create test user node for MOC integration tests."""
    from datetime import datetime

    from neo4j import AsyncGraphDatabase

    uri = neo4j_container.get_connection_url()
    driver = AsyncGraphDatabase.driver(uri)

    async def create_user():
        """Create User node for MOC tests."""
        async with driver.session() as session:
            result = await session.run(
                """
                MERGE (u:User {uid: $user_uid})
                ON CREATE SET u.created_at = datetime($created_at)
                RETURN u
                """,
                user_uid="user.test_integration",
                created_at=datetime.now().isoformat(),
            )
            await result.consume()  # Ensure transaction commits

    # Create user before tests
    await create_user()

    yield

    # Cleanup after all tests
    async def cleanup():
        async with driver.session() as session:
            await session.run(
                """
                MATCH (u:User {uid: 'user.test_integration'})
                DETACH DELETE u
                """
            )
        await driver.close()

    await cleanup()


@pytest_asyncio.fixture
async def services(neo4j_container):
    """
    Create unified services fixture with all domain services and their relationship services.

    Provides access to:
    - services.choices.relationships
    - services.principles.relationships
    - services.lp.relationships
    - services.ku.graph
    - services.ku.semantic
    """
    from dataclasses import dataclass
    from unittest.mock import AsyncMock, MagicMock

    from neo4j import AsyncGraphDatabase

    from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
    from core.models.ku.ku import Ku
    from core.models.ku.ku_dto import KuDTO
    from core.models.user.user import User
    from core.services.choices_service import ChoicesService
    from core.services.events_service import EventsService
    from core.services.goals_service import GoalsService
    from core.services.ku_service import KuService
    from core.services.lp_service import LpService
    from core.services.ls_service import LsService
    from core.services.principles_service import PrinciplesService
    from core.services.tasks_service import TasksService
    from core.services.user_service import UserService

    uri = neo4j_container.get_connection_url()
    driver = AsyncGraphDatabase.driver(uri)

    @dataclass
    class TestServices:
        """Container for test services."""

        choices: ChoicesService
        principles: PrinciplesService
        lp: LpService
        ls: LsService
        ku: KuService
        knowledge: KuService  # Alias for ku (used by rich context tests)
        learning_paths: LpService  # Alias for lp (used by curriculum tests)
        learning_steps: LsService  # Alias for ls (used by curriculum tests)
        tasks: TasksService
        goals: GoalsService
        events: EventsService
        users: UserService

    # Test backend wrapper - accepts dicts and converts to dataclasses
    class TestBackendWrapper:
        """Wrapper to make backends accept dicts (for test compatibility)."""

        def __init__(self, backend, model_class):
            self.backend = backend
            self.model_class = model_class
            # Expose driver for test access
            self.driver = backend.driver

        async def create(self, entity):
            """Create - accepts dict or dataclass."""
            import dataclasses

            # Convert dataclass to dict first (handles both DTO and domain models)
            if dataclasses.is_dataclass(entity) and not isinstance(entity, type):
                # Manually extract fields to avoid deepcopy issues
                entity = {f.name: getattr(entity, f.name) for f in dataclasses.fields(entity)}

            # Now convert dict to target model class
            if isinstance(entity, dict):
                # Filter to only valid fields for the model
                if dataclasses.is_dataclass(self.model_class):
                    valid_fields = {f.name for f in dataclasses.fields(self.model_class)}
                    filtered_dict = {k: v for k, v in entity.items() if k in valid_fields}
                    entity = self.model_class(**filtered_dict)
                else:
                    entity = self.model_class(**entity)

            return await self.backend.create(entity)

        def __getattr__(self, name):
            """Forward all other calls to backend."""
            return getattr(self.backend, name)

    # Create backends with test wrappers
    raw_ku_backend = UniversalNeo4jBackend[KuDTO](driver, "Ku", KuDTO)
    ku_backend = TestBackendWrapper(raw_ku_backend, KuDTO)

    raw_tasks_backend = UniversalNeo4jBackend[Ku](driver, "Task", Ku)
    tasks_backend = TestBackendWrapper(raw_tasks_backend, Ku)

    raw_goals_backend = UniversalNeo4jBackend[Ku](driver, "Goal", Ku)
    goals_backend = TestBackendWrapper(raw_goals_backend, Ku)

    raw_events_backend = UniversalNeo4jBackend[Ku](driver, "Event", Ku)
    events_backend = TestBackendWrapper(raw_events_backend, Ku)

    raw_ls_backend = UniversalNeo4jBackend[Ku](driver, "Ku", Ku)
    ls_backend = TestBackendWrapper(raw_ls_backend, Ku)

    raw_lp_backend = UniversalNeo4jBackend[Ku](driver, "Ku", Ku)
    lp_backend = TestBackendWrapper(raw_lp_backend, Ku)

    raw_principles_backend = UniversalNeo4jBackend[Ku](
        driver, "Ku", Ku, default_filters={"ku_type": "principle"}
    )
    principles_backend = TestBackendWrapper(raw_principles_backend, Ku)

    # These backends aren't used by tests, create without wrapper
    choices_backend = UniversalNeo4jBackend[Ku](driver, "Ku", Ku)
    users_backend = UniversalNeo4jBackend[User](driver, "User", User)

    # Mock GraphIntelligenceService for services that require it
    mock_graph_intel = MagicMock()

    # Create Choices service (requires graph_intelligence_service)
    choices_service = ChoicesService(
        backend=choices_backend,
        graph_intelligence_service=mock_graph_intel,
    )

    # Create Principles service (requires graph_intelligence_service)
    principles_service = PrinciplesService(
        backend=principles_backend,
        graph_intelligence_service=mock_graph_intel,
    )

    # Create LS service (used by LP service)
    # January 2026: graph_intel now REQUIRED for unified Curriculum architecture
    ls_service = LsService(driver=driver, graph_intel=mock_graph_intel)

    # Create LP service (January 2026: intelligence created internally)
    lp_service = LpService(
        driver=driver,
        ls_service=ls_service,
        graph_intelligence_service=mock_graph_intel,
    )

    # Create KU service (mock dependencies)
    mock_content_repo = AsyncMock()
    mock_query_builder = MagicMock()
    mock_neo4j_adapter = MagicMock()

    ku_service = KuService(
        repo=ku_backend,
        content_repo=mock_content_repo,
        query_builder=mock_query_builder,
        neo4j_adapter=mock_neo4j_adapter,
        driver=driver,
        graph_intelligence_service=mock_graph_intel,
    )

    # Create Tasks service
    tasks_service = TasksService(backend=tasks_backend)

    # Create Goals service (requires graph_intelligence_service)
    goals_service = GoalsService(
        backend=goals_backend,
        graph_intelligence_service=mock_graph_intel,
    )

    # Create Events service (requires graph_intelligence_service)
    events_service = EventsService(
        backend=events_backend,
        graph_intelligence_service=mock_graph_intel,
    )

    # Create Users service
    users_service = UserService(user_repo=users_backend, driver=driver)

    # PATCH: Expose backends through core services for test access
    # Tests expect services.{domain}.core.backend.driver
    # But core services have .repo, not .backend
    # Add .backend as an alias for .repo + driver access
    ku_service.core.backend = ku_backend
    tasks_service.core.backend = tasks_backend
    goals_service.core.backend = goals_backend
    events_service.core.backend = events_backend
    ls_service.core.backend = ls_backend
    lp_service.core.backend = lp_backend
    principles_service.core.backend = principles_backend

    services_container = TestServices(
        choices=choices_service,
        principles=principles_service,
        lp=lp_service,
        ls=ls_service,
        ku=ku_service,
        knowledge=ku_service,  # Alias for ku (used by rich context tests)
        learning_paths=lp_service,  # Alias for lp (used by curriculum tests)
        learning_steps=ls_service,  # Alias for ls (used by curriculum tests)
        tasks=tasks_service,
        goals=goals_service,
        events=events_service,
        users=users_service,
    )

    yield services_container

    # Cleanup
    await driver.close()


# ============================================================================
# LP Relationship Service Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def lp_relationship_service(services):
    """
    Provide LP relationship service for integration tests.

    Accesses the LpRelationshipService through the LP service facade.
    Used by test_lp_relationships_integration.py.
    """
    return services.lp.relationships


@pytest_asyncio.fixture
async def create_relationship(neo4j_container):
    """
    Fixture to create relationships in Neo4j for testing.

    Provides a helper function that creates nodes and relationships
    between entities for integration tests.
    """
    from neo4j import AsyncGraphDatabase

    uri = neo4j_container.get_connection_url()
    driver = AsyncGraphDatabase.driver(uri)

    async def _create_relationship(
        from_uid: str,
        from_label: str,
        to_uid: str,
        to_label: str,
        rel_type: str,
        properties: dict | None = None,
    ):
        """Create a relationship between two nodes (creating nodes if needed)."""
        async with driver.session() as session:
            # Build properties clause for relationship
            props_clause = ""
            if properties:
                props_parts = [f"{k}: ${k}" for k in properties]
                props_clause = " {" + ", ".join(props_parts) + "}"

            # Create query with MERGE for nodes and CREATE for relationship
            query = f"""
                MERGE (a:{from_label} {{uid: $from_uid}})
                MERGE (b:{to_label} {{uid: $to_uid}})
                CREATE (a)-[r:{rel_type}{props_clause}]->(b)
                RETURN r
            """

            params = {"from_uid": from_uid, "to_uid": to_uid}
            if properties:
                params.update(properties)

            await session.run(query, params)

    yield _create_relationship

    await driver.close()


@pytest_asyncio.fixture
async def count_relationships(neo4j_container):
    """
    Fixture to count relationships in Neo4j for testing.

    Provides a helper function that counts outgoing relationships
    of a specific type from an entity.
    """
    from neo4j import AsyncGraphDatabase

    uri = neo4j_container.get_connection_url()
    driver = AsyncGraphDatabase.driver(uri)

    async def _count_relationships(uid: str, rel_type: str) -> int:
        """Count outgoing relationships of a specific type."""
        async with driver.session() as session:
            query = f"""
                MATCH (n {{uid: $uid}})-[r:{rel_type}]->()
                RETURN count(r) as count
            """
            result = await session.run(query, uid=uid)
            record = await result.single()
            return record["count"] if record else 0

    yield _count_relationships

    await driver.close()


# ============================================================================
# RAG Test Data Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def populated_test_data(skuel_app):
    """
    Populate Neo4j with test data for RAG tests.

    Creates:
    - Test user with context
    - Sample knowledge units
    - Prerequisites relationships

    Used by:
    - test_askesis_ask_endpoint.py
    - test_askesis_rag_wiring.py
    """
    from datetime import datetime

    # Get driver from bootstrapped services
    services = skuel_app.state.services
    driver = services.neo4j_driver

    test_user_uid = "user.test_rag"

    # Test knowledge units for RAG tests
    test_kus = [
        {
            "uid": "ku.async_programming",
            "title": "Async Programming",
            "summary": "Concurrent code patterns in Python",
            "domain": "programming",
        },
        {
            "uid": "ku.python_basics",
            "title": "Python Basics",
            "summary": "Python fundamentals and syntax",
            "domain": "programming",
        },
        {
            "uid": "ku.concurrency",
            "title": "Concurrency Patterns",
            "summary": "Making code run in parallel",
            "domain": "programming",
        },
    ]

    async with driver.session() as session:
        # Create test user
        await session.run(
            """
            MERGE (u:User {uid: $user_uid})
            ON CREATE SET u.created_at = datetime($created_at)
            """,
            user_uid=test_user_uid,
            created_at=datetime.now().isoformat(),
        )

        # Create test knowledge units
        for ku in test_kus:
            await session.run(
                """
                MERGE (k:Ku {uid: $uid})
                ON CREATE SET
                    k.title = $title,
                    k.summary = $summary,
                    k.domain = $domain,
                    k.created_at = datetime($created_at)
                """,
                uid=ku["uid"],
                title=ku["title"],
                summary=ku["summary"],
                domain=ku["domain"],
                created_at=datetime.now().isoformat(),
            )

        # Create prerequisite relationship: async_programming REQUIRES python_basics
        await session.run(
            """
            MATCH (a:Ku {uid: 'ku.async_programming'})
            MATCH (b:Ku {uid: 'ku.python_basics'})
            MERGE (a)-[:REQUIRES]->(b)
            """
        )

    yield {
        "user_uid": test_user_uid,
        "knowledge_uids": [ku["uid"] for ku in test_kus],
    }

    # Cleanup - remove test data
    async with driver.session() as session:
        # Delete test KUs
        await session.run(
            """
            MATCH (k:Ku)
            WHERE k.uid IN $uids
            DETACH DELETE k
            """,
            uids=[ku["uid"] for ku in test_kus],
        )
        # Delete test user
        await session.run(
            """
            MATCH (u:User {uid: $user_uid})
            DETACH DELETE u
            """,
            user_uid=test_user_uid,
        )


# ========================================================================
# ASYNC EMBEDDING TEST FIXTURES (January 2026)
# ========================================================================


@pytest.fixture
def event_bus():
    """Create a simple event bus for testing."""
    from core.events.event_bus import EventBus

    return EventBus()


@pytest.fixture
def user_uid():
    """Standard test user UID."""
    return "user.test_async_embeddings"


@pytest_asyncio.fixture
async def tasks_backend(neo4j_driver):
    """Create tasks backend for testing."""
    from core.models.ku.ku import Ku

    return UniversalNeo4jBackend[Ku](driver=neo4j_driver, label="Task", model_class=Ku)


@pytest_asyncio.fixture
async def tasks_service(tasks_backend, event_bus):
    """Create tasks core service for testing."""
    from core.services.tasks.tasks_core_service import TasksCoreService

    return TasksCoreService(backend=tasks_backend, event_bus=event_bus)


@pytest_asyncio.fixture
async def goals_backend(neo4j_driver):
    """Create goals backend for testing."""
    from core.models.ku.ku import Ku

    return UniversalNeo4jBackend[Ku](driver=neo4j_driver, label="Goal", model_class=Ku)


@pytest_asyncio.fixture
async def goals_service(goals_backend, event_bus):
    """Create goals core service for testing."""
    from core.services.goals.goals_core_service import GoalsCoreService

    return GoalsCoreService(backend=goals_backend, event_bus=event_bus)


@pytest_asyncio.fixture
async def habits_backend(neo4j_driver):
    """Create habits backend for testing."""
    from core.models.ku.ku import Ku as Habit

    return UniversalNeo4jBackend[Habit](driver=neo4j_driver, label="Habit", model_class=Habit)


@pytest_asyncio.fixture
async def habits_service(habits_backend, event_bus):
    """Create habits core service for testing."""
    from core.services.habits.habits_core_service import HabitsCoreService

    return HabitsCoreService(backend=habits_backend, event_bus=event_bus)


@pytest_asyncio.fixture
async def events_backend(neo4j_driver):
    """Create events backend for testing."""
    from core.models.ku.ku import Ku

    return UniversalNeo4jBackend[Ku](driver=neo4j_driver, label="Event", model_class=Ku)


@pytest_asyncio.fixture
async def events_service(events_backend, event_bus):
    """Create events core service for testing."""
    from core.services.events.events_core_service import EventsCoreService

    return EventsCoreService(backend=events_backend, event_bus=event_bus)


@pytest_asyncio.fixture
async def choices_backend(neo4j_driver):
    """Create choices backend for testing — unified Ku model with ku_type filter."""
    from core.models.ku.ku import Ku

    return UniversalNeo4jBackend[Ku](
        driver=neo4j_driver,
        label="Ku",
        model_class=Ku,
        default_filters={"ku_type": "choice"},
    )


@pytest_asyncio.fixture
async def choices_service(choices_backend, event_bus):
    """Create choices core service for testing."""
    from core.services.choices.choices_core_service import ChoicesCoreService

    return ChoicesCoreService(backend=choices_backend, event_bus=event_bus)


@pytest_asyncio.fixture
async def principles_backend(neo4j_driver):
    """Create principles backend for testing."""
    from core.models.ku.ku import Ku

    return UniversalNeo4jBackend[Ku](
        driver=neo4j_driver, label="Ku", model_class=Ku, default_filters={"ku_type": "principle"}
    )


@pytest_asyncio.fixture
async def principles_service(principles_backend, event_bus):
    """Create principles core service for testing."""
    from core.services.principles.principles_core_service import PrinciplesCoreService

    return PrinciplesCoreService(backend=principles_backend, event_bus=event_bus)
