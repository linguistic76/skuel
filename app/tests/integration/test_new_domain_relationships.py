"""
Integration Tests for New Domain Relationship Helpers
======================================================

Tests for:
- ChoiceRelationships
- PrincipleRelationships

These tests verify that the Domain Relationships Pattern implementation
works correctly with real Neo4j data.

Test Coverage:
- Parallel fetching (asyncio.gather)
- Empty relationships (empty())
- Helper methods (has_*, is_*, total_count, etc.)
- Cross-domain relationships
"""

import asyncio
from datetime import date

import pytest

from core.models.choice.choice_request import ChoiceCreateRequest
from core.models.principle.principle_request import PrincipleCreateRequest
from core.services.choices.choice_relationships import ChoiceRelationships
from core.services.principles.principle_relationships import PrincipleRelationships

# ============================================================================
# CHOICE RELATIONSHIPS TESTS
# ============================================================================


class TestChoiceRelationships:
    """Test ChoiceRelationships helper class."""

    def test_empty_choice_relationships(self):
        """Test empty() classmethod creates empty relationships."""
        rels = ChoiceRelationships.empty()

        assert rels.informed_by_knowledge_uids == []
        assert rels.opens_learning_path_uids == []
        assert rels.required_knowledge_uids == []
        assert rels.aligned_principle_uids == []

    def test_choice_relationships_helper_methods(self):
        """Test helper methods with empty relationships."""
        rels = ChoiceRelationships.empty()

        assert not rels.has_any_knowledge()
        assert not rels.is_principle_aligned()
        assert not rels.is_informed_decision()
        assert not rels.opens_learning()
        assert rels.total_knowledge_count() == 0
        assert len(rels.get_all_knowledge_uids()) == 0

    def test_choice_relationships_with_data(self):
        """Test helper methods with populated relationships."""
        rels = ChoiceRelationships(
            informed_by_knowledge_uids=["ku.1", "ku.2"],
            opens_learning_path_uids=["lp.1"],
            required_knowledge_uids=["ku.3"],
            aligned_principle_uids=["principle.1"],
        )

        assert rels.has_any_knowledge()
        assert rels.is_principle_aligned()
        assert rels.is_informed_decision()
        assert rels.opens_learning()
        assert rels.total_knowledge_count() == 4
        assert len(rels.get_all_knowledge_uids()) == 3  # 3 unique KUs

    @pytest.mark.asyncio
    async def test_choice_relationships_fetch(self, services):
        """Test fetch() method with real services."""
        # Create a test choice
        choice_request = ChoiceCreateRequest(
            title="Test Choice for Relationships",
            description="Testing relationship fetching",
            decision_date=date.today(),
            user_uid="test_user",
        )

        # Call core service directly with explicit user_uid (facade has a bug)
        choice_result = await services.choices.core.create_choice(choice_request, "test_user")
        assert choice_result.is_ok, f"Failed to create choice: {choice_result.error}"
        choice = choice_result.value

        # Fetch relationships
        rels = await ChoiceRelationships.fetch(choice.uid, services.choices.relationships)

        # Verify structure (should be empty for new choice)
        assert isinstance(rels, ChoiceRelationships)
        assert isinstance(rels.informed_by_knowledge_uids, list)
        assert isinstance(rels.opens_learning_path_uids, list)
        assert isinstance(rels.required_knowledge_uids, list)
        assert isinstance(rels.aligned_principle_uids, list)


# ============================================================================
# PRINCIPLE RELATIONSHIPS TESTS
# ============================================================================


