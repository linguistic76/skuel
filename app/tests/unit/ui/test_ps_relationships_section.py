"""The PathStep page's relationship graph: what it asks for, and what it leaves out."""

from __future__ import annotations

import html
import json
import re
from types import SimpleNamespace

from fasthtml.common import to_xml

from core.models.relationship_registry import PS_CONFIG
from ui.explore.ps_detail import render_ps_detail_content
from ui.patterns.relationships.relationship_graph import RelationshipGraphView

_UID = "ps.test.step"


def _page(user_uid: str | None) -> str:
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
            user_uid=user_uid,
            prerequisites=[],
        )
    )


def _graph_args(page: str) -> list[object]:
    match = re.search(r"""x-data=(['"])relationshipGraph\((.*?)\)\1""", page, re.DOTALL)
    assert match, "the page mounts no relationship graph"
    args: list[object] = json.loads(f"[{html.unescape(match.group(2))}]")
    return args


def test_a_signed_in_reader_gets_the_graph_over_the_registrys_edges() -> None:
    assert _graph_args(_page("user_test")) == [
        _UID,
        "ps",
        2,
        ",".join(sorted(PS_CONFIG.cross_domain_relationship_types)),
    ]


def test_a_signed_out_reader_gets_no_graph() -> None:
    assert "relationshipGraph" not in _page(None)


def test_the_lateral_views_that_would_contradict_the_page_stay_off() -> None:
    page = _page("user_test")

    assert "lateral/chain" not in page
    assert "lateral/alternatives" not in page


def test_the_legend_describes_only_the_lateral_graph() -> None:
    lateral = to_xml(RelationshipGraphView("task_abc", "tasks"))
    chosen = to_xml(RelationshipGraphView("ps.abc", "ps", types=("USES_KU",)))

    assert "Complementary" in lateral
    assert "Complementary" not in chosen
