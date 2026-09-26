"""The Share panel (Submit & Share arc R2, R7, R8) — server-rendered checkboxes in the vocabulary."""

from __future__ import annotations

import re

from fasthtml.common import to_xml

from core.services.user_entry.audience_resolver import ShareOutcome
from ui.gradebook.share_panel import ShareButton, SharePanelForm

_CANDIDATES = {
    "groups": [{"uid": "g_1", "name": "Physics 101"}, {"uid": "g_2", "name": "Chemistry"}],
    "people": [
        {"uid": "user_a", "username": "alice", "display_name": "Alice"},
        {"uid": "user_b", "username": "bob", "display_name": None},
    ],
    "shared_group_uids": ["g_2"],
    "shared_user_uids": ["user_b"],
}


def test_form_posts_the_vocabulary_values_and_marks_what_is_already_shared() -> None:
    html = to_xml(SharePanelForm("ue_1", _CANDIDATES))
    assert 'hx-post="/api/user-entries/ue_1/share"' in html
    assert 'name="audience" value="group:g_1"' in html
    assert 'name="audience" value="user:alice"' in html
    assert "Physics 101" in html and "Alice" in html and "@bob" in html
    # already shared → checked + disabled, on exactly the two shared targets
    assert html.count("disabled") == 2
    shared_g2 = re.search(r'<input[^>]*value="group:g_2"[^>]*>', html)
    assert shared_g2 and "checked" in shared_g2.group(0) and "disabled" in shared_g2.group(0)
    fresh_g1 = re.search(r'<input[^>]*value="group:g_1"[^>]*>', html)
    assert fresh_g1 and "disabled" not in fresh_g1.group(0)
    assert "Your wall" in html


def test_form_with_nobody_to_offer_says_so() -> None:
    html = to_xml(
        SharePanelForm(
            "ue_1",
            {"groups": [], "people": [], "shared_group_uids": [], "shared_user_uids": []},
        )
    )
    assert "No groups or classmates to share with yet" in html
    assert "hx-post" not in html


def test_form_shows_the_outcome_and_the_error() -> None:
    outcome = ShareOutcome(
        shared_groups=("g_1",), shared_users=("user_a",), newly_shared_users=("user_a",)
    )
    html = to_xml(SharePanelForm("ue_1", _CANDIDATES, outcome=outcome))
    assert "Shared with 2 targets" in html
    assert "1 notified" in html
    assert "Refused" not in html

    html = to_xml(SharePanelForm("ue_1", _CANDIDATES, error="A private entry cannot be shared"))
    assert "A private entry cannot be shared" in html


def test_button_loads_the_panel_lazily_and_opens_on_request() -> None:
    closed = to_xml(ShareButton("ue_1"))
    assert 'hx-get="/gradebook/ue_1/share-panel"' in closed
    assert "shareOpen: false" in closed
    opened = to_xml(ShareButton("ue_1", open=True))
    assert "shareOpen: true" in opened
