"""Curriculum lateral writes: a TEACHER gate and curriculum-only endpoints.

The ku / ps / lp lateral routes have no owner to verify, so they pass
``domain_service=None``. Two things stand in for the ownership check, and a
missing one would let any user write curriculum edges, or join a Ku to another
user's private task and learn from the answer whether that uid exists.

The contract, pinned here over real HTTP against a real Neo4j
(``tests/helpers/lateral_routes_client.py``):

- every curriculum write route answers 403 to a MEMBER and lets a TEACHER (and
  an ADMIN, through the role hierarchy) through;
- a curriculum write names only curriculum endpoints: a private entity is
  answered exactly as a nonexistent uid is — same status, same body — and no
  edge is written or removed;
- the Activity routes keep their ownership gate and consult no role.

"""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest
import pytest_asyncio
from neo4j import AsyncDriver

from adapters.inbound.route_factories.lateral_route_factory import LateralRouteFactory
from core.models.enums import UserRole
from tests.helpers.lateral_routes_client import (
    RoleUserService,
    lateral_client,
    without_timestamp,
)

MEMBER = "user_f4_member"
TEACHER = "user_f4_teacher"
ADMIN = "user_f4_admin"
OTHER = "user_f4_other"  # owns the private task; never signs in
ROLES = {
    MEMBER: UserRole.MEMBER,
    TEACHER: UserRole.TEACHER,
    ADMIN: UserRole.ADMIN,
    OTHER: UserRole.MEMBER,
}

KU_PARENT = "ku.f4.parent"
KU_A = "ku.f4.a"
KU_B = "ku.f4.b"
PS_A = "ps.f4.a"
LP_A = "lp.f4.a"
PRIVATE_TASK = "task_f4_private"
MEMBER_TASK_A = "task_f4_member_a"
MEMBER_TASK_B = "task_f4_member_b"
MISSING = "ku.f4.missing"
_ALL_UIDS = [KU_PARENT, KU_A, KU_B, PS_A, LP_A, PRIVATE_TASK, MEMBER_TASK_A, MEMBER_TASK_B]

# The anchor each curriculum domain's routes are exercised on.
ANCHORS = {"ku": KU_A, "ps": PS_A, "lp": LP_A}

# (route suffix, form fields beyond target_uid, relationship type written)
CREATES = [
    ("blocks", {"reason": "order matters"}, "BLOCKS"),
    ("prerequisites", {}, "PREREQUISITE_FOR"),
    ("alternatives", {"comparison_criteria": "depth"}, "ALTERNATIVE_TO"),
    ("complementary", {"synergy_description": "pair well"}, "COMPLEMENTARY_TO"),
]
CREATE_IDS = [suffix for suffix, _, _ in CREATES]


def _curriculum_writes(target: str) -> list[tuple[str, str, dict[str, str]]]:
    """Every curriculum write route as (method, path, form) aimed at ``target``."""
    writes: list[tuple[str, str, dict[str, str]]] = []
    for domain, anchor in ANCHORS.items():
        for suffix, extra, _ in CREATES:
            writes.append(
                (
                    "POST",
                    f"/api/{domain}/{anchor}/lateral/{suffix}",
                    {"target_uid": target, **extra},
                )
            )
        writes.append(("DELETE", f"/api/{domain}/{anchor}/lateral/blocks/{target}", {}))
    writes.append(("POST", f"/api/ku/{KU_A}/lateral/enables", {"target_uid": target}))
    return writes


WRITES = _curriculum_writes(KU_B)
WRITE_IDS = [f"{method} {path}" for method, path, _ in WRITES]


