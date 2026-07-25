"""
Integration Tests for Curriculum Architecture (KU, PS, LP)
===========================================================

Tests the three core curriculum entities with real Neo4j:
- KU (Knowledge Unit): Atomic knowledge content
- PS (PathStep): Single step in learning journey
- LP (Learning Path): Complete learning sequence

Test Coverage:
- CRUD operations for each entity
- Relationship creation (REQUIRES, ENABLES, etc.)
- User mastery tracking integration
- Curriculum flow (ku → ls → lp)
"""

from collections.abc import Generator

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.curriculum_backends import LpBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from adapters.persistence.neo4j.user_context_queries import UserContextQueryExecutor

# Domain models - use domain-specific types
from core.models.curriculum import Curriculum
from core.models.enums import Domain, LearningLevel, SELCategory

# Backend
from core.models.enums.neo_labels import NeoLabel
from core.models.pathways.learning_path import LearningPath
from core.models.pathways.path_step import PathStep
from core.models.relationship_names import RelationshipName

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def ku_backend(neo4j_driver) -> UniversalNeo4jBackend[Curriculum]:
    """Create KU backend with real Neo4j."""
    return UniversalNeo4jBackend[Curriculum](
        neo4j_driver, NeoLabel.PATH_STEP, Curriculum, base_label=NeoLabel.ENTITY
    )


@pytest.fixture
def lp_backend(neo4j_driver) -> LpBackend:
    """Create LP backend with real Neo4j."""
    return LpBackend(neo4j_driver, NeoLabel.LEARNING_PATH, LearningPath, base_label=NeoLabel.ENTITY)


@pytest.fixture
def ps_backend(neo4j_driver) -> UniversalNeo4jBackend[PathStep]:
    """Create PS backend with real Neo4j."""
    return UniversalNeo4jBackend[PathStep](
        neo4j_driver, NeoLabel.PATH_STEP, PathStep, base_label=NeoLabel.ENTITY
    )


@pytest_asyncio.fixture
async def clean_curriculum(neo4j_driver) -> Generator[None]:
    """Clean all curriculum data before tests."""

    async def cleanup():
        async with neo4j_driver.session() as session:
            # Delete all curriculum entities and relationships
            await session.run("""
                MATCH (n)
                WHERE n:Entity
                OPTIONAL MATCH (n)-[r]-()
                DETACH DELETE r, n
            """)

    await cleanup()

    yield

    await cleanup()


# ============================================================================
# KNOWLEDGE UNIT (KU) TESTS
# ============================================================================


