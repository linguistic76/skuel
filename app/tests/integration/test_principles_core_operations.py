"""
Integration Test: Principles Core Operations
============================================

Tests basic CRUD operations and core functionality for the Principles domain.

This test suite verifies that:
1. Principles can be created, retrieved, and listed
2. Principles can be filtered by category, strength, and source
3. Validation rules are enforced
4. Business logic works correctly

Test Coverage:
--------------
- PrinciplesCoreService.create()
- PrinciplesCoreService.get()
- PrinciplesCoreService.backend.find_by()
- Principle validation rules
- Principle enum classifications
"""

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums.ku_enums import (
    AlignmentLevel,
    PrincipleCategory,
    PrincipleSource,
    PrincipleStrength,
)
from core.models.principle.principle import Principle
from core.services.principles.principles_core_service import PrinciplesCoreService


@pytest.mark.asyncio
class TestPrinciplesCoreOperations:
    """Integration tests for Principles core CRUD operations."""

    @pytest_asyncio.fixture
    async def event_bus(self):
        """Create event bus with history capture."""
        return InMemoryEventBus(capture_history=True)

    @pytest_asyncio.fixture
    async def principles_backend(self, neo4j_driver, clean_neo4j):
        """Create principles backend with clean database."""
        return UniversalNeo4jBackend[Principle](neo4j_driver, "Ku", Principle)

    @pytest_asyncio.fixture
    async def principles_service(self, principles_backend, event_bus):
        """Create PrinciplesCoreService with event bus."""
        return PrinciplesCoreService(backend=principles_backend, event_bus=event_bus)

    @pytest_asyncio.fixture
    async def test_user_uid(self):
        """Standard test user UID."""
        return "user.test_principles_core"

    # ==========================================================================
    # CRUD OPERATIONS TESTS (5 tests)
    # ==========================================================================

    async def test_create_principle(self, principles_service, test_user_uid):
        """Test creating a new principle."""
        # Arrange
        principle = Principle(
            uid="principle.continuous_learning",
            user_uid=test_user_uid,
            title="Continuous Learning",
            statement="I commit to learning something new every day",
            description="Lifelong learning is essential for personal growth and adaptability",
            principle_category=PrincipleCategory.INTELLECTUAL,
            principle_source=PrincipleSource.PERSONAL,
            strength=PrincipleStrength.CORE,
        )

        # Act
        result = await principles_service.create(principle)

        # Assert
        assert result.is_ok
        created = result.value
        assert created.uid == "principle.continuous_learning"
        assert created.title == "Continuous Learning"
        assert created.principle_category == PrincipleCategory.INTELLECTUAL
        assert created.strength == PrincipleStrength.CORE
        assert created.principle_source == PrincipleSource.PERSONAL

    async def test_get_principle_by_uid(self, principles_service, test_user_uid):
        """Test retrieving a principle by UID."""
        # Arrange - Create a principle first
        principle = Principle(
            uid="principle.get_test",
            user_uid=test_user_uid,
            title="Test Principle",
            statement="This is a test principle statement for retrieval",
            principle_category=PrincipleCategory.PERSONAL,
        )
        create_result = await principles_service.create(principle)
        assert create_result.is_ok

        # Act - Retrieve the principle
        result = await principles_service.get("principle.get_test")

        # Assert
        assert result.is_ok
        retrieved = result.value
        assert retrieved.uid == "principle.get_test"
        assert retrieved.title == "Test Principle"

    async def test_get_nonexistent_principle(self, principles_service):
        """Test getting a principle that doesn't exist."""
        # Act
        result = await principles_service.get("principle.nonexistent")

        # Assert
        assert result.is_error
        assert "not found" in result.error.message.lower()

    async def test_list_user_principles(self, principles_service, test_user_uid):
        """Test listing all principles for a user."""
        # Arrange - Create multiple principles
        principles = [
            Principle(
                uid=f"principle.list_test_{i}",
                user_uid=test_user_uid,
                title=f"Principle {i}",
                statement=f"This is test principle number {i} for comprehensive testing",
                principle_category=PrincipleCategory.PERSONAL,
            )
            for i in range(3)
        ]

        for principle in principles:
            result = await principles_service.create(principle)
            assert result.is_ok

        # Act - List principles
        result = await principles_service.backend.find_by(user_uid=test_user_uid)

        # Assert
        assert result.is_ok
        user_principles = result.value
        assert len(user_principles) >= 3

    async def test_multiple_principles_same_user(self, principles_service, test_user_uid):
        """Test creating multiple principles for the same user."""
        # Arrange & Act - Create 5 principles
        for i in range(5):
            principle = Principle(
                uid=f"principle.multi_{i}",
                user_uid=test_user_uid,
                title=f"Multiple Principle {i}",
                statement=f"This is principle number {i} for testing multiple entries",
                principle_category=PrincipleCategory.PERSONAL,
            )
            result = await principles_service.create(principle)
            assert result.is_ok

        # Assert - Verify all were created
        list_result = await principles_service.backend.find_by(user_uid=test_user_uid)
        assert list_result.is_ok
        assert len(list_result.value) >= 5

    # ==========================================================================
    # FILTERING TESTS (3 tests)
    # ==========================================================================

    async def test_filter_by_category(self, principles_service, test_user_uid):
        """Test filtering principles by category."""
        # Arrange - Create principles in different categories
        intellectual = Principle(
            uid="principle.intellectual",
            user_uid=test_user_uid,
            title="Critical Thinking",
            statement="I question assumptions and seek evidence before forming conclusions",
            principle_category=PrincipleCategory.INTELLECTUAL,
        )
        ethical = Principle(
            uid="principle.ethical",
            user_uid=test_user_uid,
            title="Honesty",
            statement="I always speak the truth and act with integrity in all situations",
            principle_category=PrincipleCategory.ETHICAL,
        )
        personal = Principle(
            uid="principle.personal",
            user_uid=test_user_uid,
            title="Growth Mindset",
            statement="I embrace challenges as opportunities for personal development",
            principle_category=PrincipleCategory.PERSONAL,
        )

        await principles_service.create(intellectual)
        await principles_service.create(ethical)
        await principles_service.create(personal)

        # Act - Filter by category
        intellectual_result = await principles_service.backend.find_by(
            user_uid=test_user_uid, principle_category=PrincipleCategory.INTELLECTUAL.value
        )
        ethical_result = await principles_service.backend.find_by(
            user_uid=test_user_uid, principle_category=PrincipleCategory.ETHICAL.value
        )

        # Assert
        assert intellectual_result.is_ok
        assert len(intellectual_result.value) >= 1
        assert all(
            p.principle_category == PrincipleCategory.INTELLECTUAL
            for p in intellectual_result.value
        )

        assert ethical_result.is_ok
        assert len(ethical_result.value) >= 1
        assert all(p.principle_category == PrincipleCategory.ETHICAL for p in ethical_result.value)

    async def test_filter_by_strength(self, principles_service, test_user_uid):
        """Test filtering principles by strength level."""
        # Arrange - Create principles with different strengths
        core_principle = Principle(
            uid="principle.core",
            user_uid=test_user_uid,
            title="Core Value",
            statement="This is a core, non-negotiable principle that defines my identity",
            strength=PrincipleStrength.CORE,
        )
        developing_principle = Principle(
            uid="principle.developing",
            user_uid=test_user_uid,
            title="New Habit",
            statement="I am working on developing this principle in my daily life",
            strength=PrincipleStrength.DEVELOPING,
        )

        await principles_service.create(core_principle)
        await principles_service.create(developing_principle)

        # Act - Filter by strength
        core_result = await principles_service.backend.find_by(
            user_uid=test_user_uid, strength=PrincipleStrength.CORE.value
        )
        developing_result = await principles_service.backend.find_by(
            user_uid=test_user_uid, strength=PrincipleStrength.DEVELOPING.value
        )

        # Assert
        assert core_result.is_ok
        assert len(core_result.value) >= 1
        assert all(p.strength == PrincipleStrength.CORE for p in core_result.value)

        assert developing_result.is_ok
        assert len(developing_result.value) >= 1
        assert all(p.strength == PrincipleStrength.DEVELOPING for p in developing_result.value)

    async def test_filter_by_source(self, principles_service, test_user_uid):
        """Test filtering principles by source."""
        # Arrange - Create principles from different sources
        philosophical = Principle(
            uid="principle.philosophical",
            user_uid=test_user_uid,
            title="Stoic Principle",
            statement="I focus on what I can control and accept what I cannot change",
            principle_source=PrincipleSource.PHILOSOPHICAL,
            tradition="Stoicism",
        )
        personal = Principle(
            uid="principle.personal_exp",
            user_uid=test_user_uid,
            title="Learned from Experience",
            statement="I have learned through personal experience the value of persistence",
            principle_source=PrincipleSource.PERSONAL,
        )

        await principles_service.create(philosophical)
        await principles_service.create(personal)

        # Act - Filter by source
        philosophical_result = await principles_service.backend.find_by(
            user_uid=test_user_uid, principle_source=PrincipleSource.PHILOSOPHICAL.value
        )
        personal_result = await principles_service.backend.find_by(
            user_uid=test_user_uid, principle_source=PrincipleSource.PERSONAL.value
        )

        # Assert
        assert philosophical_result.is_ok
        assert len(philosophical_result.value) >= 1
        assert all(
            p.principle_source == PrincipleSource.PHILOSOPHICAL for p in philosophical_result.value
        )

        assert personal_result.is_ok
        assert len(personal_result.value) >= 1
        assert all(p.principle_source == PrincipleSource.PERSONAL for p in personal_result.value)

    # ==========================================================================
    # VALIDATION TESTS (2 tests)
    # ==========================================================================

    async def test_validation_statement_too_short(self, principles_service, test_user_uid):
        """Test that short statements are rejected."""
        # Arrange - Statement < 10 characters
        principle = Principle(
            uid="principle.invalid_short",
            user_uid=test_user_uid,
            title="Invalid",
            statement="Too short",  # Only 9 characters
            principle_category=PrincipleCategory.PERSONAL,
        )

        # Act
        result = await principles_service.create(principle)

        # Assert - Should fail validation
        assert result.is_error
        assert "statement" in result.error.message.lower() or "10" in result.error.message

    async def test_validation_description_too_short(self, principles_service, test_user_uid):
        """Test that short descriptions are rejected."""
        # Arrange - Description < 20 characters
        principle = Principle(
            uid="principle.invalid_desc",
            user_uid=test_user_uid,
            title="Invalid Description",
            statement="This is a valid statement with more than ten characters",
            description="Too short desc",  # Only 15 characters
            principle_category=PrincipleCategory.PERSONAL,
        )

        # Act
        result = await principles_service.create(principle)

        # Assert - Should fail validation
        assert result.is_error
        assert "description" in result.error.message.lower() or "20" in result.error.message

    # ==========================================================================
    # BUSINESS LOGIC TESTS (3 tests)
    # ==========================================================================

    async def test_principle_strength_levels(self, principles_service, test_user_uid):
        """Test creating principles with all strength levels."""
        # Arrange & Act - Create principles with each strength level
        strengths = [
            PrincipleStrength.CORE,
            PrincipleStrength.STRONG,
            PrincipleStrength.MODERATE,
            PrincipleStrength.DEVELOPING,
            PrincipleStrength.EXPLORING,
        ]

        for strength in strengths:
            principle = Principle(
                uid=f"principle.strength_{strength.value}",
                user_uid=test_user_uid,
                title=f"{strength.value.capitalize()} Principle",
                statement=f"This is a principle with {strength.value} strength level for testing",
                strength=strength,
            )
            result = await principles_service.create(principle)
            assert result.is_ok
            assert result.value.strength == strength

    async def test_principle_categories(self, principles_service, test_user_uid):
        """Test creating principles in all categories."""
        # Arrange & Act - Create principles in each category
        categories = [
            PrincipleCategory.SPIRITUAL,
            PrincipleCategory.ETHICAL,
            PrincipleCategory.RELATIONAL,
            PrincipleCategory.PERSONAL,
            PrincipleCategory.PROFESSIONAL,
            PrincipleCategory.INTELLECTUAL,
            PrincipleCategory.HEALTH,
            PrincipleCategory.CREATIVE,
        ]

        for category in categories:
            principle = Principle(
                uid=f"principle.cat_{category.value}",
                user_uid=test_user_uid,
                title=f"{category.value.capitalize()} Principle",
                statement=f"This is a principle in the {category.value} category for comprehensive testing",
                principle_category=category,
            )
            result = await principles_service.create(principle)
            assert result.is_ok
            assert result.value.principle_category == category

    async def test_principle_with_optional_fields(self, principles_service, test_user_uid):
        """Test creating a principle with optional philosophical context."""
        # Arrange
        principle = Principle(
            uid="principle.stoic_with_context",
            user_uid=test_user_uid,
            title="Amor Fati",
            statement="I love my fate and embrace everything that happens to me",
            description="The Stoic practice of accepting and loving one's destiny, including all challenges",
            principle_category=PrincipleCategory.SPIRITUAL,
            principle_source=PrincipleSource.PHILOSOPHICAL,
            strength=PrincipleStrength.STRONG,
            tradition="Stoicism",
            original_source="Marcus Aurelius, Meditations",
            personal_interpretation="I interpret this as finding meaning in adversity",
        )

        # Act
        result = await principles_service.create(principle)

        # Assert
        assert result.is_ok
        created = result.value
        assert created.tradition == "Stoicism"
        assert "Marcus Aurelius" in created.original_source
        assert created.personal_interpretation is not None

    # ==========================================================================
    # EDGE CASES TESTS (2 tests)
    # ==========================================================================

    async def test_principle_without_description(self, principles_service, test_user_uid):
        """Test creating a principle without a description (optional field)."""
        # Arrange
        principle = Principle(
            uid="principle.no_description",
            user_uid=test_user_uid,
            title="No Description",
            statement="This principle has no description field specified",
            description=None,  # Explicitly None
            principle_category=PrincipleCategory.PERSONAL,
        )

        # Act
        result = await principles_service.create(principle)

        # Assert
        assert result.is_ok
        created = result.value
        assert created.description is None

    async def test_principle_alignment_levels(self, principles_service, test_user_uid):
        """Test creating principles with different alignment levels."""
        # Arrange & Act - Create principles with each alignment level
        alignments = [
            AlignmentLevel.ALIGNED,
            AlignmentLevel.MOSTLY_ALIGNED,
            AlignmentLevel.PARTIAL,
            AlignmentLevel.MISALIGNED,
            AlignmentLevel.UNKNOWN,
        ]

        for alignment in alignments:
            principle = Principle(
                uid=f"principle.alignment_{alignment.value}",
                user_uid=test_user_uid,
                title=f"{alignment.value.replace('_', ' ').title()} Principle",
                statement=f"This principle has {alignment.value} alignment for testing purposes",
                current_alignment=alignment,
            )
            result = await principles_service.create(principle)
            assert result.is_ok
            assert result.value.current_alignment == alignment
