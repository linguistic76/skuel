"""The teacher review body — the student's work, and the one action rule.

The review page (``/teaching/review/{uid}/content``) and the per-student panel
(``/api/teaching/review/{uid}/panel``) render one body
(``ui.teaching.detail.render_review_body``). These pin its contracts:

- the revision form posts the fields ``RequestRevisionRequest`` reads —
  ``instructions`` among them — and never an exercise uid (the route reads the
  exercise from the gated detail);
- the actions follow the writers' status guards and the queue's supersession:
  feedback + revision from ``REVIEWABLE_ENTRY_STATUSES``, Approve from
  ``revision_requested``, nothing on a superseded copy;
- every form reports into a target rendered exactly once;
- the card shows the student's ``content``, escaped, and never a server path.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fasthtml.common import to_xml

from core.models.enums.learning_enums import FeedbackCategory
from core.models.teaching.teaching_request import RequestRevisionRequest
from ui.teaching.detail import render_review_body, render_submission_content
from ui.teaching.forms import render_review_actions
from ui.teaching.types import submission_detail_from_dict

UID = "ue_abc12345"
_REVISION_POST = f"/api/teaching/review/{UID}/revision"
_APPROVE_POST = f"/api/teaching/review/{UID}/approve"
_SKUEL_JS = Path(__file__).resolve().parents[3] / "static" / "js" / "skuel.js"


def _html(status: str, *, has_exercise: bool = True, superseded: bool = False) -> str:
    return to_xml(render_review_actions(UID, status, has_exercise, superseded))


def _revision_form(html: str) -> str:
    forms = re.findall(r"<form\b[^>]*>.*?</form>", html, flags=re.DOTALL)
    revision = [f for f in forms if f'hx-post="{_REVISION_POST}"' in f]
    assert len(revision) == 1, f"expected exactly one revision form, found {len(revision)}"
    return revision[0]


def _field_names(form_html: str) -> set[str]:
    return set(re.findall(r'<(?:input|textarea|select)\b[^>]*\bname="([^"]+)"', form_html))


class TestRevisionFormPostsWhatTheRouteReads:
    @pytest.mark.parametrize("has_exercise", [True, False], ids=["turn-in", "no-exercise"])
    def test_every_posted_name_is_a_request_field(self, has_exercise: bool) -> None:
        names = _field_names(_revision_form(_html("submitted", has_exercise=has_exercise)))

        assert "instructions" in names
        assert names <= set(RequestRevisionRequest.model_fields)
        assert "exercise_uid" not in names  # the route reads it from the gated detail

    def test_instructions_are_required(self) -> None:
        form = _revision_form(_html("submitted"))
        textarea = re.search(r'<textarea\b[^>]*name="instructions"[^>]*>', form)
        assert textarea is not None and "required" in textarea.group(0)

    def test_feedback_points_and_rationale_only_for_a_turn_in(self) -> None:
        with_exercise = _field_names(_revision_form(_html("submitted", has_exercise=True)))
        without = _field_names(_revision_form(_html("submitted", has_exercise=False)))

        assert {"fp_count", "revision_rationale"} <= with_exercise
        assert not {"fp_count", "revision_rationale"} & without

    def test_the_alpine_rows_post_the_names_the_route_reads(self) -> None:
        """``fp_category_{i}`` / ``fp_detail_{i}`` are emitted by skuel.js, not the
        Python render — pin them where they are written, bounded to the block."""
        source = _SKUEL_JS.read_text()
        start = source.index("Alpine.data('revisionForm'")
        block = source[start : source.index("Alpine.data(", start + 1)]

        assert "'fp_category_' + idx" in block.replace('"', "'")
        assert "'fp_detail_' + idx" in block.replace('"', "'")
        categories = set(re.findall(r"value: '([a-z_]+)'", block))
        assert categories, "no categories found in the revisionForm block"
        assert categories <= {c.value for c in FeedbackCategory}


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
