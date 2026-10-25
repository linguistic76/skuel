"""The lateral traversals return only what their caller may see.

The graph, the blocking chain and the alternatives comparison each walk out
from an anchor the route has already admitted (owned, or curriculum). Every
node on every path they return — not only the end node: an intermediate uid
rides the graph's edge list as ``from`` / ``to`` — is curriculum (published;
the anchor alone may be a draft, because the caller named it) or an entity the
caller owns. A ``User`` node is never one, and neither is another user's
entity, whichever relationship types ``?types=`` names.

Pinned over real HTTP against a real Neo4j (``tests/helpers/lateral_routes_client.py``),
with the stranger's side seeded as the create doors write it (``user_uid`` and
the ``OWNS`` edge).
"""

from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from neo4j import AsyncDriver

from core.models.relationship_names import RelationshipName
from core.models.type_hints import EntityUID
from core.services.lateral_relationships.lateral_relationship_service import (
    LateralRelationshipService,
)
from tests.helpers.lateral_routes_client import lateral_client
from tests.helpers.production_backends import build_production_backends
from tests.helpers.seed_uids import seed_user_uid

pytestmark = pytest.mark.asyncio(loop_scope="session")

MEMBER = seed_user_uid("lta_member")
STRANGER = seed_user_uid("lta_stranger")
MEMBER_NAME = "lta_member_name"
STRANGER_NAME = "lta_stranger_name"

STEP = "ps.lta.step"
KU = "ku.lta.shared"
KU_NEIGHBOUR = "ku.lta.neighbour"  # blocks KU — the curriculum control
KU_BEYOND = "ku.lta.beyond"  # reached from KU only through the stranger's entry
KU_DRAFT = "ku.lta.draft"
KU_ALT = "ku.lta.alt"
KU_CHAIN_ROOT = "ku.lta.chain-root"  # blocks KU only through the stranger's task

MEMBER_TASK = "task.lta-member"
MEMBER_TASK_2 = "task.lta-member-two"
MEMBER_GOAL = "goal.lta-member"
STRANGER_TASK = "task.lta-stranger"
STRANGER_GOAL = "goal.lta-stranger"
STRANGER_ENTRY = "ue.lta-stranger"

_ENTITY_UIDS = [
    STEP,
    KU,
    KU_NEIGHBOUR,
    KU_BEYOND,
    KU_DRAFT,
    KU_ALT,
    KU_CHAIN_ROOT,
    MEMBER_TASK,
    MEMBER_TASK_2,
    MEMBER_GOAL,
    STRANGER_TASK,
    STRANGER_GOAL,
    STRANGER_ENTRY,
]
TASK_OWNERS = {MEMBER_TASK: MEMBER, MEMBER_TASK_2: MEMBER}

# Everything that exists only on the stranger's side, plus every User node —
# the member's own included. None may appear in any traversal response.
NEVER_SEEN = (
    STRANGER,
    STRANGER_NAME,
    MEMBER_NAME,
    STRANGER_TASK,
    STRANGER_GOAL,
    STRANGER_ENTRY,
    "Stranger task secret",
    "Stranger goal secret",
    "Stranger journal secret",
)


