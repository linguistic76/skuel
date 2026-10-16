# mypy: disable-error-code="assignment,attr-defined"
"""
Unit tests for LpService facade orchestration methods.

Tests focus on the ps_service guard (get_step/list_steps return fail when
ps_service is None).

NOT tested: pure delegation methods (*args/**kwargs).
"""

from unittest.mock import AsyncMock, Mock

import pytest

from core.services.lp_service import LpService
from core.utils.result_simplified import Result

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_backend() -> Mock:
    backend = Mock()
    backend.create = AsyncMock(return_value=Result.ok({}))
    backend.get = AsyncMock(return_value=Result.ok(None))
    backend.list = AsyncMock(return_value=Result.ok(([], 0)))
    return backend


@pytest.fixture
def mock_ps_service() -> Mock:
    return Mock()


@pytest.fixture
def mock_graph_intel() -> Mock:
    return Mock()


@pytest.fixture
def lp_service(
    mock_backend: Mock,
    mock_ps_service: Mock,
    mock_graph_intel: Mock,
) -> LpService:
    service = LpService(
        backend=mock_backend,
        ps_service=mock_ps_service,
        graph_intel=mock_graph_intel,
    )
    # Replace sub-services with AsyncMocks AFTER construction
    service.core = AsyncMock()
    service.search = AsyncMock()
    service.relationships = AsyncMock()
    service.intelligence = AsyncMock()
    service.progress = AsyncMock()
    service.ps_service = mock_ps_service
    return service


# ---------------------------------------------------------------------------
# TestLpServicePsServiceGuard
# ---------------------------------------------------------------------------


class TestLpServicePsServiceGuard:
    @pytest.mark.asyncio
    async def test_get_step_fails_when_ps_service_is_none(self, lp_service: LpService) -> None:
        """get_step returns fail when ps_service is None."""
        lp_service.ps_service = None

        result = await lp_service.get_step("ls_abc")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_list_steps_fails_when_ps_service_is_none(self, lp_service: LpService) -> None:
        """list_steps returns fail when ps_service is None."""
        lp_service.ps_service = None

        result = await lp_service.list_steps()

        assert result.is_error


# ---------------------------------------------------------------------------
# TestLpServiceCreate
# ---------------------------------------------------------------------------
