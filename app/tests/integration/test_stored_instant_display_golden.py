"""Every surface that shows a stored instant renders as its golden file (testcontainer Neo4j).

Each display of a stored instant goes through the helpers in
``core/utils/timestamp_helpers.py`` (``shown_in``, ``age_of``, ``parse_stamp``),
which read ``STORED_INSTANT_CLOCK``. The golden files hold what the pages show
while that constant is the host's zone; a change that alters what a user sees
fails here.

One classroom — a teacher who owns a group, a student in it — is seeded through
the real writers, each under a frozen clock (``time_machine``, given a timestamp
so the process zone stays America/Vancouver, the laptop's): a turn-in, a group
share, the teacher's feedback, a personal share, a notification and an activity
report written for the student. Then the clock moves to the render moment and
the GradeBook, the recipient's card, the exchange thread, the Shared page, the
notifications and the activity report are rendered from the same service reads
their routes make. The writers' random uids are replaced by names before the
comparison.

Regenerate the golden files with ``SKUEL_UPDATE_GOLDEN=1`` — only for a change
that means to alter what is shown, whose diff of these files is then the record
of what it changes. The shares read "14h ago" here, seven hours more than their
age, because their stored digits are the host's wall clock.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import time_machine
from fasthtml.common import Div, to_xml

from adapters.persistence.neo4j.backends.collab_backends import NotificationBackend
from adapters.persistence.neo4j.backends.exercise_backends import EntryReportBackend
from adapters.persistence.neo4j.backends.misc_backends import ActivityReportBackend
from adapters.persistence.neo4j.backends.sharing_backend import SharingBackend
from adapters.persistence.neo4j.backends.user_entry_backend import UserEntryBackend
from adapters.persistence.neo4j.neo4j_query_executor import Neo4jQueryExecutor
from core.models.entity import Entity
from core.models.enums.entity_enums import EntityType
from core.models.enums.neo_labels import NeoLabel
from core.models.enums.notification_enums import NotificationType
from core.models.enums.pipeline import Pipeline
from core.models.report.activity_report import ActivityReport
from core.models.report.entry_report import EntryReport
from core.models.type_hints import UserUID
from core.models.user_entry.user_entry_request import UserEntryCreateRequest
from core.orchestrator.user_entry_orchestrator import UserEntryOrchestrator
from core.services.notifications.notification_service import NotificationService
from core.services.report.activity_report_service import ActivityReportService
from core.services.report.report_relationship_service import ReportRelationshipService
from core.services.report.teacher_review_service import TeacherReviewService
from core.services.sharing.unified_sharing_service import UnifiedSharingService
from core.services.user_entry.user_entry_service import UserEntryService
from ui.gradebook.recipient_card import RecipientEntryCard
from ui.gradebook.summary import (
    render_activity_reports_group,
    render_exchange_section,
    render_other_feedback_group,
)
from ui.learning_loop.exchange_thread import render_exchange_thread
from ui.learning_loop.report import render_activity_report_detail, render_activity_report_list
from ui.notifications.cards import render_notification_card
from ui.profile.shared_view import SharedPage

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.integration,
    pytest.mark.usefixtures("laptop_zone"),
]

GOLDEN_DIR = Path(__file__).parent / "golden" / "stored_instant_display"
UPDATE = os.environ.get("SKUEL_UPDATE_GOLDEN") == "1"

TEACHER = "user_golden_teacher"
STUDENT = "user_golden_student"
GROUP = "group.golden_class"
EXERCISE = "exercise.golden_essay"


def _at(stamp: str) -> float:
    """A moment given as a UTC ISO string, as the timestamp time_machine travels to."""
    return datetime.fromisoformat(stamp).replace(tzinfo=UTC).timestamp()


# The laptop's clock is America/Vancouver (PDT, UTC-7) throughout.
TURN_IN = _at("2026-09-21T01:30:00")  # 18:30 on the 20th in Vancouver — the 21st in UTC
GROUP_SHARE = _at("2026-09-21T01:45:00")  # 18:45 on the 20th
FEEDBACK = _at("2026-09-21T16:15:00")  # 09:15 on the 21st
PERSONAL_SHARE = _at("2026-09-28T00:40:00")  # 17:40 on the 27th
NOTIFIED = _at("2026-09-28T00:41:00")  # 17:41 on the 27th
ACTIVITY_REPORT = _at("2026-09-28T03:10:00")  # 20:10 on the 27th — "2026-09" still open
RENDER = _at("2026-09-28T08:05:00")  # 01:05 on the 28th


async def _seed_classroom(driver: Any) -> None:
    """The structure the writers need: two users, the teacher's group, the student in it,
    and the exercise assigned to the group. No stamp seeded here is displayed."""
    async with driver.session() as session:
        await session.run(
            """
            MERGE (t:User {uid: $teacher}) SET t.display_name = 'Ms Rivera'
            MERGE (s:User {uid: $student}) SET s.display_name = 'Sam Student'
            MERGE (g:Group {uid: $group}) SET g.name = 'Essay class', g.is_active = true
            MERGE (t)-[:OWNS]->(g)
            MERGE (s)-[:MEMBER_OF]->(g)
            MERGE (ex:Entity:Exercise {uid: $exercise})
            SET ex.title = 'A personal essay', ex.entity_type = 'exercise',
                ex.status = 'active', ex.visibility = 'private', ex.scope = 'assigned'
            MERGE (ex)-[:SHARED_WITH_GROUP]->(g)
            """,
            teacher=TEACHER,
            student=STUDENT,
            group=GROUP,
            exercise=EXERCISE,
        )


def _render(node: Any, names: dict[str, str]) -> str:
    html = to_xml(node)
    for uid, name in names.items():
        html = html.replace(uid, name)
    return html


async def test_every_stored_instant_renders_as_it_did(clean_neo4j, neo4j_driver) -> None:
    user_entry_backend = UserEntryBackend(neo4j_driver)
    sharing = UnifiedSharingService(backend=SharingBackend(neo4j_driver, NeoLabel.ENTITY, Entity))
    entries = UserEntryService(backend=user_entry_backend, sharing_service=sharing)  # type: ignore[arg-type]
    report_backend = EntryReportBackend(
        driver=neo4j_driver,
        label=NeoLabel.ENTRY_REPORT,
        entity_class=EntryReport,
        base_label=NeoLabel.ENTITY,
    )
    review = TeacherReviewService(
        user_entry_backend=user_entry_backend,
        report_backend=report_backend,
        exercise_backend=None,  # type: ignore[arg-type]
        group_backend=None,  # type: ignore[arg-type]
        ku_interaction_service=None,  # type: ignore[arg-type]
        report_mastery_service=None,  # type: ignore[arg-type]
        event_bus=None,  # type: ignore[arg-type]
    )
    notifications = NotificationService(
        backend=NotificationBackend(executor=Neo4jQueryExecutor(neo4j_driver))
    )
    activity_reports = ActivityReportService(
        backend=ActivityReportBackend(
            neo4j_driver, NeoLabel.ACTIVITY_REPORT, ActivityReport, base_label=NeoLabel.ENTITY
        ),
        context_builder=None,  # type: ignore[arg-type]
        event_bus=None,
        sharing_service=sharing,
    )
    orchestrator = UserEntryOrchestrator(
        user_entry_service=entries,
        exercises_service=None,  # type: ignore[arg-type]
        teacher_review_service=review,
        user_service=None,  # type: ignore[arg-type]
        activity_report_service=activity_reports,
        revised_exercise_service=None,  # type: ignore[arg-type]
        entry_report_service=None,  # type: ignore[arg-type]
        report_relationship_service=ReportRelationshipService(backend=user_entry_backend),
    )
    student_uid = UserUID(STUDENT)
    teacher_uid = UserUID(TEACHER)

    await _seed_classroom(neo4j_driver)

    with time_machine.travel(TURN_IN, tick=False):
        created = await entries.create_entry(
            UserEntryCreateRequest(
                title="Where I grew up",
                content="A river town, and the bridge we crossed every day.",
                pipeline=Pipeline.TEACHER_REVIEW,
                fulfills_exercise_uid=EXERCISE,
            ),
            student_uid,
        )
    assert created.is_ok, created.expect_error()
    entry_uid = created.value[0].uid

    with time_machine.travel(GROUP_SHARE, tick=False):
        shared = await sharing.share_with_group(entry_uid, STUDENT, GROUP)
    assert shared.is_ok, shared.expect_error()

    with time_machine.travel(FEEDBACK, tick=False):
        feedback = await review.submit_report(
            entry_uid, TEACHER, "Vivid. Say more about the bridge."
        )
    assert feedback.is_ok, feedback.expect_error()
    report_uid = feedback.value["report_uid"]

    with time_machine.travel(PERSONAL_SHARE, tick=False):
        personal = await sharing.share(entry_uid, STUDENT, TEACHER)
    assert personal.is_ok, personal.expect_error()

    with time_machine.travel(NOTIFIED, tick=False):
        notified = await notifications.create_notification(
            user_uid=teacher_uid,
            notification_type=NotificationType.SHARED_WITH_YOU,
            title="Sam Student shared an entry with you",
            message="Where I grew up",
            source_uid=entry_uid,
            source_type=EntityType.USER_ENTRY,
        )
    assert notified.is_ok, notified.expect_error()
    notification_uid = notified.value

    with time_machine.travel(ACTIVITY_REPORT, tick=False):
        written = await activity_reports.submit_report(
            admin_uid=TEACHER,
            subject_uid=STUDENT,
            feedback_text="A steady month: four entries, one revision.",
            time_period="2026-09",
        )
    assert written.is_ok, written.expect_error()
    activity_report_uid = written.value.uid

    names = {
        entry_uid: "{entry}",
        report_uid: "{feedback}",
        notification_uid: "{notification}",
        activity_report_uid: "{activity_report}",
    }

    with time_machine.travel(RENDER, tick=False):
        summaries = (await orchestrator.get_student_exchange_summaries(student_uid)).value
        history = (await orchestrator.get_activity_report_history(student_uid, limit=50)).value
        viewed = await orchestrator.get_entry_for_viewer(entry_uid, teacher_uid)
        assert viewed.is_ok, viewed.expect_error()
        thread = await orchestrator.get_exchange_thread(teacher_uid, EXERCISE, STUDENT)
        assert thread.is_ok, thread.expect_error()
        shared_with_teacher = (await sharing.get_shared_with_me(user_uid=TEACHER, limit=50)).value
        shared_by_student = (await sharing.get_shared_by_me(user_uid=STUDENT, limit=100)).value
        teacher_notifications = (
            await notifications.get_notifications(user_uid=teacher_uid, limit=50)
        ).value
        report = (await orchestrator.get_activity_report(activity_report_uid, student_uid)).value

        rendered = {
            "gradebook": _render(
                Div(
                    render_exchange_section(summaries["exercises"], "all", "all"),
                    render_activity_reports_group(render_activity_report_list(history)),
                    render_other_feedback_group(summaries["other_feedback"]),
                ),
                names,
            ),
            "recipient_card": _render(RecipientEntryCard(viewed.value, "Sam Student"), names),
            "exchange_thread": _render(render_exchange_thread(thread.value, TEACHER), names),
            "shared": _render(SharedPage(shared_with_teacher, shared_by_student), names),
            "notifications": _render(
                Div(*[render_notification_card(n) for n in teacher_notifications]), names
            ),
            "activity_report": _render(render_activity_report_detail(report), names),
        }

    mismatched = []
    for surface, html in rendered.items():
        golden = GOLDEN_DIR / f"{surface}.html"
        if UPDATE:
            golden.parent.mkdir(parents=True, exist_ok=True)
            golden.write_text(html)
        elif golden.read_text() != html:
            mismatched.append(surface)
    assert not mismatched, (
        f"rendered differently from the golden files: {mismatched} "
        f"(compare with {GOLDEN_DIR}; SKUEL_UPDATE_GOLDEN=1 regenerates them)"
    )
