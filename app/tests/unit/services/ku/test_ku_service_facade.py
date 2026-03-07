"""
Unit tests for KuService facade.

Tests:
- Construction via create_curriculum_sub_services() factory
- CRUD/search delegation unchanged
- Intelligence delegation
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.utils.result_simplified import Result


class TestKuServiceConstruction:
    """Verify KuService creates 4 sub-services via factory."""

    def test_requires_backend(self):
        from core.services.ku_service import KuService

        with pytest.raises(ValueError, match="backend is REQUIRED"):
            KuService(backend=None, graph_intel=MagicMock())

    def test_requires_graph_intel(self):
        from core.services.ku_service import KuService

        with pytest.raises(ValueError, match="graph_intel is REQUIRED"):
            KuService(backend=MagicMock(), graph_intel=None)

    @patch("core.utils.curriculum_domain_config.create_curriculum_sub_services")
    def test_creates_4_sub_services(self, mock_factory):
        from core.services.ku_service import KuService

        mock_common = MagicMock()
        mock_common.core = MagicMock()
        mock_common.search = MagicMock()
        mock_common.relationships = MagicMock()
        mock_common.intelligence = MagicMock()
        mock_factory.return_value = mock_common

        backend = MagicMock()
        graph_intel = MagicMock()
        event_bus = MagicMock()

        service = KuService(backend=backend, graph_intel=graph_intel, event_bus=event_bus)

        mock_factory.assert_called_once_with(
            domain="ku",
            backend=backend,
            graph_intel=graph_intel,
            event_bus=event_bus,
        )
        assert service.core is mock_common.core
        assert service.search_service is mock_common.search
        assert service.relationships is mock_common.relationships
        assert service.intelligence is mock_common.intelligence
        assert service.backend is backend


class TestKuServiceDelegation:
    """Verify CRUD/search delegation works correctly."""

    @patch("core.utils.curriculum_domain_config.create_curriculum_sub_services")
    def _make_service(self, mock_factory):
        from core.services.ku_service import KuService

        mock_common = MagicMock()
        mock_common.core = AsyncMock()
        mock_common.search = AsyncMock()
        mock_common.relationships = MagicMock()
        mock_common.intelligence = AsyncMock()
        mock_factory.return_value = mock_common

        service = KuService(backend=MagicMock(), graph_intel=MagicMock())
        return service, mock_common

    @pytest.mark.asyncio
    async def test_create_ku_delegates_to_core(self):
        service, common = self._make_service()
        common.core.create_ku.return_value = Result.ok(None)

        await service.create_ku(title="caffeine", namespace="body")

        common.core.create_ku.assert_awaited_once_with(
            title="caffeine",
            namespace="body",
            ku_category=None,
            aliases=None,
            source=None,
            description=None,
            summary=None,
            domain=None,
            tags=None,
        )

    @pytest.mark.asyncio
    async def test_get_ku_delegates_to_core(self):
        service, common = self._make_service()
        common.core.get_ku.return_value = Result.ok(None)

        await service.get_ku("ku_test_abc123")

        common.core.get_ku.assert_awaited_once_with("ku_test_abc123")

    @pytest.mark.asyncio
    async def test_search_delegates_to_search_service(self):
        service, common = self._make_service()
        common.search.search.return_value = Result.ok([])

        await service.search("caffeine")

        common.search.search.assert_awaited_once_with("caffeine", None)

    @pytest.mark.asyncio
    async def test_get_by_namespace_delegates_to_search_service(self):
        service, common = self._make_service()
        common.search.get_by_namespace.return_value = Result.ok([])

        await service.get_by_namespace("attention")

        common.search.get_by_namespace.assert_awaited_once_with("attention")


class TestKuServiceIntelligenceDelegation:
    """Verify intelligence delegation works correctly."""

    @patch("core.utils.curriculum_domain_config.create_curriculum_sub_services")
    def _make_service(self, mock_factory):
        from core.services.ku_service import KuService

        mock_common = MagicMock()
        mock_common.core = AsyncMock()
        mock_common.search = AsyncMock()
        mock_common.relationships = MagicMock()
        mock_common.intelligence = AsyncMock()
        mock_factory.return_value = mock_common

        service = KuService(backend=MagicMock(), graph_intel=MagicMock())
        return service, mock_common

    @pytest.mark.asyncio
    async def test_get_with_context_delegates(self):
        service, common = self._make_service()
        common.intelligence.get_with_context.return_value = Result.ok(("ku", "ctx"))

        await service.get_with_context("ku_test_abc123", depth=3)

        common.intelligence.get_with_context.assert_awaited_once_with(
            "ku_test_abc123", 3
        )

    @pytest.mark.asyncio
    async def test_get_usage_summary_delegates(self):
        service, common = self._make_service()
        common.intelligence.get_usage_summary.return_value = Result.ok(
            {"articles": 1, "learning_steps": 0, "organized_children": 0}
        )

        await service.get_usage_summary("ku_test_abc123")

        common.intelligence.get_usage_summary.assert_awaited_once_with("ku_test_abc123")
