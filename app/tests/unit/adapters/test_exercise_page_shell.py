"""The exercise page is a shell that loads its content (adapters/inbound/exercises_ui.py).

``/exercises/get`` reads nothing: it renders ``BasePage`` (the Library section lit) and
a placeholder that loads ``/exercises/get/content``, where the read and its boundary
live. The page's query reaches the fragment encoded, so a value carrying ``&`` or
``#`` stays one value instead of becoming a second parameter.
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

import adapters.inbound.exercises_ui as exercises_ui
from core.utils.auth_context import AuthState, auth_state_var
from core.utils.result_simplified import Result


class _SignedInChrome:
    """Sets the auth state the chrome reads, as ``AuthContextMiddleware`` does."""

    def __init__(self, app: object) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: object, send: object) -> None:
        token = auth_state_var.set(AuthState(user_uid="user_learner"))
        try:
            await self.app(scope, receive, send)  # type: ignore[operator]
        finally:
            auth_state_var.reset(token)


def _client(monkeypatch: pytest.MonkeyPatch, service: MagicMock | None = None) -> TestClient:
    def signed_in(_request: object) -> str:
        return "user_learner"

    monkeypatch.setattr(exercises_ui, "require_authenticated_user", signed_in)
    app, rt = fast_app(pico=False, default_hdrs=False)
    exercises_ui.create_exercises_ui_routes(rt, service or MagicMock())
    return TestClient(_SignedInChrome(app))


def _fragment_url(page: str) -> str:
    match = re.search(r'hx-get="([^"]*)"', page[page.index('id="main-content"') :])
    assert match is not None, "the shell loads no content"
    return match.group(1)


@pytest.mark.parametrize(
    ("path", "answer", "marker"),
    [
        ("/exercises/get?uid=exercise.essay", 200, 'id="main-content"'),
        ("/exercises/get/content?uid=exercise.missing", 404, 'id="exercise-detail-content"'),
    ],
)
def test_each_route_answers_get_and_refuses_post(
    monkeypatch: pytest.MonkeyPatch, path: str, answer: int, marker: str
) -> None:
    """Both are reads: GET reaches the handler, POST is no method the route takes."""
    service = MagicMock()
    service.get_exercise_for_user = AsyncMock(return_value=Result.ok(None))
    client = _client(monkeypatch, service)
    response = client.get(path)

    assert (response.status_code, marker in response.text) == (answer, True)
    assert client.post(path).status_code == 405


def test_the_page_is_the_shell_with_the_library_lit(monkeypatch: pytest.MonkeyPatch) -> None:
    page = _client(monkeypatch).get("/exercises/get?uid=exercise.essay").text

    assert page.count('id="main-content"') == 1
    lit = re.findall(r'<a[^>]*aria-current="page"[^>]*>', page[: page.index('id="main-content"')])
    assert [re.search(r'href="([^"]*)"', tag).group(1) for tag in lit] == ["/explore/library"]  # type: ignore[union-attr]
    assert _fragment_url(page) == "/exercises/get/content?uid=exercise.essay"


def test_the_page_hands_its_query_to_the_content_encoded(monkeypatch: pytest.MonkeyPatch) -> None:
    page = (
        _client(monkeypatch)
        .get("/exercises/get", params={"uid": "exercise.a&b", "from_ps": "ps.sel.x#top"})
        .text
    )

    assert _fragment_url(page) == (
        "/exercises/get/content?uid=exercise.a%26b&amp;from_ps=ps.sel.x%23top"
    )