@pytest_asyncio.fixture(loop_scope="session")
async def graph(neo4j_driver):
    """Shared curriculum touched by both users, the stranger as the doors write them."""
    async with neo4j_driver.session() as session:
        await session.run(
            """
            CREATE (member:User {uid: $member, title: $member_name, username: $member_name})
            CREATE (stranger:User {uid: $stranger, title: $stranger_name,
                                   username: $stranger_name})
            CREATE (step:Entity:PathStep {uid: $step, title: 'Shared step',
                                          entity_type: 'path_step'})
            CREATE (ku:Entity:Ku {uid: $ku, title: 'Shared ku', entity_type: 'ku'})
            CREATE (nb:Entity:Ku {uid: $ku_neighbour, title: 'Neighbour ku', entity_type: 'ku'})
            CREATE (beyond:Entity:Ku {uid: $ku_beyond, title: 'Beyond ku', entity_type: 'ku'})
            CREATE (draft:Entity:Ku {uid: $ku_draft, title: 'Draft ku', entity_type: 'ku',
                                     publication_state: 'draft'})
            CREATE (alt:Entity:Ku {uid: $ku_alt, title: 'Alternative ku', entity_type: 'ku'})
            CREATE (root:Entity:Ku {uid: $ku_chain_root, title: 'Chain root ku',
                                    entity_type: 'ku'})

            CREATE (mt:Entity:Task {uid: $member_task, title: 'My task', entity_type: 'task',
                                    user_uid: $member, status: 'active'})
            CREATE (mt2:Entity:Task {uid: $member_task_2, title: 'My other task',
                                     entity_type: 'task', user_uid: $member, status: 'active'})
            CREATE (mg:Entity:Goal {uid: $member_goal, title: 'My goal', entity_type: 'goal',
                                    user_uid: $member, status: 'active'})
            CREATE (member)-[:OWNS]->(mt), (member)-[:OWNS]->(mt2), (member)-[:OWNS]->(mg)

            CREATE (st:Entity:Task {uid: $stranger_task, title: 'Stranger task secret',
                                    entity_type: 'task', user_uid: $stranger,
                                    status: 'active'})
            CREATE (sg:Entity:Goal {uid: $stranger_goal, title: 'Stranger goal secret',
                                    entity_type: 'goal', user_uid: $stranger,
                                    status: 'active'})
            CREATE (se:Entity:UserEntry {uid: $stranger_entry, title: 'Stranger journal secret',
                                         entity_type: 'user_entry', user_uid: $stranger,
                                         status: 'completed'})
            CREATE (stranger)-[:OWNS]->(st), (stranger)-[:OWNS]->(sg), (stranger)-[:OWNS]->(se)

            // Learner state and knowledge links, both users
            CREATE (stranger)-[:VIEWED]->(step), (member)-[:VIEWED]->(step)
            CREATE (se)-[:APPLIES_KNOWLEDGE]->(ku), (se)-[:APPLIES_KNOWLEDGE]->(beyond)
            CREATE (mt)-[:APPLIES_KNOWLEDGE]->(ku)
            CREATE (sg)-[:REQUIRES_KNOWLEDGE]->(step), (mg)-[:REQUIRES_KNOWLEDGE]->(step)
            CREATE (ku)-[:ENABLES_KNOWLEDGE]->(step), (ku)-[:ENABLES_KNOWLEDGE]->(draft)

            // Lateral edges (curriculum ones as the content vault writes them)
            CREATE (nb)-[:BLOCKS]->(ku), (ku)-[:BLOCKED_BY]->(nb)
            CREATE (ku)-[:BLOCKS]->(st), (st)-[:BLOCKED_BY]->(ku)
            CREATE (ku)-[:BLOCKS]->(mt), (mt)-[:BLOCKED_BY]->(ku)
            CREATE (draft)-[:BLOCKS]->(ku), (ku)-[:BLOCKED_BY]->(draft)
            CREATE (root)-[:BLOCKS]->(st)
            CREATE (st)-[:BLOCKS]->(ku)
            CREATE (mt2)-[:BLOCKS]->(mt), (mt)-[:BLOCKED_BY]->(mt2)
            CREATE (ku)-[:ALTERNATIVE_TO]->(alt)
            CREATE (ku)-[:ALTERNATIVE_TO]->(st)
            CREATE (ku)-[:ALTERNATIVE_TO]->(draft)
            """,
            member=MEMBER,
            member_name=MEMBER_NAME,
            stranger=STRANGER,
            stranger_name=STRANGER_NAME,
            step=STEP,
            ku=KU,
            ku_neighbour=KU_NEIGHBOUR,
            ku_beyond=KU_BEYOND,
            ku_draft=KU_DRAFT,
            ku_alt=KU_ALT,
            ku_chain_root=KU_CHAIN_ROOT,
            member_task=MEMBER_TASK,
            member_task_2=MEMBER_TASK_2,
            member_goal=MEMBER_GOAL,
            stranger_task=STRANGER_TASK,
            stranger_goal=STRANGER_GOAL,
            stranger_entry=STRANGER_ENTRY,
        )
    yield
    async with neo4j_driver.session() as session:
        await session.run(
            "MATCH (n) WHERE (n:Entity AND n.uid IN $uids) OR (n:User AND n.uid IN $users) "
            "DETACH DELETE n",
            uids=_ENTITY_UIDS,
            users=[MEMBER, STRANGER],
        )


