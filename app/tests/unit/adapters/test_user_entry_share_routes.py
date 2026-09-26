"""The Share / Stop-sharing routes (Submit & Share arc PR 6b).

``POST /api/user-entries/{uid}/share`` and ``/unshare`` are CSRF-protected,
owner-only doors over ``EntrySharingService``: the vocabulary is parsed at
the door, an HTMX request reads back a fragment (the Share panel, the wall
row), any other caller JSON. Harness mirrors ``test_user_entry_api_routes.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.user_entry_api import create_user_entry_api_routes
from core.models.entity_dto import EntityDTO
from core.services.user_entry.audience_resolver import ShareOutcome
from core.utils.result_simplified import Errors, Result

_USER_UID = "user_owner"
_ENTRY_UID = "ue_1"

_CANDIDATES = {
    "groups": [{"uid": "g_1", "name": "Physics 101"}],
    "people": [{"uid": "user_a", "username": "alice", "display_name": "Alice"}],
    "shared_group_uids": [],
    "shared_user_uids": [],
}


def _fake_auth(request: object) -> str:
    return _USER_UID


@dataclass(frozen=True)
class _Harness:
    client: TestClient
    sharing: MagicMock


def _make_harness(monkeypatch: pytest.MonkeyPatch, *, with_sharing: bool = True) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)
    entries = MagicMock()
    sharing = MagicMock()
    sharing.share = AsyncMock(
        return_value=Result.ok(
            ShareOutcome(
                shared_groups=("g_1",), shared_users=("user_a",), newly_shared_users=("user_a",)
            )
        )
    )
    sharing.unshare = AsyncMock(return_value=Result.ok("user:alice"))
    sharing.candidates = AsyncMock(return_value=Result.ok(_CANDIDATES))
    sharing.wall_row = AsyncMock(return_value=Result.ok(None))
    monkeypatch.setattr("adapters.inbound.user_entry_api.require_authenticated_user", _fake_auth)
    create_user_entry_api_routes(None, rt, entries, entry_sharing=sharing if with_sharing else None)
    return _Harness(client=TestClient(app), sharing=sharing)


def _csrf(client: TestClient) -> dict[str, str]:
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return {CSRF_HEADER_NAME: token}


class TestShare:
    def test_without_csrf_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        h = _make_harness(monkeypatch)
        response = h.client.post(
            f"/api/user-entries/{_ENTRY_UID}/share", json={"audience": "group:g_1"}
        )
        assert response.status_code == 403
        h.sharing.share.assert_not_awaited()

    def test_json_body_shares_and_returns_the_outcome(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        h = _make_harness(monkeypatch)
        response = h.client.post(
            f"/api/user-entries/{_ENTRY_UID}/share",
            json={"audience": ["group:g_1", "user:alice"]},
            headers=_csrf(h.client),
        )
        assert response.status_code == 200
        assert response.json()["share_outcome"]["newly_shared_users"] == ["user_a"]
        args = h.sharing.share.await_args.args
        assert args[0] == _ENTRY_UID and args[1] == _USER_UID
        assert args[2].share_groups == ("g_1",) and args[2].share_users == ("alice",)

    def test_form_post_from_the_panel_reads_back_the_panel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        h = _make_harness(monkeypatch)
        response = h.client.post(
            f"/api/user-entries/{_ENTRY_UID}/share",
            data={"audience": ["group:g_1", "user:alice"]},
            headers={**_csrf(h.client), "HX-Request": "true"},
        )
        assert response.status_code == 200
        assert "Shared with 2 targets" in response.text
        assert f'hx-post="/api/user-entries/{_ENTRY_UID}/share"' in response.text
        h.sharing.candidates.assert_awaited_once()

    def test_a_bad_vocabulary_value_is_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        h = _make_harness(monkeypatch)
        response = h.client.post(
            f"/api/user-entries/{_ENTRY_UID}/share",
            json={"audience": "nonsense"},
            headers=_csrf(h.client),
        )
        assert response.status_code == 400
        h.sharing.share.assert_not_awaited()

    def test_a_refusal_on_htmx_reads_back_the_panel_with_the_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        h = _make_harness(monkeypatch)
        h.sharing.share = AsyncMock(
            return_value=Result.fail(
                Errors.validation("A private entry cannot be shared", field="audience")
            )
        )
        response = h.client.post(
            f"/api/user-entries/{_ENTRY_UID}/share",
            data={"audience": "user:alice"},
            headers={**_csrf(h.client), "HX-Request": "true"},
        )
        assert response.status_code == 200
        assert "A private entry cannot be shared" in response.text

    def test_not_owner_is_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        h = _make_harness(monkeypatch)
        h.sharing.share = AsyncMock(
            return_value=Result.fail(Errors.not_found(resource="UserEntry", identifier=_ENTRY_UID))
        )
        response = h.client.post(
            f"/api/user-entries/{_ENTRY_UID}/share",
            json={"audience": "user:alice"},
            headers=_csrf(h.client),
        )
        assert response.status_code == 404
        htmx = h.client.post(
            f"/api/user-entries/{_ENTRY_UID}/share",
            data={"audience": "user:alice"},
            headers={**_csrf(h.client), "HX-Request": "true"},
        )
        assert htmx.status_code == 404

    def test_without_the_service_is_unavailable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        h = _make_harness(monkeypatch, with_sharing=False)
        response = h.client.post(
            f"/api/user-entries/{_ENTRY_UID}/share",
            json={"audience": "user:alice"},
            headers=_csrf(h.client),
        )
        assert response.status_code >= 500


class TestUnshare:
    def test_json_unshare_returns_the_removed_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        h = _make_harness(monkeypatch)
        response = h.client.post(
            f"/api/user-entries/{_ENTRY_UID}/unshare",
            json={"audience": "user:alice"},
            headers=_csrf(h.client),
        )
        assert response.status_code == 200
        assert response.json() == {"uid": _ENTRY_UID, "removed": "user:alice"}
        h.sharing.unshare.assert_awaited_once_with(_ENTRY_UID, _USER_UID, "user:alice")

    def test_htmx_unshare_reads_back_the_wall_row_or_nothing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        h = _make_harness(monkeypatch)
        empty = h.client.post(
            f"/api/user-entries/{_ENTRY_UID}/unshare?audience=user:alice",
            headers={**_csrf(h.client), "HX-Request": "true"},
        )
        assert empty.status_code == 200
        assert empty.text.strip() == ""

        h.sharing.wall_row = AsyncMock(
            return_value=Result.ok(
                {
                    "entity": EntityDTO.from_dict(
                        {"uid": _ENTRY_UID, "entity_type": "user_entry", "title": "Mine"}
                    ),
                    "users": [],
                    "groups": [{"uid": "g_1", "name": "Physics 101", "shared_at": None}],
                    "last_shared_at": None,
                }
            )
        )
        row = h.client.post(
            f"/api/user-entries/{_ENTRY_UID}/unshare?audience=user:alice",
            headers={**_csrf(h.client), "HX-Request": "true"},
        )
        assert row.status_code == 200
        assert f'data-wall-row="{_ENTRY_UID}"' in row.text
        assert "Physics 101" in row.text

    def test_two_values_are_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        h = _make_harness(monkeypatch)
        response = h.client.post(
            f"/api/user-entries/{_ENTRY_UID}/unshare",
            json={"audience": ["user:alice", "group:g_1"]},
            headers=_csrf(h.client),
        )
        assert response.status_code == 400
        h.sharing.unshare.assert_not_awaited()

    def test_not_owner_is_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        h = _make_harness(monkeypatch)
        h.sharing.unshare = AsyncMock(
            return_value=Result.fail(Errors.not_found(resource="UserEntry", identifier=_ENTRY_UID))
        )
        response = h.client.post(
            f"/api/user-entries/{_ENTRY_UID}/unshare",
            json={"audience": "user:alice"},
            headers=_csrf(h.client),
        )
        assert response.status_code == 404
