"""
Integration Test Template - SKUEL Best Practices
================================================

This template demonstrates SKUEL testing patterns for integration tests.

**When to Use:**
- Testing service layer with real Neo4j database
- Testing cross-domain interactions
- Testing graph queries and relationships

**Key Patterns:**
1. Type annotations on ALL fixtures and test methods
2. Result[T] unwrapping for service methods
3. Proper fixture organization
4. Clear test documentation
5. Descriptive assertions with helpful error messages

**See Also:**
- /docs/patterns/error_handling.md - Result[T] pattern
- /docs/testing/integration_test_guide.md - Testing guidelines
- /tests/integration/test_curriculum_core_integration.py - Reference implementation
"""

from collections.abc import Generator
from typing import Any

import pytest

# Import domain models
from core.models.example.example import Example  # Replace with your domain model

# Import services (if testing service layer)
from core.services.example_service import ExampleService  # Replace with your service
from testcontainers.neo4j import Neo4jContainer

# Import backends (if testing backend layer)
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend

# Import shared enums/types
from core.models.enums import Domain  # Import relevant enums

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def example_backend(neo4j_container: Neo4jContainer) -> UniversalNeo4jBackend[Example]:
    """
    Create backend for Example domain with real Neo4j.

    **Pattern:**
    - Accept neo4j_container fixture (provided by conftest.py)
    - Create driver from container URL
    - Return UniversalNeo4jBackend[T] with proper type annotation

    Args:
        neo4j_container: TestContainers Neo4j instance

    Returns:
        Typed backend for Example domain
    """
    from neo4j import AsyncGraphDatabase

    uri = neo4j_container.get_connection_url()
    driver = AsyncGraphDatabase.driver(uri)

    # validate_label=False for test-only labels not in NeoLabel enum
    return UniversalNeo4jBackend[Example](driver, "Example", Example, validate_label=False)


@pytest.fixture
def example_service(example_backend: UniversalNeo4jBackend[Example]) -> ExampleService:
    """
    Create service with backend dependency.

    **Pattern:**
    - Inject backend fixture as dependency
    - Return service instance with type annotation

    Args:
        example_backend: Backend for Example domain

    Returns:
        ExampleService instance
    """
    return ExampleService(example_backend)


@pytest.fixture
def clean_database(neo4j_container: Neo4jContainer, event_loop: Any) -> Generator[None, None, None]:
    """
    Clean database before and after tests.

    **Pattern:**
    - Setup: Clean database before test
    - Yield: Run test
    - Teardown: Clean database after test and close driver

    Args:
        neo4j_container: TestContainers Neo4j instance
        event_loop: pytest-asyncio event loop

    Yields:
        None (fixture setup/teardown only)
    """
    from neo4j import AsyncGraphDatabase

    uri = neo4j_container.get_connection_url()
    driver = AsyncGraphDatabase.driver(uri)

    async def cleanup() -> None:
        """Delete all test data."""
        async with driver.session() as session:
            await session.run("""
                MATCH (n:Example)
                OPTIONAL MATCH (n)-[r]-()
                DELETE r, n
            """)

    # Setup: Clean before test
    event_loop.run_until_complete(cleanup())

    yield  # Run test

    # Teardown: Clean after test
    event_loop.run_until_complete(cleanup())
    event_loop.run_until_complete(driver.close())


# ============================================================================
# TEST CLASSES
# ============================================================================


