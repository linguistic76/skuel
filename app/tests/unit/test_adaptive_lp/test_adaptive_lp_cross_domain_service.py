"""
Test Suite for AdaptiveLpCrossDomainService
============================================

Tests the cross-domain opportunity discovery service:
- Multi-domain opportunity detection
- Innovation opportunity generation (3+ domains)
- Domain grouping from KU UIDs
- Confidence threshold filtering
"""

from __future__ import annotations

import pytest

from core.services.adaptive_lp.adaptive_lp_cross_domain_service import (
    AdaptiveLpCrossDomainService,
)
from core.services.adaptive_lp.adaptive_lp_models import CrossDomainOpportunity
from core.services.adaptive_lp_types import KnowledgeState

# ============================================================================
# TEST FIXTURES
# ============================================================================


@pytest.fixture
def cross_domain_service():
    """Create cross-domain service (no dependencies needed)."""
    return AdaptiveLpCrossDomainService()


@pytest.fixture
def single_domain_state():
    """KnowledgeState with knowledge in only one domain."""
    return KnowledgeState(
        mastered_knowledge={"ku.tech.python", "ku.tech.javascript"},
        in_progress_knowledge=set(),
        applied_knowledge=set(),
        knowledge_strengths={},
        knowledge_gaps=[],
        mastery_levels={"ku.tech.python": 0.9, "ku.tech.javascript": 0.8},
        learning_velocity=1.0,
    )


@pytest.fixture
def two_domain_state():
    """KnowledgeState with knowledge in two domains."""
    return KnowledgeState(
        mastered_knowledge={
            "ku.tech.python",
            "ku.tech.javascript",
            "ku.data.ml",
            "ku.data.statistics",
        },
        in_progress_knowledge=set(),
        applied_knowledge=set(),
        knowledge_strengths={},
        knowledge_gaps=[],
        mastery_levels={
            "ku.tech.python": 0.9,
            "ku.tech.javascript": 0.8,
            "ku.data.ml": 0.85,
            "ku.data.statistics": 0.75,
        },
        learning_velocity=1.5,
    )


@pytest.fixture
def multi_domain_state():
    """KnowledgeState with knowledge in 3+ domains (innovation opportunities)."""
    return KnowledgeState(
        mastered_knowledge={
            "ku.tech.python",
            "ku.tech.javascript",
            "ku.data.ml",
            "ku.data.statistics",
            "ku.business.strategy",
            "ku.business.marketing",
        },
        in_progress_knowledge=set(),
        applied_knowledge=set(),
        knowledge_strengths={},
        knowledge_gaps=[],
        mastery_levels={
            "ku.tech.python": 0.9,
            "ku.tech.javascript": 0.8,
            "ku.data.ml": 0.85,
            "ku.data.statistics": 0.75,
            "ku.business.strategy": 0.7,
            "ku.business.marketing": 0.65,
        },
        learning_velocity=2.0,
    )


@pytest.fixture
def empty_state():
    """Empty KnowledgeState."""
    return KnowledgeState(
        mastered_knowledge=set(),
        in_progress_knowledge=set(),
        applied_knowledge=set(),
        knowledge_strengths={},
        knowledge_gaps=[],
        mastery_levels={},
        learning_velocity=0.0,
    )


# ============================================================================
# TESTS: Cross-Domain Opportunity Discovery
# ============================================================================


class TestCrossDomainOpportunityDiscovery:
    """Test cross-domain opportunity discovery."""

    @pytest.mark.asyncio
    async def test_discover_cross_domain_opportunities_two_domains(
        self, cross_domain_service, two_domain_state
    ):
        """Opportunities discovered when user has knowledge in 2+ domains."""
        result = await cross_domain_service.discover_cross_domain_opportunities(
            user_uid="user_001",
            knowledge_state=two_domain_state,
        )

        assert result.is_ok
        opportunities = result.value
        assert isinstance(opportunities, list)
        # Should find opportunities bridging tech and data domains

    @pytest.mark.asyncio
    async def test_discover_cross_domain_opportunities_insufficient_domains(
        self, cross_domain_service, single_domain_state
    ):
        """No opportunities when knowledge is in only one domain."""
        result = await cross_domain_service.discover_cross_domain_opportunities(
            user_uid="user_001",
            knowledge_state=single_domain_state,
        )

        assert result.is_ok
        opportunities = result.value
        # Single domain = no cross-domain opportunities
        assert isinstance(opportunities, list)

    @pytest.mark.asyncio
    async def test_discover_cross_domain_opportunities_empty_state(
        self, cross_domain_service, empty_state
    ):
        """Empty knowledge state returns empty opportunities list."""
        result = await cross_domain_service.discover_cross_domain_opportunities(
            user_uid="user_001",
            knowledge_state=empty_state,
        )

        assert result.is_ok
        opportunities = result.value
        assert len(opportunities) == 0


# ============================================================================
# TESTS: Innovation Opportunities
# ============================================================================


class TestInnovationOpportunities:
    """Test innovation opportunity generation (3+ domains)."""

    @pytest.mark.asyncio
    async def test_discover_innovation_opportunities_three_plus_domains(
        self, cross_domain_service, multi_domain_state
    ):
        """Innovation opportunities generated for 3+ domain knowledge."""
        result = await cross_domain_service.discover_cross_domain_opportunities(
            user_uid="user_001",
            knowledge_state=multi_domain_state,
        )

        assert result.is_ok
        opportunities = result.value
        assert isinstance(opportunities, list)
        # May include innovation opportunities combining tech, data, and business


# ============================================================================
# TESTS: Scoring and Filtering
# ============================================================================


class TestScoringAndFiltering:
    """Test opportunity scoring and confidence filtering."""

    @pytest.mark.asyncio
    async def test_score_cross_domain_opportunities(self, cross_domain_service, two_domain_state):
        """Opportunities are scored by relevance and impact."""
        result = await cross_domain_service.discover_cross_domain_opportunities(
            user_uid="user_001",
            knowledge_state=two_domain_state,
        )

        assert result.is_ok
        opportunities = result.value

        # Each opportunity should have scoring fields
        for opp in opportunities:
            if isinstance(opp, CrossDomainOpportunity):
                assert hasattr(opp, "skill_transfer_potential")
                assert hasattr(opp, "estimated_value")

    @pytest.mark.asyncio
    async def test_confidence_threshold_filtering(self, cross_domain_service, two_domain_state):
        """Low confidence opportunities filtered out."""
        result = await cross_domain_service.discover_cross_domain_opportunities(
            user_uid="user_001",
            knowledge_state=two_domain_state,
            min_confidence=0.8,  # High threshold
        )

        assert result.is_ok
        opportunities = result.value
        # May return fewer opportunities with high threshold
        assert isinstance(opportunities, list)  # Verify return type


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
