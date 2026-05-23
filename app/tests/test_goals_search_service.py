#!/usr/bin/env python3
"""
GoalsSearchService Test Suite
==============================

Tests for search and discovery operations in GoalsSearchService, with
particular focus on the harmonized time-query surface
(``get_upcoming``/``get_overdue``/``get_active``) and goal-specific
filters (timeframe, knowledge blockers, habit support).
"""

from datetime import date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from core.models.enums import Domain, EntityStatus, Priority
from core.models.enums.goal_enums import GoalTimeframe
from core.models.goal.goal import Goal
from core.models.goal.goal_dto import GoalDTO
from core.services.goals.goals_search_service import GoalsSearchService
from core.services.user import UserContext
from core.utils.result_simplified import Errors, Result

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_backend() -> Any:
    """Create a mock goals backend."""
    backend = Mock()
    backend.find_by = AsyncMock(return_value=Result.ok([]))
    backend.get = AsyncMock()
    backend.get_related_uids = AsyncMock(return_value=Result.ok([]))
    backend.count_related = AsyncMock(return_value=Result.ok(0))
    # Temporal raw helpers used by TimeQueryMixin
    backend.upcoming_raw = AsyncMock(return_value=Result.ok([]))
    backend.overdue_raw = AsyncMock(return_value=Result.ok([]))
    backend.active_raw = AsyncMock(return_value=Result.ok([]))
    return backend


@pytest.fixture
def search_service(mock_backend) -> GoalsSearchService:
    """Create GoalsSearchService instance."""
    return GoalsSearchService(backend=mock_backend)


@pytest.fixture
def sample_goals() -> list[Goal]:
    """Create sample goals."""
    now = datetime.now()
    return [
        Goal.from_dto(
            GoalDTO(
                uid="goal:1",
                user_uid="user_demo",
                title="Ship v1",
                domain=Domain.TECH,
                status=EntityStatus.ACTIVE,
                priority=Priority.HIGH.value,
                timeframe=GoalTimeframe.QUARTERLY,
                target_date=date.today() + timedelta(days=30),
                progress_percentage=25.0,
                created_at=now,
            )
        ),
        Goal.from_dto(
            GoalDTO(
                uid="goal:2",
                user_uid="user_demo",
                title="Run marathon",
                domain=Domain.HEALTH,
                status=EntityStatus.ACTIVE,
                priority=Priority.MEDIUM.value,
                timeframe=GoalTimeframe.YEARLY,
                target_date=date.today() + timedelta(days=180),
                progress_percentage=10.0,
                created_at=now,
            )
        ),
        Goal.from_dto(
            GoalDTO(
                uid="goal:3",
                user_uid="user_demo",
                title="Learn Rust",
                domain=Domain.TECH,
                status=EntityStatus.COMPLETED,
                timeframe=GoalTimeframe.MONTHLY,
                target_date=date.today() - timedelta(days=7),
                progress_percentage=100.0,
                created_at=now,
            )
        ),
    ]


@pytest.fixture
def user_context() -> UserContext:
    """Create sample user context."""
    return UserContext(
        user_uid="user_demo",
        username="test_user",
        knowledge_mastery={"ku.python.basics": 0.9},
    )


# ============================================================================
# INITIALIZATION
# ============================================================================


def test_init_with_backend(mock_backend):
    service = GoalsSearchService(backend=mock_backend)
    assert service.backend == mock_backend


def test_init_without_backend():
    with pytest.raises(ValueError, match=r"[Bb]ackend is REQUIRED"):
        GoalsSearchService(backend=None)


# ============================================================================
# HARMONIZED TIME-QUERY SURFACE (get_upcoming / get_overdue / get_active)
# ============================================================================


@pytest.mark.asyncio
async def test_get_upcoming_uses_target_date(search_service, mock_backend, sample_goals):
    """Goals.get_upcoming forwards target_date as the date_field."""
    mock_backend.upcoming_raw.return_value = Result.ok(
        [g.to_dto().to_dict() for g in sample_goals[:2]]
    )

    result = await search_service.get_upcoming(days_ahead=60, user_uid="user_demo", limit=20)

    assert result.is_ok
    assert len(result.value) == 2
    kwargs = mock_backend.upcoming_raw.call_args.kwargs
    assert kwargs["date_field"] == "target_date"
    assert kwargs["days_ahead"] == 60
    assert kwargs["user_uid"] == "user_demo"
    assert kwargs["limit"] == 20


@pytest.mark.asyncio
async def test_get_upcoming_excludes_terminal_statuses(search_service, mock_backend):
    """Default exclusions hide completed/cancelled/failed/archived goals."""
    mock_backend.upcoming_raw.return_value = Result.ok([])

    await search_service.get_upcoming()

    kwargs = mock_backend.upcoming_raw.call_args.kwargs
    assert set(kwargs["exclude_statuses"]) >= {"completed", "failed", "cancelled", "archived"}


@pytest.mark.asyncio
async def test_get_upcoming_error_propagates(search_service, mock_backend):
    mock_backend.upcoming_raw.return_value = Result.fail(Errors.database("upcoming_raw", "boom"))

    result = await search_service.get_upcoming()

    assert result.is_error


