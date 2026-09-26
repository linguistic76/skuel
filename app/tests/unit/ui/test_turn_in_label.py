"""The exercise-and-version label beside a turn-in's title (Submit & Share arc PR 7 ruling).

The title is the student's; which exercise and which attempt is read from the
turn-in snapshot and printed by one renderer on every surface.
"""

from __future__ import annotations

from datetime import datetime

from fastcore.xml import to_xml  # type: ignore[import-untyped]

from adapters.inbound.user_entry_ui import _to_history_dict
from core.models.enums.entity_enums import EntityType
from core.models.enums.pipeline import Pipeline
from core.models.user_entry.user_entry import UserEntry
from core.models.user_entry.user_entry_dto import UserEntryDTO
from ui.learning_loop.report import render_submission_history_row
from ui.learning_loop.turn_in_label import TurnInBadge, TurnInNote, turn_in_label
from ui.teaching.cards import render_queue_item
from ui.teaching.types import queue_item_from_dict


def test_label_is_exercise_and_version():
    assert turn_in_label("The Gentle Return", 3) == "The Gentle Return · v3"


def test_label_without_a_version_is_the_exercise_alone():
    assert turn_in_label("The Gentle Return", None) == "The Gentle Return"


def test_no_exercise_means_no_label():
    assert turn_in_label(None, 2) is None
    assert turn_in_label("  ", 2) is None
    assert TurnInBadge(None, 2) == ""
    assert TurnInNote(None, 2) == ""


def test_note_and_badge_carry_the_label():
    assert "for The Gentle Return · v3" in to_xml(TurnInNote("The Gentle Return", 3))
    assert "The Gentle Return · v3" in to_xml(TurnInBadge("The Gentle Return", 3))


def test_the_snapshot_version_rides_the_dto_onto_the_model():
    dto = UserEntryDTO.from_dict(
        {
            "uid": "ue_1",
            "title": "My own words",
            "entity_type": "user_entry",
            "user_uid": "user_1",
            "pipeline": "teacher_review",
            "turn_in_exercise_uid": "ex.root",
            "turn_in_exercise_title": "The Gentle Return",
            "turn_in_revision": 3,
        }
    )
    entry = UserEntry.from_dto(dto)
    assert entry.turn_in_revision == 3
    assert entry.to_dto().turn_in_revision == 3


def _entry() -> UserEntry:
    now = datetime.now()
    return UserEntry(
        uid="ue_1",
        title="My own words",
        entity_type=EntityType.USER_ENTRY,
        user_uid="user_1",
        pipeline=Pipeline.TEACHER_REVIEW,
        original_filename="gentle_return_response.md",
        turn_in_exercise_uid="ex.root",
        turn_in_exercise_title="The Gentle Return",
        turn_in_revision=3,
        created_at=now,
        updated_at=now,
    )


def test_history_row_prints_the_students_title_then_the_label():
    html = to_xml(render_submission_history_row(_to_history_dict(_entry())))
    assert "My own words" in html
    assert "for The Gentle Return · v3" in html
    # the filename is no longer the row's headline
    assert html.index("My own words") < html.index("The Gentle Return")


def test_queue_card_subtitle_carries_the_label():
    item = queue_item_from_dict(
        {
            "title": "My own words",
            "student_name": "Ada",
            "status": "submitted",
            "exercise_name": "The Gentle Return",
            "revision": 3,
            "submission_uid": "ue_1",
        }
    )
    html = to_xml(render_queue_item(item))
    assert "My own words" in html
    assert "for The Gentle Return · v3" in html
