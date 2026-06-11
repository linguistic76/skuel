"""
Tests for Principles Alignment Tracking
========================================

Comprehensive tests for the alignment calculation and activity tracking
methods added to PrinciplesAlignmentService.

Version: 1.0.0
Date: 2025-10-14
"""

from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from core.models.enums import Priority
from core.models.enums.entity_enums import EntityType
from core.models.enums.principle_enums import (
    AlignmentLevel,
    PrincipleCategory,
    PrincipleSource,
    PrincipleStrength,
)
from core.models.principle.principle import Principle
from core.models.principle.principle_types import AlignmentAssessment, PrincipleExpression
from core.services.principles.principles_alignment_service import PrinciplesAlignmentService
from core.utils.result_simplified import Result


@pytest.fixture
def mock_backend() -> AsyncMock:
    """Create mock backend for testing."""
    return AsyncMock()


@pytest.fixture
def mock_cross_domain_query() -> AsyncMock:
    """Mock CrossDomainQueryService — required by PrinciplesAlignmentService."""
    return AsyncMock()


@pytest.fixture
def alignment_service(mock_backend, mock_cross_domain_query) -> PrinciplesAlignmentService:
    """Create alignment service with mock backend."""
    return PrinciplesAlignmentService(
        backend=mock_backend,
        cross_domain_query=mock_cross_domain_query,
    )


