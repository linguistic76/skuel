"""Regression guard for the AI-route ownership gate (cross-user IDOR fix).

The AI routes (`adapters/inbound/ai_routes.py`) previously authenticated the caller
but never verified ownership of the entity uid they operated on. Because the routes
are GET (CSRF-exempt), any authenticated user could `GET /api/tasks/ai/insight?uid=
<victim_task_uid>` and receive AI-generated content derived from another user's
PRIVATE entity (and spend LLM budget on it).

The fix threads the authenticated ``user_uid`` and an explicit ``entity_uid`` into
``_ai_route`` and gates USER_OWNED domains (the 6 Activity Domains) through
``verify_entity_ownership`` — returning 404 (not 403) so the uid's existence is not
confirmed. SHARED curriculum domains (ps/lp) are public-read and stay ungated.

These tests exercise ``_ai_route`` directly with fakes (no live Neo4j / FastHTML).
"""

import pytest
from starlette.responses import JSONResponse

import adapters.inbound.ai_routes as ai_routes
from adapters.inbound.ai_routes import (
    _USER_OWNED_AI_DOMAINS,
    AI_ROUTE_SPECS,
    _ai_route,
)
from core.utils.result_simplified import Errors, Result

_CALLER = "user_alice"


class _FakeAI:
    """Stand-in for a domain ``.ai`` sub-service that records whether it ran."""

    def __init__(self) -> None:
        self.called = False

    def __getattr__(self, name: str):
        # Any method name resolves to a coroutine that flags it was invoked.
        async def _invoke(*_args: object) -> Result[dict]:
            self.called = True
            return Result.ok({"method": name})

        return _invoke


class _FakeFacade:
    """Stand-in for a domain facade exposing ``.ai`` and ``verify_ownership``."""

    def __init__(self, *, owns: bool, ai: _FakeAI | None) -> None:
        self.ai = ai
        self._owns = owns
        self.verify_ownership_called = False

    async def verify_ownership(self, uid: str, user_uid: str) -> Result[dict]:
        self.verify_ownership_called = True
        if self._owns:
            return Result.ok({"uid": uid, "user_uid": user_uid})
        return Result.fail(Errors.not_found("Entity", uid))


class _Services:
    def __init__(self, **facades: object) -> None:
        for name, facade in facades.items():
            setattr(self, name, facade)


def _fixed_caller(_request: object) -> str:
    return _CALLER


@pytest.fixture(autouse=True)
def _stub_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    # require_authenticated_user reads the signed session cookie in production;
    # stub it so _ai_route sees an authenticated caller without a live request.
    monkeypatch.setattr(ai_routes, "require_authenticated_user", _fixed_caller)


async def test_user_owned_route_denies_non_owner() -> None:
    """A USER_OWNED route must 404 (and never call the AI service) for a non-owner."""
    ai = _FakeAI()
    facade = _FakeFacade(owns=False, ai=ai)
    services = _Services(tasks=facade)

    resp = await _ai_route(
        object(),
        services,
        "tasks",
        "Tasks",
        "generate_task_insight",
        ("task_victim",),
        entity_uid="task_victim",
        wrap_key="insight",
    )

    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 404
    assert facade.verify_ownership_called is True
    # The IDOR-critical assertion: the AI method never ran → no data leak, no LLM spend.
    assert ai.called is False


async def test_user_owned_route_allows_owner() -> None:
    """A USER_OWNED route proceeds normally when the caller owns the entity."""
    ai = _FakeAI()
    facade = _FakeFacade(owns=True, ai=ai)
    services = _Services(tasks=facade)

    resp = await _ai_route(
        object(),
        services,
        "tasks",
        "Tasks",
        "generate_task_insight",
        ("task_mine",),
        entity_uid="task_mine",
        wrap_key="insight",
    )

    assert facade.verify_ownership_called is True
    assert ai.called is True
    assert resp == {"insight": {"method": "generate_task_insight"}}


async def test_shared_domain_skips_ownership() -> None:
    """SHARED curriculum domains (ps/lp) are public-read — ownership is not consulted."""
    ai = _FakeAI()
    # owns=False would deny if checked; the gate must not consult it for ps.
    facade = _FakeFacade(owns=False, ai=ai)
    services = _Services(ps=facade)

    resp = await _ai_route(
        object(),
        services,
        "ps",
        "Knowledge",
        "generate_summary",
        ("ps_public",),
        entity_uid="ps_public",
        wrap_key="summary",
    )

    assert facade.verify_ownership_called is False
    assert ai.called is True
    assert resp == {"summary": {"method": "generate_summary"}}


async def test_query_based_route_skips_ownership() -> None:
    """entity_uid=None (query routes) has no single owned entity → no uid gate."""
    ai = _FakeAI()
    facade = _FakeFacade(owns=False, ai=ai)
    services = _Services(tasks=facade)

    resp = await _ai_route(
        object(),
        services,
        "tasks",
        "Tasks",
        "semantic_search",
        ("query text", 10),
        entity_uid=None,
        wrap_key="results",
    )

    assert facade.verify_ownership_called is False
    assert ai.called is True
    assert resp == {"results": {"method": "semantic_search"}}


async def test_ai_unavailable_returns_503_before_ownership() -> None:
    """When the domain has no .ai, return 503 without a (DB-touching) ownership check."""
    facade = _FakeFacade(owns=True, ai=None)
    services = _Services(tasks=facade)

    resp = await _ai_route(
        object(),
        services,
        "tasks",
        "Tasks",
        "generate_task_insight",
        ("task_mine",),
        entity_uid="task_mine",
        wrap_key="insight",
    )

    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 503
    assert facade.verify_ownership_called is False


def test_user_owned_ai_domains_are_the_six_activity_domains() -> None:
    """The owner-scoped set is exactly the Activity Domains; curriculum is excluded."""
    assert frozenset(
        {"tasks", "goals", "habits", "events", "choices", "principles"}
    ) == _USER_OWNED_AI_DOMAINS
    assert "ps" not in _USER_OWNED_AI_DOMAINS
    assert "lp" not in _USER_OWNED_AI_DOMAINS


def test_every_user_owned_spec_carries_a_uid_signature() -> None:
    """Invariant the domain-derived gate relies on: every USER_OWNED AI route keys on
    an entity uid (uid / uid_limit / uid_level). A query-based USER_OWNED route would
    bypass the uid gate and must instead scope by user_uid inside the service."""
    uid_signatures = {"uid", "uid_limit", "uid_level"}
    offenders = [
        spec.func_name
        for spec in AI_ROUTE_SPECS
        if spec.domain_attr in _USER_OWNED_AI_DOMAINS and spec.signature not in uid_signatures
    ]
    assert offenders == [], (
        f"USER_OWNED AI routes without a uid signature bypass the ownership gate: {offenders}"
    )
