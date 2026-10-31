"""Life Path's vision flow, form to chosen path, answers in the Life Path shell
(adapters/inbound/lifepath_ui.py, ui/lifepath/vision.py).

The vision form posts natively. A captured vision answers a 303 to the
recommendations page, which rebuilds them from the SAVED vision's themes, so a
reload is a GET that extracts nothing. A refused or unsaved vision comes back as
the form, in the shell, with its banner and the learner's text; a validation
refusal's banner reads its reason. The recommendations page sends a learner with
no saved vision back to the form, and a failed read is a banner, never an empty
result. The learner's designated path, when the search finds it, is marked "Your
current path" in place of its button. The vision page itself fills the form from
the saved vision, and a failed read there is the banner alone. Each other
recommendation's "Choose This Path" is a native POST; a designation answers a 303 to the alignment page, or its refusal in
the shell with the way back to the recommendations. CSRF is enforced for real:
cookie plus the form field.
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock

import pytest
from fasthtml.common import fast_app, to_xml
from starlette.testclient import TestClient

import adapters.inbound.lifepath_ui as lifepath_ui
from adapters.inbound.csrf import CSRF_COOKIE_NAME, mint_token
from core.models.type_hints import UserUID
from core.ports.query_types import LpMatchResult, SavedVision, VisionData
from core.ports.service_protocols import LifePathOperations
from core.utils.csrf_token_context import CSRF_FORM_FIELD
from core.utils.result_simplified import Errors, Result
from tests.helpers.settings_stub import settings_stub
from ui.lifepath import render_recommendation_cards

VISION = SavedVision(
    statement="I want to become a patient teacher and a mindful leader",
    themes=["teaching", "leadership"],
    life_path_uid=None,
)
MATCHES = [
    LpMatchResult(
        lp_uid="lp.x.teacher",
        lp_name="Patient Teaching",
        match_score=0.5,
        matching_themes=["teaching"],
    ),
]
OTHER_MATCH = LpMatchResult(
    lp_uid="lp.x.leader",
    lp_name="Mindful Leadership",
    match_score=0.5,
    matching_themes=["leadership"],
)
#: What a capture answers: the vision as saved.
CAPTURED = VisionData(statement=VISION["statement"], themes=VISION["themes"])
RECOMMENDATIONS = "/lifepath/vision/recommendations"


def _service() -> MagicMock:
    """The facade as the routes see it: the protocol, and nothing past it."""
    return MagicMock(spec=LifePathOperations)


def _client(monkeypatch: pytest.MonkeyPatch, service: MagicMock) -> TestClient:
    def signed_in(_request: object) -> UserUID:
        return UserUID("user_learner")

    monkeypatch.setattr(lifepath_ui, "require_authenticated_user", signed_in)
    monkeypatch.setattr(lifepath_ui, "get_settings", settings_stub(debug=False))
    app, rt = fast_app(pico=False, default_hdrs=False)
    lifepath_ui.create_lifepath_ui_routes(app, rt, service, MagicMock())
    return TestClient(app)


def _post_form(client: TestClient, path: str, data: dict[str, str], *, follow: bool = False):
    """A native form POST: the token rides in the form field, as the page renders it."""
    token = mint_token()
    client.cookies.set(CSRF_COOKIE_NAME, token)
    return client.post(path, data={CSRF_FORM_FIELD: token, **data}, follow_redirects=follow)


def _assert_in_the_shell_on_vision(page: str) -> None:
    assert page.count('id="main-content"') == 1, "the page is not the shell's"
    assert re.search(r'<a href="/lifepath/vision"[^>]*aria-current="page"', page)


def _banner_text(page: str) -> str:
    """The banner's headline: its first row, which renders whatever the settings — the
    technical details, when shown at all, follow it in a collapsed ``<details>``."""
    headline = re.search(r'<div role="alert"[^>]*>(.*?)</div>', page, re.DOTALL)
    assert headline is not None, "no banner"
    return " ".join(re.sub(r"<[^>]+>", " ", headline.group(1)).split())


# ---------------------------------------------------------------------------
# The vision form
# ---------------------------------------------------------------------------


def test_a_captured_vision_answers_a_303_to_its_recommendations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    service.capture_vision.return_value = Result.ok(CAPTURED)
    response = _post_form(
        _client(monkeypatch, service), "/lifepath/vision", {"vision_statement": VISION["statement"]}
    )

    assert response.status_code == 303
    assert response.headers["location"] == RECOMMENDATIONS
    service.capture_vision.assert_awaited_once_with("user_learner", VISION["statement"])
    service.match_learning_paths.assert_not_awaited()
    service.capture_and_recommend.assert_not_awaited()


def test_reloading_the_recommendations_captures_nothing_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The landing page is a GET: a reload re-reads the saved vision and searches,
    and the capture (theme extraction, the LLM in FULL tier) ran once."""
    service = _service()
    service.capture_vision.return_value = Result.ok(CAPTURED)
    service.get_vision.return_value = Result.ok(VISION)
    service.match_learning_paths.return_value = Result.ok(MATCHES)
    client = _client(monkeypatch, service)

    landed = _post_form(
        client, "/lifepath/vision", {"vision_statement": VISION["statement"]}, follow=True
    )
    reloaded = client.get(RECOMMENDATIONS)

    assert [r.status_code for r in landed.history] == [303]
    assert landed.request.method == "GET"
    assert str(landed.url).endswith(RECOMMENDATIONS)
    assert "Patient Teaching" in landed.text
    assert "Patient Teaching" in reloaded.text
    assert service.capture_vision.await_count == 1
    assert service.match_learning_paths.await_count == 2


