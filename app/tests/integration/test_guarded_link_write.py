"""The guarded link write, and the uid-bound endpoint and anchor reads — on a real graph.

``write_guarded_links`` (``_RelationshipCrudMixin``) is the write every
``UnifiedRelationshipService`` link goes through. Its statement re-asserts the link-edge
guard's rule as it merges the edge: the far end is an entity of an allowed kind, owned
by one of the anchor's owners, or by nobody and published. A far end that fails it
refuses the whole call — the writes share one transaction — and a replace deletes the
anchor's other edges of the type in the statement that writes the new ones.

The endpoint reads (``get_node_labels_batch`` / ``get_owner_uids_batch``) and the anchor
reads (``get_related_uids`` / ``count_related``) bind a uid under ``:Entity``, ``:User``,
``:Group`` and the backend's own label — index seeks — and still tell a User or a Group
apart from a uid that names nothing.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.universal_backend import UniversalNeo4jBackend
from core.config.credential_store import get_credential
from core.config.intelligence_tier import IntelligenceTier
from core.models.entity import Entity
from core.models.enums.neo_labels import NeoLabel
from core.models.habit.completion import HabitCompletion
from core.models.link_write_contracts import GuardedLinkWrite
from core.models.relationship_names import RelationshipName

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from neo4j import AsyncDriver

pytestmark = [
    pytest.mark.asyncio(loop_scope="session"),
    pytest.mark.skipif(
        IntelligenceTier.from_env().ai_enabled and not get_credential("OPENAI_API_KEY"),
        reason="FULL tier cannot bootstrap without OPENAI_API_KEY — run with INTELLIGENCE_TIER=core",
    ),
]

MARK = "zzzguardedlink"
ALICE = f"user_{MARK}_alice"
BOB = f"user_{MARK}_bob"

GOAL = f"goal_{MARK}_alice"
GOAL_SHARED_SOURCE = f"goal_{MARK}_nobodys"  # a goal nobody owns
HABIT = f"habit_{MARK}_alice"
HABIT_TWO = f"habit_{MARK}_alice_two"
HABIT_BOB = f"habit_{MARK}_bob"
HABIT_CONTESTED = f"habit_{MARK}_contested"
KU = f"ku_{MARK}_published"
KU_DRAFT = f"ku_{MARK}_draft"
GROUP = f"group_{MARK}"
SESSION = f"session_{MARK}"
COMPLETION = f"completion_{MARK}"
MISSING = f"habit_{MARK}_names_nothing"

ALICES = frozenset({ALICE})
NOBODY: frozenset[str] = frozenset()

REINFORCES_HABIT = RelationshipName.REINFORCES_HABIT
REQUIRES_KNOWLEDGE = RelationshipName.REQUIRES_KNOWLEDGE
HABITS = frozenset({NeoLabel.HABIT.value})
KUS = frozenset({NeoLabel.KU.value})


async def _run(driver: AsyncDriver, query: str, **params: Any) -> None:  # boundary: Cypher params
    async with driver.session() as session:
        await session.run(query, **params)


async def _wipe(driver: AsyncDriver) -> None:
    await _run(driver, "MATCH (n) WHERE n.uid CONTAINS $mark DETACH DELETE n", mark=MARK)


async def _owned(driver: AsyncDriver, label: str, uid: str, owner: str) -> None:
    """An entity as the create doors write it: the label pair, ``user_uid`` and ``:OWNS``."""
    await _run(
        driver,
        f"""
        MATCH (u:User {{uid: $owner}})
        CREATE (e:Entity:{label} {{uid: $uid, title: $uid, user_uid: $owner,
                                   entity_type: $entity_type, status: 'active'}})
        CREATE (u)-[:OWNS]->(e)
        """,
        uid=uid,
        owner=owner,
        entity_type=label.lower(),
    )


@pytest_asyncio.fixture(loop_scope="session")
async def graph(skuel_app: Any) -> AsyncIterator[AsyncDriver]:  # boundary: fasthtml-app
    driver: AsyncDriver = skuel_app.state.services.neo4j_driver
    await _wipe(driver)
    for user in (ALICE, BOB):
        await _run(driver, "CREATE (:User {uid: $uid, title: $uid})", uid=user)
    await _owned(driver, "Goal", GOAL, ALICE)
    await _owned(driver, "Habit", HABIT, ALICE)
    await _owned(driver, "Habit", HABIT_TWO, ALICE)
    await _owned(driver, "Habit", HABIT_BOB, BOB)
    await _run(
        driver,
        """
        CREATE (:Entity:Goal {uid: $nobodys, title: $nobodys, entity_type: 'goal'})
        CREATE (:Entity:Ku {uid: $ku, title: $ku, entity_type: 'ku',
                            publication_state: 'published'})
        CREATE (:Entity:Ku {uid: $draft, title: $draft, entity_type: 'ku',
                            publication_state: 'draft'})
        CREATE (:Content {uid: $ku})
        WITH 1 AS one
        MATCH (alice:User {uid: $alice})
        CREATE (g:Group {uid: $group, title: $group, owner_uid: $alice})
        CREATE (alice)-[:OWNS]->(g)
        CREATE (:Session {uid: $session, user_uid: $alice})
        CREATE (alice)-[:OWNS]->(:HabitCompletion {uid: $completion, user_uid: $alice})
        """,
        nobodys=GOAL_SHARED_SOURCE,
        ku=KU,
        draft=KU_DRAFT,
        alice=ALICE,
        group=GROUP,
        session=SESSION,
        completion=COMPLETION,
    )
    yield driver
    await _wipe(driver)


@pytest.fixture
def backend(graph: AsyncDriver) -> UniversalNeo4jBackend[Entity]:
    return UniversalNeo4jBackend[Entity](graph, NeoLabel.ENTITY, Entity, base_label=NeoLabel.ENTITY)


async def _links(driver: AsyncDriver, source: str) -> set[tuple[str, str]]:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (:Entity {uid: $uid})-[r]->(far) RETURN type(r) AS type, far.uid AS far",
            uid=source,
        )
        return {(row["type"], row["far"]) async for row in result}


async def _clear_links(driver: AsyncDriver) -> None:
    await _run(
        driver,
        "MATCH (a:Entity)-[r]->(:Entity) WHERE a.uid CONTAINS $mark DELETE r",
        mark=MARK,
    )


def _habits(*uids: str, replace: bool = False) -> GuardedLinkWrite:
    return GuardedLinkWrite(
        far_uids=uids,
        relationship=REINFORCES_HABIT,
        anchor_is_source=True,
        far_labels=HABITS,
        replace=replace,
        replace_label=NeoLabel.HABIT if replace else None,
    )


def _knowledge(*uids: str) -> GuardedLinkWrite:
    return GuardedLinkWrite(
        far_uids=uids,
        relationship=REQUIRES_KNOWLEDGE,
        anchor_is_source=True,
        far_labels=KUS,
        properties={"priority": 1},
    )


class TestTheWriteReassertsTheRule:
    async def test_the_owners_entity_and_published_shared_content_are_linked(
        self, graph: AsyncDriver, backend: UniversalNeo4jBackend[Entity]
    ) -> None:
        await _clear_links(graph)

        outcome = await backend.write_guarded_links(
            GOAL, [_habits(HABIT), _knowledge(KU)], anchor_owners=ALICES
        )

        assert outcome.is_ok
        assert outcome.value.refused_uid is None
        assert outcome.value.anchor_owners == frozenset({ALICE})
        assert await _links(graph, GOAL) == {
            (REINFORCES_HABIT.value, HABIT),
            (REQUIRES_KNOWLEDGE.value, KU),
        }

    @pytest.mark.parametrize(
        "write",
        [
            _habits(HABIT_BOB),  # another user's
            _habits(KU),  # the wrong kind
            _knowledge(KU_DRAFT),  # unpublished shared content
            _habits(MISSING),  # names nothing
            _habits(GROUP),  # a node outside :Entity
        ],
        ids=["cross-user", "wrong-kind", "draft", "missing", "not-an-entity"],
    )
    async def test_a_far_end_the_rule_refuses_writes_nothing(
        self, graph: AsyncDriver, backend: UniversalNeo4jBackend[Entity], write: GuardedLinkWrite
    ) -> None:
        await _clear_links(graph)

        outcome = await backend.write_guarded_links(
            GOAL, [_habits(HABIT), write], anchor_owners=ALICES
        )

        assert outcome.is_ok
        assert outcome.value.refused_uid == write.far_uids[0]
        # The first write was in the same transaction: rolled back with the refusal.
        assert await _links(graph, GOAL) == set()

    async def test_a_source_nobody_owns_links_shared_content_only(
        self, graph: AsyncDriver, backend: UniversalNeo4jBackend[Entity]
    ) -> None:
        await _clear_links(graph)

        refused = await backend.write_guarded_links(
            GOAL_SHARED_SOURCE, [_habits(HABIT)], anchor_owners=NOBODY
        )
        linked = await backend.write_guarded_links(
            GOAL_SHARED_SOURCE, [_knowledge(KU)], anchor_owners=NOBODY
        )

        assert refused.value.refused_uid == HABIT
        assert linked.value.refused_uid is None
        assert await _links(graph, GOAL_SHARED_SOURCE) == {(REQUIRES_KNOWLEDGE.value, KU)}

    async def test_an_anchor_that_names_nothing_is_refused(
        self, backend: UniversalNeo4jBackend[Entity]
    ) -> None:
        outcome = await backend.write_guarded_links(MISSING, [_habits(HABIT)], anchor_owners=NOBODY)

        assert outcome.value.refused_uid == MISSING


class TestTheWriteReadsUnderTheFarEndsLock:
    async def test_a_far_end_re_owned_by_a_transaction_in_flight_is_refused(
        self, graph: AsyncDriver, backend: UniversalNeo4jBackend[Entity]
    ) -> None:
        """Another writer holds the far end, re-owning it, when the write starts: the
        write waits for that transaction and reads what it committed — Bob's habit."""
        await _clear_links(graph)
        await _owned(graph, "Habit", HABIT_CONTESTED, ALICE)
        async with graph.session() as session:
            other = await session.begin_transaction()
            await other.run(
                """
                MATCH (alice:User {uid: $alice})-[owns:OWNS]->(h:Entity {uid: $habit})
                MATCH (bob:User {uid: $bob})
                DELETE owns
                SET h.user_uid = $bob
                CREATE (bob)-[:OWNS]->(h)
                """,
                alice=ALICE,
                bob=BOB,
                habit=HABIT_CONTESTED,
            )
            write = asyncio.create_task(
                backend.write_guarded_links(GOAL, [_habits(HABIT_CONTESTED)], anchor_owners=ALICES)
            )
            await asyncio.sleep(1)
            assert not write.done(), "the write waits for the transaction holding its far end"
            await other.commit()
            outcome = await write

        assert outcome.is_ok
        assert outcome.value.refused_uid == HABIT_CONTESTED
        assert await _links(graph, GOAL) == set()

    async def test_control_a_far_end_left_alone_in_flight_is_linked(
        self, graph: AsyncDriver, backend: UniversalNeo4jBackend[Entity]
    ) -> None:
        """The same wait, with the other transaction touching the far end but not its owner."""
        await _clear_links(graph)
        async with graph.session() as session:
            other = await session.begin_transaction()
            await other.run("MATCH (h:Entity {uid: $habit}) SET h.title = 'renamed'", habit=HABIT)
            write = asyncio.create_task(
                backend.write_guarded_links(GOAL, [_habits(HABIT)], anchor_owners=ALICES)
            )
            await asyncio.sleep(1)
            await other.commit()
            outcome = await write

        assert outcome.value.refused_uid is None
        assert await _links(graph, GOAL) == {(REINFORCES_HABIT.value, HABIT)}


