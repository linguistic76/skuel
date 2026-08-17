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
from testcontainers.neo4j import Neo4jContainer  # type: ignore[import-untyped]

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend

# Lazy imports to avoid circular import issues
# These are imported inside fixtures that need them

# NOTE: No custom event_loop fixture needed - pytest-asyncio provides one automatically
# with better cleanup handling for async fixtures


@pytest.fixture(scope="session")
def neo4j_container():
    """
    Start Neo4j container for integration tests.

    Note: Requires Docker to be running.
    Image pinned to the calendar release in infrastructure/docker-compose.yml
    (ADR-067 § 3a — bump both together).

    ⚠ The APOC profile here is DELIBERATELY more permissive than compose, which
    sets both `..._unrestricted` and `..._allowlist` to `apoc.meta.*`. Do not
    "fix" it to match production: this fixture's job is plugin liveness ("did
    the image bump break APOC?"), which needs `apoc.version()` — itself outside
    `apoc.meta.*` — plus the wider namespaces the canary probes.

    The production profile is exercised separately, against its own container,
    by tests/integration/test_apoc_allowlist_lockdown.py, which also uses THIS
    fixture as the positive control for its refusal assertions. Both profiles
    are load-bearing; neither replaces the other.
    """
    container = Neo4jContainer("neo4j:2026.06.0")
    # Disable auth completely for testing
    container.with_env("NEO4J_dbms_security_auth__enabled", "false")
    container.with_env("NEO4J_PLUGINS", '["apoc"]')
    # Allow APOC procedures without role checks
    container.with_env("NEO4J_dbms_security_procedures_unrestricted", "apoc.*")

    # Start container
    container.start()

    yield container

    # Cleanup
    container.stop()