@pytest_asyncio.fixture(loop_scope="session")
async def graph(neo4j_driver):
    """Three curriculum kinds under one parent, a stranger's task, a member's two tasks.

    The shared parent keeps BLOCKS's same-parent rule satisfied for curriculum
    pairs, so a refusal of a private endpoint cannot be that rule in disguise.
    """
    async with neo4j_driver.session() as session:
        await session.run(
            """
            CREATE (parent:Entity:Ku {uid: $parent, title: 'Parent', entity_type: 'ku'})
            CREATE (a:Entity:Ku {uid: $ku_a, title: 'Ku A', entity_type: 'ku'})
            CREATE (b:Entity:Ku {uid: $ku_b, title: 'Ku B', entity_type: 'ku'})
            CREATE (ps:Entity:PathStep {uid: $ps_a, title: 'Step', entity_type: 'path_step'})
            CREATE (lp:Entity:LearningPath {uid: $lp_a, title: 'Path', entity_type: 'learning_path'})
            CREATE (parent)-[:ORGANIZES]->(a), (parent)-[:ORGANIZES]->(b),
                   (parent)-[:ORGANIZES]->(ps), (parent)-[:ORGANIZES]->(lp)
            CREATE (t:Entity:Task {uid: $private, title: 'Stranger secret', entity_type: 'task',
                                   user_uid: $other, status: 'active'})
            CREATE (parent)-[:ORGANIZES]->(t)
            CREATE (:Entity:Task {uid: $mt_a, title: 'Mine A', entity_type: 'task',
                                  user_uid: $member, status: 'active'})
            CREATE (:Entity:Task {uid: $mt_b, title: 'Mine B', entity_type: 'task',
                                  user_uid: $member, status: 'active'})
            """,
            parent=KU_PARENT,
            ku_a=KU_A,
            ku_b=KU_B,
            ps_a=PS_A,
            lp_a=LP_A,
            private=PRIVATE_TASK,
            other=OTHER,
            mt_a=MEMBER_TASK_A,
            mt_b=MEMBER_TASK_B,
            member=MEMBER,
        )
    yield
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n:Entity) WHERE n.uid IN $uids DETACH DELETE n", uids=_ALL_UIDS)


TASK_OWNERS = {MEMBER_TASK_A: MEMBER, MEMBER_TASK_B: MEMBER, PRIVATE_TASK: OTHER}


def _user_service() -> RoleUserService:
    return RoleUserService(ROLES)


def _client(neo4j_driver: AsyncDriver, user_service: RoleUserService) -> httpx.AsyncClient:
    return lateral_client(neo4j_driver, user_service, TASK_OWNERS, secret_key="f4-lateral-gate")


async def _send(client: httpx.AsyncClient, method: str, path: str, form: dict[str, str]):
    if method == "DELETE":
        return await client.delete(path)
    return await client.post(path, data=form)


async def _edges(neo4j_driver, uid_a: str, uid_b: str) -> list[str]:
    async with neo4j_driver.session() as session:
        record = await (
            await session.run(
                "MATCH (:Entity {uid: $a})-[r]-(:Entity {uid: $b}) "
                "RETURN collect(type(r)) AS types",
                a=uid_a,
                b=uid_b,
            )
        ).single()
    assert record is not None
    return sorted(record["types"])


