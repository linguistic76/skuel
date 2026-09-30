"""The HTTP contract of the AI routes, through a ``TestClient``.

``adapters/inbound/ai_routes.py`` registers one route per ``AIRouteSpec``. Every one
spends LLM or embeddings money, so the door is ``POST`` only and CSRF-protected, and
the AI method's ``Result`` is answered through the boundary's mapping. This file pins:

- registration refuses a spec that names nothing (``create_ai_routes`` raises), and the
  live ``AI_ROUTE_SPECS`` all resolve;
- every spec whose method does not return a dict carries a ``wrap_key``, and a value
  of any type is answered as JSON — never as a rendered page;
- ``GET`` and ``HEAD`` answer 405 and spend no quota unit; a ``POST`` without a CSRF
  token is refused before any gate runs;
- a failed ``Result`` answers the status of its category with the client-safe error
  dict — no capture site, no file path;
- ``/api/ai/status`` stays a ``GET``.

The gates themselves (tier, ownership, quota order) are pinned by direct ``_ai_route``
calls in ``tests/unit/test_ai_routes_ownership.py`` and
``tests/unit/adapters/test_llm_quota_gate.py``.
"""

from __future__ import annotations

import typing
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

import adapters.inbound.ai_routes as ai_routes
from adapters.inbound.ai_routes import (
    AI_ROUTE_SPECS,
    AI_SERVICE_CLASSES,
    AIRouteSpec,
    create_ai_routes,
    unresolved_ai_route_specs,
)
from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from core.utils.result_simplified import ErrorContext, Errors, Result

_CALLER = "user_http"


def _fixed_caller(_request: object) -> str:
    return _CALLER


class _QuotaLedger:
    """Counts the quota units ``_ai_route`` would record."""

    def __init__(self) -> None:
        self.units = 0

    def allow(self, _user_uid: str) -> bool:
        self.units += 1
        return True


def _facade(ai: object | None) -> SimpleNamespace:
    return SimpleNamespace(ai=ai, verify_ownership=AsyncMock(return_value=Result.ok({"uid": "g1"})))


def _services(goals_ai: object | None = None) -> SimpleNamespace:
    names = ("tasks", "goals", "habits", "events", "choices", "principles", "ps", "lp")
    container = SimpleNamespace(**{name: _facade(None) for name in names})
    container.goals = _facade(goals_ai)
    container.intelligence_tier = None  # skip the per-user tier gate
    container.user = None
    return container


def _client(services: SimpleNamespace) -> TestClient:
    app, rt = fast_app()
    create_ai_routes(app, rt, services)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def ledger(monkeypatch: pytest.MonkeyPatch) -> _QuotaLedger:
    monkeypatch.setattr(ai_routes, "require_authenticated_user", _fixed_caller)
    ledger = _QuotaLedger()
    monkeypatch.setattr(ai_routes, "llm_quota_allowed", ledger.allow)
    return ledger


@pytest.fixture
def csrf() -> tuple[dict[str, str], dict[str, str]]:
    """``(cookies, headers)`` carrying one matching CSRF token pair."""
    token = mint_token()
    return {CSRF_COOKIE_NAME: token}, {CSRF_HEADER_NAME: token}


def _post(
    client: TestClient, path: str, csrf: tuple[dict[str, str], dict[str, str]], **params: str
) -> typing.Any:  # boundary: httpx.Response
    cookies, headers = csrf
    for name, value in cookies.items():
        client.cookies.set(name, value)
    return client.post(path, params=params, headers=headers)


# ============================================================================
# Registration: every spec resolves
# ============================================================================


def test_live_specs_all_resolve() -> None:
    assert unresolved_ai_route_specs(AI_ROUTE_SPECS) == []


def test_registration_refuses_a_spec_naming_no_method(monkeypatch: pytest.MonkeyPatch) -> None:
    ghost = AIRouteSpec(
        "tasks", "Tasks", "tasks", "ghost", "no_such_method", "uid", "tasks_ai_ghost"
    )
    monkeypatch.setattr(ai_routes, "AI_ROUTE_SPECS", [*AI_ROUTE_SPECS, ghost])
    app, rt = fast_app()

    with pytest.raises(ValueError, match="no_such_method"):
        create_ai_routes(app, rt, _services())

    assert not any(route.path == "/api/tasks/ai/ghost" for route in app.routes)


