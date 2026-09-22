# mypy: disable-error-code="assignment,attr-defined"
"""
Unit tests for LpService facade orchestration methods.

Tests focus on:
- ps_service guard (create_step/get_step etc. return fail when ps_service is None)
- create() keyword assembly from entity fields

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
    async def test_create_step_fails_when_ps_service_is_none(self, lp_service: LpService) -> None:
        """create_step returns fail when ps_service is None."""
        lp_service.ps_service = None

        result = await lp_service.create_step(Mock())

        assert result.is_error

    @pytest.mark.asyncio
    async def test_get_step_fails_when_ps_service_is_none(self, lp_service: LpService) -> None:
        """get_step returns fail when ps_service is None."""
        lp_service.ps_service = None

        result = await lp_service.get_step("ls_abc")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_delete_step_fails_when_ps_service_is_none(self, lp_service: LpService) -> None:
        """delete_step returns fail when ps_service is None."""
        lp_service.ps_service = None

        result = await lp_service.delete_step("ls_abc")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_list_steps_fails_when_ps_service_is_none(self, lp_service: LpService) -> None:
        """list_steps returns fail when ps_service is None."""
        lp_service.ps_service = None

        result = await lp_service.list_steps()

        assert result.is_error

    @pytest.mark.asyncio
    async def test_create_step_delegates_to_ps_service_when_available(
        self, lp_service: LpService, mock_ps_service: Mock
    ) -> None:
        """create_step delegates to ps_service.create_step when available."""
        mock_step = Mock()
        mock_ps_service.create_step = AsyncMock(return_value=Result.ok(mock_step))
        mock_path_uid = "lp_path_abc"

        result = await lp_service.create_step(mock_step, mock_path_uid)

        assert result.is_ok
        mock_ps_service.create_step.assert_called_once_with(mock_step, mock_path_uid)


# ---------------------------------------------------------------------------
# TestLpServiceCreate
# ---------------------------------------------------------------------------


class TestLpServiceCreate:
    @pytest.mark.asyncio
    async def test_create_assembles_kwargs_from_entity_fields(self, lp_service: LpService) -> None:
        """create() extracts user_uid, title, description, steps, and domain from entity."""
        entity = Mock()
        entity.user_uid = "user_admin"
        entity.title = "Python Fundamentals"
        entity.description = "Core Python concepts"
        entity.metadata = {"steps": ["ls_abc", "ls_def"]}
        entity.domain = "TECH"
        mock_path = Mock()
        lp_service.core.create_path = AsyncMock(return_value=Result.ok(mock_path))

        result = await lp_service.create(entity)

        assert result.is_ok
        lp_service.core.create_path.assert_called_once_with(
            user_uid="user_admin",
            title="Python Fundamentals",
            description="Core Python concepts",
            steps=["ls_abc", "ls_def"],
            domain="TECH",
        )

    @pytest.mark.asyncio
    async def test_create_uses_empty_steps_when_metadata_is_none(
        self, lp_service: LpService
    ) -> None:
        """create() uses empty steps list when entity.metadata is None."""
        entity = Mock()
        entity.user_uid = "user_admin"
        entity.title = "Path"
        entity.description = "Desc"
        entity.metadata = None
        entity.domain = "GENERAL"
        lp_service.core.create_path = AsyncMock(return_value=Result.ok(Mock()))

        await lp_service.create(entity)

        call_kwargs = lp_service.core.create_path.call_args.kwargs
        assert call_kwargs["steps"] == []
