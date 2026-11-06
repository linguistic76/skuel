"""Blocking dependencies: what the PathStep page seeds for each read of its prerequisites."""

from __future__ import annotations

import html
import json
import os
import re
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from fasthtml.common import FT, Div, to_xml

from core.ports.query_types import PsPrerequisiteStatusRow
from ui.explore.ps_detail import _blocking_seed, _deps_accordion, render_ps_detail_content

_UID = "ps.test.step"
_FIXTURE = Path(__file__).resolve().parents[2] / "js" / "fixtures" / "ps-blocking-accordion.html"


def _page(prerequisites: list[PsPrerequisiteStatusRow] | None) -> str:
    step = SimpleNamespace(title="A step", description="", estimated_time_minutes=None, tags=())
    return to_xml(
        render_ps_detail_content(
            step=step,
            uid=_UID,
            content_html="",
            is_marked_read=False,
            is_bookmarked=False,
            is_in_progress=False,
            is_mastered=False,
            user_uid="user_test",
            prerequisites=prerequisites,
        )
    )


def _blocking(page: str) -> list[dict[str, str]]:
    match = re.search(r"""x-data=(['"])pathstep\((.*?)\)\1""", page, re.DOTALL)
    assert match, "the page carries no pathstep seed"
    return cast("list[dict[str, str]]", json.loads(html.unescape(match.group(2)))["blocking"])


def _row(
    uid: str, title: str, entity_type: str = "path_step", *, completed: bool
) -> PsPrerequisiteStatusRow:
    return {"uid": uid, "title": title, "entity_type": entity_type, "completed": completed}


def test_a_completed_prerequisite_reads_completed_and_the_rest_are_blocked() -> None:
    blocking = _blocking(
        _page(
            [
                _row("ps.test.done", "Done first", completed=True),
                _row("ps.test.open", "Still open", completed=False),
            ]
        )
    )

    assert blocking == [
        {
            "uid": "ps.test.done",
            "title": "Done first",
            "href": "/explore/ps/ps.test.done",
            "status": "completed",
        },
        {
            "uid": "ps.test.open",
            "title": "Still open",
            "href": "/explore/ps/ps.test.open",
            "status": "blocked",
        },
    ]


def test_a_knowledge_prerequisite_links_to_its_own_page() -> None:
    blocking = _blocking(_page([_row("ku.test.one", "A concept", "ku", completed=False)]))

    assert blocking[0]["href"] == "/explore/ku/ku.test.one"


def test_a_title_with_quotes_survives_the_seed() -> None:
    title = """It's "tricky" <b>"""

    blocking = _blocking(_page([_row("ps.test.q", title, completed=False)]))

    assert blocking[0]["title"] == title


def test_no_prerequisites_is_an_empty_list_with_the_section_shown() -> None:
    page = _page([])

    assert _blocking(page) == []
    assert "Blocking dependencies" in page


def test_a_failed_read_leaves_the_section_out() -> None:
    page = _page(None)

    assert "Blocking dependencies" not in page
    assert "nothing blocks this step" not in page


def _accordion() -> FT:
    seed = {
        "blocking": _blocking_seed(
            [
                _row("ps.test.done", "Done first", completed=True),
                _row("ps.test.open", "Still open", completed=False),
            ]
        )
    }
    return Div(_deps_accordion(), **{"x-data": f"pathstep({json.dumps(seed)})"})


def test_js_fixture_matches_the_rendered_accordion() -> None:
    """``tests/js/ps-blocking-accordion.test.js`` runs ``static/js/ps-detail.js`` on this markup."""
    rendered = to_xml(_accordion())
    if os.environ.get("SKUEL_WRITE_JS_FIXTURES") == "1":
        _FIXTURE.write_text(rendered)
    assert _FIXTURE.read_text() == rendered, (
        f"{_FIXTURE} is stale — regenerate with SKUEL_WRITE_JS_FIXTURES=1 "
        "uv run pytest tests/unit/ui/test_ps_blocking_seed.py"
    )
