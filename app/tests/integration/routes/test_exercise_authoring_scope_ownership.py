"""Audience scoping for the two teacher-gated exercise authoring routes.

``GET /exercises/{uid}/edit`` and ``GET /exercises/{uid}/view`` were gated by
``@require_teacher`` and then read by UID with no scoping at all — so any
TEACHER could read, and open the editor for, any other user's PERSONAL
exercise. Students hold PERSONAL exercises too, and ADR-042 §3 answers the
policy question directly: user content is readable by the owner, by a
``SHARES_WITH`` recipient, or through a group it was shared with, and
"Teachers, unless the above conditions are met" sits on the NOT-readable side.
Role and ownership are orthogonal; the role gate says who may author, never
whose work.

The audience pinned here is the exercise's **owner**, which is narrower than
the SCOPE_AWARE rule the student fragment uses
(``ExerciseService.get_exercise_for_user``). Two reasons, each with its own
class below:

- These are authoring routes. The edit form's Save posts to
  ``PUT /api/exercises/{uid}``, which is owner-scoped (``EXERCISES_CONFIG.crud``
  declares ``scope=USER_OWNED`` alongside ``require_role=TEACHER``). A read
  audience wider than the write audience renders an editable form whose Save
  can only fail — ``TestReadMatchesWrite`` asserts the two audiences are the
  same set rather than copying a matrix by hand.
- Nothing is lost by the narrowing, because every wider read already has a
  surface: ``/exercises/get`` serves the full SCOPE_AWARE audience.
  ``TestLearnerSurfaceStillServes`` pins that content refused *here* is still
  reachable *there* by a user in its audience. This moved a read between
  surfaces; it did not remove one.

Every actor in this file is a TEACHER, so ``@require_teacher`` passes for all
of them and the audience predicate is the only variable — a refusal below can
never be the role gate wearing a disguise. ``TestRoleGateStillApplies`` covers
the other direction.

Run against a real Neo4j container: the ownership claim resolves against
persisted node properties and the ``:OWNS`` edge, and the ``:OWNS`` half is a
warn-only write that can be missing. A mocked backend would assert only that
the route calls a method.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fasthtml.common import to_xml
from starlette.exceptions import HTTPException

from adapters.inbound.exercises_ui import create_exercises_ui_routes
from adapters.persistence.neo4j.backends.exercise_backends import ExerciseBackend
from core.models.enums import EntityType, ExerciseScope, UserRole
from core.models.enums.neo_labels import NeoLabel
from core.models.exercises.exercise import Exercise
from core.models.update_contracts import RawChanges
from core.models.user.user import User
from core.services.exercises.exercise_service import ExerciseService
from core.utils.result_simplified import Errors, Result

AUTHOR = "user_auth_author"
OTHER_TEACHER = "user_auth_other_teacher"
GROUP_TEACHER = "user_auth_group_teacher"
STUDENT = "user_auth_student"
GROUP_UID = "group_auth_scope"

EDIT_PATH = "/exercises/{uid}/edit"
VIEW_PATH = "/exercises/{uid}/view"
LEARNER_PATH = "/exercises/get/content"
DASHBOARD_PATH = "/exercises/content"

AUTHORING_PATHS = [EDIT_PATH, VIEW_PATH]
AUTHORING_IDS = ["edit-form", "view"]

# Roles are fixed per actor and never vary across a test: three TEACHERs so the
# role gate is a constant, one MEMBER to prove the gate itself still bites.
ROLES = {
    AUTHOR: UserRole.TEACHER,
    OTHER_TEACHER: UserRole.TEACHER,
    GROUP_TEACHER: UserRole.TEACHER,
    STUDENT: UserRole.MEMBER,
}
TEACHERS = [AUTHOR, OTHER_TEACHER, GROUP_TEACHER]

# One distinctive title per fixture, so a leak shows up as the actual secret
# text of a specific exercise appearing in someone else's response.
CURRICULUM = "curriculum"
PERSONAL_AUTHOR = "personal_author"
PERSONAL_STUDENT = "personal_student"
ASSIGNED = "assigned"
ASSESSMENT = "assessment"

TITLES = {
    CURRICULUM: "Photosynthesis shared drill",
    PERSONAL_AUTHOR: "Author private authoring drill",
    PERSONAL_STUDENT: "Student private journal drill",
    ASSIGNED: "Author assigned group drill",
    ASSESSMENT: "Author formal assessment drill",
}

# (key, scope, owner, group)
SPECS = [
    (CURRICULUM, ExerciseScope.CURRICULUM, None, None),
    (PERSONAL_AUTHOR, ExerciseScope.PERSONAL, AUTHOR, None),
    (PERSONAL_STUDENT, ExerciseScope.PERSONAL, STUDENT, None),
    (ASSIGNED, ExerciseScope.ASSIGNED, AUTHOR, GROUP_UID),
    (ASSESSMENT, ExerciseScope.ASSESSMENT, AUTHOR, None),
]


@pytest.fixture
def exercise_service(neo4j_driver) -> ExerciseService:
    backend = ExerciseBackend(
        driver=neo4j_driver,
        label=NeoLabel.EXERCISE,
        entity_class=Exercise,
        base_label=NeoLabel.ENTITY,
    )
    return ExerciseService(backend=backend)


def _user_service() -> Any:
    """A user service over real ``User`` records, so ``@require_teacher`` runs
    its real hierarchy check rather than a stubbed ``True``."""

    async def get_user(user_uid: str) -> Result[User]:
        role = ROLES.get(user_uid)
        if role is None:
            return Result.fail(Errors.not_found(resource="User", identifier=user_uid))
        return Result.ok(User(uid=user_uid, title=user_uid, role=role))

    return SimpleNamespace(get_user=get_user)


def _make_request(user_uid: str | None) -> Any:
    """Minimal session-backed request stub for the auth guards."""
    return SimpleNamespace(
        method="GET",
        session={"user_uid": user_uid} if user_uid is not None else {},
        url=SimpleNamespace(path=EDIT_PATH),
        query_params={},
        cookies={},
    )


def _collector() -> tuple[Any, dict[str, Any]]:
    """A stand-in app/rt pair that records path → handler."""
    registered: dict[str, Any] = {}

    def decorator_for(path: str) -> Any:
        def decorator(fn: Any) -> Any:
            registered[path] = fn
            return fn

        return decorator

    def rt(path: str, *_a: Any, **_kw: Any) -> Any:
        return decorator_for(path)

    app = SimpleNamespace(get=rt, post=rt, route=rt)
    return (app, rt), registered


@pytest.fixture
def handlers(exercise_service: ExerciseService) -> dict[str, Any]:
    """Real routes over the real service — only Neo4j is a container."""
    (app, rt), registered = _collector()
    create_exercises_ui_routes(app, rt, exercise_service, user_service=_user_service())
    return registered


async def _seed_users_and_group(neo4j_driver) -> None:
    async with neo4j_driver.session() as session:
        await session.run(
            "UNWIND $uids AS uid MERGE (u:User {uid: uid})",
            uids=[AUTHOR, OTHER_TEACHER, GROUP_TEACHER, STUDENT],
        )
        await session.run(
            """
            MERGE (g:Group {uid: $group_uid})
            WITH g
            MATCH (member:User {uid: $member})
            MERGE (member)-[:MEMBER_OF]->(g)
            """,
            group_uid=GROUP_UID,
            member=GROUP_TEACHER,
        )


async def _seed_exercises(neo4j_driver, exercise_service: ExerciseService) -> dict[str, str]:
    created: dict[str, str] = {}
    for key, scope, owner, group in SPECS:
        exercise = Exercise(
            uid=f"exercise_authoring_{key}",
            title=TITLES[key],
            entity_type=EntityType.EXERCISE,
            instructions=f"secret instructions for {key}",
            scope=scope,
            owner_uid=owner,
            group_uid=group,
        )
        result = await exercise_service.create(exercise)
        assert result.is_ok, result.expect_error()
        created[key] = exercise.uid

    # ExerciseService.create writes SHARED_WITH_GROUP through the sharing
    # service, which is not wired here — seed the ADR-040 edge directly so the
    # learner-surface control has a real group share to resolve.
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MATCH (e:Exercise {uid: $uid}), (g:Group {uid: $group_uid})
            MERGE (e)-[:SHARED_WITH_GROUP]->(g)
            """,
            uid=created[ASSIGNED],
            group_uid=GROUP_UID,
        )
    return created