@pytest.fixture(scope="session")
def neo4j_uri(neo4j_container):
    """Get Neo4j connection URI."""
    return neo4j_container.get_connection_url()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
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


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def ensure_test_users(neo4j_driver):
    """
    Ensure all test user UIDs have User nodes in the database.

    This fixture creates User nodes for all UIDs used across integration tests,
    preventing "User not found" errors when creating user relationships.

    Created before any tests run (session scope).
    """
    from datetime import datetime

    # All test user UIDs used across integration tests
    test_user_uids = [
        "user_test",
        "user_test_event_ku_flow",
        "user_test_goal_recommendations",
        "user_test_habit_goal_flow",
        "user_test_integration",
        "user_test_ku_lp_flow",
        "user_test_task_goal_flow",
        "user_mike",  # Used in askesis tests
        "user_test_123",  # Used in some tests
        "user_test_456",  # Used in some tests
        # Semantic search integration test users
        "user_test_learning",
        "user_discovery",
        "user_test_perf",
        # Per-domain core-operations suites. These became REQUIRED when the CRUD
        # door started writing the (User)-[:OWNS]->(entity) edge in the same
        # statement as the node: an entity owned by a user that does not exist
        # is the exact shape that used to diverge the two OWNER_ONLY read
        # mechanisms, so `create` now refuses it instead of leaving an orphan.
        # A new test that creates owned entities must add its uid here — the
        # failure names the missing owner.
        "test_user",
        "user_test_tasks_core",
        "user_test_goals_core",
        "user_test_habits_core",
        "user_test_events_core",
        "user_test_choices_core",
        "user_test_principles_core",
        "user_test_async_embeddings",
        "user_intent_pipeline",
        "user_cascade",
        "user_other",
    ]

    async def create_users():
        """Create all test User nodes."""
        async with neo4j_driver.session() as session:
            for user_uid in test_user_uids:
                result = await session.run(
                    """
                    MERGE (u:User {uid: $user_uid})
                    ON CREATE SET u.title = $user_uid,
                                  u.created_at = datetime($created_at)
                    """,
                    user_uid=user_uid,
                    created_at=datetime.now().isoformat(),
                )
                await result.consume()  # Ensure transaction commits

    # Create all test users before tests
    await create_users()

    yield

    # Cleanup after all tests (delete test users)
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MATCH (u:User)
            WHERE u.uid IN $user_uids
            DETACH DELETE u
            """,
            user_uids=test_user_uids,
        )


@pytest_asyncio.fixture
async def clean_neo4j(neo4j_driver, create_moc_test_user, ensure_test_users):
    """
    Clean Neo4j database before each test (after creating test users).

    Deletes all nodes EXCEPT User nodes, which are preserved across tests
    for user relationship creation.

    Also ensures vector indexes are created for semantic search tests.
    """

    async def cleanup():
        async with neo4j_driver.session() as session:
            # Delete all nodes except User nodes
            await session.run("MATCH (n) WHERE NOT n:User DETACH DELETE n")

    async def create_vector_indexes():
        """Create vector indexes required for semantic search tests."""
        async with neo4j_driver.session() as session:
            # Create vector index for KU entities
            # Required by semantic search integration tests
            result = await session.run("""
                CREATE VECTOR INDEX entity_embedding_idx IF NOT EXISTS
                FOR (n:Entity)
                ON (n.embedding)
                OPTIONS {
                    indexConfig: {
                        `vector.dimensions`: 1024,
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


@pytest.fixture
def temp_yaml_dir() -> Generator[Path]:
    """Create temporary directory for YAML files."""
    temp_dir = tempfile.mkdtemp(prefix="skuel_yaml_test_")
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


@pytest_asyncio.fixture
async def ku_backend(neo4j_driver):
    """Create real PsService backend."""
    from core.models.curriculum_dto import CurriculumDTO

    # Use "Entity" to match what UnifiedIngestionService creates
    # IMPORTANT: Must use CurriculumDTO (not EntityDTO) to include quality_score, complexity, etc.
    backend = UniversalNeo4jBackend[CurriculumDTO](neo4j_driver, "Entity", CurriculumDTO)

    yield backend


@pytest.fixture
def mock_intelligence_service() -> AsyncMock:
    """Create mock intelligence service for PsService."""
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
def ku_service(ku_backend):
    """Backend with .get() for integration tests that only need read access."""
    # PsService facade requires many sub-services; for round-trip tests
    # the backend's .get() method is sufficient.
    return ku_backend


@pytest_asyncio.fixture
async def ingestion_service(neo4j_driver):
    """Create real UnifiedIngestionService."""
    from adapters.persistence.neo4j.ingestion_service_factory import make_unified_ingestion_service

    service = make_unified_ingestion_service(driver=neo4j_driver)

    yield service


@pytest_asyncio.fixture
async def user_service(neo4j_driver):
    """Create UserService for user-entity tracking tests."""
    from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
    from adapters.persistence.neo4j.user_backend import UserBackend
    from adapters.persistence.neo4j.user_context_queries import UserContextQueryExecutor
    from core.services.user_service import UserService

    # UserBackend is the dedicated identity backend — has get_user_by_username etc.
    # UniversalNeo4jBackend[User] lacks these domain-specific methods.
    user_backend = UserBackend(neo4j_driver)

    # UserService takes an injected UserContextQueryExecutor for context building
    # (built at the composition root in production). Mirror that here.
    query_executor = Neo4jQueryExecutor(neo4j_driver)
    service = UserService(
        user_repo=user_backend, query_executor=UserContextQueryExecutor(query_executor)
    )

    # Wire the cross-domain backend so the stats aggregator (used by
    # get_profile_hub_data) is initialized — mirrors services_bootstrap.
    service.wire_cross_domain_backend(CrossDomainBackend(query_executor))

    yield service


@pytest_asyncio.fixture
async def test_user(neo4j_driver):
    """
    Create and return a test User object for rich context pattern tests.

    Returns a User domain model that can be used in tests that need access
    to user properties (e.g., test_user.uid).
    """
    from datetime import datetime

    from core.models.user.user import User

    # Create a test user with minimal required fields
    test_user_obj = User(
        uid="user_test_rich_context",
        title="Test User",
        description="User for rich context pattern tests",
        email="test@example.com",
        display_name="Test User",
        created_at=datetime.now(),
        is_active=True,
    )

    # Ensure the user exists in Neo4j
    async with neo4j_driver.session() as session:
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
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (u:User {uid: $uid}) DETACH DELETE u",
            uid=test_user_obj.uid,
        )


@pytest_asyncio.fixture
async def create_test_users(neo4j_driver):
    """Create test user nodes in Neo4j for user-entity tracking tests."""
    from datetime import datetime

    async with neo4j_driver.session() as session:
        await session.run(
            """
            MERGE (u:User {uid: $user_uid})
            ON CREATE SET u.title = $user_uid,
                          u.created_at = datetime($created_at)
            RETURN u
            """,
            user_uid="user_test_123",
            created_at=datetime.now().isoformat(),
        )
        await session.run(
            """
            MERGE (u:User {uid: $user_uid})
            ON CREATE SET u.title = $user_uid,
                          u.created_at = datetime($created_at)
            RETURN u
            """,
            user_uid="user_test_456",
            created_at=datetime.now().isoformat(),
        )

    yield

    # Cleanup after test
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MATCH (u:User)
            WHERE u.uid IN ['user_test_123', 'user_test_456']
            DETACH DELETE u
            """
        )


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def create_moc_test_user(neo4j_driver):
    """Create test user node for MOC integration tests."""
    from datetime import datetime

    async with neo4j_driver.session() as session:
        result = await session.run(
            """
            MERGE (u:User {uid: $user_uid})
            ON CREATE SET u.created_at = datetime($created_at)
            RETURN u
            """,
            user_uid="user_test_integration",
            created_at=datetime.now().isoformat(),
        )
        await result.consume()  # Ensure transaction commits

    yield

    # Cleanup after all tests
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MATCH (u:User {uid: 'user_test_integration'})
            DETACH DELETE u
            """
        )


