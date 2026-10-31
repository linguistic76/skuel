"""/lifepath/alignment holds both alignment measures, and shows only one as alignment
(adapters/inbound/lifepath_ui.py, ui/lifepath/alignment.py).

The fragment reads the five-dimension alignment (``LifePathService.get_full_status``)
and the learner's personal substance over the path's steps
(``AnalyticsService.calculate_life_path_alignment``). The five-dimension score is the
page's one alignment figure. The substance half shows as the steps' band counts, the
least-lived steps (each a link to its step, its band from the payload), and each
channel's share — the substance mean is never rendered. A failed substance read
banners its own cards and leaves the five-dimension half standing; a failed status
read banners the fragment. Neither banner shows developer text.
"""

from __future__ import annotations

import html
import re
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import fast_app
from starlette.testclient import TestClient

import adapters.inbound.lifepath_ui as lifepath_ui
from core.models.enums import SubstanceBand
from core.models.type_hints import UserUID
from core.ports.query_types import LifePathStatus, LifePathSubstanceAlignment
from core.utils.result_simplified import Errors, Result
from tests.helpers.settings_stub import settings_stub

URL = "/lifepath/alignment/content"

STATUS: LifePathStatus = {
    "has_vision": True,
    "has_designation": True,
    "alignment": {
        "life_path_uid": "lp.x.teacher",
        "life_path_title": "Become a patient teacher",
        "alignment_score": 0.62,
        "alignment_level": "mostly_aligned",
        "dimensions": {
            "knowledge": 0.42,
            "activity": 0.55,
            "goal": 0.5,
            "principle": 0.33,
            "momentum": 0.7,
        },
        "knowledge_stats": {"total": 14, "embodied": 3, "theoretical": 8},
    },
    "recommendations": [{"title": "Strengthen value alignment", "description": "…"}],
}

LIVED: LifePathSubstanceAlignment = {
    "life_path_uid": "lp.x.teacher",
    "life_path_title": "Become a patient teacher",
    "alignment_score": 0.31,
    "knowledge_count": 8,
    "embodied_knowledge": 1,
    "practiced_knowledge": 1,
    "applied_knowledge": 2,
    "theoretical_knowledge": 4,
    "domain_contributions": {
        "tasks": 0.2,
        "habits": 0.45,
        "events": 0.1,
        "entries": 0.25,
        "choices": 0.0,
        "principles": 0.0,
    },
    "gaps": [
        {
            "ku_uid": "ps.teaching.listening",
            "title": "Listening without fixing",
            "substance": 0.0,
            "band": SubstanceBand.THEORETICAL,
        },
        {
            "ku_uid": "ps.teaching.feedback",
            "title": "Feedback on the work",
            # Displays as 0.30 and is banded THEORETICAL from its raw score: the
            # row shows the payload's band, never one re-derived from the display.
            "substance": 0.3,
            "band": SubstanceBand.THEORETICAL,
        },
    ],
    "recommendations": ["Increase substance for: Listening without fixing (currently 0.0)"],
}


def _client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    status: Result[LifePathStatus] | None = None,
    lived: Result[LifePathSubstanceAlignment] | None = None,
) -> tuple[TestClient, MagicMock]:
    def signed_in(_request: object) -> UserUID:
        return UserUID("user_learner")

    monkeypatch.setattr(lifepath_ui, "require_authenticated_user", signed_in)
    monkeypatch.setattr(lifepath_ui, "get_settings", settings_stub(debug=False))
    lifepath = MagicMock()
    lifepath.get_full_status = AsyncMock(return_value=status or Result.ok(STATUS))
    analytics = MagicMock()
    analytics.calculate_life_path_alignment = AsyncMock(return_value=lived or Result.ok(LIVED))
    app, rt = fast_app(pico=False, default_hdrs=False)
    lifepath_ui.create_lifepath_ui_routes(app, rt, lifepath, analytics)
    return TestClient(app), analytics


