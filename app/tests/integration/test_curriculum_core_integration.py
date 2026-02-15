"""
Integration Tests for Curriculum Architecture (KU, LS, LP)
===========================================================

Tests the three core curriculum entities with real Neo4j:
- KU (Knowledge Unit): Atomic knowledge content
- LS (Learning Step): Single step in learning journey
- LP (Learning Path): Complete learning sequence

Test Coverage:
- CRUD operations for each entity
- Relationship creation (REQUIRES, ENABLES, etc.)
- User mastery tracking integration
- Curriculum flow (ku → ls → lp)
"""

from collections.abc import Generator
from typing import Any

import pytest
from testcontainers.neo4j import Neo4jContainer

# Backend
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums import Domain, LearningLevel, SELCategory

# Domain models - use unified Ku model
from core.models.ku.ku import Ku

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def ku_backend(neo4j_container: Neo4jContainer) -> UniversalNeo4jBackend[Ku]:
    """Create KU backend with real Neo4j."""
    from neo4j import AsyncGraphDatabase

    uri = neo4j_container.get_connection_url()
    driver = AsyncGraphDatabase.driver(uri)

    return UniversalNeo4jBackend[Ku](driver, "Ku", Ku)


@pytest.fixture
def lp_backend(neo4j_container: Neo4jContainer) -> UniversalNeo4jBackend[Ku]:
    """Create LP backend with real Neo4j (unified Ku model)."""
    from neo4j import AsyncGraphDatabase

    uri = neo4j_container.get_connection_url()
    driver = AsyncGraphDatabase.driver(uri)

    return UniversalNeo4jBackend[Ku](driver, "Ku", Ku)


@pytest.fixture
def ls_backend(neo4j_container: Neo4jContainer) -> UniversalNeo4jBackend[Ku]:
    """Create LS backend with real Neo4j (unified Ku model)."""
    from neo4j import AsyncGraphDatabase

    uri = neo4j_container.get_connection_url()
    driver = AsyncGraphDatabase.driver(uri)

    return UniversalNeo4jBackend[Ku](driver, "Ku", Ku)


@pytest.fixture
def clean_curriculum(
    neo4j_container: Neo4jContainer, event_loop: Any
) -> Generator[None, None, None]:
    """Clean all curriculum data before tests."""
    from neo4j import AsyncGraphDatabase

    uri = neo4j_container.get_connection_url()
    driver = AsyncGraphDatabase.driver(uri)

    async def cleanup():
        async with driver.session() as session:
            # Delete all curriculum entities and relationships
            await session.run("""
                MATCH (n)
                WHERE n:Ku
                OPTIONAL MATCH (n)-[r]-()
                DETACH DELETE r, n
            """)

    event_loop.run_until_complete(cleanup())

    yield

    event_loop.run_until_complete(cleanup())
    event_loop.run_until_complete(driver.close())


# ============================================================================
# KNOWLEDGE UNIT (KU) TESTS
# ============================================================================


