"""The teaching student page's KU tab: one emptiness, one message.

The summary's counts are the lengths of the four interaction lists, so "no
interactions" is one fact. The tab says it once, in the line its sibling tabs use for
an empty list; with interactions it shows the summary and the list.
"""

import re
from typing import Any

from fasthtml.common import to_xml

from ui.teaching.detail import render_student_detail_sections

# boundary: the KU detail is a summary map beside four interaction lists, as the renderer takes it
_EMPTY: dict[str, Any] = {
    "summary": {},
    "viewed": [],
    "in_progress": [],
    "mastered": [],
    "bookmarked": [],
}


def _ku_panel(ku_detail: dict[str, Any] | None) -> str:  # boundary: the KU detail shape
    xml = to_xml(
        render_student_detail_sections(
            pending=[], revision_requested=[], completed=[], student_name="Ada", ku_detail=ku_detail
        )
    )
    return xml[xml.index("section === 'ku'") :]


def _texts(xml: str) -> list[str]:
    return [t.strip() for t in re.findall(r">([^<>]+)<", xml) if t.strip()]


def test_no_interactions_is_said_once() -> None:
    texts = _texts(_ku_panel(_EMPTY))
    assert texts == ["No Knowledge Unit interactions yet."], texts


def test_no_interactions_uses_the_sibling_tabs_empty_line() -> None:
    panel = _ku_panel(_EMPTY)
    assert (
        '<p class="text-center text-muted-foreground text-sm">No Knowledge Unit interactions yet.</p>'
        in panel
    )


def test_interactions_show_the_summary_and_the_list() -> None:
    viewed = [{"uid": "ku.sel.naming", "title": "Naming a feeling", "last_viewed_at": "2026-10-20"}]
    detail = {**_EMPTY, "viewed": viewed, "summary": {"viewed_count": 1}}
    texts = _texts(_ku_panel(detail))
    assert "Naming a feeling" in texts
    assert "Viewed" in texts
    assert not any("No Knowledge Unit" in t or "no KU interactions" in t for t in texts)


def test_unavailable_detail_still_says_so() -> None:
    assert _texts(_ku_panel(None)) == ["KU progress data unavailable."]
