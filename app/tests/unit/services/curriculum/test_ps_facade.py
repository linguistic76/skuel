"""
Unit tests for PsService facade orchestration methods.

Tests focus on attach_step_to_path (sequence auto-calculation logic)
and relationship delegation — NOT pure CRUD delegation methods.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from core.services.ps_service import PsService
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
    backend.get_next_step_sequence = AsyncMock(return_value=Result.ok(0))
    return backend


@pytest.fixture
def mock_executor() -> Mock:
    executor = AsyncMock()
    executor.execute_query = AsyncMock(return_value=Result.ok([{"next_sequence": 0}]))
    executor.get_next_step_sequence = AsyncMock(return_value=Result.ok(0))
    return executor


@pytest.fixture
def mock_graph_intel() -> Mock:
    return Mock()


@pytest.fixture
def ps_service(mock_backend: Mock, mock_executor: Mock, mock_graph_intel: Mock) -> PsService:
    service = PsService(
        backend=mock_backend,
        executor=mock_executor,
        graph_intel=mock_graph_intel,
        event_bus=None,
    )
    # Replace sub-services with AsyncMocks AFTER construction
    service.core = AsyncMock()
    service.search = AsyncMock()
    service.relationships = AsyncMock()
    service.intelligence = AsyncMock()
    service.executor = mock_executor
    return service


# ---------------------------------------------------------------------------
# TestPsServiceAttachStep
# ---------------------------------------------------------------------------


class TestPsServiceAttachStep:
    @pytest.mark.asyncio
    async def test_attach_with_explicit_sequence_skips_sequence_query(
        self, ps_service: PsService, mock_backend: Mock
    ) -> None:
        """attach_step_to_path with an explicit sequence skips the sequence query."""
        ps_service.relationships.create_relationship_with_properties = AsyncMock(
            return_value=Result.ok(True)
        )

        await ps_service.attach_step_to_path("ls_step_abc", "lp_path_xyz", sequence=3)

        mock_backend.get_next_step_sequence.assert_not_called()
        ps_service.relationships.create_relationship_with_properties.assert_called_once_with(
            relationship_key="in_paths",
            from_uid="ls_step_abc",
            to_uid="lp_path_xyz",
            edge_properties={"sequence": 3, "completed": False},
        )

    @pytest.mark.asyncio
    async def test_attach_without_sequence_queries_backend_for_next(
        self, ps_service: PsService, mock_backend: Mock
    ) -> None:
        """attach_step_to_path without sequence queries backend to determine next_sequence."""
        mock_backend.get_next_step_sequence.return_value = Result.ok(5)
        ps_service.relationships.create_relationship_with_properties = AsyncMock(
            return_value=Result.ok(True)
        )

        await ps_service.attach_step_to_path("ls_step_abc", "lp_path_xyz")

        mock_backend.get_next_step_sequence.assert_called_once_with("lp_path_xyz")
        call_args = ps_service.relationships.create_relationship_with_properties.call_args
        assert call_args.kwargs["edge_properties"]["sequence"] == 5

    @pytest.mark.asyncio
    async def test_attach_falls_back_to_zero_when_backend_returns_error(
        self, ps_service: PsService, mock_backend: Mock
    ) -> None:
        """attach_step_to_path uses sequence=0 when backend query fails."""
        mock_backend.get_next_step_sequence.return_value = Result.fail(
            Errors.database("get_next_step_sequence", "DB error")
        )
        ps_service.relationships.create_relationship_with_properties = AsyncMock(
            return_value=Result.ok(True)
        )

        await ps_service.attach_step_to_path("ls_step_abc", "lp_path_xyz")

        call_args = ps_service.relationships.create_relationship_with_properties.call_args
        assert call_args.kwargs["edge_properties"]["sequence"] == 0

    @pytest.mark.asyncio
    async def test_attach_uses_backend_sequence_value_of_zero(
        self, ps_service: PsService, mock_backend: Mock
    ) -> None:
        """attach_step_to_path uses sequence=0 when backend returns 0 (first step)."""
        mock_backend.get_next_step_sequence.return_value = Result.ok(0)
        ps_service.relationships.create_relationship_with_properties = AsyncMock(
            return_value=Result.ok(True)
        )

        await ps_service.attach_step_to_path("ls_step_abc", "lp_path_xyz")

        call_args = ps_service.relationships.create_relationship_with_properties.call_args
        assert call_args.kwargs["edge_properties"]["sequence"] == 0


# ---------------------------------------------------------------------------
# TestPsServiceDetachAndGetPaths
# ---------------------------------------------------------------------------


class TestPsServiceDetachAndGetPaths:
    @pytest.mark.asyncio
    async def test_detach_step_delegates_to_relationships(self, ps_service: PsService) -> None:
        """detach_step_from_path delegates to relationships.delete_relationship."""
        ps_service.relationships.delete_relationship = AsyncMock(return_value=Result.ok(True))

        result = await ps_service.detach_step_from_path("ls_step_abc", "lp_path_xyz")

        assert result.is_ok
        ps_service.relationships.delete_relationship.assert_called_once_with(
            relationship_key="in_paths",
            from_uid="ls_step_abc",
            to_uid="lp_path_xyz",
        )

    @pytest.mark.asyncio
    async def test_detach_step_propagates_relationships_failure(
        self, ps_service: PsService
    ) -> None:
        """detach_step_from_path propagates failure from relationships sub-service."""
        ps_service.relationships.delete_relationship = AsyncMock(
            return_value=Result.fail(Errors.database("delete", "DB error"))
        )

        result = await ps_service.detach_step_from_path("ls_step_abc", "lp_path_xyz")

        assert result.is_error
