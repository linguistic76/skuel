"""
Integration Test: Choices Core Operations
==========================================

Tests basic CRUD operations and core functionality for the Choices domain.

This test suite verifies that:
1. Choices can be created, retrieved, and listed
2. Choice options can be added and managed
3. Choice business logic works correctly

Test Coverage:
--------------
- ChoicesCoreService.create()
- ChoicesCoreService.get()
- ChoicesCoreService.backend.find_by()
- Choice option scoring logic
"""

import pytest
import pytest_asyncio

from adapters.infrastructure.event_bus import InMemoryEventBus
from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.models.enums import Domain, Priority
from core.models.enums.ku_enums import ChoiceType, EntityStatus
from core.models.choice.choice import Choice
from core.models.choice.choice_option import ChoiceOption
from core.services.choices.choices_core_service import ChoicesCoreService


@pytest.mark.asyncio
class TestChoicesCoreOperations:
    """Integration tests for Choices core CRUD operations."""

    @pytest_asyncio.fixture
    async def event_bus(self):
        """Create event bus with history capture."""
        return InMemoryEventBus(capture_history=True)

    @pytest_asyncio.fixture
    async def choices_backend(self, neo4j_driver, clean_neo4j):
        """Create choices backend with clean database."""
        return UniversalNeo4jBackend[Choice](
            neo4j_driver, "Entity", Choice, default_filters={"ku_type": "choice"}
        )

    @pytest_asyncio.fixture
    async def choices_service(self, choices_backend, event_bus):
        """Create ChoicesCoreService with event bus."""
        return ChoicesCoreService(backend=choices_backend, event_bus=event_bus)

    @pytest_asyncio.fixture
    async def test_user_uid(self):
        """Standard test user UID."""
        return "user.test_choices_core"

    @pytest_asyncio.fixture
    async def sample_options(self):
        """Create sample choice options."""
        return (
            ChoiceOption(
                uid="option.python",
                title="Learn Python",
                description="Focus on Python for career growth",
                feasibility_score=0.8,
                risk_level=0.2,
                potential_impact=0.9,
                resource_requirement=0.6,
            ),
            ChoiceOption(
                uid="option.javascript",
                title="Learn JavaScript",
                description="Focus on JavaScript for web development",
                feasibility_score=0.7,
                risk_level=0.3,
                potential_impact=0.8,
                resource_requirement=0.5,
            ),
        )

    async def test_create_choice(self, choices_service, test_user_uid, sample_options):
        """Test creating a new choice."""
        # Arrange
        choice = Choice(
            uid="choice.tech_stack",
            title="Choose Primary Tech Stack",
            description="Select primary programming language to focus on",
            user_uid=test_user_uid,
            choice_type=ChoiceType.MULTIPLE,
            status=EntityStatus.DRAFT,
            priority=Priority.HIGH,
            domain=Domain.TECH,
            options=sample_options,
        )

        # Act
        result = await choices_service.create(choice)

        # Assert
        assert result.is_ok
        created_choice = result.value
        assert created_choice.uid == "choice.tech_stack"
        assert created_choice.title == "Choose Primary Tech Stack"
        assert created_choice.status == EntityStatus.DRAFT
        assert len(created_choice.options) == 2

    async def test_get_choice_by_uid(self, choices_service, test_user_uid, sample_options):
        """Test retrieving a choice by UID."""
        # Arrange - Create a choice first
        choice = Choice(
            uid="choice.get_test",
            title="Test Choice",
            description="Test choice for retrieval",
            user_uid=test_user_uid,
            options=sample_options,
        )
        create_result = await choices_service.create(choice)
        assert create_result.is_ok

        # Act - Retrieve the choice
        result = await choices_service.get("choice.get_test")

        # Assert
        assert result.is_ok
        retrieved_choice = result.value
        assert retrieved_choice.uid == "choice.get_test"
        assert retrieved_choice.title == "Test Choice"

    async def test_get_nonexistent_choice(self, choices_service):
        """Test getting a choice that doesn't exist."""
        # Act
        result = await choices_service.get("choice.nonexistent")

        # Assert
        assert result.is_error
        assert "not found" in result.error.message.lower()

    async def test_list_user_choices(self, choices_service, test_user_uid, sample_options):
        """Test listing all choices for a user."""
        # Arrange - Create multiple choices
        choices = [
            Choice(
                uid=f"choice.list_test_{i}",
                title=f"Choice {i}",
                description=f"Test choice {i}",
                user_uid=test_user_uid,
                options=sample_options,
            )
            for i in range(3)
        ]

        for choice in choices:
            result = await choices_service.create(choice)
            assert result.is_ok

        # Act - List choices
        result = await choices_service.backend.find_by(user_uid=test_user_uid)

        # Assert
        assert result.is_ok
        user_choices = result.value
        assert len(user_choices) >= 3

    async def test_get_choices_by_status(self, choices_service, test_user_uid, sample_options):
        """Test filtering choices by status."""
        # Arrange - Create choices with different statuses
        pending_choice = Choice(
            uid="choice.pending",
            title="Pending Choice",
            description="Not yet decided",
            user_uid=test_user_uid,
            status=EntityStatus.DRAFT,
            options=sample_options,
        )
        decided_choice = Choice(
            uid="choice.decided",
            title="Decided Choice",
            description="Already decided",
            user_uid=test_user_uid,
            status=EntityStatus.ACTIVE,
            selected_option_uid="option.python",
            options=sample_options,
        )

        await choices_service.create(pending_choice)
        await choices_service.create(decided_choice)

        # Act - Query by status
        pending_result = await choices_service.backend.find_by(
            user_uid=test_user_uid, status=EntityStatus.DRAFT.value
        )
        decided_result = await choices_service.backend.find_by(
            user_uid=test_user_uid, status=EntityStatus.ACTIVE.value
        )

        # Assert
        assert pending_result.is_ok
        assert len(pending_result.value) >= 1
        assert all(c.status == EntityStatus.DRAFT for c in pending_result.value)

        assert decided_result.is_ok
        assert len(decided_result.value) >= 1
        assert all(c.status == EntityStatus.ACTIVE for c in decided_result.value)

    async def test_multiple_choices_same_user(self, choices_service, test_user_uid, sample_options):
        """Test creating multiple choices for the same user."""
        # Arrange & Act - Create 5 choices
        choices = []
        for i in range(5):
            choice = Choice(
                uid=f"choice.multi_{i}",
                title=f"Multiple Choice {i}",
                description=f"Choice number {i}",
                user_uid=test_user_uid,
                status=EntityStatus.DRAFT if i % 2 == 0 else EntityStatus.ACTIVE,
                options=sample_options,
            )
            result = await choices_service.create(choice)
            assert result.is_ok
            choices.append(result.value)

        # Assert - Verify all were created
        list_result = await choices_service.backend.find_by(user_uid=test_user_uid)
        assert list_result.is_ok
        assert len(list_result.value) >= 5

    async def test_choice_priority_levels(self, choices_service, test_user_uid, sample_options):
        """Test creating choices with different priority levels."""
        # Arrange & Act - Create choices with different priorities
        priorities = [Priority.LOW, Priority.MEDIUM, Priority.HIGH, Priority.CRITICAL]
        for priority in priorities:
            choice = Choice(
                uid=f"choice.priority_{priority.value}",
                title=f"{priority.value.capitalize()} Priority Choice",
                description=f"Choice with {priority.value} priority",
                user_uid=test_user_uid,
                priority=priority,
                options=sample_options,
            )
            result = await choices_service.create(choice)
            assert result.is_ok
            assert result.value.priority == priority

    async def test_choice_domain_assignment(self, choices_service, test_user_uid, sample_options):
        """Test assigning choices to different domains."""
        # Arrange & Act - Create choices in different domains
        domains = [Domain.TECH, Domain.PERSONAL, Domain.BUSINESS, Domain.HEALTH]
        for domain in domains:
            choice = Choice(
                uid=f"choice.domain_{domain.value}",
                title=f"{domain.value.capitalize()} Choice",
                description=f"Choice in {domain.value} domain",
                user_uid=test_user_uid,
                domain=domain,
                options=sample_options,
            )
            result = await choices_service.create(choice)
            assert result.is_ok
            assert result.value.domain == domain

    async def test_choice_with_decision_criteria(
        self, choices_service, test_user_uid, sample_options
    ):
        """Test creating a choice with decision criteria."""
        # Arrange
        choice = Choice(
            uid="choice.with_criteria",
            title="Choice with Criteria",
            description="Choice that has decision criteria",
            user_uid=test_user_uid,
            decision_criteria=("career growth", "work-life balance", "learning opportunity"),
            constraints=("must be remote", "salary > 100k"),
            stakeholders=("family", "current employer"),
            options=sample_options,
        )

        # Act
        result = await choices_service.create(choice)

        # Assert
        assert result.is_ok
        created_choice = result.value
        assert len(created_choice.decision_criteria) == 3
        assert len(created_choice.constraints) == 2
        assert len(created_choice.stakeholders) == 2

    async def test_choice_inspiration_fields(self, choices_service, test_user_uid, sample_options):
        """Test creating a choice with inspiration/possibility fields."""
        # Arrange
        choice = Choice(
            uid="choice.career_pivot",
            title="Career Pivot Decision",
            description="Becoming a lead software architect in 5 years",
            user_uid=test_user_uid,
            inspiration_type="career_path",
            expands_possibilities=True,
            options=sample_options,
        )

        # Act
        result = await choices_service.create(choice)

        # Assert
        assert result.is_ok
        created_choice = result.value
        assert created_choice.inspiration_type == "career_path"
        assert created_choice.expands_possibilities is True
