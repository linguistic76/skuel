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
from core.models.enums.ku_enums import (
    AlignmentLevel,
    EntityType,
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
def alignment_service(mock_backend) -> PrinciplesAlignmentService:
    """Create alignment service with mock backend."""
    return PrinciplesAlignmentService(backend=mock_backend, goals_backend=None, habits_backend=None)


@pytest.fixture
def sample_principle_with_alignment() -> Principle:
    """Create sample principle with alignment history."""
    return Principle(
        ku_type=EntityType.PRINCIPLE,
        uid="principle.integrity",
        user_uid="user.mike",  # REQUIRED - principle ownership
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
        ku_type=EntityType.PRINCIPLE,
        uid="principle.growth",
        user_uid="user.mike",  # REQUIRED - principle ownership
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
    """Test alignment level to numeric score conversion."""

    def test_aligned_score(self, alignment_service):
        """Test ALIGNED maps to 1.0."""
        score = alignment_service._alignment_level_to_score(AlignmentLevel.ALIGNED)
        assert score == 1.0

    def test_mostly_aligned_score(self, alignment_service):
        """Test MOSTLY_ALIGNED maps to 0.75."""
        score = alignment_service._alignment_level_to_score(AlignmentLevel.MOSTLY_ALIGNED)
        assert score == 0.75

    def test_partial_alignment_score(self, alignment_service):
        """Test PARTIAL maps to 0.5."""
        score = alignment_service._alignment_level_to_score(AlignmentLevel.PARTIAL)
        assert score == 0.5

    def test_misaligned_score(self, alignment_service):
        """Test MISALIGNED maps to 0.0."""
        score = alignment_service._alignment_level_to_score(AlignmentLevel.MISALIGNED)
        assert score == 0.0

    def test_unknown_alignment_score(self, alignment_service):
        """Test UNKNOWN maps to 0.25."""
        score = alignment_service._alignment_level_to_score(AlignmentLevel.UNKNOWN)
        assert score == 0.25

    def test_none_alignment_score(self, alignment_service):
        """Test None alignment level defaults to 0.0."""
        score = alignment_service._alignment_level_to_score(None)
        assert score == 0.0


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
        result = await alignment_service.calculate_average_alignment("user.mike")

        # Verify
        assert result.is_ok
        # Only principle with alignment history counts
        # Latest alignment is STRONG (1.0)
        assert result.value == 1.0

    @pytest.mark.asyncio
    async def test_calculate_average_alignment_no_principles(self, alignment_service, mock_backend):
        """Test average alignment with no principles."""
        mock_backend.find_by.return_value = Result.ok([])

        result = await alignment_service.calculate_average_alignment("user.mike")

        assert result.is_ok
        assert result.value == 0.0

    @pytest.mark.asyncio
    async def test_calculate_average_alignment_backend_error(self, alignment_service, mock_backend):
        """Test average alignment calculation when backend fails."""
        mock_backend.find_by.return_value = Result.fail(
            {"code": "DB_ERROR", "message": "Database error"}
        )

        result = await alignment_service.calculate_average_alignment("user.mike")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_calculate_average_multiple_alignments(self, alignment_service, mock_backend):
        """Test average with multiple principles having different alignment levels."""
        # Create principles with different alignment levels
        principle1 = Principle(
            ku_type=EntityType.PRINCIPLE,
            uid="p1",
            user_uid="user.mike",  # REQUIRED - principle ownership
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
                    alignment_level=AlignmentLevel.ALIGNED,  # 1.0
                    evidence="",
                    reflection="",
                ),
            ),
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        principle2 = Principle(
            ku_type=EntityType.PRINCIPLE,
            uid="p2",
            user_uid="user.mike",  # REQUIRED - principle ownership
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
                    alignment_level=AlignmentLevel.MOSTLY_ALIGNED,  # 0.75
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

        result = await alignment_service.calculate_average_alignment("user.mike")

        assert result.is_ok
        # Average of 1.0 and 0.75 = 0.875
        assert result.value == 0.875


class TestGetPrincipleExpressionsAndAlignments:
    """Test getting expressions and alignments for a principle."""

    @pytest.mark.asyncio
    async def test_get_expressions_and_alignments_success(
        self, alignment_service, mock_backend, sample_principle_with_alignment
    ):
        """Test successfully getting expressions and alignments."""
        mock_backend.get.return_value = Result.ok(
            sample_principle_with_alignment.to_dto().to_dict()
        )

        result = await alignment_service.get_principle_expressions_and_alignments(
            "principle.integrity"
        )

        assert result.is_ok
        data = result.value

        # Check structure
        assert data["principle_uid"] == "principle.integrity"
        assert len(data["expressions"]) == 2
        # Expressions are now PrincipleExpression objects converted to strings
        assert any("Be honest" in str(expr) for expr in data["expressions"])

        # Check alignments
        assert len(data["alignments"]) == 2
        assert data["alignments"][1]["alignment_level"] == "aligned"
        assert data["alignments"][1]["alignment_score"] == 1.0

        # Check metadata
        assert data["total_expressions"] == 2
        assert data["total_assessments"] == 2
        assert data["current_alignment"] == "aligned"

    @pytest.mark.asyncio
    async def test_get_expressions_no_data(
        self, alignment_service, mock_backend, sample_principle_no_alignment
    ):
        """Test getting expressions when principle has no alignments."""
        mock_backend.get.return_value = Result.ok(sample_principle_no_alignment.to_dto().to_dict())

        result = await alignment_service.get_principle_expressions_and_alignments(
            "principle.growth"
        )

        assert result.is_ok
        data = result.value

        assert len(data["expressions"]) == 2
        assert len(data["alignments"]) == 0
        assert data["current_alignment"] == "unknown"

    @pytest.mark.asyncio
    async def test_get_expressions_backend_error(self, alignment_service, mock_backend):
        """Test error handling when backend fails."""
        mock_backend.get.return_value = Result.fail(
            {"code": "NOT_FOUND", "message": "Principle not found"}
        )

        result = await alignment_service.get_principle_expressions_and_alignments(
            "principle.nonexistent"
        )

        assert result.is_error


class TestGetRecentActivity:
    """Test recent activity tracking."""

    @pytest.mark.asyncio
    async def test_get_recent_activity_with_data(
        self, alignment_service, mock_backend, sample_principle_with_alignment
    ):
        """Test getting recent activity with principles."""
        mock_backend.find_by.return_value = Result.ok(
            [sample_principle_with_alignment.to_dto().to_dict()]
        )

        result = await alignment_service.get_recent_activity("user.mike", limit=10)

        assert result.is_ok
        activities = result.value

        # Should have: 1 principle update + 2 alignment assessments + 2 expressions = 5
        assert len(activities) == 5

        # Check activity types
        activity_types = [a["type"] for a in activities]
        assert "principle_updated" in activity_types
        assert "alignment_assessed" in activity_types
        assert "expression_added" in activity_types

        # Check activities are sorted by timestamp (most recent first)
        timestamps = [a["timestamp"] for a in activities]
        assert timestamps == sorted(timestamps, reverse=True)

    @pytest.mark.asyncio
    async def test_get_recent_activity_limit(
        self, alignment_service, mock_backend, sample_principle_with_alignment
    ):
        """Test activity limit is respected."""
        mock_backend.find_by.return_value = Result.ok(
            [sample_principle_with_alignment.to_dto().to_dict()]
        )

        result = await alignment_service.get_recent_activity("user.mike", limit=2)

        assert result.is_ok
        activities = result.value
        assert len(activities) == 2

    @pytest.mark.asyncio
    async def test_get_recent_activity_no_principles(self, alignment_service, mock_backend):
        """Test getting activity with no principles."""
        mock_backend.find_by.return_value = Result.ok([])

        result = await alignment_service.get_recent_activity("user.mike")

        assert result.is_ok
        assert len(result.value) == 0

    @pytest.mark.asyncio
    async def test_get_recent_activity_backend_error(self, alignment_service, mock_backend):
        """Test activity tracking when backend fails."""
        mock_backend.find_by.return_value = Result.fail(
            {"code": "DB_ERROR", "message": "Database error"}
        )

        result = await alignment_service.get_recent_activity("user.mike")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_activity_content_structure(
        self, alignment_service, mock_backend, sample_principle_with_alignment
    ):
        """Test activity content has correct structure."""
        mock_backend.find_by.return_value = Result.ok(
            [sample_principle_with_alignment.to_dto().to_dict()]
        )

        result = await alignment_service.get_recent_activity("user.mike")

        assert result.is_ok
        activities = result.value

        for activity in activities:
            assert "timestamp" in activity
            assert "type" in activity
            assert "description" in activity
            assert "principle_uid" in activity
            assert "principle_name" in activity

            # Alignment assessments have extra field
            if activity["type"] == "alignment_assessed":
                assert "alignment_level" in activity

            # Expressions have extra field
            if activity["type"] == "expression_added":
                assert "expression" in activity


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