@pytest_asyncio.fixture
async def services(neo4j_driver):
    """
    Create unified services fixture with all domain services and their relationship services.

    Provides access to:
    - services.choices.relationships
    - services.principles.relationships
    - services.lp.relationships
    - services.ps.graph
    - services.ps.semantic
    """
    from dataclasses import dataclass
    from unittest.mock import MagicMock

    from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
    from core.models.entity import Entity
    from core.models.user.user import User
    from core.services.choices_service import ChoicesService
    from core.services.events_service import EventsService
    from core.services.goals_service import GoalsService
    from core.services.lp_service import LpService
    from core.services.principles_service import PrinciplesService
    from core.services.ps_service import PsService
    from core.services.tasks_service import TasksService
    from core.services.user_service import UserService

    @dataclass
    class TestServices:
        """Container for test services."""

        choices: ChoicesService
        principles: PrinciplesService
        lp: LpService
        ps: PsService
        knowledge: PsService  # Alias for ps (used by rich context tests)
        learning_paths: LpService  # Alias for lp (used by curriculum tests)
        path_steps: PsService  # Alias for ps (used by curriculum tests)
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
                    entity = self.model_class(**filtered_dict)  # type: ignore[operator]
                else:
                    entity = self.model_class(**entity)

            return await self.backend.create(entity)

        def __getattr__(self, name):
            """Forward all other calls to backend."""
            return getattr(self.backend, name)

    # Create backends with test wrappers
    from adapters.persistence.neo4j.backends.activity_backends import TasksBackend
    from adapters.persistence.neo4j.backends.curriculum_backends import PsBackend
    from core.models.choice.choice import Choice
    from core.models.enums.neo_labels import NeoLabel
    from core.models.event.event import Event
    from core.models.goal.goal import Goal
    from core.models.principle.principle import Principle
    from core.models.task.task import Task

    raw_tasks_backend = TasksBackend(neo4j_driver, NeoLabel.TASK, Task, base_label=NeoLabel.ENTITY)
    tasks_backend = TestBackendWrapper(raw_tasks_backend, Task)

    from adapters.persistence.neo4j.backends.activity_backends import GoalsBackend

    raw_goals_backend = GoalsBackend(neo4j_driver, NeoLabel.GOAL, Goal, base_label=NeoLabel.ENTITY)
    goals_backend = TestBackendWrapper(raw_goals_backend, Goal)

    from adapters.persistence.neo4j.backends.activity_backends import EventsBackend

    raw_events_backend = EventsBackend(
        neo4j_driver, NeoLabel.EVENT, Event, base_label=NeoLabel.ENTITY
    )
    events_backend = TestBackendWrapper(raw_events_backend, Event)

    raw_ps_backend = PsBackend(neo4j_driver, NeoLabel.PATH_STEP, Entity, base_label=NeoLabel.ENTITY)
    ps_backend = TestBackendWrapper(raw_ps_backend, Entity)

    from adapters.persistence.neo4j.backends.curriculum_backends import LpBackend
    from core.models.pathways.learning_path import LearningPath

    raw_lp_backend = LpBackend(
        neo4j_driver, NeoLabel.LEARNING_PATH, LearningPath, base_label=NeoLabel.ENTITY
    )
    lp_backend = TestBackendWrapper(raw_lp_backend, LearningPath)

    from adapters.persistence.neo4j.backends.activity_backends import PrinciplesBackend

    raw_principles_backend = PrinciplesBackend(
        neo4j_driver, NeoLabel.PRINCIPLE, Principle, base_label=NeoLabel.ENTITY
    )
    principles_backend = TestBackendWrapper(raw_principles_backend, Principle)

    # Use domain-specific backends so sub-services can bind methods at init time
    from adapters.persistence.neo4j.backends.activity_backends import ChoicesBackend

    choices_backend = ChoicesBackend(
        neo4j_driver, NeoLabel.CHOICE, Choice, base_label=NeoLabel.ENTITY
    )
    users_backend = UniversalNeo4jBackend[User](neo4j_driver, "User", User)

    # Mock GraphIntelligenceService for services that require it
    mock_graph_intel = MagicMock()

    # Create QueryExecutor adapter for services that require it
    from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
    from adapters.persistence.neo4j.user_context_queries import UserContextQueryExecutor

    query_executor = Neo4jQueryExecutor(neo4j_driver)

    # Cross-domain query service (graph-direct cross-domain reads)
    from adapters.persistence.neo4j.cross_domain_backend import CrossDomainBackend
    from core.services.cross_domain import CrossDomainQueryService

    cross_domain_backend = CrossDomainBackend(query_executor)
    cross_domain_query = CrossDomainQueryService(cross_domain_backend)

    # Create Choices service (requires graph_intel + cross_domain_query)
    choices_service = ChoicesService(
        backend=choices_backend,
        graph_intel=mock_graph_intel,
        cross_domain_query=cross_domain_query,
    )

    # Create Principles service (requires graph_intel + cross_domain_query)
    principles_service = PrinciplesService(
        backend=principles_backend,
        graph_intel=mock_graph_intel,
        cross_domain_query=cross_domain_query,
    )

    # Create PS service (used by LP service)
    # January 2026: graph_intel now REQUIRED for unified Curriculum architecture.
    # ps_intelligence_backend mirrors the production composition root (built here,
    # injected — the service never imports the adapter, ADR-044 / SKUEL022) so
    # ps.intelligence practice/readiness reads work against the testcontainer.
    from adapters.persistence.neo4j.ps_intelligence_backend import PsIntelligenceBackend

    ps_service = PsService(
        backend=ps_backend,
        executor=query_executor,
        graph_intel=mock_graph_intel,
        ps_intelligence_backend=PsIntelligenceBackend(query_executor),
    )

    # Create LP service (January 2026: intelligence created internally)
    lp_service = LpService(
        backend=lp_backend,
        ps_service=ps_service,
        graph_intel=mock_graph_intel,
    )

    # Create Tasks service (requires graph_intel + cross_domain_query)
    tasks_service = TasksService(
        backend=tasks_backend,
        cross_domain_query=cross_domain_query,
        graph_intel=mock_graph_intel,
    )

    # Create Goals service (requires graph_intel + cross_domain_query)
    goals_service = GoalsService(
        backend=goals_backend,
        graph_intel=mock_graph_intel,
        cross_domain_query=cross_domain_query,
    )

    # Create Events service (requires graph_intel + cross_domain_query)
    events_service = EventsService(
        backend=events_backend,
        graph_intel=mock_graph_intel,
        cross_domain_query=cross_domain_query,
    )

    # Create Users service (inject the UserContextQueryExecutor for context building)
    users_service = UserService(
        user_repo=users_backend, query_executor=UserContextQueryExecutor(query_executor)
    )

    # PATCH: Expose backends through core services for test access
    # Tests expect services.{domain}.core.backend.driver
    # But core services have .repo, not .backend
    # Add .backend as an alias for .repo + driver access
    tasks_service.core.backend = tasks_backend
    goals_service.core.backend = goals_backend
    events_service.core.backend = events_backend
    ps_service.core.backend = ps_backend
    lp_service.core.backend = lp_backend
    principles_service.core.backend = principles_backend

    services_container = TestServices(
        choices=choices_service,
        principles=principles_service,
        lp=lp_service,
        ps=ps_service,
        knowledge=ps_service,  # Alias for ps (used by rich context tests)
        learning_paths=lp_service,  # Alias for lp (used by curriculum tests)
        path_steps=ps_service,  # Alias for ps (used by curriculum tests)
        tasks=tasks_service,
        goals=goals_service,
        events=events_service,
        users=users_service,
    )

    yield services_container