def test_a_refused_vision_is_the_form_again_with_its_reason_and_the_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    service.capture_vision.return_value = Result.fail(
        Errors.validation(
            "Vision statement must be at least 10 characters", field="vision_statement"
        )
    )
    response = _post_form(
        _client(monkeypatch, service), "/lifepath/vision", {"vision_statement": "short"}
    )

    assert response.status_code == 200
    _assert_in_the_shell_on_vision(response.text)
    assert "Vision statement must be at least 10 characters" in _banner_text(response.text)
    assert re.search(r'<textarea[^>]*name="vision_statement"[^>]*>short</textarea>', response.text)
    service.capture_vision.assert_awaited_once_with("user_learner", "short")


@pytest.mark.parametrize(
    "error",
    [
        Errors.integration("llm", "theme extraction timed out"),
        Errors.database("save_vision", "write failed"),
    ],
    ids=["extraction-failed", "save-failed"],
)
def test_a_vision_that_was_not_saved_is_the_form_again_with_a_retry(
    monkeypatch: pytest.MonkeyPatch, error: object
) -> None:
    """A vision whose themes could not be read, or that could not be saved, is not
    captured: no redirect to recommendations a failed save never stored."""
    service = _service()
    service.capture_vision.return_value = Result.fail(error)
    response = _post_form(
        _client(monkeypatch, service), "/lifepath/vision", {"vision_statement": "A patient teacher"}
    )

    assert response.status_code == 200
    _assert_in_the_shell_on_vision(response.text)
    assert _banner_text(response.text) == "❌ Could not save your vision"
    assert re.search(
        r'<textarea[^>]*name="vision_statement"[^>]*>A patient teacher</textarea>', response.text
    )
    assert "timed out" not in response.text and "write failed" not in response.text


# ---------------------------------------------------------------------------
# The recommendations page
# ---------------------------------------------------------------------------


def test_the_recommendations_are_rebuilt_from_the_saved_themes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    service.get_vision.return_value = Result.ok(VISION)
    service.match_learning_paths.return_value = Result.ok(MATCHES)
    response = _client(monkeypatch, service).get(RECOMMENDATIONS)

    assert response.status_code == 200
    _assert_in_the_shell_on_vision(response.text)
    assert VISION["statement"] in response.text
    assert "Themes extracted: teaching, leadership" in response.text
    assert re.search(r'<form[^>]*action="/lifepath/designate"', response.text)
    service.get_vision.assert_awaited_once_with("user_learner")
    service.match_learning_paths.assert_awaited_once_with(["teaching", "leadership"])
    service.capture_vision.assert_not_awaited()
    service.capture_and_recommend.assert_not_awaited()