async def _lateral_edges_from(neo4j_driver, uid: str) -> list[str]:
    async with neo4j_driver.session() as session:
        record = await (
            await session.run(
                "MATCH (:Entity {uid: $uid})-[r]-() WHERE type(r) <> 'ORGANIZES' "
                "RETURN collect(type(r)) AS types",
                uid=uid,
            )
        ).single()
    assert record is not None
    return sorted(record["types"])


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.usefixtures("graph")
class TestRoleGate:
    @pytest.mark.parametrize(("method", "path", "form"), WRITES, ids=WRITE_IDS)
    async def test_a_member_is_refused_and_nothing_is_written(
        self, neo4j_driver, method: str, path: str, form: dict[str, str]
    ) -> None:
        async with _client(neo4j_driver, _user_service()) as client:
            await client.get(f"/sign-in/{MEMBER}")
            response = await _send(client, method, path, form)

        assert response.status_code == 403
        for anchor in ANCHORS.values():
            assert await _lateral_edges_from(neo4j_driver, anchor) == []

    async def test_a_member_cannot_delete_an_existing_curriculum_edge(self, neo4j_driver) -> None:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (a:Entity {uid: $a}), (b:Entity {uid: $b}) CREATE (a)-[:BLOCKS]->(b)",
                a=KU_A,
                b=KU_B,
            )
        async with _client(neo4j_driver, _user_service()) as client:
            await client.get(f"/sign-in/{MEMBER}")
            response = await client.delete(f"/api/ku/{KU_A}/lateral/blocks/{KU_B}")

        assert response.status_code == 403
        assert await _edges(neo4j_driver, KU_A, KU_B) == ["BLOCKS"]

    async def test_an_anonymous_caller_is_401(self, neo4j_driver) -> None:
        async with _client(neo4j_driver, _user_service()) as client:
            response = await client.post(
                f"/api/ku/{KU_A}/lateral/prerequisites", data={"target_uid": KU_B}
            )

        assert response.status_code == 401


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.usefixtures("graph")
class TestTeacherWritesCurriculum:
    @pytest.mark.parametrize("domain", list(ANCHORS))
    @pytest.mark.parametrize(("suffix", "extra", "rel_type"), CREATES, ids=CREATE_IDS)
    async def test_a_teacher_creates_the_edge(
        self, neo4j_driver, domain: str, suffix: str, extra: dict[str, str], rel_type: str
    ) -> None:
        anchor = ANCHORS[domain]
        async with _client(neo4j_driver, _user_service()) as client:
            await client.get(f"/sign-in/{TEACHER}")
            response = await client.post(
                f"/api/{domain}/{anchor}/lateral/{suffix}", data={"target_uid": KU_B, **extra}
            )

        assert response.status_code == 201, response.text
        assert rel_type in await _edges(neo4j_driver, anchor, KU_B)

    async def test_a_teacher_creates_an_enables_edge(self, neo4j_driver) -> None:
        async with _client(neo4j_driver, _user_service()) as client:
            await client.get(f"/sign-in/{TEACHER}")
            response = await client.post(
                f"/api/ku/{KU_A}/lateral/enables", data={"target_uid": KU_B}
            )

        assert response.status_code == 201, response.text
        assert await _edges(neo4j_driver, KU_A, KU_B) == ["ENABLED_BY", "ENABLES"]

    async def test_a_teacher_deletes_the_edge(self, neo4j_driver) -> None:
        async with _client(neo4j_driver, _user_service()) as client:
            await client.get(f"/sign-in/{TEACHER}")
            created = await client.post(
                f"/api/ku/{KU_A}/lateral/prerequisites", data={"target_uid": KU_B}
            )
            assert created.status_code == 201, created.text
            deleted = await client.delete(f"/api/ku/{KU_A}/lateral/prerequisites/{KU_B}")

        assert deleted.status_code == 200, deleted.text
        assert await _edges(neo4j_driver, KU_A, KU_B) == []

    async def test_an_admin_passes_through_the_hierarchy(self, neo4j_driver) -> None:
        async with _client(neo4j_driver, _user_service()) as client:
            await client.get(f"/sign-in/{ADMIN}")
            response = await client.post(
                f"/api/lp/{LP_A}/lateral/complementary",
                data={"target_uid": KU_B, "synergy_description": "pair well"},
            )

        assert response.status_code == 201, response.text


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.usefixtures("graph")
class TestCurriculumEndpointsOnly:
    """A private entity on a curriculum route reads exactly as a missing uid."""

    @pytest.mark.parametrize(("method", "path", "form"), _curriculum_writes(PRIVATE_TASK))
    async def test_a_private_target_answers_as_a_missing_one(
        self, neo4j_driver, method: str, path: str, form: dict[str, str]
    ) -> None:
        missing_path = path.replace(PRIVATE_TASK, MISSING)
        missing_form = {k: (MISSING if v == PRIVATE_TASK else v) for k, v in form.items()}
        async with _client(neo4j_driver, _user_service()) as client:
            await client.get(f"/sign-in/{TEACHER}")
            private = await _send(client, method, path, form)
            missing = await _send(client, method, missing_path, missing_form)

        assert private.status_code == missing.status_code == 404
        assert without_timestamp(private) == without_timestamp(missing)
        assert await _lateral_edges_from(neo4j_driver, PRIVATE_TASK) == []

    @pytest.mark.parametrize(("suffix", "extra", "_rel"), CREATES, ids=CREATE_IDS)
    async def test_a_private_anchor_answers_as_a_missing_one(
        self, neo4j_driver, suffix: str, extra: dict[str, str], _rel: str
    ) -> None:
        form = {"target_uid": KU_A, **extra}
        async with _client(neo4j_driver, _user_service()) as client:
            await client.get(f"/sign-in/{TEACHER}")
            private = await client.post(f"/api/ps/{PRIVATE_TASK}/lateral/{suffix}", data=form)
            missing = await client.post(f"/api/ps/{MISSING}/lateral/{suffix}", data=form)

        assert private.status_code == missing.status_code == 404
        assert without_timestamp(private) == without_timestamp(missing)
        assert await _lateral_edges_from(neo4j_driver, PRIVATE_TASK) == []

    async def test_an_existing_edge_to_a_private_entity_is_not_removed(self, neo4j_driver) -> None:
        """An edge another writer (edge-YAML ingestion) put there stays put."""
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (a:Entity {uid: $a}), (t:Entity {uid: $t}) CREATE (a)-[:BLOCKS]->(t)",
                a=KU_A,
                t=PRIVATE_TASK,
            )
        async with _client(neo4j_driver, _user_service()) as client:
            await client.get(f"/sign-in/{TEACHER}")
            private = await client.delete(f"/api/ku/{KU_A}/lateral/blocks/{PRIVATE_TASK}")
            missing = await client.delete(f"/api/ku/{KU_A}/lateral/blocks/{MISSING}")

        assert private.status_code == missing.status_code == 404
        assert without_timestamp(private) == without_timestamp(missing)
        assert await _edges(neo4j_driver, KU_A, PRIVATE_TASK) == ["BLOCKS"]