@pytest.fixture
async def seeded(clean_neo4j, neo4j_driver, exercise_service) -> dict[str, str]:
    await _seed_users_and_group(neo4j_driver)
    return await _seed_exercises(neo4j_driver, exercise_service)


async def _read(handlers: dict[str, Any], path: str, user_uid: str | None, uid: str) -> str:
    """Render an authoring route as the given user and return its markup."""
    response = await handlers[path](request=_make_request(user_uid), uid=uid)
    return to_xml(response)


async def _read_learner(handlers: dict[str, Any], user_uid: str, uid: str) -> str:
    """Render the student-facing detail fragment for the same exercise."""
    response = await handlers[LEARNER_PATH](request=_make_request(user_uid), uid=uid)
    return to_xml(response)


async def _read_dashboard(handlers: dict[str, Any], user_uid: str) -> str:
    """Render the exercises dashboard fragment — the surface whose cards carry
    the Edit and View buttons these routes serve."""
    response = await handlers[DASHBOARD_PATH](request=_make_request(user_uid))
    return to_xml(response)


def _assert_readable(markup: str, key: str) -> None:
    assert TITLES[key] in markup, f"{key} should be readable but was refused"


def _assert_refused(markup: str, key: str) -> None:
    assert TITLES[key] not in markup, f"{key} leaked to a user outside its audience"
    assert f"secret instructions for {key}" not in markup
    assert "Exercise not found" in markup


