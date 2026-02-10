"""
Tests for UniversalNeo4jBackend default_filters feature.

Verifies that ``default_filters`` parameter correctly:
1. Injects WHERE clauses into all query methods
2. Auto-sets properties on newly created nodes
3. Prevents overwriting filter properties via update()
4. Has no effect when empty (backward compatibility)
"""

from dataclasses import dataclass
from datetime import datetime
from unittest.mock import AsyncMock, Mock, call

import pytest

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend


# ============================================================================
# FIXTURES
# ============================================================================


@dataclass(frozen=True)
class SampleKu:
    """Minimal domain model for testing default_filters."""

    uid: str
    title: str
    ku_type: str = "task"
    status: str = "active"
    created_at: str = "2026-01-01T00:00:00"
    description: str | None = None
    user_uid: str | None = None


def _mock_driver() -> Mock:
    """Create a mock Neo4j driver with async session."""
    driver = Mock()
    driver._closed = False  # Prevent _is_driver_closed() from short-circuiting
    session = AsyncMock()
    ctx = AsyncMock()
    ctx.__aenter__.return_value = session
    ctx.__aexit__.return_value = None
    driver.session.return_value = ctx
    return driver, session


def _backend_with_filters(
    driver: Mock, filters: dict | None = None
) -> UniversalNeo4jBackend[SampleKu]:
    return UniversalNeo4jBackend[SampleKu](
        driver=driver,
        label="Ku",
        entity_class=SampleKu,
        validate_label=False,
        default_filters=filters,
    )


# ============================================================================
# CONSTRUCTOR / HELPER TESTS
# ============================================================================


class TestDefaultFiltersConstructor:
    """Constructor and helper method tests."""

    def test_default_filters_stored(self):
        driver, _ = _mock_driver()
        backend = _backend_with_filters(driver, {"ku_type": "task"})
        assert backend.default_filters == {"ku_type": "task"}

    def test_default_filters_none_becomes_empty(self):
        driver, _ = _mock_driver()
        backend = _backend_with_filters(driver, None)
        assert backend.default_filters == {}

    def test_default_filters_omitted_becomes_empty(self):
        driver, _ = _mock_driver()
        backend = UniversalNeo4jBackend[SampleKu](
            driver=driver, label="Ku", entity_class=SampleKu, validate_label=False
        )
        assert backend.default_filters == {}

    def test_filter_clause_with_filters(self):
        driver, _ = _mock_driver()
        backend = _backend_with_filters(driver, {"ku_type": "task"})
        assert backend._default_filter_clause() == "n.ku_type = $_df_ku_type"

    def test_filter_clause_custom_node_var(self):
        driver, _ = _mock_driver()
        backend = _backend_with_filters(driver, {"ku_type": "task"})
        assert backend._default_filter_clause("e") == "e.ku_type = $_df_ku_type"

    def test_filter_clause_empty(self):
        driver, _ = _mock_driver()
        backend = _backend_with_filters(driver, None)
        assert backend._default_filter_clause() == ""

    def test_filter_params(self):
        driver, _ = _mock_driver()
        backend = _backend_with_filters(driver, {"ku_type": "task"})
        assert backend._default_filter_params() == {"_df_ku_type": "task"}

    def test_filter_params_empty(self):
        driver, _ = _mock_driver()
        backend = _backend_with_filters(driver, None)
        assert backend._default_filter_params() == {}

    def test_inject_default_filters(self):
        driver, _ = _mock_driver()
        backend = _backend_with_filters(driver, {"ku_type": "task", "status": "active"})
        clauses: list[str] = []
        params: dict = {}
        backend._inject_default_filters(clauses, params, "e")
        assert "e.ku_type = $_df_ku_type" in clauses
        assert "e.status = $_df_status" in clauses
        assert params == {"_df_ku_type": "task", "_df_status": "active"}

    def test_inject_default_filters_noop_when_empty(self):
        driver, _ = _mock_driver()
        backend = _backend_with_filters(driver, None)
        clauses: list[str] = ["existing"]
        params: dict = {"existing_key": 1}
        backend._inject_default_filters(clauses, params)
        assert clauses == ["existing"]
        assert params == {"existing_key": 1}

    def test_multiple_filters_clause(self):
        driver, _ = _mock_driver()
        backend = _backend_with_filters(driver, {"ku_type": "task", "visibility": "private"})
        clause = backend._default_filter_clause()
        assert "n.ku_type = $_df_ku_type" in clause
        assert "n.visibility = $_df_visibility" in clause
        assert " AND " in clause


