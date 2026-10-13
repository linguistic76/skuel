"""The exercise-teacher admission: who may be named an exercise's teacher (ADR-091 S3).

A teacher is one user uid naming a user with the TEACHER role or higher. Anything else —
no user, a lower role, no role, a value that is not one uid — is refused with a reason
the sync shows beside the file's name. The roles are read once for the whole batch; a
failed read admits nothing.
"""

from __future__ import annotations

import pytest

from core.services.ingestion.exercise_teacher import refuse_unqualified_teachers
from core.utils.result_simplified import Errors, Result


class _Roles:
    """The one read the admission makes, with its real signature, recording each call."""

    def __init__(self, roles: dict[str, str], *, fail: bool = False) -> None:
        self._roles = roles
        self._fail = fail
        self.calls: list[list[str]] = []

    async def get_user_roles_batch(self, uids: list[str]) -> Result[dict[str, str]]:
        self.calls.append(list(uids))
        if self._fail:
            return Result.fail(Errors.database("get_user_roles_batch", "down"))
        return Result.ok({uid: role for uid, role in self._roles.items() if uid in uids})


_ROLES = {
    "user_teacher": "teacher",
    "user_admin": "admin",
    "user_member": "member",
    "user_roleless": "",
}


@pytest.mark.asyncio
@pytest.mark.parametrize("teacher", ["user_teacher", "user_admin"])
async def test_a_teacher_or_higher_is_admitted(teacher: str) -> None:
    reader = _Roles(_ROLES)
    result = await refuse_unqualified_teachers(reader, [{"uid": "ex.a", "teacher": teacher}])
    assert result.is_ok
    assert result.value == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("teacher", "says"),
    [
        ("user_nobody", "names no user"),
        ("user_member", "has the 'member' role"),
        ("user_roleless", "has the 'no' role"),
        (["user_teacher", "user_admin"], "must be one user uid"),
        (7, "must be one user uid"),
    ],
)
async def test_anything_else_is_refused_with_its_reason(teacher: object, says: str) -> None:
    exercise = {"uid": "ex.a", "teacher": teacher}
    reader = _Roles(_ROLES)
    result = await refuse_unqualified_teachers(reader, [exercise])
    assert result.is_ok
    [(refused, reason)] = result.value
    assert refused is exercise
    assert says in reason


@pytest.mark.asyncio
async def test_the_roles_are_read_once_for_the_batch() -> None:
    reader = _Roles(_ROLES)
    exercises = [
        {"uid": "ex.a", "teacher": "user_teacher"},
        {"uid": "ex.b", "teacher": "user_teacher"},
        {"uid": "ex.c", "teacher": "user_member"},
    ]
    result = await refuse_unqualified_teachers(reader, exercises)
    assert reader.calls == [["user_member", "user_teacher"]]
    assert [refused["uid"] for refused, _ in result.value] == ["ex.c"]


@pytest.mark.asyncio
async def test_a_failed_read_admits_nothing() -> None:
    reader = _Roles(_ROLES, fail=True)
    result = await refuse_unqualified_teachers(reader, [{"uid": "ex.a", "teacher": "user_teacher"}])
    assert result.is_error