class TestKnowledgeUnitCRUD:
    """Test KU CRUD operations with real Neo4j."""

    @pytest.mark.asyncio
    async def test_create_knowledge_unit(self, ku_backend, clean_curriculum) -> None:
        """Should create KU in Neo4j."""
        ku = Ku(
            uid="ku:test_python_basics",
            title="Python Basics",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_MANAGEMENT,
            learning_level=LearningLevel.BEGINNER,
        )

        result = await ku_backend.create(ku)

        assert result.is_ok
        assert result.value.uid == "ku:test_python_basics"
        assert result.value.title == "Python Basics"

    @pytest.mark.asyncio
    async def test_get_knowledge_unit(self, ku_backend, clean_curriculum) -> None:
        """Should retrieve KU from Neo4j."""
        # Create KU
        ku = Ku(
            uid="ku:test_get",
            title="Test Get",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_MANAGEMENT,
        )
        result = await ku_backend.create(ku)
        assert result.is_ok, "Setup failed: Could not create KU"

        # Retrieve KU
        result = await ku_backend.get("ku:test_get")

        assert result.is_ok
        assert result.value is not None
        assert result.value.uid == "ku:test_get"
        assert result.value.title == "Test Get"

    @pytest.mark.asyncio
    async def test_update_knowledge_unit(self, ku_backend, clean_curriculum) -> None:
        """Should update KU in Neo4j."""
        # Create KU
        ku = Ku(
            uid="ku:test_update",
            title="Original Title",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_MANAGEMENT,
        )
        create_result = await ku_backend.create(ku)
        assert create_result.is_ok

        # Update KU with dictionary of changes
        updates = {
            "title": "Updated Title",
            "content": "Updated content",
        }
        update_result = await ku_backend.update("ku:test_update", updates)

        assert update_result.is_ok
        assert update_result.value.title == "Updated Title"
        assert update_result.value.content == "Updated content"

    @pytest.mark.asyncio
    async def test_delete_knowledge_unit(self, ku_backend, clean_curriculum) -> None:
        """Should delete KU from Neo4j."""
        # Create KU
        ku = Ku(
            uid="ku:test_delete",
            title="Test Delete",
            domain=Domain.TECH,
            sel_category=SELCategory.SELF_MANAGEMENT,
        )
        result = await ku_backend.create(ku)
        assert result.is_ok, "Setup failed: Could not create KU"

        # Delete KU
        delete_result = await ku_backend.delete("ku:test_delete")
        assert delete_result.is_ok
        assert delete_result.value is True

        # Verify deletion
        get_result = await ku_backend.get("ku:test_delete")
        assert get_result.is_ok
        assert get_result.value is None


# ============================================================================
# LEARNING STEP (LS) TESTS
# ============================================================================


class TestLearningStepCRUD:
    """Test LS CRUD operations with real Neo4j."""

    @pytest.mark.asyncio
    async def test_create_learning_step(self, ls_backend, clean_curriculum) -> None:
        """Should create LS in Neo4j."""
        ls = Ku(
            uid="ls:test_step_1",
            title="Step 1: Learn Python Basics",
            intent="Master Python fundamentals",
            description="First step in Python journey",
            estimated_hours=1.0,
        )

        result = await ls_backend.create(ls)

        assert result.is_ok
        assert result.value.uid == "ls:test_step_1"
        assert result.value.title == "Step 1: Learn Python Basics"
        assert result.value.intent == "Master Python fundamentals"

    @pytest.mark.asyncio
    async def test_get_learning_step(self, ls_backend, clean_curriculum) -> None:
        """Should retrieve LS from Neo4j."""
        # Create LS
        ls = Ku(
            uid="ls:test_get",
            title="Test Get Step",
            intent="Test learning objective",
            description="Test description",
        )
        result = await ls_backend.create(ls)
        assert result.is_ok, "Setup failed: Could not create LS"

        # Retrieve LS
        result = await ls_backend.get("ls:test_get")

        assert result.is_ok
        assert result.value is not None
        assert result.value.uid == "ls:test_get"
        assert result.value.title == "Test Get Step"

    @pytest.mark.asyncio
    async def test_update_learning_step(self, ls_backend, clean_curriculum) -> None:
        """Should update LS in Neo4j."""
        # Create LS
        ls = Ku(
            uid="ls:test_update",
            title="Original Step Title",
            intent="Original learning objective",
            description="Original description",
            estimated_hours=1.0,
        )
        create_result = await ls_backend.create(ls)
        assert create_result.is_ok

        # Update LS with dictionary of changes
        updates = {
            "title": "Updated Step Title",
            "intent": "Updated learning objective",
            "description": "Updated description",
            "estimated_hours": 2.0,
        }
        update_result = await ls_backend.update("ls:test_update", updates)

        assert update_result.is_ok
        assert update_result.value.title == "Updated Step Title"
        assert update_result.value.intent == "Updated learning objective"
        assert update_result.value.description == "Updated description"
        assert update_result.value.estimated_hours == 2.0

    @pytest.mark.asyncio
    async def test_delete_learning_step(self, ls_backend, clean_curriculum) -> None:
        """Should delete LS from Neo4j."""
        # Create LS
        ls = Ku(
            uid="ls:test_delete",
            title="Test Delete Step",
            intent="Test deletion",
            description="This step will be deleted",
        )
        result = await ls_backend.create(ls)
        assert result.is_ok, "Setup failed: Could not create LS"

        # Delete LS
        delete_result = await ls_backend.delete("ls:test_delete")
        assert delete_result.is_ok
        assert delete_result.value is True

        # Verify deletion
        get_result = await ls_backend.get("ls:test_delete")
        assert get_result.is_ok
        assert get_result.value is None


