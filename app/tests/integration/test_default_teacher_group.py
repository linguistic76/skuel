"""
Integration tests pinning the care-arc teacher-path fixes (testcontainer Neo4j).

Three seams, all raw-Cypher and therefore invisible to the mock-only suites:

1. ``UserEntryBackend.get_admin_uid`` — the default-teacher pick is the
   oldest admin, by ``created_at``.
2. ``SharingBackend.query_exercise_teacher`` — a CURRICULUM exercise's
   feedback request goes to the teacher its vault file names (``REVIEWED_BY``,
   ADR-091 S3), never to the learner's default group. A revision resolves to
   the exercise it revises in this lookup, so a turn-in against a revision
   reaches the root exercise's teacher (N8).
3. ``PsBackend.count_in_progress_path_steps`` — the basis of the enrollment
   cap counts IN_PROGRESS edges to :PathStep nodes only; a :Ku edge must
   not inflate the cap.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.curriculum_backends import PsBackend
from adapters.persistence.neo4j.backends.sharing_backend import SharingBackend
from core.models.entity import Entity
from core.models.enums.neo_labels import NeoLabel
from core.models.group.group import default_group_uid
from core.services.ps.ps_mastery_service import PsMasteryService
from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid

pytestmark = pytest.mark.asyncio(loop_scope="session")

# Unique per run so a shared/session container never sees stale collisions.
_RUN = uuid.uuid4().hex[:8]

# --- (a) get_admin_uid fixtures -------------------------------------------
_OLDER_ADMIN_UID = seed_user_uid(f"zz_older_admin_{_RUN}")
_NEWER_ADMIN_UID = seed_user_uid(f"zz_newer_admin_{_RUN}")

# --- (b) default-group fixtures --------------------------------------------
_CURRICULUM_EX_UID = f"ex.test.dtg-{_RUN}"
_UNNAMED_EX_UID = f"ex.test.dtg-unnamed-{_RUN}"
_CURRICULUM_REVISION_UID = f"re.test-curriculum-{_RUN}"
_ORPHAN_REVISION_UID = f"re.test-orphan-{_RUN}"
_STUDENT_UID = seed_user_uid(f"zz_student_{_RUN}")
_LONER_UID = seed_user_uid(f"zz_loner_{_RUN}")  # in no default group
_NAMED_TEACHER_UID = seed_user_uid(f"zz_named_teacher_{_RUN}")  # the curriculum exercise's teacher
_DEFAULT_GROUP_UID = default_group_uid(seed_user_uid(f"zz_admin_{_RUN}"))

# --- (c) enrollment-cap fixtures --------------------------------------------
_LEARNER_UID = seed_user_uid(f"zz_learner_{_RUN}")
_PS_UIDS = [f"ps.test.cap-one-{_RUN}", f"ps.test.cap-two-{_RUN}"]
_KU_UID = f"ku.test-cap-{_RUN}"


@pytest_asyncio.fixture(loop_scope="session")
async def admin_pick_graph(neo4j_driver):
    """Two admins: the older one is the pick."""
    rows = [
        (_OLDER_ADMIN_UID, "older@example.com", "2020-01-01T00:00:00"),
        (_NEWER_ADMIN_UID, "newer@example.com", "2021-01-01T00:00:00"),
    ]
    async with neo4j_driver.session() as session:
        for uid, email, created_at in rows:
            await session.run(
                """
                MERGE (u:User {uid: $uid})
                SET u.title = $uid,
                    u.email = $email,
                    u.role = 'admin',
                    u.created_at = datetime($created_at)
                """,
                uid=uid,
                email=email,
                created_at=created_at,
            )

    yield {"older_admin_uid": _OLDER_ADMIN_UID, "newer_admin_uid": _NEWER_ADMIN_UID}

    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (u:User) WHERE u.uid IN $uids DETACH DELETE u",
            uids=[r[0] for r in rows],
        )


@pytest_asyncio.fixture(loop_scope="session")
async def default_group_graph(neo4j_driver):
    """Two curriculum Exercises (one naming a teacher), a default group, one member,
    one loner."""
    async with neo4j_driver.session() as session:
        await session.run(
            """
            MERGE (ex:Entity:Exercise {uid: $uid})
            SET ex.title = 'DTG curriculum exercise',
                ex.entity_type = 'exercise',
                ex.scope = 'curriculum'
            """,
            uid=_CURRICULUM_EX_UID,
        )
        await session.run(
            """
            MERGE (ex:Entity:Exercise {uid: $uid})
            SET ex.title = 'DTG exercise naming no teacher',
                ex.entity_type = 'exercise',
                ex.scope = 'curriculum'
            """,
            uid=_UNNAMED_EX_UID,
        )
        for user_uid in (_STUDENT_UID, _LONER_UID):
            await session.run(
                "MERGE (u:User {uid: $uid}) SET u.title = $uid",
                uid=user_uid,
            )
        # The curriculum exercise names its teacher, as the vault door writes it.
        await session.run(
            """
            MATCH (ex:Entity:Exercise {uid: $ex})
            MERGE (t:User {uid: $teacher})
            SET t.title = $teacher, t.role = 'teacher'
            MERGE (ex)-[:REVIEWED_BY]->(t)
            """,
            ex=_CURRICULUM_EX_UID,
            teacher=_NAMED_TEACHER_UID,
        )
        await session.run(
            """
            MERGE (g:Group {uid: $group_uid})
            SET g.title = 'Default group (DTG test)', g.is_default = true
            WITH g
            MATCH (u:User {uid: $user_uid})
            MERGE (u)-[:MEMBER_OF]->(g)
            """,
            group_uid=_DEFAULT_GROUP_UID,
            user_uid=_STUDENT_UID,
        )

        # Revisions: one of the curriculum exercise, one whose original is gone.
        await session.run(
            """
            MATCH (curriculum:Entity:Exercise {uid: $curriculum_uid})
            MERGE (rc:Entity:RevisedExercise {uid: $curriculum_revision_uid})
            SET rc.entity_type = 'revised_exercise', rc.student_uid = $student_uid
            MERGE (rc)-[:REVISES_EXERCISE]->(curriculum)
            MERGE (ro:Entity:RevisedExercise {uid: $orphan_revision_uid})
            SET ro.entity_type = 'revised_exercise'
            """,
            curriculum_uid=_CURRICULUM_EX_UID,
            student_uid=_STUDENT_UID,
            curriculum_revision_uid=_CURRICULUM_REVISION_UID,
            orphan_revision_uid=_ORPHAN_REVISION_UID,
        )

    yield {
        "curriculum_ex": _CURRICULUM_EX_UID,
        "unnamed_ex": _UNNAMED_EX_UID,
        "curriculum_revision": _CURRICULUM_REVISION_UID,
        "orphan_revision": _ORPHAN_REVISION_UID,
        "student": _STUDENT_UID,
        "loner": _LONER_UID,
        "group": _DEFAULT_GROUP_UID,
        "teacher": _NAMED_TEACHER_UID,
    }

    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (n) WHERE n.uid IN $uids DETACH DELETE n",
            uids=[
                _CURRICULUM_EX_UID,
                _UNNAMED_EX_UID,
                _CURRICULUM_REVISION_UID,
                _ORPHAN_REVISION_UID,
                _STUDENT_UID,
                _LONER_UID,
                _DEFAULT_GROUP_UID,
                _NAMED_TEACHER_UID,
            ],
        )


@pytest_asyncio.fixture(loop_scope="session")
async def enrollment_cap_graph(neo4j_driver):
    """Learner with IN_PROGRESS → 2 PathSteps and IN_PROGRESS → 1 Ku."""
    async with neo4j_driver.session() as session:
        await session.run(
            "MERGE (u:User {uid: $uid}) SET u.title = $uid",
            uid=_LEARNER_UID,
        )
        for ps_uid in _PS_UIDS:
            await session.run(
                """
                MERGE (ps:Entity:PathStep {uid: $uid})
                SET ps.title = $uid, ps.entity_type = 'path_step', ps.status = 'active'
                WITH ps
                MATCH (u:User {uid: $user_uid})
                MERGE (u)-[:IN_PROGRESS]->(ps)
                """,
                uid=ps_uid,
                user_uid=_LEARNER_UID,
            )
        # A Ku IN_PROGRESS edge exists too (KU-grain study) — it must NOT
        # count against the PathStep enrollment cap.
        await session.run(
            """
            MERGE (k:Entity:Ku {uid: $uid})
            SET k.title = $uid, k.entity_type = 'ku'
            WITH k
            MATCH (u:User {uid: $user_uid})
            MERGE (u)-[:IN_PROGRESS]->(k)
            """,
            uid=_KU_UID,
            user_uid=_LEARNER_UID,
        )

    yield {"learner": _LEARNER_UID}

    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (n) WHERE n.uid IN $uids DETACH DELETE n",
            uids=[_LEARNER_UID, *_PS_UIDS, _KU_UID],
        )


# ============================================================================
# (a) get_admin_uid — service accounts never win the default-teacher pick
# ============================================================================


async def test_get_admin_uid_picks_the_oldest_admin(neo4j_driver, admin_pick_graph):
    backend = build_production_backends(neo4j_driver)["user_entry_backend"]

    result = await backend.get_admin_uid()

    assert result.is_ok, f"get_admin_uid failed: {result.error}"
    records = result.value or []
    assert records, "An admin exists — get_admin_uid must return a row"
    # The older admin (2020) is older than any admin another test could create with
    # datetime.now(), so it wins on a session-shared container too.
    assert records[0]["admin_uid"] == admin_pick_graph["older_admin_uid"]


# ============================================================================
# (b) query_exercise_teacher — a curriculum exercise asks the teacher it names
# ============================================================================


def _sharing_backend(neo4j_driver) -> SharingBackend:
    # Same construction as services_bootstrap/compose.py.
    return SharingBackend(neo4j_driver, NeoLabel.ENTITY, Entity)


async def _teachers(neo4j_driver, exercise_uid: str, user_uid: str) -> list[str]:
    result = await _sharing_backend(neo4j_driver).query_exercise_teacher(
        exercise_uid=exercise_uid, user_uid=user_uid
    )
    assert result.is_ok, f"Query failed: {result.error}"
    return [row["teacher_uid"] for row in result.value or []]


async def test_a_curriculum_exercise_asks_its_named_teacher(neo4j_driver, default_group_graph):
    """The student is in a default group; the request still goes to the named teacher."""
    assert await _teachers(
        neo4j_driver, default_group_graph["curriculum_ex"], default_group_graph["student"]
    ) == [default_group_graph["teacher"]]


async def test_an_exercise_naming_no_teacher_asks_nobody(neo4j_driver, default_group_graph):
    assert (
        await _teachers(
            neo4j_driver, default_group_graph["unnamed_ex"], default_group_graph["student"]
        )
        == []
    )


async def test_the_named_teacher_never_asks_themselves(neo4j_driver, default_group_graph):
    assert (
        await _teachers(
            neo4j_driver, default_group_graph["curriculum_ex"], default_group_graph["teacher"]
        )
        == []
    )


async def test_revision_of_a_curriculum_exercise_asks_its_roots_teacher(
    neo4j_driver, default_group_graph
):
    """A revision names no teacher of its own; it resolves to the exercise it revises."""
    assert await _teachers(
        neo4j_driver,
        default_group_graph["curriculum_revision"],
        default_group_graph["student"],
    ) == [default_group_graph["teacher"]]


async def test_revision_with_no_original_asks_nobody(neo4j_driver, default_group_graph):
    assert (
        await _teachers(
            neo4j_driver, default_group_graph["orphan_revision"], default_group_graph["student"]
        )
        == []
    )


async def test_a_revision_is_usable_by_the_student_it_names(neo4j_driver, default_group_graph):
    """The exercise-use check: a revision is never owned by its student, so the
    claim is the revision's own ``student_uid``."""
    backend = _sharing_backend(neo4j_driver)

    named = await backend.query_user_can_use_exercise(
        exercise_uid=default_group_graph["curriculum_revision"],
        user_uid=default_group_graph["student"],
    )
    other = await backend.query_user_can_use_exercise(
        exercise_uid=default_group_graph["curriculum_revision"],
        user_uid=default_group_graph["loner"],
    )
    unaddressed = await backend.query_user_can_use_exercise(
        exercise_uid=default_group_graph["orphan_revision"],
        user_uid=default_group_graph["student"],
    )

    assert named.is_ok and other.is_ok and unaddressed.is_ok
    assert named.value is True
    assert other.value is False
    assert unaddressed.value is False


