"""The Share panel (Submit & Share arc R2, R7, R8) — server-rendered checkboxes in the vocabulary."""

from __future__ import annotations

import re

from fasthtml.common import to_xml

from core.services.user_entry.audience_resolver import ShareOutcome
from ui.gradebook.share_panel import PRESELECT_REVIEWERS, ShareButton, SharePanelForm

_CANDIDATES = {
    "groups": [{"uid": "g_1", "name": "Physics 101"}, {"uid": "g_2", "name": "Chemistry"}],
    "people": [
        {"uid": "user_a", "username": "alice", "display_name": "Alice"},
        {"uid": "user_b", "username": "bob", "display_name": None},
    ],
    "shared_group_uids": ["g_2"],
    "shared_user_uids": ["user_b"],
    "reviewer_group_uids": ["g_1", "g_2", "g_unoffered"],
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
            {
                "groups": [],
                "people": [],
                "shared_group_uids": [],
                "shared_user_uids": [],
                "reviewer_group_uids": [],
            },
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


def _checkbox(html: str, value: str) -> str:
    match = re.search(rf'<input[^>]*value="{re.escape(value)}"[^>]*>', html)
    assert match, value
    return match.group(0)


def test_preselect_reviewers_checks_the_offered_reviewer_groups_not_yet_shared() -> None:
    """The GradeBook nudge (Submit & Share arc R2): the class that reviewed the
    work is checked — enabled, so the owner can still untick it; a reviewer
    group already shared stays checked + disabled as before; a reviewer group
    the panel does not offer is never invented; people are untouched."""
    html = to_xml(SharePanelForm("ue_1", _CANDIDATES, preselect=PRESELECT_REVIEWERS))
    g1 = _checkbox(html, "group:g_1")
    assert "checked" in g1 and "disabled" not in g1
    g2 = _checkbox(html, "group:g_2")
    assert "checked" in g2 and "disabled" in g2
    assert "g_unoffered" not in html
    alice = _checkbox(html, "user:alice")
    assert "checked" not in alice
    assert html.count("checked") == 3  # g_1 (preselected), g_2 and bob (shared)


def test_an_unknown_preselect_token_preselects_nothing() -> None:
    html = to_xml(SharePanelForm("ue_1", _CANDIDATES, preselect="everyone"))
    assert "checked" not in _checkbox(html, "group:g_1")
    assert html == to_xml(SharePanelForm("ue_1", _CANDIDATES))


def test_the_button_forwards_the_preselect_token_to_the_panel_load() -> None:
    html = to_xml(ShareButton("ue_1", open=True, preselect=PRESELECT_REVIEWERS))
    assert 'hx-get="/gradebook/ue_1/share-panel?preselect=reviewers"' in html
    assert "shareOpen: true" in html
    # dynamic parts are percent-encoded, never interpolated raw
    odd = to_xml(ShareButton("ue_1", preselect="a b&c"))
    assert 'hx-get="/gradebook/ue_1/share-panel?preselect=a+b%26c"' in odd
