"""Regression guard for the AI-route ownership gate (cross-user IDOR fix).

The AI routes (`adapters/inbound/ai_routes.py`) previously authenticated the caller
but never verified ownership of the entity uid they operated on. Because the routes
are GET (CSRF-exempt), any authenticated user could `GET /api/tasks/ai/insight?uid=
<victim_task_uid>` and receive AI-generated content derived from another user's
PRIVATE entity (and spend LLM budget on it).

The fix threads the authenticated ``user_uid``, the route's ``ContentScope``, and an
explicit ``entity_uid`` into ``_ai_route``. USER_OWNED routes are gated through
``verify_entity_ownership`` (404, not 403, so the uid's existence is not confirmed);
SHARED curriculum routes (ps/lp) stay ungated. Scope is an enum on each ``AIRouteSpec``
and defaults to the fail-closed USER_OWNED — a new route is owner-gated until it
explicitly opts into SHARED.

These tests exercise ``_ai_route`` directly with fakes (no live Neo4j / FastHTML).
"""

import pytest
from starlette.responses import JSONResponse

import adapters.inbound.ai_routes as ai_routes
from adapters.inbound.ai_routes import AI_ROUTE_SPECS, _ai_route
from adapters.inbound.rate_limit import reset_buckets_for_testing
from core.models.enums import ContentScope
from core.utils.result_simplified import Errors, Result

_CALLER = "user_alice"
_ACTIVITY_DOMAINS = {"tasks", "goals", "habits", "events", "choices", "principles"}
_CURRICULUM_DOMAINS = {"ps", "lp"}


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
    intelligence_tier = None  # None → skip per-user tier gate in _ai_route

    def __init__(self, **facades: object) -> None:
        for name, facade in facades.items():
            setattr(self, name, facade)


def _fixed_caller(_request: object) -> str:
    return _CALLER


@pytest.fixture(autouse=True)
def _stub_auth(monkeypatch: pytest.MonkeyPatch):
    # require_authenticated_user reads the signed session cookie in production;
    # stub it so _ai_route sees an authenticated caller without a live request.
    monkeypatch.setattr(ai_routes, "require_authenticated_user", _fixed_caller)
    # _ai_route records daily-quota units per successful gate pass — clean
    # buckets so tests never accumulate against the shared _CALLER.
    reset_buckets_for_testing()
    yield
    reset_buckets_for_testing()


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
        scope=ContentScope.USER_OWNED,
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
        scope=ContentScope.USER_OWNED,
        entity_uid="task_mine",
        wrap_key="insight",
    )

    assert facade.verify_ownership_called is True
    assert ai.called is True
    assert resp == {"insight": {"method": "generate_task_insight"}}


async def test_shared_scope_skips_ownership() -> None:
    """SHARED curriculum routes (ps/lp) are public-read — ownership is not consulted."""
    ai = _FakeAI()
    # owns=False would deny if checked; the SHARED gate must not consult it.
    facade = _FakeFacade(owns=False, ai=ai)
    services = _Services(ps=facade)

    resp = await _ai_route(
        object(),
        services,
        "ps",
        "Knowledge",
        "generate_summary",
        ("ps_public",),
        scope=ContentScope.SHARED,
        entity_uid="ps_public",
        wrap_key="summary",
    )

    assert facade.verify_ownership_called is False
    assert ai.called is True
    assert resp == {"summary": {"method": "generate_summary"}}


async def test_user_owned_query_route_skips_ownership() -> None:
    """USER_OWNED but entity_uid=None (query routes) → no single entity to gate."""
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
        scope=ContentScope.USER_OWNED,
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
        scope=ContentScope.USER_OWNED,
        entity_uid="task_mine",
        wrap_key="insight",
    )

    assert isinstance(resp, JSONResponse)
    assert resp.status_code == 503
    assert facade.verify_ownership_called is False


async def test_ai_route_default_scope_is_user_owned() -> None:
    """_ai_route defaults to the fail-closed USER_OWNED scope (gate on by default)."""
    ai = _FakeAI()
    facade = _FakeFacade(owns=False, ai=ai)
    services = _Services(tasks=facade)

    # No scope argument → must behave as USER_OWNED → non-owner denied.
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
    assert ai.called is False


def test_spec_scopes_match_ownership_model() -> None:
    """Curriculum (ps/lp) specs are SHARED; every Activity-Domain spec is USER_OWNED."""
    for spec in AI_ROUTE_SPECS:
        if spec.domain_attr in _CURRICULUM_DOMAINS:
            assert spec.scope is ContentScope.SHARED, (
                f"{spec.func_name}: curriculum route must be SHARED (public-read)"
            )
        elif spec.domain_attr in _ACTIVITY_DOMAINS:
            assert spec.scope is ContentScope.USER_OWNED, (
                f"{spec.func_name}: Activity-Domain route must be USER_OWNED (owner-gated)"
            )
        else:  # pragma: no cover - guards an unmapped future domain
            pytest.fail(f"{spec.func_name}: unmapped AI domain {spec.domain_attr!r}")


def test_every_user_owned_spec_carries_a_uid_signature() -> None:
    """Invariant the ownership gate relies on: every USER_OWNED AI route keys on an
    entity uid (uid / uid_limit / uid_level). A query-based USER_OWNED route would
    bypass the uid gate and must instead scope by user_uid inside the service."""
    uid_signatures = {"uid", "uid_limit", "uid_level"}
    offenders = [
        spec.func_name
        for spec in AI_ROUTE_SPECS
        if spec.scope is ContentScope.USER_OWNED and spec.signature not in uid_signatures
    ]
    assert offenders == [], (
        f"USER_OWNED AI routes without a uid signature bypass the ownership gate: {offenders}"
    )
