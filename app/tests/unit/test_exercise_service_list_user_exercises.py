"""The teacher's own exercise list reads the mapped owner door.

`ExerciseService.list_user_exercises` backs `/exercises/content`, the page that
carries each exercise's Delete button. It reads the owner read
(`backend.get_user_entities`), whose adapter maps every node with
`from_neo4j_node` (the mapper half, embedded nodes included, is pinned in
`tests/unit/adapters/test_domain_query_node_mapping.py`) — so a failed read
stays a failure, and a list longer than one bulk page is read whole.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from core.constants import QueryLimit
from core.models.enums.entity_enums import EntityType
from core.models.enums.user_entry_enums import ExerciseScope
from core.models.exercises.exercise import Exercise
from core.services.exercises.exercise_service import ExerciseService
from core.utils.result_simplified import Errors, Result

OWNER = "user_teacher"


def _exercise(uid: str, scope: ExerciseScope = ExerciseScope.ASSIGNED) -> Exercise:
    return Exercise(
        uid=uid,
        entity_type=EntityType.EXERCISE,
        title=f"Exercise {uid}",
        instructions="Write one paragraph.",
        scope=scope,
        owner_uid=OWNER,
    )


def _service(get_user_entities: AsyncMock) -> ExerciseService:
    backend = MagicMock()
    backend.get_user_entities = get_user_entities
    return ExerciseService(backend=backend)


async def test_reads_the_owner_door_newest_first_and_returns_the_page() -> None:
    page = [_exercise("ex_1"), _exercise("ex_2")]
    read = AsyncMock(return_value=Result.ok((page, 2)))
    service = _service(read)

    result = await service.list_user_exercises(OWNER)

    assert result.is_ok
    assert result.value == page  # the page, never the (page, total) tuple
    read.assert_awaited_once()
    assert read.await_args is not None
    assert read.await_args.args == (OWNER,)
    kwargs = read.await_args.kwargs
    assert kwargs["sort_by"] == "created_at"
    assert kwargs["sort_order"] == "desc"
    assert kwargs["limit"] == QueryLimit.BULK


async def test_a_failed_read_is_a_failure_not_an_empty_list() -> None:
    read = AsyncMock(return_value=Result.fail(Errors.database(operation="list", message="boom")))
    service = _service(read)

    result = await service.list_user_exercises(OWNER)

    assert result.is_error
    read.assert_awaited_once()
    # The backend's own error, not a decorator-wrapped crash.
    assert result.expect_error().message == "boom"


async def test_a_list_longer_than_one_page_is_read_whole() -> None:
    first_page = [_exercise(f"ex_{i}") for i in range(3)]
    everything = [_exercise(f"ex_{i}") for i in range(5)]
    read = AsyncMock(side_effect=[Result.ok((first_page, 5)), Result.ok((everything, 5))])
    service = _service(read)

    result = await service.list_user_exercises(OWNER)

    assert result.is_ok
    assert result.value == everything
    assert read.await_count == 2
    assert read.await_args is not None
    assert read.await_args.kwargs["limit"] == 5  # the second read asks for the whole list


async def test_a_failed_second_read_is_a_failure() -> None:
    read = AsyncMock(
        side_effect=[
            Result.ok(([_exercise("ex_1")], 2)),
            Result.fail(Errors.database(operation="list", message="boom")),
        ]
    )
    service = _service(read)

    result = await service.list_user_exercises(OWNER)

    assert result.is_error
    assert result.expect_error().message == "boom"


async def test_filtered_context_counts_every_listed_exercise() -> None:
    page = [
        _exercise("ex_1"),
        _exercise("ex_2", ExerciseScope.PERSONAL),
        _exercise("ex_3"),
    ]
    service = _service(AsyncMock(return_value=Result.ok((page, 3))))

    result = await service.get_filtered_context(OWNER, status_filter="assigned")

    assert result.is_ok
    assert result.value["stats"]["total"] == 3
    assert [e.uid for e in result.value["entities"]] == ["ex_1", "ex_3"]
