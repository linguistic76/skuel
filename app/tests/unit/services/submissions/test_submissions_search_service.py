"""
Unit tests for SubmissionsSearchService.

Covers the five rewritten search methods that now filter at the Cypher level
(previously fetched a superset and filtered in Python):

- get_report_for_date
- list_reports_by_date_range
- search_submissions
- get_recent_submissions
- get_report_statistics

Each test asserts on the *call arguments* forwarded to ``backend.find_by`` /
``backend.execute_query`` so a future regression that drops the
``entity_type`` / ``$submission_type`` scoping is caught immediately.
"""

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from core.models.enums.entity_enums import EntityStatus, EntityType
from core.models.submissions.submission import Submission
from core.services.submissions.submissions_search_service import (
    SubmissionsSearchService,
)
from core.utils.result_simplified import Errors, Result

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_entity(
    uid: str,
    created_at: datetime,
    *,
    title: str = "Sample",
    processed_content: str | None = None,
    status: EntityStatus = EntityStatus.SUBMITTED,
    entity_type: EntityType = EntityType.EXERCISE_SUBMISSION,
    user_uid: str = "user_1",
) -> Submission:
    """Build a minimal Submission test double."""
    return Submission(
        uid=uid,
        entity_type=entity_type,
        title=title,
        created_at=created_at,
        status=status,
        processed_content=processed_content,
        user_uid=user_uid,
    )


@pytest.fixture
def backend() -> AsyncMock:
    """Mock BackendOperations with find_by / execute_query."""
    mock = AsyncMock()
    mock.find_by = AsyncMock()
    mock.execute_query = AsyncMock()
    return mock


@pytest.fixture
def service(backend: AsyncMock) -> SubmissionsSearchService:
    return SubmissionsSearchService(submissions_backend=backend)


# ---------------------------------------------------------------------------
# get_report_for_date
# ---------------------------------------------------------------------------


class TestGetReportForDate:
    async def test_returns_submission_when_on_target_date(
        self, service: SubmissionsSearchService, backend: AsyncMock
    ) -> None:
        target = date(2026, 4, 5)
        match = _make_entity("es_a", datetime(2026, 4, 5, 9, 0, 0))
        backend.find_by.return_value = Result.ok([match])

        result = await service.get_report_for_date(user_uid="user_1", target_date=target)

        assert result.is_ok
        assert result.value is match
        call_kwargs = backend.find_by.call_args.kwargs
        assert call_kwargs["user_uid"] == "user_1"
        assert call_kwargs["entity_type"] == EntityType.EXERCISE_SUBMISSION.value
        assert call_kwargs["created_at__gte"] == "2026-04-05T00:00:00"
        assert call_kwargs["created_at__lt"] == "2026-04-06T00:00:00"
        assert call_kwargs["sort_order"] == "desc"
        assert call_kwargs["limit"] == 1

    async def test_returns_none_when_no_submission_on_date(
        self, service: SubmissionsSearchService, backend: AsyncMock
    ) -> None:
        backend.find_by.return_value = Result.ok([])

        result = await service.get_report_for_date(user_uid="user_1", target_date=date(2026, 4, 5))

        assert result.is_ok
        assert result.value is None

    async def test_older_submission_on_target_date_is_not_masked_by_newer(
        self, service: SubmissionsSearchService, backend: AsyncMock
    ) -> None:
        """Regression: previous impl fetched limit=1 newest and silently
        returned None when the newest submission wasn't from target_date,
        even though an older submission *was*. The Cypher-level date filter
        means find_by only returns submissions on target_date — the service
        no longer has to post-filter and cannot silently drop the match.
        """
        target = date(2026, 4, 5)
        on_target = _make_entity("es_on_target", datetime(2026, 4, 5, 10, 0, 0))
        backend.find_by.return_value = Result.ok([on_target])

        result = await service.get_report_for_date(user_uid="user_1", target_date=target)

        assert result.is_ok
        assert result.value is on_target
        # Crucially, the caller bounded the query to target_date's day —
        # there is no way for a "newest but wrong day" row to hide the match.
        kwargs = backend.find_by.call_args.kwargs
        assert kwargs["created_at__gte"] == "2026-04-05T00:00:00"
        assert kwargs["created_at__lt"] == "2026-04-06T00:00:00"

    async def test_propagates_backend_error(
        self, service: SubmissionsSearchService, backend: AsyncMock
    ) -> None:
        backend.find_by.return_value = Result.fail(
            Errors.database(operation="find_by", message="boom")
        )

        result = await service.get_report_for_date(user_uid="user_1", target_date=date(2026, 4, 5))

        assert result.is_error


# ---------------------------------------------------------------------------
# list_reports_by_date_range
# ---------------------------------------------------------------------------