def test_unresolved_names_unknown_domain_and_signature() -> None:
    bad_domain = AIRouteSpec("finance", "Finance", "finance", "x", "m", "uid", "finance_ai_x")
    bad_signature = AIRouteSpec(
        "tasks", "Tasks", "tasks", "x", "find_similar_tasks", "query_limit", "t"
    )

    unresolved = unresolved_ai_route_specs([bad_domain, bad_signature])

    assert len(unresolved) == 2
    assert "no AI class for domain 'finance'" in unresolved[0]
    assert "unknown signature 'query_limit'" in unresolved[1]


def test_func_names_are_unique() -> None:
    """FastHTML names each route after its function; a repeat would shadow a route name."""
    names = [spec.func_name for spec in AI_ROUTE_SPECS]
    assert len(names) == len(set(names))


def test_every_non_dict_method_has_a_wrap_key() -> None:
    """A dict is a JSON object on its own; any other value is wrapped as {wrap_key: value}
    so the body names what it carries. Read from each method's return annotation."""
    offenders: list[str] = []
    for spec in AI_ROUTE_SPECS:
        method = getattr(AI_SERVICE_CLASSES[spec.domain_attr], spec.method_name)
        inner = typing.get_args(typing.get_type_hints(method)["return"])[0]
        origin = typing.get_origin(inner) or inner
        returns_dict = origin is dict or (isinstance(inner, type) and typing.is_typeddict(inner))
        if not returns_dict and spec.wrap_key is None:
            offenders.append(f"{spec.func_name} returns {inner}")
    assert offenders == []


# ============================================================================
# Verbs and CSRF
# ============================================================================


def test_get_and_head_answer_405_and_spend_nothing(ledger: _QuotaLedger) -> None:
    client = _client(_services(SimpleNamespace(generate_goal_insight=AsyncMock())))

    assert client.get("/api/goals/ai/insight", params={"uid": "g1"}).status_code == 405
    assert client.head("/api/goals/ai/insight", params={"uid": "g1"}).status_code == 405
    assert ledger.units == 0


def test_post_without_csrf_token_is_refused_before_the_gates(ledger: _QuotaLedger) -> None:
    ai = SimpleNamespace(generate_goal_insight=AsyncMock(return_value=Result.ok("text")))
    client = _client(_services(ai))

    response = client.post("/api/goals/ai/insight", params={"uid": "g1"})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_INVALID"
    assert ledger.units == 0
    ai.generate_goal_insight.assert_not_awaited()


def test_every_registered_ai_route_is_post_only() -> None:
    app, rt = fast_app()
    create_ai_routes(app, rt, _services())

    ai_routes_registered = [
        route for route in app.routes if "/ai/" in route.path and route.path != "/api/ai/status"
    ]

    assert len(ai_routes_registered) == len(AI_ROUTE_SPECS)
    assert all(list(route.methods) == ["POST"] for route in ai_routes_registered)


def test_status_endpoint_is_a_get(ledger: _QuotaLedger) -> None:
    client = _client(_services())

    response = client.get("/api/ai/status")

    assert response.status_code == 200
    assert response.json() == {
        "ai_available": {
            "tasks": False,
            "goals": False,
            "habits": False,
            "events": False,
            "choices": False,
            "principles": False,
            "path_steps": False,
            "learning_paths": False,
        }
    }
    assert client.post("/api/ai/status").status_code == 405
    assert ledger.units == 0


# ============================================================================
# Success shapes: always JSON
# ============================================================================


def test_dict_return_is_the_body(
    ledger: _QuotaLedger, csrf: tuple[dict[str, str], dict[str, str]]
) -> None:
    ai = SimpleNamespace(
        suggest_achievement_strategy=AsyncMock(return_value=Result.ok({"goal_uid": "g1"}))
    )
    client = _client(_services(ai))

    response = _post(client, "/api/goals/ai/strategy", csrf, uid="g1")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"goal_uid": "g1"}
    assert ledger.units == 1


def test_list_return_is_wrapped_json(
    ledger: _QuotaLedger, csrf: tuple[dict[str, str], dict[str, str]]
) -> None:
    ai = SimpleNamespace(
        generate_milestones=AsyncMock(return_value=Result.ok([{"title": "m1"}, {"title": "m2"}]))
    )
    client = _client(_services(ai))

    response = _post(client, "/api/goals/ai/milestones", csrf, uid="g1")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"milestones": [{"title": "m1"}, {"title": "m2"}]}