def _client(neo4j_driver: AsyncDriver) -> httpx.AsyncClient:
    return lateral_client(neo4j_driver, TASK_OWNERS, secret_key="lateral-traversal-audience")


async def _get_as_member(neo4j_driver: AsyncDriver, path: str) -> httpx.Response:
    async with _client(neo4j_driver) as client:
        await client.get(f"/sign-in/{MEMBER}")
        response = await client.get(path)
    assert response.status_code == 200, response.text
    return response


def _assert_never_seen(response: httpx.Response) -> None:
    for secret in NEVER_SEEN:
        assert secret not in response.text, secret


def _graph_ids(response: httpx.Response) -> tuple[set[str], set[str]]:
    """The node ids, and every uid an edge names at either end."""
    body = response.json()
    nodes = {node["id"] for node in body["nodes"]}
    ends = {edge["from"] for edge in body["edges"]} | {edge["to"] for edge in body["edges"]}
    return nodes, ends


GRAPH_PROBES = [
    pytest.param(f"/api/ps/{STEP}/lateral/graph?types=VIEWED&depth=1", id="ps-viewed-1"),
    pytest.param(f"/api/ps/{STEP}/lateral/graph?types=VIEWED,OWNS&depth=2", id="ps-viewed-owns-2"),
    pytest.param(f"/api/ku/{KU}/lateral/graph?types=APPLIES_KNOWLEDGE&depth=1", id="ku-applies-1"),
    pytest.param(
        f"/api/ku/{KU}/lateral/graph?types=APPLIES_KNOWLEDGE,OWNS&depth=3",
        id="ku-applies-owns-3",
    ),
    pytest.param(f"/api/ku/{KU}/lateral/graph?depth=3", id="ku-default-types-3"),
    pytest.param(
        f"/api/tasks/{MEMBER_TASK}/lateral/graph?types=APPLIES_KNOWLEDGE,OWNS&depth=3",
        id="task-through-shared-ku-3",
    ),
    pytest.param(
        f"/api/ps/{STEP}/lateral/graph?types=REQUIRES_KNOWLEDGE,ENABLES_KNOWLEDGE&depth=3",
        id="ps-knowledge-dependency-3",
    ),
]


@pytest.mark.integration
@pytest.mark.usefixtures("graph")
class TestGraphAudience:
    @pytest.mark.parametrize("path", GRAPH_PROBES)
    async def test_no_user_node_and_nothing_of_the_strangers(self, neo4j_driver, path: str) -> None:
        response = await _get_as_member(neo4j_driver, path)

        _assert_never_seen(response)
        nodes, ends = _graph_ids(response)
        assert ends <= nodes, ends - nodes

    async def test_a_node_reached_only_through_a_strangers_entity_is_not_returned(
        self, neo4j_driver
    ) -> None:
        """The stranger's entry joins KU to KU_BEYOND; the path is withheld whole."""
        response = await _get_as_member(
            neo4j_driver, f"/api/ku/{KU}/lateral/graph?types=APPLIES_KNOWLEDGE&depth=2"
        )

        nodes, _ = _graph_ids(response)
        assert KU_BEYOND not in nodes
        assert MEMBER_TASK in nodes  # control: the member's own link survives

    async def test_the_members_own_task_and_curriculum_come_back(self, neo4j_driver) -> None:
        """Control: the filter withholds strangers, not the graph."""
        response = await _get_as_member(neo4j_driver, f"/api/ku/{KU}/lateral/graph?depth=2")

        nodes, _ = _graph_ids(response)
        assert {KU, KU_NEIGHBOUR, MEMBER_TASK, MEMBER_TASK_2} <= nodes

    async def test_the_activity_centre_reaches_curriculum_and_its_own(self, neo4j_driver) -> None:
        response = await _get_as_member(
            neo4j_driver,
            f"/api/tasks/{MEMBER_TASK}/lateral/graph?types=APPLIES_KNOWLEDGE,BLOCKS&depth=3",
        )

        nodes, _ = _graph_ids(response)
        assert {MEMBER_TASK, KU, MEMBER_TASK_2, KU_NEIGHBOUR} <= nodes
        _assert_never_seen(response)

    async def test_the_knowledge_dependency_view_is_curriculum_plus_my_own(
        self, neo4j_driver
    ) -> None:
        response = await _get_as_member(
            neo4j_driver,
            f"/api/ps/{STEP}/lateral/graph?types=REQUIRES_KNOWLEDGE,ENABLES_KNOWLEDGE&depth=1",
        )

        nodes, _ = _graph_ids(response)
        assert nodes == {STEP, KU, MEMBER_GOAL}

    async def test_a_draft_is_withheld_as_a_far_node(self, neo4j_driver) -> None:
        response = await _get_as_member(neo4j_driver, f"/api/ku/{KU}/lateral/graph?depth=1")

        nodes, _ = _graph_ids(response)
        assert KU_DRAFT not in nodes
        assert "Draft ku" not in response.text

    async def test_a_draft_centre_still_draws_its_neighbours(self, neo4j_driver) -> None:
        """The caller named the draft, so it comes back with what it reaches."""
        response = await _get_as_member(neo4j_driver, f"/api/ku/{KU_DRAFT}/lateral/graph?depth=1")

        nodes, _ = _graph_ids(response)
        assert {KU_DRAFT, KU} <= nodes


