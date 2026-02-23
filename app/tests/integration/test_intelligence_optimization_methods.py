"""
Integration tests for intelligence service optimization methods using fetch().

Tests the new quick check and batch analysis methods that use
ChoiceRelationships.fetch() and PrincipleRelationships.fetch() for
improved performance.
"""

from datetime import date

import pytest

from core.models.enums.ku_enums import PrincipleCategory
from core.models.activity_requests import ChoiceCreateRequest


@pytest.mark.asyncio
class TestChoicesIntelligenceOptimization:
    """Test ChoicesIntelligenceService optimization methods."""

    async def test_quick_decision_metrics_basic(self, services):
        """Test get_quick_decision_metrics() with basic choice."""
        # Create choice
        choice_request = ChoiceCreateRequest(
            title="Test Decision",
            description="Test choice for quick metrics",
            decision_date=date.today(),
            user_uid="test_user",
        )
        choice_result = await services.choices.core.create_choice(choice_request, "test_user")
        assert choice_result.is_ok
        choice_uid = choice_result.value.uid

        # Get quick metrics
        metrics_result = await services.choices.intelligence.get_quick_decision_metrics(choice_uid)
        assert metrics_result.is_ok

        metrics = metrics_result.value

        # Verify structure
        assert "choice_uid" in metrics
        assert "relationship_counts" in metrics
        assert "quick_complexity" in metrics
        assert "stake_level" in metrics
        assert "needs_full_analysis" in metrics
        assert "is_informed" in metrics
        assert "is_principle_aligned" in metrics

        # Verify counts for empty relationships
        counts = metrics["relationship_counts"]
        assert counts["knowledge"] == 0
        assert counts["principles"] == 0
        assert counts["learning_paths"] == 0
        assert counts["required_knowledge"] == 0

        # Verify helper method results
        assert metrics["is_informed"] is False
        assert metrics["is_principle_aligned"] is False
        assert metrics["quick_complexity"] == 0.0
        assert metrics["stake_level"] == "low"

    async def test_batch_analyze_decision_complexity_basic(self, services):
        """Test batch_analyze_decision_complexity() for multiple choices."""
        # Create 3 simple choices
        choice_uids = []
        for i in range(3):
            choice_request = ChoiceCreateRequest(
                title=f"Test Choice {i}",
                description=f"Test choice {i}",
                decision_date=date.today(),
                user_uid="test_user",
            )
            choice_result = await services.choices.core.create_choice(choice_request, "test_user")
            assert choice_result.is_ok
            choice_uids.append(choice_result.value.uid)

        # Batch analyze
        batch_result = await services.choices.intelligence.batch_analyze_decision_complexity(
            choice_uids
        )
        assert batch_result.is_ok

        results = batch_result.value

        # Verify all choices analyzed
        assert len(results) == 3
        for uid in choice_uids:
            assert uid in results
            assert "complexity" in results[uid]
            assert "total_relationships" in results[uid]
            assert "is_informed" in results[uid]
            assert "is_principle_aligned" in results[uid]


@pytest.mark.asyncio
class TestPrinciplesIntelligenceOptimization:
    """Test PrinciplesIntelligenceService optimization methods."""

    async def test_quick_principle_impact_basic(self, services):
        """Test get_quick_principle_impact() with basic principle."""
        # Create principle
        principle_result = await services.principles.core.create_principle(
            label="Test Principle",
            description="Test principle for quick impact",
            category=PrincipleCategory.PERSONAL,
            why_matters="For testing",
            user_uid="test_user",
        )
        assert principle_result.is_ok
        principle_uid = principle_result.value.uid

        # Get quick impact
        impact_result = await services.principles.intelligence.get_quick_principle_impact(
            principle_uid
        )
        assert impact_result.is_ok

        impact = impact_result.value

        # Verify structure
        assert "principle_uid" in impact
        assert "relationship_counts" in impact
        assert "impact_score" in impact
        assert "adoption_level" in impact
        assert "has_foundation" in impact
        assert "guides_actions" in impact
        assert "total_action_count" in impact

        # Verify counts for empty relationships
        counts = impact["relationship_counts"]
        assert counts["grounded_knowledge"] == 0
        assert counts["guided_goals"] == 0
        assert counts["inspired_habits"] == 0
        assert counts["related_principles"] == 0

        # Verify helper method results
        assert impact["has_foundation"] is False
        assert impact["guides_actions"] is False
        assert impact["total_action_count"] == 0
        assert impact["impact_score"] == 0.0
        assert impact["adoption_level"] == "exploring"

    async def test_batch_analyze_principle_adoption_basic(self, services):
        """Test batch_analyze_principle_adoption() for multiple principles."""
        # Create 3 simple principles
        principle_uids = []
        for i in range(3):
            principle_result = await services.principles.core.create_principle(
                label=f"Test Principle {i}",
                description=f"Test principle {i}",
                category=PrincipleCategory.PERSONAL,
                why_matters="For testing",
                user_uid="test_user",
            )
            assert principle_result.is_ok
            principle_uids.append(principle_result.value.uid)

        # Batch analyze
        batch_result = await services.principles.intelligence.batch_analyze_principle_adoption(
            principle_uids
        )
        assert batch_result.is_ok

        results = batch_result.value

        # Verify all principles analyzed
        assert len(results) == 3
        for uid in principle_uids:
            assert uid in results
            assert "impact_score" in results[uid]
            assert "adoption_level" in results[uid]
            assert "total_actions" in results[uid]
            assert "has_foundation" in results[uid]
            assert "guides_actions" in results[uid]