class TestPrincipleRelationships:
    """Test PrincipleRelationships helper class."""

    def test_empty_principle_relationships(self):
        """Test empty() classmethod creates empty relationships."""
        rels = PrincipleRelationships.empty()

        assert rels.grounded_knowledge_uids == []
        assert rels.guided_goal_uids == []
        assert rels.inspired_habit_uids == []
        assert rels.related_principle_uids == []

    def test_principle_relationships_helper_methods(self):
        """Test helper methods with empty relationships."""
        rels = PrincipleRelationships.empty()

        assert not rels.has_any_knowledge()
        assert not rels.guides_goals()
        assert not rels.inspires_habits()
        assert not rels.is_integrated()
        assert rels.integration_score() == 0.0
        assert rels.total_influence_count() == 0

    def test_principle_relationships_with_data(self):
        """Test helper methods with populated relationships."""
        rels = PrincipleRelationships(
            grounded_knowledge_uids=["ku.1"],
            guided_goal_uids=["goal.1", "goal.2"],
            inspired_habit_uids=["habit.1"],
            related_principle_uids=["principle.2"],
        )

        assert rels.has_any_knowledge()
        assert rels.guides_goals()
        assert rels.inspires_habits()
        assert rels.is_integrated()
        assert rels.integration_score() > 0.0
        assert rels.total_influence_count() == 3  # 2 goals + 1 habit

    @pytest.mark.asyncio
    async def test_principle_relationships_fetch(self, services):
        """Test fetch() method with real services."""
        from core.models.enums.principle_enums import PrincipleCategory

        # Create a test principle using core service directly
        request = PrincipleCreateRequest(
            title="Test Principle",
            statement="Testing relationship fetching",
            description="Testing relationship fetching",
            principle_category=PrincipleCategory.PERSONAL,
            why_important="For testing relationships",
        )
        principle_result = await services.principles.core.create_principle(
            request, user_uid="test_user"
        )
        assert principle_result.is_ok, (
            f"Failed to create principle: {principle_result.expect_error()}"
        )
        principle = principle_result.value

        # Fetch relationships
        rels = await PrincipleRelationships.fetch(principle.uid, services.principles.relationships)

        # Verify structure
        assert isinstance(rels, PrincipleRelationships)
        assert isinstance(rels.grounded_knowledge_uids, list)
        assert isinstance(rels.guided_goal_uids, list)
        assert isinstance(rels.inspired_habit_uids, list)
        assert isinstance(rels.related_principle_uids, list)


# ============================================================================
# PARALLEL FETCHING TESTS
# ============================================================================


class TestParallelFetching:
    """Test parallel relationship fetching performance."""

    @pytest.mark.asyncio
    async def test_parallel_fetch_multiple_choices(self, services):
        """Test fetching relationships for multiple choices in parallel."""
        # Create multiple test choices
        choices = []
        for i in range(3):
            choice_request = ChoiceCreateRequest(
                title=f"Test Choice {i}",
                description=f"Testing parallel fetch {i}",
                decision_date=date.today(),
                user_uid="test_user",
            )
            # Call core service directly with explicit user_uid (facade has a bug)
            result = await services.choices.core.create_choice(choice_request, "test_user")
            assert result.is_ok
            choices.append(result.value)

        # Fetch all relationships in parallel
        all_rels = await asyncio.gather(
            *[
                ChoiceRelationships.fetch(choice.uid, services.choices.relationships)
                for choice in choices
            ]
        )

        # Verify we got 3 results
        assert len(all_rels) == 3
        assert all(isinstance(r, ChoiceRelationships) for r in all_rels)

    @pytest.mark.asyncio
    async def test_parallel_fetch_multiple_domains(self, services):
        """Test fetching relationships across different domains in parallel."""
        from core.models.enums.principle_enums import PrincipleCategory

        # Create test entities in different domains using core services
        choice_request = ChoiceCreateRequest(
            title="Test Choice",
            description="Test choice for relationship fetching",
            decision_date=date.today(),
            user_uid="test_user",
        )
        choice_result = await services.choices.core.create_choice(choice_request, "test_user")

        principle_request = PrincipleCreateRequest(
            title="Test Principle",
            statement="Test",
            description="Test",
            principle_category=PrincipleCategory.PERSONAL,
            why_important="Testing",
        )
        principle_result = await services.principles.core.create_principle(
            principle_request, user_uid="test_user"
        )

        assert choice_result.is_ok
        assert principle_result.is_ok

        choice = choice_result.value
        principle = principle_result.value

        # Fetch relationships for both domains in parallel
        choice_rels, principle_rels = await asyncio.gather(
            ChoiceRelationships.fetch(choice.uid, services.choices.relationships),
            PrincipleRelationships.fetch(principle.uid, services.principles.relationships),
        )

        # Verify both fetched successfully
        assert isinstance(choice_rels, ChoiceRelationships)
        assert isinstance(principle_rels, PrincipleRelationships)


# ============================================================================
# FROZEN DATACLASS IMMUTABILITY TESTS
# ============================================================================


class TestImmutability:
    """Test that all relationship classes are immutable (frozen)."""

    def test_choice_relationships_immutable(self):
        """Test ChoiceRelationships is immutable."""
        rels = ChoiceRelationships.empty()

        with pytest.raises(Exception):  # FrozenInstanceError
            rels.informed_by_knowledge_uids = ["ku.1"]

    def test_principle_relationships_immutable(self):
        """Test PrincipleRelationships is immutable."""
        rels = PrincipleRelationships.empty()

        with pytest.raises(Exception):
            rels.guided_goal_uids = ["goal.1"]