class TestListReportsByDateRange:
    async def test_inclusive_range_passes_correct_bounds(
        self, service: SubmissionsSearchService, backend: AsyncMock
    ) -> None:
        backend.find_by.return_value = Result.ok([])

        await service.list_reports_by_date_range(
            user_uid="user_1",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 7),
        )

        kwargs = backend.find_by.call_args.kwargs
        assert kwargs["created_at__gte"] == "2026-04-01T00:00:00"
        # end_date is inclusive → exclusive bound is end_date + 1 day midnight
        assert kwargs["created_at__lt"] == "2026-04-08T00:00:00"
        assert kwargs["entity_type"] == EntityType.EXERCISE_SUBMISSION.value
        assert kwargs["sort_by"] == "created_at"
        assert kwargs["sort_order"] == "desc"

    async def test_returns_empty_list_when_no_matches(
        self, service: SubmissionsSearchService, backend: AsyncMock
    ) -> None:
        backend.find_by.return_value = Result.ok([])

        result = await service.list_reports_by_date_range(
            user_uid="user_1",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 7),
        )

        assert result.is_ok
        assert result.value == []

    async def test_respects_explicit_limit(
        self, service: SubmissionsSearchService, backend: AsyncMock
    ) -> None:
        backend.find_by.return_value = Result.ok([])

        await service.list_reports_by_date_range(
            user_uid="user_1",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 30),
            limit=25,
        )

        assert backend.find_by.call_args.kwargs["limit"] == 25

    async def test_entity_type_override(
        self, service: SubmissionsSearchService, backend: AsyncMock
    ) -> None:
        backend.find_by.return_value = Result.ok([])

        await service.list_reports_by_date_range(
            user_uid="user_1",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 7),
            entity_type=EntityType.ACTIVITY_REPORT,
        )

        assert backend.find_by.call_args.kwargs["entity_type"] == EntityType.ACTIVITY_REPORT.value


# ---------------------------------------------------------------------------
# search_submissions
# ---------------------------------------------------------------------------


class TestSearchSubmissions:
    async def test_empty_query_short_circuits(
        self, service: SubmissionsSearchService, backend: AsyncMock
    ) -> None:
        result = await service.search_submissions(user_uid="user_1", query="")

        assert result.is_ok
        assert result.value == []
        backend.execute_query.assert_not_called()

    async def test_cypher_uses_case_insensitive_contains(
        self, service: SubmissionsSearchService, backend: AsyncMock
    ) -> None:
        backend.execute_query.return_value = Result.ok([])

        await service.search_submissions(user_uid="user_1", query="Fractions", limit=25)

        cypher, params = backend.execute_query.call_args.args
        assert "toLower(s.processed_content) CONTAINS toLower($query)" in cypher
        assert "s.entity_type = $submission_type" in cypher
        assert "ORDER BY s.created_at DESC" in cypher
        assert "LIMIT $limit" in cypher
        assert params == {
            "user_uid": "user_1",
            "submission_type": EntityType.EXERCISE_SUBMISSION.value,
            "query": "Fractions",
            "limit": 25,
        }

    async def test_converts_records_to_entities(
        self, service: SubmissionsSearchService, backend: AsyncMock
    ) -> None:
        """Records returned by execute_query are converted via from_neo4j_node."""
        backend.execute_query.return_value = Result.ok(
            [
                {"s": {"uid": "es_1", "title": "t1"}},
                {"s": {"uid": "es_2", "title": "t2"}},
            ]
        )
        fake_entities = [
            _make_entity("es_1", datetime(2026, 4, 1)),
            _make_entity("es_2", datetime(2026, 4, 2)),
        ]

        with patch(
            "core.services.submissions.submissions_search_service.from_neo4j_node",
            side_effect=fake_entities,
        ) as mapper:
            result = await service.search_submissions(user_uid="user_1", query="something")

        assert result.is_ok
        assert result.value == fake_entities
        assert mapper.call_count == 2

    async def test_propagates_backend_error(
        self, service: SubmissionsSearchService, backend: AsyncMock
    ) -> None:
        backend.execute_query.return_value = Result.fail(
            Errors.database(operation="execute_query", message="boom")
        )

        result = await service.search_submissions(user_uid="user_1", query="anything")

        assert result.is_error


# ---------------------------------------------------------------------------
# get_recent_submissions
# ---------------------------------------------------------------------------


