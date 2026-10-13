"""
PathStep Enrollment Handler
============================

Listens for PathStepEnrolled events and auto-enrols the student in the admin's
default group, so every learner on a PathStep has a group and a teacher before
anyone adds them to a class. Membership lets the learner ask that teacher for
feedback on work that answers no exercise (a ``teachers`` request without an
exercise goes to the learner's groups) and share work with the group. A
feedback request on an exercise goes to the teacher its vault file names, not
here (ADR-091 S3).

See: /docs/decisions/ADR-091-one-door-for-curriculum.md (N9)
See: /docs/decisions/ADR-053-groups-first-class-and-unified-sharing.md
"""

from datetime import UTC, datetime
from typing import Any

from core.events.curriculum_events import PathStepEnrolled
from core.utils.logging import get_logger

logger = get_logger("skuel.events.path_step_enrollment_handler")


async def handle_path_step_enrolled(
    event: PathStepEnrolled,
    user_entry_backend: Any,
    group_backend: Any,
) -> None:
    """Auto-enrol a student in the admin's default group on PathStep enrolment.

    1. Fetch the oldest admin user (the default group's teacher).
    2. MERGE the admin's default group.
    3. MERGE the student's MEMBER_OF relationship.

    All steps are idempotent — safe to call on repeated enrolments.
    """
    admin_result = await user_entry_backend.get_admin_uid()
    if admin_result.is_error or not admin_result.value:
        logger.warning(
            "PathStepEnrolled: no admin found — skipping default group enrolment",
            user_uid=event.user_uid,
            ps_uid=event.ps_uid,
        )
        return

    admin_uid: str = admin_result.value[0]["admin_uid"]
    now = datetime.now(UTC).isoformat()

    group_result = await group_backend.get_or_create_default_group(admin_uid, now)
    if group_result.is_error or not group_result.value:
        logger.warning(
            "PathStepEnrolled: failed to get/create default group",
            admin_uid=admin_uid,
            error=group_result.error if group_result.is_error else "no result",
        )
        return

    group_uid: str = group_result.value[0]["group_uid"]

    member_result = await group_backend.ensure_group_member(event.user_uid, group_uid, now)
    if member_result.is_error:
        logger.warning(
            "PathStepEnrolled: failed to ensure group membership",
            user_uid=event.user_uid,
            group_uid=group_uid,
            error=member_result.error,
        )
        return

    logger.debug(
        "PathStepEnrolled: student enrolled in default group",
        user_uid=event.user_uid,
        group_uid=group_uid,
    )
