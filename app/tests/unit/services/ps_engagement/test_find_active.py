"""Unit tests for ``PsEngagementService.find_active`` (public read method).

The method is a thin delegate to ``_EngagementGateway.find_active``; these
tests verify the delegation contract — that the public surface forwards
both the engagement-present and engagement-absent cases unchanged.

Real edge lookups against Neo4j are covered by
``tests/integration/test_ps_engagement_lifecycle.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from core.services.ps_engagement.engagement import Engagement
from core.services.ps_engagement.ps_engagement_service import PsEngagementService
from core.utils.result_simplified import Result


def _service_with_gateway(gateway_mock: AsyncMock) -> PsEngagementService:
    """Build a PsEngagementService with only the gateway wired.

    ``find_active`` only touches ``self._gateway`` — skipping the full
    constructor keeps the test focused on the delegation surface.
    """
    svc = PsEngagementService.__new__(PsEngagementService)
    svc._gateway = gateway_mock  # type: ignore[attr-defined]
    return svc


@pytest.mark.anyio
async def test_find_active_returns_engagement_when_present() -> None:
    engagement = Engagement(
        student_uid="user_alice",
        ps_uid="ps_test",
        state="engaged",
        since=datetime(2026, 5, 3, 10, 0, tzinfo=UTC),
    )
    gateway = AsyncMock()
    gateway.find_active = AsyncMock(return_value=Result.ok(engagement))
    svc = _service_with_gateway(gateway)

    result = await svc.find_active("user_alice", "ps_test")

    assert result.is_ok
    assert result.value is engagement
    gateway.find_active.assert_awaited_once_with("user_alice", "ps_test")


@pytest.mark.anyio
async def test_find_active_returns_none_when_absent() -> None:
    gateway = AsyncMock()
    gateway.find_active = AsyncMock(return_value=Result.ok(None))
    svc = _service_with_gateway(gateway)

    result = await svc.find_active("user_alice", "ps_test")

    assert result.is_ok
    assert result.value is None
    gateway.find_active.assert_awaited_once_with("user_alice", "ps_test")