# ============================================================================
# (c) enrollment cap basis — count IN_PROGRESS → :PathStep only
# ============================================================================


def _ps_backend(neo4j_driver) -> PsBackend:
    # Same construction as the conftest `services` fixture.
    return build_production_backends(neo4j_driver)["ps_backend"]


async def test_count_in_progress_counts_path_steps_only(neo4j_driver, enrollment_cap_graph):
    """2 IN_PROGRESS→PathStep edges + 1 IN_PROGRESS→Ku edge → count == 2."""
    backend = _ps_backend(neo4j_driver)

    result = await backend.count_in_progress_path_steps(enrollment_cap_graph["learner"])

    assert result.is_ok, f"count_in_progress_path_steps failed: {result.error}"
    records = result.value or []
    assert records, "Count query must return a row"
    assert int(records[0]["cnt"]) == 2, (
        "The enrollment-cap basis must count IN_PROGRESS→PathStep edges only; "
        "a :Ku IN_PROGRESS edge must not inflate the cap"
    )


async def test_mastery_service_count_matches_backend(neo4j_driver, enrollment_cap_graph):
    """The service layer the enrollment cap actually calls agrees with the backend."""
    service = PsMasteryService(backend=_ps_backend(neo4j_driver))

    result = await service.count_in_progress_steps(enrollment_cap_graph["learner"])

    assert result.is_ok, f"count_in_progress_steps failed: {result.error}"
    assert result.value == 2
