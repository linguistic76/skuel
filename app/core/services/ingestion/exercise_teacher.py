"""
Exercise Teacher Admission
==========================

Every exercise names its teacher in its vault file (ADR-091 S3): the ``teacher``
field holds one user uid, which ingestion writes as
``(Exercise)-[:REVIEWED_BY]->(User)`` — never ``OWNS``; the exercise stays
ownerless. A feedback request on the exercise goes to that teacher.

The field is required (``ENTITY_CONFIGS``); this module decides whether the uid
it holds may be a teacher: an existing user with the TEACHER role or higher.
Both ingest doors ask before any node is written, so a refused file writes
nothing and the sync names it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.models.enums.user_enums import UserRole
from core.utils.result_simplified import Result

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from core.ports.ingestion_protocols import IngestionWriteOperations

#: The frontmatter field naming an exercise's teacher (the registry's ``yaml_field_path``).
TEACHER_FIELD = "teacher"


def _role_reason(teacher_uid: str, role: str | None) -> str | None:
    """Why ``teacher_uid`` cannot be an exercise's teacher, or ``None`` when it can."""
    if role is None:
        return (
            f"teacher '{teacher_uid}' names no user — an exercise's teacher is a user "
            "with the teacher role or higher"
        )
    held = next((r for r in UserRole if r.value == role), None)
    if held is None or not held.has_permission(UserRole.TEACHER):
        return (
            f"teacher '{teacher_uid}' has the '{role or 'no'}' role — an exercise's "
            "teacher is a user with the teacher role or higher"
        )
    return None


async def refuse_unqualified_teachers(
    reader: IngestionWriteOperations,
    exercises: Sequence[Mapping[str, object]],
) -> Result[list[tuple[Mapping[str, object], str]]]:
    """Each prepared exercise whose ``teacher`` may not be its teacher, with the reason.

    A teacher is one user uid naming a user with the TEACHER role or higher. A
    value that is not one uid (a list, a number) is refused as well: the edge
    template would write one edge per element. The roles of every named user are
    read in one statement; a failed read fails the whole check, so no exercise is
    admitted on a read that did not happen.
    """
    named = sorted(
        {value for exercise in exercises if isinstance(value := exercise.get(TEACHER_FIELD), str)}
    )
    roles: dict[str, str] = {}
    if named:
        read = await reader.get_user_roles_batch(named)
        if read.is_error:
            return Result.fail(read)
        roles = read.value

    refused: list[tuple[Mapping[str, object], str]] = []
    for exercise in exercises:
        value = exercise.get(TEACHER_FIELD)
        if not isinstance(value, str):
            refused.append((exercise, f"teacher must be one user uid, got {value!r}"))
            continue
        reason = _role_reason(value, roles.get(value))
        if reason is not None:
            refused.append((exercise, reason))
    return Result.ok(refused)


__all__ = ["TEACHER_FIELD", "refuse_unqualified_teachers"]