@pytest.mark.asyncio
async def test_get_overdue_uses_target_date(search_service, mock_backend, sample_goals):
    """Goals.get_overdue forwards target_date as the date_field."""
    mock_backend.overdue_raw.return_value = Result.ok(
        [g.to_dto().to_dict() for g in sample_goals[:1]]
    )

    result = await search_service.get_overdue(user_uid="user_demo")

    assert result.is_ok
    assert len(result.value) == 1
    kwargs = mock_backend.overdue_raw.call_args.kwargs
    assert kwargs["date_field"] == "target_date"
    assert kwargs["user_uid"] == "user_demo"


@pytest.mark.asyncio
async def test_get_overdue_admin_path(search_service, mock_backend):
    """Admin queries are allowed (user_uid=None)."""
    mock_backend.overdue_raw.return_value = Result.ok([])

    result = await search_service.get_overdue()

    assert result.is_ok
    kwargs = mock_backend.overdue_raw.call_args.kwargs
    assert kwargs["user_uid"] is None


@pytest.mark.asyncio
async def test_get_active_requires_user_uid(search_service, mock_backend):
    result = await search_service.get_active(user_uid="")

    assert result.is_error
    mock_backend.active_raw.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_active_success(search_service, mock_backend, sample_goals):
    mock_backend.active_raw.return_value = Result.ok(
        [g.to_dto().to_dict() for g in sample_goals[:2]]
    )

    result = await search_service.get_active(user_uid="user_demo", limit=10)

    assert result.is_ok
    assert len(result.value) == 2
    kwargs = mock_backend.active_raw.call_args.kwargs
    assert kwargs["user_uid"] == "user_demo"
    assert kwargs["limit"] == 10
    # Goals exclude both COMPLETED and CANCELLED per config
    assert "completed" in kwargs["exclude_statuses"]
    assert "cancelled" in kwargs["exclude_statuses"]


# ============================================================================
# GOAL-SPECIFIC SEARCH METHODS
# ============================================================================


@pytest.mark.asyncio
async def test_get_by_timeframe(search_service, mock_backend, sample_goals):
    quarterly = [g for g in sample_goals if g.timeframe == GoalTimeframe.QUARTERLY]
    mock_backend.find_by.return_value = Result.ok([g.to_dto().to_dict() for g in quarterly])

    result = await search_service.get_by_timeframe(GoalTimeframe.QUARTERLY)

    assert result.is_ok
    assert len(result.value) == 1
    kwargs = mock_backend.find_by.call_args.kwargs
    assert kwargs["timeframe"] == GoalTimeframe.QUARTERLY.value


@pytest.mark.asyncio
async def test_get_prioritized_sorts_by_score(
    search_service, mock_backend, sample_goals, user_context
):
    """get_prioritized queries active goals and sorts via score_goal."""
    active = [g for g in sample_goals if g.status == EntityStatus.ACTIVE]
    mock_backend.find_by.return_value = Result.ok([g.to_dto().to_dict() for g in active])

    result = await search_service.get_prioritized(user_context, limit=5)

    assert result.is_ok
    assert len(result.value) <= 5
    # Must have queried with ACTIVE status
    kwargs = mock_backend.find_by.call_args.kwargs
    assert kwargs["status"] == EntityStatus.ACTIVE.value
    assert kwargs["user_uid"] == "user_demo"


@pytest.mark.asyncio
async def test_get_needing_habits_filters_low_progress(
    search_service, mock_backend, sample_goals, user_context
):
    """Goals with <=1 supporting habit and <50% progress are returned."""
    active = [g for g in sample_goals if g.status == EntityStatus.ACTIVE]
    mock_backend.find_by.return_value = Result.ok([g.to_dto().to_dict() for g in active])
    mock_backend.count_related.return_value = Result.ok(0)

    result = await search_service.get_needing_habits(user_context, limit=5)

    assert result.is_ok
    # Both active goals in sample have <50% progress and 0 habits
    assert len(result.value) == 2


@pytest.mark.asyncio
async def test_get_blocked_by_knowledge_skips_mastered(search_service, mock_backend, user_context):
    """Goals whose knowledge prerequisites are all mastered are not blocked."""
    active_goal = GoalDTO(
        uid="goal:unblocked",
        user_uid="user_demo",
        title="Unblocked goal",
        domain=Domain.TECH,
        status=EntityStatus.ACTIVE,
        created_at=datetime.now(),
    )
    mock_backend.find_by.return_value = Result.ok([active_goal.to_dict()])
    # Goal requires ku.python.basics, which user has mastered (0.9)
    mock_backend.get_related_uids.return_value = Result.ok(["ku.python.basics"])

    result = await search_service.get_blocked_by_knowledge(user_context, limit=5)

    assert result.is_ok
    assert result.value == []


# ============================================================================
# INTELLIGENT SEARCH
# ============================================================================


@pytest.mark.asyncio
async def test_intelligent_search_extracts_timeframe(search_service, mock_backend, sample_goals):
    """'monthly goals' maps to timeframe=MONTHLY."""
    mock_backend.find_by.return_value = Result.ok([g.to_dto().to_dict() for g in sample_goals])

    result = await search_service.intelligent_search("monthly tech goals")

    assert result.is_ok
    kwargs = mock_backend.find_by.call_args.kwargs
    assert kwargs["timeframe"] == GoalTimeframe.MONTHLY.value


@pytest.mark.asyncio
async def test_intelligent_search_extracts_status(search_service, mock_backend):
    """'achieved' maps to EntityStatus.COMPLETED."""
    mock_backend.find_by.return_value = Result.ok([])

    await search_service.intelligent_search("achieved goals")

    kwargs = mock_backend.find_by.call_args.kwargs
    assert kwargs["status"] == EntityStatus.COMPLETED.value


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
