"""The Life Path dashboard's doors to the recommended Learning Paths
(ui/lifepath/dashboard.py, the body of ``GET /lifepath/content``).

A learner with a saved vision has a "Recommended Paths" button beside "View
Alignment Details" and "Update Vision". While they have chosen no path, the
alignment card, which cannot measure anything yet, says so and links to the same
page: "See your recommended Learning Paths". A learner with no vision has
neither: their dashboard is the invitation to express one.

The statuses are shaped as ``LifePathService.get_full_status`` builds them.
"""

from __future__ import annotations

import re

from fasthtml.common import to_xml

from core.ports.query_types import LifePathAlignmentResult, LifePathStatus, VisionData
from ui.lifepath.dashboard import render_dashboard_content

RECOMMENDATIONS = "/lifepath/vision/recommendations"
LINK_TEXT = "See your recommended Learning Paths"

VISION = VisionData(
    statement="I want to become a patient teacher",
    themes=["teaching"],
    captured_at="2026-10-31T09:00:00+00:00",
)
ALIGNMENT: LifePathAlignmentResult = {
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
}

VISION_NO_PATH: LifePathStatus = {
    "has_vision": True,
    "has_designation": False,
    "vision": VISION,
    "designation": None,
    "alignment": None,
    "recommendations": [],
    "daily_focus": None,
}
VISION_AND_PATH: LifePathStatus = {
    **VISION_NO_PATH,
    "has_designation": True,
    "designation": {"life_path_uid": "lp.x.teacher", "designated_at": "2026-10-31T09:05:00+00:00"},
    "alignment": ALIGNMENT,
}
NO_VISION: LifePathStatus = {
    "has_vision": False,
    "has_designation": False,
    "alignment": None,
    "recommendations": [],
    "next_step": "Express your vision to get started",
}


def _alignment_card(page: str) -> str:
    """The alignment card: from its heading to the action row that follows it."""
    start = page.index("Alignment Score")
    return page[start : page.index('href="/lifepath/alignment"', start)]


def _action_row(page: str) -> str:
    row = re.search(
        r'<div class="[^"]*">\s*<a [^>]*href="/lifepath/alignment".*?</div>', page, re.DOTALL
    )
    assert row, "the dashboard's action row was not found"
    return row.group(0)


def test_a_vision_without_a_path_links_to_the_recommendations_from_the_alignment_card() -> None:
    page = to_xml(render_dashboard_content(VISION_NO_PATH))

    card = _alignment_card(page)
    assert "Choose a Learning Path for your vision" in card
    assert re.search(rf'<a href="{RECOMMENDATIONS}"[^>]*>{LINK_TEXT}</a>', card)


def test_a_chosen_path_has_no_link_in_the_alignment_card() -> None:
    page = to_xml(render_dashboard_content(VISION_AND_PATH))

    card = _alignment_card(page)
    assert "62%" in card
    assert LINK_TEXT not in page


def test_a_saved_vision_has_the_recommendations_button_with_or_without_a_path() -> None:
    for status in (VISION_NO_PATH, VISION_AND_PATH):
        row = _action_row(to_xml(render_dashboard_content(status)))

        labels = re.findall(r"<a [^>]*>([^<]+)</a>", row)
        assert labels == ["View Alignment Details", "Update Vision", "Recommended Paths"]
        assert f'href="{RECOMMENDATIONS}"' in row


def test_no_vision_has_neither_door() -> None:
    page = to_xml(render_dashboard_content(NO_VISION))

    assert "Express Your Vision" in page
    assert RECOMMENDATIONS not in page
