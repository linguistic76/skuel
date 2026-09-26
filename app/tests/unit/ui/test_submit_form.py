"""The Submit page's form asks two questions (Submit & Share arc PR 7).

Ask for feedback? Teacher (the default, with or without an exercise) / AI (only
with an exercise, stated honestly) / No — and Share with (optional, collapsed):
the student's groups and co-members in the one vocabulary, plus Portfolio.
The Title field is optional: the title is the student's.
"""

from __future__ import annotations

import re

from fastcore.xml import to_xml  # type: ignore[import-untyped]

from ui.user_entry.forms import (
    ALL_MY_TEACHERS,
    FEEDBACK_AI,
    FEEDBACK_NONE,
    FEEDBACK_TEACHER,
    SUBMIT_PAGE_PATH,
    render_upload_form,
    submit_page_href,
)

_TARGETS = {
    "groups": [{"uid": "g_class", "name": "Physics 101"}],
    "people": [
        {"uid": "user_a", "username": "alice", "display_name": "Alice"},
        {"uid": "user_n", "username": None, "display_name": "Nameless"},
    ],
}


def _checkbox(html: str, value: str) -> str:
    match = re.search(rf'<input[^>]*value="{re.escape(value)}"[^>]*>', html)
    assert match, value
    return match.group(0)


def test_submit_page_href_encodes_its_parameters() -> None:
    assert submit_page_href() == SUBMIT_PAGE_PATH
    assert submit_page_href("ex.a b") == "/submissions/submit?exercise_uid=ex.a+b"
    assert (
        submit_page_href("ex_1", from_ps="ps.x.y")
        == "/submissions/submit?exercise_uid=ex_1&from_ps=ps.x.y"
    )


def test_the_title_field_is_optional_and_says_what_an_empty_one_becomes() -> None:
    with_exercise = to_xml(
        render_upload_form(selected_exercise_uid="ex_1", exercise_title="The Gentle Return")
    )
    assert 'name="title"' in with_exercise
    assert "required" not in _checkbox(with_exercise, "ex_1")  # the hidden exercise field
    assert "Leave empty to use “The Gentle Return v&lt;N&gt;”" in with_exercise
    assert "Answering: " in with_exercise and "The Gentle Return" in with_exercise

    without = to_xml(render_upload_form())
    assert "Leave empty to use the file name" in without
    assert "Answering: " not in without


def test_teacher_is_the_default_and_works_without_an_exercise() -> None:
    html = to_xml(render_upload_form())
    assert f"x-data=\"submit('{FEEDBACK_TEACHER}', true)\"" in html
    assert f"selectFeedback('{FEEDBACK_TEACHER}')" in html
    assert f"selectFeedback('{FEEDBACK_NONE}')" in html
    # the feedback half of the audience and the pipeline ride as bound hidden fields
    assert 'name="pipeline" x-bind:value="pipeline"' in html
    assert (
        'name="audience" x-bind:value="feedbackAudience" x-bind:disabled="!feedbackAudience"'
        in html
    )
    assert 'hx-post="/api/user-entries/upload"' in html


def test_ai_is_disabled_without_an_exercise_and_offered_with_one() -> None:
    without = to_xml(render_upload_form())
    assert f"selectFeedback('{FEEDBACK_AI}')" not in without
    assert "Needs an exercise" in without
    assert "x-data=\"submit('teacher', true)\"" in without

    with_exercise = to_xml(render_upload_form(selected_exercise_uid="ex_1"))
    assert f"selectFeedback('{FEEDBACK_AI}')" in with_exercise
    assert "Needs an exercise" not in with_exercise
    assert "Request AI feedback" in with_exercise  # the honest next step
    assert "x-data=\"submit('teacher', false)\"" in with_exercise


def test_which_class_appears_only_with_several_classes_and_no_exercise() -> None:
    one = to_xml(render_upload_form(teacher_groups=[("g_a", "Physics")]))
    assert 'name="teacher_group"' not in one

    several = to_xml(render_upload_form(teacher_groups=[("g_a", "Physics"), ("g_b", "Chemistry")]))
    assert 'name="teacher_group"' in several
    assert f'<option value="{ALL_MY_TEACHERS}">All my teachers</option>' in several
    assert '<option value="g_b">Chemistry</option>' in several
    assert 'x-model="teacherGroup"' in several

    with_exercise = to_xml(
        render_upload_form(
            selected_exercise_uid="ex_1", teacher_groups=[("g_a", "Physics"), ("g_b", "Chem")]
        )
    )
    assert 'name="teacher_group"' not in with_exercise


def test_share_with_lists_the_targets_in_the_vocabulary_and_the_portfolio_row() -> None:
    html = to_xml(render_upload_form(targets=_TARGETS))
    assert "shareOpen = !shareOpen" in html
    group = _checkbox(html, "group:g_class")
    assert 'name="audience"' in group and "disabled" not in group and "checked" not in group
    person = _checkbox(html, "user:alice")
    assert 'name="audience"' in person and "disabled" not in person
    assert "Physics 101" in html and "Alice" in html and "@alice" in html
    assert "Nameless" not in html  # a person with no username has no vocabulary value
    portfolio = _checkbox(html, "public")
    assert "disabled" in portfolio
    assert "Coming soon" in html


def test_share_with_says_nobody_yet_when_there_is_nobody() -> None:
    html = to_xml(render_upload_form(targets={"groups": [], "people": []}))
    assert "No groups or classmates to share with yet" in html
    assert "group:" not in html and "user:" not in html
    # the Portfolio row is still offered, disabled
    assert "disabled" in _checkbox(html, "public")


def test_hidden_context_fields_ride_along() -> None:
    html = to_xml(render_upload_form(selected_exercise_uid="ex_1", from_ps="ps.a.b"))
    assert 'name="fulfills_exercise_uid" value="ex_1"' in html
    assert 'name="about_path_step_uid" value="ps.a.b"' in html
