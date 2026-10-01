"""Unit pins for UserProgressService.get_mastered_uids.

The Result-preserving mastery read (distinct from the resilient
build_user_knowledge_profile) — every mastered entity's uid, a Ku or a PathStep,
propagating a failed backend read rather than swallowing it into an empty set.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.services.user_progress_service import UserProgressService
from core.utils.result_simplified import Errors, Result


def _service(backend_result: Result) -> UserProgressService:
    backend = MagicMock()
    backend.get_mastered_entity_uids = AsyncMock(return_value=backend_result)
    return UserProgressService(backend)


@pytest.mark.asyncio
async def test_extracts_every_mastered_uid_ku_or_step() -> None:
    service = _service(Result.ok([{"uid": "ku.a"}, {"uid": "ps.the-step"}]))

    result = await service.get_mastered_uids("user_x")

    assert result.is_ok
    assert result.value == {"ku.a", "ps.the-step"}


@pytest.mark.asyncio
async def test_propagates_backend_error() -> None:
    service = _service(
        Result.fail(Errors.database(operation="get_mastered_entity_uids", message="boom"))
    )

    result = await service.get_mastered_uids("user_x")

    # Failure is preserved, NOT swallowed into an empty set.
    assert result.is_error
