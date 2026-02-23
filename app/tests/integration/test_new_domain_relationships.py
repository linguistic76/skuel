"""
Integration Tests for New Domain Relationship Helpers
======================================================

Tests for:
- ChoiceRelationships
- PrincipleRelationships
- LpRelationships
- KuRelationships

These tests verify that the Domain Relationships Pattern implementation
works correctly with real Neo4j data.

Test Coverage:
- Parallel fetching (asyncio.gather)
- Empty relationships (empty())
- Helper methods (has_*, is_*, total_count, etc.)
- Cross-domain relationships
- Semantic context (KU only)
"""

import asyncio
from datetime import date

import pytest

from core.models.ku.ku_relationships import KuRelationships
from core.models.ku.ku_request import KuChoiceCreateRequest
from core.models.ku.lp_relationships import LpRelationships
from core.models.principle.principle_relationships import PrincipleRelationships
from core.services.choices.choice_relationships import ChoiceRelationships

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
        choice_request = KuChoiceCreateRequest(
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
        assert not rels.has_related_principles()
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
        assert rels.has_related_principles()
        assert rels.integration_score() > 0.0
        assert rels.total_influence_count() == 3  # 2 goals + 1 habit

    @pytest.mark.asyncio
    async def test_principle_relationships_fetch(self, services):
        """Test fetch() method with real services."""
        from core.models.enums.ku_enums import PrincipleCategory

        # Create a test principle using core service directly
        principle_result = await services.principles.core.create_principle(
            label="Test Principle",
            description="Testing relationship fetching",
            category=PrincipleCategory.PERSONAL,
            why_matters="For testing relationships",
            user_uid="test_user",
        )
        assert principle_result.is_ok, f"Failed to create principle: {principle_result.error}"
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
# LEARNING PATH RELATIONSHIPS TESTS
# ============================================================================


class TestLpRelationships:
    """Test LpRelationships helper class."""

    def test_empty_lp_relationships(self):
        """Test empty() classmethod creates empty relationships."""
        rels = LpRelationships.empty()

        assert rels.prerequisite_uids == []
        assert rels.milestone_event_uids == []
        assert rels.aligned_goal_uids == []
        assert rels.embodied_principle_uids == []
        assert rels.step_uids == []

    def test_lp_relationships_helper_methods(self):
        """Test helper methods with empty relationships."""
        rels = LpRelationships.empty()

        assert not rels.has_prerequisites()
        assert not rels.has_milestones()
        assert not rels.is_goal_aligned()
        assert not rels.embodies_principles()
        assert not rels.has_steps()
        assert not rels.is_complete_path()
        assert rels.motivational_score() == 0.0

    def test_lp_relationships_with_data(self):
        """Test helper methods with populated relationships."""
        rels = LpRelationships(
            prerequisite_uids=["ku.1"],
            milestone_event_uids=["event.1"],
            aligned_goal_uids=["goal.1", "goal.2"],
            embodied_principle_uids=["principle.1"],
            step_uids=["ls.1", "ls.2", "ls.3"],
        )

        assert rels.has_prerequisites()
        assert rels.has_milestones()
        assert rels.is_goal_aligned()
        assert rels.embodies_principles()
        assert rels.has_steps()
        assert rels.is_complete_path()
        assert rels.motivational_score() > 0.0
        assert rels.total_step_count() == 3
        assert rels.prerequisite_count() == 1

    @pytest.mark.asyncio
    async def test_lp_relationships_fetch(self, services):
        """Test fetch() method with real services."""
        from core.models.enums import Domain

        # Create a test learning path using core service
        lp_result = await services.lp.core.create_path(
            user_uid="test_user",
            title="Test Learning Path",
            description="Testing relationship fetching",
            steps=[],  # Empty steps for testing
            domain=Domain.LEARNING,
        )
        assert lp_result.is_ok, f"Failed to create learning path: {lp_result.error}"
        lp = lp_result.value

        # Fetch relationships
        rels = await LpRelationships.fetch(lp.uid, services.lp.relationships)

        # Verify structure
        assert isinstance(rels, LpRelationships)
        assert isinstance(rels.prerequisite_uids, list)
        assert isinstance(rels.milestone_event_uids, list)
        assert isinstance(rels.aligned_goal_uids, list)
        assert isinstance(rels.embodied_principle_uids, list)
        assert isinstance(rels.step_uids, list)


# ============================================================================
# KNOWLEDGE UNIT RELATIONSHIPS TESTS (HYBRID PATTERN)
# ============================================================================


class TestKuRelationships:
    """Test KuRelationships helper class (hybrid pattern)."""

    def test_empty_ku_relationships(self):
        """Test empty() classmethod creates empty relationships."""
        rels = KuRelationships.empty()

        # Curriculum relationships
        assert rels.prerequisite_uids == []
        assert rels.enables_uids == []
        assert rels.related_uids == []
        assert rels.broader_uids == []
        assert rels.narrower_uids == []

        # Cross-domain relationships
        assert rels.part_of_path_uids == []
        assert rels.applied_in_task_uids == []
        assert rels.practiced_in_event_uids == []
        assert rels.reinforced_by_habit_uids == []

        # Semantic context
        assert rels.semantic_context is None

    def test_ku_relationships_simple_helper_methods(self):
        """Test simple helper methods with empty relationships."""
        rels = KuRelationships.empty()

        assert not rels.has_prerequisites()
        assert not rels.enables_other_knowledge()
        assert not rels.has_related_knowledge()
        assert not rels.has_curriculum_relationships()
        assert not rels.is_applied_in_practice()
        assert not rels.is_part_of_curriculum()
        assert not rels.is_foundational()
        assert not rels.is_advanced()

        assert rels.total_curriculum_connections() == 0
        assert rels.total_application_count() == 0
        assert rels.prerequisite_count() == 0
        assert rels.enables_count() == 0

    def test_ku_relationships_with_curriculum_data(self):
        """Test helper methods with populated curriculum relationships."""
        rels = KuRelationships(
            prerequisite_uids=["ku.1", "ku.2"],
            enables_uids=["ku.3", "ku.4"],
            related_uids=["ku.5"],
            broader_uids=["ku.6"],
            narrower_uids=["ku.7", "ku.8"],
        )

        assert rels.has_prerequisites()
        assert rels.enables_other_knowledge()
        assert rels.has_related_knowledge()
        assert rels.has_curriculum_relationships()
        assert not rels.is_foundational()  # Has prerequisites
        assert rels.is_advanced()  # 2+ prerequisites

        assert rels.total_curriculum_connections() == 8
        assert rels.prerequisite_count() == 2
        assert rels.enables_count() == 2

    def test_ku_relationships_with_application_data(self):
        """Test helper methods with populated cross-domain relationships."""
        rels = KuRelationships(
            part_of_path_uids=["lp.1"],
            applied_in_task_uids=["task.1", "task.2"],
            practiced_in_event_uids=["event.1"],
            reinforced_by_habit_uids=["habit.1"],
        )

        assert rels.is_applied_in_practice()
        assert rels.is_part_of_curriculum()
        assert rels.total_application_count() == 4

    def test_ku_relationships_foundational_knowledge(self):
        """Test is_foundational() for knowledge with no prerequisites."""
        rels = KuRelationships(
            prerequisite_uids=[],  # No prerequisites
            enables_uids=["ku.1", "ku.2"],  # Enables others
        )

        assert rels.is_foundational()
        assert not rels.is_advanced()

    def test_ku_relationships_semantic_helpers(self):
        """Test semantic helper methods."""
        rels = KuRelationships(
            prerequisite_uids=["ku.1", "ku.2", "ku.3"],
            semantic_context={
                "relationships": [
                    {
                        "type": "REQUIRES_KNOWLEDGE",
                        "target_uid": "ku.1",
                        "confidence": 0.9,
                    },
                    {
                        "type": "REQUIRES_KNOWLEDGE",
                        "target_uid": "ku.2",
                        "confidence": 0.85,
                    },
                    {
                        "type": "REQUIRES_KNOWLEDGE",
                        "target_uid": "ku.3",
                        "confidence": 0.6,  # Low confidence
                    },
                ]
            },
        )

        # High confidence filtering
        high_conf = rels.get_high_confidence_prerequisites(min_confidence=0.8)
        assert len(high_conf) == 2  # Only ku.1 and ku.2

        # Strong prerequisites check
        assert rels.has_strong_prerequisites(min_count=2, min_confidence=0.8)
        assert not rels.has_strong_prerequisites(min_count=3, min_confidence=0.8)

    def test_ku_relationships_semantic_helpers_without_context(self):
        """Test semantic helpers fallback when no semantic_context."""
        rels = KuRelationships(prerequisite_uids=["ku.1", "ku.2"])

        # Should fallback to all prerequisites
        high_conf = rels.get_high_confidence_prerequisites()
        assert high_conf == ["ku.1", "ku.2"]

    @pytest.mark.asyncio
    async def test_ku_relationships_fetch_basic(self, services):
        """Test fetch() method with real services (basic mode)."""
        # Create a test knowledge unit using core service
        ku_result = await services.ku.core.create(
            title="Test KU for Relationships",
            body="Testing relationship fetching",
            summary="Test KU",
            user_uid="test_user",
            domain="TECH",  # Required for CurriculumDTO
        )
        assert ku_result.is_ok, f"Failed to create KU: {ku_result.error}"
        ku = ku_result.value

        # Fetch relationships (basic mode - no semantic context)
        rels = await KuRelationships.fetch(ku.uid, services.ku.graph)

        # Verify structure
        assert isinstance(rels, KuRelationships)
        assert isinstance(rels.prerequisite_uids, list)
        assert isinstance(rels.enables_uids, list)
        assert isinstance(rels.related_uids, list)
        assert isinstance(rels.broader_uids, list)
        assert isinstance(rels.narrower_uids, list)
        assert isinstance(rels.part_of_path_uids, list)
        assert isinstance(rels.applied_in_task_uids, list)
        assert isinstance(rels.practiced_in_event_uids, list)
        assert isinstance(rels.reinforced_by_habit_uids, list)
        assert rels.semantic_context is None  # Not fetched in basic mode

    @pytest.mark.asyncio
    async def test_ku_relationships_fetch_with_semantic_context(self, services):
        """Test fetch() method with semantic context enabled."""
        # Create a test knowledge unit using core service
        ku_result = await services.ku.core.create(
            title="Test KU with Semantic Context",
            body="Testing semantic relationship fetching",
            summary="Test KU with semantics",
            user_uid="test_user",
            domain="TECH",  # Required for CurriculumDTO
        )
        assert ku_result.is_ok, f"Failed to create KU: {ku_result.error}"
        ku = ku_result.value

        # Fetch relationships with semantic context
        rels = await KuRelationships.fetch(
            ku.uid,
            services.ku.graph,
            semantic_service=services.ku.semantic,
            include_semantic_context=True,
        )

        # Verify structure
        assert isinstance(rels, KuRelationships)
        # semantic_context may be None or dict depending on KU relationships
        assert rels.semantic_context is None or isinstance(rels.semantic_context, dict)


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
            choice_request = KuChoiceCreateRequest(
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
        from core.models.enums.ku_enums import PrincipleCategory

        # Create test entities in different domains using core services
        choice_request = KuChoiceCreateRequest(
            title="Test Choice",
            description="Test choice for relationship fetching",
            decision_date=date.today(),
            user_uid="test_user",
        )
        choice_result = await services.choices.core.create_choice(choice_request, "test_user")

        principle_result = await services.principles.core.create_principle(
            label="Test Principle",
            description="Test",
            category=PrincipleCategory.PERSONAL,
            why_matters="Testing",
            user_uid="test_user",
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

    def test_lp_relationships_immutable(self):
        """Test LpRelationships is immutable."""
        rels = LpRelationships.empty()

        with pytest.raises(Exception):
            rels.step_uids = ["ls.1"]

    def test_ku_relationships_immutable(self):
        """Test KuRelationships is immutable."""
        rels = KuRelationships.empty()

        with pytest.raises(Exception):
            rels.prerequisite_uids = ["ku.1"]
