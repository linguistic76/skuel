"""The ``/profile`` hub is retired; only the Shared With Me inbox keeps the prefix.

``GET /profile`` is a real 404 through the app — no route, no redirect: every
hub tab has its own door (Tasks+ → ``/today``, Library → ``/library``,
Submissions → ``/submissions``, Reports → ``/gradebook``). ``/profile/shared``
and its list fragment stay at their URLs and read the sharing service
directly — the inbox filters cross that boundary typed and untouched.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

import adapters.inbound.user_profile_ui as profile_module
from adapters.inbound.user_profile_ui import setup_user_profile_routes
from core.models.enums.entity_enums import EntityType
from core.utils.result_simplified import Errors, Result


def _fake_authenticated_user(request: object) -> str:
    return "user_test"


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, MagicMock]:
    monkeypatch.setattr(profile_module, "require_authenticated_user", _fake_authenticated_user)
    services = MagicMock()
    services.sharing.get_shared_with_me = AsyncMock(return_value=Result.ok([]))
    app, rt = fast_app(pico=False, default_hdrs=False)
    setup_user_profile_routes(rt, services)
    return TestClient(app), services.sharing


def test_the_profile_hub_is_a_real_404_not_a_redirect(
    harness: tuple[TestClient, MagicMock],
) -> None:
    client, _ = harness
    response = client.get("/profile", follow_redirects=False)

    assert response.status_code == 404
    assert "location" not in response.headers


def test_shared_with_me_renders_from_the_sharing_service(
    harness: tuple[TestClient, MagicMock],
) -> None:
    client, sharing = harness
    response = client.get("/profile/shared")

    assert response.status_code == 200
    assert "Shared With Me" in response.text
    sharing.get_shared_with_me.assert_awaited_once_with(
        user_uid="user_test", limit=50, entity_type=None, sharer_uid=None
    )


def test_list_fragment_forwards_the_inbox_filters_typed(
    harness: tuple[TestClient, MagicMock],
) -> None:
    """The Type · Shared-by filters reach the service as EntityType / UserUID."""
    client, sharing = harness
    response = client.get(
        "/profile/shared/list-fragment?entity_type=entry_report&sharer=user_admin",
        headers={"HX-Request": "true"},
    )

    assert response.status_code == 200
    sharing.get_shared_with_me.assert_awaited_once_with(
        user_uid="user_test",
        limit=50,
        entity_type=EntityType.ENTRY_REPORT,
        sharer_uid="user_admin",
    )


def test_a_failed_read_renders_an_error_never_an_empty_inbox(
    harness: tuple[TestClient, MagicMock],
) -> None:
    client, sharing = harness
    sharing.get_shared_with_me.return_value = Result.fail(Errors.database("read", "down"))
    response = client.get("/profile/shared")

    assert response.status_code == 200
    assert "Could not load your shared items" in response.text


# --- the insight cards' entity links (the hub's ``/profile/{domain}?focus=`` door is gone) ---


def _insight(domain: str, entity_uid: str):
    from datetime import datetime

    from core.models.insight.persisted_insight import (
        InsightImpact,
        InsightType,
        PersistedInsight,
    )

    return PersistedInsight(
        uid=f"insight.test.{entity_uid}",
        user_uid="user_test",
        insight_type=InsightType.COMPLETION_PATTERN,
        domain=domain,
        title="t",
        description="d",
        confidence=0.9,
        impact=InsightImpact.LOW,
        entity_uid=entity_uid,
        created_at=datetime(2026, 9, 19),
    )


@pytest.mark.parametrize(
    ("domain", "uid", "expected"),
    [
        ("tasks", "task_1", "/tasks/detail?uid=task_1"),
        ("goals", "goal_1", "/goals/detail?uid=goal_1"),
        ("habits", "habit_1", "/habits/detail?uid=habit_1"),
        ("events", "event_1", "/events/detail?uid=event_1"),
        ("choices", "choice_1", "/choices/detail?uid=choice_1"),
        ("principles", "principle_1", "/principles/detail?uid=principle_1"),
        ("user_entry", "ue_1", "/gradebook/ue_1"),
    ],
)
def test_insight_cards_link_to_the_entity_detail_page(domain: str, uid: str, expected: str) -> None:
    from fasthtml.common import to_xml

    from ui.insights.insight_card import InsightCard

    html = to_xml(InsightCard(_insight(domain, uid)))
    assert f'href="{expected}"' in html
    assert "/profile/" not in html


def test_an_insight_without_an_entity_renders_no_entity_link() -> None:
    from fasthtml.common import to_xml

    from ui.insights.insight_card import InsightCard

    assert "View Entity" not in to_xml(InsightCard(_insight("user_entry", "")))