# ============================================================================
# CREATE TESTS
# ============================================================================


class TestCreateWithDefaultFilters:
    """create() should auto-set default_filter properties on new nodes."""

    @pytest.mark.asyncio
    async def test_create_sets_filter_properties(self):
        driver, session = _mock_driver()
        backend = _backend_with_filters(driver, {"ku_type": "task"})

        # Mock successful create
        mock_result = AsyncMock()
        mock_record = {
            "n": {
                "uid": "ku_test_abc",
                "title": "Test",
                "ku_type": "task",
                "status": "active",
                "created_at": "2026-01-01T00:00:00",
            }
        }
        mock_result.single.return_value = mock_record
        session.run.return_value = mock_result

        entity = SampleKu(uid="ku_test_abc", title="Test")
        result = await backend.create(entity)

        # Verify ku_type was in the props passed to Neo4j
        call_args = session.run.call_args
        props = call_args[1]["props"] if "props" in call_args[1] else call_args[0][1]["props"]
        assert props["ku_type"] == "task"


# ============================================================================
# GET TESTS
# ============================================================================


class TestGetWithDefaultFilters:
    """get() should add WHERE clause for default_filters."""

    @pytest.mark.asyncio
    async def test_get_includes_filter_in_query(self):
        driver, session = _mock_driver()
        backend = _backend_with_filters(driver, {"ku_type": "task"})

        mock_result = AsyncMock()
        mock_result.single.return_value = None
        session.run.return_value = mock_result

        await backend.get("ku_test_abc")

        call_args = session.run.call_args
        query = call_args[0][0]
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]

        assert "n.ku_type = $_df_ku_type" in query
        assert params["_df_ku_type"] == "task"
        assert params["uid"] == "ku_test_abc"

    @pytest.mark.asyncio
    async def test_get_no_filter_when_empty(self):
        driver, session = _mock_driver()
        backend = _backend_with_filters(driver, None)

        mock_result = AsyncMock()
        mock_result.single.return_value = None
        session.run.return_value = mock_result

        await backend.get("ku_test_abc")

        call_args = session.run.call_args
        query = call_args[0][0]
        assert "_df_" not in query
        assert "WHERE" not in query


# ============================================================================
# GET_MANY TESTS
# ============================================================================


class TestGetManyWithDefaultFilters:
    """get_many() should add default_filter conditions to WHERE clause."""

    @pytest.mark.asyncio
    async def test_get_many_includes_filter(self):
        driver, session = _mock_driver()
        backend = _backend_with_filters(driver, {"ku_type": "task"})

        mock_result = AsyncMock()
        mock_result.data.return_value = []
        session.run.return_value = mock_result

        await backend.get_many(["uid1", "uid2"])

        call_args = session.run.call_args
        query = call_args[0][0]
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]

        assert "n.uid IN $uids" in query
        assert "n.ku_type = $_df_ku_type" in query
        assert params["_df_ku_type"] == "task"
        assert params["uids"] == ["uid1", "uid2"]


# ============================================================================
# UPDATE TESTS
# ============================================================================


class TestUpdateWithDefaultFilters:
    """update() should add WHERE clause and prevent overwriting filter properties."""

    @pytest.mark.asyncio
    async def test_update_includes_filter_in_query(self):
        driver, session = _mock_driver()
        backend = _backend_with_filters(driver, {"ku_type": "task"})

        mock_result = AsyncMock()
        mock_result.single.return_value = {
            "n": {
                "uid": "ku_test_abc",
                "title": "Updated",
                "ku_type": "task",
                "status": "active",
                "created_at": "2026-01-01T00:00:00",
            }
        }
        session.run.return_value = mock_result

        await backend.update("ku_test_abc", {"title": "Updated"})

        call_args = session.run.call_args
        query = call_args[0][0]
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]

        assert "n.ku_type = $_df_ku_type" in query
        assert params["_df_ku_type"] == "task"

    @pytest.mark.asyncio
    async def test_update_strips_filter_properties_from_updates(self):
        """Prevent callers from overwriting ku_type via update()."""
        driver, session = _mock_driver()
        backend = _backend_with_filters(driver, {"ku_type": "task"})

        mock_result = AsyncMock()
        mock_result.single.return_value = {
            "n": {
                "uid": "ku_test_abc",
                "title": "Updated",
                "ku_type": "task",
                "status": "active",
                "created_at": "2026-01-01T00:00:00",
            }
        }
        session.run.return_value = mock_result

        # Try to sneak ku_type into updates
        await backend.update("ku_test_abc", {"title": "Updated", "ku_type": "goal"})

        call_args = session.run.call_args
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]

        # ku_type should have been stripped from the updates dict
        assert "ku_type" not in params["updates"]
        assert params["updates"]["title"] == "Updated"