# ============================================================================
# The audience, in both directions, on both routes
# ============================================================================


@pytest.mark.parametrize("path", AUTHORING_PATHS, ids=AUTHORING_IDS)
class TestAuthoringAudience:
    """Both routes read the same entity for the same purpose, so both get the
    same coverage — parametrizing rather than duplicating means neither can
    drift into its own policy."""

    async def test_author_reads_own_personal(self, handlers, seeded, path) -> None:
        """Positive control — the predicate must not refuse everything."""
        markup = await _read(handlers, path, AUTHOR, seeded[PERSONAL_AUTHOR])
        _assert_readable(markup, PERSONAL_AUTHOR)

    async def test_another_teacher_is_refused_the_authors_personal(
        self, handlers, seeded, path
    ) -> None:
        """Same exercise, same route, same role — only ownership differs."""
        markup = await _read(handlers, path, OTHER_TEACHER, seeded[PERSONAL_AUTHOR])
        _assert_refused(markup, PERSONAL_AUTHOR)

    async def test_a_teacher_is_refused_a_students_personal(self, handlers, seeded, path) -> None:
        """The leak this file exists for: a student's private exercise was
        readable — and editable — by any teacher at all (ADR-042 §3)."""
        markup = await _read(handlers, path, OTHER_TEACHER, seeded[PERSONAL_STUDENT])
        _assert_refused(markup, PERSONAL_STUDENT)

    async def test_owning_another_exercise_grants_nothing(self, handlers, seeded, path) -> None:
        """AUTHOR is a legitimate author elsewhere in this same fixture, so a
        refusal here cannot be 'this user can never read anything'."""
        markup = await _read(handlers, path, AUTHOR, seeded[PERSONAL_STUDENT])
        _assert_refused(markup, PERSONAL_STUDENT)

    async def test_assessment_is_owner_scoped(self, handlers, seeded, path) -> None:
        uid = seeded[ASSESSMENT]
        _assert_refused(await _read(handlers, path, OTHER_TEACHER, uid), ASSESSMENT)
        _assert_readable(await _read(handlers, path, AUTHOR, uid), ASSESSMENT)

    async def test_assigned_is_owner_scoped_not_group_scoped(self, handlers, seeded, path) -> None:
        """GROUP_TEACHER is inside this exercise's SCOPE_AWARE audience — they
        are a member of the group it is shared with — and is still refused
        here. This is the deliberate narrowing: an authoring surface answers to
        authorship, not to readership."""
        uid = seeded[ASSIGNED]
        _assert_refused(await _read(handlers, path, GROUP_TEACHER, uid), ASSIGNED)
        _assert_readable(await _read(handlers, path, AUTHOR, uid), ASSIGNED)

    @pytest.mark.parametrize("user_uid", TEACHERS, ids=["author", "other-teacher", "group-teacher"])
    async def test_ownerless_curriculum_has_no_author(
        self, handlers, seeded, path, user_uid
    ) -> None:
        """CURRICULUM is vault-authored and has no owner, so no teacher is its
        author — including the one who authors everything else here."""
        markup = await _read(handlers, path, user_uid, seeded[CURRICULUM])
        _assert_refused(markup, CURRICULUM)


