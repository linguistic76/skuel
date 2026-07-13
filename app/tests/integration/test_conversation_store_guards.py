"""
Discussion-store integration guards — live Neo4j (ADR-078 §7 guards 1, 2, 6).
=============================================================================

The unit suite (``tests/unit/conversation/``) locks the *shape* of the store —
owner-scoped Cypher, standalone thin backend, no EntityType membership. Those are
CI-runnable source/structure checks. This module supplies the three guards ADR-078
§7 marks **integration**, which only a real graph can prove because they are
statements about *what actually lands in Neo4j*:

1. **Owner-visibility symmetry** — every session a user owns appears in that
   user's ``list_sessions``; a session owned by someone else is absent from that
   list AND a direct ``get_session`` / ``get_turns`` for it returns not-found
   (the service layer of the 404-not-403 convention).
2. **Delete completeness** — ``delete_session`` removes the ``:ConversationSession``
   AND every one of its ``:ConversationTurn`` nodes (zero orphans), and it vanishes
   from ``list_sessions``.
6. **No enrichment edges** — after a create + one follow-up exchange, there are
   ZERO ``MENTIONS`` / enrichment / ``APPLIES_KNOWLEDGE`` edges — indeed zero edges
   of any kind — from any ``:ConversationTurn`` to any ``:Entity``. The store is
   understanding-agnostic by construction (ADR-078 §2); this proves it against the
   live graph, not just the source.

These drive the REAL ``ConversationService`` + ``ConversationBackend`` against the
session-scoped Docker Neo4j container (``tests/integration/conftest.py``). The
store is CORE-safe — no LLM, no embeddings — so nothing here needs API keys.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.conversation_backend import ConversationBackend
from core.models.conversation import CONVERSATION_KIND_DISCUSSION, ROLE_ASSISTANT, ROLE_USER
from core.services.conversation import ConversationService
from core.utils.result_simplified import ErrorCategory

# Two distinct owners — the whole point of guard 1 is cross-owner isolation.
_OWNER = "user_test_conv_owner"
_OTHER = "user_test_conv_other"


@pytest.mark.asyncio
class TestConversationStoreGuards:
    """ADR-078 §7 integration guards 1, 2, 6 against a live graph."""

    @pytest_asyncio.fixture
    async def conversation_service(self, neo4j_driver, clean_neo4j) -> ConversationService:
        """Real service over the real thin backend on the test driver."""
        return ConversationService(ConversationBackend(neo4j_driver))

    @pytest_asyncio.fixture
    async def owners(self, neo4j_driver, clean_neo4j):
        """Create the two owner User nodes (clean_neo4j preserves :User nodes)."""
        async with neo4j_driver.session() as session:
            await session.run(
                """
                UNWIND $uids AS uid
                MERGE (u:User {uid: uid})
                ON CREATE SET u.title = uid, u.created_at = datetime()
                """,
                uids=[_OWNER, _OTHER],
            )
        yield {"owner": _OWNER, "other": _OTHER}
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (u:User) WHERE u.uid IN $uids DETACH DELETE u",
                uids=[_OWNER, _OTHER],
            )

    # -- helpers ------------------------------------------------------------

    async def _count(self, driver, query: str, **params) -> int:
        async with driver.session() as session:
            result = await session.run(query, params)
            record = await result.single()
            return int(record["n"]) if record else 0

    # -- Guard 1: owner-visibility symmetry --------------------------------

    async def test_owner_visibility_symmetry(self, conversation_service, owners) -> None:
        owner, other = owners["owner"], owners["other"]

        # Owner creates two sessions; the other user creates one of their own.
        owned_a = (
            await conversation_service.create_session(
                owner, CONVERSATION_KIND_DISCUSSION, "Owned A", "{}"
            )
        ).value
        owned_b = (
            await conversation_service.create_session(
                owner, CONVERSATION_KIND_DISCUSSION, "Owned B", "{}"
            )
        ).value
        foreign = (
            await conversation_service.create_session(
                other, CONVERSATION_KIND_DISCUSSION, "Foreign", "{}"
            )
        ).value

        # Every session the owner owns appears in the owner's revisit list...
        owner_list = (await conversation_service.list_sessions(owner)).value
        owner_ids = {s.session_id for s in owner_list}
        assert owned_a.session_id in owner_ids
        assert owned_b.session_id in owner_ids
        # ...and the other user's session is NOT visible to the owner.
        assert foreign.session_id not in owner_ids
        # Symmetry: the other user sees only their own.
        other_ids = {s.session_id for s in (await conversation_service.list_sessions(other)).value}
        assert other_ids == {foreign.session_id}

        # A direct fetch of the foreign session BY the owner is not-found.
        # get_session maps a non-owner to Ok(None) (the route turns None → 404).
        foreign_get = await conversation_service.get_session(foreign.session_id, owner)
        assert not foreign_get.is_error
        assert foreign_get.value is None
        # get_turns on a non-owned session is an explicit NOT_FOUND failure.
        foreign_turns = await conversation_service.get_turns(foreign.session_id, owner)
        assert foreign_turns.is_error
        assert foreign_turns.expect_error().category is ErrorCategory.NOT_FOUND

        # The owner CAN fetch their own session + (empty) turns — positive control.
        assert (await conversation_service.get_session(owned_a.session_id, owner)).value is not None
        assert (await conversation_service.get_turns(owned_a.session_id, owner)).value == []

    # -- Guard 2: delete completeness --------------------------------------

    async def test_delete_removes_session_and_all_turns(
        self, conversation_service, owners, neo4j_driver
    ) -> None:
        owner = owners["owner"]
        session = (
            await conversation_service.create_session(
                owner, CONVERSATION_KIND_DISCUSSION, "To delete", "{}"
            )
        ).value
        sid = session.session_id

        # Two exchanges → four turns hanging off this session.
        assert not (await conversation_service.append_exchange(sid, owner, "u1", "a1")).is_error
        assert not (await conversation_service.append_exchange(sid, owner, "u2", "a2")).is_error
        assert (
            await self._count(
                neo4j_driver,
                "MATCH (:ConversationSession {session_id: $sid})-[:HAS_TURN]->(t) "
                "RETURN count(t) AS n",
                sid=sid,
            )
            == 4
        )

        deleted = await conversation_service.delete_session(sid, owner)
        assert deleted.value is True

        # The session is gone from the revisit list...
        owner_ids = {s.session_id for s in (await conversation_service.list_sessions(owner)).value}
        assert sid not in owner_ids

        # ...the :ConversationSession node is gone...
        assert (
            await self._count(
                neo4j_driver,
                "MATCH (s:ConversationSession {session_id: $sid}) RETURN count(s) AS n",
                sid=sid,
            )
            == 0
        )
        # ...and NO orphaned :ConversationTurn nodes survive (the completeness claim).
        assert (
            await self._count(
                neo4j_driver,
                "MATCH (t:ConversationTurn {session_id: $sid}) RETURN count(t) AS n",
                sid=sid,
            )
            == 0
        )

        # Deleting an absent / non-owned session is a benign False, never a crash.
        assert (await conversation_service.delete_session(sid, owner)).value is False

    # -- Guard 6: no enrichment edges --------------------------------------

    async def test_no_enrichment_edges_from_turns(
        self, conversation_service, owners, neo4j_driver
    ) -> None:
        owner = owners["owner"]

        # Plant an :Entity in the graph so "zero edges to :Entity" is a real
        # assertion (a turn COULD point at it if the store were understanding-wired).
        async with neo4j_driver.session() as session:
            await session.run(
                """
                CREATE (:Entity:Ku {uid: 'ku_conv_guard_probe', entity_type: 'ku',
                                    title: 'Guard probe concept', created_at: datetime()})
                """
            )

        created = (
            await conversation_service.create_session(
                owner, CONVERSATION_KIND_DISCUSSION, "Discuss the probe", "{}"
            )
        ).value
        # A create + one follow-up exchange — the full write path guard 6 covers.
        exchange = await conversation_service.append_exchange(
            created.session_id, owner, "Tell me about the probe concept", "Here is the probe."
        )
        assert not exchange.is_error

        # ZERO edges of ANY type from any :ConversationTurn to any :Entity.
        assert (
            await self._count(
                neo4j_driver,
                "MATCH (:ConversationTurn)-[r]->(:Entity) RETURN count(r) AS n",
            )
            == 0
        )
        # ...in either direction (an enrichment writer could point the other way).
        assert (
            await self._count(
                neo4j_driver,
                "MATCH (:Entity)-[r]->(:ConversationTurn) RETURN count(r) AS n",
            )
            == 0
        )
        # Named understanding edges specifically: none anywhere on a turn.
        assert (
            await self._count(
                neo4j_driver,
                "MATCH (:ConversationTurn)-[r:MENTIONS|APPLIES_KNOWLEDGE|ANCHORED_TO]-() "
                "RETURN count(r) AS n",
            )
            == 0
        )
        # The turn's ONLY relationship is the inbound HAS_TURN from its session —
        # proof the node is a leaf w.r.t. understanding, not silently enriched.
        turn_rel_types = set()
        async with neo4j_driver.session() as session:
            result = await session.run(
                "MATCH (:ConversationTurn)-[r]-() RETURN DISTINCT type(r) AS t"
            )
            async for record in result:
                turn_rel_types.add(record["t"])
        assert turn_rel_types == {"HAS_TURN"}

        # Sanity: the exchange really did persist (guard 6 is meaningful only if
        # turns exist) and carries the expected roles.
        turns = (await conversation_service.get_turns(created.session_id, owner)).value
        assert [t.role for t in turns] == [ROLE_USER, ROLE_ASSISTANT]