def _text(page: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


def test_the_page_names_one_alignment_figure(monkeypatch: pytest.MonkeyPatch) -> None:
    client, analytics = _client(monkeypatch)
    page = client.get(URL).text

    analytics.calculate_life_path_alignment.assert_awaited_once_with("user_learner")
    assert "62%" in page
    assert "31%" not in page, "the substance mean rendered beside the alignment score"
    assert "Alignment Score" not in page
    assert "Mostly aligned" in _text(page)
    assert "Become a patient teacher" in page


def test_the_steps_card_counts_every_band(monkeypatch: pytest.MonkeyPatch) -> None:
    page = _text(_client(monkeypatch)[0].get(URL).text)

    assert "8 steps, by how much of each shows up in what you do." in page
    for count, band in ((1, "Embodied"), (1, "Practiced"), (2, "Applied"), (4, "Theoretical")):
        assert f"{count} {band}" in page


def test_each_least_lived_step_links_to_its_step_with_its_own_band(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = _client(monkeypatch)[0].get(URL).text

    rows = re.findall(r"<li[^>]*>(.*?)</li>", page, re.DOTALL)
    assert [re.search(r'href="([^"]*)"', row).group(1) for row in rows] == [  # type: ignore[union-attr]
        "/explore/ps/ps.teaching.listening",
        "/explore/ps/ps.teaching.feedback",
    ]
    assert all(_text(row).endswith("Theoretical") for row in rows), (
        "a row's band came from somewhere other than the payload"
    )


def test_the_practice_card_shows_each_channel_share(monkeypatch: pytest.MonkeyPatch) -> None:
    page = _text(_client(monkeypatch)[0].get(URL).text)

    assert "Where your practice comes from" in page
    assert "Habits 45%" in page
    assert "Choices not yet" in page


def test_a_learner_with_no_practice_reads_a_sentence_not_six_empty_bars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    idle: LifePathSubstanceAlignment = {
        **LIVED,
        "domain_contributions": dict.fromkeys(LIVED["domain_contributions"], 0.0),
    }
    page = _text(_client(monkeypatch, lived=Result.ok(idle))[0].get(URL).text)

    assert "None of your activity touches your path's knowledge yet." in page
    assert "Habits" not in page, "the six channel rows rendered for a learner with no practice"


def test_a_path_with_no_steps_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    empty: LifePathSubstanceAlignment = {
        **LIVED,
        "knowledge_count": 0,
        "gaps": [],
        "domain_contributions": {},
        "message": "Life Path has no path steps yet",
    }
    page = _text(_client(monkeypatch, lived=Result.ok(empty))[0].get(URL).text)

    assert "Life Path has no path steps yet" in page
    assert "Least lived" not in page


def test_a_failed_substance_read_banners_its_cards_and_keeps_the_dimensions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed: Result[LifePathSubstanceAlignment] = Result.fail(
        Errors.database("get_user_knowledge_channels", "read failed")
    )
    page = _client(monkeypatch, lived=failed)[0].get(URL).text

    assert "Could not load how your path's steps are lived" in _text(page)
    assert "Your path's steps" not in _text(page)
    assert "5-Dimension Breakdown" in page and "62%" in page
    assert "read failed" not in page and ".py" not in page


def test_a_failed_status_read_banners_the_fragment_without_developer_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed: Result[LifePathStatus] = Result.fail(Errors.database("get_designation", "read failed"))
    response = _client(monkeypatch, status=failed)[0].get(URL)

    assert response.status_code == 200
    assert 'id="lifepath-alignment-content"' in response.text
    assert "Could not load your Life Path alignment" in response.text
    assert "read failed" not in response.text and ".py" not in response.text


def test_no_designation_redirects_to_the_vision(monkeypatch: pytest.MonkeyPatch) -> None:
    undesignated_status: LifePathStatus = {**STATUS, "has_designation": False}
    undesignated = Result.ok(undesignated_status)
    response = _client(monkeypatch, status=undesignated)[0].get(URL)

    assert response.headers["HX-Redirect"] == "/lifepath/vision"
