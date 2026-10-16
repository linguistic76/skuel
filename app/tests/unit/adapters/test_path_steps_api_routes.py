"""Path Steps API security/wiring pins (adapters/inbound/path_steps_api.py).

PIN tests over the domain-specific PathStep reads — the SEL-category input
guard refusing before the service, the unwired-user-service seam on my-context,
and the prerequisite chain. Every route here reads: a path step is authored
only in the content vault (ADR-091), and the retired write doors are pinned
on the real app by
``tests/integration/routes/test_pathstep_lp_authoring_retired.py``. Harness
mirrors ``test_choices_api_routes.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.path_steps_api import create_path_steps_api_routes
from core.utils.result_simplified import Errors, Result

_USER_UID = "user_admin"
_CHILD_UID = "ps.core.child"


def _fake_auth(request: object) -> str:
    return _USER_UID


@dataclass(frozen=True)
class _Harness:
    client: TestClient
    ps: MagicMock
    user_progress: MagicMock


def _chain_row(
    uid: str,
    title: str,
    distance: int,
    domain: str = "programming",
    entity_type: str = "path_step",
) -> dict[str, object]:
    """A PrerequisiteChainRow stand-in as the service returns (uid/title/domain/type/distance)."""
    return {
        "uid": uid,
        "title": title,
        "domain": domain,
        "entity_type": entity_type,
        "distance": distance,
    }


def _make_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
) -> _Harness:
    app, rt = fast_app(pico=False, default_hdrs=False)

    ps_service = MagicMock()
    ps_service.get_personalized_curriculum = AsyncMock(return_value=Result.ok([]))
    ps_service.relationships.get_related_uids = AsyncMock(return_value=Result.ok([]))
    ps_service.get_prerequisite_chain = AsyncMock(return_value=Result.ok([]))
    # Existence gate for the prerequisite-chain read; default = step exists.
    ps_service.get_step = AsyncMock(
        return_value=Result.ok(SimpleNamespace(uid=_CHILD_UID, title="Child"))
    )

    # Prerequisite-chain mastery source; default = nothing mastered.
    user_progress_service = MagicMock()
    user_progress_service.get_mastered_uids = AsyncMock(return_value=Result.ok(set()))

    if authenticated:
        monkeypatch.setattr(
            "adapters.inbound.path_steps_api.require_authenticated_user", _fake_auth
        )

    create_path_steps_api_routes(
        app,
        rt,
        ps_service,
        user_progress_service=user_progress_service,
    )
    return _Harness(client=TestClient(app), ps=ps_service, user_progress=user_progress_service)


class TestInputGuards:
    def test_invalid_sel_category_refuses_before_service(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get("/api/path-steps/curriculum/not-a-category")

        assert response.status_code == 400
        harness.ps.get_personalized_curriculum.assert_not_awaited()


class TestUserContextSeam:
    def test_my_context_without_user_service_is_500(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        harness.ps.user_service = None

        response = harness.client.get("/api/path-steps/my-context?uid=" + _CHILD_UID)

        assert response.status_code == 500


class TestPrerequisiteChain:
    def test_empty_chain_shape(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get(f"/api/path-steps/prerequisites?step_uid={_CHILD_UID}")

        assert response.status_code == 200
        payload = response.json()
        assert payload["step_uid"] == _CHILD_UID
        assert payload["has_prerequisites"] is False
        assert payload["prerequisites"] == []
        assert payload["total_prerequisites"] == 0
        assert payload["prerequisites_mastered"] == 0
        assert payload["unmet_count"] == 0

    def test_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch, authenticated=False)

        response = harness.client.get(f"/api/path-steps/prerequisites?step_uid={_CHILD_UID}")

        assert response.status_code == 401
        harness.ps.get_prerequisite_chain.assert_not_awaited()

    def test_missing_step_is_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        # Step does not exist → 404, not a valid-looking empty chain.
        harness.ps.get_step = AsyncMock(return_value=Result.ok(None))

        response = harness.client.get("/api/path-steps/prerequisites?step_uid=ps.missing")

        assert response.status_code == 404
        harness.ps.get_prerequisite_chain.assert_not_awaited()

    def test_chain_distance_and_mastery(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        # Diamond deduped upstream → flat rows, nearest-first.
        harness.ps.get_prerequisite_chain = AsyncMock(
            return_value=Result.ok(
                [
                    _chain_row("ps.functions", "Functions", 1),
                    _chain_row("ku.variables", "Variables", 2, entity_type="ku"),
                ]
            )
        )
        # Caller has mastered the nearer prerequisite only.
        harness.user_progress.get_mastered_uids = AsyncMock(
            return_value=Result.ok({"ps.functions"})
        )

        response = harness.client.get(
            f"/api/path-steps/prerequisites?step_uid={_CHILD_UID}&depth=5"
        )

        assert response.status_code == 200
        payload = response.json()
        harness.ps.get_prerequisite_chain.assert_awaited_once_with(_CHILD_UID, max_depth=5)
        assert payload["total_prerequisites"] == 2
        assert payload["prerequisites_mastered"] == 1
        assert payload["unmet_count"] == 1
        assert payload["has_prerequisites"] is True
        assert [p["distance"] for p in payload["prerequisites"]] == [1, 2]
        assert payload["prerequisites"][0] == {
            "uid": "ps.functions",
            "title": "Functions",
            "domain": "programming",
            "entity_type": "path_step",
            "distance": 1,
            "is_mastered": True,
        }
        # A Ku prerequisite is carried with its entity_type and is not mastered.
        assert payload["prerequisites"][1]["entity_type"] == "ku"
        assert payload["prerequisites"][1]["is_mastered"] is False

    def test_mastery_read_error_propagates(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)
        harness.ps.get_prerequisite_chain = AsyncMock(
            return_value=Result.ok([_chain_row("ps.functions", "Functions", 1)])
        )
        # A failing mastery read must fail the request — silently marking every
        # node unmastered would be valid-looking but wrong.
        harness.user_progress.get_mastered_uids = AsyncMock(
            return_value=Result.fail(
                Errors.database(operation="get_mastered_uids", message="read failed")
            )
        )

        response = harness.client.get(f"/api/path-steps/prerequisites?step_uid={_CHILD_UID}")

        # Database error propagates (503), not a fake-200 with everything unmastered.
        assert response.status_code == 503

    def test_depth_clamped_to_max(self, monkeypatch: pytest.MonkeyPatch) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get(
            f"/api/path-steps/prerequisites?step_uid={_CHILD_UID}&depth=99"
        )

        assert response.status_code == 200
        # The route clamps to the 1-10 ceiling; the service and the report agree.
        harness.ps.get_prerequisite_chain.assert_awaited_once_with(_CHILD_UID, max_depth=10)
        assert response.json()["depth"] == 10

    @pytest.mark.parametrize("depth", ["abc", "2.5", "0"])
    def test_an_unreadable_or_too_shallow_depth_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, depth: str
    ) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get(
            f"/api/path-steps/prerequisites?step_uid={_CHILD_UID}&depth={depth}"
        )

        assert response.status_code == 400, response.text
        harness.ps.get_prerequisite_chain.assert_not_awaited()

    @pytest.mark.parametrize("depth", ["", "%20"])
    def test_a_missing_or_blank_depth_is_the_default(
        self, monkeypatch: pytest.MonkeyPatch, depth: str
    ) -> None:
        harness = _make_harness(monkeypatch)

        response = harness.client.get(
            f"/api/path-steps/prerequisites?step_uid={_CHILD_UID}&depth={depth}"
        )

        assert response.status_code == 200, response.text
        harness.ps.get_prerequisite_chain.assert_awaited_once_with(_CHILD_UID, max_depth=3)
        assert response.json()["depth"] == 3