# ============================================================================
# LEARNING PATH (LP) TESTS
# ============================================================================


class TestLearningPathCRUD:
    """Test LP CRUD operations with real Neo4j."""

    @pytest.mark.asyncio
    async def test_create_learning_path(self, lp_backend, clean_curriculum) -> None:
        """Should create LP in Neo4j."""
        lp = Ku(
            uid="lp:test_python_journey",
            title="Python Learning Journey",
            description="Complete path to Python mastery",
            domain=Domain.TECH,
            difficulty_rating=0.5,  # intermediate
        )

        result = await lp_backend.create(lp)

        assert result.is_ok
        assert result.value.uid == "lp:test_python_journey"
        assert result.value.title == "Python Learning Journey"

    @pytest.mark.asyncio
    async def test_get_learning_path(self, lp_backend, clean_curriculum) -> None:
        """Should retrieve LP from Neo4j."""
        # Create LP
        lp = Ku(
            uid="lp:test_get",
            title="Test Get Path",
            description="Test learning goal",
            domain=Domain.TECH,
        )
        result = await lp_backend.create(lp)
        assert result.is_ok, "Setup failed: Could not create LP"

        # Retrieve LP
        result = await lp_backend.get("lp:test_get")

        assert result.is_ok
        assert result.value is not None
        assert result.value.uid == "lp:test_get"
        assert result.value.title == "Test Get Path"

    @pytest.mark.asyncio
    async def test_update_learning_path(self, lp_backend, clean_curriculum) -> None:
        """Should update LP in Neo4j."""
        # Create LP
        lp = Ku(
            uid="lp:test_update",
            title="Original Path Name",
            description="Original learning goal",
            domain=Domain.TECH,
            difficulty_rating=0.3,  # beginner
            estimated_hours=10.0,
        )
        create_result = await lp_backend.create(lp)
        assert create_result.is_ok

        # Update LP with dictionary of changes
        updates = {
            "title": "Updated Path Name",
            "description": "Updated learning goal",
            "difficulty_rating": 0.8,  # advanced
            "estimated_hours": 25.0,
        }
        update_result = await lp_backend.update("lp:test_update", updates)

        assert update_result.is_ok
        assert update_result.value.title == "Updated Path Name"
        assert update_result.value.description == "Updated learning goal"
        assert update_result.value.difficulty_rating == 0.8
        assert update_result.value.estimated_hours == 25.0

    @pytest.mark.asyncio
    async def test_delete_learning_path(self, lp_backend, clean_curriculum) -> None:
        """Should delete LP from Neo4j."""
        # Create LP
        lp = Ku(
            uid="lp:test_delete",
            title="Test Delete Path",
            description="This path will be deleted",
            domain=Domain.TECH,
        )
        result = await lp_backend.create(lp)
        assert result.is_ok, "Setup failed: Could not create LP"

        # Delete LP
        delete_result = await lp_backend.delete("lp:test_delete")
        assert delete_result.is_ok
        assert delete_result.value is True

        # Verify deletion
        get_result = await lp_backend.get("lp:test_delete")
        assert get_result.is_ok
        assert get_result.value is None


# ============================================================================
# CURRICULUM RELATIONSHIPS TESTS
# ============================================================================


