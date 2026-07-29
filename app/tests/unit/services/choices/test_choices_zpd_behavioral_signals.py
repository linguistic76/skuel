"""
Unit tests for _BehavioralSignalsMixin.get_zpd_behavioral_signals
================================================================

Tests the ZPD bridge that feeds behavioral readiness signals to
ZPDService.assess_zone(). Cross-domain reads are delegated to
CrossDomainQueryService; this test verifies the delegation wiring
and graceful-degradation paths.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.choices.choices_intelligence_service import ChoicesIntelligenceService
from core.services.cross_domain import ChoicePrincipleAdherence, ChoicePrincipleConflictCount
from core.utils.result_simplified import Errors, Result


@pytest.fixture
def mock_backend() -> MagicMock:
    backend = MagicMock()
    backend.find_by = AsyncMock(return_value=Result.ok([]))
    return backend


@pytest.fixture
def mock_cross_domain_query() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def intelligence_service(
    mock_backend: MagicMock, mock_cross_domain_query: AsyncMock
) -> ChoicesIntelligenceService:
    # _require_relationships = True — the constructor refuses a missing relationship
    # service, so supply a stub even where these tests do not exercise a graph read.
    return ChoicesIntelligenceService(
        backend=mock_backend,
        cross_domain_query=mock_cross_domain_query,
        relationship_service=MagicMock(),
    )


class TestGetZpdBehavioralSignals:
    @pytest.mark.asyncio
    async def test_delegates_to_cross_domain_query(
        self,
        intelligence_service: ChoicesIntelligenceService,
        mock_cross_domain_query: AsyncMock,
    ) -> None:
        """Both cross-domain methods are called; result keys are present."""
        mock_cross_domain_query.get_choice_principle_adherence.return_value = Result.ok(
            ChoicePrincipleAdherence(total_choices=10, aligned_count=7, choice_details=())
        )
        mock_cross_domain_query.get_choice_conflict_count.return_value = Result.ok(
            ChoicePrincipleConflictCount(conflict_count=2)
        )

        result = await intelligence_service.get_zpd_behavioral_signals(user_uid="user_mike")

        assert result.is_ok
        data = result.value
        assert "principle_adherence_score" in data
        assert "decision_consistency_score" in data
        assert "active_conflict_count" in data
        assert data["active_conflict_count"] == 2
        assert "high_quality_decision_rate" in data

        mock_cross_domain_query.get_choice_principle_adherence.assert_awaited_once()
        mock_cross_domain_query.get_choice_conflict_count.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_propagates_adherence_failure_gracefully(
        self,
        intelligence_service: ChoicesIntelligenceService,
        mock_cross_domain_query: AsyncMock,
    ) -> None:
        """When adherence query fails, score defaults to 0.0."""
        mock_cross_domain_query.get_choice_principle_adherence.return_value = Result.fail(
            Errors.database(operation="execute_query", message="neo4j down")
        )
        mock_cross_domain_query.get_choice_conflict_count.return_value = Result.ok(
            ChoicePrincipleConflictCount(conflict_count=0)
        )

        result = await intelligence_service.get_zpd_behavioral_signals(user_uid="user_mike")

        assert result.is_ok
        assert result.value["principle_adherence_score"] == 0.0

    @pytest.mark.asyncio
    async def test_propagates_conflict_failure_gracefully(
        self,
        intelligence_service: ChoicesIntelligenceService,
        mock_cross_domain_query: AsyncMock,
    ) -> None:
        """When conflict query fails, count defaults to 0."""
        mock_cross_domain_query.get_choice_principle_adherence.return_value = Result.ok(
            ChoicePrincipleAdherence(total_choices=5, aligned_count=3, choice_details=())
        )
        mock_cross_domain_query.get_choice_conflict_count.return_value = Result.fail(
            Errors.database(operation="execute_query", message="neo4j down")
        )

        result = await intelligence_service.get_zpd_behavioral_signals(user_uid="user_mike")

        assert result.is_ok
        assert result.value["active_conflict_count"] == 0