# ============================================================================
# The OWNS edge is half a dual write, and the other half must still count
# ============================================================================


@pytest.mark.parametrize("path", AUTHORING_PATHS, ids=AUTHORING_IDS)
class TestOwnerWithoutOwnsEdge:
    """An owner whose ``:OWNS`` edge is missing must still reach their exercise.

    ``ExerciseService.create()`` persists the node and only *warns* when
    ``create_owns_relationship()`` fails, so this state follows a create that
    reported success. Scoping on the edge alone would 404 an author on their
    own work — a regression caused by a fix.
    """

    async def test_author_still_reads_with_the_owns_edge_deleted(
        self, handlers, seeded, neo4j_driver, path
    ) -> None:
        uid = seeded[PERSONAL_AUTHOR]
        async with neo4j_driver.session() as session:
            result = await session.run(
                "MATCH (:User {uid: $owner})-[r:OWNS]->(e:Exercise {uid: $uid}) "
                "DELETE r RETURN count(r) AS deleted",
                owner=AUTHOR,
                uid=uid,
            )
            record = await result.single()
        # Positive control on the fixture itself: if the seed never wrote the
        # edge, deleting nothing would make the assertion below vacuous.
        assert record["deleted"] == 1

        _assert_readable(await _read(handlers, path, AUTHOR, uid), PERSONAL_AUTHOR)

    async def test_other_teacher_still_refused_with_the_owns_edge_deleted(
        self, handlers, seeded, neo4j_driver, path
    ) -> None:
        """The owner_uid claim must widen the audience by exactly one user."""
        uid = seeded[PERSONAL_AUTHOR]
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (:User {uid: $owner})-[r:OWNS]->(e:Exercise {uid: $uid}) DELETE r",
                owner=AUTHOR,
                uid=uid,
            )

        _assert_refused(await _read(handlers, path, OTHER_TEACHER, uid), PERSONAL_AUTHOR)


# ============================================================================
# The refusal must be 404-equivalent, not 403-equivalent
# ============================================================================


@pytest.mark.parametrize("path", AUTHORING_PATHS, ids=AUTHORING_IDS)
class TestRefusalLeaksNothing:
    """Per OWNERSHIP_VERIFICATION.md a refusal may not confirm that a UID
    exists. Byte-identical output is the strong form: a distinct "forbidden"
    branch, or a message echoing the uid, makes these diverge."""

    async def test_foreign_personal_is_indistinguishable_from_a_missing_uid(
        self, handlers, seeded, path
    ) -> None:
        refused = await _read(handlers, path, OTHER_TEACHER, seeded[PERSONAL_STUDENT])
        absent = await _read(handlers, path, OTHER_TEACHER, "exercise_does_not_exist_at_all")
        assert refused == absent

    async def test_ownerless_curriculum_is_indistinguishable_from_a_missing_uid(
        self, handlers, seeded, path
    ) -> None:
        """An ownerless entity fails ownership verification down a different
        internal branch than a foreign one. The route must still emit one
        answer — otherwise the refusal itself classifies the UID."""
        refused = await _read(handlers, path, AUTHOR, seeded[CURRICULUM])
        absent = await _read(handlers, path, AUTHOR, "exercise_does_not_exist_at_all")
        assert refused == absent


# ============================================================================
# The reason the audience is the owner and not the wider learner rule
# ============================================================================


class TestReadMatchesWrite:
    async def test_edit_form_renders_exactly_when_the_save_would_succeed(
        self, handlers, seeded, exercise_service
    ) -> None:
        """The edit form and its Save target must admit the same set.

        The form posts to ``PUT /api/exercises/{uid}``, which routes through
        ``update_for_user``. Probing the real write — rather than re-asserting
        the read's own helper — is what makes this independent of the predicate
        under test. Asserting agreement, not a hand-copied matrix, means the
        two cannot drift apart without failing here.
        """
        for key, uid in seeded.items():
            for user_uid in TEACHERS:
                markup = await _read(handlers, EDIT_PATH, user_uid, uid)
                form_rendered = TITLES[key] in markup

                write = await exercise_service.update_for_user(
                    uid,
                    RawChanges({"description": f"probe from {user_uid}"}),
                    user_uid,
                )

                assert form_rendered == write.is_ok, (
                    f"{user_uid} on {key}: the edit form "
                    f"{'rendered' if form_rendered else 'refused'} but its Save "
                    f"{'succeeded' if write.is_ok else 'failed'} — a form that "
                    f"cannot save, or a save with no form"
                )


