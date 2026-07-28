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

    @patch("core.services.curriculum_domain_config.create_curriculum_sub_services")
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
            backend=backend,
            graph_intel=graph_intel,
            event_bus=event_bus,
        )
        assert service.core is mock_common.core
        assert service.search is mock_common.search
        assert service.relationships is mock_common.relationships
        assert service.intelligence is mock_common.intelligence
        assert service.backend is backend


class TestKuServiceDelegation:
    """Verify CRUD/search delegation works correctly."""

    @patch("core.services.curriculum_domain_config.create_curriculum_sub_services")
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

        await service.create_ku(title="caffeine", aliases=["coffee"])

        common.core.create_ku.assert_awaited_once_with(
            title="caffeine",
            aliases=["coffee"],
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

    def test_search_is_the_sub_service_not_a_method(self):
        """`.search` must be the sub-service ATTRIBUTE (PS pattern) —
        SearchRouter._get_search_service resolves it only when non-callable;
        a facade method here would shadow it with a divergent signature."""
        service, common = self._make_service()

        assert service.search is common.search

    @pytest.mark.asyncio
    async def test_search_by_alias_delegates_to_search_service(self):
        service, common = self._make_service()
        common.search.search_by_alias.return_value = Result.ok([])

        await service.search_by_alias("coffee")

        common.search.search_by_alias.assert_awaited_once_with("coffee")

    @pytest.mark.asyncio
    async def test_list_nous_topics_delegates_to_search_service(self):
        service, common = self._make_service()
        common.search.list_all_categories.return_value = Result.ok(["words", "stories"])

        result = await service.list_nous_topics()

        common.search.list_all_categories.assert_awaited_once_with()
        assert result.value == ["words", "stories"]


class TestKuServiceIntelligenceDelegation:
    """Verify intelligence delegation works correctly."""

    @patch("core.services.curriculum_domain_config.create_curriculum_sub_services")
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

        common.intelligence.get_with_context.assert_awaited_once_with("ku_test_abc123", 3)

    @pytest.mark.asyncio
    async def test_get_usage_summary_delegates(self):
        service, common = self._make_service()
        common.intelligence.get_usage_summary.return_value = Result.ok(
            {"path_steps_using": 1, "path_steps_training": 0, "organized_children": 0}
        )

        await service.get_usage_summary("ku_test_abc123")

        common.intelligence.get_usage_summary.assert_awaited_once_with("ku_test_abc123")
