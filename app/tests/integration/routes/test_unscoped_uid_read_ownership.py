"""Ownership coverage for the two confirmed cross-tenant reads found by the
bare-``require_authenticated_user`` sweep.

Both handlers authenticated the request and **discarded** the user, then read an
entity by UID with no scoping:

- ``GET /api/groups/{uid}/members`` (``groups_api.py::list_members``) — any
  authenticated user could enumerate any group's membership roster (user UID,
  name, role, join timestamp), while the handler's own docstring promised
  "Accessible to owner and members".
- ``GET /teaching/forms/submission?uid=`` (``teaching_forms_ui.py::
  teaching_forms_submission_detail``) — the TEACHER *role* was checked but not
  *authority over that particular student*, so any teacher could read any
  student's form submission, including students in another teacher's classroom.

These tests pin the closed form. Both services are real (``GroupService``,
``TeacherReviewService``'s authority predicate) with only the Neo4j backend
mocked, so they exercise route → service → gate end to end: a handler that
forgets the gate reaches the backend and returns the victim's data, failing the
``_foreign`` cases.

The asserted property for a refusal is **indistinguishability** — a foreign
entity and a nonexistent one must produce the same response, so a UID cannot be
probed for existence (per docs/patterns/OWNERSHIP_VERIFICATION.md, 404 never
403). Preservation cases (owner, member, admin) assert the fixes did not simply
close the pages.

Companion to ``test_lateral_route_ownership.py`` (the same defect class in
``LateralRouteFactory``) and ``test_teacher_review_idor_isolation.py`` (the
backend-level half of the teacher-authority gate).
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fasthtml.common import to_xml
from starlette.responses import Response

import adapters.inbound.teaching_forms_ui as tfu
from adapters.inbound.groups_api import create_groups_api_routes
from core.models.enums.user_enums import UserRole
from core.models.forms.form_submission import FormSubmission
from core.models.group.group import Group
from core.services.groups.group_service import GroupService
from core.utils.result_simplified import Errors, Result

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

# --- groups ---------------------------------------------------------------
OWNER = "user_group_owner"
MEMBER = "user_group_member"
INTRUDER = "user_group_intruder"
GROUP_UID = "group_physics_101"

# --- forms ----------------------------------------------------------------
TEACHER_A = "user_teacher_a"
TEACHER_B = "user_teacher_b"
ADMIN = "user_admin"
STUDENT_1 = "user_student_1"
SUBMISSION_UID = "fs_student1_survey"
# The payload that must never reach a teacher outside Student 1's classroom.
SECRET_ANSWER = "my-private-reflection-text"


def _make_request(user_uid: str | None = OWNER, path: str = "/api/groups/x/members") -> Any:
    """Minimal session-backed request stub for ``require_authenticated_user``."""
    return SimpleNamespace(
        method="GET",
        session={"user_uid": user_uid} if user_uid is not None else {},
        url=SimpleNamespace(path=path),
        query_params={},
        cookies={},
    )


# ============================================================================
# GET /api/groups/{uid}/members — owner OR member only
# ============================================================================

# Roster rows shaped as the real Cypher returns them, so a missing gate shows up
# as a 200 carrying real member identities rather than an incidental empty list.
_MEMBER_ROWS = [
    {"user_uid": MEMBER, "user_name": "A Student", "role": "student", "joined_at": "2026-01-01"},
    {"user_uid": OWNER, "user_name": "A Teacher", "role": "teacher", "joined_at": "2026-01-01"},
]


@pytest.fixture
def group_backend() -> Any:
    """Backend where GROUP_UID exists, is owned by OWNER, and has MEMBER in it."""
    backend = MagicMock()

    async def get(uid: str) -> Result[Group | None]:
        if uid == GROUP_UID:
            return Result.ok(Group(uid=uid, name="Physics 101", owner_uid=OWNER))
        return Result.ok(None)

    backend.get = AsyncMock(side_effect=get)
    backend.get_members = AsyncMock(return_value=Result.ok(_MEMBER_ROWS))
    return backend


@pytest.fixture
def group_handlers(group_backend: Any) -> dict[str, Any]:
    """Register the real groups API routes against the real GroupService."""
    registered: dict[str, Any] = {}

    def rt_collector(path: str, *_a: Any, **_kw: Any) -> Any:
        def decorator(fn: Any) -> Any:
            registered[path] = fn
            return fn

        return decorator

    service = GroupService(backend=group_backend)
    create_groups_api_routes(MagicMock(), rt_collector, service, MagicMock())
    return registered


def _members_route(handlers: dict[str, Any]) -> Any:
    return handlers["/api/groups/{uid}/members"]


def _body(response: Any) -> Any:
    """Decode a ``boundary_handler`` JSONResponse body."""
    return json.loads(bytes(response.body).decode())


class TestGroupRosterIsScoped:
    """The membership roster is classroom data, not public directory data."""

    async def test_owner_sees_roster(self, group_handlers: dict[str, Any]) -> None:
        response = await _members_route(group_handlers)(request=_make_request(OWNER), uid=GROUP_UID)

        assert response.status_code == 200
        assert {row["user_uid"] for row in _body(response)} == {MEMBER, OWNER}

    async def test_member_sees_roster(self, group_handlers: dict[str, Any]) -> None:
        """The docstring promises owner AND members — not owner only."""
        response = await _members_route(group_handlers)(
            request=_make_request(MEMBER), uid=GROUP_UID
        )

        assert response.status_code == 200
        assert {row["user_uid"] for row in _body(response)} == {MEMBER, OWNER}

    async def test_non_member_cannot_enumerate_roster(self, group_handlers: dict[str, Any]) -> None:
        """The pre-fix failure mode: a 200 carrying every member's identity."""
        response = await _members_route(group_handlers)(
            request=_make_request(INTRUDER), uid=GROUP_UID
        )

        assert response.status_code == 404
        # No member identity may survive in the error payload.
        body = json.dumps(_body(response)).lower()
        assert MEMBER.lower() not in body
        assert "a student" not in body

    async def test_foreign_and_missing_are_indistinguishable(
        self, group_handlers: dict[str, Any], group_backend: Any
    ) -> None:
        """A real-but-forbidden group must look exactly like a nonexistent one.

        Otherwise the endpoint is a group-existence oracle: an attacker walks
        UIDs and reads which ones come back "forbidden" instead of "missing".

        The comparison holds the **UID fixed** and changes the world — asking
        for two different UIDs would differ merely because the caller-supplied
        UID is echoed back, which proves nothing.
        """
        foreign = await _members_route(group_handlers)(
            request=_make_request(INTRUDER), uid=GROUP_UID
        )

        # Same UID, but now the group does not exist for anyone.
        group_backend.get = AsyncMock(return_value=Result.ok(None))
        missing = await _members_route(group_handlers)(
            request=_make_request(INTRUDER), uid=GROUP_UID
        )

        assert foreign.status_code == missing.status_code == 404

        foreign_body = _body(foreign)
        missing_body = _body(missing)
        # ``timestamp`` is wall-clock, carries nothing about the group, and is
        # the only field allowed to differ. Pinning the key set here is
        # deliberate: the two refusals are raised from *different lines* of
        # GroupService, so a future payload carrying source_location (or any
        # other provenance field) would leak which branch fired.
        assert set(foreign_body) == {"category", "code", "message", "severity", "timestamp"}
        foreign_body.pop("timestamp")
        missing_body.pop("timestamp")
        assert foreign_body == missing_body
        # 404, never 403 — nothing may hint the group is real but withheld.
        assert "forbidden" not in json.dumps(foreign_body).lower()
        # The UID must not survive into the code — that was the sentence-as-
        # resource bug this fix also cleared (code was NOT_FOUND_GROUP <UID>...).
        assert foreign_body["code"] == "NOT_FOUND_GROUP"

    async def test_backend_failure_is_not_reported_as_not_found(
        self, group_handlers: dict[str, Any], group_backend: Any
    ) -> None:
        """Routing the roster through the access gate must not convert a Neo4j
        outage into a confident 404 — before this route used the gate,
        ``get_members`` surfaced the real database error. Only a successful
        no-access answer is not-found."""
        group_backend.get = AsyncMock(
            return_value=Result.fail(
                Errors.database(operation="get_group", message="Neo4j unavailable")
            )
        )

        response = await _members_route(group_handlers)(request=_make_request(OWNER), uid=GROUP_UID)

        assert response.status_code != 404
        assert _body(response)["category"] == "database"

    async def test_unauthenticated_is_refused(self, group_handlers: dict[str, Any]) -> None:
        from starlette.exceptions import HTTPException

        with pytest.raises(HTTPException) as exc:
            await _members_route(group_handlers)(request=_make_request(None), uid=GROUP_UID)
        assert exc.value.status_code == 401


