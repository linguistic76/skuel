"""Audience scoping for the direct-read exercise routes.

``GET /exercises/get/content`` (the HTMX fragment behind the student detail
page) and ``GET /api/exercises/md`` both called ``require_authenticated_user``
and discarded the result, then fetched by UID with no scoping — so any
authenticated user could read another user's PERSONAL exercise, instructions
and all, by guessing or replaying a UID.

Exercise declares ``SearchVisibility.SCOPE_AWARE``, so the policy already
existed for the *same entity* on the search surface: CURRICULUM is everyone's,
PERSONAL/ASSIGNED/ASSESSMENT need OWNS / SHARES_WITH / group membership. Search
fail-closed on a foreign PERSONAL exercise while the direct read handed it
over. These tests pin the closed form, and the last one pins the invariant that
made this a bug rather than a preference: **the two surfaces must agree.**

Run against a real Neo4j container, because the audience check IS a Cypher
predicate — a mocked backend would assert only that the route calls a method.
Every refusal is paired with a positive control, so a predicate that refused
everything (equally wrong, and invisible to negative-only assertions) fails.

Note ``/exercises/get`` — the page shell — is deliberately untested here: it
never fetches the exercise, it only echoes the uid into this fragment's URL.
The read is entirely in the fragment, and so is the check.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fasthtml.common import to_xml

from adapters.inbound.exercises_api import create_exercises_api_routes
from adapters.inbound.exercises_ui import create_exercises_ui_routes
from adapters.persistence.neo4j.backends.exercise_backends import ExerciseBackend
from core.models.enums import EntityType, ExerciseScope
from core.models.enums.neo_labels import NeoLabel
from core.models.exercises.exercise import Exercise
from core.services.exercises.exercise_service import ExerciseService

OWNER = "user_ex_owner"
STRANGER = "user_ex_stranger"
TEACHER = "user_ex_teacher"
MEMBER = "user_ex_member"
GROUP_UID = "group_ex_scope"

FRAGMENT_PATH = "/exercises/get/content"
MD_PATH = "/api/exercises/md"

# One distinctive title per scope: assertions key on the title, so a leak shows
# up as the actual secret text appearing in another user's response.
TITLES = {
    ExerciseScope.CURRICULUM: "Photosynthesis shared drill",
    ExerciseScope.PERSONAL: "Owner private journal drill",
    ExerciseScope.ASSIGNED: "Teacher assigned group drill",
    ExerciseScope.ASSESSMENT: "Owner formal assessment drill",
}


@pytest.fixture
def exercise_service(neo4j_driver) -> ExerciseService:
    backend = ExerciseBackend(
        driver=neo4j_driver,
        label=NeoLabel.EXERCISE,
        entity_class=Exercise,
        base_label=NeoLabel.ENTITY,
    )
    return ExerciseService(backend=backend)


def _make_request(user_uid: str | None) -> Any:
    """Minimal session-backed request stub for ``require_authenticated_user``."""
    return SimpleNamespace(
        method="GET",
        session={"user_uid": user_uid} if user_uid is not None else {},
        url=SimpleNamespace(path=FRAGMENT_PATH),
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
    create_exercises_ui_routes(app, rt, exercise_service)
    create_exercises_api_routes(
        app,
        rt,
        exercises_service=exercise_service,
        transcript_service=None,
        entry_report_service=None,
    )
    return registered


async def _seed_users_and_group(neo4j_driver) -> None:
    async with neo4j_driver.session() as session:
        await session.run(
            "UNWIND $uids AS uid MERGE (u:User {uid: uid})",
            uids=[OWNER, STRANGER, TEACHER, MEMBER],
        )
        await session.run(
            """
            MERGE (g:Group {uid: $group_uid})
            WITH g
            MATCH (member:User {uid: $member})
            MERGE (member)-[:MEMBER_OF]->(g)
            """,
            group_uid=GROUP_UID,
            member=MEMBER,
        )


async def _seed_exercises(neo4j_driver, exercise_service: ExerciseService) -> dict[str, str]:
    """All four scopes, keyed by scope value."""
    specs = [
        (ExerciseScope.CURRICULUM, None, None),
        (ExerciseScope.PERSONAL, OWNER, None),
        (ExerciseScope.ASSIGNED, TEACHER, GROUP_UID),
        (ExerciseScope.ASSESSMENT, OWNER, None),
    ]
    created: dict[str, str] = {}
    for scope, owner, group in specs:
        exercise = Exercise(
            uid=f"exercise_audience_{scope.value}",
            title=TITLES[scope],
            entity_type=EntityType.EXERCISE,
            instructions=f"secret instructions for {scope.value}",
            scope=scope,
            owner_uid=owner,
            group_uid=group,
        )
        result = await exercise_service.create(exercise)
        assert result.is_ok, result.expect_error()
        created[scope.value] = exercise.uid

    # ExerciseService.create writes SHARED_WITH_GROUP through the sharing
    # service, which is not wired here — seed the ADR-040 edge directly.
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MATCH (e:Exercise {uid: $uid}), (g:Group {uid: $group_uid})
            MERGE (e)-[:SHARED_WITH_GROUP]->(g)
            """,
            uid=created[ExerciseScope.ASSIGNED.value],
            group_uid=GROUP_UID,
        )
    return created


