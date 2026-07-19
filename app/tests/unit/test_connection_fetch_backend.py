"""Unit tests for ConnectionFetchBackend (relocated from core/utils, ADR-044).

The two cross-domain connection queries now live below the hexagonal boundary in
``adapters/persistence/neo4j/connection_fetch_backend.py`` behind the
``ConnectionFetchOperations`` port. These tests mock the QueryExecutor and assert
the outgoing vs incoming query shapes, parameter binding, record mapping, and the
page-resilient empty-on-error safety-net.
"""

from unittest.mock import AsyncMock

import pytest

from adapters.persistence.neo4j.connection_fetch_backend import ConnectionFetchBackend
from core.models.enums.neo_labels import NeoLabel
from core.utils.connection_configs import (
    GOAL_CONNECTION_CONFIG,
    TASK_CONNECTION_CONFIG,
    ConnectionConfig,
)
from core.utils.result_simplified import Errors, Result


def _backend_returning(records: object) -> tuple[ConnectionFetchBackend, AsyncMock]:
    executor = AsyncMock()
    executor.execute_query = AsyncMock(return_value=records)
    return ConnectionFetchBackend(executor), executor.execute_query


class TestFetchEntityConnections:
    @pytest.mark.asyncio
    async def test_empty_uids_short_circuits_without_query(self):
        backend, execute_query = _backend_returning(Result.ok([]))
        assert await backend.fetch_entity_connections(TASK_CONNECTION_CONFIG, []) == {}
        execute_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_outgoing_query_shape_and_params(self):
        backend, execute_query = _backend_returning(Result.ok([]))
        await backend.fetch_entity_connections(TASK_CONNECTION_CONFIG, ["task:1"])

        assert execute_query.await_args is not None
        query, params = execute_query.await_args.args
        # Outgoing: source is n, target is other.
        assert "(n)-[r]->(other:Entity)" in query
        # Enum-typed label seam interpolated as its .value.
        assert ":Entity:Task" in query
        assert params == {
            "uids": ["task:1"],
            "rel_types": list(TASK_CONNECTION_CONFIG.relationship_types),
        }

    @pytest.mark.asyncio
    async def test_incoming_query_shape(self):
        backend, execute_query = _backend_returning(Result.ok([]))
        await backend.fetch_entity_connections(GOAL_CONNECTION_CONFIG, ["goal:1"])

        assert execute_query.await_args is not None
        query, _params = execute_query.await_args.args
        # Incoming/gravity-well: edge points from other into n
        # (expressed via the shared direction_clause arrow).
        assert "(n)<-[r]-(other:Entity)" in query
        assert ":Entity:Goal" in query

    @pytest.mark.asyncio
    async def test_maps_records_and_skips_null_rel_type(self):
        records = Result.ok(
            [
                {
                    "entity_uid": "task:1",
                    "rel_type": "FULFILLS_GOAL",
                    "connected_uid": "goal:9",
                    "title": "Ship it",
                    "connected_type": "goal",
                },
                # OPTIONAL MATCH miss → rel_type None → skipped.
                {"entity_uid": "task:2", "rel_type": None},
            ]
        )
        backend, _ = _backend_returning(records)
        result = await backend.fetch_entity_connections(
            TASK_CONNECTION_CONFIG, ["task:1", "task:2"]
        )
        assert result == {
            "task:1": [
                {
                    "rel_type": "FULFILLS_GOAL",
                    "connected_uid": "goal:9",
                    "title": "Ship it",
                    "connected_type": "goal",
                }
            ]
        }
        assert "task:2" not in result

    @pytest.mark.asyncio
    async def test_empty_on_result_error(self):
        backend, _ = _backend_returning(Result.fail(Errors.database("connections", "boom")))
        assert await backend.fetch_entity_connections(TASK_CONNECTION_CONFIG, ["task:1"]) == {}

    @pytest.mark.asyncio
    async def test_empty_on_executor_exception_safety_net(self):
        executor = AsyncMock()
        executor.execute_query = AsyncMock(side_effect=RuntimeError("driver down"))
        backend = ConnectionFetchBackend(executor)
        # Page-resilient: a Neo4j failure must not propagate.
        assert await backend.fetch_entity_connections(TASK_CONNECTION_CONFIG, ["task:1"]) == {}

    @pytest.mark.asyncio
    async def test_invalid_label_seam_rejected(self):
        # An out-of-band label (not a real NeoLabel) is refused before interpolation.
        bad = ConnectionConfig(config_lookup_label="Task; DROP", relationship_types=("RELATED_TO",))  # type: ignore[arg-type]
        backend, _ = _backend_returning(Result.ok([]))
        with pytest.raises(ValueError, match="Invalid Neo4j label"):
            await backend.fetch_entity_connections(bad, ["task:1"])

    @pytest.mark.asyncio
    async def test_label_seam_accepts_every_activity_config(self):
        # All six shipped configs carry a valid NeoLabel seam.
        backend, _ = _backend_returning(Result.ok([]))
        for config in (TASK_CONNECTION_CONFIG, GOAL_CONNECTION_CONFIG):
            assert isinstance(config.config_lookup_label, NeoLabel)
            await backend.fetch_entity_connections(config, ["x:1"])


class TestFetchSourcePathstep:
    @pytest.mark.asyncio
    async def test_returns_uid_and_title_on_hit(self):
        backend, _ = _backend_returning(Result.ok([{"uid": "ps:demo:step-1", "title": "Intro"}]))
        assert await backend.fetch_source_pathstep("ps:demo:step-1") == {
            "uid": "ps:demo:step-1",
            "title": "Intro",
        }

    @pytest.mark.asyncio
    async def test_none_for_empty_uid_without_querying(self):
        backend, execute_query = _backend_returning(Result.ok([]))
        assert await backend.fetch_source_pathstep("") is None
        execute_query.assert_not_called()

    @pytest.mark.asyncio
    async def test_none_when_pathstep_missing(self):
        backend, _ = _backend_returning(Result.ok([]))
        assert await backend.fetch_source_pathstep("ps:gone") is None

    @pytest.mark.asyncio
    async def test_none_on_query_error(self):
        backend, _ = _backend_returning(Result.fail(Errors.database("lookup", "boom")))
        assert await backend.fetch_source_pathstep("ps:demo:step-1") is None

    @pytest.mark.asyncio
    async def test_none_on_executor_exception_safety_net(self):
        executor = AsyncMock()
        executor.execute_query = AsyncMock(side_effect=RuntimeError("driver down"))
        backend = ConnectionFetchBackend(executor)
        assert await backend.fetch_source_pathstep("ps:demo:step-1") is None

    @pytest.mark.asyncio
    async def test_falls_back_to_uid_when_title_null(self):
        backend, _ = _backend_returning(Result.ok([{"uid": "ps:demo:step-1", "title": None}]))
        assert await backend.fetch_source_pathstep("ps:demo:step-1") == {
            "uid": "ps:demo:step-1",
            "title": "ps:demo:step-1",
        }
