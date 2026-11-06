"""Every PathStep intelligence read that needs the backend fails through one guard.

``_require_backend`` is the one place a read finds the injected backend missing, so
an unwired service answers the same error from every method and a caller's branch on
it holds everywhere.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from core.services.ps.ps_intelligence_service import PsIntelligenceService
from core.utils.result_simplified import Result

_UID = "ps.test.step"

_READS: list[tuple[str, tuple[object, ...]]] = [
    ("is_ready", (_UID, set())),
    ("get_prerequisite_statuses", (_UID, "user_test")),
    ("get_practice_summary", (_UID,)),
    ("practice_completeness_score", (_UID,)),
    ("calculate_guidance_strength", (_UID,)),
    ("has_prerequisites", (_UID,)),
    ("has_guidance", (_UID,)),
    ("has_practice_opportunities", (_UID,)),
    ("calculate_user_substance", (_UID, Mock())),
    ("calculate_user_substance_for_steps", ([_UID], {})),
    ("calculate_user_substance_breakdown_for_steps", ([_UID], {})),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "args"), _READS, ids=[name for name, _ in _READS])
async def test_an_unwired_backend_fails_through_the_one_guard(
    method: str, args: tuple[object, ...]
) -> None:
    service = PsIntelligenceService(backend=Mock(), intelligence_backend=None)

    result = await getattr(service, method)(*args)

    assert result.is_error
    error = result.expect_error()
    assert error.message == "PsIntelligenceBackend not wired"
    assert error.details["operation"] == "require_backend"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method", ["has_prerequisites", "has_guidance", "has_practice_opportunities"]
)
async def test_a_wired_backend_answers_the_existence_reads(method: str) -> None:
    intelligence_backend = Mock()
    read = AsyncMock(return_value=Result.ok(True))
    setattr(intelligence_backend, method, read)
    service = PsIntelligenceService(backend=Mock(), intelligence_backend=intelligence_backend)

    result = await getattr(service, method)(_UID)

    assert result.is_ok
    assert result.value is True
    read.assert_awaited_once_with(_UID)
