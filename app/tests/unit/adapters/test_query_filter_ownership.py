"""Every goal/habit filter route checks the anchor's owner before it reads.

``GET /api/{domain}/goal?goal_uid=…`` and ``/habit?habit_uid=…`` come from
``CommonQueryRouteFactory``, registered by ``register_domain_routes`` for each
config whose ``QueryRouteConfig`` turns the filter on. A goal or habit the caller
does not own answers 404 — missing and foreign alike — and the domain service is
never asked. The cases are derived from the live configs, so a domain that turns
on a filter is checked the moment it does.

The factory refuses at construction a filter turned on without the service that
checks its anchor, so the check cannot be skipped silently.
"""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.route_factories import DomainRouteConfig, register_domain_routes
from adapters.inbound.route_factories.query_route_factory import CommonQueryRouteFactory
from core.utils.result_simplified import Errors, Result
from tests.helpers.route_configs import collect_module_configs

_USER_UID = "user_caller"
_ANCHOR_UID = "anchor_1"

# (anchor word, Services attribute that owns the anchor)
_FILTERS = {"goal": "goals", "habit": "habits"}


def _filter_cases() -> list[tuple[str, DomainRouteConfig, str]]:
    configs, _ = collect_module_configs()
    cases: list[tuple[str, DomainRouteConfig, str]] = []
    for _module, name, config in configs:
        if config.query is None:
            continue
        if config.query.supports_goal_filter:
            cases.append((name, config, "goal"))
        if config.query.supports_habit_filter:
            cases.append((name, config, "habit"))
    return cases


_CASES = _filter_cases()


def test_the_derived_cases_cover_the_known_filters() -> None:
    """Control: derivation found the filters the Activity configs declare today."""
    found = {(name, anchor) for name, _config, anchor in _CASES}
    assert {
        ("TASKS_CONFIG", "goal"),
        ("TASKS_CONFIG", "habit"),
        ("EVENTS_CONFIG", "habit"),
        ("PRINCIPLES_CONFIG", "goal"),
    } <= found


def _fake_auth(_request: object) -> str:
    return _USER_UID


def _noop_api_factory(*_args: object, **_kwargs: object) -> None:
    pass


def _anchor_service(*, owned: bool) -> MagicMock:
    service = MagicMock()
    verdict = Result.ok(True) if owned else Result.fail(Errors.not_found("anchor", _ANCHOR_UID))
    service.verify_ownership = AsyncMock(return_value=verdict)
    return service


def _client(
    monkeypatch: pytest.MonkeyPatch, config: DomainRouteConfig, anchor: str, *, owned: bool
) -> tuple[TestClient, AsyncMock, MagicMock]:
    """Register only the config's query routes over a services stand-in."""
    monkeypatch.setattr(
        "adapters.inbound.route_factories.query_route_factory.require_authenticated_user",
        _fake_auth,
    )
    app, rt = fast_app(pico=False, default_hdrs=False)

    read = AsyncMock(return_value=Result.ok([]))
    primary = MagicMock()
    setattr(primary, f"get_{config.domain_name}_for_{anchor}", read)

    anchors = {attr: _anchor_service(owned=True) for attr in _FILTERS.values()}
    anchors[_FILTERS[anchor]] = _anchor_service(owned=owned)
    attributes: dict[str, object] = dict.fromkeys(config.api_related_services.values())
    attributes.update(anchors)
    attributes["user"] = MagicMock()
    attributes[config.primary_service_attr] = primary
    services = SimpleNamespace(**attributes)

    query_only = dataclasses.replace(
        config, crud=None, intelligence=None, ui_factory=None, api_factory=_noop_api_factory
    )
    register_domain_routes(app, rt, services, query_only)
    return TestClient(app), read, anchors[_FILTERS[anchor]]


@pytest.mark.parametrize(
    ("name", "config", "anchor"), _CASES, ids=[f"{n}-{a}" for n, _c, a in _CASES]
)
def test_a_foreign_anchor_is_404_and_the_domain_is_not_read(
    monkeypatch: pytest.MonkeyPatch, name: str, config: DomainRouteConfig, anchor: str
) -> None:
    client, read, anchor_service = _client(monkeypatch, config, anchor, owned=False)

    response = client.get(
        f"/api/{config.domain_name}/{anchor}", params={f"{anchor}_uid": _ANCHOR_UID}
    )

    assert response.status_code == 404, f"{name}: {response.status_code} {response.text[:200]}"
    anchor_service.verify_ownership.assert_awaited_once_with(_ANCHOR_UID, _USER_UID)
    read.assert_not_awaited()


@pytest.mark.parametrize(
    ("name", "config", "anchor"), _CASES, ids=[f"{n}-{a}" for n, _c, a in _CASES]
)
def test_an_owned_anchor_reads_the_domain(
    monkeypatch: pytest.MonkeyPatch, name: str, config: DomainRouteConfig, anchor: str
) -> None:
    client, read, _anchor_service = _client(monkeypatch, config, anchor, owned=True)

    response = client.get(
        f"/api/{config.domain_name}/{anchor}", params={f"{anchor}_uid": _ANCHOR_UID}
    )

    assert response.status_code == 200, f"{name}: {response.status_code} {response.text[:200]}"
    read.assert_awaited_once_with(_ANCHOR_UID, user_uid=_USER_UID)


@pytest.mark.parametrize(
    ("flag", "service"),
    [("supports_goal_filter", "goals_service"), ("supports_habit_filter", "habits_service")],
)
def test_a_filter_without_its_anchor_service_is_refused(flag: str, service: str) -> None:
    with pytest.raises(ValueError, match=service):
        CommonQueryRouteFactory(service=MagicMock(), domain_name="principles", **{flag: True})
