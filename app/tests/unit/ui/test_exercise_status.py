"""Exercise status chip derivation — loop-phase precedence + action links.

The vault exercise channel (PR 2 surfaces) added the ``in_progress`` display
key: a living vault entry declares the exercise via its intent property
(``has_in_progress``) and the chip shows "In Progress" — but only until a
turn-in exists, because the living entry keeps its intent forever and a copy
outranks declared intent.
"""

from __future__ import annotations

from typing import Any, cast

from fasthtml.common import to_xml

from core.ports.query_types import ExerciseStatusRow
from ui.learning_loop.exercise_status import (
    exercise_action_link,
    exercise_status_badge,
    exercise_status_key,
)


def _row(**overrides: Any) -> ExerciseStatusRow:
    base: dict[str, Any] = {
        "uid": "exercise.demo",
        "title": "Demo",
        "description": None,
        "due_date": None,
        "group_name": "",
        "has_submission": False,
        "submission_uid": None,
        "submission_status": None,
        "has_report": False,
        "report_uid": None,
        "report_outcome": None,
        "has_in_progress": False,
        "in_progress_uid": None,
    }
    base.update(overrides)
    return cast("ExerciseStatusRow", base)


class TestExerciseStatusKeyPrecedence:
    def test_default_is_not_submitted(self) -> None:
        assert exercise_status_key(_row()) == "not_submitted"

    def test_living_intent_alone_is_in_progress(self) -> None:
        row = _row(has_in_progress=True, in_progress_uid="ue.vault.tasks-list")
        assert exercise_status_key(row) == "in_progress"

    def test_submission_outranks_living_intent(self) -> None:
        """After the frozen copy files, the living entry keeps its intent
        property — the chip must advance to Submitted, not stick at
        In Progress forever."""
        row = _row(
            has_in_progress=True,
            in_progress_uid="ue.vault.tasks-list",
            has_submission=True,
            submission_uid="ue_copy1",
        )
        assert exercise_status_key(row) == "submitted"

    def test_report_outranks_everything(self) -> None:
        row = _row(
            has_in_progress=True,
            has_submission=True,
            has_report=True,
            report_uid="er_1",
        )
        assert exercise_status_key(row) == "feedback_available"

    def test_needs_revision_report(self) -> None:
        row = _row(has_report=True, report_outcome="NEEDS_REVISION")
        assert exercise_status_key(row) == "revision_requested"


class TestInProgressRendering:
    def test_badge_renders_in_progress_label(self) -> None:
        html = to_xml(exercise_status_badge("in_progress"))
        assert "In Progress" in html

    def test_action_link_targets_living_entry_gradebook_page(self) -> None:
        row = _row(has_in_progress=True, in_progress_uid="ue.vault.tasks-list")
        html = to_xml(exercise_action_link(row))
        assert "/gradebook/ue.vault.tasks-list" in html
        assert "View Entry" in html

    def test_not_submitted_action_link_unchanged(self) -> None:
        html = to_xml(exercise_action_link(_row()))
        assert "/submit?exercise_uid=exercise.demo" in html
