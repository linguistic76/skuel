"""
Integration tests pinning the care-arc teacher-path fixes (testcontainer Neo4j).

Three seams, all raw-Cypher and therefore invisible to the mock-only suites:

1. ``UserEntryBackend.get_admin_uid`` — the default-teacher pick must skip
   service accounts (``@skuel.local`` emails: user_system, the legacy
   vault-watcher) even when they are OLDER than the real admin. A default
   group owned by user_system is a review queue nobody can log into.
2. ``SharingBackend.query_default_groups_for_curriculum_submission`` — the
   fallback review route for CURRICULUM exercises is scope-gated in Cypher:
   personal exercises must resolve to zero rows so they can never leak to
   the default group.
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
from adapters.persistence.neo4j.backends.user_entry_backend import UserEntryBackend
from core.models.entity import Entity
from core.models.enums.neo_labels import NeoLabel
from core.services.ps.ps_mastery_service import PsMasteryService

pytestmark = pytest.mark.asyncio(loop_scope="session")

# Unique per run so a shared/session container never sees stale collisions.
_RUN = uuid.uuid4().hex[:8]

# --- (a) get_admin_uid fixtures -------------------------------------------
_SVC_SYSTEM_UID = f"user_zz_svc_system_{_RUN}"
_SVC_WATCHER_UID = f"user_zz_svc_watcher_{_RUN}"
_REAL_ADMIN_UID = f"user_zz_real_admin_{_RUN}"

# --- (b) default-group fixtures --------------------------------------------
_CURRICULUM_EX_UID = f"ex.test.dtg.{_RUN}"
_PERSONAL_EX_UID = f"ex_test_personal_{_RUN}"
_STUDENT_UID = f"user_zz_student_{_RUN}"
_LONER_UID = f"user_zz_loner_{_RUN}"  # in no default group
_DEFAULT_GROUP_UID = f"group_default_user_zz_admin_{_RUN}"

# --- (c) enrollment-cap fixtures --------------------------------------------
_LEARNER_UID = f"user_zz_learner_{_RUN}"
_PS_UIDS = [f"ps.test.cap-one.{_RUN}", f"ps.test.cap-two.{_RUN}"]
_KU_UID = f"ku_test_cap_{_RUN}"


@pytest_asyncio.fixture(loop_scope="session")
async def admin_pick_graph(neo4j_driver):
    """Two OLDER service-account admins + one NEWER real admin.

    Service accounts are deliberately oldest: created_at ordering alone would
    pick them — only the @skuel.local email exclusion saves the real admin.
    """
    rows = [
        (_SVC_SYSTEM_UID, "system@skuel.local", "2020-01-01T00:00:00"),
        (_SVC_WATCHER_UID, "vault-watcher@skuel.local", "2020-06-01T00:00:00"),
        (_REAL_ADMIN_UID, "real@example.com", "2021-01-01T00:00:00"),
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

    yield {"svc_uids": {_SVC_SYSTEM_UID, _SVC_WATCHER_UID}, "real_admin_uid": _REAL_ADMIN_UID}

    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (u:User) WHERE u.uid IN $uids DETACH DELETE u",
            uids=[r[0] for r in rows],
        )


@pytest_asyncio.fixture(loop_scope="session")
async def default_group_graph(neo4j_driver):
    """Curriculum + personal Exercises, a default group, one member, one loner."""
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
            SET ex.title = 'DTG personal exercise',
                ex.entity_type = 'exercise',
                ex.scope = 'personal'
            """,
            uid=_PERSONAL_EX_UID,
        )
        for user_uid in (_STUDENT_UID, _LONER_UID):
            await session.run(
                "MERGE (u:User {uid: $uid}) SET u.title = $uid",
                uid=user_uid,
            )
        await session.run(
            """
            MERGE (g:Group {uid: $group_uid})
            SET g.title = 'Default group (DTG test)'
            WITH g
            MATCH (u:User {uid: $user_uid})
            MERGE (u)-[:MEMBER_OF]->(g)
            """,
            group_uid=_DEFAULT_GROUP_UID,
            user_uid=_STUDENT_UID,
        )

    yield {
        "curriculum_ex": _CURRICULUM_EX_UID,
        "personal_ex": _PERSONAL_EX_UID,
        "student": _STUDENT_UID,
        "loner": _LONER_UID,
        "group": _DEFAULT_GROUP_UID,
    }

    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (n) WHERE n.uid IN $uids DETACH DELETE n",
            uids=[
                _CURRICULUM_EX_UID,
                _PERSONAL_EX_UID,
                _STUDENT_UID,
                _LONER_UID,
                _DEFAULT_GROUP_UID,
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


async def test_get_admin_uid_skips_service_accounts(neo4j_driver, admin_pick_graph):
    backend = UserEntryBackend(neo4j_driver)

    result = await backend.get_admin_uid()

    assert result.is_ok, f"get_admin_uid failed: {result.error}"
    records = result.value or []
    assert records, "An admin exists — get_admin_uid must return a row"
    admin_uid = records[0]["admin_uid"]

    # Robust form (container is session-shared across integration files):
    # whoever wins must be a real human — never a @skuel.local service account.
    assert admin_uid not in admin_pick_graph["svc_uids"], (
        "Service accounts must never win the default-teacher pick, "
        "even when they are the oldest admins"
    )
    async with neo4j_driver.session() as session:
        email_result = await session.run(
            "MATCH (u:User {uid: $uid}) RETURN u.email AS email",
            uid=admin_uid,
        )
        record = await email_result.single()
    assert record is not None, "Returned admin_uid must correspond to a User node"
    email = record["email"] or ""
    assert not email.endswith("@skuel.local"), (
        f"Default teacher resolved to a service account email: {email!r}"
    )

    # Fresh-container form: our real admin (2021) is older than any admin
    # another test could create with datetime.now(), so it must win.
    assert admin_uid == admin_pick_graph["real_admin_uid"]


# ============================================================================
# (b) query_default_groups_for_curriculum_submission — the scope gate
# ============================================================================


def _sharing_backend(neo4j_driver) -> SharingBackend:
    # Same construction as services_bootstrap/compose.py.
    return SharingBackend(neo4j_driver, NeoLabel.ENTITY, Entity)


async def test_curriculum_exercise_routes_to_default_group(neo4j_driver, default_group_graph):
    backend = _sharing_backend(neo4j_driver)

    result = await backend.query_default_groups_for_curriculum_submission(
        exercise_uid=default_group_graph["curriculum_ex"],
        user_uid=default_group_graph["student"],
    )

    assert result.is_ok, f"Query failed: {result.error}"
    group_uids = [row["group_uid"] for row in result.value or []]
    assert group_uids == [default_group_graph["group"]], (
        "A curriculum exercise from a default-group member must resolve to "
        "exactly that default group"
    )


async def test_personal_exercise_never_leaks_to_default_group(neo4j_driver, default_group_graph):
    """The scope gate: scope='personal' must yield ZERO rows even though the
    submitter IS in a default group."""
    backend = _sharing_backend(neo4j_driver)

    result = await backend.query_default_groups_for_curriculum_submission(
        exercise_uid=default_group_graph["personal_ex"],
        user_uid=default_group_graph["student"],
    )

    assert result.is_ok, f"Query failed: {result.error}"
    assert (result.value or []) == [], (
        "PERSONAL submissions must never route to the default group — "
        "the Cypher scope gate is the only thing preventing the leak"
    )


async def test_user_without_default_group_gets_zero_rows(neo4j_driver, default_group_graph):
    backend = _sharing_backend(neo4j_driver)

    result = await backend.query_default_groups_for_curriculum_submission(
        exercise_uid=default_group_graph["curriculum_ex"],
        user_uid=default_group_graph["loner"],
    )

    assert result.is_ok, f"Query failed: {result.error}"
    assert (result.value or []) == [], (
        "A user in no default group must resolve to zero rows, not an error"
    )


# ============================================================================
# (c) enrollment cap basis — count IN_PROGRESS → :PathStep only
# ============================================================================


def _ps_backend(neo4j_driver) -> PsBackend:
    # Same construction as the conftest `services` fixture.
    return PsBackend(neo4j_driver, NeoLabel.PATH_STEP, Entity, base_label=NeoLabel.ENTITY)


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
