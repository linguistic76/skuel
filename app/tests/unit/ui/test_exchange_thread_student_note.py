"""The exchange thread's teacher note names the student — never their uid."""

from __future__ import annotations

from fasthtml.common import to_xml

from core.ports.query_types import ExchangeThread
from ui.learning_loop.exchange_thread import render_exchange_thread

STUDENT = "user_bf2a1c0e8d7f6a51"
TEACHER = "user_819f725e53621059"


def _thread(student_name: str) -> ExchangeThread:
    return ExchangeThread(
        exercise_uid="ex.zz.one",
        exercise_title="One",
        exercise_removed=False,
        student_uid=STUDENT,
        student_name=student_name,
        entries=[],
        reports=[],
        revisions=[],
    )


def test_a_teacher_reads_the_students_name() -> None:
    html = to_xml(render_exchange_thread(_thread("Sam Student"), viewer_uid=TEACHER))

    assert "with Sam Student" in html
    assert f"with {STUDENT.removeprefix('user_')}" not in html


def test_a_student_with_no_name_gets_no_note() -> None:
    html = to_xml(render_exchange_thread(_thread(""), viewer_uid=TEACHER))

    assert "with " not in html


def test_the_student_reads_no_note_about_themselves() -> None:
    html = to_xml(render_exchange_thread(_thread("Sam Student"), viewer_uid=STUDENT))

    assert "with Sam Student" not in html