def test_no_saved_vision_goes_back_to_the_form(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service()
    service.get_vision.return_value = Result.ok(None)
    response = _client(monkeypatch, service).get(RECOMMENDATIONS, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/lifepath/vision"
    service.match_learning_paths.assert_not_awaited()


def test_a_vision_with_no_themes_is_sent_to_revise_it_without_a_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    service.get_vision.return_value = Result.ok(
        SavedVision(statement="I want it all.", themes=[], life_path_uid=None)
    )
    response = _client(monkeypatch, service).get(RECOMMENDATIONS)

    assert response.status_code == 200
    assert "No themes found in your vision" in response.text
    assert re.search(r'<a href="/lifepath/vision"[^>]*>\s*Revise your vision', response.text)
    assert "No Matching Learning Paths" not in response.text
    service.match_learning_paths.assert_not_awaited()


def test_a_failed_vision_read_is_a_banner(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service()
    service.get_vision.return_value = Result.fail(Errors.database("get_designation", "timeout"))
    response = _client(monkeypatch, service).get(RECOMMENDATIONS, follow_redirects=False)

    assert response.status_code == 200
    _assert_in_the_shell_on_vision(response.text)
    assert _banner_text(response.text) == "❌ Could not load your vision"
    service.match_learning_paths.assert_not_awaited()


def test_a_failed_recommendation_read_is_a_banner_under_the_vision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    service.get_vision.return_value = Result.ok(VISION)
    service.match_learning_paths.return_value = Result.fail(
        Errors.database("text_search", "timeout")
    )
    response = _client(monkeypatch, service).get(RECOMMENDATIONS)

    assert response.status_code == 200
    assert VISION["statement"] in response.text
    assert _banner_text(response.text) == "❌ Could not load your recommended Learning Paths"
    assert "No Matching Learning Paths" not in response.text


def test_no_matching_paths_offers_the_paths_to_browse(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service()
    service.get_vision.return_value = Result.ok(VISION)
    service.match_learning_paths.return_value = Result.ok([])
    response = _client(monkeypatch, service).get(RECOMMENDATIONS)

    assert "No Matching Learning Paths" in response.text
    assert re.search(r'<a href="/learning-paths"[^>]*>\s*Browse Learning Paths', response.text)


def test_the_designated_path_is_marked_in_place_of_its_button(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Choosing the path the learner already has would only re-designate it."""
    service = _service()
    service.get_vision.return_value = Result.ok(
        SavedVision(**{**VISION, "life_path_uid": "lp.x.teacher"})
    )
    service.match_learning_paths.return_value = Result.ok([*MATCHES, OTHER_MATCH])
    page = _client(monkeypatch, service).get(RECOMMENDATIONS).text

    forms = re.findall(r'<form[^>]*action="/lifepath/designate".*?</form>', page, re.DOTALL)
    assert len(forms) == 1
    assert 'value="lp.x.leader"' in forms[0]
    assert "Mindful Leadership" in forms[0]
    assert 'value="lp.x.teacher"' not in page
    teacher_card = page[page.index("Patient Teaching") : page.index("Mindful Leadership")]
    assert "Your current path" in teacher_card
    assert "Choose This Path" not in teacher_card
    assert page.count("Your current path") == 1


def test_a_designated_path_the_search_did_not_find_marks_no_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service()
    service.get_vision.return_value = Result.ok(
        SavedVision(**{**VISION, "life_path_uid": "lp.x.elsewhere"})
    )
    service.match_learning_paths.return_value = Result.ok([*MATCHES, OTHER_MATCH])
    page = _client(monkeypatch, service).get(RECOMMENDATIONS).text

    assert "Your current path" not in page
    assert len(re.findall(r'<form[^>]*action="/lifepath/designate"', page)) == 2


def test_each_recommendation_posts_natively_with_its_path_and_token() -> None:
    page = to_xml(render_recommendation_cards(MATCHES, None))
    form = re.search(r'<form[^>]*action="/lifepath/designate".*?</form>', page, re.DOTALL)

    assert form is not None
    assert 'method="post"' in form.group(0)
    assert "hx-post" not in form.group(0)
    assert re.search(
        r'<input type="hidden" name="life_path_uid" value="lp.x.teacher"', form.group(0)
    )
    assert f'name="{CSRF_FORM_FIELD}"' in form.group(0)


# ---------------------------------------------------------------------------
# The vision page
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("saved", "text"),
    [(VISION, VISION["statement"]), (None, "")],
    ids=["saved-vision", "no-vision"],
)
def test_the_vision_page_fills_the_form_from_the_saved_vision(
    monkeypatch: pytest.MonkeyPatch, saved: SavedVision | None, text: str
) -> None:
    service = _service()
    service.get_vision.return_value = Result.ok(saved)
    response = _client(monkeypatch, service).get("/lifepath/vision")

    assert response.status_code == 200
    _assert_in_the_shell_on_vision(response.text)
    assert re.search(
        rf'<textarea[^>]*name="vision_statement"[^>]*>{re.escape(text)}</textarea>', response.text
    )


def test_a_failed_read_on_the_vision_page_is_the_banner_and_no_form(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty form would invite the learner to replace a vision they cannot see."""
    service = _service()
    service.get_vision.return_value = Result.fail(Errors.database("get_designation", "timeout"))
    response = _client(monkeypatch, service).get("/lifepath/vision")

    assert response.status_code == 200
    _assert_in_the_shell_on_vision(response.text)
    assert _banner_text(response.text) == "❌ Could not load your vision"
    assert "<textarea" not in response.text
    assert 'action="/lifepath/vision"' not in response.text


# ---------------------------------------------------------------------------
# The designation form
# ---------------------------------------------------------------------------


def test_a_designation_navigates_to_the_alignment_page(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service()
    service.designate_and_calculate.return_value = Result.ok({})
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
    service = _service()
    service.designate_and_calculate.return_value = result
    response = _post_form(
        _client(monkeypatch, service), "/lifepath/designate", {"life_path_uid": life_path_uid}
    )

    assert response.status_code == 200
    _assert_in_the_shell_on_vision(response.text)
    assert _banner_text(response.text) == f"❌ {reason}"
    assert re.search(
        rf'<a href="{RECOMMENDATIONS}"[^>]*>\s*Back to your recommendations', response.text
    )


def test_a_post_without_the_token_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """The harness enforces CSRF: the field is what lets the forms through."""
    service = _service()
    response = _client(monkeypatch, service).post(
        "/lifepath/designate", data={"life_path_uid": "lp.x.teacher"}, follow_redirects=False
    )

    assert response.status_code == 403
    service.designate_and_calculate.assert_not_awaited()