class TestExampleCRUD:
    """
    Test CRUD operations for Example domain.

    **Pattern:**
    - Group related tests in classes
    - Use descriptive class names (Test + Feature)
    - Add class docstring explaining test scope
    """

    @pytest.mark.asyncio
    async def test_create_example(
        self,
        example_backend: UniversalNeo4jBackend[Example],
        clean_database: None,
    ) -> None:
        """
        Should create Example entity in Neo4j.

        **Pattern:**
        - Add `-> None` return type annotation
        - Use descriptive test name (test_ACTION_EXPECTED_OUTCOME)
        - Add docstring explaining what the test verifies
        - Unwrap Result[T] before assertions
        """
        # Arrange: Create domain model instance
        example = Example(
            uid="example:test_1",
            title="Test Example",
            domain=Domain.TECH,
        )

        # Act: Call service method
        result = await example_backend.create(example)

        # Assert: Verify Result is OK
        assert result.is_ok, (
            f"Failed to create example: {result.error if result.is_error else 'Unknown error'}"
        )

        # Assert: Verify created entity
        created_example = result.value
        assert created_example.uid == "example:test_1"
        assert created_example.title == "Test Example"

    @pytest.mark.asyncio
    async def test_get_example(
        self,
        example_backend: UniversalNeo4jBackend[Example],
        clean_database: None,
    ) -> None:
        """
        Should retrieve Example entity from Neo4j.

        **Pattern:**
        - Setup: Create entity first
        - Act: Retrieve entity
        - Assert: Verify retrieved matches created
        """
        # Setup: Create example
        example = Example(uid="example:test_get", title="Get Test")
        create_result = await example_backend.create(example)
        assert create_result.is_ok, "Setup failed: Could not create example"

        # Act: Retrieve example
        get_result = await example_backend.get("example:test_get")

        # Assert: Verify Result is OK
        assert get_result.is_ok, (
            f"Failed to get example: {get_result.error if get_result.is_error else 'Unknown error'}"
        )

        # Assert: Verify retrieved entity
        retrieved = get_result.value
        assert retrieved is not None, "Expected example to exist, got None"
        assert retrieved.uid == "example:test_get"
        assert retrieved.title == "Get Test"

    @pytest.mark.asyncio
    async def test_update_example(
        self,
        example_backend: UniversalNeo4jBackend[Example],
        clean_database: None,
    ) -> None:
        """
        Should update Example entity in Neo4j.

        **Pattern:**
        - Setup: Create entity
        - Act: Update with dictionary
        - Assert: Verify updated fields
        """
        # Setup: Create example
        example = Example(uid="example:test_update", title="Original Title")
        create_result = await example_backend.create(example)
        assert create_result.is_ok, "Setup failed"

        # Act: Update example
        updates = {"title": "Updated Title"}
        update_result = await example_backend.update("example:test_update", updates)

        # Assert: Verify update succeeded
        assert update_result.is_ok, (
            f"Failed to update: {update_result.error if update_result.is_error else 'Unknown'}"
        )

        # Assert: Verify updated value
        updated = update_result.value
        assert updated.title == "Updated Title"

    @pytest.mark.asyncio
    async def test_delete_example(
        self,
        example_backend: UniversalNeo4jBackend[Example],
        clean_database: None,
    ) -> None:
        """
        Should delete Example entity from Neo4j.

        **Pattern:**
        - Setup: Create entity
        - Act: Delete entity
        - Assert: Verify deletion (get returns None)
        """
        # Setup: Create example
        example = Example(uid="example:test_delete", title="Delete Test")
        create_result = await example_backend.create(example)
        assert create_result.is_ok, "Setup failed"

        # Act: Delete example
        delete_result = await example_backend.delete("example:test_delete")

        # Assert: Verify deletion succeeded
        assert delete_result.is_ok, (
            f"Failed to delete: {delete_result.error if delete_result.is_error else 'Unknown'}"
        )
        assert delete_result.value is True, "Expected delete to return True"

        # Assert: Verify entity no longer exists
        get_result = await example_backend.get("example:test_delete")
        assert get_result.is_ok, "Get query failed"
        assert get_result.value is None, "Expected deleted entity to be None"


class TestExampleService:
    """
    Test service layer operations for Example domain.

    **Pattern:**
    - Test service methods that return Result[T]
    - Always unwrap Result before assertions
    - Test both success and error cases
    """

    @pytest.mark.asyncio
    async def test_service_create(
        self,
        example_service: ExampleService,
        clean_database: None,
    ) -> None:
        """
        Should create Example via service layer.

        **Pattern - Service Testing:**
        - Service methods return Result[T]
        - ALWAYS unwrap Result before assertions
        - Check both result.is_ok and result.value
        """
        # Arrange
        example_data = {
            "uid": "example:service_test",
            "title": "Service Test",
            "domain": Domain.TECH,
        }

        # Act
        create_result = await example_service.create(example_data)

        # Assert: Check Result wrapper
        assert create_result.is_ok, (
            f"Service create failed: {create_result.error if create_result.is_error else 'Unknown'}"
        )

        # Assert: Check unwrapped value
        created = create_result.value
        assert created.uid == "example:service_test"
        assert created.title == "Service Test"

    @pytest.mark.asyncio
    async def test_service_get(
        self,
        example_service: ExampleService,
        clean_database: None,
    ) -> None:
        """
        Should retrieve Example via service layer.

        **Pattern - Result[T] Unwrapping:**
        ```python
        result = await service.method()  # Returns Result[T]
        assert result.is_ok  # Check success
        value = result.value  # Unwrap value
        assert value.field == expected  # Assert on value
        ```
        """
        # Setup: Create via service
        create_data = {"uid": "example:service_get", "title": "Get Test"}
        create_result = await example_service.create(create_data)
        assert create_result.is_ok, "Setup failed"

        # Act: Get via service
        get_result = await example_service.get("example:service_get")

        # Assert: Unwrap and verify
        assert get_result.is_ok, (
            f"Service get failed: {get_result.error if get_result.is_error else 'Unknown'}"
        )
        retrieved = get_result.value
        assert retrieved.uid == "example:service_get"
        assert retrieved.title == "Get Test"