class TestGetRecentSubmissions:
    async def test_scopes_by_entity_type_even_when_none_passed(
        self, service: SubmissionsSearchService, backend: AsyncMock
    ) -> None:
        """Regression: previous impl let entity_type=None fall through, so
        find_by returned every user-owned entity (Tasks, Goals, …) sharing
        the :Entity label. The rewrite defaults to EXERCISE_SUBMISSION.
        """
        backend.find_by.return_value = Result.ok([])

        await service.get_recent_submissions(user_uid="user_1")

        kwargs = backend.find_by.call_args.kwargs
        assert kwargs["entity_type"] == EntityType.EXERCISE_SUBMISSION.value
        assert kwargs["sort_order"] == "desc"
        assert kwargs["sort_by"] == "created_at"

    async def test_explicit_entity_type_override(
        self, service: SubmissionsSearchService, backend: AsyncMock
    ) -> None:
        backend.find_by.return_value = Result.ok([])

        await service.get_recent_submissions(
            user_uid="user_1", entity_type=EntityType.ACTIVITY_REPORT
        )

        assert backend.find_by.call_args.kwargs["entity_type"] == EntityType.ACTIVITY_REPORT.value

    async def test_returns_entities(
        self, service: SubmissionsSearchService, backend: AsyncMock
    ) -> None:
        entities = [
            _make_entity("es_1", datetime(2026, 4, 5)),
            _make_entity("es_2", datetime(2026, 4, 4)),
        ]
        backend.find_by.return_value = Result.ok(entities)

        result = await service.get_recent_submissions(user_uid="user_1", limit=2)

        assert result.is_ok
        assert result.value == entities
        assert backend.find_by.call_args.kwargs["limit"] == 2


# ---------------------------------------------------------------------------
# get_report_statistics
# ---------------------------------------------------------------------------


class TestGetReportStatistics:
    async def test_empty_range_returns_zeros(
        self, service: SubmissionsSearchService, backend: AsyncMock
    ) -> None:
        backend.find_by.return_value = Result.ok([])

        result = await service.get_report_statistics(
            user_uid="user_1",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 7),
        )

        assert result.is_ok
        stats = result.value
        assert stats["total"] == 0
        assert stats["total_words"] == 0
        assert stats["longest_streak"] == 0
        assert stats["current_streak"] == 0
        # Stale "kus_by_*" keys must be gone; new keys use "submissions_by_*".
        assert "submissions_by_day_of_week" in stats
        assert "submissions_by_type" in stats
        assert "kus_by_day_of_week" not in stats
        assert "kus_by_type" not in stats

    async def test_computes_word_count_and_distributions(
        self, service: SubmissionsSearchService, backend: AsyncMock
    ) -> None:
        entities = [
            _make_entity(
                "es_1",
                datetime(2026, 4, 6, 10, 0, 0),  # Monday
                processed_content="one two three four",
                status=EntityStatus.SUBMITTED,
            ),
            _make_entity(
                "es_2",
                datetime(2026, 4, 7, 10, 0, 0),  # Tuesday
                processed_content="alpha beta",
                status=EntityStatus.COMPLETED,
            ),
        ]
        backend.find_by.return_value = Result.ok(entities)

        result = await service.get_report_statistics(
            user_uid="user_1",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 30),
        )

        assert result.is_ok
        stats = result.value
        assert stats["total"] == 2
        assert stats["total_words"] == 6
        assert stats["average_words"] == 3.0
        assert stats["submissions_by_day_of_week"] == {"Monday": 1, "Tuesday": 1}
        assert stats["submissions_by_type"] == {EntityType.EXERCISE_SUBMISSION.value: 2}
        assert stats["by_status"] == {
            EntityStatus.SUBMITTED.value: 1,
            EntityStatus.COMPLETED.value: 1,
        }

    async def test_longest_streak_across_consecutive_days(
        self, service: SubmissionsSearchService, backend: AsyncMock
    ) -> None:
        base = datetime(2026, 4, 1, 12, 0, 0)
        entities = [_make_entity(f"es_{i}", base + timedelta(days=i)) for i in range(3)]
        backend.find_by.return_value = Result.ok(entities)

        result = await service.get_report_statistics(
            user_uid="user_1",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 10),
        )

        assert result.is_ok
        assert result.value["longest_streak"] == 3

    async def test_delegates_to_list_by_date_range(
        self, service: SubmissionsSearchService, backend: AsyncMock
    ) -> None:
        """Stats reads through list_reports_by_date_range, so the backend
        call must carry the same Cypher-level date bounds and EXERCISE_SUBMISSION
        scoping the rewritten list method establishes."""
        backend.find_by.return_value = Result.ok([])

        await service.get_report_statistics(
            user_uid="user_1",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 7),
        )

        kwargs = backend.find_by.call_args.kwargs
        assert kwargs["entity_type"] == EntityType.EXERCISE_SUBMISSION.value
        assert kwargs["created_at__gte"] == "2026-04-01T00:00:00"
        assert kwargs["created_at__lt"] == "2026-04-08T00:00:00"
