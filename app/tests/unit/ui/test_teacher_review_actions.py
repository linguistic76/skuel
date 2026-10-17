"""The teacher review body — the student's work, and the one action rule.

The review page (``/teaching/review/{uid}/content``) and the per-student panel
(``/api/teaching/review/{uid}/panel``) render one body
(``ui.teaching.detail.render_review_body``). These pin its contracts:

- the revision form posts the fields ``RequestRevisionRequest`` reads —
  ``instructions`` among them — and never an exercise uid (the service reads the
  exercise from the gated detail);
- where the teacher may not request a revision (no exercise, or the exercise
  names another teacher), the service's sentence replaces the form;
- the actions follow the writers' status guards and the queue's supersession:
  feedback + revision from ``REVIEWABLE_ENTRY_STATUSES``, Approve from
  ``revision_requested``, nothing on a superseded copy;
- every form reports into a target rendered exactly once;
- the card shows the student's ``content``, escaped, and never a server path.

The revision form is also kept as a fixture file under ``tests/js/fixtures/``,
where ``tests/js/revision-form.test.js`` mounts it with the vendored Alpine and
adds and removes feedback points. The drift test keeps that file equal to what
the Python renders; regenerate it with
``SKUEL_WRITE_JS_FIXTURES=1 uv run pytest tests/unit/ui/test_teacher_review_actions.py``.
"""

from __future__ import annotations

import html as html_lib
import os
import re
from pathlib import Path

import pytest
from fasthtml.common import to_xml

from core.models.enums.learning_enums import FeedbackCategory
from core.models.teaching.teaching_request import RequestRevisionRequest
from core.services.report.teacher_review_service import (
    REVISION_NAMED_TEACHER_ONLY,
    REVISION_NEEDS_EXERCISE,
)
from ui.components.form import _FIELD_SIZE
from ui.teaching.detail import render_review_body, render_submission_content
from ui.teaching.forms import (
    FEEDBACK_POINT_INDEX,
    render_review_actions,
    render_revision_request_form,
)
from ui.teaching.types import submission_detail_from_dict

UID = "ue_abc12345"
_REVISION_POST = f"/api/teaching/review/{UID}/revision"
_APPROVE_POST = f"/api/teaching/review/{UID}/approve"
_APP_ROOT = Path(__file__).resolve().parents[3]
_SKUEL_JS = _APP_ROOT / "static" / "js" / "skuel.js"
_FIXTURE = _APP_ROOT / "tests" / "js" / "fixtures" / "revision-form.html"


def _html(status: str, *, revision_refusal: str | None = None, superseded: bool = False) -> str:
    return to_xml(render_review_actions(UID, status, revision_refusal, superseded))


def _revision_form(html: str) -> str:
    forms = re.findall(r"<form\b[^>]*>.*?</form>", html, flags=re.DOTALL)
    revision = [f for f in forms if f'hx-post="{_REVISION_POST}"' in f]
    assert len(revision) == 1, f"expected exactly one revision form, found {len(revision)}"
    return revision[0]


def _template_rows(form_html: str) -> list[str]:
    return re.findall(r"<template\b[^>]*>(.*?)</template>", form_html, flags=re.DOTALL)


def _field_names(form_html: str) -> set[str]:
    """The names the form posts — a ``<template>``'s content is not part of the form."""
    posted = re.sub(r"<template\b[^>]*>.*?</template>", "", form_html, flags=re.DOTALL)
    return set(re.findall(r'<(?:input|textarea|select)\b[^>]*\bname="([^"]+)"', posted))


class TestRevisionFormPostsWhatTheRouteReads:
    def test_every_posted_name_is_a_request_field(self) -> None:
        names = _field_names(_revision_form(_html("submitted")))

        assert "instructions" in names
        assert names <= set(RequestRevisionRequest.model_fields)
        assert "exercise_uid" not in names  # the route reads it from the gated detail

    def test_instructions_are_required(self) -> None:
        form = _revision_form(_html("submitted"))
        textarea = re.search(r'<textarea\b[^>]*name="instructions"[^>]*>', form)
        assert textarea is not None and "required" in textarea.group(0)

    def test_the_form_carries_feedback_points_and_rationale(self) -> None:
        assert {"fp_count", "revision_rationale"} <= _field_names(
            _revision_form(_html("submitted"))
        )

    @pytest.mark.parametrize("reason", [REVISION_NEEDS_EXERCISE, REVISION_NAMED_TEACHER_ONLY])
    def test_a_refusal_replaces_the_form_and_keeps_the_report(self, reason: str) -> None:
        html = _html("submitted", revision_refusal=reason)

        assert f'hx-post="{_REVISION_POST}"' not in html
        assert reason in html_lib.unescape(html)
        assert 'name="feedback_file"' in html

    def test_the_feedback_point_row_is_a_server_template_of_the_components(self) -> None:
        """``revisionForm`` copies this row; its names, options and field sizes come from here."""
        rows = _template_rows(_revision_form(_html("submitted")))
        assert len(rows) == 1
        row = rows[0]
        index = FEEDBACK_POINT_INDEX

        select = re.search(
            rf'<select\b[^>]*name="fp_category_{index}"[^>]*>(.*?)</select>', row, re.DOTALL
        )
        detail = re.search(rf'<input\b[^>]*name="fp_detail_{index}"[^>]*>', row)
        assert select and detail
        options = re.findall(r'<option value="([^"]+)">([^<]+)</option>', select.group(1))
        assert options == [(c.value, c.get_label()) for c in FeedbackCategory]
        for tag in (select.group(0), detail.group(0)):
            classes = re.search(r'class="([^"]*)"', tag)
            assert classes and set(_FIELD_SIZE.split()) <= set(classes.group(1).split())
        assert "required" in detail.group(0)
        assert 'aria-label="Remove feedback point"' in row

    def test_skuel_js_copies_the_template_and_holds_no_category_list(self) -> None:
        source = _SKUEL_JS.read_text()
        start = source.index("Alpine.data('revisionForm'")
        block = source[start : source.index("Alpine.data(", start + 1)]

        assert "fpRowTemplate" in block and f"'{FEEDBACK_POINT_INDEX}'" in block
        assert not any(f"'{c.value}'" in block for c in FeedbackCategory)
        assert "fp_category_" not in block and "fp_detail_" not in block