class TestExampleRelationships:
    """
    Test graph relationships for Example domain.

    **Pattern:**
    - Test relationship creation with raw Cypher
    - Test relationship queries via service methods
    - Verify relationship properties and direction
    """

    @pytest.mark.asyncio
    async def test_create_relationship(
        self,
        neo4j_container: Neo4jContainer,
        clean_database: None,
    ) -> None:
        """
        Should create relationship between Example entities.

        **Pattern - Raw Cypher for Relationships:**
        When testing relationships, use raw Cypher to:
        1. Create entities with relationships
        2. Query relationship patterns
        3. Verify relationship properties
        """
        from neo4j import AsyncGraphDatabase

        uri = neo4j_container.get_connection_url()
        driver = AsyncGraphDatabase.driver(uri)

        # Arrange & Act: Create entities with relationship
        async with driver.session() as session:
            await session.run("""
                CREATE (e1:Example {uid: 'example:parent', title: 'Parent'})
                CREATE (e2:Example {uid: 'example:child', title: 'Child'})
                CREATE (e1)-[:HAS_CHILD {strength: 'strong'}]->(e2)
            """)

        # Assert: Verify relationship exists
        async with driver.session() as session:
            result = await session.run("""
                MATCH (parent:Example {uid: 'example:parent'})-[r:HAS_CHILD]->(child:Example {uid: 'example:child'})
                RETURN parent.uid as parent_uid, child.uid as child_uid, r.strength as strength
            """)
            record = await result.single()

            assert record is not None, "Relationship not found"
            assert record["parent_uid"] == "example:parent"
            assert record["child_uid"] == "example:child"
            assert record["strength"] == "strong"

        await driver.close()


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================


class TestExampleErrorHandling:
    """
    Test error handling and edge cases.

    **Pattern:**
    - Test Result[T] error cases
    - Test validation errors
    - Test database constraint violations
    """

    @pytest.mark.asyncio
    async def test_get_nonexistent_example(
        self,
        example_service: ExampleService,
        clean_database: None,
    ) -> None:
        """
        Should return error when getting nonexistent Example.

        **Pattern - Testing Errors:**
        - Call service method
        - Check result.is_error
        - Verify error details via result.error
        """
        # Act: Try to get nonexistent example
        get_result = await example_service.get("example:nonexistent")

        # Assert: Verify error Result
        assert get_result.is_error, "Expected error for nonexistent example"

        # Assert: Verify error details
        error = get_result.error
        assert error is not None
        assert "not found" in error.message.lower() or "does not exist" in error.message.lower()


# ============================================================================
# INTEGRATION TESTS (Cross-Domain)
# ============================================================================


class TestExampleIntegration:
    """
    Test cross-domain integrations.

    **Pattern:**
    - Test interactions between multiple domains
    - Test complex workflows
    - Test graph traversals across domains
    """

    @pytest.mark.asyncio
    async def test_example_with_user_context(
        self,
        neo4j_container: Neo4jContainer,
        clean_database: None,
    ) -> None:
        """
        Should integrate Example with User context.

        **Pattern - Integration Testing:**
        - Create entities across multiple domains
        - Create cross-domain relationships
        - Query integrated data
        - Verify complete workflow
        """
        from neo4j import AsyncGraphDatabase

        uri = neo4j_container.get_connection_url()
        driver = AsyncGraphDatabase.driver(uri)

        # Setup: Create user and example entities
        async with driver.session() as session:
            await session.run("""
                CREATE (u:User {uid: 'user:test', title: 'Test User', email: 'test@example.com'})
                CREATE (e:Example {uid: 'example:user_owned', title: 'User Example'})
                CREATE (u)-[:OWNS]->(e)
            """)

        # Act: Query integrated data
        async with driver.session() as session:
            result = await session.run("""
                MATCH (u:User {uid: 'user:test'})-[:OWNS]->(e:Example)
                RETURN u.title as user_title, e.title as example_title
            """)
            record = await result.single()

            # Assert: Verify integration
            assert record is not None
            assert record["user_title"] == "Test User"
            assert record["example_title"] == "User Example"

        await driver.close()


# ============================================================================
# BEST PRACTICES CHECKLIST
# ============================================================================

"""
Integration Test Best Practices Checklist:
==========================================

✅ Type Annotations:
   - All fixtures have return type annotations
   - All test methods have `-> None` return type
   - All parameters have type annotations

✅ Result[T] Pattern:
   - Service methods return Result[T]
   - Tests unwrap Result before assertions
   - Tests check both result.is_ok and result.value
   - Error tests check result.is_error and result.error

✅ Fixtures:
   - Backend fixtures return UniversalNeo4jBackend[T]
   - Service fixtures inject backend dependencies
   - Cleanup fixtures use Generator[None, None, None]
   - Fixtures have clear docstrings

✅ Test Organization:
   - Related tests grouped in classes
   - Descriptive test names (test_ACTION_EXPECTED_OUTCOME)
   - Clear Arrange-Act-Assert structure
   - Helpful assertion messages

✅ Documentation:
   - Module docstring explains test scope
   - Class docstrings explain test category
   - Test docstrings explain what's being verified
   - Inline comments for complex setup

✅ Error Handling:
   - Tests verify Result.is_ok with helpful error messages
   - Error cases tested explicitly
   - Edge cases covered
   - Database constraints validated

✅ Performance:
   - Database cleaned before/after tests
   - Minimal data created per test
   - Efficient queries (avoid N+1 patterns)
   - Tests are independent (can run in any order)
"""
