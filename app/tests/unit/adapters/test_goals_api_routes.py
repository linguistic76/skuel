"""Goals API security/wiring pins (adapters/inbound/goals_api.py).

Testing-gap roadmap item 6, first tranche: the per-domain ``*_api.py``
mutation modules had zero TestClient coverage — PR #702 proved this class of
gap ships real bugs (12 admin/teacher routes 400'd from the day they were
written). These are PIN tests, not exhaustive route coverage: auth gate,
CSRF gate, ownership verification (including the cross-service principle
check), one happy-path mutation with exact service args, one malformed-body
guard, and one field-update-factory route. Harness mirrors
``test_admin_api_security.py`` — real ``fast_app`` + CSRF minting + mocked
services.

Auth seam: ``goals_api`` imports ``require_authenticated_user`` at module
level and ``activity_field_api_factory`` imports its own copy, but both
function objects resolve ``get_current_user`` through
``adapters.inbound.auth.session`` module globals at call time — so patching
``adapters.inbound.auth.session.get_current_user`` authenticates every seam
at once while keeping the real 401-raising ``require_authenticated_user``
in the loop.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

from adapters.inbound.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, mint_token
from adapters.inbound.goals_api import create_goals_api_routes
from core.models.enums.goal_enums import HabitEssentiality
from core.models.enums.relationship_enums import ProficiencyLevel
from core.models.goal.goal import Goal
from core.utils.result_simplified import Errors, Result
from core.utils.zone_context import today_in_current_zone
from tests.helpers.page_links_fake import FakePageLinks

_OWNER_UID = "user_owner"
_GOAL_UID = "goal_1"
_CHILD_UID = "goal_2"
_KU_UID = "ku_math_abc123"
_PRINCIPLE_UID = "principle_1"


def _fake_session_user(request: object) -> str:
    return _OWNER_UID


def _owned_goal() -> Goal:
    return Goal(uid=_GOAL_UID, title="Pinned goal", user_uid=_OWNER_UID)


def _make_services() -> tuple[MagicMock, MagicMock]:
    goals_service = MagicMock()
    goals_service.verify_ownership = AsyncMock(return_value=Result.ok(_owned_goal()))
    goals_service.get_subgoals = AsyncMock(return_value=Result.ok([]))
    goals_service.get_parent_goal = AsyncMock(return_value=Result.ok(None))
    goals_service.remove_subgoal_relationship = AsyncMock(return_value=Result.ok(True))
    goals_service.create_subgoal_relationship = AsyncMock(return_value=Result.ok(True))
    goals_service.link_goal_to_knowledge = AsyncMock(return_value=Result.ok(True))
    goals_service.link_goal_to_principle = AsyncMock(return_value=Result.ok(True))
    # set_status is captured into the FieldUpdateSpec at registration time,
    # so it must be an AsyncMock BEFORE create_goals_api_routes runs.
    goals_service.set_status = AsyncMock(return_value=Result.ok(_owned_goal()))
    goals_service.update_goal = AsyncMock(return_value=Result.ok(_owned_goal()))
    goals_service.update_goal_progress = AsyncMock(return_value=Result.ok(_owned_goal()))
    goals_service.create_goal_milestone = AsyncMock(return_value=Result.ok(_owned_goal()))
    goals_service.complete_milestone = AsyncMock(return_value=Result.ok(_owned_goal()))
    goals_service.get_goal = AsyncMock(return_value=Result.ok(_owned_goal()))
    goals_service.link_goal_to_habit = AsyncMock(return_value=Result.ok(True))
    goals_service.change_habit_essentiality = AsyncMock(return_value=Result.ok(True))
    goals_service.unlink_goal_from_habit = AsyncMock(return_value=Result.ok(True))
    goals_service.replace_habit_system = AsyncMock(return_value=Result.ok(frozenset()))

    principles_service = MagicMock()
    principles_service.verify_ownership = AsyncMock(return_value=Result.ok(MagicMock()))
    return goals_service, principles_service


def _make_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    authenticated: bool = True,
) -> tuple[TestClient, MagicMock, MagicMock]:
    app, rt = fast_app(pico=False, default_hdrs=False)
    goals_service, principles_service = _make_services()

    if authenticated:
        monkeypatch.setattr(
            "adapters.inbound.auth.session.get_current_user",
            _fake_session_user,
        )

    # user_service is asserted at wiring time (fail-fast) — a mock satisfies it;
    # these tests only exercise the field/hierarchy/link routes.
    create_goals_api_routes(
        rt,
        goals_service,
        principles_service,
        connection_fetch_backend=FakePageLinks(),
        user_service=MagicMock(),
    )
    return TestClient(app), goals_service, principles_service


def _post_json(client: TestClient, path: str, json: dict[str, object] | None = None):
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return client.post(path, json=json, headers={CSRF_HEADER_NAME: token})


def _post_form(client: TestClient, path: str, data: dict[str, str]):
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return client.post(path, data=data, headers={CSRF_HEADER_NAME: token})


class TestAuthGate:
    def test_children_unauthenticated_is_401(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, goals_service, _principles = _make_client(monkeypatch, authenticated=False)

        response = client.get(f"/api/goals/children?uid={_GOAL_UID}")

        assert response.status_code == 401
        goals_service.verify_ownership.assert_not_awaited()
        goals_service.get_subgoals.assert_not_awaited()


class TestCsrfGate:
    def test_remove_child_without_csrf_is_403(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, goals_service, _principles = _make_client(monkeypatch)

        response = client.post(
            "/api/goals/remove-child",
            json={"parent_uid": _GOAL_UID, "child_uid": _CHILD_UID},
        )

        assert response.status_code == 403
        goals_service.verify_ownership.assert_not_awaited()
        goals_service.remove_subgoal_relationship.assert_not_awaited()


class TestOwnership:
    def test_children_of_foreign_goal_is_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # verify_entity_ownership surfaces the service's NotFound Result —
        # entities owned by ANOTHER user must read as "not found", never 403.
        client, goals_service, _principles = _make_client(monkeypatch)
        goals_service.verify_ownership = AsyncMock(
            return_value=Result.fail(Errors.not_found("goal", _GOAL_UID))
        )

        response = client.get(f"/api/goals/children?uid={_GOAL_UID}")

        assert response.status_code == 404
        goals_service.get_subgoals.assert_not_awaited()

    def test_link_principle_refuses_foreign_principle(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Cross-service pin: goal ownership passes, principle belongs to
        # another user — the link must not be created.
        client, goals_service, principles_service = _make_client(monkeypatch)
        principles_service.verify_ownership = AsyncMock(
            return_value=Result.fail(Errors.not_found("principle", _PRINCIPLE_UID))
        )

        response = _post_json(
            client,
            "/api/goals/link-principle",
            {"goal_uid": _GOAL_UID, "principle_uid": _PRINCIPLE_UID},
        )

        assert response.status_code == 404
        goals_service.link_goal_to_principle.assert_not_awaited()


class TestMutations:
    def test_link_principle_links_the_pair_and_carries_no_strength(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, goals_service, _principles = _make_client(monkeypatch)

        response = _post_json(
            client,
            "/api/goals/link-principle",
            {"goal_uid": _GOAL_UID, "principle_uid": _PRINCIPLE_UID, "alignment_strength": 0.2},
        )

        assert response.status_code == 200
        goals_service.link_goal_to_principle.assert_awaited_once_with(_GOAL_UID, _PRINCIPLE_UID)

    def test_link_knowledge_happy_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, goals_service, _principles = _make_client(monkeypatch)

        response = _post_json(
            client,
            "/api/goals/link-knowledge",
            {"goal_uid": _GOAL_UID, "knowledge_uid": _KU_UID},
        )

        assert response.status_code == 200
        assert response.json() == {"linked": True}
        goals_service.link_goal_to_knowledge.assert_awaited_once_with(
            _GOAL_UID, _KU_UID, ProficiencyLevel.INTERMEDIATE, 1
        )


class TestInputGuards:
    def test_non_json_body_refuses_before_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # text/plain so the malformed body reaches parse_json_body's own guard —
        # FastHTML pre-parses application/json bodies during param extraction.
        client, goals_service, _principles = _make_client(monkeypatch)

        token = mint_token()
        client.cookies.set(CSRF_COOKIE_NAME, token)
        response = client.post(
            "/api/goals/link-knowledge",
            content=b"not json",
            headers={CSRF_HEADER_NAME: token, "content-type": "text/plain"},
        )

        assert response.status_code == 400
        goals_service.verify_ownership.assert_not_awaited()
        goals_service.link_goal_to_knowledge.assert_not_awaited()

    def test_children_missing_uid_is_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, goals_service, _principles = _make_client(monkeypatch)

        response = client.get("/api/goals/children")

        assert response.status_code == 400
        goals_service.verify_ownership.assert_not_awaited()
        goals_service.get_subgoals.assert_not_awaited()


class TestFieldUpdateRoutes:
    """Routes registered via create_activity_field_api_routes (status/priority)."""

    def test_status_update_happy_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Goals wire set_status directly as the FieldUpdateSpec apply — the
        # transition dispatch (activate/complete/archive side effects) lives
        # in the service, so the route must pass the raw value through.
        client, goals_service, _principles = _make_client(monkeypatch)

        response = _post_form(client, f"/api/goals/{_GOAL_UID}/status", {"status": "active"})

        assert response.status_code == 200
        goals_service.set_status.assert_awaited_once_with(_GOAL_UID, "active")

    def test_invalid_priority_value_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, goals_service, _principles = _make_client(monkeypatch)

        response = _post_form(client, f"/api/goals/{_GOAL_UID}/priority", {"priority": "bananas"})

        assert "Invalid priority value" in response.text
        goals_service.update_goal.assert_not_awaited()


_DOORS: tuple[tuple[str, dict[str, str], str], ...] = (
    (f"/api/goals/{_GOAL_UID}/progress", {"progress": "40"}, "update_goal_progress"),
    (f"/api/goals/{_GOAL_UID}/milestones", {"title": "First draft"}, "create_goal_milestone"),
    (
        f"/api/goals/{_GOAL_UID}/milestones/complete",
        {"milestone_uid": "milestone_1"},
        "complete_milestone",
    ),
)


class TestProgressAndMilestoneDoors:
    """The goal page's three write doors: progress, add a milestone, complete one."""

    @pytest.mark.parametrize(("path", "body", "method"), _DOORS)
    def test_unauthenticated_is_401(
        self, monkeypatch: pytest.MonkeyPatch, path: str, body: dict[str, str], method: str
    ) -> None:
        client, goals_service, _principles = _make_client(monkeypatch, authenticated=False)

        response = _post_json(client, path, dict(body))

        assert response.status_code == 401
        getattr(goals_service, method).assert_not_awaited()

    @pytest.mark.parametrize(("path", "body", "method"), _DOORS)
    def test_no_csrf_token_is_403(
        self, monkeypatch: pytest.MonkeyPatch, path: str, body: dict[str, str], method: str
    ) -> None:
        client, goals_service, _principles = _make_client(monkeypatch)

        response = client.post(path, json=body)

        assert response.status_code == 403
        getattr(goals_service, method).assert_not_awaited()

    @pytest.mark.parametrize(("path", "body", "method"), _DOORS)
    def test_a_goal_that_is_not_the_callers_is_404(
        self, monkeypatch: pytest.MonkeyPatch, path: str, body: dict[str, str], method: str
    ) -> None:
        client, goals_service, _principles = _make_client(monkeypatch)
        goals_service.verify_ownership = AsyncMock(
            return_value=Result.fail(Errors.not_found("goal", _GOAL_UID))
        )

        response = _post_json(client, path, dict(body))

        assert response.status_code == 404
        getattr(goals_service, method).assert_not_awaited()

    @pytest.mark.parametrize(
        ("path", "body", "method"),
        [
            (_DOORS[0][0], {}, "update_goal_progress"),
            (_DOORS[0][0], {"progress": "-1"}, "update_goal_progress"),
            (_DOORS[0][0], {"progress": "lots"}, "update_goal_progress"),
            (_DOORS[0][0], {"progress": "nan"}, "update_goal_progress"),
            (_DOORS[1][0], {}, "create_goal_milestone"),
            (_DOORS[1][0], {"title": "   "}, "create_goal_milestone"),
            (_DOORS[1][0], {"title": "x", "target_date": "soon"}, "create_goal_milestone"),
            (_DOORS[2][0], {}, "complete_milestone"),
            (_DOORS[2][0], {"milestone_uid": ""}, "complete_milestone"),
        ],
    )
    def test_a_bad_body_is_400_and_reaches_no_service(
        self, monkeypatch: pytest.MonkeyPatch, path: str, body: dict[str, str], method: str
    ) -> None:
        client, goals_service, _principles = _make_client(monkeypatch)

        response = _post_form(client, path, body)

        assert response.status_code == 400
        getattr(goals_service, method).assert_not_awaited()

    def test_a_milestone_dated_before_today_is_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, goals_service, _principles = _make_client(monkeypatch)
        yesterday = today_in_current_zone() - timedelta(days=1)

        response = _post_form(
            client, _DOORS[1][0], {"title": "Late", "target_date": yesterday.isoformat()}
        )

        assert response.status_code == 400
        goals_service.create_goal_milestone.assert_not_awaited()

    def test_progress_reaches_the_service_from_json_and_from_the_form(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, goals_service, _principles = _make_client(monkeypatch)

        assert _post_json(client, _DOORS[0][0], {"progress": 40}).status_code == 200
        assert _post_form(client, _DOORS[0][0], {"progress": "62.5"}).status_code == 200

        calls = goals_service.update_goal_progress.await_args_list
        assert [c.args for c in calls] == [(_GOAL_UID, 40.0), (_GOAL_UID, 62.5)]
        assert [c.kwargs for c in calls] == [{"update_date": None}, {"update_date": None}]

    def test_a_milestone_reaches_the_service_trimmed_with_a_blank_date_as_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, goals_service, _principles = _make_client(monkeypatch)
        today = today_in_current_zone()

        blank = _post_form(client, _DOORS[1][0], {"title": "  First draft ", "target_date": ""})
        dated = _post_form(
            client, _DOORS[1][0], {"title": "Second", "target_date": today.isoformat()}
        )

        assert (blank.status_code, dated.status_code) == (200, 200)
        assert [c.args for c in goals_service.create_goal_milestone.await_args_list] == [
            (_GOAL_UID, "First draft", None, None),
            (_GOAL_UID, "Second", today, None),
        ]

    def test_a_completion_names_the_milestone_by_uid(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, goals_service, _principles = _make_client(monkeypatch)

        response = _post_form(client, _DOORS[2][0], {"milestone_uid": "milestone_1"})

        assert response.status_code == 200
        goals_service.complete_milestone.assert_awaited_once_with(_GOAL_UID, "milestone_1")

    def test_a_milestone_the_goal_does_not_hold_is_404(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, goals_service, _principles = _make_client(monkeypatch)
        goals_service.complete_milestone = AsyncMock(
            return_value=Result.fail(Errors.not_found("Milestone", "milestone_gone"))
        )

        response = _post_form(client, _DOORS[2][0], {"milestone_uid": "milestone_gone"})

        assert response.status_code == 404

    def test_a_derived_figure_refusal_is_422(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, goals_service, _principles = _make_client(monkeypatch)
        goals_service.update_goal_progress = AsyncMock(
            return_value=Result.fail(Errors.business("goal_figure_is_derived", "Measured for you"))
        )

        response = _post_form(client, _DOORS[0][0], {"progress": "40"})

        assert response.status_code == 422

    @pytest.mark.parametrize(("path", "body", "method"), _DOORS)
    def test_json_answers_the_goal_and_htmx_answers_the_detail_view(
        self, monkeypatch: pytest.MonkeyPatch, path: str, body: dict[str, str], method: str
    ) -> None:
        client, _goals_service, _principles = _make_client(monkeypatch)

        as_json = _post_json(client, path, dict(body))
        token = mint_token()
        client.cookies.set(CSRF_COOKIE_NAME, token)
        as_page = client.post(
            path, data=body, headers={CSRF_HEADER_NAME: token, "HX-Request": "true"}
        )

        assert as_json.headers["content-type"].startswith("application/json")
        assert as_json.json()["uid"] == _GOAL_UID
        assert as_page.headers["content-type"].startswith("text/html")
        assert f'id="goal-detail-{_GOAL_UID}"' in as_page.text
        assert "<html" not in as_page.text


_HABIT_UID = "habit_1"

#: The four habit-system doors: path, a good form body, and the service method it calls.
_HABIT_DOORS: tuple[tuple[str, dict[str, str], str], ...] = (
    (f"/api/goals/{_GOAL_UID}/habits", {"habit_uid": _HABIT_UID}, "link_goal_to_habit"),
    (
        f"/api/goals/{_GOAL_UID}/habits/essentiality",
        {"habit_uid": _HABIT_UID, "new_essentiality": "critical"},
        "change_habit_essentiality",
    ),
    (f"/api/goals/{_GOAL_UID}/habits/unlink", {"habit_uid": _HABIT_UID}, "unlink_goal_from_habit"),
    (f"/api/goals/{_GOAL_UID}/habits/system", {}, "replace_habit_system"),
)


class TestHabitSystemDoors:
    """The goal page's habit section: link, change a tier, unlink, replace the system."""

    @pytest.mark.parametrize(("path", "body", "method"), _HABIT_DOORS)
    def test_unauthenticated_is_401(
        self, monkeypatch: pytest.MonkeyPatch, path: str, body: dict[str, str], method: str
    ) -> None:
        client, goals_service, _principles = _make_client(monkeypatch, authenticated=False)

        response = _post_json(client, path, dict(body))

        assert response.status_code == 401
        getattr(goals_service, method).assert_not_awaited()

    @pytest.mark.parametrize(("path", "body", "method"), _HABIT_DOORS)
    def test_no_csrf_token_is_403(
        self, monkeypatch: pytest.MonkeyPatch, path: str, body: dict[str, str], method: str
    ) -> None:
        client, goals_service, _principles = _make_client(monkeypatch)

        response = client.post(path, json=body)

        assert response.status_code == 403
        getattr(goals_service, method).assert_not_awaited()

    @pytest.mark.parametrize(("path", "body", "method"), _HABIT_DOORS)
    def test_a_goal_that_is_not_the_callers_is_404(
        self, monkeypatch: pytest.MonkeyPatch, path: str, body: dict[str, str], method: str
    ) -> None:
        client, goals_service, _principles = _make_client(monkeypatch)
        goals_service.verify_ownership = AsyncMock(
            return_value=Result.fail(Errors.not_found("goal", _GOAL_UID))
        )

        response = _post_json(client, path, dict(body))

        assert response.status_code == 404
        getattr(goals_service, method).assert_not_awaited()

    @pytest.mark.parametrize(
        ("path", "body", "method"),
        [
            (_HABIT_DOORS[0][0], {}, "link_goal_to_habit"),
            (_HABIT_DOORS[0][0], {"habit_uid": ""}, "link_goal_to_habit"),
            (
                _HABIT_DOORS[0][0],
                {"habit_uid": _HABIT_UID, "essentiality": "vital"},
                "link_goal_to_habit",
            ),
            (_HABIT_DOORS[1][0], {"habit_uid": _HABIT_UID}, "change_habit_essentiality"),
            (
                _HABIT_DOORS[1][0],
                {"habit_uid": _HABIT_UID, "new_essentiality": "vital"},
                "change_habit_essentiality",
            ),
            (_HABIT_DOORS[2][0], {}, "unlink_goal_from_habit"),
        ],
    )
    def test_a_bad_body_is_400_and_reaches_no_service(
        self, monkeypatch: pytest.MonkeyPatch, path: str, body: dict[str, str], method: str
    ) -> None:
        client, goals_service, _principles = _make_client(monkeypatch)

        response = _post_form(client, path, body)

        assert response.status_code == 400
        getattr(goals_service, method).assert_not_awaited()

    def test_a_habit_in_two_tiers_is_400(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, goals_service, _principles = _make_client(monkeypatch)

        response = _post_json(
            client,
            _HABIT_DOORS[3][0],
            {"essential_habit_uids": [_HABIT_UID], "optional_habit_uids": [_HABIT_UID]},
        )

        assert response.status_code == 400
        goals_service.replace_habit_system.assert_not_awaited()

    def test_a_habit_that_is_not_the_callers_is_404(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The service's admission refuses it; the door answers its 404 and reads no goal."""
        client, goals_service, _principles = _make_client(monkeypatch)
        goals_service.link_goal_to_habit = AsyncMock(
            return_value=Result.fail(Errors.not_found("habit", "habit_theirs"))
        )

        response = _post_form(client, _HABIT_DOORS[0][0], {"habit_uid": "habit_theirs"})

        assert response.status_code == 404
        goals_service.get_goal.assert_not_awaited()

    def test_a_tier_change_on_a_habit_not_linked_is_404(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, goals_service, _principles = _make_client(monkeypatch)
        goals_service.change_habit_essentiality = AsyncMock(
            return_value=Result.fail(Errors.not_found("Relationship", "habit_9 -> goal_1"))
        )

        response = _post_form(
            client,
            _HABIT_DOORS[1][0],
            {"habit_uid": "habit_9", "new_essentiality": "essential"},
        )

        assert response.status_code == 404

    def test_each_door_reaches_its_service_with_the_tier_as_the_enum(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client, goals_service, _principles = _make_client(monkeypatch)

        linked_default = _post_form(client, _HABIT_DOORS[0][0], {"habit_uid": _HABIT_UID})
        linked_critical = _post_json(
            client, _HABIT_DOORS[0][0], {"habit_uid": "habit_2", "essentiality": "critical"}
        )
        changed = _post_form(client, *_HABIT_DOORS[1][:2])
        unlinked = _post_form(client, *_HABIT_DOORS[2][:2])
        replaced = _post_json(
            client,
            _HABIT_DOORS[3][0],
            {"essential_habit_uids": ["habit_2"], "supporting_habit_uids": [_HABIT_UID]},
        )

        assert {
            r.status_code for r in (linked_default, linked_critical, changed, unlinked, replaced)
        } == {200}
        assert [c.args for c in goals_service.link_goal_to_habit.await_args_list] == [
            (_GOAL_UID, _HABIT_UID, HabitEssentiality.SUPPORTING),
            (_GOAL_UID, "habit_2", HabitEssentiality.CRITICAL),
        ]
        goals_service.change_habit_essentiality.assert_awaited_once_with(
            _GOAL_UID, _HABIT_UID, HabitEssentiality.CRITICAL
        )
        goals_service.unlink_goal_from_habit.assert_awaited_once_with(_GOAL_UID, _HABIT_UID)
        goals_service.replace_habit_system.assert_awaited_once_with(
            _GOAL_UID,
            {"habit_2": HabitEssentiality.ESSENTIAL, _HABIT_UID: HabitEssentiality.SUPPORTING},
        )

    def test_an_empty_system_unlinks_every_habit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client, goals_service, _principles = _make_client(monkeypatch)

        response = _post_json(client, _HABIT_DOORS[3][0], {})

        assert response.status_code == 200
        goals_service.replace_habit_system.assert_awaited_once_with(_GOAL_UID, {})

    @pytest.mark.parametrize(("path", "body", "method"), _HABIT_DOORS)
    def test_json_answers_the_goal_and_htmx_answers_the_detail_view(
        self, monkeypatch: pytest.MonkeyPatch, path: str, body: dict[str, str], method: str
    ) -> None:
        client, _goals_service, _principles = _make_client(monkeypatch)

        as_json = _post_json(client, path, dict(body))
        token = mint_token()
        client.cookies.set(CSRF_COOKIE_NAME, token)
        as_page = client.post(
            path, data=body, headers={CSRF_HEADER_NAME: token, "HX-Request": "true"}
        )

        assert as_json.headers["content-type"].startswith("application/json")
        assert as_json.json()["uid"] == _GOAL_UID
        assert as_page.headers["content-type"].startswith("text/html")
        assert f'id="goal-detail-{_GOAL_UID}"' in as_page.text
        assert "<html" not in as_page.text
