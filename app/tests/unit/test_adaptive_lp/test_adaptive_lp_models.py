"""
Test Suite for Adaptive LP Models
==================================

Tests the data models used by the adaptive learning path services:
- CrossDomainOpportunity (dataclass)
- KnowledgeState (frozen dataclass)
"""

from __future__ import annotations

import pytest

from core.models.enums import Domain
from core.services.adaptive_lp.adaptive_lp_models import CrossDomainOpportunity
from core.services.adaptive_lp_types import KnowledgeState

# ============================================================================
# TESTS: CrossDomainOpportunity Model
# ============================================================================


class TestCrossDomainOpportunityModel:
    """Test CrossDomainOpportunity frozen dataclass."""

    def test_cross_domain_opportunity_creation(self):
        """CrossDomainOpportunity can be created with domain pair."""
        opp = CrossDomainOpportunity(
            opportunity_id="opp_001",
            title="Tech to Data Science",
            description="Apply programming skills to data science",
            source_domain=Domain.TECH,
            target_domain=Domain.TECH,  # Both programming and data are TECH
            bridging_knowledge=["ku.python-basics", "ku.data-ml"],
            application_type="data_science",
            practical_projects=["Build a data pipeline"],
            skill_transfer_potential=0.85,
            innovation_potential=0.8,
            prerequisite_knowledge=["ku.python-basics"],
            source_knowledge_uids=["ku.python-basics"],
            target_knowledge_uids=["ku.data-ml"],
            estimated_difficulty=6.0,
            estimated_value=0.9,
            supporting_examples=["Data engineering roles"],
            success_patterns=["Python to ML transition"],
            confidence_score=0.85,
        )

        assert opp.source_domain == Domain.TECH
        assert opp.target_domain == Domain.TECH
        assert len(opp.bridging_knowledge) == 2


# ============================================================================
# TESTS: KnowledgeState Model
# ============================================================================


class TestKnowledgeStateModel:
    """Test KnowledgeState frozen dataclass."""

    def test_knowledge_state_creation(self):
        """KnowledgeState can be created with knowledge sets."""
        state = KnowledgeState(
            mastered_knowledge={"ku.python-basics"},
            in_progress_knowledge={"ku.python-advanced"},
            applied_knowledge=set(),
            knowledge_strengths={"ku.python-basics": 5},
            knowledge_gaps=["ku.data-structures"],
            mastery_levels={"ku.python-basics": 0.9},
            learning_velocity=1.5,
        )

        assert "ku.python-basics" in state.mastered_knowledge
        assert state.learning_velocity == 1.5

    def test_knowledge_state_frozen(self):
        """KnowledgeState is immutable."""
        state = KnowledgeState(
            mastered_knowledge=set(),
            in_progress_knowledge=set(),
            applied_knowledge=set(),
            knowledge_strengths={},
            knowledge_gaps=[],
            mastery_levels={},
            learning_velocity=0.0,
        )

        with pytest.raises((AttributeError, TypeError)):
            state.learning_velocity = 5.0  # type: ignore[misc]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