@pytest.fixture
async def seeded(clean_neo4j, neo4j_driver, exercise_service) -> dict[str, str]:
    await _seed_users_and_group(neo4j_driver)
    return await _seed_exercises(neo4j_driver, exercise_service)


async def _read_fragment(handlers: dict[str, Any], user_uid: str | None, uid: str) -> str:
    """Render the detail fragment as the given user and return its markup."""
    response = await handlers[FRAGMENT_PATH](request=_make_request(user_uid), uid=uid)
    return to_xml(response)


def _assert_readable(markup: str, scope: ExerciseScope) -> None:
    assert TITLES[scope] in markup, f"{scope.value} should be readable but was refused"


def _assert_refused(markup: str, scope: ExerciseScope) -> None:
    assert TITLES[scope] not in markup, f"{scope.value} leaked to a user outside its audience"
    assert f"secret instructions for {scope.value}" not in markup
    assert "Exercise not found" in markup


# ============================================================================
# The four scopes, each in both directions
# ============================================================================


class TestFragmentAudience:
    async def test_curriculum_is_readable_by_a_stranger(self, handlers, seeded) -> None:
        """CURRICULUM is shared content — scoping must not hide it."""
        markup = await _read_fragment(handlers, STRANGER, seeded[ExerciseScope.CURRICULUM.value])
        _assert_readable(markup, ExerciseScope.CURRICULUM)

    async def test_foreign_personal_is_not_found(self, handlers, seeded) -> None:
        """The leak: a stranger could read the owner's PERSONAL exercise."""
        markup = await _read_fragment(handlers, STRANGER, seeded[ExerciseScope.PERSONAL.value])
        _assert_refused(markup, ExerciseScope.PERSONAL)

    async def test_owner_still_reads_own_personal(self, handlers, seeded) -> None:
        """Positive control — the predicate must not refuse everything."""
        markup = await _read_fragment(handlers, OWNER, seeded[ExerciseScope.PERSONAL.value])
        _assert_readable(markup, ExerciseScope.PERSONAL)

    async def test_assigned_is_readable_via_group_membership(self, handlers, seeded) -> None:
        """MEMBER_OF + SHARED_WITH_GROUP grants access without ownership."""
        markup = await _read_fragment(handlers, MEMBER, seeded[ExerciseScope.ASSIGNED.value])
        _assert_readable(markup, ExerciseScope.ASSIGNED)

    async def test_assigned_is_refused_to_non_member(self, handlers, seeded) -> None:
        """Same exercise, same route — only group membership differs."""
        markup = await _read_fragment(handlers, STRANGER, seeded[ExerciseScope.ASSIGNED.value])
        _assert_refused(markup, ExerciseScope.ASSIGNED)

    async def test_assessment_is_owner_scoped(self, handlers, seeded) -> None:
        """The fourth scope: a formal assessment is not public curriculum."""
        uid = seeded[ExerciseScope.ASSESSMENT.value]
        _assert_refused(await _read_fragment(handlers, STRANGER, uid), ExerciseScope.ASSESSMENT)
        _assert_readable(await _read_fragment(handlers, OWNER, uid), ExerciseScope.ASSESSMENT)


# ============================================================================
# The OWNS edge is half a dual write, and the other half must still count
# ============================================================================


