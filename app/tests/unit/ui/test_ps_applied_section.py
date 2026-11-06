"""How you've applied this: what the section says for each reading of a step."""

from __future__ import annotations

from types import SimpleNamespace

from fasthtml.common import to_xml

from core.ports.query_types import PsKuSubstanceRow, PsUserSubstanceResult
from ui.explore.ps_detail import (
    render_ps_applied,
    render_ps_applied_error,
    render_ps_detail_content,
)

_UID = "ps.test.step"


def _row(
    uid: str = "ku.test.one",
    title: str = "Naming a feeling",
    substance: float = 0.0,
    mastery: float = 0.0,
) -> PsKuSubstanceRow:
    return {
        "ku_uid": uid,
        "ku_title": title,
        "substance_score": substance,
        "mastery_score": mastery,
        "is_ready_to_learn": False,
    }


def _substance(*rows: PsKuSubstanceRow) -> PsUserSubstanceResult:
    return {
        "ps_uid": _UID,
        "user_uid": "user_test",
        "overall_substance_score": 0.0,
        "overall_mastery_score": 0.0,
        "is_ready_to_learn": False,
        "taught_kus_count": len(rows),
        "underlying_kus": list(rows),
        "status_message": "Starting to practice this material.",
    }


def test_a_step_teaching_no_ku_has_no_section() -> None:
    html = to_xml(render_ps_applied(_substance()))

    assert 'id="ps-applied-fragment"' in html
    assert "How you&#x27;ve applied this" not in html
    assert "How you've applied this" not in html
    assert "Starting to practice" not in html


def test_nothing_applied_says_how_to_change_that_and_lists_no_rows() -> None:
    html = to_xml(render_ps_applied(_substance(_row())))

    assert "Starting to practice this material." in html
    assert "Link a task, habit, event, choice or principle" in html
    assert "Applied 0%" not in html
    assert "<li" not in html


def test_each_taught_ku_gets_a_linked_row_with_its_reading() -> None:
    html = to_xml(
        render_ps_applied(
            _substance(
                _row("ku.test.one", "Naming a feeling", substance=0.15),
                _row("ku.test.two", "Pausing first", substance=0.0),
            )
        )
    )

    assert 'href="/explore/ku/ku.test.one"' in html
    assert "Naming a feeling" in html
    assert "Applied 15%" in html
    assert 'aria-valuenow="15"' in html
    assert 'aria-label="Naming a feeling: applied 15%"' in html
    assert 'href="/explore/ku/ku.test.two"' in html
    assert "Applied 0%" in html
    assert "Link a task" not in html


def test_mastery_shows_only_when_there_is_some() -> None:
    applied_only = to_xml(render_ps_applied(_substance(_row(substance=0.1))))
    mastered = to_xml(render_ps_applied(_substance(_row(substance=0.0, mastery=0.8))))

    assert "Mastery" not in applied_only
    # Mastery alone is a reading too: the row shows, not the "nothing applied" prompt.
    assert "Applied 0% · Mastery 80%" in mastered
    assert "Link a task" not in mastered


def test_the_error_line_stands_in_the_section() -> None:
    html = to_xml(render_ps_applied_error("We could not read this just now."))

    assert 'id="ps-applied-fragment"' in html
    assert "We could not read this just now." in html


def test_the_page_mounts_the_section_for_a_signed_in_reader_only() -> None:
    step = SimpleNamespace(title="A step", description="", estimated_time_minutes=None, tags=())
    common = {
        "step": step,
        "uid": _UID,
        "content_html": "",
        "is_marked_read": False,
        "is_bookmarked": False,
        "is_in_progress": False,
        "is_mastered": False,
    }

    signed_in = to_xml(render_ps_detail_content(user_uid="user_test", **common))
    signed_out = to_xml(render_ps_detail_content(user_uid=None, **common))

    assert f'hx-get="/explore/ps/{_UID}/applied"' in signed_in
    assert "/applied" not in signed_out