class TestTheWriteIsBoundToTheAdmittedOwners:
    async def test_an_anchor_owned_by_someone_else_than_admitted_writes_nothing(
        self, graph: AsyncDriver, backend: UniversalNeo4jBackend[Entity]
    ) -> None:
        """Admitted as Alice's goal; the goal is Bob's (or shared) at the write."""
        await _clear_links(graph)

        bob = await backend.write_guarded_links(
            GOAL, [_knowledge(KU)], anchor_owners=frozenset({BOB})
        )
        shared = await backend.write_guarded_links(GOAL, [_knowledge(KU)], anchor_owners=NOBODY)

        assert bob.value.refused_uid == GOAL
        assert shared.value.refused_uid == GOAL
        assert await _links(graph, GOAL) == set()


class TestAReplaceIsOneStatement:
    async def test_a_replace_removes_the_old_edge_and_writes_the_new(
        self, graph: AsyncDriver, backend: UniversalNeo4jBackend[Entity]
    ) -> None:
        await _clear_links(graph)
        await backend.write_guarded_links(
            GOAL, [_habits(HABIT), _knowledge(KU)], anchor_owners=ALICES
        )

        outcome = await backend.write_guarded_links(
            GOAL, [_habits(HABIT_TWO, replace=True)], anchor_owners=ALICES
        )

        assert outcome.value.refused_uid is None
        # The knowledge edge is another type: a habit replace leaves it alone.
        assert await _links(graph, GOAL) == {
            (REINFORCES_HABIT.value, HABIT_TWO),
            (REQUIRES_KNOWLEDGE.value, KU),
        }

    async def test_a_refused_replace_keeps_the_old_edge(
        self, graph: AsyncDriver, backend: UniversalNeo4jBackend[Entity]
    ) -> None:
        await _clear_links(graph)
        await backend.write_guarded_links(GOAL, [_habits(HABIT)], anchor_owners=ALICES)

        outcome = await backend.write_guarded_links(
            GOAL, [_habits(HABIT_BOB, replace=True)], anchor_owners=ALICES
        )

        assert outcome.value.refused_uid == HABIT_BOB
        assert await _links(graph, GOAL) == {(REINFORCES_HABIT.value, HABIT)}

    async def test_an_empty_replace_clears_the_type(
        self, graph: AsyncDriver, backend: UniversalNeo4jBackend[Entity]
    ) -> None:
        await _clear_links(graph)
        await backend.write_guarded_links(
            GOAL, [_habits(HABIT, HABIT_TWO), _knowledge(KU)], anchor_owners=ALICES
        )

        outcome = await backend.write_guarded_links(
            GOAL, [_habits(replace=True)], anchor_owners=ALICES
        )

        assert outcome.value.refused_uid is None
        assert await _links(graph, GOAL) == {(REQUIRES_KNOWLEDGE.value, KU)}