class TestCurriculumRelationships:
    """Test relationships between KU, LS, and LP."""

    @pytest.mark.asyncio
    async def test_ku_prerequisite_relationship(self, neo4j_container, clean_curriculum) -> None:
        """Should create REQUIRES relationship between KUs."""
        from neo4j import AsyncGraphDatabase

        uri = neo4j_container.get_connection_url()
        driver = AsyncGraphDatabase.driver(uri)

        # Create two KUs with prerequisite relationship
        async with driver.session() as session:
            await session.run("""
                CREATE (ku1:Ku {
                    uid: 'ku:python_basics',
                    title: 'Python Basics',
                    content: 'Basic Python',
                    domain: 'tech',
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (ku2:Ku {
                    uid: 'ku:python_advanced',
                    title: 'Advanced Python',
                    content: 'Advanced Python',
                    domain: 'tech',
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (ku2)-[:REQUIRES]->(ku1)
            """)

        # Verify relationship exists
        async with driver.session() as session:
            result = await session.run("""
                MATCH (ku2:Ku {uid: 'ku:python_advanced'})-[:REQUIRES]->(ku1:Ku {uid: 'ku:python_basics'})
                RETURN ku1.uid as prereq_uid, ku2.uid as dependent_uid
            """)
            record = await result.single()

            assert record is not None
            assert record["prereq_uid"] == "ku:python_basics"
            assert record["dependent_uid"] == "ku:python_advanced"

        await driver.close()

    @pytest.mark.asyncio
    async def test_lp_contains_ls_relationship(self, neo4j_container, clean_curriculum) -> None:
        """Should create CONTAINS relationship between LP and LS."""
        from neo4j import AsyncGraphDatabase

        uri = neo4j_container.get_connection_url()
        driver = AsyncGraphDatabase.driver(uri)

        # Create LP and LS with CONTAINS relationship (both are Ku nodes)
        async with driver.session() as session:
            await session.run("""
                CREATE (lp:Ku {
                    uid: 'lp:python_journey',
                    title: 'Python Journey',
                    description: 'Learn Python',
                    domain: 'tech',
                    ku_type: 'learning_path',
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (ls:Ku {
                    uid: 'ls:step_1',
                    title: 'Step 1',
                    description: 'First step',
                    ku_type: 'learning_step',
                    order: 1,
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (lp)-[:CONTAINS {order: 1}]->(ls)
            """)

        # Verify relationship exists
        async with driver.session() as session:
            result = await session.run("""
                MATCH (lp:Ku {uid: 'lp:python_journey'})-[r:CONTAINS]->(ls:Ku {uid: 'ls:step_1'})
                RETURN lp.uid as lp_uid, ls.uid as ls_uid, r.order as step_order
            """)
            record = await result.single()

            assert record is not None
            assert record["lp_uid"] == "lp:python_journey"
            assert record["ls_uid"] == "ls:step_1"
            assert record["step_order"] == 1

        await driver.close()


# ============================================================================
# USER MASTERY INTEGRATION TESTS
# ============================================================================


class TestCurriculumUserIntegration:
    """Test curriculum integration with user mastery tracking."""

    @pytest.mark.asyncio
    async def test_user_mastery_tracking(self, neo4j_container, clean_curriculum) -> None:
        """Should track user mastery of KUs."""
        from neo4j import AsyncGraphDatabase

        uri = neo4j_container.get_connection_url()
        driver = AsyncGraphDatabase.driver(uri)

        # Create user and KU with MASTERED relationship
        async with driver.session() as session:
            await session.run("""
                CREATE (u:User {
                    uid: 'user:test_learner',
                    title: 'Test Learner',
                    email: 'learner@test.com',
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (ku:Ku {
                    uid: 'ku:python_basics',
                    title: 'Python Basics',
                    content: 'Basic Python',
                    domain: 'tech',
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (u)-[:MASTERED {mastery_score: 0.85, mastered_at: datetime()}]->(ku)
            """)

        # Verify mastery relationship
        async with driver.session() as session:
            result = await session.run("""
                MATCH (u:User {uid: 'user:test_learner'})-[m:MASTERED]->(ku:Ku {uid: 'ku:python_basics'})
                RETURN u.uid as user_uid, ku.uid as ku_uid, m.mastery_score as score
            """)
            record = await result.single()

            assert record is not None
            assert record["user_uid"] == "user:test_learner"
            assert record["ku_uid"] == "ku:python_basics"
            assert record["score"] == 0.85

        await driver.close()