@pytest.mark.integration
@pytest.mark.usefixtures("graph")
class TestChainAudience:
    async def test_the_chain_names_no_strangers_blocker(self, neo4j_driver) -> None:
        response = await _get_as_member(neo4j_driver, f"/api/ku/{KU}/lateral/chain")

        _assert_never_seen(response)
        assert "Neighbour ku" in response.text  # control

    async def test_a_blocker_reached_only_through_a_strangers_task_is_not_named(
        self, neo4j_driver
    ) -> None:
        response = await _get_as_member(neo4j_driver, f"/api/ku/{KU}/lateral/chain")

        assert "Chain root ku" not in response.text
        assert "Draft ku" not in response.text

    async def test_an_activity_chain_keeps_the_members_own_blockers(self, neo4j_driver) -> None:
        response = await _get_as_member(neo4j_driver, f"/api/tasks/{MEMBER_TASK}/lateral/chain")

        assert "My other task" in response.text
        assert "Shared ku" in response.text
        assert "Neighbour ku" in response.text
        _assert_never_seen(response)

    async def test_a_blockers_count_names_only_what_the_caller_may_see(self, neo4j_driver) -> None:
        """KU blocks the member's task and the stranger's; its count is one."""
        response = await _get_as_member(neo4j_driver, f"/api/tasks/{MEMBER_TASK}/lateral/chain")

        assert "Blocks 1 entities" in response.text
        assert "Blocks 2 entities" not in response.text


@pytest.mark.integration
@pytest.mark.usefixtures("graph")
class TestComparisonAudience:
    async def test_the_comparison_names_no_strangers_alternative(self, neo4j_driver) -> None:
        response = await _get_as_member(neo4j_driver, f"/api/ku/{KU}/lateral/alternatives/compare")

        _assert_never_seen(response)
        assert "Draft ku" not in response.text
        assert "Alternative ku" in response.text  # control


@pytest.mark.integration
@pytest.mark.usefixtures("graph")
class TestNoUserFailsClosed:
    """The service takes ``user_uid=None``; with no caller, only published curriculum."""

    @pytest.fixture
    def service(self, neo4j_driver) -> LateralRelationshipService:
        return LateralRelationshipService(
            build_production_backends(neo4j_driver)["lateral_relationship_backend"]
        )

    async def test_graph(self, service: LateralRelationshipService) -> None:
        result = await service.get_relationship_graph(
            EntityUID(KU),
            depth=3,
            relationship_types=[
                RelationshipName.APPLIES_KNOWLEDGE,
                RelationshipName.OWNS,
                RelationshipName.BLOCKS,
            ],
        )

        assert not result.is_error
        nodes = {node["id"] for node in result.value["nodes"]}
        assert nodes == {KU, KU_NEIGHBOUR}

    async def test_chain(self, service: LateralRelationshipService) -> None:
        result = await service.get_blocking_chain(EntityUID(KU))

        assert not result.is_error
        names = {e["uid"] for level in result.value["levels"] for e in level["entities"]}
        assert names == {KU_NEIGHBOUR}

    async def test_comparison(self, service: LateralRelationshipService) -> None:
        result = await service.get_alternatives_with_comparison(EntityUID(KU))

        assert not result.is_error
        assert [alt["uid"] for alt in result.value] == [KU_ALT]