@pytest.mark.integration
@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.usefixtures("graph")
class TestActivityRoutesUnchanged:
    """The ownership gate still decides; no role is consulted."""

    async def test_a_member_links_their_own_tasks(self, neo4j_driver) -> None:
        users = _user_service()
        async with _client(neo4j_driver, users) as client:
            await client.get(f"/sign-in/{MEMBER}")
            response = await client.post(
                f"/api/tasks/{MEMBER_TASK_A}/lateral/complementary",
                data={"target_uid": MEMBER_TASK_B, "synergy_description": "same trip"},
            )
            deleted = await client.delete(
                f"/api/tasks/{MEMBER_TASK_A}/lateral/complementary/{MEMBER_TASK_B}"
            )

        assert response.status_code == 201, response.text
        assert deleted.status_code == 200, deleted.text
        assert users.calls == []

    async def test_another_users_task_is_still_not_found(self, neo4j_driver) -> None:
        users = _user_service()
        async with _client(neo4j_driver, users) as client:
            await client.get(f"/sign-in/{MEMBER}")
            response = await client.post(
                f"/api/tasks/{MEMBER_TASK_A}/lateral/complementary",
                data={"target_uid": PRIVATE_TASK, "synergy_description": "x"},
            )

        assert response.status_code == 404
        assert await _lateral_edges_from(neo4j_driver, PRIVATE_TASK) == []
        assert users.calls == []


class TestFactoryRefusesAnUngatedSharedDomain:
    """A shared-content factory cannot be built with its writes open."""

    def test_no_verifier_and_no_role_is_refused(self) -> None:
        with pytest.raises(ValueError, match="require_role"):
            LateralRouteFactory(
                domain="ku", lateral_service=MagicMock(), entity_name="Knowledge Unit"
            )

    def test_a_role_without_a_user_service_is_refused(self) -> None:
        with pytest.raises(ValueError, match="user_service_getter"):
            LateralRouteFactory(
                domain="ku",
                lateral_service=MagicMock(),
                entity_name="Knowledge Unit",
                require_role=UserRole.TEACHER,
            )
