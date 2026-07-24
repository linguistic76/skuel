"""Per-user daily LLM quota (MEMBER+) — helpers + the AI-route chokepoint.

Droplet-prep fast-follow C2: every money-spending AI request records one unit
against a per-user sliding 24 h window (``core.constants.LLMQuota``), enforced
at the three cost chokepoints (``_ai_route``, journals' ``_load_ai_gated_user``,
folder transcription). This file pins the shared helpers in ``rate_limit.py``
and the ``_ai_route`` guard order: tier and ownership denials must never burn
quota, and the quota denial must read as "limit reached", never as the
subscription upsell. Journals and transcription chokepoints are pinned in
``test_journals_follow_up_gate.py`` / ``test_batch_transcription_api_routes.py``.

``_ai_route`` is exercised directly with fakes (no live Neo4j / FastHTML),
mirroring ``test_ai_routes_ownership.py``.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.responses import JSONResponse

import adapters.inbound.ai_routes as ai_routes
from adapters.inbound.ai_routes import _ai_route
from adapters.inbound.rate_limit import (
    LLM_QUOTA_MESSAGE,
    allow_key,
    llm_quota_allowed,
    llm_quota_exceeded_error,
    reset_buckets_for_testing,
)
from core.config.intelligence_tier import IntelligenceTier
from core.constants import LLMQuota
from core.models.enums import ContentScope, UserRole
from core.utils.result_simplified import ErrorCategory, Errors, Result

_CALLER = "user_quota"


def _fixed_caller(_request: object) -> str:
    return _CALLER


@pytest.fixture(autouse=True)
def _clean_buckets_and_auth(monkeypatch: pytest.MonkeyPatch):
    reset_buckets_for_testing()
    monkeypatch.setattr(ai_routes, "require_authenticated_user", _fixed_caller)
    yield
    reset_buckets_for_testing()


def _exhaust_quota(user_uid: str, *, leave: int = 0) -> None:
    """Consume all but ``leave`` units of the user's daily quota."""
    for _ in range(LLMQuota.DAILY_LIMIT - leave):
        assert llm_quota_allowed(user_uid)


class _FakeAI:
    def __init__(self) -> None:
        self.called = False

    def __getattr__(self, name: str):
        async def _invoke(*_args: object) -> Result[dict]:
            self.called = True
            return Result.ok({"method": name})

        return _invoke


class _FakeFacade:
    def __init__(self, *, owns: bool, ai: _FakeAI | None) -> None:
        self.ai = ai
        self._owns = owns

    async def verify_ownership(self, uid: str, user_uid: str) -> Result[dict]:
        if self._owns:
            return Result.ok({"uid": uid, "user_uid": user_uid})
        return Result.fail(Errors.not_found("Entity", uid))


class _Services:
    # None → skip the per-user tier gate in _ai_route; tier tests set both.
    intelligence_tier: IntelligenceTier | None = None
    user: MagicMock | None = None

    def __init__(self, **facades: object) -> None:
        for name, facade in facades.items():
            setattr(self, name, facade)


async def _call_insight_route(services: _Services) -> object:
    return await _ai_route(
        object(),
        services,
        "tasks",
        "Tasks",
        "generate_task_insight",
        ("task_mine",),
        scope=ContentScope.USER_OWNED,
        entity_uid="task_mine",
        wrap_key="insight",
    )


class TestQuotaHelpers:
    def test_allows_up_to_daily_limit_then_denies(self) -> None:
        _exhaust_quota(_CALLER)
        assert llm_quota_allowed(_CALLER) is False

    def test_quota_is_per_user(self) -> None:
        _exhaust_quota("user_spender")
        assert llm_quota_allowed("user_spender") is False
        assert llm_quota_allowed("user_frugal") is True

    def test_quota_key_never_collides_with_burst_buckets(self) -> None:
        # The per-route burst limiter keys on the bare user_uid; the quota key
        # is namespaced. Exhausting one must not touch the other.
        assert allow_key(_CALLER, 1, 60.0) is True
        assert allow_key(_CALLER, 1, 60.0) is False  # burst bucket exhausted
        assert llm_quota_allowed(_CALLER) is True  # quota bucket untouched

    def test_quota_error_is_forbidden_with_distinct_message(self) -> None:
        error = llm_quota_exceeded_error()
        assert error.category is ErrorCategory.FORBIDDEN
        assert error.message == LLM_QUOTA_MESSAGE
        # No upsell: the caller already holds MEMBER+, so the denial must not
        # carry the subscription gate's required_role hint.
        assert "required_role" not in error.details
        assert "subscription" not in error.message.lower()


class TestAiRouteQuotaGate:
    async def test_over_quota_denies_403_without_ai_call(self) -> None:
        ai = _FakeAI()
        services = _Services(tasks=_FakeFacade(owns=True, ai=ai))
        _exhaust_quota(_CALLER)

        resp = await _call_insight_route(services)

        assert isinstance(resp, JSONResponse)
        assert resp.status_code == 403
        assert LLM_QUOTA_MESSAGE.encode() in resp.body
        assert ai.called is False

    async def test_under_quota_passes_and_records_one_unit(self) -> None:
        ai = _FakeAI()
        services = _Services(tasks=_FakeFacade(owns=True, ai=ai))
        _exhaust_quota(_CALLER, leave=2)

        resp = await _call_insight_route(services)

        assert resp == {"insight": {"method": "generate_task_insight"}}
        # The route call recorded exactly one unit: one remains, then dry.
        assert llm_quota_allowed(_CALLER) is True
        assert llm_quota_allowed(_CALLER) is False

    async def test_ownership_denial_does_not_burn_quota(self) -> None:
        ai = _FakeAI()
        services = _Services(tasks=_FakeFacade(owns=False, ai=ai))
        _exhaust_quota(_CALLER, leave=1)

        resp = await _call_insight_route(services)

        assert isinstance(resp, JSONResponse)
        assert resp.status_code == 404
        assert ai.called is False
        # The 404 fired before the quota check — the last unit is still there.
        assert llm_quota_allowed(_CALLER) is True

    async def test_registered_user_still_gets_subscription_denial(self) -> None:
        # REGISTERED unchanged: the tier gate fires before the quota check, so
        # a free-trial user always sees the upgrade message — even at quota.
        ai = _FakeAI()
        services = _Services(tasks=_FakeFacade(owns=True, ai=ai))
        services.intelligence_tier = IntelligenceTier.FULL
        user = MagicMock()
        user.role = UserRole.REGISTERED
        services.user = MagicMock()
        services.user.get_user = AsyncMock(return_value=Result.ok(user))
        _exhaust_quota(_CALLER)

        resp = await _call_insight_route(services)

        assert isinstance(resp, JSONResponse)
        assert resp.status_code == 403
        assert b"paid subscription" in resp.body
        assert LLM_QUOTA_MESSAGE.encode() not in resp.body
        assert ai.called is False

    async def test_member_passes_tier_gate_then_quota_applies(self) -> None:
        ai = _FakeAI()
        services = _Services(tasks=_FakeFacade(owns=True, ai=ai))
        services.intelligence_tier = IntelligenceTier.FULL
        user = MagicMock()
        user.role = UserRole.MEMBER
        services.user = MagicMock()
        services.user.get_user = AsyncMock(return_value=Result.ok(user))
        _exhaust_quota(_CALLER)

        resp = await _call_insight_route(services)

        assert isinstance(resp, JSONResponse)
        assert resp.status_code == 403
        assert LLM_QUOTA_MESSAGE.encode() in resp.body
        assert ai.called is False