def test_js_fixture_matches_the_rendered_markup() -> None:
    rendered = to_xml(render_revision_request_form(UID, "revision-result"))
    if os.environ.get("SKUEL_WRITE_JS_FIXTURES") == "1":
        _FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        _FIXTURE.write_text(rendered)
    assert _FIXTURE.exists() and _FIXTURE.read_text() == rendered, (
        f"{_FIXTURE} is stale — regenerate with SKUEL_WRITE_JS_FIXTURES=1 "
        "uv run pytest tests/unit/ui/test_teacher_review_actions.py"
    )


class TestTheActionRule:
    @pytest.mark.parametrize("status", ["submitted", "active"])
    def test_a_reviewable_entry_offers_feedback_and_revision(self, status: str) -> None:
        html = _html(status)
        assert f'hx-post="/api/teaching/review/{UID}/report"' in html
        assert f'hx-post="{_REVISION_POST}"' in html
        assert _APPROVE_POST not in html

    @pytest.mark.parametrize("status", ["queued", "processing", "completed", "draft"])
    def test_no_form_the_writers_would_refuse(self, status: str) -> None:
        html = _html(status)
        assert "hx-post" not in html
        assert "not awaiting review" in html

    def test_revision_requested_offers_approve_only(self) -> None:
        html = _html("revision_requested")
        assert f'hx-post="{_APPROVE_POST}"' in html
        assert _REVISION_POST not in html

    @pytest.mark.parametrize("status", ["submitted", "revision_requested"])
    def test_a_superseded_copy_offers_nothing(self, status: str) -> None:
        html = _html(status, superseded=True)
        assert "hx-post" not in html
        assert "this copy is history" in html

    @pytest.mark.parametrize("status", ["submitted", "revision_requested"])
    def test_every_target_is_rendered_exactly_once(self, status: str) -> None:
        html = _html(status)
        targets = set(re.findall(r'hx-target="#([^"]+)"', html))
        assert targets, "the actions render no target"
        for target in targets:
            assert len(re.findall(rf'\bid="{re.escape(target)}"', html)) == 1, target


class TestTheCardShowsTheStudentsWork:
    def _card(self, **fields: object) -> str:
        detail = submission_detail_from_dict({"uid": UID, "status": "submitted", **fields})
        return to_xml(render_submission_content(detail))

    def test_the_content_is_shown_escaped(self) -> None:
        html = self._card(content="<script>alert(1)</script> My paragraph.")
        assert "&lt;script&gt;alert(1)&lt;/script&gt; My paragraph." in html
        assert "<script>alert(1)" not in html

    def test_an_upload_with_no_text_names_its_file(self) -> None:
        html = self._card(content=None, original_filename="essay.pdf")
        assert "Uploaded file: essay.pdf — no text to show." in html

    def test_no_text_at_all_says_so(self) -> None:
        assert "No text submitted." in self._card(content="   ")

    def test_the_server_path_never_renders(self) -> None:
        html = self._card(content="Words.", file_path="/srv/secret/path.md")
        assert "/srv/secret" not in html

    def test_the_version_prints_beside_the_exercise(self) -> None:
        html = self._card(content="Words.", exercise_title="The Gentle Return", revision=3)
        assert "Exercise: The Gentle Return · v3" in html


class TestTheConverter:
    def test_it_carries_what_the_body_reads(self) -> None:
        detail = submission_detail_from_dict(
            {
                "title": None,
                "status": "SUBMITTED",
                "exercise_uid": "ex.root",
                "revision": 2,
                "superseded": True,
                "processed_content": "never shown",
                "file_path": "/srv/x",
            }
        )
        assert detail.title == "Untitled"
        assert detail.status == "submitted"
        assert detail.exercise_uid == "ex.root"
        assert detail.revision == 2
        assert detail.superseded is True

    def test_the_body_wires_the_rule_to_the_detail(self) -> None:
        detail = submission_detail_from_dict(
            {
                "title": "Essay",
                "status": "submitted",
                "content": "Words.",
                "exercise_uid": "ex.root",
            }
        )
        html = to_xml(render_review_body(UID, detail, []))
        assert "Words." in html
        assert 'name="fp_count"' in html  # a turn-in: the exercise fields render