class TestKnowledgeUnitCRUD:
    """Test KU CRUD operations with real Neo4j."""

    @pytest.mark.asyncio
    async def test_create_knowledge_unit(self, ku_backend, clean_curriculum) -> None:
        """Should create KU in Neo4j."""
        ku = Curriculum(
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
        ku = Curriculum(
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
        ku = Curriculum(
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
        ku = Curriculum(
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
# PATH STEP (PS) TESTS
# ============================================================================


class TestPathStepCRUD:
    """Test PS CRUD operations with real Neo4j."""

    @pytest.mark.asyncio
    async def test_create_path_step(self, ps_backend, clean_curriculum) -> None:
        """Should create PS in Neo4j."""
        ls = PathStep(
            uid="ps:test_step_1",
            title="Step 1: Learn Python Basics",
            intent="Master Python fundamentals",
            description="First step in Python journey",
            estimated_hours=1.0,
        )

        result = await ps_backend.create(ls)

        assert result.is_ok
        assert result.value.uid == "ps:test_step_1"
        assert result.value.title == "Step 1: Learn Python Basics"
        assert result.value.intent == "Master Python fundamentals"

    @pytest.mark.asyncio
    async def test_get_path_step(self, ps_backend, clean_curriculum) -> None:
        """Should retrieve PS from Neo4j."""
        # Create PS
        ls = PathStep(
            uid="ps:test_get",
            title="Test Get Step",
            intent="Test learning objective",
            description="Test description",
        )
        result = await ps_backend.create(ls)
        assert result.is_ok, "Setup failed: Could not create PS"

        # Retrieve PS
        result = await ps_backend.get("ps:test_get")

        assert result.is_ok
        assert result.value is not None
        assert result.value.uid == "ps:test_get"
        assert result.value.title == "Test Get Step"

    @pytest.mark.asyncio
    async def test_update_path_step(self, ps_backend, clean_curriculum) -> None:
        """Should update PS in Neo4j."""
        # Create PS
        ls = PathStep(
            uid="ps:test_update",
            title="Original Step Title",
            intent="Original learning objective",
            description="Original description",
            estimated_hours=1.0,
        )
        create_result = await ps_backend.create(ls)
        assert create_result.is_ok

        # Update PS with dictionary of changes
        updates = {
            "title": "Updated Step Title",
            "intent": "Updated learning objective",
            "description": "Updated description",
            "estimated_hours": 2.0,
        }
        update_result = await ps_backend.update("ps:test_update", updates)

        assert update_result.is_ok
        assert update_result.value.title == "Updated Step Title"
        assert update_result.value.intent == "Updated learning objective"
        assert update_result.value.description == "Updated description"
        assert update_result.value.estimated_hours == 2.0

    @pytest.mark.asyncio
    async def test_delete_path_step(self, ps_backend, clean_curriculum) -> None:
        """Should delete PS from Neo4j."""
        # Create PS
        ls = PathStep(
            uid="ps:test_delete",
            title="Test Delete Step",
            intent="Test deletion",
            description="This step will be deleted",
        )
        result = await ps_backend.create(ls)
        assert result.is_ok, "Setup failed: Could not create PS"

        # Delete PS
        delete_result = await ps_backend.delete("ps:test_delete")
        assert delete_result.is_ok
        assert delete_result.value is True

        # Verify deletion
        get_result = await ps_backend.get("ps:test_delete")
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
        lp = LearningPath(
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
        lp = LearningPath(
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
        lp = LearningPath(
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
        lp = LearningPath(
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
    """Test relationships between KU, PS, and LP."""

    @pytest.mark.asyncio
    async def test_ku_prerequisite_relationship(self, neo4j_driver, clean_curriculum) -> None:
        """Should create REQUIRES relationship between KUs."""
        # Create two KUs with prerequisite relationship
        async with neo4j_driver.session() as session:
            await session.run("""
                CREATE (ku1:Entity {
                    uid: 'ku:python_basics',
                    title: 'Python Basics',
                    content: 'Basic Python',
                    domain: 'tech',
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (ku2:Entity {
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
        async with neo4j_driver.session() as session:
            result = await session.run("""
                MATCH (ku2:Entity {uid: 'ku:python_advanced'})-[:REQUIRES]->(ku1:Entity {uid: 'ku:python_basics'})
                RETURN ku1.uid as prereq_uid, ku2.uid as dependent_uid
            """)
            record = await result.single()

            assert record is not None
            assert record["prereq_uid"] == "ku:python_basics"
            assert record["dependent_uid"] == "ku:python_advanced"

    @pytest.mark.asyncio
    async def test_lp_contains_ls_relationship(self, neo4j_driver, clean_curriculum) -> None:
        """Should create CONTAINS relationship between LP and PS."""
        # Create LP and PS with CONTAINS relationship (both are Entity nodes)
        async with neo4j_driver.session() as session:
            await session.run("""
                CREATE (lp:Entity {
                    uid: 'lp:python_journey',
                    title: 'Python Journey',
                    description: 'Learn Python',
                    domain: 'tech',
                    entity_type: 'learning_path',
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (ps:Entity {
                    uid: 'ps:step_1',
                    title: 'Step 1',
                    description: 'First step',
                    entity_type: 'path_step',
                    order: 1,
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (lp)-[:HAS_STEP {order: 1}]->(ps)
            """)

        # Verify relationship exists
        async with neo4j_driver.session() as session:
            result = await session.run("""
                MATCH (lp:Entity {uid: 'lp:python_journey'})-[r:HAS_STEP]->(ps:Entity {uid: 'ps:step_1'})
                RETURN lp.uid as lp_uid, ps.uid as ps_uid, r.order as step_order
            """)
            record = await result.single()

            assert record is not None
            assert record["lp_uid"] == "lp:python_journey"
            assert record["ps_uid"] == "ps:step_1"
            assert record["step_order"] == 1


# ============================================================================
# USER MASTERY INTEGRATION TESTS
# ============================================================================


class TestCurriculumUserIntegration:
    """Test curriculum integration with user mastery tracking."""

    @pytest.mark.asyncio
    async def test_user_mastery_tracking(self, neo4j_driver, clean_curriculum) -> None:
        """Should track user mastery of KUs."""
        # Create user and KU with MASTERED relationship
        async with neo4j_driver.session() as session:
            await session.run("""
                CREATE (u:User {
                    uid: 'user_test_learner',
                    title: 'Test Learner',
                    email: 'learner@test.com',
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (ku:Entity {
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
        async with neo4j_driver.session() as session:
            result = await session.run("""
                MATCH (u:User {uid: 'user_test_learner'})-[m:MASTERED]->(ku:Entity {uid: 'ku:python_basics'})
                RETURN u.uid as user_uid, ku.uid as ku_uid, m.mastery_score as score
            """)
            record = await result.single()

            assert record is not None
            assert record["user_uid"] == "user_test_learner"
            assert record["ku_uid"] == "ku:python_basics"
            assert record["score"] == 0.85


# ============================================================================
# CONTEXT BUILDER INTEGRATION TESTS
# ============================================================================


class TestCurriculumContextBuilder:
    """Test UserContextBuilder correctly queries and populates curriculum data."""

    @pytest.mark.asyncio
    async def test_builder_populates_mastered_knowledge(
        self, neo4j_driver, clean_curriculum
    ) -> None:
        """
        Verify UserContextBuilder.build_user_context() correctly populates
        mastered knowledge UIDs and mastery scores from Neo4j queries.

        This tests the REAL construction pipeline, not manual mock data.
        """
        from core.models.user.user import User
        from core.services.user.user_context_builder import UserContextBuilder

        # Setup: Create user and multiple KUs with varying mastery scores
        test_user_uid = "user_builder_test"
        async with neo4j_driver.session() as session:
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
                CREATE (ku1:Entity {
                    uid: 'ku:python_basics',
                    title: 'Python Basics',
                    content: 'Basic Python',
                    domain: 'tech',
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (ku2:Entity {
                    uid: 'ku:advanced_python',
                    title: 'Advanced Python',
                    content: 'Advanced Python',
                    domain: 'tech',
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (ku3:Entity {
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
        builder = UserContextBuilder(UserContextQueryExecutor(Neo4jQueryExecutor(neo4j_driver)))
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

    @pytest.mark.asyncio
    async def test_builder_populates_enrolled_learning_paths(
        self, neo4j_driver, clean_curriculum
    ) -> None:
        """
        Verify UserContextBuilder correctly populates enrolled learning path UIDs.

        Tests the builder queries for ENROLLED_IN relationships.
        """
        from core.models.user.user import User
        from core.services.user.user_context_builder import UserContextBuilder

        # Setup: Create user enrolled in multiple learning paths
        test_user_uid = "user_learning_path_test"
        async with neo4j_driver.session() as session:
            await session.run(
                """
                CREATE (u:User {
                    uid: $user_uid,
                    title: 'Learning Path User',
                    email: 'lp@test.com',
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (lp1:Entity {
                    uid: 'lp:python_journey',
                    title: 'Python Journey',
                    description: 'Complete Python learning',
                    entity_type: 'learning_path',
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (lp2:Entity {
                    uid: 'lp:web_development',
                    title: 'Web Development',
                    description: 'Web dev path',
                    entity_type: 'learning_path',
                    created_at: datetime(),
                    updated_at: datetime()
                })
                // Add :LearningPath secondary labels for MEGA-QUERY/CONSOLIDATED_QUERY compatibility
                SET lp1:LearningPath, lp2:LearningPath

                CREATE (u)-[:ENROLLED_IN {enrolled_at: datetime()}]->(lp1)
                CREATE (u)-[:ENROLLED_IN {enrolled_at: datetime()}]->(lp2)
            """,
                user_uid=test_user_uid,
            )

        # Test: Build context via builder pipeline
        builder = UserContextBuilder(UserContextQueryExecutor(Neo4jQueryExecutor(neo4j_driver)))
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

    @pytest.mark.asyncio
    async def test_builder_handles_no_curriculum_data(self, neo4j_driver, clean_curriculum) -> None:
        """
        Verify builder handles user with no curriculum entities gracefully.

        Tests that queries return empty collections when no data exists.
        """
        from core.models.user.user import User
        from core.services.user.user_context_builder import UserContextBuilder

        # Setup: Create user with NO curriculum data
        test_user_uid = "user_empty_curriculum"
        async with neo4j_driver.session() as session:
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
        builder = UserContextBuilder(UserContextQueryExecutor(Neo4jQueryExecutor(neo4j_driver)))
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

    @pytest.mark.asyncio
    async def test_builder_integrates_curriculum_with_activity_domains(
        self, neo4j_driver, clean_curriculum
    ) -> None:
        """
        Verify builder correctly integrates curriculum data alongside activity domains.

        Tests the complete pipeline with curriculum + tasks/habits/goals/events.
        This is the REAL production scenario.
        """
        from datetime import date, timedelta

        from core.models.user.user import User
        from core.services.user.user_context_builder import UserContextBuilder

        # Setup: Create user with curriculum + activity domain entities
        test_user_uid = "user_integrated_test"
        async with neo4j_driver.session() as session:
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
                CREATE (ku1:Entity {
                    uid: 'ku:python',
                    title: 'Python',
                    content: 'Python programming',
                    created_at: datetime(),
                    updated_at: datetime()
                })
                CREATE (ku2:Entity {
                    uid: 'ku:testing',
                    title: 'Testing',
                    content: 'Testing knowledge',
                    created_at: datetime(),
                    updated_at: datetime()
                })

                // Curriculum: Learning path
                CREATE (lp:Entity {
                    uid: 'lp:python_mastery',
                    title: 'Python Mastery',
                    description: 'Complete Python path',
                    entity_type: 'learning_path',
                    created_at: datetime(),
                    updated_at: datetime()
                })

                // Activity: Task
                CREATE (t:Task {
                    uid: 'task:build_api',
                    title: 'Build API',
                    user_uid: $user_uid,
                    status: 'active',
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

                // Add :LearningPath secondary label for CONSOLIDATED_QUERY compatibility
                SET lp:LearningPath

                // Relationships: Curriculum
                CREATE (u)-[:MASTERED {mastery_score: 0.8}]->(ku1)
                CREATE (u)-[:MASTERED {mastery_score: 0.6}]->(ku2)
                CREATE (u)-[:ENROLLED_IN]->(lp)

                // Relationships: Activity domains
                CREATE (u)-[:OWNS]->(t)
                CREATE (u)-[:OWNS]->(g)

                // Cross-domain: Task applies knowledge
                CREATE (t)-[:APPLIES_KNOWLEDGE]->(ku1)
                CREATE (g)-[:REQUIRES_KNOWLEDGE]->(ku2)
            """,
                user_uid=test_user_uid,
                due_date=(date.today() + timedelta(days=3)).isoformat(),
            )

        # Test: Build context with COMPLETE domain integration
        builder = UserContextBuilder(UserContextQueryExecutor(Neo4jQueryExecutor(neo4j_driver)))
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


# ============================================================================
# PREREQUISITE CHAIN (distance-annotated, min-distance deduped)
# ============================================================================


class TestPrerequisiteChainWithDistance:
    """Real-graph coverage for the distance-carrying prerequisite chain.

    The mock-based route tests can't exercise the Cypher itself: multi-hop
    distance, the REQUIRES_STEP|REQUIRES_KNOWLEDGE multi-type pattern, and the
    ``min(length(path))`` diamond dedup that makes the totals honest. This does.
    """

    @pytest.mark.asyncio
    async def test_diamond_dedup_and_min_distance(
        self, ps_backend, neo4j_driver, clean_curriculum
    ) -> None:
        """A node reachable by several paths appears once, at its nearest distance."""
        # Diamond with a shortcut:
        #   A -REQUIRES_STEP->      B
        #   A -REQUIRES_KNOWLEDGE-> C
        #   B -REQUIRES_KNOWLEDGE-> D   (D via B = distance 2)
        #   C -REQUIRES_KNOWLEDGE-> D   (D via C = distance 2)
        #   A -REQUIRES_KNOWLEDGE-> D   (D direct  = distance 1)  ← min wins
        steps = {
            "A": "ps:chain_a",
            "B": "ps:chain_b",
            "C": "ps:chain_c",
            "D": "ps:chain_d",
        }
        for label, uid in steps.items():
            create = await ps_backend.create(
                PathStep(uid=uid, title=f"Step {label}", intent=f"intent {label}")
            )
            assert create.is_ok, f"Setup failed: could not create {uid}"

        step_rel = RelationshipName.REQUIRES_STEP.value
        know_rel = RelationshipName.REQUIRES_KNOWLEDGE.value
        async with neo4j_driver.session() as session:
            await session.run(
                f"""
                MATCH (a:Entity {{uid:$a}}), (b:Entity {{uid:$b}}),
                      (c:Entity {{uid:$c}}), (d:Entity {{uid:$d}})
                CREATE (a)-[:{step_rel}]->(b)
                CREATE (a)-[:{know_rel}]->(c)
                CREATE (b)-[:{know_rel}]->(d)
                CREATE (c)-[:{know_rel}]->(d)
                CREATE (a)-[:{know_rel}]->(d)
                """,
                {"a": steps["A"], "b": steps["B"], "c": steps["C"], "d": steps["D"]},
            )

        result = await ps_backend.prerequisite_chain_with_distance(
            uid=steps["A"],
            relationship_types=[step_rel, know_rel],
            depth=3,
        )

        assert result.is_ok, result.error if result.is_error else "unexpected"
        by_uid = {step.uid: distance for step, distance in result.value}

        # Exactly three DISTINCT prerequisites — D is not double-counted despite
        # three inbound paths (proves the min(length(path)) dedup).
        assert len(result.value) == 3
        assert set(by_uid) == {steps["B"], steps["C"], steps["D"]}
        # REQUIRES_STEP is traversed alongside REQUIRES_KNOWLEDGE (B reached via step edge).
        assert by_uid[steps["B"]] == 1
        assert by_uid[steps["C"]] == 1
        # D's nearest path (direct, distance 1) wins over the via-B/C paths (distance 2).
        assert by_uid[steps["D"]] == 1

    @pytest.mark.asyncio
    async def test_depth_bounds_the_chain(self, ps_backend, neo4j_driver, clean_curriculum) -> None:
        """depth=1 yields only immediate prerequisites; deeper nodes are excluded."""
        chain = ["ps:linear_a", "ps:linear_b", "ps:linear_c"]
        for i, uid in enumerate(chain):
            create = await ps_backend.create(PathStep(uid=uid, title=f"Linear {i}"))
            assert create.is_ok

        know_rel = RelationshipName.REQUIRES_KNOWLEDGE.value
        async with neo4j_driver.session() as session:
            await session.run(
                f"""
                MATCH (a:Entity {{uid:$a}}), (b:Entity {{uid:$b}}), (c:Entity {{uid:$c}})
                CREATE (a)-[:{know_rel}]->(b)
                CREATE (b)-[:{know_rel}]->(c)
                """,
                {"a": chain[0], "b": chain[1], "c": chain[2]},
            )

        shallow = await ps_backend.prerequisite_chain_with_distance(
            uid=chain[0], relationship_types=[know_rel], depth=1
        )
        deep = await ps_backend.prerequisite_chain_with_distance(
            uid=chain[0], relationship_types=[know_rel], depth=3
        )

        assert shallow.is_ok and deep.is_ok
        assert {s.uid for s, _ in shallow.value} == {chain[1]}
        assert {s.uid for s, _ in deep.value} == {chain[1], chain[2]}
