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

Guard **7** (added 2026-07-13, ADR-078 §7 opt-in amendment) is the load-bearing
"not saved by default" proof and lives here too: driving the REAL journals route
handlers over the REAL store (LLM mocked), opening and continuing a discussion
creates **zero** ``:ConversationSession`` / ``:ConversationTurn`` nodes — only an
explicit ``POST /journals/save`` writes. It fails loudly if any door ever
auto-creates a session again (the exact P2 regression this arc reverts).

These drive the REAL ``ConversationService`` + ``ConversationBackend`` against the
session-scoped Docker Neo4j container (``tests/integration/conftest.py``). The
store is CORE-safe — no LLM, no embeddings — so nothing here needs API keys.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from adapters.persistence.neo4j.backends.conversation_backend import ConversationBackend
from core.models.conversation import CONVERSATION_KIND_DISCUSSION, ROLE_ASSISTANT, ROLE_USER
from core.services.conversation import ConversationService
from core.utils.result_simplified import ErrorCategory, Result
from tests.fixtures.csrf import attach_csrf

# Two distinct owners — the whole point of guard 1 is cross-owner isolation.
_OWNER = "user_test_conv_owner"
_OTHER = "user_test_conv_other"


def _journal_request(user_uid: str, form: dict[str, str], *, hx: bool = False) -> Any:
    """A minimal request the journals handlers can auth + read a form from.

    ``hx=True`` sets the ``HX-Request`` header so page routes (e.g. continue)
    return the inline fragment instead of a full ``BasePage``.
    """
    from starlette.datastructures import FormData

    form_data = FormData(list(form.items()))

    async def _form() -> FormData:
        return form_data

    return attach_csrf(
        SimpleNamespace(
            method="POST",
            session={"user_uid": user_uid},
            url=SimpleNamespace(path="/journals/save"),
            query_params={},
            form=_form,
            cookies={},
            headers={"HX-Request": "true"} if hx else {},
        )
    )


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
                owner, CONVERSATION_KIND_DISCUSSION, "Owned A", "{}", "gpt-4o"
            )
        ).value
        owned_b = (
            await conversation_service.create_session(
                owner, CONVERSATION_KIND_DISCUSSION, "Owned B", "{}", "gpt-4o"
            )
        ).value
        foreign = (
            await conversation_service.create_session(
                other, CONVERSATION_KIND_DISCUSSION, "Foreign", "{}", "gpt-4o"
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
                owner, CONVERSATION_KIND_DISCUSSION, "To delete", "{}", "gpt-4o"
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
                owner, CONVERSATION_KIND_DISCUSSION, "Discuss the probe", "{}", "gpt-4o"
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

    # -- Switcher: the per-conversation model round-trips through real Cypher ----

    async def test_model_persists_and_updates(self, conversation_service, owners) -> None:
        # A Cypher property-name typo would silently store nothing and read back as
        # the default, so assert the VALUE round-trips through create → get → update.
        owner = owners["owner"]
        created = (
            await conversation_service.create_session(
                owner, CONVERSATION_KIND_DISCUSSION, "On models", "{}", "claude-sonnet-4-6"
            )
        ).value
        assert created.model == "claude-sonnet-4-6"

        fetched = (await conversation_service.get_session(created.session_id, owner)).value
        assert fetched is not None and fetched.model == "claude-sonnet-4-6"

        # A mid-thread switch (session-backed follow-up) co-persists the new model.
        await conversation_service.update_source_selection(
            created.session_id, owner, "{}", model="gpt-4o-mini"
        )
        reread = (await conversation_service.get_session(created.session_id, owner)).value
        assert reread is not None and reread.model == "gpt-4o-mini"


@pytest.mark.asyncio
class TestOptInPersistenceGuard:
    """ADR-078 §7 guard 7 — persistence is opt-in; only ``/journals/save`` writes.

    Drives the REAL journals route handlers over the REAL store (only the LLM +
    user lookup are mocked). Opening (``/journals/start``) and continuing
    (``/journals/follow-up``) a discussion must leave the store empty; the single
    explicit ``/journals/save`` is the only writer. This is the operational form
    of "not saved by default" against a live graph.
    """

    @pytest_asyncio.fixture
    async def owner_node(self, neo4j_driver, clean_neo4j):
        """The owner :User (clean_neo4j preserves :User nodes between tests)."""
        async with neo4j_driver.session() as session:
            await session.run(
                "MERGE (u:User {uid: $uid}) "
                "ON CREATE SET u.title = $uid, u.created_at = datetime()",
                uid=_OWNER,
            )
        yield _OWNER
        async with neo4j_driver.session() as session:
            await session.run("MATCH (u:User {uid: $uid}) DETACH DELETE u", uid=_OWNER)

    @pytest_asyncio.fixture
    def journal_handlers(self, neo4j_driver, clean_neo4j, monkeypatch) -> dict[str, Any]:
        """Register the journals routes with a REAL conversation store, LLM mocked."""
        # Pin enforcement ON — _journal_request stubs carry a real token pair.
        monkeypatch.setenv("SKUEL_CSRF_ENFORCE", "true")
        from adapters.inbound.journals_routes import create_journals_routes
        from adapters.inbound.rate_limit import reset_buckets_for_testing
        from core.services.journal.journal_service import JournalFollowUp

        reset_buckets_for_testing()

        services = MagicMock()
        services.user = MagicMock()
        user = MagicMock()
        user.journal_tier.is_founder.return_value = False
        # Real string identity so the continue route's page render is clean.
        user.journal_tier.value = "standard"
        user.display_name = "Owner"
        user.title = "Owner"
        services.user.get_user = AsyncMock(return_value=Result.ok(user))
        services.journal = MagicMock()
        services.journal.run_discussion = AsyncMock(
            return_value=Result.ok(JournalFollowUp(text="reply-1", sources=()))
        )
        services.journal.run_follow_up = AsyncMock(
            return_value=Result.ok(JournalFollowUp(text="reply-2", sources=()))
        )
        services.journal.suggestions_available = True
        services.batch_transcription = None
        services.user_entry_processor = None
        services.user_entry = MagicMock()
        # The one real collaborator — proves what actually lands in Neo4j.
        services.conversation = ConversationService(ConversationBackend(neo4j_driver))

        registered: dict[str, Any] = {}

        def rt_collector(path: str, *_a: Any, **_kw: Any) -> Any:
            def decorator(fn: Any) -> Any:
                registered[path] = fn
                return fn

            return decorator

        create_journals_routes(MagicMock(), rt_collector, services)
        return registered

    async def _count(self, driver, query: str, **params) -> int:
        async with driver.session() as session:
            result = await session.run(query, params)
            record = await result.single()
            return int(record["n"]) if record else 0

    async def test_unsaved_creates_zero_nodes_only_save_persists(
        self, journal_handlers, owner_node, neo4j_driver
    ) -> None:
        sessions_q = "MATCH (s:ConversationSession {user_uid: $u}) RETURN count(s) AS n"
        turns_q = "MATCH (t:ConversationTurn) RETURN count(t) AS n"

        # 1. Open a discussion (typed door). Ephemeral by default — zero nodes.
        await journal_handlers["/journals/start"](
            request=_journal_request(_OWNER, {"raw_entry": "First thought."})
        )
        assert await self._count(neo4j_driver, sessions_q, u=_OWNER) == 0
        assert await self._count(neo4j_driver, turns_q) == 0

        # 2. A follow-up on the ephemeral transcript still persists nothing.
        transcript = json.dumps(
            [
                {"role": ROLE_USER, "content": "First thought."},
                {"role": ROLE_ASSISTANT, "content": "reply-1"},
            ]
        )
        await journal_handlers["/journals/follow-up"](
            request=_journal_request(_OWNER, {}),
            user_reply="Tell me more.",
            transcript_json=transcript,
        )
        assert await self._count(neo4j_driver, sessions_q, u=_OWNER) == 0
        assert await self._count(neo4j_driver, turns_q) == 0

        # 3. Save — the ONLY writer. Now the session + its turn pairs exist.
        full = json.dumps(
            [
                {"role": ROLE_USER, "content": "First thought."},
                {"role": ROLE_ASSISTANT, "content": "reply-1"},
                {"role": ROLE_USER, "content": "Tell me more."},
                {"role": ROLE_ASSISTANT, "content": "reply-2"},
            ]
        )
        await journal_handlers["/journals/save"](
            request=_journal_request(_OWNER, {}),
            transcript_json=full,
            title="Saved discussion",
        )
        assert await self._count(neo4j_driver, sessions_q, u=_OWNER) == 1
        assert await self._count(neo4j_driver, turns_q) == 4

        # The saved turns landed in order with the expected roles (the fold from
        # transcript → (user, assistant) pairs is faithful).
        async with neo4j_driver.session() as session:
            result = await session.run(
                "MATCH (:ConversationSession {user_uid: $u})-[r:HAS_TURN]->(t:ConversationTurn) "
                "RETURN t.role AS role ORDER BY r.turn_number",
                u=_OWNER,
            )
            roles = [record["role"] async for record in result]
        assert roles == [ROLE_USER, ROLE_ASSISTANT, ROLE_USER, ROLE_ASSISTANT]

    async def test_saved_chat_round_trips_revisit_continue_delete(
        self, journal_handlers, owner_node, neo4j_driver
    ) -> None:
        """The full saved-chat lifecycle end to end through the routes (ADR-078 §5).

        Save → the chat is in the revisit list and its turns rehydrate on continue
        → delete removes the whole subtree. Proves revisit/continue/delete for a
        chat the user chose to save, against the live graph.
        """
        from fasthtml.common import to_xml

        full = json.dumps(
            [
                {"role": ROLE_USER, "content": "opening line"},
                {"role": ROLE_ASSISTANT, "content": "assistant reply"},
            ]
        )
        await journal_handlers["/journals/save"](
            request=_journal_request(_OWNER, {}), transcript_json=full, title="Round trip"
        )

        # The session id is minted server-side; read it back from the graph.
        async with neo4j_driver.session() as session:
            record = await (
                await session.run(
                    "MATCH (:User {uid: $u})-[:HAS_SESSION]->(s:ConversationSession) "
                    "RETURN s.session_id AS sid",
                    u=_OWNER,
                )
            ).single()
        sid = record["sid"]
        assert sid

        # Continue (GET route, HX fragment) rehydrates the workspace from the
        # stored turns AND lists the saved chat in the revisit sidebar.
        continued = await journal_handlers["/journals/discussion/{session_id}"](
            request=_journal_request(_OWNER, {}, hx=True), session_id=sid
        )
        html = to_xml(continued)
        assert "opening line" in html and "assistant reply" in html
        # Prove *revisit* specifically: the session's own row is in the sidebar
        # discussions panel (its unique row marker, not just the title — which
        # also renders in the composer's hidden field). (Codex #640 P2.)
        assert f'data-discussion-row="{sid}"' in html

        # Delete (POST route) drops the whole subtree — session AND turns gone.
        await journal_handlers["/journals/discussion/{session_id}/delete"](
            request=_journal_request(_OWNER, {}), session_id=sid
        )
        assert (
            await self._count(
                neo4j_driver,
                "MATCH (s:ConversationSession {user_uid: $u}) RETURN count(s) AS n",
                u=_OWNER,
            )
            == 0
        )
        assert (
            await self._count(neo4j_driver, "MATCH (t:ConversationTurn) RETURN count(t) AS n") == 0
        )
