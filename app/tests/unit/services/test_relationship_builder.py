"""The fluent relationship builder — behaviour and the guarantees it claims.

The type-level guarantees (cannot omit a step, cannot swap source and target,
cannot pass a string edge type) are enforced by mypy and cannot be asserted at
runtime — a test that tried would have to write the very code mypy rejects.
They are verified in the PR by a probe file; what is tested here is that the
builder delegates exactly once, with exactly the values it was given.
"""

from unittest.mock import AsyncMock

import pytest

from core.models.relationship_names import RelationshipName
from core.services.relationship_builder import relate
from core.utils.result_simplified import Result


@pytest.fixture
def backend() -> AsyncMock:
    b = AsyncMock()
    b.add_relationship = AsyncMock(return_value=Result.ok(True))
    return b


@pytest.mark.asyncio
async def test_delegates_once_with_the_values_given(backend: AsyncMock) -> None:
    result = await (
        relate(backend, "task.1").via(RelationshipName.FULFILLS_GOAL).to("goal.1").create()
    )

    assert result.is_ok
    backend.add_relationship.assert_awaited_once_with(
        from_uid="task.1",
        to_uid="goal.1",
        relationship_type=RelationshipName.FULFILLS_GOAL,
        properties=None,
    )


@pytest.mark.asyncio
async def test_source_and_target_reach_the_backend_in_that_order(backend: AsyncMock) -> None:
    """The whole point: `from` is the source, `to` is the target, never reversed."""
    await relate(backend, "source.uid").via(RelationshipName.OWNS).to("target.uid").create()

    kwargs = backend.add_relationship.await_args.kwargs
    assert kwargs["from_uid"] == "source.uid"
    assert kwargs["to_uid"] == "target.uid"


@pytest.mark.asyncio
async def test_properties_merge_and_later_keys_win(backend: AsyncMock) -> None:
    await (
        relate(backend, "a")
        .via(RelationshipName.OWNS)
        .to("b")
        .with_properties(confidence=0.5, note="first")
        .with_properties(confidence=0.9)
        .create()
    )

    assert backend.add_relationship.await_args.kwargs["properties"] == {
        "confidence": 0.9,
        "note": "first",
    }


@pytest.mark.asyncio
async def test_no_properties_passes_none_not_an_empty_dict(backend: AsyncMock) -> None:
    """`{}` and None are different to a MERGE that SETs properties."""
    await relate(backend, "a").via(RelationshipName.OWNS).to("b").create()

    assert backend.add_relationship.await_args.kwargs["properties"] is None


@pytest.mark.asyncio
async def test_backend_failure_propagates_unchanged(backend: AsyncMock) -> None:
    """The builder adds no logic — including no error handling of its own."""
    from core.utils.result_simplified import Errors

    backend.add_relationship.return_value = Result.fail(Errors.database("add", "boom"))

    result = await relate(backend, "a").via(RelationshipName.OWNS).to("b").create()

    assert result.is_error
    assert "boom" in result.expect_error().message
