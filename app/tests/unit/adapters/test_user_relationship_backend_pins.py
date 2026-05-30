"""Unit tests for UserRelationshipBackend pin/unpin Result shape.

Regression guard for the double-wrapped ``Result[Result[bool]]`` bug (arg-type
AD-6). The pin/unpin processors previously returned ``Result[bool]`` while the
executor *also* wrapped the processor output in ``Result.ok(...)``, so a
``not_found`` failure ended up as the ``.value`` of an outer ``ok`` Result —
callers checking ``.is_error`` never saw it (e.g. unpinning a non-existent pin
reported success).

These tests assert:
- success path: ``result.value`` is a plain ``bool`` (NOT a nested ``Result``)
- empty-records path: ``result.is_error is True`` with a NotFound error
"""

from unittest.mock import AsyncMock

import pytest

from adapters.persistence.neo4j.user_relationship_backend import UserRelationshipBackend
from core.utils.result_simplified import Result


def _executor_returning(records: list[dict[str, object]]) -> AsyncMock:
    """Build a mock executor whose ``execute`` faithfully mirrors the real
    contract: apply the given ``processor`` to ``records`` and wrap in
    ``Result.ok`` (matching ``Neo4jQueryExecutor.execute``).

    The pin/unpin ``operation`` under test receives ``records``; the incidental
    ``get_pinned_entities`` lookup that ``pin_entity`` performs first is fed an
    empty list so its ``extract_uids_list`` processor stays happy.
    """
    executor = AsyncMock()

    async def fake_execute(*, query, params, processor, operation):
        served = records if operation != "get_pinned_entities" else []
        return Result.ok(processor(served))

    executor.execute = AsyncMock(side_effect=fake_execute)
    return executor


@pytest.mark.asyncio
async def test_pin_entity_success_returns_plain_bool() -> None:
    """A successful pin returns ``Result.ok(True)`` — value is a bare bool."""
    executor = _executor_returning([{"success": True}])
    backend = UserRelationshipBackend(executor)

    result = await backend.pin_entity("user_alice", "task_1")

    assert result.is_error is False
    assert result.value is True
    assert not isinstance(result.value, Result), "double-wrapped Result regression"


@pytest.mark.asyncio
async def test_unpin_entity_empty_records_is_error() -> None:
    """Unpinning a non-existent pin surfaces a NotFound error, not a false ok."""
    executor = _executor_returning([])
    backend = UserRelationshipBackend(executor)

    result = await backend.unpin_entity("user_alice", "task_missing")

    assert result.is_error is True
    error = result.expect_error()
    assert "Pin not found" in error.message


@pytest.mark.asyncio
async def test_unpin_entity_success_returns_plain_bool() -> None:
    """A successful unpin returns ``Result.ok(True)`` — value is a bare bool."""
    executor = _executor_returning([{"success": True}])
    backend = UserRelationshipBackend(executor)

    result = await backend.unpin_entity("user_alice", "task_1")

    assert result.is_error is False
    assert result.value is True
    assert not isinstance(result.value, Result), "double-wrapped Result regression"