# ============================================================================
# CONTEXT BUILDER INTEGRATION TESTS
# ============================================================================


class TestCurriculumContextBuilder:
    """Test UserContextBuilder correctly queries and populates curriculum data."""

    @pytest.mark.asyncio
    async def test_builder_populates_mastered_knowledge(
        self, neo4j_container, clean_curriculum
    ) -> None:
        """
        Verify UserContextBuilder.build_user_context() correctly populates
        mastered knowledge UIDs and mastery scores from Neo4j queries.

        This tests the REAL construction pipeline, not manual mock data.
        """
        from neo4j import AsyncGraphDatabase

        from core.models.user.user import User
        from core.services.user.user_context_builder import UserContextBuilder

        uri = neo4j_container.get_connection_url()
        driver = AsyncGraphDatabase.driver(uri)

        # Setup: Create user and multiple KUs with varying mastery scores
        test_user_uid = "user:builder_test"
        async with driver.session() as session:
            await session.run(
                """
                CREATE (u:User {
                    uid: $user_uid,
                    title: 'Builder Test User',
                    email: 'builder@test.com',
                    display_name: 'Builder Test',
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (ku1:Ku {
                    uid: 'ku:python_basics',
                    title: 'Python Basics',
                    content: 'Basic Python',
                    domain: 'tech',
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (ku2:Ku {
                    uid: 'ku:advanced_python',
                    title: 'Advanced Python',
                    content: 'Advanced Python',
                    domain: 'tech',
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (ku3:Ku {
                    uid: 'ku:testing',
                    title: 'Testing',
                    content: 'Testing knowledge',
                    domain: 'tech',
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (u)-[:MASTERED {mastery_score: 0.9, mastered_at: datetime()}]->(ku1)
                CREATE (u)-[:MASTERED {mastery_score: 0.75, mastered_at: datetime()}]->(ku2)
                CREATE (u)-[:MASTERED {mastery_score: 0.6, mastered_at: datetime()}]->(ku3)
            """,
                user_uid=test_user_uid,
            )

        # Test: Build context using UserContextBuilder (THE real pipeline)
        builder = UserContextBuilder(driver)
        test_user = User(uid=test_user_uid, title="Builder Test User", email="builder@test.com")

        context_result = await builder.build_user_context(test_user_uid, test_user)

        # Verify Result is successful
        assert context_result.is_ok, (
            f"Failed to build context: {context_result.error if context_result.is_error else 'Unknown error'}"
        )
        context = context_result.value

        # Verify: Context populated with REAL Neo4j query results
        assert context.user_uid == test_user_uid
        assert context.username == "Builder Test User"

        # Verify mastered knowledge UIDs
        assert len(context.mastered_knowledge_uids) == 3
        assert "ku:python_basics" in context.mastered_knowledge_uids
        assert "ku:advanced_python" in context.mastered_knowledge_uids
        assert "ku:testing" in context.mastered_knowledge_uids

        # Verify knowledge mastery scores
        assert len(context.knowledge_mastery) == 3
        assert context.knowledge_mastery["ku:python_basics"] == 0.9
        assert context.knowledge_mastery["ku:advanced_python"] == 0.75
        assert context.knowledge_mastery["ku:testing"] == 0.6

        await driver.close()

    @pytest.mark.asyncio
    async def test_builder_populates_enrolled_learning_paths(
        self, neo4j_container, clean_curriculum
    ) -> None:
        """
        Verify UserContextBuilder correctly populates enrolled learning path UIDs.

        Tests the builder queries for ENROLLED_IN relationships.
        """
        from neo4j import AsyncGraphDatabase

        from core.models.user.user import User
        from core.services.user.user_context_builder import UserContextBuilder

        uri = neo4j_container.get_connection_url()
        driver = AsyncGraphDatabase.driver(uri)

        # Setup: Create user enrolled in multiple learning paths
        test_user_uid = "user:learning_path_test"
        async with driver.session() as session:
            await session.run(
                """
                CREATE (u:User {
                    uid: $user_uid,
                    title: 'Learning Path User',
                    email: 'lp@test.com',
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (lp1:Ku {
                    uid: 'lp:python_journey',
                    title: 'Python Journey',
                    description: 'Complete Python learning',
                    ku_type: 'learning_path',
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (lp2:Ku {
                    uid: 'lp:web_development',
                    title: 'Web Development',
                    description: 'Web dev path',
                    ku_type: 'learning_path',
                    created_at: datetime(),
                    updated_at: datetime()
                })
                // Add :Lp secondary labels for MEGA-QUERY/CONSOLIDATED_QUERY compatibility
                SET lp1:Lp, lp2:Lp

                CREATE (u)-[:ENROLLED_IN {enrolled_at: datetime()}]->(lp1)
                CREATE (u)-[:ENROLLED_IN {enrolled_at: datetime()}]->(lp2)
            """,
                user_uid=test_user_uid,
            )

        # Test: Build context via builder pipeline
        builder = UserContextBuilder(driver)
        test_user = User(uid=test_user_uid, title="Learning Path User", email="lp@test.com")

        context_result = await builder.build_user_context(test_user_uid, test_user)

        # Verify Result is successful
        assert context_result.is_ok, (
            f"Failed to build context: {context_result.error if context_result.is_error else 'Unknown error'}"
        )
        context = context_result.value

        # Verify: Enrolled learning paths populated from Neo4j queries
        assert len(context.enrolled_path_uids) == 2
        assert "lp:python_journey" in context.enrolled_path_uids
        assert "lp:web_development" in context.enrolled_path_uids

        await driver.close()

    @pytest.mark.asyncio
    async def test_builder_handles_no_curriculum_data(
        self, neo4j_container, clean_curriculum
    ) -> None:
        """
        Verify builder handles user with no curriculum entities gracefully.

        Tests that queries return empty collections when no data exists.
        """
        from neo4j import AsyncGraphDatabase

        from core.models.user.user import User
        from core.services.user.user_context_builder import UserContextBuilder

        uri = neo4j_container.get_connection_url()
        driver = AsyncGraphDatabase.driver(uri)

        # Setup: Create user with NO curriculum data
        test_user_uid = "user:empty_curriculum"
        async with driver.session() as session:
            await session.run(
                """
                CREATE (u:User {
                    uid: $user_uid,
                    title: 'Empty Curriculum User',
                    email: 'empty@test.com',
                    created_at: datetime(),
                    updated_at: datetime()
                })
            """,
                user_uid=test_user_uid,
            )

        # Test: Build context (should not fail on empty data)
        builder = UserContextBuilder(driver)
        test_user = User(uid=test_user_uid, title="Empty Curriculum User", email="empty@test.com")

        context_result = await builder.build_user_context(test_user_uid, test_user)

        # Verify Result is successful
        assert context_result.is_ok, (
            f"Failed to build context: {context_result.error if context_result.is_error else 'Unknown error'}"
        )
        context = context_result.value

        # Verify: Empty collections (not None, not errors)
        assert context.mastered_knowledge_uids == set()
        assert context.enrolled_path_uids == []
        assert context.knowledge_mastery == {}

        await driver.close()

    @pytest.mark.asyncio
    async def test_builder_integrates_curriculum_with_activity_domains(
        self, neo4j_container, clean_curriculum
    ) -> None:
        """
        Verify builder correctly integrates curriculum data alongside activity domains.

        Tests the complete pipeline with curriculum + tasks/habits/goals/events.
        This is the REAL production scenario.
        """
        from datetime import date, timedelta

        from neo4j import AsyncGraphDatabase

        from core.models.user.user import User
        from core.services.user.user_context_builder import UserContextBuilder

        uri = neo4j_container.get_connection_url()
        driver = AsyncGraphDatabase.driver(uri)

        # Setup: Create user with curriculum + activity domain entities
        test_user_uid = "user:integrated_test"
        async with driver.session() as session:
            await session.run(
                """
                // User
                CREATE (u:User {
                    uid: $user_uid,
                    title: 'Integrated User',
                    email: 'integrated@test.com',
                    created_at: datetime(),
                    updated_at: datetime()
                })

                // Curriculum: Knowledge units
                CREATE (ku1:Ku {
                    uid: 'ku:python',
                    title: 'Python',
                    content: 'Python programming',
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (ku2:Ku {
                    uid: 'ku:testing',
                    title: 'Testing',
                    content: 'Testing knowledge',
                    created_at: datetime(),
                    updated_at: datetime()
                })

                // Curriculum: Learning path
                CREATE (lp:Ku {
                    uid: 'lp:python_mastery',
                    title: 'Python Mastery',
                    description: 'Complete Python path',
                    ku_type: 'learning_path',
                    created_at: datetime(),
                    updated_at: datetime()
                })

                // Activity: Task
                CREATE (t:Task {
                    uid: 'task:build_api',
                    title: 'Build API',
                    user_uid: $user_uid,
                    status: 'in_progress',
                    priority: 'high',
                    due_date: date($due_date),
                    created_at: datetime(),
                    updated_at: datetime()
                })

                // Activity: Goal
                CREATE (g:Goal {
                    uid: 'goal:learn_python',
                    title: 'Learn Python',
                    user_uid: $user_uid,
                    status: 'active',
                    progress: 0.7,
                    created_at: datetime(),
                    updated_at: datetime()
                })

                // Add :Lp secondary label for CONSOLIDATED_QUERY compatibility
                SET lp:Lp

                // Relationships: Curriculum
                CREATE (u)-[:MASTERED {mastery_score: 0.8}]->(ku1)
                CREATE (u)-[:MASTERED {mastery_score: 0.6}]->(ku2)
                CREATE (u)-[:ENROLLED_IN]->(lp)

                // Relationships: Activity domains
                CREATE (u)-[:HAS_TASK]->(t)
                CREATE (u)-[:HAS_GOAL]->(g)

                // Cross-domain: Task applies knowledge
                CREATE (t)-[:APPLIES_KNOWLEDGE]->(ku1)
                CREATE (g)-[:REQUIRES_KNOWLEDGE]->(ku2)
            """,
                user_uid=test_user_uid,
                due_date=(date.today() + timedelta(days=3)).isoformat(),
            )

        # Test: Build context with COMPLETE domain integration
        builder = UserContextBuilder(driver)
        test_user = User(uid=test_user_uid, title="Integrated User", email="integrated@test.com")

        context_result = await builder.build_user_context(test_user_uid, test_user)

        # Verify Result is successful
        assert context_result.is_ok, (
            f"Failed to build context: {context_result.error if context_result.is_error else 'Unknown error'}"
        )
        context = context_result.value

        # Verify: ALL domain data populated correctly
        # User identity
        assert context.user_uid == test_user_uid
        assert context.username == "Integrated User"

        # Curriculum data
        assert len(context.mastered_knowledge_uids) == 2
        assert "ku:python" in context.mastered_knowledge_uids
        assert context.knowledge_mastery["ku:python"] == 0.8
        assert context.knowledge_mastery["ku:testing"] == 0.6
        assert len(context.enrolled_path_uids) == 1
        assert "lp:python_mastery" in context.enrolled_path_uids

        # Activity domain data
        assert len(context.active_task_uids) == 1
        assert "task:build_api" in context.active_task_uids
        assert len(context.active_goal_uids) == 1
        assert "goal:learn_python" in context.active_goal_uids
        assert context.goal_progress["goal:learn_python"] == 0.7

        await driver.close()
