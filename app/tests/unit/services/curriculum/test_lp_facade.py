"""
Unit tests for LpService facade orchestration methods.

Tests focus on:
- ls_service guard (create_step/get_step etc. return fail when ls_service is None)
- list() filtering: user_uid routing, sorting, pagination
- create() keyword assembly from entity fields

NOT tested: pure delegation methods (*args/**kwargs).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from core.services.lp_service import LpService
from core.utils.result_simplified import Errors, Result


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
def mock_executor() -> Mock:
    executor = AsyncMock()
    return executor


@pytest.fixture
def mock_ls_service() -> Mock:
    return Mock()


@pytest.fixture
def mock_graph_intel() -> Mock:
    return Mock()


@pytest.fixture
def lp_service(
    mock_backend: Mock,
    mock_executor: Mock,
    mock_ls_service: Mock,
    mock_graph_intel: Mock,
) -> LpService:
    service = LpService(
        backend=mock_backend,
        executor=mock_executor,
        ls_service=mock_ls_service,
        graph_intelligence_service=mock_graph_intel,
    )
    # Replace sub-services with AsyncMocks AFTER construction
    service.core = AsyncMock()
    service.search = AsyncMock()
    service.relationships = AsyncMock()
    service.intelligence = AsyncMock()
    service.progress = AsyncMock()
    service.ls_service = mock_ls_service
    return service


# ---------------------------------------------------------------------------
# TestLpServiceLsServiceGuard
# ---------------------------------------------------------------------------


class TestLpServiceLsServiceGuard:
    @pytest.mark.asyncio
    async def test_create_step_fails_when_ls_service_is_none(
        self, lp_service: LpService
    ) -> None:
        """create_step returns fail when ls_service is None."""
        lp_service.ls_service = None

        result = await lp_service.create_step(Mock())

        assert result.is_error

    @pytest.mark.asyncio
    async def test_get_step_fails_when_ls_service_is_none(
        self, lp_service: LpService
    ) -> None:
        """get_step returns fail when ls_service is None."""
        lp_service.ls_service = None

        result = await lp_service.get_step("ls_abc")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_delete_step_fails_when_ls_service_is_none(
        self, lp_service: LpService
    ) -> None:
        """delete_step returns fail when ls_service is None."""
        lp_service.ls_service = None

        result = await lp_service.delete_step("ls_abc")

        assert result.is_error

    @pytest.mark.asyncio
    async def test_list_steps_fails_when_ls_service_is_none(
        self, lp_service: LpService
    ) -> None:
        """list_steps returns fail when ls_service is None."""
        lp_service.ls_service = None

        result = await lp_service.list_steps()

        assert result.is_error

    @pytest.mark.asyncio
    async def test_create_step_delegates_to_ls_service_when_available(
        self, lp_service: LpService, mock_ls_service: Mock
    ) -> None:
        """create_step delegates to ls_service.create_step when available."""
        mock_step = Mock()
        mock_ls_service.create_step = AsyncMock(return_value=Result.ok(mock_step))
        mock_path_uid = "lp_path_abc"

        result = await lp_service.create_step(mock_step, mock_path_uid)

        assert result.is_ok
        mock_ls_service.create_step.assert_called_once_with(mock_step, mock_path_uid)


# ---------------------------------------------------------------------------
# TestLpServiceList
# ---------------------------------------------------------------------------


class TestLpServiceList:
    @pytest.mark.asyncio
    async def test_list_with_user_uid_calls_list_user_paths(
        self, lp_service: LpService
    ) -> None:
        """list() with user_uid routes to core.list_user_paths."""
        mock_path = Mock()
        lp_service.core.list_user_paths = AsyncMock(return_value=Result.ok([mock_path]))

        result = await lp_service.list(user_uid="user_alice", limit=10)

        assert result.is_ok
        lp_service.core.list_user_paths.assert_called_once_with("user_alice", 10)
        lp_service.core.list_all_paths.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_without_user_uid_calls_list_all_paths(
        self, lp_service: LpService
    ) -> None:
        """list() without user_uid routes to core.list_all_paths."""
        lp_service.core.list_all_paths = AsyncMock(return_value=Result.ok([]))

        result = await lp_service.list(limit=5)

        assert result.is_ok
        lp_service.core.list_all_paths.assert_called_once()
        lp_service.core.list_user_paths.assert_not_called()

    @pytest.mark.asyncio
    async def test_list_with_order_by_sorts_result(
        self, lp_service: LpService
    ) -> None:
        """list() with order_by sorts paths by the specified attribute."""
        path_b = SimpleNamespace(title="Beta", uid="lp_b")
        path_a = SimpleNamespace(title="Alpha", uid="lp_a")
        lp_service.core.list_all_paths = AsyncMock(
            return_value=Result.ok([path_b, path_a])
        )

        result = await lp_service.list(order_by="title")

        assert result.is_ok
        # Alpha sorts before Beta
        assert result.value[0].uid == "lp_a"
        assert result.value[1].uid == "lp_b"

    @pytest.mark.asyncio
    async def test_list_with_order_desc_reverses_sort(
        self, lp_service: LpService
    ) -> None:
        """list() with order_desc=True produces descending order."""
        path_a = SimpleNamespace(title="Alpha", uid="lp_a")
        path_b = SimpleNamespace(title="Beta", uid="lp_b")
        lp_service.core.list_all_paths = AsyncMock(
            return_value=Result.ok([path_a, path_b])
        )

        result = await lp_service.list(order_by="title", order_desc=True)

        assert result.is_ok
        assert result.value[0].uid == "lp_b"  # Beta first when descending

    @pytest.mark.asyncio
    async def test_list_with_offset_skips_leading_items(
        self, lp_service: LpService
    ) -> None:
        """list() with offset skips the first N items from the result."""
        path_1 = SimpleNamespace(title="Path1", uid="lp_1")
        path_2 = SimpleNamespace(title="Path2", uid="lp_2")
        path_3 = SimpleNamespace(title="Path3", uid="lp_3")
        lp_service.core.list_all_paths = AsyncMock(
            return_value=Result.ok([path_1, path_2, path_3])
        )

        result = await lp_service.list(limit=10, offset=1)

        assert result.is_ok
        assert len(result.value) == 2
        assert result.value[0].uid == "lp_2"

    @pytest.mark.asyncio
    async def test_list_propagates_backend_error(
        self, lp_service: LpService
    ) -> None:
        """list() propagates failure from core.list_all_paths."""
        lp_service.core.list_all_paths = AsyncMock(
            return_value=Result.fail(Errors.database("list", "DB error"))
        )

        result = await lp_service.list()

        assert result.is_error


# ---------------------------------------------------------------------------
# TestLpServiceCreate
# ---------------------------------------------------------------------------


class TestLpServiceCreate:
    @pytest.mark.asyncio
    async def test_create_assembles_kwargs_from_entity_fields(
        self, lp_service: LpService
    ) -> None:
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
