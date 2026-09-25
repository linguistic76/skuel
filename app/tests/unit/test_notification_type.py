"""``NotificationType`` — the bell vocabulary and its presentation traits.

Every member carries an icon, a badge variant that is a real ``BadgeT`` value,
and a label; a stored value this build does not know resolves to ``None`` so
the card falls back to a generic bell instead of dropping the row.
"""

from __future__ import annotations

import pytest

from core.models.enums import NotificationType
from ui.feedback import BadgeT

EXPECTED_VALUES = {
    "feedback_received",
    "submission_approved",
    "revision_requested",
    "revised_exercise_created",
    "activity_report_received",
    "submission_for_review",
    "shared_with_you",
}


def test_members_are_the_seven_kinds() -> None:
    assert {m.value for m in NotificationType} == EXPECTED_VALUES


@pytest.mark.parametrize("member", list(NotificationType))
def test_every_member_presents(member: NotificationType) -> None:
    assert member.get_icon()
    assert member.get_label()
    # The variant string must name a badge the UI can render.
    assert BadgeT(member.get_badge_variant())


def test_from_string_resolves_a_known_value() -> None:
    assert NotificationType.from_string("feedback_received") is NotificationType.FEEDBACK_RECEIVED


def test_from_string_is_none_for_an_unknown_value() -> None:
    assert NotificationType.from_string("kind_from_a_later_build") is None
