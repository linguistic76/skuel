"""Single-builder wiring — the ZPD capstone must reach the production path.

Regression tests for the dual-UserContextBuilder bug (PR 5, discovery-analytics
arc): compose.py used to construct a SECOND UserContextBuilder and post-wire
zpd_service/ps_engagement onto that copy only, while
``UserService.get_rich_unified_context`` (the production daily-plan path) used
UserService's internal builder — so ``zpd_assessment`` was always None in
production. One Path Forward fix: UserService's internal builder IS the single
app-wide builder; compose reuses it.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.models.user.user import User
from core.models.zpd.zpd_assessment import ZPDAssessment
from core.services.user_service import UserService
from core.utils.result_simplified import Errors, Result

_COMPOSE_PATH = Path(__file__).parents[3] / "services_bootstrap" / "compose.py"


def _fake_user(uid: str = "user_test_wiring") -> User:
    return User(uid=uid, title=uid, email="wiring@test.local", display_name="Wiring Test")


def _fake_assessment() -> ZPDAssessment:
    return ZPDAssessment(
        current_zone=["ku.test.a"],
        proximal_zone=["ku.test.b"],
        engaged_paths=[],
        readiness_scores={"ku.test.b": 1.0},
        blocking_gaps=[],
        behavioral_readiness=0.5,
    )


def _mock_query_executor() -> MagicMock:
    """UserContextQueryExecutor double with the minimal MEGA-QUERY shape."""
    executor = MagicMock()
    executor.execute_mega_query = AsyncMock(
        return_value=Result.ok({"uids": {}, "entities": {}, "rich": {}})
    )
    executor.execute_consolidated_query = AsyncMock(return_value=Result.ok({}))
    # Secondary fetches fail-soft in the builder (is_ok checks) — errors are fine.
    executor.fetch_current_path_steps = AsyncMock(
        return_value=Result.fail(Errors.system(message="not in this test"))
    )
    executor.fetch_user_groups = AsyncMock(
        return_value=Result.fail(Errors.system(message="not in this test"))
    )
    return executor


def _user_service() -> UserService:
    repo = MagicMock()
    repo.get_user_by_uid = AsyncMock(return_value=Result.ok(_fake_user()))
    return UserService(user_repo=repo, query_executor=_mock_query_executor())


class TestSingleBuilderWiring:
    def test_user_service_owns_the_builder(self) -> None:
        service = _user_service()
        assert service.context_builder is not None
        # The builder resolves users through this exact facade (circular by design)
        assert service.context_builder.user_service is service

    async def test_rich_context_runs_zpd_capstone_when_service_wired(self) -> None:
        """Post-wiring zpd_service onto UserService's builder (what
        _intelligence_hub does to the ONE shared builder) makes the production
        path — get_rich_unified_context — carry a real assessment."""
        service = _user_service()
        assessment = _fake_assessment()
        zpd = MagicMock()
        zpd.assess_zone = AsyncMock(return_value=Result.ok(assessment))
        assert service.context_builder is not None
        service.context_builder.zpd_service = zpd

        result = await service.get_rich_unified_context("user_test_wiring")

        assert result.is_ok, f"rich context failed: {result.error}"
        assert result.value.zpd_assessment is assessment
        zpd.assess_zone.assert_awaited_once()

    async def test_rich_context_zpd_none_when_service_absent(self) -> None:
        """CORE tier: no zpd_service on the builder → zpd_assessment stays None."""
        service = _user_service()

        result = await service.get_rich_unified_context("user_test_wiring")

        assert result.is_ok, f"rich context failed: {result.error}"
        assert result.value.zpd_assessment is None


class TestComposeReusesTheBuilder:
    """Source-level guard: compose.py must never construct a second builder.

    The bug was invisible at runtime (both builders 'worked'; only the capstone
    silently vanished), so guard the composition root's shape directly.
    """

    def test_compose_does_not_construct_a_builder(self) -> None:
        source = _COMPOSE_PATH.read_text()
        assert "UserContextBuilder(" not in source, (
            "compose.py constructs its own UserContextBuilder — production must "
            "reuse user_service.context_builder (the single app-wide builder) or "
            "_intelligence_hub's zpd/ps_engagement post-wiring never reaches "
            "UserService.get_rich_unified_context (daily-plan zpd_assessment "
            "regresses to None)."
        )

    def test_compose_reuses_user_service_builder(self) -> None:
        source = _COMPOSE_PATH.read_text()
        assert "context_builder = user_service.context_builder" in source


@pytest.mark.parametrize("attr", ["zpd_service", "ps_engagement_service"])
def test_builder_exposes_post_wire_seams(attr: str) -> None:
    """_intelligence_hub post-wires these onto the shared builder — keep the seams."""
    service = _user_service()
    assert service.context_builder is not None
    assert hasattr(type(service.context_builder), "__init__")
    assert getattr(service.context_builder, attr, "MISSING") is None