# ============================================================================
# LP Relationship Service Fixtures
# ============================================================================


@pytest_asyncio.fixture
async def lp_relationship_service(services):
    """
    Provide LP relationship service for integration tests.

    Accesses the UnifiedRelationshipService through the LP service facade.
    Used by test_lp_relationships_integration.py.
    """
    return services.lp.relationships


@pytest_asyncio.fixture
async def create_relationship(neo4j_driver):
    """
    Fixture to create relationships in Neo4j for testing.

    Provides a helper function that creates nodes and relationships
    between entities for integration tests.
    """

    async def _create_relationship(
        from_uid: str,
        from_label: str,
        to_uid: str,
        to_label: str,
        rel_type: str,
        properties: dict | None = None,
    ):
        """Create a relationship between two nodes (creating nodes if needed)."""
        async with neo4j_driver.session() as session:
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


@pytest_asyncio.fixture
async def count_relationships(neo4j_driver):
    """
    Fixture to count relationships in Neo4j for testing.

    Provides a helper function that counts outgoing relationships
    of a specific type from an entity.
    """

    async def _count_relationships(uid: str, rel_type: str) -> int:
        """Count outgoing relationships of a specific type."""
        async with neo4j_driver.session() as session:
            query = f"""
                MATCH (n {{uid: $uid}})-[r:{rel_type}]->()
                RETURN count(r) as count
            """
            result = await session.run(query, uid=uid)
            record = await result.single()
            return record["count"] if record else 0

    yield _count_relationships


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

    test_user_uid = "user_test_rag"

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
        # Create test user (title is required by User dataclass)
        await session.run(
            """
            MERGE (u:User {uid: $user_uid})
            ON CREATE SET u.title = $user_uid, u.created_at = datetime($created_at)
            """,
            user_uid=test_user_uid,
            created_at=datetime.now().isoformat(),
        )

        # Create test knowledge units
        for ku in test_kus:
            await session.run(
                """
                MERGE (k:Entity {uid: $uid})
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
            MATCH (a:Entity {uid: 'ku.async_programming'})
            MATCH (b:Entity {uid: 'ku.python_basics'})
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
            MATCH (k:Entity)
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
# GUIDED PIPELINE TEST DATA (Askesis ZPD + GuidanceMode path)
# ========================================================================


@pytest_asyncio.fixture
async def enrolled_user_with_lp(skuel_app):
    """
    Populate Neo4j with the minimum graph for Askesis's guided pipeline to activate.

    The guided pipeline requires (all three must be true):
    1. The enrollment gate passes (PS-first): user_context.current_ps_uids or
       user_context.enrolled_path_uids is non-empty
    2. user_context.active_path_steps_rich has a non-mastered candidate
       → (User)-[:IN_PROGRESS]->(PathStep) where ps.status in ['draft','active']
          and ps.current_mastery < ps.mastery_threshold
    3. The PathStep references at least one Ku

    Uses direct Cypher so the fixture doesn't depend on service-level wiring
    that itself might be under test.
    """
    from datetime import datetime

    services = skuel_app.state.services
    driver = services.neo4j_driver

    user_uid = "user_test_guided"
    lp_uid = "lp:test:guided-pipeline"
    ps_uid = "ps:test:guided-step"
    ku_uid = "ku_test_guided_concept"  # kind derives from the :Ku label/entity_type, never the uid spelling
    created_at = datetime.now().isoformat()

    async with driver.session() as session:
        # User (MEMBER role so per-user tier gate passes; title required by User dataclass)
        await session.run(
            """
            MERGE (u:User {uid: $user_uid})
            SET u.title = $user_uid, u.role = 'MEMBER', u.created_at = datetime($ts)
            """,
            user_uid=user_uid,
            ts=created_at,
        )

        # Ku — knowledge unit the PathStep teaches
        await session.run(
            """
            MERGE (k:Entity:Ku {uid: $uid})
            SET k.title = 'Test Guided Concept',
                k.entity_type = 'ku',
                k.summary = 'A concept used to verify guided pipeline activation',
                k.status = 'active',
                k.created_at = datetime($ts)
            """,
            uid=ku_uid,
            ts=created_at,
        )

        # LearningPath
        await session.run(
            """
            MERGE (lp:Entity:LearningPath {uid: $uid})
            SET lp.title = 'Test Guided LP',
                lp.entity_type = 'learning_path',
                lp.status = 'active',
                lp.created_at = datetime($ts)
            """,
            uid=lp_uid,
            ts=created_at,
        )

        # PathStep — non-mastered so _find_active_ps includes it.
        # Kus are resolved via edges/entity_type (context_retriever), not uid shape.
        await session.run(
            """
            MERGE (ps:Entity:PathStep {uid: $uid})
            SET ps.title = 'Test Guided PathStep',
                ps.entity_type = 'path_step',
                ps.status = 'active',
                ps.current_mastery = 0.0,
                ps.mastery_threshold = 0.7,
                ps.intent = 'Verify guided pipeline activation',
                ps.knowledge_uids = [$ku_uid],
                ps.created_at = datetime($ts)
            """,
            uid=ps_uid,
            ku_uid=ku_uid,
            ts=created_at,
        )

        # LP → PS containment
        await session.run(
            """
            MATCH (lp:LearningPath {uid: $lp_uid})
            MATCH (ps:PathStep {uid: $ps_uid})
            MERGE (lp)-[:CONTAINS_STEP]->(ps)
            """,
            lp_uid=lp_uid,
            ps_uid=ps_uid,
        )

        # PS → Ku via CONTAINS_KNOWLEDGE (what the MEGA-query traverses for knowledge_relationships)
        await session.run(
            """
            MATCH (ps:PathStep {uid: $ps_uid})
            MATCH (k:Ku {uid: $ku_uid})
            MERGE (ps)-[:CONTAINS_KNOWLEDGE]->(k)
            """,
            ps_uid=ps_uid,
            ku_uid=ku_uid,
        )

        # Enrollment: (User)-[:ENROLLED_IN]->(LearningPath) → populates enrolled_path_uids
        await session.run(
            """
            MATCH (u:User {uid: $user_uid})
            MATCH (lp:LearningPath {uid: $lp_uid})
            MERGE (u)-[:ENROLLED_IN]->(lp)
            """,
            user_uid=user_uid,
            lp_uid=lp_uid,
        )

        # Actively studying: (User)-[:IN_PROGRESS]->(PathStep) → populates
        # active_path_steps_rich + current_ps_uids (the edge PsMasteryService writes)
        await session.run(
            """
            MATCH (u:User {uid: $user_uid})
            MATCH (ps:PathStep {uid: $ps_uid})
            MERGE (u)-[:IN_PROGRESS]->(ps)
            """,
            user_uid=user_uid,
            ps_uid=ps_uid,
        )

    yield {
        "user_uid": user_uid,
        "lp_uid": lp_uid,
        "ps_uid": ps_uid,
        "ku_uid": ku_uid,
    }

    # Cleanup
    async with driver.session() as session:
        await session.run(
            """
            MATCH (n)
            WHERE n.uid IN $uids
            DETACH DELETE n
            """,
            uids=[user_uid, lp_uid, ps_uid, ku_uid],
        )


# ========================================================================
# ASYNC EMBEDDING TEST FIXTURES (January 2026)
# ========================================================================


@pytest.fixture
def embeddings_service():
    """Create embeddings service with mock backend + inference client.

    Tests that use this fixture immediately override service methods (e.g.,
    create_batch_embeddings) with AsyncMock, so a mock backend + mock inference
    client is sufficient. The vendor SDK now lives in the adapter, so there is
    no HF_API_TOKEN to set up here.
    """
    from unittest.mock import AsyncMock, MagicMock

    from core.services.embeddings_service import EmbeddingsService
    from core.utils.result_simplified import Result

    mock_backend = MagicMock()
    mock_backend.store_embedding_metadata = AsyncMock()
    mock_backend.get_embedding_metadata = AsyncMock()
    mock_backend.get_cached_embedding = AsyncMock()
    # Freshness pre-check reads (ADR-074 §8): no stored rows = nothing fresh,
    # so the worker embeds the full batch — the pre-#493 behavior these tests
    # were written against.
    mock_backend.get_embedding_freshness = AsyncMock(return_value=Result.ok([]))
    mock_backend.touch_embedding_updated_at = AsyncMock(return_value=Result.ok([{"touched": 0}]))
    mock_client = MagicMock()
    mock_client.model = "BAAI/bge-m3"
    mock_client.dimension = 1024
    mock_client.max_input_chars = 20000
    mock_client.embed = AsyncMock()
    return EmbeddingsService(mock_backend, embedding_client=mock_client)


@pytest.fixture
def event_bus():
    """Create a simple event bus for testing."""
    from adapters.infrastructure.event_bus import InMemoryEventBus

    return InMemoryEventBus()


@pytest.fixture
def user_uid():
    """Standard test user UID."""
    return "user_test_async_embeddings"


@pytest_asyncio.fixture
async def tasks_backend(neo4j_driver):
    """Create tasks backend for testing."""
    from core.models.enums.neo_labels import NeoLabel
    from core.models.task.task import Task

    return UniversalNeo4jBackend[Task](
        neo4j_driver, NeoLabel.TASK, Task, base_label=NeoLabel.ENTITY
    )


@pytest_asyncio.fixture
async def tasks_service(tasks_backend, event_bus):
    """Create tasks core service for testing."""
    from core.services.tasks.tasks_core_service import TasksCoreService

    return TasksCoreService(backend=tasks_backend, event_bus=event_bus)


@pytest_asyncio.fixture
async def goals_backend(neo4j_driver):
    """Create goals backend for testing."""
    from core.models.enums.neo_labels import NeoLabel
    from core.models.goal.goal import Goal

    return UniversalNeo4jBackend[Goal](
        neo4j_driver, NeoLabel.GOAL, Goal, base_label=NeoLabel.ENTITY
    )


@pytest_asyncio.fixture
async def goals_service(goals_backend, event_bus):
    """Create goals core service for testing."""

    from core.services.goals.goals_core_service import GoalsCoreService

    return GoalsCoreService(
        backend=goals_backend,
        event_bus=event_bus,
    )


@pytest_asyncio.fixture
async def habits_backend(neo4j_driver):
    """Create habits backend for testing."""
    from core.models.enums.neo_labels import NeoLabel
    from core.models.habit.habit import Habit

    return UniversalNeo4jBackend[Habit](
        neo4j_driver, NeoLabel.HABIT, Habit, base_label=NeoLabel.ENTITY
    )


@pytest_asyncio.fixture
async def habits_service(habits_backend, event_bus):
    """Create habits core service for testing."""
    from core.services.habits.habits_core_service import HabitsCoreService

    return HabitsCoreService(backend=habits_backend, event_bus=event_bus)


@pytest_asyncio.fixture
async def events_backend(neo4j_driver):
    """Create events backend for testing."""
    from core.models.enums.neo_labels import NeoLabel
    from core.models.event.event import Event

    return UniversalNeo4jBackend[Event](
        neo4j_driver, NeoLabel.EVENT, Event, base_label=NeoLabel.ENTITY
    )


@pytest_asyncio.fixture
async def events_service(events_backend, event_bus):
    """Create events core service for testing."""
    from core.services.events.events_core_service import EventsCoreService

    return EventsCoreService(backend=events_backend, event_bus=event_bus)


@pytest_asyncio.fixture
async def choices_backend(neo4j_driver):
    """Create choices backend for testing."""
    from core.models.choice.choice import Choice
    from core.models.enums.neo_labels import NeoLabel

    return UniversalNeo4jBackend[Choice](
        neo4j_driver, NeoLabel.CHOICE, Choice, base_label=NeoLabel.ENTITY
    )


@pytest_asyncio.fixture
async def choices_service(choices_backend, event_bus):
    """Create choices core service for testing."""
    from core.services.choices.choices_core_service import ChoicesCoreService

    return ChoicesCoreService(backend=choices_backend, event_bus=event_bus)


@pytest_asyncio.fixture
async def principles_backend(neo4j_driver):
    """Create principles backend for testing."""
    from core.models.enums.neo_labels import NeoLabel
    from core.models.principle.principle import Principle

    return UniversalNeo4jBackend[Principle](
        neo4j_driver, NeoLabel.PRINCIPLE, Principle, base_label=NeoLabel.ENTITY
    )


@pytest_asyncio.fixture
async def principles_service(principles_backend, event_bus):
    """Create principles core service for testing."""
    from core.services.principles.principles_core_service import PrinciplesCoreService

    return PrinciplesCoreService(backend=principles_backend, event_bus=event_bus)
