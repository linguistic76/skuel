"""
Unit tests for KuIntelligenceService.

Tests graph analytics for atomic Knowledge Units:
- Protocol methods (get_with_context, get_performance_analytics, get_domain_insights)
- Domain-specific methods (get_usage_summary, is_trained, is_organized, get_organization_depth)
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.ku.ku import Ku
from core.services.ku.ku_intelligence_service import KuIntelligenceService
from core.utils.result_simplified import Errors, Result


def _make_ku(uid: str = "ku_test_abc123", title: str = "Test Ku", **kwargs):
    """Create a minimal Ku for testing."""
    return Ku(uid=uid, title=title, **kwargs)


def _make_backend():
    """Create a mock backend with common methods."""
    backend = AsyncMock()
    backend.execute_query = AsyncMock()
    backend.find_by = AsyncMock()
    backend.get = AsyncMock()
    return backend


class TestKuIntelligenceGetWithContext:
    """Test get_with_context protocol method."""

    @pytest.mark.asyncio
    async def test_returns_error_without_graph_intel(self):
        backend = _make_backend()
        service = KuIntelligenceService(backend=backend, graph_intelligence_service=None)

        result = await service.get_with_context("ku_test_abc123")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_delegates_to_orchestrator(self):
        backend = _make_backend()
        graph_intel = MagicMock()
        service = KuIntelligenceService(backend=backend, graph_intelligence_service=graph_intel)

        mock_context = MagicMock()
        ku = _make_ku()
        service.orchestrator.get_with_context = AsyncMock(
            return_value=Result.ok((ku, mock_context))
        )

        result = await service.get_with_context("ku_test_abc123", depth=3)

        assert result.is_ok
        service.orchestrator.get_with_context.assert_awaited_once_with(
            uid="ku_test_abc123", depth=3
        )


class TestKuIntelligencePerformanceAnalytics:
    """Test get_performance_analytics protocol method."""

    @pytest.mark.asyncio
    async def test_returns_total_and_namespace_breakdown(self):
        backend = _make_backend()
        backend.find_by.return_value = Result.ok(
            [
                _make_ku("ku_a_1", namespace="attention"),
                _make_ku("ku_b_2", namespace="attention"),
                _make_ku("ku_c_3", namespace="emotion"),
            ]
        )
        service = KuIntelligenceService(backend=backend)

        result = await service.get_performance_analytics("user_123", period_days=7)

        assert result.is_ok
        data = result.value
        assert data["total_kus"] == 3
        assert data["by_namespace"]["attention"] == 2
        assert data["by_namespace"]["emotion"] == 1

    @pytest.mark.asyncio
    async def test_handles_backend_error(self):
        backend = _make_backend()
        backend.find_by.return_value = Result.fail(
            Errors.database(operation="find_by", message="connection failed")
        )
        service = KuIntelligenceService(backend=backend)

        result = await service.get_performance_analytics("user_123")

        assert result.is_error


class TestKuIntelligenceDomainInsights:
    """Test get_domain_insights protocol method."""

    @pytest.mark.asyncio
    async def test_returns_insights_with_usage_and_depth(self):
        backend = _make_backend()
        ku = _make_ku(namespace="body", ku_category="substance", aliases=("coffee", "java"))
        backend.get.return_value = Result.ok(ku)
        backend.execute_query.return_value = Result.ok(
            [{"articles": 3, "learning_steps": 1, "organized_children": 0}]
        )
        service = KuIntelligenceService(backend=backend)

        result = await service.get_domain_insights("ku_test_abc123")

        assert result.is_ok
        data = result.value
        assert data["ku_title"] == "Test Ku"
        assert data["namespace"] == "body"
        assert data["alias_count"] == 2
        assert data["usage"]["articles"] == 3

    @pytest.mark.asyncio
    async def test_returns_not_found_for_missing_ku(self):
        backend = _make_backend()
        backend.get.return_value = Result.ok(None)
        service = KuIntelligenceService(backend=backend)

        result = await service.get_domain_insights("ku_missing_xyz")

        assert result.is_error


class TestKuIntelligenceUsageSummary:
    """Test get_usage_summary domain method."""

    @pytest.mark.asyncio
    async def test_returns_counts(self):
        backend = _make_backend()
        backend.execute_query.return_value = Result.ok(
            [{"articles": 5, "learning_steps": 2, "organized_children": 3}]
        )
        service = KuIntelligenceService(backend=backend)

        result = await service.get_usage_summary("ku_test_abc123")

        assert result.is_ok
        assert result.value == {
            "articles": 5,
            "learning_steps": 2,
            "organized_children": 3,
        }

    @pytest.mark.asyncio
    async def test_returns_zeros_for_no_records(self):
        backend = _make_backend()
        backend.execute_query.return_value = Result.ok([])
        service = KuIntelligenceService(backend=backend)

        result = await service.get_usage_summary("ku_test_abc123")

        assert result.is_ok
        assert result.value == {"articles": 0, "learning_steps": 0, "organized_children": 0}


class TestKuIntelligenceIsTrained:
    """Test is_trained domain method."""

    @pytest.mark.asyncio
    async def test_true_when_trained(self):
        backend = _make_backend()
        backend.execute_query.return_value = Result.ok([{"trained": True}])
        service = KuIntelligenceService(backend=backend)

        result = await service.is_trained("ku_test_abc123")

        assert result.is_ok
        assert result.value is True

    @pytest.mark.asyncio
    async def test_false_when_not_trained(self):
        backend = _make_backend()
        backend.execute_query.return_value = Result.ok([{"trained": False}])
        service = KuIntelligenceService(backend=backend)

        result = await service.is_trained("ku_test_abc123")

        assert result.is_ok
        assert result.value is False


class TestKuIntelligenceIsOrganized:
    """Test is_organized domain method."""

    @pytest.mark.asyncio
    async def test_true_when_has_children(self):
        backend = _make_backend()
        backend.execute_query.return_value = Result.ok([{"organized": True}])
        service = KuIntelligenceService(backend=backend)

        result = await service.is_organized("ku_test_abc123")

        assert result.is_ok
        assert result.value is True

    @pytest.mark.asyncio
    async def test_false_when_no_children(self):
        backend = _make_backend()
        backend.execute_query.return_value = Result.ok([{"organized": False}])
        service = KuIntelligenceService(backend=backend)

        result = await service.is_organized("ku_test_abc123")

        assert result.is_ok
        assert result.value is False


class TestKuIntelligenceOrganizationDepth:
    """Test get_organization_depth domain method."""

    @pytest.mark.asyncio
    async def test_returns_depth(self):
        backend = _make_backend()
        backend.execute_query.return_value = Result.ok([{"max_depth": 3}])
        service = KuIntelligenceService(backend=backend)

        result = await service.get_organization_depth("ku_test_abc123")

        assert result.is_ok
        assert result.value == 3

    @pytest.mark.asyncio
    async def test_returns_zero_for_leaf(self):
        backend = _make_backend()
        backend.execute_query.return_value = Result.ok([{"max_depth": None}])
        service = KuIntelligenceService(backend=backend)

        result = await service.get_organization_depth("ku_test_abc123")

        assert result.is_ok
        assert result.value == 0