class TestDashboardOffersNoDeadButtons:
    async def test_every_listed_exercise_opens_in_the_authoring_routes(
        self, handlers, seeded
    ) -> None:
        """Every card the dashboard renders carries Edit and View buttons, so
        each one must open.

        The two surfaces resolve the same ownership claim through different
        halves of a dual write — the listing traverses the ``:OWNS`` edge, the
        authoring check reads the ``owner_uid`` property — so their agreement is
        a statement about the data, not a tautology. Only this direction holds:
        the reverse would forbid ``TestOwnerWithoutOwnsEdge``, where an author
        whose edge is missing drops off the listing but must still get in.
        """
        checked = 0
        for user_uid in TEACHERS:
            dashboard = await _read_dashboard(handlers, user_uid)
            for key, title in TITLES.items():
                if title not in dashboard:
                    continue
                for path in AUTHORING_PATHS:
                    _assert_readable(await _read(handlers, path, user_uid, seeded[key]), key)
                checked += 1

        # Without this the loop passes by listing nothing at all — and two of
        # the three teachers legitimately list nothing.
        assert checked == 3, (
            f"expected AUTHOR's three owned exercises on the dashboard, checked {checked}"
        )


class TestLearnerSurfaceStillServes:
    """Refusing on the authoring surface must not remove a read from the app.

    Each case below is a user refused by ``TestAuthoringAudience`` reading the
    very same exercise on ``/exercises/get/content``, which serves the full
    SCOPE_AWARE audience. Without these, "scoped" and "deleted" would look
    identical from the outside.
    """

    async def test_group_member_reads_the_assigned_exercise_there(self, handlers, seeded) -> None:
        uid = seeded[ASSIGNED]
        _assert_refused(await _read(handlers, VIEW_PATH, GROUP_TEACHER, uid), ASSIGNED)
        _assert_readable(await _read_learner(handlers, GROUP_TEACHER, uid), ASSIGNED)

    async def test_any_user_reads_the_curriculum_exercise_there(self, handlers, seeded) -> None:
        uid = seeded[CURRICULUM]
        _assert_refused(await _read(handlers, VIEW_PATH, OTHER_TEACHER, uid), CURRICULUM)
        _assert_readable(await _read_learner(handlers, OTHER_TEACHER, uid), CURRICULUM)

    async def test_the_students_private_exercise_is_refused_on_both(self, handlers, seeded) -> None:
        """The one case with no relocation: a teacher outside the audience is
        refused on the learner surface too, so this content is not readable by
        them anywhere. That is the point of ADR-042 §3."""
        uid = seeded[PERSONAL_STUDENT]
        _assert_refused(await _read(handlers, VIEW_PATH, OTHER_TEACHER, uid), PERSONAL_STUDENT)
        _assert_refused(await _read_learner(handlers, OTHER_TEACHER, uid), PERSONAL_STUDENT)


# ============================================================================
# Ownership scoping is additional to the role gate, not a replacement for it
# ============================================================================


@pytest.mark.parametrize("path", AUTHORING_PATHS, ids=AUTHORING_IDS)
class TestRoleGateStillApplies:
    async def test_a_non_teacher_owner_cannot_reach_the_authoring_routes(
        self, handlers, seeded, path
    ) -> None:
        """STUDENT owns this exercise, so the ownership check would pass — the
        403 can only come from the role gate."""
        with pytest.raises(HTTPException) as exc_info:
            await _read(handlers, path, STUDENT, seeded[PERSONAL_STUDENT])
        assert exc_info.value.status_code == 403

    async def test_an_unauthenticated_request_is_rejected(self, handlers, seeded, path) -> None:
        with pytest.raises(HTTPException) as exc_info:
            await _read(handlers, path, None, seeded[PERSONAL_AUTHOR])
        assert exc_info.value.status_code == 401