class TestOwnerWithoutOwnsEdge:
    """An owner whose OWNS edge is missing must still reach their exercise.

    `ExerciseService.create()` persists the node and only *warns* when
    `create_owns_relationship()` fails, so this state follows a create that
    reported success. Scoping on the edge alone would hide an exercise from the
    very user who made it — a 404 on your own content, caused by a fix.
    """

    async def test_owner_reads_own_exercise_with_the_owns_edge_deleted(
        self, handlers, seeded, neo4j_driver
    ) -> None:
        uid = seeded[ExerciseScope.PERSONAL.value]
        async with neo4j_driver.session() as session:
            result = await session.run(
                "MATCH (:User {uid: $owner})-[r:OWNS]->(e:Exercise {uid: $uid}) "
                "DELETE r RETURN count(r) AS deleted",
                owner=OWNER,
                uid=uid,
            )
            record = await result.single()
        # Positive control on the fixture itself: if the seed never wrote the
        # edge, deleting nothing would make the assertion below vacuous.
        assert record["deleted"] == 1

        markup = await _read_fragment(handlers, OWNER, uid)
        _assert_readable(markup, ExerciseScope.PERSONAL)

    async def test_stranger_still_refused_with_the_owns_edge_deleted(
        self, handlers, seeded, neo4j_driver
    ) -> None:
        """The owner_uid fallback must widen the audience by exactly one user."""
        uid = seeded[ExerciseScope.PERSONAL.value]
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (:User {uid: $owner})-[r:OWNS]->(e:Exercise {uid: $uid}) DELETE r",
                owner=OWNER,
                uid=uid,
            )

        markup = await _read_fragment(handlers, STRANGER, uid)
        _assert_refused(markup, ExerciseScope.PERSONAL)


# ============================================================================
# The refusal must be 404-equivalent, not 403-equivalent
# ============================================================================


class TestRefusalLeaksNothing:
    async def test_refusal_is_indistinguishable_from_a_missing_uid(self, handlers, seeded) -> None:
        """Per OWNERSHIP_VERIFICATION.md a refusal may not confirm existence.

        Byte-identical output is the strong form: with a distinct "forbidden"
        branch, or a message echoing the uid, these two diverge.
        """
        refused = await _read_fragment(handlers, STRANGER, seeded[ExerciseScope.PERSONAL.value])
        absent = await _read_fragment(handlers, STRANGER, "exercise_does_not_exist_at_all")
        assert refused == absent


# ============================================================================
# The .md download route reads the same entity and needed the same check
# ============================================================================


class TestMarkdownDownloadAudience:
    async def test_foreign_personal_download_is_404(self, handlers, seeded) -> None:
        response = await handlers[MD_PATH](
            request=_make_request(STRANGER), uid=seeded[ExerciseScope.PERSONAL.value]
        )
        assert response.status_code == 404
        assert TITLES[ExerciseScope.PERSONAL] not in response.body.decode()

    async def test_owner_download_still_works(self, handlers, seeded) -> None:
        """Positive control for the same route."""
        response = await handlers[MD_PATH](
            request=_make_request(OWNER), uid=seeded[ExerciseScope.PERSONAL.value]
        )
        assert response.status_code == 200
        assert TITLES[ExerciseScope.PERSONAL] in response.body.decode()

    async def test_curriculum_download_open_to_all(self, handlers, seeded) -> None:
        response = await handlers[MD_PATH](
            request=_make_request(STRANGER), uid=seeded[ExerciseScope.CURRICULUM.value]
        )
        assert response.status_code == 200


# ============================================================================
# The invariant behind the bug: one entity, one answer
# ============================================================================


class TestSurfacesAgree:
    @pytest.mark.parametrize(
        "user_uid",
        [OWNER, STRANGER, MEMBER, TEACHER],
        ids=["owner", "stranger", "group-member", "teacher"],
    )
    async def test_direct_read_matches_search_for_every_scope(
        self, handlers, seeded, exercise_service, user_uid: str
    ) -> None:
        """Search and the direct read must classify each exercise identically.

        This is the defect stated as a property: search declared SCOPE_AWARE
        and refused, the direct read had no policy at all and allowed. Asserting
        agreement — rather than a hand-copied expected matrix — means the two
        cannot drift apart again without failing here.
        """
        search = await exercise_service.search("drill", user_uid=user_uid, limit=50)
        assert search.is_ok, search.expect_error()
        searchable = {e.uid for e in search.value}

        for uid in seeded.values():
            direct = await exercise_service.get_exercise_for_user(uid, user_uid)
            assert direct.is_ok == (uid in searchable), (
                f"{user_uid}: search and direct read disagree on {uid} "
                f"(search={'visible' if uid in searchable else 'hidden'}, "
                f"direct={'visible' if direct.is_ok else 'refused'})"
            )
