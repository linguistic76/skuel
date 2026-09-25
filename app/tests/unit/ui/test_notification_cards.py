"""Notification cards link to the page their source entity lives on.

The href is resolved from ``source_type`` + ``source_uid`` through
``entity_detail_href`` — a feedback bell opens its EntryReport, a revision
bell its RevisedExercise, an activity-report bell the report — with one
override: a submission for review opens the teacher's review page.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from fastcore.xml import to_xml  # type: ignore[import-untyped]

from core.models.enums import NotificationType
from core.models.enums.entity_enums import EntityType
from core.models.notification import Notification
from core.models.type_hints import UserUID
from ui.notifications import notification_href, render_notification_card


def _notif(
    kind: NotificationType | None,
    source_type: EntityType,
    source_uid: str = "src_1",
) -> Notification:
    return Notification(
        uid="notif_1",
        user_uid=UserUID("user_student"),
        notification_type=kind,
        title="Title",
        message="Message",
        source_uid=source_uid,
        source_type=source_type,
        created_at=datetime(2026, 9, 24, 10, 0),
    )


@pytest.mark.parametrize(
    ("kind", "source_type", "expected"),
    [
        (
            NotificationType.FEEDBACK_RECEIVED,
            EntityType.ENTRY_REPORT,
            "/entry-reports/detail?uid=src_1",
        ),
        (
            NotificationType.REVISION_REQUESTED,
            EntityType.ENTRY_REPORT,
            "/entry-reports/detail?uid=src_1",
        ),
        (NotificationType.SUBMISSION_APPROVED, EntityType.USER_ENTRY, "/gradebook/src_1"),
        (
            NotificationType.REVISED_EXERCISE_CREATED,
            EntityType.REVISED_EXERCISE,
            "/revised-exercises/detail?uid=src_1",
        ),
        (
            NotificationType.ACTIVITY_REPORT_RECEIVED,
            EntityType.ACTIVITY_REPORT,
            "/activity-reports/detail?uid=src_1",
        ),
        (NotificationType.SHARED_WITH_YOU, EntityType.USER_ENTRY, "/gradebook/src_1"),
        # The override: the teacher's review page, not the entry's own detail.
        (NotificationType.SUBMISSION_FOR_REVIEW, EntityType.USER_ENTRY, "/teaching/review/src_1"),
        # An unknown kind still opens its source.
        (None, EntityType.USER_ENTRY, "/gradebook/src_1"),
    ],
)
def test_href_follows_the_source(
    kind: NotificationType | None, source_type: EntityType, expected: str
) -> None:
    notif = _notif(kind, source_type)
    assert notification_href(notif) == expected
    assert f'href="{expected}"' in to_xml(render_notification_card(notif))


def test_a_source_with_no_detail_page_renders_no_view_link() -> None:
    notif = _notif(NotificationType.SHARED_WITH_YOU, EntityType.INTERACTION)
    assert notification_href(notif) is None
    assert "View →" not in to_xml(render_notification_card(notif))


def test_an_unknown_kind_renders_a_generic_bell() -> None:
    html = to_xml(render_notification_card(_notif(None, EntityType.USER_ENTRY)))
    assert "🔔" in html
    assert "Notification" in html


def test_a_known_kind_renders_its_traits() -> None:
    kind = NotificationType.ACTIVITY_REPORT_RECEIVED
    html = to_xml(render_notification_card(_notif(kind, EntityType.ACTIVITY_REPORT)))
    assert kind.get_icon() in html
    assert kind.get_label() in html