@pytest.fixture
def sample_principle_with_alignment() -> Principle:
    """Create sample principle with alignment history."""
    return Principle(
        entity_type=EntityType.PRINCIPLE,
        uid="principle.integrity",
        user_uid="user_mike",  # REQUIRED - principle ownership
        title="Integrity",
        statement="Act with honesty and consistency",
        description="Always do what I say I will do",
        principle_category=PrincipleCategory.ETHICAL,
        strength=PrincipleStrength.CORE,
        principle_source=PrincipleSource.PHILOSOPHICAL,
        priority=Priority.HIGH,
        alignment_history=(
            AlignmentAssessment(
                assessed_date=datetime(2025, 10, 1),
                alignment_level=AlignmentLevel.MOSTLY_ALIGNED,
                evidence="Made good decisions this week",
                reflection="Could be more consistent",
            ),
            AlignmentAssessment(
                assessed_date=datetime(2025, 10, 10),
                alignment_level=AlignmentLevel.ALIGNED,
                evidence="Kept all commitments",
                reflection="Feeling aligned",
            ),
        ),
        current_alignment=AlignmentLevel.ALIGNED,
        expressions=(
            PrincipleExpression(context="daily life", behavior="Be honest"),
            PrincipleExpression(context="commitments", behavior="Keep promises"),
        ),
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


@pytest.fixture
def sample_principle_no_alignment() -> Principle:
    """Create sample principle without alignment history."""
    return Principle(
        entity_type=EntityType.PRINCIPLE,
        uid="principle.growth",
        user_uid="user_mike",  # REQUIRED - principle ownership
        title="Growth",
        statement="Continuously learn and improve",
        description="Never stop growing",
        principle_category=PrincipleCategory.PERSONAL,
        strength=PrincipleStrength.DEVELOPING,
        principle_source=PrincipleSource.PERSONAL,
        priority=Priority.MEDIUM,
        alignment_history=(),
        current_alignment=AlignmentLevel.UNKNOWN,  # Use UNKNOWN instead of None
        expressions=(
            PrincipleExpression(context="daily", behavior="Read daily"),
            PrincipleExpression(context="skills", behavior="Learn new skills"),
        ),
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


class TestAlignmentLevelToScore:
    """Test alignment level to numeric score conversion.

    Delegates to AlignmentLevel.to_score() — canonical scores from _ALIGNMENT_SCORES.
    """

    def test_aligned_score(self, alignment_service):
        """Test ALIGNED maps to 0.85."""
        score = alignment_service._alignment_level_to_score(AlignmentLevel.ALIGNED)
        assert score == 0.85

    def test_mostly_aligned_score(self, alignment_service):
        """Test MOSTLY_ALIGNED maps to 0.7."""
        score = alignment_service._alignment_level_to_score(AlignmentLevel.MOSTLY_ALIGNED)
        assert score == 0.7

    def test_partial_alignment_score(self, alignment_service):
        """Test PARTIAL maps to 0.35."""
        score = alignment_service._alignment_level_to_score(AlignmentLevel.PARTIAL)
        assert score == 0.35

    def test_misaligned_score(self, alignment_service):
        """Test MISALIGNED maps to 0.1."""
        score = alignment_service._alignment_level_to_score(AlignmentLevel.MISALIGNED)
        assert score == 0.1

    def test_unknown_alignment_score(self, alignment_service):
        """Test UNKNOWN maps to 0.0."""
        score = alignment_service._alignment_level_to_score(AlignmentLevel.UNKNOWN)
        assert score == 0.0

    def test_flourishing_score(self, alignment_service):
        """Test FLOURISHING maps to 1.0."""
        score = alignment_service._alignment_level_to_score(AlignmentLevel.FLOURISHING)
        assert score == 1.0


class TestCalculateAverageAlignment:
    """Test average alignment calculation."""

    @pytest.mark.asyncio
    async def test_calculate_average_alignment_with_data(
        self,
        alignment_service,
        mock_backend,
        sample_principle_with_alignment,
        sample_principle_no_alignment,
    ):
        """Test average alignment calculation with multiple principles."""
        # Mock backend to return principles
        mock_backend.find_by.return_value = Result.ok(
            [
                sample_principle_with_alignment.to_dto().to_dict(),
                sample_principle_no_alignment.to_dto().to_dict(),
            ]
        )

        # Calculate average
        result = await alignment_service.calculate_average_alignment("user_mike")

        # Verify
        assert result.is_ok
        # Only principle with alignment history counts
        # Latest alignment is ALIGNED (0.85)
        assert result.value == 0.85

    @pytest.mark.asyncio
    async def test_calculate_average_alignment_no_principles(self, alignment_service, mock_backend):
        """Test average alignment with no principles."""
        mock_backend.find_by.return_value = Result.ok([])

        result = await alignment_service.calculate_average_alignment("user_mike")

        assert result.is_ok
        assert result.value == 0.0

    @pytest.mark.asyncio
    async def test_calculate_average_alignment_backend_error(self, alignment_service, mock_backend):
        """Test average alignment calculation when backend fails."""
        mock_backend.find_by.return_value = Result.fail(
            {"code": "DB_ERROR", "message": "Database error"}
        )

        result = await alignment_service.calculate_average_alignment("user_mike")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_calculate_average_multiple_alignments(self, alignment_service, mock_backend):
        """Test average with multiple principles having different alignment levels."""
        # Create principles with different alignment levels
        principle1 = Principle(
            entity_type=EntityType.PRINCIPLE,
            uid="p1",
            user_uid="user_mike",  # REQUIRED - principle ownership
            title="P1",
            statement="Test",
            description="Test",
            principle_category=PrincipleCategory.ETHICAL,
            strength=PrincipleStrength.CORE,
            principle_source=PrincipleSource.PERSONAL,
            priority=Priority.HIGH,
            alignment_history=(
                AlignmentAssessment(
                    assessed_date=datetime.now(),
                    alignment_level=AlignmentLevel.ALIGNED,  # 0.85
                    evidence="",
                    reflection="",
                ),
            ),
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        principle2 = Principle(
            entity_type=EntityType.PRINCIPLE,
            uid="p2",
            user_uid="user_mike",  # REQUIRED - principle ownership
            title="P2",
            statement="Test",
            description="Test",
            principle_category=PrincipleCategory.ETHICAL,
            strength=PrincipleStrength.CORE,
            principle_source=PrincipleSource.PERSONAL,
            priority=Priority.MEDIUM,
            alignment_history=(
                AlignmentAssessment(
                    assessed_date=datetime.now(),
                    alignment_level=AlignmentLevel.MOSTLY_ALIGNED,  # 0.7
                    evidence="",
                    reflection="",
                ),
            ),
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        mock_backend.find_by.return_value = Result.ok(
            [principle1.to_dto().to_dict(), principle2.to_dto().to_dict()]
        )

        result = await alignment_service.calculate_average_alignment("user_mike")

        assert result.is_ok
        # Average of 0.85 and 0.7 = 0.775
        assert result.value == pytest.approx(0.775)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