# ============================================================================
# GET /teaching/forms/submission?uid= — TEACHER role AND authority over student
# ============================================================================


def _fake_user(uid: str, role: UserRole) -> Any:
    """Stand-in for the ``User`` entity ``@require_role`` injects."""
    return SimpleNamespace(
        uid=uid,
        role=role,
        has_permission=lambda required: role.has_permission(required),
    )


@pytest.fixture
def forms_handlers(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Register the real teaching-forms routes with a real authority predicate.

    ``require_role`` is applied at route-creation time, so it is patched to an
    identity decorator and ``current_user`` is injected by the caller instead —
    the same technique as ``tests/unit/test_teaching_forms_ui.py``. This keeps
    the *role* gate out of the way so the tests below can prove the *authority*
    gate independently: the two are different checks and only one existed.
    """

    def _identity_decorator(fn: Any) -> Any:
        return fn

    def _fake_require_role(*_a: Any, **_kw: Any) -> Any:
        return _identity_decorator

    def _fake_render(content: Any, active: str, request: Any) -> Any:
        return content

    monkeypatch.setattr(tfu, "require_role", _fake_require_role)
    monkeypatch.setattr(tfu, "render_teaching_sidebar_page", _fake_render)

    submission = FormSubmission(
        uid=SUBMISSION_UID,
        user_uid=STUDENT_1,
        title="Student 1 reflection",
        form_template_uid="ft_survey",
        form_data={"reflection": SECRET_ANSWER},
    )

    submission_service = MagicMock()

    async def get_submission_admin(uid: str) -> Result[FormSubmission]:
        if uid == SUBMISSION_UID:
            return Result.ok(submission)
        return Result.fail(Errors.not_found(resource="FormSubmission", identifier=uid))

    submission_service.get_submission_admin = AsyncMock(side_effect=get_submission_admin)

    template_service = MagicMock()
    template_service.get = AsyncMock(return_value=Result.ok(None))

    # Real authority semantics: Teacher A shares an active group with Student 1,
    # Teacher B does not. Mirrors the Cypher in _user_entry_assessment_mixin.
    async def verify_teacher_authority(teacher_uid: str, student_uid: str) -> Result[bool]:
        if teacher_uid == TEACHER_A and student_uid == STUDENT_1:
            return Result.ok(True)
        return Result.fail(
            Errors.forbidden(
                action="verify_teacher_authority",
                reason=f"Teacher {teacher_uid} has no authority over {student_uid}",
            )
        )

    review_service = MagicMock()
    review_service.verify_teacher_authority = AsyncMock(side_effect=verify_teacher_authority)

    registered: dict[str, Any] = {}

    def rt_collector(path: str, *_a: Any, **_kw: Any) -> Any:
        def decorator(fn: Any) -> Any:
            registered[path] = fn
            return fn

        return decorator

    tfu.create_teaching_forms_ui_routes(
        MagicMock(),
        rt_collector,
        template_service,
        submission_service,
        MagicMock(),
        review_service,
    )
    registered["_review_service"] = review_service
    return registered


def _submission_route(handlers: dict[str, Any]) -> Any:
    return handlers["/teaching/forms/submission"]


def _page(result: Any) -> tuple[int, str]:
    """Normalise a handler return into ``(status_code, html)``.

    The success path returns a bare FT node, which FastHTML serves as 200;
    refusals return an explicit ``Response`` carrying a status. Asserting on
    markup alone cannot tell those apart — a denied read that rendered
    "Submission not found" inside an HTTP 200 would pass a text-only check
    while telling every client and intermediary the request succeeded.
    """
    if isinstance(result, Response):
        return result.status_code, bytes(result.body).decode()
    return 200, to_xml(result)


class TestFormSubmissionDetailRequiresAuthority:
    """The TEACHER role is not authority over a particular student."""

    async def test_teacher_in_classroom_sees_submission(
        self, forms_handlers: dict[str, Any]
    ) -> None:
        status, rendered = _page(
            await _submission_route(forms_handlers)(
                request=_make_request(TEACHER_A, path="/teaching/forms/submission"),
                uid=SUBMISSION_UID,
                current_user=_fake_user(TEACHER_A, UserRole.TEACHER),
            )
        )

        assert status == 200
        assert SECRET_ANSWER in rendered

    async def test_teacher_outside_classroom_gets_not_found(
        self, forms_handlers: dict[str, Any]
    ) -> None:
        """The pre-fix failure mode: Teacher B reading Student 1's answers."""
        status, rendered = _page(
            await _submission_route(forms_handlers)(
                request=_make_request(TEACHER_B, path="/teaching/forms/submission"),
                uid=SUBMISSION_UID,
                current_user=_fake_user(TEACHER_B, UserRole.TEACHER),
            )
        )

        # A real 404, not a 200 that merely says "not found" in its body.
        assert status == 404
        assert SECRET_ANSWER not in rendered
        assert STUDENT_1 not in rendered
        assert "not found" in rendered.lower()

    async def test_foreign_and_missing_are_indistinguishable(
        self, forms_handlers: dict[str, Any]
    ) -> None:
        """Same response for "another classroom's" and "does not exist".

        Asserted as response equality rather than absence-of-a-word: the page
        must not become a submission-existence oracle for a curious teacher.
        """
        foreign_status, foreign = _page(
            await _submission_route(forms_handlers)(
                request=_make_request(TEACHER_B, path="/teaching/forms/submission"),
                uid=SUBMISSION_UID,
                current_user=_fake_user(TEACHER_B, UserRole.TEACHER),
            )
        )
        missing_status, missing = _page(
            await _submission_route(forms_handlers)(
                request=_make_request(TEACHER_B, path="/teaching/forms/submission"),
                uid="fs_does_not_exist",
                current_user=_fake_user(TEACHER_B, UserRole.TEACHER),
            )
        )

        assert foreign_status == missing_status == 404
        # The UID is echoed in the banner, so compare with it neutralised.
        assert foreign.replace(SUBMISSION_UID, "UID") == missing.replace("fs_does_not_exist", "UID")

    async def test_backend_failure_is_not_reported_as_not_found(
        self, forms_handlers: dict[str, Any]
    ) -> None:
        """An infrastructure fault is not an access decision.

        If the authority query itself fails (Neo4j down), a legitimate teacher
        must not be handed a confident "no such submission" — that hides the
        outage and misinforms the caller. Only a FORBIDDEN verdict is a denial.
        """
        forms_handlers["_review_service"].verify_teacher_authority = AsyncMock(
            return_value=Result.fail(
                Errors.database(operation="verify_teacher_authority", message="Neo4j unavailable")
            )
        )

        status, rendered = _page(
            await _submission_route(forms_handlers)(
                request=_make_request(TEACHER_A, path="/teaching/forms/submission"),
                uid=SUBMISSION_UID,
                current_user=_fake_user(TEACHER_A, UserRole.TEACHER),
            )
        )

        assert status == 503
        assert "not found" not in rendered.lower()
        # Still fails closed — the submission body never renders.
        assert SECRET_ANSWER not in rendered

    async def test_admin_retains_cross_classroom_view(self, forms_handlers: dict[str, Any]) -> None:
        """This page is documented as the Admin/Teacher view — the authority
        gate must not lock admins out of submissions outside their own groups."""
        status, rendered = _page(
            await _submission_route(forms_handlers)(
                request=_make_request(ADMIN, path="/teaching/forms/submission"),
                uid=SUBMISSION_UID,
                current_user=_fake_user(ADMIN, UserRole.ADMIN),
            )
        )

        assert status == 200
        assert SECRET_ANSWER in rendered
        # Admins short-circuit the predicate rather than being granted by it.
        forms_handlers["_review_service"].verify_teacher_authority.assert_not_awaited()

    async def test_authority_checked_against_the_submitting_student(
        self, forms_handlers: dict[str, Any]
    ) -> None:
        """The gate must ask about the submission's owner and the session
        teacher — not a default, and not the UID being requested."""
        await _submission_route(forms_handlers)(
            request=_make_request(TEACHER_A, path="/teaching/forms/submission"),
            uid=SUBMISSION_UID,
            current_user=_fake_user(TEACHER_A, UserRole.TEACHER),
        )

        forms_handlers["_review_service"].verify_teacher_authority.assert_awaited_once_with(
            TEACHER_A, STUDENT_1
        )
