"""Life Path's two forms post natively and answer in the Life Path shell
(adapters/inbound/lifepath_ui.py, ui/lifepath/vision.py).

The vision form and each recommendation's "Choose This Path" form are native POSTs
carrying their CSRF field. A refused vision comes back as the vision form, in the
shell, with its banner and the learner's text; a validation refusal's banner reads its
reason. A designation answers a 303 to the alignment page, or its refusal in the shell
with the way back to the vision. CSRF is enforced for real: cookie plus the form field.
"""

from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app, to_xml
from starlette.testclient import TestClient

import adapters.inbound.lifepath_ui as lifepath_ui
from adapters.inbound.csrf import CSRF_COOKIE_NAME, mint_token
from core.models.type_hints import UserUID
from core.utils.csrf_token_context import CSRF_FORM_FIELD
from core.utils.result_simplified import Errors, Result
from ui.lifepath import render_recommendations_page

RECOMMENDATIONS = {
    "vision": {"statement": "I want to become a patient teacher", "themes": ["teaching"]},
    "recommendations": [
        {
            "lp_uid": "lp.x.teacher",
            "lp_name": "Teaching",
            "match_score": 0.8,
            "matching_themes": [],
        },
    ],
}


def _client(monkeypatch: pytest.MonkeyPatch, service: MagicMock) -> TestClient:
    def signed_in(_request: object) -> UserUID:
        return UserUID("user_learner")

    def debug_off() -> SimpleNamespace:
        """Settings stub — get_settings() needs real env config, unavailable in unit tests."""
        return SimpleNamespace(application=SimpleNamespace(debug=False))

    monkeypatch.setattr(lifepath_ui, "require_authenticated_user", signed_in)
    monkeypatch.setattr(lifepath_ui, "get_settings", debug_off)
    app, rt = fast_app(pico=False, default_hdrs=False)
    lifepath_ui.create_lifepath_ui_routes(app, rt, service)
    return TestClient(app)


def _post_form(client: TestClient, path: str, data: dict[str, str]):
    """A native form POST: the token rides in the form field, as the page renders it."""
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return client.post(path, data={CSRF_FORM_FIELD: token, **data}, follow_redirects=False)


def _assert_in_the_shell_on_vision(page: str) -> None:
    assert page.count('id="main-content"') == 1, "the page is not the shell's"
    assert re.search(r'<a href="/lifepath/vision"[^>]*aria-current="page"', page)


def _banner_text(page: str) -> str:
    """The banner's headline: its first row, which renders whatever the settings — the
    technical details, when shown at all, follow it in a collapsed ``<details>``."""
    headline = re.search(r'<div role="alert"[^>]*>(.*?)</div>', page, re.DOTALL)
    assert headline is not None, "no banner"
    return " ".join(re.sub(r"<[^>]+>", " ", headline.group(1)).split())


def test_a_refused_vision_is_the_form_again_with_its_reason_and_the_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = MagicMock()
    service.capture_and_recommend = AsyncMock(
        return_value=Result.fail(
            Errors.validation(
                "Vision statement must be at least 10 characters", field="vision_statement"
            )
        )
    )
    response = _post_form(
        _client(monkeypatch, service), "/lifepath/vision", {"vision_statement": "short"}
    )

    assert response.status_code == 200
    _assert_in_the_shell_on_vision(response.text)
    assert "Vision statement must be at least 10 characters" in _banner_text(response.text)
    assert re.search(r'<textarea[^>]*name="vision_statement"[^>]*>short</textarea>', response.text)
    service.capture_and_recommend.assert_awaited_once_with("user_learner", "short")


def test_a_vision_the_service_cannot_read_offers_a_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    service = MagicMock()
    service.capture_and_recommend = AsyncMock(
        return_value=Result.fail(Errors.integration("llm", "theme extraction timed out"))
    )
    response = _post_form(
        _client(monkeypatch, service), "/lifepath/vision", {"vision_statement": "A patient teacher"}
    )

    assert response.status_code == 200
    _assert_in_the_shell_on_vision(response.text)
    assert _banner_text(response.text) == "❌ Could not read your vision"
    assert "theme extraction timed out" not in response.text  # the detail renders only in debug


def test_a_designation_navigates_to_the_alignment_page(monkeypatch: pytest.MonkeyPatch) -> None:
    service = MagicMock()
    service.designate_and_calculate = AsyncMock(return_value=Result.ok({}))
    response = _post_form(
        _client(monkeypatch, service), "/lifepath/designate", {"life_path_uid": "lp.x.teacher"}
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/lifepath/alignment"
    service.designate_and_calculate.assert_awaited_once_with("user_learner", "lp.x.teacher")


@pytest.mark.parametrize(
    ("life_path_uid", "result", "reason"),
    [
        ("lp.x.teacher", Result.fail(Errors.database("designate", "write failed")), "Could not set your Life Path"),
        ("lp.x.teacher", Result.fail(Errors.validation("That path is not a Learning Path", field="life_path_uid")),
         "That path is not a Learning Path"),
        ("", None, "Please choose a Learning Path."),
    ],
)  # fmt: skip
def test_a_refused_designation_answers_in_the_shell_with_the_way_back(
    monkeypatch: pytest.MonkeyPatch, life_path_uid: str, result: object, reason: str
) -> None:
    service = MagicMock()
    service.designate_and_calculate = AsyncMock(return_value=result)
    response = _post_form(
        _client(monkeypatch, service), "/lifepath/designate", {"life_path_uid": life_path_uid}
    )

    assert response.status_code == 200
    _assert_in_the_shell_on_vision(response.text)
    assert _banner_text(response.text) == f"❌ {reason}"
    assert re.search(r'<a href="/lifepath/vision"[^>]*>\s*Back to your vision', response.text)


def test_a_post_without_the_token_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """The harness enforces CSRF: the field is what lets the forms through."""
    service = MagicMock()
    service.designate_and_calculate = AsyncMock(return_value=Result.ok({}))
    response = _client(monkeypatch, service).post(
        "/lifepath/designate", data={"life_path_uid": "lp.x.teacher"}, follow_redirects=False
    )

    assert response.status_code == 403
    service.designate_and_calculate.assert_not_awaited()


def test_each_recommendation_posts_natively_with_its_path_and_token() -> None:
    page = to_xml(render_recommendations_page(RECOMMENDATIONS, UserUID("user_learner")))
    form = re.search(r'<form[^>]*action="/lifepath/designate".*?</form>', page, re.DOTALL)

    assert form is not None
    assert 'method="post"' in form.group(0)
    assert "hx-post" not in form.group(0)
    assert re.search(
        r'<input type="hidden" name="life_path_uid" value="lp.x.teacher"', form.group(0)
    )
    assert f'name="{CSRF_FORM_FIELD}"' in form.group(0)