class TestTheUidBoundReads:
    async def test_the_labels_read_sees_an_entity_a_user_and_a_group(
        self, backend: UniversalNeo4jBackend[Entity]
    ) -> None:
        labels = await backend.get_node_labels_batch([HABIT, ALICE, GROUP, KU, SESSION, MISSING])

        assert labels.is_ok
        assert {uid: sorted(found) for uid, found in labels.value.items()} == {
            HABIT: ["Entity", "Habit"],
            ALICE: ["User"],
            GROUP: ["Group"],
            # The :Content shadow sharing the Ku's uid is not read.
            KU: ["Entity", "Ku"],
            # A node outside :Entity, :User and :Group reads as no node, as MISSING does.
        }

    async def test_the_owners_read_spells_ownership_three_ways(
        self, backend: UniversalNeo4jBackend[Entity]
    ) -> None:
        owners = await backend.get_owner_uids_batch([HABIT, GROUP, KU, MISSING])

        assert owners.is_ok
        assert {uid: sorted(set(found)) for uid, found in owners.value.items()} == {
            HABIT: [ALICE],
            GROUP: [ALICE],
        }

    async def test_an_anchor_read_binds_a_user(
        self, backend: UniversalNeo4jBackend[Entity]
    ) -> None:
        owned = await backend.get_related_uids(ALICE, RelationshipName.OWNS, "outgoing")
        counted = await backend.count_related(
            ALICE, RelationshipName.OWNS, "outgoing", target_label=NeoLabel.HABIT
        )

        assert owned.is_ok
        assert {HABIT, HABIT_TWO} <= set(owned.value)
        assert counted.value == 2

    async def test_an_anchor_read_binds_the_backends_own_label(self, graph: AsyncDriver) -> None:
        completions = UniversalNeo4jBackend[HabitCompletion](
            graph, NeoLabel.HABIT_COMPLETION, HabitCompletion
        )
        entities = UniversalNeo4jBackend[Entity](
            graph, NeoLabel.ENTITY, Entity, base_label=NeoLabel.ENTITY
        )

        own = await completions.count_related(COMPLETION, RelationshipName.OWNS, "incoming")
        other = await entities.count_related(COMPLETION, RelationshipName.OWNS, "incoming")

        assert own.value == 1
        # Through a backend of another label a HabitCompletion is no anchor.
        assert other.value == 0
