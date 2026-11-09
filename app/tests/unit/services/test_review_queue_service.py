"""``ReviewQueueService``: a learner's review request, one pending at a time.

The backend decides under the user's lock whether a request opens; the service
reads its row: ``created`` says which, and no row means the user does not exist.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.type_hints import UserUID
from core.services.report.review_queue_service import ReviewQueueService
from core.utils.result_simplified import ErrorCategory, Errors, Result

LEARNER = UserUID("user_learner")
ROW: dict[str, object] = {
    "uid": "rr_0123456789abcdef",
    "user_uid": "user_learner",
    "status": "pending",
    "time_period": "30d",
    "domains": ["habits"],
    "message": "Look at my habits",
    "created_at": "2026-11-08T10:00:00Z",
}


def _service(rows: Result[list[dict[str, object]]]) -> tuple[ReviewQueueService, MagicMock]:
    backend = MagicMock()
    backend.create_review_request = AsyncMock(return_value=rows)
    backend.get_pending_request = AsyncMock(return_value=rows)
    return ReviewQueueService(backend=backend), backend


@pytest.mark.asyncio
@pytest.mark.parametrize("created", [True, False])
async def test_the_request_answers_the_pending_row_and_whether_it_opened(created: bool) -> None:
    service, backend = _service(Result.ok([{**ROW, "created": created}]))

    result = await service.request_review(
        LEARNER, time_period="30d", domains=["habits"], message="Look at my habits"
    )

    assert result.value == {**ROW, "created": created}
    kwargs = backend.create_review_request.await_args.kwargs
    assert kwargs["user_uid"] == LEARNER
    assert kwargs["uid"].startswith("rr_")
    assert (kwargs["time_period"], kwargs["domains"], kwargs["message"]) == (
        "30d",
        ["habits"],
        "Look at my habits",
    )


@pytest.mark.asyncio
async def test_a_user_who_does_not_exist_is_not_found() -> None:
    service, _ = _service(Result.ok([]))

    result = await service.request_review(LEARNER)

    assert result.expect_error().category is ErrorCategory.NOT_FOUND


@pytest.mark.asyncio
async def test_a_failed_write_propagates() -> None:
    service, _ = _service(Result.fail(Errors.database("create_review_request", "lost")))

    result = await service.request_review(LEARNER)

    assert result.expect_error().category is ErrorCategory.DATABASE


@pytest.mark.asyncio
async def test_the_pending_read_is_the_row_or_none() -> None:
    held, _ = _service(Result.ok([ROW]))
    none, _ = _service(Result.ok([]))

    assert (await held.get_pending_request(LEARNER)).value == ROW
    assert (await none.get_pending_request(LEARNER)).value is None
