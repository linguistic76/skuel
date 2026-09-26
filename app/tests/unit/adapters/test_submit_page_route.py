"""``GET /submissions/submit`` — the one Submit page (Submit & Share arc PR 7).

The route names the preselected exercise, offers "Which class?" from the
student's classes, and reuses the Share panel's targets read for "Share with".
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastcore.xml import to_xml  # type: ignore[import-untyped]

from adapters.inbound.user_entry_ui import create_user_entry_ui_routes
from core.utils.result_simplified import Errors, Result

_TARGETS = {
    "groups": [{"uid": "g_class", "name": "Physics 101"}],
    "people": [{"uid": "user_a", "username": "alice", "display_name": "Alice"}],
}


class _RouteRegistry:
    def __init__(self) -> None:
        self.handlers: dict[tuple[str, str], object] = {}

    def __call__(self, path: str, methods: list[str] | None = None):
        method = (methods[0] if methods else "GET").upper()

        def decorator(func):
            self.handlers[(path, method)] = func
            return func

        return decorator

    def get(self, path: str, method: str = "GET"):
        return self.handlers[(path, method.upper())]


def _request(query: dict[str, str] | None = None) -> SimpleNamespace:
    request = SimpleNamespace()
    request.session = {"user_uid": "user_student"}
    request.url = SimpleNamespace(path="/submissions/submit")
    request.method = "GET"
    request.cookies = {}
    request.headers = {}
    request.query_params = query or {}
    return request


def _handler(*, groups: list[SimpleNamespace] | None = None, targets=None, exercise=None):
    registry = _RouteRegistry()
    orchestrator = SimpleNamespace(
        get_exercise=AsyncMock(
            return_value=(
                Result.ok(exercise)
                if exercise is not None
                else Result.fail(Errors.not_found(resource="Exercise", identifier="ex_missing"))
            )
        )
    )
    groups_service = SimpleNamespace(
        get_user_groups=AsyncMock(return_value=Result.ok(groups or []))
    )
    sharing = SimpleNamespace(
        targets=AsyncMock(return_value=Result.ok(targets if targets is not None else _TARGETS))
    )
    create_user_entry_ui_routes(
        None,
        registry,
        SimpleNamespace(),
        orchestrator=orchestrator,
        groups_service=groups_service,
        entry_sharing=sharing,
    )
    return registry.get("/submissions/submit"), orchestrator, groups_service, sharing


@pytest.mark.asyncio
async def test_the_page_names_the_exercise_and_offers_the_share_targets() -> None:
    handler, orchestrator, groups_service, sharing = _handler(
        groups=[SimpleNamespace(uid="g_a", name="Physics")],
        exercise=SimpleNamespace(uid="ex_1", title="The Gentle Return"),
    )

    html = to_xml(await handler(_request({"exercise_uid": "ex_1", "from_ps": "ps.a.b"})))

    orchestrator.get_exercise.assert_awaited_once_with("ex_1")
    groups_service.get_user_groups.assert_awaited_once_with("user_student", role="student")
    sharing.targets.assert_awaited_once_with("user_student")
    assert "Answering: " in html and "The Gentle Return" in html
    assert 'name="fulfills_exercise_uid" value="ex_1"' in html
    assert 'name="about_path_step_uid" value="ps.a.b"' in html
    assert 'value="group:g_class"' in html and 'value="user:alice"' in html
    assert "selectFeedback('ai')" in html  # AI is offered with an exercise


@pytest.mark.asyncio
async def test_without_an_exercise_teacher_still_works_and_several_classes_get_a_select() -> None:
    handler, orchestrator, _groups, _sharing = _handler(
        groups=[SimpleNamespace(uid="g_a", name="Physics"), SimpleNamespace(uid="g_b", name="Chem")]
    )

    html = to_xml(await handler(_request()))

    orchestrator.get_exercise.assert_not_awaited()
    assert "x-data=\"submit('teacher', true)\"" in html
    assert 'name="teacher_group"' in html
    assert '<option value="g_b">Chem</option>' in html
    assert "Needs an exercise" in html


@pytest.mark.asyncio
async def test_a_missing_exercise_still_renders_the_form_with_the_link() -> None:
    handler, _o, _g, _s = _handler()

    html = to_xml(await handler(_request({"exercise_uid": "ex_missing"})))

    assert 'name="fulfills_exercise_uid" value="ex_missing"' in html
    assert "Answering: " in html and "ex_missing" in html
