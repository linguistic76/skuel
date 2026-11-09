"""``ActivityReviewOrchestrator.submit_report`` checks the subject is a user
before the report is written as theirs (Submit & Share arc R11). The reviewed
period is the subject's, so the snapshot and the report run in the subject's
zone, not the reviewing admin's (UTC arc, PR 2b). The snapshot the admin read
goes with the report, and a review answering a learner's request closes it."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from core.models.type_hints import UserUID
from core.models.user.user import User, UserPreferences
from core.orchestrator.activity_review_orchestrator import ActivityReviewOrchestrator
from core.utils.result_simplified import ErrorCategory, Errors, Result
from core.utils.zone_context import current_zone, zone_scope


@pytest.fixture
def activity_report() -> MagicMock:
    service = MagicMock()
    service.submit_report = AsyncMock(return_value=Result.ok(MagicMock(uid="ar_1")))
    return service


@pytest.fixture
def user_service() -> MagicMock:
    service = MagicMock()
    service.get_user = AsyncMock(return_value=Result.ok(MagicMock(uid="user_student")))
    return service


@pytest.fixture
def orchestrator(activity_report: MagicMock, user_service: MagicMock) -> ActivityReviewOrchestrator:
    return ActivityReviewOrchestrator(activity_report=activity_report, user_service=user_service)


@pytest.mark.asyncio
async def test_an_unknown_subject_is_a_validation_error_on_subject_uid(
    orchestrator: ActivityReviewOrchestrator, activity_report: MagicMock, user_service: MagicMock
) -> None:
    user_service.get_user = AsyncMock(return_value=Result.ok(None))

    result = await orchestrator.submit_report(
        admin_uid=UserUID("user_admin"), subject_uid=UserUID("user_typo"), feedback_text="…"
    )

    assert result.is_error
    error = result.expect_error()
    assert error.category is ErrorCategory.VALIDATION
    assert error.details.get("field") == "subject_uid"
    activity_report.submit_report.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_failed_user_read_propagates(
    orchestrator: ActivityReviewOrchestrator, activity_report: MagicMock, user_service: MagicMock
) -> None:
    user_service.get_user = AsyncMock(
        return_value=Result.fail(Errors.database("get_user", "connection lost"))
    )

    result = await orchestrator.submit_report(
        admin_uid=UserUID("user_admin"), subject_uid=UserUID("user_student"), feedback_text="…"
    )

    assert result.is_error
    assert result.expect_error().category is ErrorCategory.DATABASE
    activity_report.submit_report.assert_not_awaited()


SNAPSHOT = {"subject_uid": "user_student", "domains": {"tasks": {"count": 1, "items": []}}}


@pytest.mark.asyncio
async def test_a_known_subject_reaches_the_writer_with_the_snapshot(
    orchestrator: ActivityReviewOrchestrator, activity_report: MagicMock
) -> None:
    result = await orchestrator.submit_report(
        admin_uid=UserUID("user_admin"),
        subject_uid=UserUID("user_student"),
        feedback_text="Good week.",
        time_period="2026-09",
        domains=["tasks"],
        snapshot_context=SNAPSHOT,
    )

    assert result.is_ok
    assert result.value.request_closed is None
    activity_report.submit_report.assert_awaited_once_with(
        admin_uid="user_admin",
        subject_uid="user_student",
        feedback_text="Good week.",
        time_period="2026-09",
        domains=["tasks"],
        snapshot_context=SNAPSHOT,
    )


@pytest.mark.asyncio
async def test_a_snapshot_of_another_user_is_refused(
    orchestrator: ActivityReviewOrchestrator, activity_report: MagicMock
) -> None:
    result = await orchestrator.submit_report(
        admin_uid=UserUID("user_admin"),
        subject_uid=UserUID("user_student"),
        feedback_text="Good week.",
        snapshot_context={**SNAPSHOT, "subject_uid": "user_other"},
    )

    assert result.expect_error().details.get("field") == "snapshot_context"
    activity_report.submit_report.assert_not_awaited()


def _queue(*, pending: bool = True, closed: Result[bool] | None = None) -> MagicMock:
    queue = MagicMock()
    queue.is_pending_for = AsyncMock(return_value=Result.ok(pending))
    queue.answer_request = AsyncMock(return_value=closed or Result.ok(True))
    return queue


def _with_queue(
    activity_report: MagicMock, user_service: MagicMock, queue: MagicMock
) -> ActivityReviewOrchestrator:
    return ActivityReviewOrchestrator(
        activity_report=activity_report, user_service=user_service, review_queue=queue
    )


@pytest.mark.asyncio
async def test_a_review_answering_a_request_closes_it_with_the_report(
    activity_report: MagicMock, user_service: MagicMock
) -> None:
    queue = _queue()
    result = await _with_queue(activity_report, user_service, queue).submit_report(
        admin_uid=UserUID("user_admin"),
        subject_uid=UserUID("user_student"),
        feedback_text="Good week.",
        review_request_uid="rr_0123456789abcdef",
    )

    assert result.value.request_closed is True
    queue.is_pending_for.assert_awaited_once_with("rr_0123456789abcdef", "user_student")
    queue.answer_request.assert_awaited_once_with("rr_0123456789abcdef", "user_student", "ar_1")


@pytest.mark.asyncio
async def test_a_request_no_longer_pending_is_refused_before_any_report(
    activity_report: MagicMock, user_service: MagicMock
) -> None:
    queue = _queue(pending=False)
    result = await _with_queue(activity_report, user_service, queue).submit_report(
        admin_uid=UserUID("user_admin"),
        subject_uid=UserUID("user_student"),
        feedback_text="Good week.",
        review_request_uid="rr_0123456789abcdef",
    )

    error = result.expect_error()
    assert error.category is ErrorCategory.VALIDATION
    assert error.details.get("field") == "review_request_uid"
    activity_report.submit_report.assert_not_awaited()
    queue.answer_request.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_failed_close_keeps_the_written_report_and_says_so(
    activity_report: MagicMock, user_service: MagicMock
) -> None:
    """The report is written and the learner rung; a failed close must not read as a failed review."""
    queue = _queue(closed=Result.fail(Errors.database("answer_review_request", "lost")))
    result = await _with_queue(activity_report, user_service, queue).submit_report(
        admin_uid=UserUID("user_admin"),
        subject_uid=UserUID("user_student"),
        feedback_text="Good week.",
        review_request_uid="rr_0123456789abcdef",
    )

    assert result.is_ok
    assert result.value.report.uid == "ar_1"
    assert result.value.request_closed is False


BANGKOK = ZoneInfo("Asia/Bangkok")
ADMINS_ZONE = ZoneInfo("Europe/Paris")


@pytest.mark.asyncio
async def test_the_report_is_written_in_the_subjects_zone(
    orchestrator: ActivityReviewOrchestrator, activity_report: MagicMock, user_service: MagicMock
) -> None:
    subject = User(
        uid="user_student",
        title="student",
        email="s@test.local",
        preferences=UserPreferences(timezone="Asia/Bangkok"),
    )
    user_service.get_user = AsyncMock(return_value=Result.ok(subject))
    zones: list[ZoneInfo] = []

    async def record(**_kwargs: object) -> Result[MagicMock]:
        zones.append(current_zone())
        return Result.ok(MagicMock(uid="ar_1"))

    activity_report.submit_report = AsyncMock(side_effect=record)

    with zone_scope(ADMINS_ZONE):
        result = await orchestrator.submit_report(
            admin_uid=UserUID("user_admin"),
            subject_uid=UserUID("user_student"),
            feedback_text="Good week.",
            time_period="2026-W37",
        )
        assert current_zone() == ADMINS_ZONE

    assert result.is_ok
    assert zones == [BANGKOK]


@pytest.mark.asyncio
async def test_the_snapshot_is_taken_in_the_subjects_zone(
    orchestrator: ActivityReviewOrchestrator, activity_report: MagicMock, user_service: MagicMock
) -> None:
    user_service.get_user_zone = AsyncMock(return_value=Result.ok(BANGKOK))
    zones: list[ZoneInfo] = []

    async def record(**_kwargs: object) -> Result[dict[str, object]]:
        zones.append(current_zone())
        return Result.ok({})

    activity_report.create_snapshot = AsyncMock(side_effect=record)
    context = MagicMock(user_uid="user_student")

    with zone_scope(ADMINS_ZONE):
        result = await orchestrator.create_snapshot(
            context=context, admin_uid=UserUID("user_admin"), time_period="2026-W37"
        )

    assert result.is_ok
    user_service.get_user_zone.assert_awaited_once_with("user_student")
    assert zones == [BANGKOK]
    # The subject's access audit names the admin who looked.
    assert activity_report.create_snapshot.await_args.kwargs["admin_uid"] == "user_admin"