# ============================================================================
# DELETE TESTS
# ============================================================================


class TestDeleteWithDefaultFilters:
    """delete() should add WHERE clause for default_filters."""

    @pytest.mark.asyncio
    async def test_delete_includes_filter_in_query(self):
        driver, session = _mock_driver()
        backend = _backend_with_filters(driver, {"ku_type": "task"})

        mock_result = AsyncMock()
        mock_summary = Mock()
        mock_summary.counters.nodes_deleted = 1
        mock_result.consume.return_value = mock_summary
        session.run.return_value = mock_result

        await backend.delete("ku_test_abc", cascade=True)

        call_args = session.run.call_args
        query = call_args[0][0]
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]

        assert "n.ku_type = $_df_ku_type" in query
        assert params["_df_ku_type"] == "task"


# ============================================================================
# SEARCH TESTS
# ============================================================================


class TestSearchWithDefaultFilters:
    """search() should add default_filter conditions to WHERE clause."""

    @pytest.mark.asyncio
    async def test_search_includes_filter(self):
        driver, session = _mock_driver()
        backend = _backend_with_filters(driver, {"ku_type": "task"})

        mock_result = AsyncMock()
        mock_result.data.return_value = []
        session.run.return_value = mock_result

        await backend.search("test query")

        call_args = session.run.call_args
        query = call_args[0][0]
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]

        assert "n.ku_type = $_df_ku_type" in query
        assert "CONTAINS" in query
        assert params["_df_ku_type"] == "task"

    @pytest.mark.asyncio
    async def test_search_no_filter_when_empty(self):
        driver, session = _mock_driver()
        backend = _backend_with_filters(driver, None)

        mock_result = AsyncMock()
        mock_result.data.return_value = []
        session.run.return_value = mock_result

        await backend.search("test query")

        call_args = session.run.call_args
        query = call_args[0][0]
        assert "_df_" not in query


# ============================================================================
# BACKWARD COMPATIBILITY TESTS
# ============================================================================


class TestBackwardCompatibility:
    """No default_filters = no behavior change."""

    def test_no_filters_no_clause(self):
        driver, _ = _mock_driver()
        backend = _backend_with_filters(driver, None)
        assert backend._default_filter_clause() == ""
        assert backend._default_filter_params() == {}

    @pytest.mark.asyncio
    async def test_get_without_filters_no_where(self):
        driver, session = _mock_driver()
        backend = _backend_with_filters(driver, None)

        mock_result = AsyncMock()
        mock_result.single.return_value = None
        session.run.return_value = mock_result

        await backend.get("uid1")

        query = session.run.call_args[0][0]
        # Should have the basic MATCH without any WHERE
        assert "MATCH (n:Ku {uid: $uid})" in query
        assert "WHERE" not in query

    @pytest.mark.asyncio
    async def test_create_without_filters_no_extra_props(self):
        driver, session = _mock_driver()
        backend = _backend_with_filters(driver, None)

        mock_result = AsyncMock()
        mock_result.single.return_value = {
            "n": {
                "uid": "ku_test",
                "title": "Test",
                "ku_type": "task",
                "status": "active",
                "created_at": "2026-01-01T00:00:00",
            }
        }
        session.run.return_value = mock_result

        entity = SampleKu(uid="ku_test", title="Test")
        await backend.create(entity)

        # With no default_filters, the node_data should come straight from to_neo4j_node
        # (no extra properties injected beyond what the entity already has)
        call_args = session.run.call_args
        props = call_args[0][1]["props"] if len(call_args[0]) > 1 else call_args[1]["props"]
        # ku_type should still be "task" because it comes from the entity default
        assert props["ku_type"] == "task"
