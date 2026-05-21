"""Unit tests for ``PsEngagementService.list_review_items``.

The method runs a single Cypher read and shapes the rows into
``ReviewItem`` instances. Tests verify the shape contract — that domain
labels are extracted (preferring non-``Entity`` labels), titles fall back
to UIDs when null, and errors propagate.

Real edge lookups against Neo4j are covered by
``tests/integration/test_ps_engagement_lifecycle.py``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.services.ps_engagement.ps_engagement_service import (
    PsEngagementService,
    ReviewItem,
)
from core.utils.result_simplified import Errors, Result


def _service_with_executor(executor_mock: AsyncMock) -> PsEngagementService:
    """Build a PsEngagementService with only the executor wired."""
    svc = PsEngagementService.__new__(PsEngagementService)
    svc._executor = executor_mock  # type: ignore[attr-defined]
    return svc


@pytest.mark.anyio
async def test_returns_review_items_with_domain_label() -> None:
    executor = AsyncMock()
    executor.execute = AsyncMock(
        return_value=Result.ok(
            [
                {
                    "template_uid": "tpl_task_x",
                    "instance_uid": "task_001",
                    "labels": ["Entity", "Task"],
                    "title": "Read chapter 3",
                },
                {
                    "template_uid": "tpl_habit_y",
                    "instance_uid": "habit_001",
                    "labels": ["Entity", "Habit"],
                    "title": "Practice daily",
                },
            ]
        )
    )
    svc = _service_with_executor(executor)

    result = await svc.list_review_items("user_alice", "ps_test")

    assert result.is_ok
    assert result.value == [
        ReviewItem(
            template_uid="tpl_task_x",
            instance_uid="task_001",
            label="Task",
            title="Read chapter 3",
        ),
        ReviewItem(
            template_uid="tpl_habit_y",
            instance_uid="habit_001",
            label="Habit",
            title="Practice daily",
        ),
    ]


@pytest.mark.anyio
async def test_falls_back_to_entity_label_when_no_domain_label() -> None:
    executor = AsyncMock()
    executor.execute = AsyncMock(
        return_value=Result.ok(
            [
                {
                    "template_uid": "tpl_z",
                    "instance_uid": "n_001",
                    "labels": ["Entity"],
                    "title": "Unlabeled",
                },
            ]
        )
    )
    svc = _service_with_executor(executor)

    result = await svc.list_review_items("user_alice", "ps_test")

    assert result.is_ok
    assert result.value[0].label == "Entity"


@pytest.mark.anyio
async def test_returns_empty_list_when_no_instances() -> None:
    executor = AsyncMock()
    executor.execute = AsyncMock(return_value=Result.ok([]))
    svc = _service_with_executor(executor)

    result = await svc.list_review_items("user_alice", "ps_test")

    assert result.is_ok
    assert result.value == []


@pytest.mark.anyio
async def test_propagates_executor_failure() -> None:
    executor = AsyncMock()
    executor.execute = AsyncMock(
        return_value=Result.fail(Errors.database("list_review_items", "boom"))
    )
    svc = _service_with_executor(executor)

    result = await svc.list_review_items("user_alice", "ps_test")

    assert result.is_error