def test_string_return_is_wrapped_json(
    ledger: _QuotaLedger, csrf: tuple[dict[str, str], dict[str, str]]
) -> None:
    ai = SimpleNamespace(generate_goal_insight=AsyncMock(return_value=Result.ok("plain text")))
    client = _client(_services(ai))

    response = _post(client, "/api/goals/ai/insight", csrf, uid="g1")

    assert response.status_code == 200
    assert response.json() == {"insight": "plain text"}


def test_similarity_tuples_are_json_arrays(
    ledger: _QuotaLedger, csrf: tuple[dict[str, str], dict[str, str]]
) -> None:
    ai = SimpleNamespace(
        find_similar_goals=AsyncMock(return_value=Result.ok([("goal_b", 0.91), ("goal_c", 0.8)]))
    )
    client = _client(_services(ai))

    response = _post(client, "/api/goals/ai/similar", csrf, uid="g1", limit="2")

    assert response.status_code == 200
    assert response.json() == {"similar_goals": [["goal_b", 0.91], ["goal_c", 0.8]]}
    ai.find_similar_goals.assert_awaited_once_with("g1", 2)


def test_an_unwrapped_list_is_still_json(
    ledger: _QuotaLedger,
    csrf: tuple[dict[str, str], dict[str, str]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wrap_key names the body; the JSON answer does not depend on it. A spec without
    one whose method returns a list must never reach FastHTML's page renderer."""
    bare = AIRouteSpec(
        "goals",
        "Goals",
        "goals",
        "milestones",
        "generate_milestones",
        "uid",
        "goals_ai_milestones_bare",
    )
    monkeypatch.setattr(ai_routes, "AI_ROUTE_SPECS", [bare])
    ai = SimpleNamespace(generate_milestones=AsyncMock(return_value=Result.ok([{"title": "m1"}])))
    client = _client(_services(ai))

    response = _post(client, "/api/goals/ai/milestones", csrf, uid="g1")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == [{"title": "m1"}]


# ============================================================================
# Failure mapping: the boundary's status per category, the client dict as body
# ============================================================================


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (Errors.not_found(resource="Goal", identifier="g1"), 404, "NOT_FOUND_GOAL"),
        (Errors.validation("Text cannot be empty", field="text"), 400, "VALIDATION_FIELD_TEXT"),
        (
            Errors.integration(message="LLM generation failed: boom", service="llm"),
            502,
            "INTEGRATION_LLM",
        ),
        (Errors.database(operation="get", message="connection lost"), 503, "DB_GET"),
        (
            Errors.unavailable(
                feature="ai_insights", reason="LLM service not configured", operation="x"
            ),
            500,
            "UNAVAILABLE_AI_INSIGHTS",
        ),
    ],
    ids=["not_found", "validation", "integration", "database", "unavailable"],
)
def test_failed_result_answers_its_category(
    ledger: _QuotaLedger,
    csrf: tuple[dict[str, str], dict[str, str]],
    error: ErrorContext,
    status: int,
    code: str,
) -> None:
    ai = SimpleNamespace(generate_goal_insight=AsyncMock(return_value=Result.fail(error)))
    client = _client(_services(ai))

    response = _post(client, "/api/goals/ai/insight", csrf, uid="g1")

    assert response.status_code == status
    body = response.json()
    assert body["code"] == code
    assert set(body) == {"category", "code", "message", "severity", "timestamp"}
    # The client dict carries no capture site: no path, no module, no line.
    assert "/" not in body["message"]
    assert ".py" not in response.text
    assert response.headers["X-Toast-Type"] == "error"


def test_shared_spec_skips_ownership_over_http(
    ledger: _QuotaLedger, csrf: tuple[dict[str, str], dict[str, str]]
) -> None:
    ai = SimpleNamespace(explain_step=AsyncMock(return_value=Result.ok("an explanation")))
    services = _services()
    services.ps = SimpleNamespace(ai=ai, verify_ownership=AsyncMock())
    client = _client(services)

    response = _post(client, "/api/path-steps/ai/explain", csrf, uid="ps1")

    assert response.status_code == 200
    assert response.json() == {"explanation": "an explanation"}
    services.ps.verify_ownership.assert_not_awaited()
    # the level the handler passes when the request names none
    ai.explain_step.assert_awaited_once_with("ps1", "intermediate")
