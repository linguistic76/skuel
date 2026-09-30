"""Curriculum lateral reads hold their anchor to curriculum.

The ku / ps / lp lateral read routes have no owner to verify, so they pass
``domain_service=None``. The anchor named in the URL must then be a Ku, a
PathStep or a LearningPath by ``entity_type``; any other uid — another user's
private task included — is answered exactly as a uid that does not exist, so a
curriculum route can neither read the neighbours of an entity its caller cannot
open nor say whether that entity is in the graph.

The contract, pinned here over real HTTP against a real Neo4j
(``tests/helpers/lateral_routes_client.py``):

- every curriculum read route answers a private anchor as a missing one — same
  status, same body — and nothing about the private entity or its neighbours
  reaches the response;
- a curriculum anchor, a draft one included, answers 200 with its edges to a
  MEMBER; reads consult no role;
- a curriculum anchor that does not exist is 404 on every read route, the
  graph route included;
- an Activity read route is decided by its ownership gate and consults no role.
"""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from neo4j import AsyncDriver

from core.models.enums import UserRole
from tests.helpers.lateral_routes_client import (
    RoleUserService,
    lateral_client,
    without_timestamp,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")

MEMBER = "user_f4b_member"
OTHER = "user_f4b_other"  # owns the private tasks; never signs in
ROLES = {MEMBER: UserRole.MEMBER, OTHER: UserRole.MEMBER}

KU_PARENT = "ku.f4b.parent"
KU_A = "ku.f4b.a"
KU_B = "ku.f4b.b"
KU_DRAFT = "ku.f4b.draft"
PS_A = "ps.f4b.a"
LP_A = "lp.f4b.a"
PRIVATE_TASK = "task_f4b_private"
PRIVATE_BLOCKER = "task_f4b_private_blocker"
PRIVATE_ALT = "task_f4b_private_alt"
MEMBER_TASK = "task_f4b_member"
MISSING = "ku.f4b.missing"
_ALL_UIDS = [
    KU_PARENT,
    KU_A,
    KU_B,
    KU_DRAFT,
    PS_A,
    LP_A,
    PRIVATE_TASK,
    PRIVATE_BLOCKER,
    PRIVATE_ALT,
    MEMBER_TASK,
]
TASK_OWNERS = {MEMBER_TASK: MEMBER, PRIVATE_TASK: OTHER, PRIVATE_BLOCKER: OTHER, PRIVATE_ALT: OTHER}

# Strings that exist only on the stranger's side of the graph. None may appear
# in any response a curriculum route gives a MEMBER.
STRANGER_STRINGS = (
    "Stranger secret",
    "Stranger blocker",
    "Stranger alternative",
    PRIVATE_BLOCKER,
    PRIVATE_ALT,
)

# The anchor each curriculum domain's routes are exercised on.
ANCHORS = {"ku": KU_A, "ps": PS_A, "lp": LP_A}

# Every read the factory registers per domain (the ten GETs).
READS = [
    "blocking",
    "blocked",
    "prerequisites",
    "alternatives",
    "complementary",
    "siblings",
    "chain",
    "alternatives/compare",
    "graph",
    "manage",
]


def _curriculum_reads(anchor_for: dict[str, str]) -> list[str]:
    """Every curriculum read route, each aimed at ``anchor_for[domain]``."""
    paths = [
        f"/api/{domain}/{anchor_for[domain]}/lateral/{suffix}"
        for domain in ANCHORS
        for suffix in READS
    ]
    paths.append(f"/api/ku/{anchor_for['ku']}/lateral/enables")
    paths.append(f"/api/ku/{anchor_for['ku']}/lateral/enabled-by")
    return paths


PRIVATE_READS = _curriculum_reads(dict.fromkeys(ANCHORS, PRIVATE_TASK))
MISSING_READS = _curriculum_reads(dict.fromkeys(ANCHORS, MISSING))
CURRICULUM_READS = _curriculum_reads(ANCHORS)


@pytest_asyncio.fixture(loop_scope="session")
async def graph(neo4j_driver):
    """Curriculum under one parent, linked to a stranger's private tasks.

    The stranger's task is blocked by a curriculum Ku AND by another private
    task, and has a private alternative — so a read anchored on it would show
    both what curriculum it links to and what else the stranger owns. The
    member's own task is blocked by the same Ku, for the Activity reads.
    """
    async with neo4j_driver.session() as session:
        await session.run(
            """
            CREATE (parent:Entity:Ku {uid: $parent, title: 'Parent', entity_type: 'ku'})
            CREATE (a:Entity:Ku {uid: $ku_a, title: 'Ku A', entity_type: 'ku'})
            CREATE (b:Entity:Ku {uid: $ku_b, title: 'Ku B', entity_type: 'ku'})
            CREATE (d:Entity:Ku {uid: $ku_draft, title: 'Ku Draft', entity_type: 'ku',
                                 publication_state: 'draft'})
            CREATE (ps:Entity:PathStep {uid: $ps_a, title: 'Step', entity_type: 'path_step'})
            CREATE (lp:Entity:LearningPath {uid: $lp_a, title: 'Path', entity_type: 'learning_path'})
            CREATE (parent)-[:ORGANIZES]->(a), (parent)-[:ORGANIZES]->(b),
                   (parent)-[:ORGANIZES]->(d),
                   (parent)-[:ORGANIZES]->(ps), (parent)-[:ORGANIZES]->(lp)
            CREATE (b)-[:BLOCKS]->(a), (a)-[:BLOCKED_BY]->(b)
            CREATE (b)-[:BLOCKS]->(d), (d)-[:BLOCKED_BY]->(b)
            CREATE (b)-[:BLOCKS]->(ps), (ps)-[:BLOCKED_BY]->(b)
            CREATE (b)-[:BLOCKS]->(lp), (lp)-[:BLOCKED_BY]->(b)
            CREATE (t:Entity:Task {uid: $private, title: 'Stranger secret', entity_type: 'task',
                                   user_uid: $other, status: 'active'})
            CREATE (tb:Entity:Task {uid: $private_blocker, title: 'Stranger blocker',
                                    entity_type: 'task', user_uid: $other, status: 'active'})
            CREATE (ta:Entity:Task {uid: $private_alt, title: 'Stranger alternative',
                                    entity_type: 'task', user_uid: $other, status: 'active'})
            CREATE (b)-[:BLOCKS]->(t), (t)-[:BLOCKED_BY]->(b)
            CREATE (tb)-[:BLOCKS]->(t), (t)-[:BLOCKED_BY]->(tb)
            CREATE (t)-[:ALTERNATIVE_TO]->(ta)
            CREATE (m:Entity:Task {uid: $member_task, title: 'Mine', entity_type: 'task',
                                   user_uid: $member, status: 'active'})
            CREATE (b)-[:BLOCKS]->(m), (m)-[:BLOCKED_BY]->(b)
            """,
            parent=KU_PARENT,
            ku_a=KU_A,
            ku_b=KU_B,
            ku_draft=KU_DRAFT,
            ps_a=PS_A,
            lp_a=LP_A,
            private=PRIVATE_TASK,
            private_blocker=PRIVATE_BLOCKER,
            private_alt=PRIVATE_ALT,
            member_task=MEMBER_TASK,
            other=OTHER,
            member=MEMBER,
        )
    yield
    async with neo4j_driver.session() as session:
        await session.run("MATCH (n:Entity) WHERE n.uid IN $uids DETACH DELETE n", uids=_ALL_UIDS)


def _client(neo4j_driver: AsyncDriver, user_service: RoleUserService) -> httpx.AsyncClient:
    return lateral_client(neo4j_driver, user_service, TASK_OWNERS, secret_key="f4b-lateral-read")


def _assert_nothing_of_the_stranger(response: httpx.Response) -> None:
    for secret in STRANGER_STRINGS:
        assert secret not in response.text, secret


@pytest.mark.integration
@pytest.mark.usefixtures("graph")
class TestPrivateAnchorAnswersAsMissing:
    @pytest.mark.parametrize(
        ("private_path", "missing_path"), list(zip(PRIVATE_READS, MISSING_READS, strict=True))
    )
    async def test_a_private_anchor_is_the_same_404_as_a_missing_one(
        self, neo4j_driver, private_path: str, missing_path: str
    ) -> None:
        async with _client(neo4j_driver, RoleUserService(ROLES)) as client:
            await client.get(f"/sign-in/{MEMBER}")
            private = await client.get(private_path)
            missing = await client.get(missing_path)

        assert private.status_code == missing.status_code == 404, private.text
        assert without_timestamp(private) == without_timestamp(missing)
        _assert_nothing_of_the_stranger(private)

    @pytest.mark.parametrize("path", MISSING_READS)
    async def test_a_missing_anchor_is_404_on_every_read(self, neo4j_driver, path: str) -> None:
        """The graph route included: a missing center is 404, not a center-only graph."""
        async with _client(neo4j_driver, RoleUserService(ROLES)) as client:
            await client.get(f"/sign-in/{MEMBER}")
            response = await client.get(path)

        assert response.status_code == 404, response.text


@pytest.mark.integration
@pytest.mark.usefixtures("graph")
class TestCurriculumAnchorReads:
    @pytest.mark.parametrize("path", CURRICULUM_READS)
    async def test_a_member_reads_every_route_on_a_curriculum_anchor(
        self, neo4j_driver, path: str
    ) -> None:
        users = RoleUserService(ROLES)
        async with _client(neo4j_driver, users) as client:
            await client.get(f"/sign-in/{MEMBER}")
            response = await client.get(path)

        assert response.status_code == 200, response.text
        assert users.calls == []

    @pytest.mark.parametrize("domain", list(ANCHORS))
    async def test_the_edges_come_back(self, neo4j_driver, domain: str) -> None:
        async with _client(neo4j_driver, RoleUserService(ROLES)) as client:
            await client.get(f"/sign-in/{MEMBER}")
            blocking = await client.get(f"/api/{domain}/{ANCHORS[domain]}/lateral/blocking")
            graph = await client.get(f"/api/{domain}/{ANCHORS[domain]}/lateral/graph")

        assert [item["target_uid"] for item in blocking.json()["blocking"]] == [KU_B]
        node_ids = {node["id"] for node in graph.json()["nodes"]}
        assert {ANCHORS[domain], KU_B} <= node_ids

    async def test_a_draft_anchor_answers(self, neo4j_driver) -> None:
        """A by-UID read is anchored: the caller named the draft, so it comes back."""
        async with _client(neo4j_driver, RoleUserService(ROLES)) as client:
            await client.get(f"/sign-in/{MEMBER}")
            blocking = await client.get(f"/api/ku/{KU_DRAFT}/lateral/blocking")
            chain = await client.get(f"/api/ku/{KU_DRAFT}/lateral/chain")

        assert blocking.status_code == 200, blocking.text
        assert [item["target_uid"] for item in blocking.json()["blocking"]] == [KU_B]
        assert chain.status_code == 200, chain.text

    async def test_a_curriculum_graph_reaches_the_task_it_blocks(self, neo4j_driver) -> None:
        """Ku B blocks the stranger's task; a graph centred on Ku B reaches it.

        The traversal is not audience-filtered (its scope is on record in
        RELATIONSHIPS_ARCHITECTURE.md § Ownership Coverage); this pins the
        current reach so a change to it is a decision, not a side effect.
        """
        async with _client(neo4j_driver, RoleUserService(ROLES)) as client:
            await client.get(f"/sign-in/{MEMBER}")
            response = await client.get(f"/api/ku/{KU_B}/lateral/graph?depth=1")

        assert response.status_code == 200, response.text
        assert PRIVATE_TASK in {node["id"] for node in response.json()["nodes"]}


@pytest.mark.integration
@pytest.mark.usefixtures("graph")
class TestActivityReadsOwnerGated:
    """The ownership gate decides an Activity read; no role is consulted."""

    async def test_a_member_reads_their_own_task(self, neo4j_driver) -> None:
        users = RoleUserService(ROLES)
        async with _client(neo4j_driver, users) as client:
            await client.get(f"/sign-in/{MEMBER}")
            blocking = await client.get(f"/api/tasks/{MEMBER_TASK}/lateral/blocking")
            graph = await client.get(f"/api/tasks/{MEMBER_TASK}/lateral/graph")

        assert blocking.status_code == 200, blocking.text
        assert [item["target_uid"] for item in blocking.json()["blocking"]] == [KU_B]
        assert graph.status_code == 200, graph.text
        assert users.calls == []

    @pytest.mark.parametrize("suffix", READS)
    async def test_another_users_task_is_the_same_404_as_a_missing_one(
        self, neo4j_driver, suffix: str
    ) -> None:
        users = RoleUserService(ROLES)
        async with _client(neo4j_driver, users) as client:
            await client.get(f"/sign-in/{MEMBER}")
            private = await client.get(f"/api/tasks/{PRIVATE_TASK}/lateral/{suffix}")
            missing = await client.get(f"/api/tasks/{MISSING}/lateral/{suffix}")

        assert private.status_code == missing.status_code == 404, private.text
        assert without_timestamp(private) == without_timestamp(missing)
        _assert_nothing_of_the_stranger(private)
        assert users.calls == []
